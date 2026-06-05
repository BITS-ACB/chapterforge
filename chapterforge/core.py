"""Core (UI-free) logic for ChapterForge.

Responsibilities:
* discover and natural-sort the MP3 files in a folder
* probe each file for duration and stream parameters (via ffprobe)
* concatenate them into a single master MP3 (lossless `-c copy` when the
  streams are compatible, otherwise a clean re-encode through the concat
  filter)
* write the master's ID3v2 tags and one ID3v2 CHAP frame per source file
  plus a top-level ordered CTOC, using each source filename as the title.

Everything here is deterministic and testable without wxPython.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field, replace
from typing import Callable, List, Optional, Sequence, Tuple

from mutagen.id3 import (
    ID3,
    APIC,
    CHAP,
    COMM,
    CTOC,
    CTOCFlags,
    TALB,
    TCON,
    TDRC,
    TIT2,
    TLEN,
    TPE1,
    TPE2,
    WXXX,
)
from mutagen.mp3 import MP3

# ---------------------------------------------------------------------------
# Tool discovery
# ---------------------------------------------------------------------------

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _candidate_dirs() -> list:
    """Directories to search for bundled ffmpeg/ffprobe before falling back
    to PATH. Supports PyInstaller (sys._MEIPASS / executable dir)."""
    dirs = []
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        dirs += [exe_dir, os.path.join(exe_dir, "bin")]
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            dirs += [meipass, os.path.join(meipass, "bin")]
    here = os.path.dirname(os.path.abspath(__file__))
    dirs += [here, os.path.join(here, "bin"), os.path.join(here, "..", "bin")]
    return dirs


def _find_tool(name: str) -> str:
    """Return the path to an ffmpeg-family tool or raise a friendly error.

    Prefers a copy bundled alongside the application (so a shipped build is
    self-contained) and falls back to whatever is on the system PATH.
    """
    exe = name + (".exe" if os.name == "nt" else "")
    for d in _candidate_dirs():
        candidate = os.path.join(d, exe)
        if os.path.isfile(candidate):
            return candidate
    found = shutil.which(name)
    if not found:
        raise FFmpegNotFoundError(
            f"Could not find '{name}'. Install FFmpeg and make sure it is on your PATH."
        )
    return found


def _run(cmd: Sequence[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=CREATE_NO_WINDOW,
        **kwargs,
    )


def _tool_version(name: str) -> str:
    """Return the path + first version line of an ffmpeg-family tool."""
    path = _find_tool(name)
    try:
        proc = _run([path, "-version"])
        first = (proc.stdout or b"").decode("utf-8", "replace").splitlines()
        version = first[0] if first else "(unknown)"
    except Exception:
        version = "(unknown)"
    return f"{version}  [{path}]"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ChapterForgeError(Exception):
    """Base class for expected, user-facing errors."""


class FFmpegNotFoundError(ChapterForgeError):
    pass


class NoAudioFilesError(ChapterForgeError):
    pass


class BuildCancelled(ChapterForgeError):
    pass


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Mp3Item:
    """A single source MP3 and everything we learned by probing it."""

    path: str
    title: str
    duration: float  # seconds
    codec_name: str = "mp3"
    sample_rate: int = 0
    channels: int = 0
    channel_layout: str = ""
    error: str = ""
    file_title: str = ""      # title derived from the filename
    embedded_title: str = ""  # title read from the file's ID3 tag, if any
    edited: bool = False      # True once the user renames this chapter
    url: str = ""             # optional per-chapter link (Podcasting 2.0)
    img: str = ""             # optional per-chapter image (Podcasting 2.0)

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)

    @property
    def duration_ms(self) -> int:
        return int(round(self.duration * 1000))


@dataclass
class Chapter:
    """A computed chapter boundary in the master file."""

    index: int
    title: str
    start_ms: int
    end_ms: int
    url: str = ""   # optional per-chapter link (Podcasting 2.0)
    img: str = ""   # optional per-chapter image (Podcasting 2.0)

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass
class Tags:
    """ID3 tags to write onto the master file."""

    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    genre: str = ""
    year: str = ""
    comment: str = ""
    cover_path: str = ""


@dataclass
class BuildResult:
    output_path: str
    chapters: List[Chapter]
    total_ms: int
    reencoded: bool
    target_sample_rate: int = 0
    target_channels: int = 0


class Canceller:
    """Cooperative cancellation shared between the UI and a running build."""

    def __init__(self) -> None:
        self._cancelled = False
        self._proc: Optional[subprocess.Popen] = None

    def cancel(self) -> None:
        self._cancelled = True
        proc = self._proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def _bind(self, proc: subprocess.Popen) -> None:
        self._proc = proc
        if self._cancelled and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

    def _check(self) -> None:
        if self._cancelled:
            raise BuildCancelled("Build cancelled.")


# ---------------------------------------------------------------------------
# Natural sort
# ---------------------------------------------------------------------------

_NUM_RE = re.compile(r"(\d+)")


def natural_key(text: str):
    """Sort key so that 'track2' precedes 'track10'."""
    return [
        int(part) if part.isdigit() else part.lower()
        for part in _NUM_RE.split(text)
    ]


def title_from_filename(path: str) -> str:
    """Derive a human chapter title from a filename.

    Strips the extension, replaces underscores with spaces and trims a common
    leading track-number prefix like '01 - ', '01.', '01_' while keeping the
    rest of the name intact.
    """
    stem = os.path.splitext(os.path.basename(path))[0]
    # Strip a leading track-number prefix: '01 - ', '02_', '03.', '4) ',
    # or a bare '01 ' / '1 ' before a word.  Four-digit years like '1984'
    # are left alone because \d{1,3} only matches up to three digits.
    cleaned = re.sub(
        r"^\s*\d{1,3}\s*(?:[-._)]+\s*|\s+(?=[A-Za-zÀ-ɏ]))", "", stem)
    cleaned = cleaned.replace("_", " ").strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    # If nothing meaningful remains (e.g. file was named "01.mp3"), return ""
    # so the caller can substitute a generated title like "Chapter N".
    return cleaned


# ---------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------


def probe_file(path: str) -> Mp3Item:
    """Probe a single MP3 file for duration and stream parameters."""
    ffprobe = _find_tool("ffprobe")
    cmd = [
        ffprobe,
        "-v", "error",
        "-select_streams", "a:0",
        "-show_entries",
        "stream=codec_name,sample_rate,channels,channel_layout:"
        "format=duration:format_tags=title",
        "-of", "json",
        path,
    ]
    file_title = title_from_filename(path)
    item = Mp3Item(path=path, title=file_title, duration=0.0,
                   file_title=file_title)
    try:
        proc = _run(cmd)
        if proc.returncode != 0:
            item.error = proc.stderr.decode("utf-8", "replace").strip() or "ffprobe failed"
            return item
        data = json.loads(proc.stdout.decode("utf-8", "replace") or "{}")
    except Exception as exc:  # pragma: no cover - defensive
        item.error = str(exc)
        return item

    streams = data.get("streams") or []
    if not streams:
        item.error = "No audio stream found."
        return item
    stream = streams[0]
    item.codec_name = stream.get("codec_name", "") or ""
    item.sample_rate = int(stream.get("sample_rate") or 0)
    item.channels = int(stream.get("channels") or 0)
    item.channel_layout = stream.get("channel_layout", "") or ""

    fmt = data.get("format", {})
    tags = fmt.get("tags") or {}
    for key, value in tags.items():
        if key.lower() == "title" and value:
            item.embedded_title = str(value).strip()
            break

    duration = fmt.get("duration")
    try:
        item.duration = float(duration)
    except (TypeError, ValueError):
        item.duration = 0.0
    if item.duration <= 0:
        item.error = "Could not determine a positive duration."
    return item


def is_probable_master(name: str, folder: str) -> bool:
    """Heuristic: does *name* look like a previously-built master in *folder*?

    Recognises a file named after the folder (e.g. ``My Book.mp3`` inside
    ``My Book``), the suggested output name (``<folder> - Master.mp3``) and any
    ``… - Master.mp3``. Used to avoid folding a prior master back in as a
    chapter.
    """
    base = os.path.basename(os.path.normpath(folder)).strip().lower()
    stem = os.path.splitext(os.path.basename(name))[0].strip().lower()
    if base and stem == base:
        return True
    if base and stem == f"{base} - master":
        return True
    if stem.endswith(" - master") or stem.endswith("- master"):
        return True
    return False


def scan_folder_detailed(folder: str, exclude_masters: bool = True
                         ) -> Tuple[List[Mp3Item], List[str]]:
    """Probe every ``.mp3`` in *folder*; return ``(items, skipped_master_names)``.

    A likely previously-built master (see :func:`is_probable_master`) is skipped
    so it is not turned into a chapter - unless skipping would leave nothing, in
    which case every file is kept.
    """
    if not os.path.isdir(folder):
        raise NoAudioFilesError(f"Not a folder: {folder}")
    names = [
        n for n in os.listdir(folder)
        if n.lower().endswith(".mp3") and os.path.isfile(os.path.join(folder, n))
    ]
    names.sort(key=natural_key)

    skipped: List[str] = []
    if exclude_masters:
        kept = [n for n in names if not is_probable_master(n, folder)]
        # Never skip everything (e.g. a folder whose files all end in 'master').
        if kept and len(kept) < len(names):
            skipped = [n for n in names if is_probable_master(n, folder)]
            names = kept

    items = [probe_file(os.path.join(folder, n)) for n in names]
    return items, skipped


def scan_folder(folder: str, exclude_masters: bool = True) -> List[Mp3Item]:
    """Return probed, naturally-sorted Mp3Items for the chapter files in *folder*.

    By default a likely previously-built master is excluded (see
    :func:`scan_folder_detailed`).
    """
    items, _ = scan_folder_detailed(folder, exclude_masters=exclude_masters)
    return items


def items_from_entries(entries: Sequence) -> List[Mp3Item]:
    """Probe an explicit, ordered list of ``(path, title)`` pairs.

    A non-empty *title* marks the item as user-specified (``edited=True``) so a
    later title-source change won't overwrite it.
    """
    items: List[Mp3Item] = []
    for path, title in entries:
        item = probe_file(path)
        if title:
            item.title = title
            item.edited = True
        items.append(item)
    return items


TITLE_SOURCE_FILENAME = "filename"
TITLE_SOURCE_EMBEDDED = "embedded"


def apply_title_source(items: Sequence[Mp3Item], source: str,
                       respect_edits: bool = True) -> None:
    """Set each item's active *title* from the chosen source.

    ``respect_edits`` keeps any chapter the user has manually renamed. When the
    embedded tag is empty the filename-derived title is used as a fallback.
    """
    for it in items:
        if respect_edits and it.edited:
            continue
        if source == TITLE_SOURCE_EMBEDDED and it.embedded_title:
            it.title = it.embedded_title
        else:
            it.title = it.file_title or it.title


_COVER_NAMES = ("cover", "folder", "front", "albumart", "album", "artwork")


def find_cover(folder: str) -> str:
    """Return a likely cover-image path in *folder*, or '' if none is found."""
    if not os.path.isdir(folder):
        return ""
    try:
        entries = os.listdir(folder)
    except OSError:
        return ""
    candidates = {}
    for name in entries:
        stem, ext = os.path.splitext(name)
        if ext.lower() in _COVER_MIME:
            candidates[stem.lower()] = os.path.join(folder, name)
    for preferred in _COVER_NAMES:
        if preferred in candidates:
            return candidates[preferred]
    return ""



# ---------------------------------------------------------------------------
# Chapter computation
# ---------------------------------------------------------------------------


def compute_chapters(items: Sequence[Mp3Item]) -> List[Chapter]:
    """Cumulative chapter boundaries (ms) from item durations."""
    chapters: List[Chapter] = []
    cursor = 0
    for i, item in enumerate(items):
        start = cursor
        end = start + max(item.duration_ms, 0)
        chapters.append(Chapter(index=i, title=item.title, start_ms=start,
                                end_ms=end, url=item.url, img=item.img))
        cursor = end
    return chapters


# ---------------------------------------------------------------------------
# Concatenation
# ---------------------------------------------------------------------------


def _streams_uniform(items: Sequence[Mp3Item]) -> bool:
    """True if every item is a single mp3 stream sharing sample rate/channels."""
    first = items[0]
    if first.codec_name != "mp3" or first.sample_rate <= 0 or first.channels <= 0:
        return False
    for it in items:
        if it.codec_name != "mp3":
            return False
        if it.sample_rate != first.sample_rate:
            return False
        if it.channels != first.channels:
            return False
        if it.channel_layout != first.channel_layout:
            return False
    return True


def _ffmpeg_escape_concat(path: str) -> str:
    abspath = os.path.abspath(path).replace("\\", "/")
    return abspath.replace("'", "'\\''")


def _parse_progress(line: str) -> Optional[int]:
    """Return out time in ms from an ffmpeg -progress line, if present."""
    line = line.strip()
    if line.startswith("out_time_us="):
        try:
            return int(line.split("=", 1)[1]) // 1000
        except ValueError:
            return None
    if line.startswith("out_time_ms="):
        # ffmpeg's out_time_ms is actually microseconds in some builds.
        try:
            value = int(line.split("=", 1)[1])
            return value // 1000 if value > 10_000_000 else value
        except ValueError:
            return None
    return None


def _stream_ffmpeg(cmd: List[str], total_ms: int, canceller: Canceller,
                   progress: Optional[Callable[[float], None]]) -> None:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW,
        bufsize=1,
        universal_newlines=True,
    )
    canceller._bind(proc)
    tail: List[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        tail.append(line)
        if len(tail) > 40:
            tail.pop(0)
        if progress and total_ms > 0:
            out_ms = _parse_progress(line)
            if out_ms is not None:
                progress(max(0.0, min(1.0, out_ms / total_ms)))
    proc.wait()
    if canceller.cancelled:
        raise BuildCancelled("Build cancelled.")
    if proc.returncode != 0:
        raise ChapterForgeError(
            "FFmpeg failed:\n" + "".join(tail).strip()
        )
    if progress:
        progress(1.0)


def _concat_copy(items: Sequence[Mp3Item], output: str, total_ms: int,
                 canceller: Canceller,
                 progress: Optional[Callable[[float], None]]) -> None:
    ffmpeg = _find_tool("ffmpeg")
    fd, list_path = tempfile.mkstemp(suffix=".txt", prefix="chapterforge_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for it in items:
                fh.write(f"file '{_ffmpeg_escape_concat(it.path)}'\n")
        cmd = [
            ffmpeg, "-hide_banner", "-nostdin", "-y",
            "-f", "concat", "-safe", "0", "-i", list_path,
            "-map", "0:a", "-c", "copy", "-map_metadata", "-1",
            "-progress", "pipe:1", "-nostats",
            output,
        ]
        _stream_ffmpeg(cmd, total_ms, canceller, progress)
    finally:
        try:
            os.remove(list_path)
        except OSError:
            pass


def _concat_reencode(items: Sequence[Mp3Item], output: str, total_ms: int,
                     target_sr: int, target_ch: int, bitrate: str,
                     canceller: Canceller,
                     progress: Optional[Callable[[float], None]],
                     normalize: bool = False, gap_ms: int = 0) -> None:
    ffmpeg = _find_tool("ffmpeg")
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y"]
    for it in items:
        cmd += ["-i", it.path]
    layout = "stereo" if target_ch == 2 else "mono"
    gap_s = max(0, gap_ms) / 1000.0
    parts = []
    for i in range(len(items)):
        chain = (f"[{i}:a]aresample={target_sr},"
                 f"aformat=sample_fmts=s16:channel_layouts={layout}")
        if gap_s > 0 and i < len(items) - 1:
            chain += f",apad=pad_dur={gap_s:g}"
        parts.append(chain + f"[a{i}]")
    concat_in = "".join(f"[a{i}]" for i in range(len(items)))
    graph = ";".join(parts) + ";" + concat_in + f"concat=n={len(items)}:v=0:a=1"
    if normalize:
        graph += "[cat];[cat]loudnorm=I=-16:TP=-1.5:LRA=11[out]"
    else:
        graph += "[out]"
    cmd += [
        "-filter_complex", graph,
        "-map", "[out]",
        "-c:a", "libmp3lame", "-b:a", bitrate,
        "-map_metadata", "-1",
        "-progress", "pipe:1", "-nostats",
        output,
    ]
    _stream_ffmpeg(cmd, total_ms, canceller, progress)


def _choose_target(items: Sequence[Mp3Item]) -> tuple[int, int]:
    rates: dict[int, int] = {}
    max_ch = 1
    for it in items:
        if it.sample_rate > 0:
            rates[it.sample_rate] = rates.get(it.sample_rate, 0) + 1
        if it.channels:
            max_ch = max(max_ch, it.channels)
    target_sr = max(rates, key=rates.get) if rates else 44100
    target_ch = 2 if max_ch >= 2 else 1
    return target_sr, target_ch


# ---------------------------------------------------------------------------
# Tagging
# ---------------------------------------------------------------------------

_COVER_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def write_tags_and_chapters(output: str, chapters: Sequence[Chapter],
                            tags: Tags, total_ms: int) -> None:
    """Write ID3v2.3 tags plus CHAP/CTOC chapter frames onto *output*."""
    id3 = ID3()

    if tags.title:
        id3.add(TIT2(encoding=3, text=[tags.title]))
    if tags.artist:
        id3.add(TPE1(encoding=3, text=[tags.artist]))
    if tags.album:
        id3.add(TALB(encoding=3, text=[tags.album]))
    if tags.album_artist:
        id3.add(TPE2(encoding=3, text=[tags.album_artist]))
    if tags.genre:
        id3.add(TCON(encoding=3, text=[tags.genre]))
    if tags.year:
        id3.add(TDRC(encoding=3, text=[tags.year]))
    if tags.comment:
        id3.add(COMM(encoding=3, lang="eng", desc="", text=[tags.comment]))
    if total_ms > 0:
        id3.add(TLEN(encoding=3, text=[str(int(total_ms))]))

    if tags.cover_path:
        ext = os.path.splitext(tags.cover_path)[1].lower()
        mime = _COVER_MIME.get(ext)
        if mime and os.path.isfile(tags.cover_path):
            with open(tags.cover_path, "rb") as fh:
                id3.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=fh.read()))

    element_ids = []
    for i, ch in enumerate(chapters):
        eid = f"chp{i:04d}"
        element_ids.append(eid)
        id3.add(CHAP(
            element_id=eid,
            start_time=int(ch.start_ms),
            end_time=int(ch.end_ms),
            start_offset=0xFFFFFFFF,
            end_offset=0xFFFFFFFF,
            sub_frames=[TIT2(encoding=3, text=[ch.title])],
        ))

    if element_ids:
        id3.add(CTOC(
            element_id="toc",
            flags=CTOCFlags.TOP_LEVEL | CTOCFlags.ORDERED,
            child_element_ids=element_ids,
            sub_frames=[TIT2(encoding=3, text=["Chapters"])],
        ))

    id3.save(output, v2_version=3)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


M4B_EXTS = {".m4b", ".m4a", ".mp4"}


def output_format(output_path: str) -> str:
    """Return 'm4b' for MP4-family outputs, otherwise 'mp3'."""
    return "m4b" if os.path.splitext(output_path)[1].lower() in M4B_EXTS else "mp3"


def build_master(items: Sequence[Mp3Item], output_path: str, tags: Tags,
                 chapters: Optional[Sequence[Chapter]] = None,
                 bitrate: str = "192k",
                 normalize: bool = False,
                 scale_chapters: bool = True,
                 gap_ms: int = 0,
                 canceller: Optional[Canceller] = None,
                 progress: Optional[Callable[[float], None]] = None) -> BuildResult:
    """Build a master file with tags and chapter markers.

    Dispatches on *output_path*'s extension: ``.m4b``/``.m4a``/``.mp4`` produce
    an AAC audiobook (chapters via MP4 metadata); anything else produces an MP3
    (chapters via ID3v2 CHAP/CTOC).

    *chapters* may be supplied to honour user edits (re-ordered or renamed
    titles); otherwise they are computed from the items in order. The order of
    *items* is what is concatenated, so callers that reorder chapters must
    reorder *items* to match. Set *scale_chapters* False when *chapters* already
    sit on the real media timeline (e.g. from silence detection) so boundaries
    are clamped but not proportionally rescaled. *gap_ms* inserts that many
    milliseconds of silence between chapters (forces a re-encode).
    """
    if output_format(output_path) == "m4b":
        return build_m4b(items, output_path, tags, chapters=chapters,
                         bitrate=bitrate, normalize=normalize,
                         scale_chapters=scale_chapters, gap_ms=gap_ms,
                         canceller=canceller, progress=progress)
    return build_mp3(items, output_path, tags, chapters=chapters,
                     bitrate=bitrate, normalize=normalize,
                     scale_chapters=scale_chapters, gap_ms=gap_ms,
                     canceller=canceller, progress=progress)


def build_mp3(items: Sequence[Mp3Item], output_path: str, tags: Tags,
              chapters: Optional[Sequence[Chapter]] = None,
              bitrate: str = "192k",
              normalize: bool = False,
              scale_chapters: bool = True,
              gap_ms: int = 0,
              canceller: Optional[Canceller] = None,
              progress: Optional[Callable[[float], None]] = None) -> BuildResult:
    """Concatenate *items* into an MP3 master with ID3v2 chapter markers."""
    items = list(items)
    canceller = canceller or Canceller()
    if not items:
        raise NoAudioFilesError("There are no MP3 files to build.")

    bad = [it for it in items if it.error or it.duration <= 0]
    if bad:
        names = ", ".join(it.filename for it in bad[:5])
        raise ChapterForgeError(f"Some files could not be used: {names}")

    canceller._check()

    if chapters is None:
        chapters = compute_chapters(items)
    chapters = list(chapters)
    if gap_ms > 0:
        if len(chapters) != len(items):
            raise ChapterForgeError(
                "Inter-chapter gaps require exactly one chapter per input file.")
        # Gaps shift every boundary; recompute on the gapped timeline while
        # keeping any user-edited titles/links.
        chapters = _chapters_with_gaps(items, gap_ms, base=chapters)
        scale_chapters = False
    total_ms = chapters[-1].end_ms if chapters else 0

    # ffmpeg writes to a temp file first so a cancel/failure never leaves a
    # half-written master in place.
    out_dir = os.path.dirname(os.path.abspath(output_path)) or "."
    os.makedirs(out_dir, exist_ok=True)
    fd, tmp_out = tempfile.mkstemp(suffix=".mp3", prefix="chapterforge_", dir=out_dir)
    os.close(fd)

    reencoded = False
    target_sr = target_ch = 0
    try:
        # Loudness normalisation or an inter-chapter gap requires decoding, so
        # either forces the re-encode path even when inputs are uniform.
        if _streams_uniform(items) and not normalize and gap_ms <= 0:
            _concat_copy(items, tmp_out, total_ms, canceller, progress)
        else:
            reencoded = True
            if _streams_uniform(items):
                target_sr = items[0].sample_rate
                target_ch = items[0].channels
            else:
                target_sr, target_ch = _choose_target(items)
            _concat_reencode(items, tmp_out, total_ms, target_sr, target_ch,
                             bitrate, canceller, progress, normalize=normalize,
                             gap_ms=gap_ms)

        canceller._check()

        # Reconcile chapter boundaries with the real encoded duration so the
        # final chapter never overshoots the file.
        actual_ms = _probe_duration_ms(tmp_out)
        if actual_ms > 0:
            chapters = _clamp_chapters(chapters, actual_ms, scale=scale_chapters)
            total_ms = actual_ms

        write_tags_and_chapters(tmp_out, chapters, tags, total_ms)

        if os.path.exists(output_path):
            os.remove(output_path)
        os.replace(tmp_out, output_path)
    except BaseException:
        if os.path.exists(tmp_out):
            try:
                os.remove(tmp_out)
            except OSError:
                pass
        raise

    return BuildResult(
        output_path=output_path,
        chapters=chapters,
        total_ms=total_ms,
        reencoded=reencoded,
        target_sample_rate=target_sr,
        target_channels=target_ch,
    )


def build_m4b(items: Sequence[Mp3Item], output_path: str, tags: Tags,
              chapters: Optional[Sequence[Chapter]] = None,
              bitrate: str = "192k",
              normalize: bool = False,
              scale_chapters: bool = True,
              gap_ms: int = 0,
              canceller: Optional[Canceller] = None,
              progress: Optional[Callable[[float], None]] = None) -> BuildResult:
    """Build an M4B/MP4 audiobook: AAC audio + MP4 chapters via ffmpeg metadata.

    Two ffmpeg passes: (1) concat + encode the sources to AAC, (2) mux an
    FFMETADATA file (tags + ``[CHAPTER]`` blocks) and optional cover art into
    the final container with ``-c copy``. Always re-encodes (MP3 -> AAC).
    *gap_ms* inserts that much silence between chapters.
    """
    items = list(items)
    canceller = canceller or Canceller()
    if not items:
        raise NoAudioFilesError("There are no MP3 files to build.")
    bad = [it for it in items if it.error or it.duration <= 0]
    if bad:
        names = ", ".join(it.filename for it in bad[:5])
        raise ChapterForgeError(f"Some files could not be used: {names}")
    canceller._check()

    if chapters is None:
        chapters = compute_chapters(items)
    chapters = list(chapters)
    if gap_ms > 0:
        if len(chapters) != len(items):
            raise ChapterForgeError(
                "Inter-chapter gaps require exactly one chapter per input file.")
        chapters = _chapters_with_gaps(items, gap_ms, base=chapters)
        scale_chapters = False
    total_ms = chapters[-1].end_ms if chapters else 0

    target_sr, target_ch = _choose_target(items)

    out_dir = os.path.dirname(os.path.abspath(output_path)) or "."
    os.makedirs(out_dir, exist_ok=True)
    fd, tmp_audio = tempfile.mkstemp(suffix=".m4a", prefix="chapterforge_", dir=out_dir)
    os.close(fd)
    fd, tmp_out = tempfile.mkstemp(suffix=".m4b", prefix="chapterforge_", dir=out_dir)
    os.close(fd)
    meta_path = tmp_audio + ".ffmeta"

    def encode_progress(frac: float) -> None:
        if progress:
            progress(max(0.0, min(1.0, frac)) * 0.9)

    try:
        # Pass 1: concat + AAC encode (progress 0.0 -> 0.9).
        _concat_aac(items, tmp_audio, total_ms, target_sr, target_ch, bitrate,
                    canceller, encode_progress, normalize=normalize,
                    gap_ms=gap_ms)
        canceller._check()

        actual_ms = _probe_duration_ms(tmp_audio)
        if actual_ms > 0:
            chapters = _clamp_chapters(chapters, actual_ms, scale=scale_chapters)
            total_ms = actual_ms

        _write_ffmetadata(meta_path, chapters, tags, total_ms)

        # Pass 2: mux metadata + chapters (+cover) with -c copy (progress -> 1.0).
        _mux_m4b(tmp_audio, meta_path, tags.cover_path, tmp_out, canceller)
        if progress:
            progress(1.0)
        canceller._check()

        if os.path.exists(output_path):
            os.remove(output_path)
        os.replace(tmp_out, output_path)
    except BaseException:
        for p in (tmp_out, tmp_audio, meta_path):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        raise
    finally:
        for p in (tmp_audio, meta_path):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

    return BuildResult(
        output_path=output_path,
        chapters=chapters,
        total_ms=total_ms,
        reencoded=True,
        target_sample_rate=target_sr,
        target_channels=target_ch,
    )


def _concat_aac(items: Sequence[Mp3Item], output: str, total_ms: int,
                target_sr: int, target_ch: int, bitrate: str,
                canceller: Canceller,
                progress: Optional[Callable[[float], None]],
                normalize: bool = False, gap_ms: int = 0) -> None:
    """Concatenate *items* and encode to AAC in an MP4 (.m4a) container."""
    ffmpeg = _find_tool("ffmpeg")
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y"]
    for it in items:
        cmd += ["-i", it.path]
    layout = "stereo" if target_ch == 2 else "mono"
    gap_s = max(0, gap_ms) / 1000.0
    parts = []
    for i in range(len(items)):
        chain = (f"[{i}:a]aresample={target_sr},"
                 f"aformat=sample_fmts=fltp:channel_layouts={layout}")
        if gap_s > 0 and i < len(items) - 1:
            chain += f",apad=pad_dur={gap_s:g}"
        parts.append(chain + f"[a{i}]")
    concat_in = "".join(f"[a{i}]" for i in range(len(items)))
    graph = ";".join(parts) + ";" + concat_in + f"concat=n={len(items)}:v=0:a=1"
    if normalize:
        graph += "[cat];[cat]loudnorm=I=-16:TP=-1.5:LRA=11[out]"
    else:
        graph += "[out]"
    cmd += [
        "-filter_complex", graph,
        "-map", "[out]",
        "-c:a", "aac", "-b:a", bitrate,
        "-map_metadata", "-1",
        "-f", "mp4",
        "-progress", "pipe:1", "-nostats",
        output,
    ]
    _stream_ffmpeg(cmd, total_ms, canceller, progress)


def _ffmeta_escape(value: str) -> str:
    """Escape a value for an FFMETADATA file (=, ;, #, \\ and newlines)."""
    out = []
    for ch in value:
        if ch in "=;#\\":
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\\n")
        else:
            out.append(ch)
    return "".join(out)


def _write_ffmetadata(path: str, chapters: Sequence[Chapter], tags: Tags,
                      total_ms: int) -> None:
    """Write an FFMETADATA1 file with global tags and [CHAPTER] blocks."""
    lines = [";FFMETADATA1"]
    meta = [
        ("title", tags.title), ("album", tags.album or tags.title),
        ("artist", tags.artist), ("album_artist", tags.album_artist or tags.artist),
        ("genre", tags.genre), ("date", tags.year), ("comment", tags.comment),
    ]
    for key, value in meta:
        if value:
            lines.append(f"{key}={_ffmeta_escape(value)}")
    for ch in chapters:
        start = max(0, int(ch.start_ms))
        end = max(start, min(int(ch.end_ms), total_ms))
        lines.append("[CHAPTER]")
        lines.append("TIMEBASE=1/1000")
        lines.append(f"START={start}")
        lines.append(f"END={end}")
        lines.append(f"title={_ffmeta_escape(ch.title)}")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


def _mux_m4b(audio_in: str, meta_path: str, cover_path: str, output: str,
             canceller: Canceller) -> None:
    """Mux audio + FFMETADATA (tags/chapters) + optional cover into *output*."""
    ffmpeg = _find_tool("ffmpeg")
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y",
           "-i", audio_in, "-i", meta_path]
    has_cover = bool(cover_path) and os.path.isfile(cover_path) and \
        os.path.splitext(cover_path)[1].lower() in _COVER_MIME
    if has_cover:
        cmd += ["-i", cover_path]
    cmd += ["-map", "0:a", "-map_metadata", "1", "-map_chapters", "1"]
    if has_cover:
        cmd += ["-map", "2:v", "-c:v", "mjpeg", "-disposition:v:0", "attached_pic"]
    cmd += ["-c:a", "copy", "-f", "mp4", output]
    _stream_ffmpeg(cmd, 0, canceller, None)


def _probe_duration_ms(path: str) -> int:
    """Return a media file's duration in ms, format-agnostic (via ffprobe).

    Falls back to mutagen for MP3 if ffprobe is unavailable. Works for both the
    MP3 and the M4B/MP4 output paths.
    """
    try:
        ffprobe = _find_tool("ffprobe")
        proc = _run([
            ffprobe, "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
        ])
        if proc.returncode == 0:
            value = proc.stdout.decode("utf-8", "replace").strip()
            if value and value.lower() != "n/a":
                return int(round(float(value) * 1000))
    except Exception:
        pass
    try:
        audio = MP3(path)
        return int(round(audio.info.length * 1000))
    except Exception:
        return 0


def _clamp_chapters(chapters: Sequence[Chapter], total_ms: int,
                    scale: bool = True) -> List[Chapter]:
    """Keep chapters monotonic and bounded by the real total duration.

    When *scale* is True (chapters estimated from summed source durations) the
    boundaries are scaled proportionally to the real encoded duration. When
    *scale* is False (chapters already on the real media timeline, e.g. from
    silence detection) boundaries are only clamped/ordered, never rescaled.
    """
    result = list(chapters)
    if not result:
        return result
    if scale:
        # Scale proportionally if the summed estimate differs from reality.
        estimated = result[-1].end_ms
        if estimated > 0 and abs(estimated - total_ms) > 0:
            ratio = total_ms / estimated
            cursor = 0
            scaled: List[Chapter] = []
            for ch in result:
                start = cursor
                end = int(round(ch.end_ms * ratio))
                end = max(end, start)
                scaled.append(replace(ch, start_ms=start, end_ms=end))
                cursor = end
            result = scaled
    else:
        # Absolute timeline: clamp into range and enforce monotonic order.
        cursor = 0
        clamped: List[Chapter] = []
        for ch in result:
            start = max(min(ch.start_ms, total_ms), cursor)
            end = max(min(ch.end_ms, total_ms), start)
            clamped.append(replace(ch, start_ms=start, end_ms=end))
            cursor = end
        result = clamped
    result[-1] = replace(result[-1], end_ms=total_ms)
    return result


# ---------------------------------------------------------------------------
# Small helpers used by the UI
# ---------------------------------------------------------------------------


def format_timestamp(ms: int) -> str:
    """Format milliseconds as H:MM:SS (or M:SS for short durations)."""
    total_seconds = int(round(ms / 1000))
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _atempo_filter(speed: float) -> str:
    """Build an FFmpeg atempo filter chain for *speed*.

    atempo only accepts values in [0.5, 100], so for extreme ratios we
    chain multiple filters.  For the speeds ChapterForge exposes (0.75-2.0)
    a single filter is always sufficient.
    """
    filters: list[str] = []
    s = speed
    while s > 2.0 + 1e-9:
        filters.append("atempo=2.0")
        s /= 2.0
    while s < 0.5 - 1e-9:
        filters.append("atempo=0.5")
        s /= 0.5
    filters.append(f"atempo={s:.6f}")
    return ",".join(filters)


def apply_tempo(src_path: str, speed: float, dst_path: str) -> bool:
    """Re-encode *src_path* at *speed* (preserving pitch) and write to *dst_path*.

    Uses FFmpeg's ``atempo`` filter, which performs time-stretching without
    the chipmunk / slow-motion pitch artefact.  Returns True on success.
    The output is always MP3 at 192 k.
    """
    ffmpeg = _find_tool("ffmpeg")
    cmd = [
        ffmpeg, "-y", "-i", src_path,
        "-filter:a", _atempo_filter(speed),
        "-c:a", "libmp3lame", "-b:a", "192k",
        "-vn",          # drop any cover-art video stream
        dst_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=600)
        return result.returncode == 0 and os.path.isfile(dst_path)
    except Exception:
        return False


def suggested_output_path(folder: str) -> str:
    base = os.path.basename(os.path.normpath(folder)) or "Master"
    return os.path.join(folder, f"{base} - Master.mp3")


def chapter_report_path(output_path: str) -> str:
    """The path of the human-readable chapter report for *output_path*."""
    stem = os.path.splitext(output_path)[0]
    return f"{stem} - chapters.txt"


def write_chapter_report(output_path: str, result: "BuildResult",
                         tags: "Tags", items: Optional[Sequence["Mp3Item"]] = None
                         ) -> str:
    """Write a readable ``… - chapters.txt`` next to a built master.

    Lists the tags, total duration and every chapter with its start time, so a
    user can see at a glance what was produced (handy for the background
    watcher). Returns the report path; best-effort (raises only on I/O error).
    """
    lines = [
        f"{__import__('chapterforge').__app_name__} - chapter report",
        "=" * 48,
        f"Master file : {os.path.basename(result.output_path)}",
        f"Built        : {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Total length : {format_timestamp(result.total_ms)}",
        f"Chapters     : {len(result.chapters)}",
        f"Mode         : {'re-encoded' if result.reencoded else 'lossless copy'}",
        "",
        "Tags",
        "-" * 48,
    ]
    for label, value in (("Title", tags.title), ("Artist", tags.artist),
                         ("Album", tags.album), ("Album artist", tags.album_artist),
                         ("Genre", tags.genre), ("Year", tags.year)):
        if value:
            lines.append(f"  {label:<12}: {value}")
    lines += ["", "Chapters", "-" * 48,
              f"  {'#':>3}  {'Start':>9}  {'Length':>9}  Title",
              f"  {'-'*3}  {'-'*9}  {'-'*9}  {'-'*5}"]
    for i, ch in enumerate(result.chapters, 1):
        lines.append(f"  {i:>3}  {format_timestamp(ch.start_ms):>9}  "
                     f"{format_timestamp(ch.duration_ms):>9}  {ch.title}")
    lines.append("")

    report_path = chapter_report_path(output_path)
    with open(report_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    return report_path


# ---------------------------------------------------------------------------
# Pre-flight validation
# ---------------------------------------------------------------------------


def preflight(items: Sequence[Mp3Item]) -> List[str]:
    """Return human-readable warnings about a set of source items.

    Non-fatal advisories (mixed formats force a re-encode, odd durations, etc.)
    so the GUI/CLI can surface them before a build. An empty list means the
    inputs look clean.
    """
    warnings: List[str] = []
    good = [it for it in items if not it.error and it.duration > 0]
    if not good:
        return warnings

    rates = {it.sample_rate for it in good if it.sample_rate > 0}
    chans = {it.channels for it in good if it.channels > 0}
    codecs = {it.codec_name for it in good if it.codec_name}
    if len(rates) > 1:
        warnings.append(
            "Source files have different sample rates "
            f"({', '.join(str(r) for r in sorted(rates))} Hz); the master will "
            "be re-encoded to a common rate.")
    if len(chans) > 1:
        warnings.append(
            "Source files mix mono and stereo; the master will be re-encoded.")
    if codecs - {"mp3"}:
        warnings.append(
            "Some sources are not MP3 (" + ", ".join(sorted(codecs - {"mp3"}))
            + "); they will be re-encoded.")

    tiny = [it for it in good if it.duration < 1.0]
    if tiny:
        warnings.append(
            f"{len(tiny)} file(s) are under 1 second - check they are real "
            "chapters (e.g. " + ", ".join(it.filename for it in tiny[:3]) + ").")

    untitled = [it for it in good if not it.title.strip()]
    if untitled:
        warnings.append(f"{len(untitled)} chapter(s) have an empty title.")

    titles = [it.title.strip().lower() for it in good if it.title.strip()]
    if len(titles) != len(set(titles)):
        warnings.append("Two or more chapters share the same title.")

    if len(good) > 300:
        warnings.append(
            f"This is a large book ({len(good)} chapters); the build may take a "
            "while and some players limit chapter counts.")
    return warnings


# ---------------------------------------------------------------------------
# Podcasting 2.0 chapters sidecar
# ---------------------------------------------------------------------------


def pod2_sidecar_path(output_path: str) -> str:
    """Path of the Podcasting 2.0 chapters JSON sidecar for *output_path*."""
    stem = os.path.splitext(output_path)[0]
    return f"{stem}.chapters.json"


def write_pod2_chapters(output_path: str, chapters: Sequence[Chapter],
                        total_ms: int = 0) -> str:
    """Write a Podcasting 2.0 ``…chapters.json`` sidecar next to *output_path*.

    Follows the podcast-namespace chapters spec: a top-level object with a
    ``version`` and a ``chapters`` array of ``{startTime, title, img?, url?}``
    where ``startTime`` is in seconds. Returns the sidecar path.
    """
    entries = []
    for ch in chapters:
        entry = {
            "startTime": round(max(0, int(ch.start_ms)) / 1000.0, 3),
            "title": ch.title,
        }
        if getattr(ch, "img", ""):
            entry["img"] = ch.img
        if getattr(ch, "url", ""):
            entry["url"] = ch.url
        entries.append(entry)
    data = {"version": "1.2.0", "chapters": entries}
    path = pod2_sidecar_path(output_path)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    return path


# ---------------------------------------------------------------------------
# Silence-based auto-chaptering
# ---------------------------------------------------------------------------

_SILENCE_START_RE = re.compile(r"silence_start:\s*([0-9.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*([0-9.]+)")


def detect_silence_chapters(path: str, noise_db: float = -30.0,
                            min_silence: float = 0.8,
                            min_chapter_ms: int = 5000,
                            title_prefix: str = "Chapter") -> List[Chapter]:
    """Split a single audio file into chapters at detected silences.

    Uses ffmpeg ``silencedetect``. A chapter boundary is placed at the midpoint
    of each qualifying silence. Chapters shorter than *min_chapter_ms* are
    merged into the previous one so brief gaps don't create slivers. Always
    returns at least one chapter spanning the whole file.
    """
    ffmpeg = _find_tool("ffmpeg")
    total_ms = _probe_duration_ms(path)
    if total_ms <= 0:
        raise ChapterForgeError("Could not read the audio file's duration.")

    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-i", path,
           "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}",
           "-f", "null", "-"]
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                          creationflags=CREATE_NO_WINDOW)
    text = proc.stderr.decode("utf-8", "replace")

    starts = [float(m) for m in _SILENCE_START_RE.findall(text)]
    ends = [float(m) for m in _SILENCE_END_RE.findall(text)]

    # Pair each silence start with the following end to get its midpoint.
    splits: List[int] = []
    ei = 0
    for s in starts:
        while ei < len(ends) and ends[ei] < s:
            ei += 1
        if ei < len(ends):
            mid_ms = int(round((s + ends[ei]) / 2.0 * 1000))
            ei += 1
        else:
            mid_ms = int(round(s * 1000))
        if 0 < mid_ms < total_ms:
            splits.append(mid_ms)

    boundaries = [0] + sorted(set(splits)) + [total_ms]
    # Merge boundaries that would create a too-short chapter.
    merged = [boundaries[0]]
    for b in boundaries[1:-1]:
        if b - merged[-1] >= min_chapter_ms:
            merged.append(b)
    merged.append(total_ms)
    if len(merged) >= 2 and merged[-1] - merged[-2] < min_chapter_ms and len(merged) > 2:
        merged.pop(-2)

    chapters: List[Chapter] = []
    for i in range(len(merged) - 1):
        chapters.append(Chapter(index=i, title=f"{title_prefix} {i + 1}",
                                start_ms=merged[i], end_ms=merged[i + 1]))
    return chapters


# ---------------------------------------------------------------------------
# Reading back an existing chaptered file (for editing)
# ---------------------------------------------------------------------------


def read_master(path: str) -> Tuple[Tags, List[Chapter], int]:
    """Read tags + chapters from an existing chaptered file.

    Supports MP3 (ID3v2 CHAP/CTOC) and M4B/MP4 (via ffprobe). Returns
    ``(tags, chapters, total_ms)``. Raises :class:`ChapterForgeError` if the
    file cannot be read.
    """
    if not os.path.isfile(path):
        raise ChapterForgeError(f"File not found: {path}")
    if output_format(path) == "m4b":
        return _read_master_mp4(path)
    return _read_master_mp3(path)


def _read_master_mp3(path: str) -> Tuple[Tags, List[Chapter], int]:
    try:
        id3 = ID3(path)
    except Exception as exc:
        raise ChapterForgeError(f"Could not read tags: {exc}")

    def text(key: str) -> str:
        frame = id3.get(key)
        if frame is not None and getattr(frame, "text", None):
            return str(frame.text[0])
        return ""

    tags = Tags(
        title=text("TIT2"), artist=text("TPE1"), album=text("TALB"),
        album_artist=text("TPE2"), genre=text("TCON"), year=text("TDRC"),
    )
    comms = id3.getall("COMM")
    if comms and comms[0].text:
        tags.comment = str(comms[0].text[0])

    chap_frames = id3.getall("CHAP")
    by_id = {ch.element_id: ch for ch in chap_frames}
    order: List[str] = []
    tocs = id3.getall("CTOC")
    if tocs:
        order = [eid for eid in tocs[0].child_element_ids if eid in by_id]
    if not order:
        order = [ch.element_id for ch in
                 sorted(chap_frames, key=lambda c: c.start_time)]

    chapters: List[Chapter] = []
    for i, eid in enumerate(order):
        ch = by_id[eid]
        title = ""
        url = ""
        sf = ch.sub_frames
        try:
            titles = sf.getall("TIT2")
            if titles and titles[0].text:
                title = str(titles[0].text[0])
            urls = sf.getall("WXXX")
            if urls:
                url = getattr(urls[0], "url", "")
        except AttributeError:
            for fr in sf:
                if getattr(fr, "FrameID", "") == "TIT2" and getattr(fr, "text", None):
                    title = str(fr.text[0])
        chapters.append(Chapter(index=i, title=title or f"Chapter {i + 1}",
                                start_ms=int(ch.start_time),
                                end_ms=int(ch.end_time), url=url))

    total_ms = _probe_duration_ms(path)
    if chapters and (total_ms <= 0 or chapters[-1].end_ms > total_ms):
        total_ms = max(total_ms, chapters[-1].end_ms)
    return tags, chapters, total_ms


def _read_master_mp4(path: str) -> Tuple[Tags, List[Chapter], int]:
    ffprobe = _find_tool("ffprobe")
    proc = _run([ffprobe, "-v", "error", "-print_format", "json",
                 "-show_format", "-show_chapters", path])
    if proc.returncode != 0:
        raise ChapterForgeError("Could not read the file with ffprobe.")
    try:
        data = json.loads(proc.stdout.decode("utf-8", "replace") or "{}")
    except ValueError as exc:
        raise ChapterForgeError(f"Could not parse media metadata: {exc}")

    fmt_tags = {k.lower(): v for k, v in
                (data.get("format", {}).get("tags", {}) or {}).items()}
    tags = Tags(
        title=fmt_tags.get("title", ""),
        artist=fmt_tags.get("artist", ""),
        album=fmt_tags.get("album", ""),
        album_artist=fmt_tags.get("album_artist", "") or fmt_tags.get("albumartist", ""),
        genre=fmt_tags.get("genre", ""),
        year=fmt_tags.get("date", "") or fmt_tags.get("year", ""),
        comment=fmt_tags.get("comment", ""),
    )

    chapters: List[Chapter] = []
    for i, ch in enumerate(data.get("chapters", []) or []):
        try:
            start_ms = int(round(float(ch.get("start_time", 0)) * 1000))
            end_ms = int(round(float(ch.get("end_time", 0)) * 1000))
        except (TypeError, ValueError):
            continue
        ctitle = (ch.get("tags", {}) or {}).get("title", "") or f"Chapter {i + 1}"
        chapters.append(Chapter(index=i, title=ctitle,
                                start_ms=start_ms, end_ms=end_ms))

    total_ms = 0
    try:
        total_ms = int(round(float(data.get("format", {}).get("duration", 0)) * 1000))
    except (TypeError, ValueError):
        total_ms = _probe_duration_ms(path)
    if chapters and chapters[-1].end_ms > total_ms:
        total_ms = chapters[-1].end_ms
    return tags, chapters, total_ms


def save_tags_chapters_inplace(path: str, chapters: Sequence[Chapter],
                               tags: Tags) -> None:
    """Rewrite only the tags/chapters of an existing MP3 (no re-encode).

    Use when editing a file that already has the right audio; avoids rebuilding.
    """
    if output_format(path) == "m4b":
        raise ChapterForgeError(
            "In-place editing of M4B files is not supported; rebuild instead.")
    total_ms = _probe_duration_ms(path)
    if total_ms <= 0 and chapters:
        total_ms = chapters[-1].end_ms
    write_tags_and_chapters(path, list(chapters), tags, total_ms)


def save_master_as(src: str, dest: str, chapters: Sequence[Chapter],
                   tags: Tags, canceller: Optional[Canceller] = None) -> str:
    """Write a copy of an existing master to *dest* with new tags/chapters.

    Keeps the original audio untouched (no re-encode): MP3 is byte-copied then
    re-tagged; M4B/MP4 is remuxed with ``-c:a copy`` plus fresh FFMETADATA
    chapters and an optional cover. Returns *dest*.
    """
    if not os.path.isfile(src):
        raise ChapterForgeError(f"File not found: {src}")
    total_ms = _probe_duration_ms(src)
    if total_ms <= 0 and chapters:
        total_ms = chapters[-1].end_ms
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    if output_format(dest) == "m4b":
        meta_fd, meta_path = tempfile.mkstemp(suffix=".ffmeta")
        os.close(meta_fd)
        try:
            _write_ffmetadata(meta_path, chapters, tags, total_ms)
            _mux_m4b(src, meta_path, tags.cover_path, dest,
                     canceller or Canceller())
        finally:
            try:
                os.remove(meta_path)
            except OSError:
                pass
    else:
        shutil.copyfile(src, dest)
        write_tags_and_chapters(dest, list(chapters), tags, total_ms)
    return dest


def reorder_audio_chapters(
    src_path: str,
    chapters: Sequence[Chapter],
    order: Sequence[int],
    output_path: str,
    tags: Tags,
    canceller: Canceller,
    progress: Optional[Callable[[float], None]] = None,
) -> "BuildResult":
    """Re-export an existing chaptered master with audio segments in a new order.

    ``chapters[order[i]]`` becomes chapter i in the output. Audio is always
    copied (no re-encode). A new file is always written -- the source is never
    modified. Raises :class:`ChapterForgeError` on failure or cancellation.
    """
    ffmpeg = _find_tool("ffmpeg")
    n = len(order)
    total_ms = sum(chapters[i].duration_ms for i in order)
    tmp_dir = tempfile.mkdtemp(prefix="chapterforge_reorder_")
    segments: List[str] = []
    try:
        # Phase 1: extract each segment into a temp file (75 % of progress)
        for pos, orig_idx in enumerate(order):
            if canceller.cancelled:
                raise ChapterForgeError("Cancelled.")
            ch = chapters[orig_idx]
            seg = os.path.join(tmp_dir, f"seg_{pos:04d}.mp3")
            result = _run([
                ffmpeg, "-hide_banner", "-nostdin", "-y",
                "-ss", f"{ch.start_ms / 1000.0:.3f}",
                "-to", f"{ch.end_ms / 1000.0:.3f}",
                "-i", src_path,
                "-map", "0:a", "-c", "copy",
                "-map_metadata", "-1",
                seg,
            ])
            if result.returncode != 0:
                raise ChapterForgeError(
                    f"Could not extract segment {pos + 1}: "
                    + result.stderr.decode("utf-8", "replace")[-400:])
            segments.append(seg)
            if progress:
                progress((pos + 1) / n * 0.75)

        # Phase 2: concatenate segments (20 % of progress)
        if canceller.cancelled:
            raise ChapterForgeError("Cancelled.")
        fd, list_path = tempfile.mkstemp(suffix=".txt", prefix="chapterforge_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                for seg in segments:
                    fh.write(f"file '{_ffmpeg_escape_concat(seg)}'\n")
            cmd = [
                ffmpeg, "-hide_banner", "-nostdin", "-y",
                "-f", "concat", "-safe", "0", "-i", list_path,
                "-map", "0:a", "-c", "copy",
                "-map_metadata", "-1",
                "-progress", "pipe:1", "-nostats",
                output_path,
            ]
            _stream_ffmpeg(
                cmd, total_ms, canceller,
                (lambda pct: progress(0.75 + pct * 0.20)) if progress else None)
        finally:
            try:
                os.remove(list_path)
            except OSError:
                pass
    finally:
        for seg in segments:
            try:
                os.remove(seg)
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass

    if canceller.cancelled:
        raise ChapterForgeError("Cancelled.")

    # Phase 3: build sequential chapter list and tag the output
    new_chapters: List[Chapter] = []
    pos_ms = 0
    for dest_pos, orig_idx in enumerate(order):
        ch = chapters[orig_idx]
        dur = ch.duration_ms
        new_chapters.append(Chapter(
            index=dest_pos, title=ch.title,
            start_ms=pos_ms, end_ms=pos_ms + dur,
            url=ch.url, img=ch.img,
        ))
        pos_ms += dur

    actual_ms = _probe_duration_ms(output_path) or total_ms
    clamped = _clamp_chapters(new_chapters, actual_ms, scale=False)
    write_tags_and_chapters(output_path, clamped, tags, actual_ms)
    if progress:
        progress(1.0)
    return BuildResult(
        output_path=output_path,
        chapters=clamped,
        total_ms=actual_ms,
        reencoded=False,
    )


# ---------------------------------------------------------------------------
# Batch building
# ---------------------------------------------------------------------------


def find_book_folders(parent: str, exclude_masters: bool = True) -> List[str]:
    """Immediate sub-folders of *parent* that contain at least one source MP3.

    Skips dot-folders and ChapterForge output folders (names starting with
    ``_``) so batch runs don't reprocess their own output.
    """
    found: List[str] = []
    try:
        names = sorted(os.listdir(parent), key=natural_key)
    except OSError:
        return found
    for name in names:
        if name.startswith((".", "_")):
            continue
        full = os.path.join(parent, name)
        if not os.path.isdir(full):
            continue
        try:
            items, _ = scan_folder_detailed(full, exclude_masters=exclude_masters)
        except OSError:
            continue
        if any(not it.error and it.duration > 0 for it in items):
            found.append(full)
    return found


def build_folder(folder: str, *, output_path: Optional[str] = None,
                 ext: str = ".mp3", bitrate: str = "192k",
                 normalize: bool = False, title_source: str = "filename",
                 auto_cover: bool = True, write_pod2: bool = False,
                 gap_ms: int = 0,
                 sticky_tags: Optional[Tags] = None,
                 canceller: Optional[Canceller] = None,
                 progress: Optional[Callable[[float], None]] = None
                 ) -> BuildResult:
    """Scan *folder* and build one master (used by batch and convenience flows).

    Tags default to the folder name (title/album) merged with *sticky_tags*
    (artist/genre/etc.). Writes a chapter report and, optionally, a Podcasting
    2.0 sidecar. Returns the :class:`BuildResult`.
    """
    items, _skipped = scan_folder_detailed(folder)
    good = [it for it in items if not it.error and it.duration > 0]
    if not good:
        raise NoAudioFilesError(f"No usable MP3 files in {folder}.")
    apply_title_source(good, title_source, respect_edits=False)

    base = os.path.basename(os.path.normpath(folder)) or "Master"
    if output_path is None:
        output_path = os.path.join(folder, f"{base} - Master{ext}")

    sticky = sticky_tags or Tags()
    tags = Tags(
        title=sticky.title or base,
        artist=sticky.artist,
        album=sticky.album or base,
        album_artist=sticky.album_artist,
        genre=sticky.genre,
        year=sticky.year,
        comment=sticky.comment,
    )
    if auto_cover and not tags.cover_path:
        cover = find_cover(folder)
        if cover:
            tags.cover_path = cover

    chapters = compute_chapters(good)
    result = build_master(good, output_path, tags, chapters=chapters,
                          bitrate=bitrate, normalize=normalize, gap_ms=gap_ms,
                          canceller=canceller, progress=progress)
    try:
        write_chapter_report(output_path, result, tags, good)
    except OSError:
        pass
    if write_pod2:
        try:
            write_pod2_chapters(output_path, result.chapters, result.total_ms)
        except OSError:
            pass
    return result


# ---------------------------------------------------------------------------
# Inter-chapter gaps, size estimate and post-build verification
# ---------------------------------------------------------------------------


def _chapters_with_gaps(items: Sequence[Mp3Item], gap_ms: int,
                        base: Optional[Sequence[Chapter]] = None
                        ) -> List[Chapter]:
    """Recompute boundaries with *gap_ms* of silence between chapters.

    Titles/links are taken from *base* (the caller's possibly-edited chapters)
    when available, else from the items. The trailing gap after the last
    chapter is omitted.
    """
    chapters: List[Chapter] = []
    cursor = 0
    n = len(items)
    for i, item in enumerate(items):
        b = base[i] if base and i < len(base) else None
        start = cursor
        end = start + max(item.duration_ms, 0)
        chapters.append(Chapter(
            index=i,
            title=(b.title if b else item.title),
            start_ms=start, end_ms=end,
            url=(b.url if b else item.url),
            img=(b.img if b else item.img)))
        cursor = end + (gap_ms if i < n - 1 else 0)
    return chapters


def _bitrate_kbps(bitrate: str) -> int:
    m = re.match(r"\s*(\d+)", str(bitrate))
    return int(m.group(1)) if m else 192


def estimate_output(items: Sequence[Mp3Item], bitrate: str = "192k",
                    gap_ms: int = 0) -> Tuple[int, int]:
    """Estimate the master's (total_ms, approximate_bytes) before building."""
    total_ms = sum(max(it.duration_ms, 0) for it in items)
    total_ms += max(0, len(items) - 1) * max(0, gap_ms)
    kbps = _bitrate_kbps(bitrate)
    est_bytes = int(kbps * 1000 / 8 * (total_ms / 1000.0))
    return total_ms, est_bytes


def format_size(num_bytes: int) -> str:
    """Human-readable byte size (e.g. ``118.3 MB``)."""
    size = float(max(0, num_bytes))
    for unit in ("bytes", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "bytes":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def verify_output(path: str, expected_n: Optional[int] = None
                  ) -> Tuple[bool, int, int, List[str]]:
    """Re-read a freshly built master and sanity-check it.

    Returns ``(ok, chapter_count, total_ms, issues)``. Used to give the user a
    trustworthy "Verified N chapters" confirmation after a build.
    """
    issues: List[str] = []
    try:
        _tags, chapters, total_ms = read_master(path)
    except ChapterForgeError as exc:
        return False, 0, 0, [str(exc)]
    n = len(chapters)
    if expected_n is not None and n != expected_n:
        issues.append(f"Expected {expected_n} chapter(s) but found {n}.")
    if total_ms <= 0:
        issues.append("Could not read a positive duration.")
    for i in range(1, n):
        if chapters[i].start_ms < chapters[i - 1].start_ms:
            issues.append("Chapter start times are out of order.")
            break
    return (not issues), n, total_ms, issues


# ---------------------------------------------------------------------------
# Importing / exporting chapter lists (Audacity labels, CUE, timestamps)
# ---------------------------------------------------------------------------

_TS_RE = re.compile(r"^(\d{1,2}:)?\d{1,2}:\d{2}(\.\d+)?$")


def _ts_to_ms(token: str) -> Optional[int]:
    token = token.strip()
    if not re.match(r"^\d{1,2}:\d{2}(:\d{2})?(\.\d+)?$", token):
        return None
    parts = token.split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 2:
        secs = nums[0] * 60 + nums[1]
    else:
        secs = nums[0] * 3600 + nums[1] * 60 + nums[2]
    return int(round(secs * 1000))


def chapters_to_audacity(chapters: Sequence[Chapter]) -> str:
    """Audacity label track: ``start<TAB>end<TAB>title`` (seconds)."""
    lines = []
    for ch in chapters:
        lines.append(f"{ch.start_ms / 1000.0:.6f}\t{ch.end_ms / 1000.0:.6f}\t"
                     f"{ch.title}")
    return "\n".join(lines) + "\n"


def chapters_to_timestamps(chapters: Sequence[Chapter]) -> str:
    """Simple ``H:MM:SS<TAB>Title`` lines (e.g. for show notes)."""
    return "".join(f"{format_timestamp(ch.start_ms)}\t{ch.title}\n"
                   for ch in chapters)


def _ms_to_cue(ms: int) -> str:
    total_frames = int(round(ms / 1000.0 * 75))
    minutes, rem = divmod(total_frames, 75 * 60)
    seconds, frames = divmod(rem, 75)
    return f"{minutes:02d}:{seconds:02d}:{frames:02d}"


def chapters_to_cue(chapters: Sequence[Chapter], audio_filename: str,
                    tags: Optional[Tags] = None) -> str:
    tags = tags or Tags()
    lines = []
    if tags.artist:
        lines.append(f'PERFORMER "{tags.artist}"')
    if tags.album or tags.title:
        lines.append(f'TITLE "{tags.album or tags.title}"')
    lines.append(f'FILE "{os.path.basename(audio_filename)}" MP3')
    for i, ch in enumerate(chapters, start=1):
        lines.append(f"  TRACK {i:02d} AUDIO")
        lines.append(f'    TITLE "{ch.title}"')
        if tags.artist:
            lines.append(f'    PERFORMER "{tags.artist}"')
        lines.append(f"    INDEX 01 {_ms_to_cue(ch.start_ms)}")
    return "\n".join(lines) + "\n"


CHAPTER_EXPORT_FORMATS = ("audacity", "timestamps", "cue", "pod2")


def export_chapter_labels(out_path: str, chapters: Sequence[Chapter], fmt: str,
                          audio_filename: str = "", tags: Optional[Tags] = None,
                          total_ms: int = 0) -> str:
    """Write *chapters* to *out_path* in *fmt* (see CHAPTER_EXPORT_FORMATS)."""
    fmt = fmt.lower()
    if fmt == "pod2":
        data = {"version": "1.2.0", "chapters": [
            {"startTime": round(ch.start_ms / 1000.0, 3), "title": ch.title,
             **({"url": ch.url} if ch.url else {}),
             **({"img": ch.img} if ch.img else {})}
            for ch in chapters]}
        text = json.dumps(data, indent=2, ensure_ascii=False)
    elif fmt == "audacity":
        text = chapters_to_audacity(chapters)
    elif fmt == "timestamps":
        text = chapters_to_timestamps(chapters)
    elif fmt == "cue":
        text = chapters_to_cue(chapters, audio_filename or out_path, tags)
    else:
        raise ChapterForgeError(f"Unknown chapter format: {fmt}")
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return out_path


def _parse_cue(lines: Sequence[str]) -> List[Tuple[int, str]]:
    pairs: List[Tuple[int, str]] = []
    title = ""
    for raw in lines:
        s = raw.strip()
        up = s.upper()
        if up.startswith("TITLE "):
            title = s[6:].strip().strip('"')
        elif up.startswith("INDEX 01"):
            token = s.split()[-1]
            parts = token.split(":")
            if len(parts) == 3:
                mm, ss, ff = (int(p) for p in parts)
                ms = int(round((mm * 60 + ss + ff / 75.0) * 1000))
                pairs.append((ms, title or f"Chapter {len(pairs) + 1}"))
                title = ""
    return pairs


def parse_chapter_text(text: str, total_ms: int) -> List[Chapter]:
    """Parse Audacity labels, a CUE sheet, or timestamp lines into chapters.

    Auto-detects the format. Times beyond *total_ms* are ignored. Returns
    contiguous chapters that tile ``[0, total_ms]``. Raises
    :class:`ChapterForgeError` if nothing usable is found.
    """
    if total_ms <= 0:
        raise ChapterForgeError("The target file has no known duration.")
    lines = text.splitlines()
    pairs: List[Tuple[int, str]] = []
    if any("INDEX 01" in ln.upper() for ln in lines):
        pairs = _parse_cue(lines)
    else:
        for raw in lines:
            s = raw.strip()
            if not s or s.startswith((";", "#")):
                continue
            cols = s.split("\t")
            if len(cols) >= 3 and _ts_re_float(cols[0]) and _ts_re_float(cols[1]):
                pairs.append((int(round(float(cols[0]) * 1000)),
                              cols[2].strip() or f"Chapter {len(pairs) + 1}"))
                continue
            m = re.match(r"^(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?)\s*[-\u2013]?\s*(.*)$", s)
            if m:
                ms = _ts_to_ms(m.group(1))
                if ms is not None:
                    title = m.group(2).strip() or f"Chapter {len(pairs) + 1}"
                    pairs.append((ms, title))
    pairs = [(ms, t) for ms, t in pairs if 0 <= ms < total_ms]
    if not pairs:
        raise ChapterForgeError("No chapter markers were found in that file.")
    title_by_start = {}
    for ms, t in pairs:
        title_by_start.setdefault(ms, t)
    starts = sorted(title_by_start)
    if starts[0] != 0:
        starts.insert(0, 0)
        title_by_start.setdefault(0, "Chapter 1")
    chapters: List[Chapter] = []
    for i, st in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else total_ms
        if end <= st:
            continue
        chapters.append(Chapter(index=len(chapters),
                                title=title_by_start.get(st, f"Chapter {i + 1}"),
                                start_ms=st, end_ms=end))
    return _renumber(chapters)


def _ts_re_float(token: str) -> bool:
    try:
        float(token)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Editing chapter boundaries (merge / split / adjust)
# ---------------------------------------------------------------------------


def _renumber(chapters: Sequence[Chapter]) -> List[Chapter]:
    return [replace(ch, index=i) for i, ch in enumerate(chapters)]


def merge_chapter(chapters: Sequence[Chapter], index: int) -> List[Chapter]:
    """Remove the marker at *index*, merging that chapter into its neighbour.

    The first chapter merges into the second (its title is kept); any other
    chapter merges into the previous one. Audio is never removed.
    """
    chapters = list(chapters)
    n = len(chapters)
    if n < 2:
        raise ChapterForgeError("There must be at least two chapters to merge.")
    if not 0 <= index < n:
        raise ChapterForgeError("No chapter is selected.")
    if index == 0:
        merged = replace(chapters[0], end_ms=chapters[1].end_ms)
        result = [merged] + chapters[2:]
    else:
        prev = replace(chapters[index - 1], end_ms=chapters[index].end_ms)
        result = chapters[:index - 1] + [prev] + chapters[index + 1:]
    return _renumber(result)


def split_chapter(chapters: Sequence[Chapter], at_ms: int,
                  title: str = "New chapter",
                  min_part_ms: int = 1000) -> List[Chapter]:
    """Insert a new chapter boundary at *at_ms*, splitting the chapter there."""
    chapters = list(chapters)
    for i, ch in enumerate(chapters):
        if ch.start_ms < at_ms < ch.end_ms:
            if at_ms - ch.start_ms < min_part_ms or ch.end_ms - at_ms < min_part_ms:
                raise ChapterForgeError(
                    "That split point is too close to a chapter boundary.")
            left = replace(ch, end_ms=at_ms)
            right = Chapter(index=i + 1, title=title or "New chapter",
                            start_ms=at_ms, end_ms=ch.end_ms)
            result = chapters[:i] + [left, right] + chapters[i + 1:]
            return _renumber(result)
    raise ChapterForgeError("The split point is not inside a chapter.")


def set_chapter_start(chapters: Sequence[Chapter], index: int,
                      new_start_ms: int, min_part_ms: int = 500
                      ) -> List[Chapter]:
    """Move chapter *index*'s start (and the previous chapter's end) to a new
    time, keeping chapters contiguous and validly ordered."""
    chapters = list(chapters)
    if not 0 <= index < len(chapters):
        raise ChapterForgeError("No chapter is selected.")
    if index == 0:
        raise ChapterForgeError("The first chapter must start at the beginning.")
    lo = chapters[index - 1].start_ms + min_part_ms
    hi = chapters[index].end_ms - min_part_ms
    if not lo <= new_start_ms <= hi:
        raise ChapterForgeError(
            f"Start must be between {format_timestamp(lo)} and "
            f"{format_timestamp(hi)}.")
    prev = replace(chapters[index - 1], end_ms=new_start_ms)
    cur = replace(chapters[index], start_ms=new_start_ms)
    result = chapters[:index - 1] + [prev, cur] + chapters[index + 1:]
    return _renumber(result)

