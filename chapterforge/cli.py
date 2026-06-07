"""Command-line interface for ChapterForge.

Running ``chapterforge`` with any arguments (or the bundled console
``chapterforge-cli.exe``) builds a master MP3 entirely from the terminal,
printing the chapter plan and a live progress bar. With no arguments the
graphical app is launched instead.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import List, Optional, Sequence

from . import __app_name__, __copyright__, __version__, core


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="chapterforge",
        description=(
            "Combine a folder of MP3 files into a single master MP3 with "
            "embedded ID3v2 chapter markers (one chapter per source file). "
            "Run with no arguments to open the graphical app."),
        epilog=(
            "Examples:\n"
            "  chapterforge \"C:\\Audiobooks\\My Book\"\n"
            "  chapterforge -i ./chapters -o book.mp3 --title \"My Book\" "
            "--artist \"Jane Doe\" --normalize\n"
            "  chapterforge ./chapters --list\n"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("folder", nargs="?", help="Folder of MP3 files (input).")
    p.add_argument("-i", "--input", dest="input_opt", metavar="FOLDER",
                   help="Folder of MP3 files (alternative to the positional argument).")
    p.add_argument("-o", "--output", metavar="FILE",
                   help="Master MP3 output path (default: '<folder> - Master.mp3').")
    p.add_argument("-j", "--job", metavar="FILE",
                   help="Build from a .cfjob job file (defines order, titles and tags).")
    p.add_argument("--watch", action="store_true",
                   help="Run the background folder watcher in the system tray.")

    tag = p.add_argument_group("ID3 tags")
    tag.add_argument("--title", help="Master title.")
    tag.add_argument("--artist", help="Artist.")
    tag.add_argument("--album", help="Album (default: folder name).")
    tag.add_argument("--album-artist", dest="album_artist", help="Album artist.")
    tag.add_argument("--genre", help="Genre.")
    tag.add_argument("--year", help="Year.")
    tag.add_argument("--comment", help="Comment.")
    tag.add_argument("--narrator", help="Narrator (written as TPE4).")
    tag.add_argument("--series", help="Series title.")
    tag.add_argument("--series-part", dest="series_part",
                     help="Series part / number.")
    tag.add_argument("--cover", metavar="IMAGE", help="Cover image (JPEG/PNG).")
    tag.add_argument("--no-auto-cover", dest="auto_cover", action="store_false",
                     help="Do not auto-detect a cover image in the folder.")

    enc = p.add_argument_group("encoding & chapters")
    enc.add_argument("--title-source", choices=["filename", "embedded"],
                     default="filename",
                     help="Where chapter titles come from (default: filename).")
    enc.add_argument("--format", choices=["mp3", "m4b", "flac", "opus"], dest="fmt",
                     help="Output format. Default: inferred from -o, else mp3. "
                          "m4b is an AAC audiobook with MP4 chapters; flac is "
                          "lossless; opus is small modern audio.")
    enc.add_argument("--bitrate", default="192k",
                     help="Bitrate for the re-encode path, e.g. 192k (default: 192k).")
    enc.add_argument("--normalize", action="store_true",
                     help="Normalize loudness across the whole master "
                          "(single-pass, forces a re-encode).")
    enc.add_argument("--per-file-normalize", dest="per_file_normalize",
                     action="store_true",
                     help="Normalize each source file individually before "
                          "concatenation (MP3 output).")
    enc.add_argument("--normalize-lufs", dest="normalize_lufs", type=float,
                     default=-16.0,
                     help="Target loudness in LUFS for --per-file-normalize "
                          "(default: -16; use -23 for ACX).")
    enc.add_argument("--fade-ms", dest="fade_ms", type=int, default=0,
                     help="Fade-in and fade-out duration in milliseconds applied "
                          "to each source file (MP3 output; default: 0).")
    enc.add_argument("--trim-silence", dest="trim_silence", action="store_true",
                     help="Trim leading/trailing silence from each source file "
                          "before concatenation.")
    enc.add_argument("--rss-url", dest="rss_url", metavar="URL",
                     help="Also write an .rss podcast feed pointing at this "
                          "public media URL for the built file.")
    enc.add_argument("--gap-seconds", dest="gap_seconds", type=float, default=0.0,
                     help="Insert this many seconds of silence between chapters "
                          "(forces a re-encode; default: 0).")
    enc.add_argument("--reverse", action="store_true",
                     help="Reverse the file order before building.")
    enc.add_argument("--pod2-chapters", dest="pod2", action="store_true",
                     help="Also write a Podcasting 2.0 chapters .json sidecar.")
    enc.add_argument("--split-silence", dest="split_silence", action="store_true",
                     help="Treat the input as ONE file and auto-chapter it at "
                          "silences instead of merging a folder.")
    enc.add_argument("--noise-db", dest="noise_db", type=float, default=-30.0,
                     help="Silence threshold in dB for --split-silence (default: -30).")
    enc.add_argument("--min-silence", dest="min_silence", type=float, default=0.8,
                     help="Minimum silence length in seconds for --split-silence "
                          "(default: 0.8).")
    enc.add_argument("--batch", metavar="PARENT",
                     help="Build a master for every sub-folder of PARENT that "
                          "contains MP3s (output stays in each sub-folder).")

    out = p.add_argument_group("behaviour")
    out.add_argument("--list", action="store_true",
                     help="List the chapter plan and exit (no build).")
    out.add_argument("--dry-run", action="store_true",
                     help="Show what would happen without building.")
    out.add_argument("-y", "--yes", action="store_true",
                     help="Overwrite the output file without prompting.")
    out.add_argument("-q", "--quiet", action="store_true",
                     help="Only print errors.")
    out.add_argument("--version", action="version",
                     version=f"{__app_name__} {__version__}\n{__copyright__}")
    out.add_argument("--check-updates", dest="check_updates", action="store_true",
                     help="Check online for a newer version and exit.")
    out.add_argument("--update", dest="update", action="store_true",
                     help="Check for a newer version and, if found, download and "
                          "launch its installer.")
    p.set_defaults(auto_cover=True)
    return p


# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------

def _supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _print(msg: str = "", quiet: bool = False) -> None:
    if not quiet:
        print(msg, flush=True)


def _err(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _print_chapter_table(items: Sequence[core.Mp3Item]) -> None:
    chapters = core.compute_chapters(items)
    width = max((len(it.title) for it in items), default=5)
    width = min(max(width, 5), 60)
    print(f"  {'#':>3}  {'Start':>8}  {'Length':>8}  Title", flush=True)
    print(f"  {'-'*3}  {'-'*8}  {'-'*8}  {'-'*width}", flush=True)
    for i, (it, ch) in enumerate(zip(items, chapters), 1):
        title = it.title if len(it.title) <= 60 else it.title[:57] + "…"
        print(f"  {i:>3}  {core.format_timestamp(ch.start_ms):>8}  "
              f"{core.format_timestamp(ch.duration_ms):>8}  {title}", flush=True)
    total = chapters[-1].end_ms if chapters else 0
    print(f"  {'='*3}  {'='*8}  {'='*8}", flush=True)
    print(f"  Total: {len(items)} chapter(s), {core.format_timestamp(total)}",
          flush=True)


class _ProgressBar:
    """A simple in-place terminal progress bar."""

    def __init__(self, label: str, enabled: bool):
        self.label = label
        self.enabled = enabled
        self._last = -1
        self._tty = sys.stdout.isatty()

    def update(self, frac: float) -> None:
        if not self.enabled:
            return
        pct = int(max(0.0, min(1.0, frac)) * 100)
        if pct == self._last:
            return
        self._last = pct
        if self._tty:
            filled = pct // 5
            bar = "#" * filled + "-" * (20 - filled)
            sys.stdout.write(f"\r{self.label} [{bar}] {pct:3d}%")
            sys.stdout.flush()
        elif pct % 10 == 0:
            sys.stdout.write(f"{self.label} {pct}%\n")
            sys.stdout.flush()

    def finish(self) -> None:
        if self.enabled and self._tty:
            sys.stdout.write("\n")
            sys.stdout.flush()


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def _run_job(args, quiet: bool) -> int:
    from . import manifest as manifest_mod

    job_path = os.path.abspath(args.job)
    if not os.path.isfile(job_path):
        _err(f"error: job file not found: {job_path}")
        return 2
    folder = os.path.dirname(job_path)
    manifest = manifest_mod.read_manifest(job_path)
    entries, missing = manifest_mod.resolve_manifest(manifest, folder)
    if missing:
        _err("error: job file references missing files:")
        for name in missing[:12]:
            _err(f"  - {name}")
        return 4
    if not entries:
        _err("error: job file lists no usable tracks.")
        return 4

    items = core.items_from_entries(entries)
    bad = [it for it in items if it.error or it.duration <= 0]
    if bad:
        _err("error: unreadable files in job:")
        for it in bad[:12]:
            _err(f"  - {it.filename}: {it.error}")
        return 4

    tags = manifest_mod.manifest_tags(manifest, folder)
    output = args.output or manifest.option("output", "") or \
        core.suggested_output_path(folder)
    if not os.path.isabs(output):
        output = os.path.join(folder, output)
    output = os.path.abspath(output)
    bitrate = args.bitrate if args.bitrate != "192k" else manifest.bitrate
    normalize = args.normalize or manifest.normalize

    _print(f"{__app_name__} {__version__}", quiet)
    _print(f"Job: {job_path}", quiet)
    if not quiet:
        _print(f"Found {len(items)} chapter(s).", quiet)
        _print("", quiet)
        _print_chapter_table(items)
        _print("", quiet)
        _print(f"Output: {output}", quiet)

    if args.list or args.dry_run:
        _print("\n(dry run - nothing was written)", quiet)
        return 0

    if os.path.exists(output) and not args.yes:
        if sys.stdin and sys.stdin.isatty():
            resp = input(f'"{output}" exists. Overwrite? [y/N] ').strip().lower()
            if resp not in ("y", "yes"):
                _print("Aborted.", quiet)
                return 1
        else:
            _err(f"error: {output} exists (use --yes to overwrite).")
            return 1

    bar = _ProgressBar("Building", enabled=not quiet)
    chapters = core.compute_chapters(items)
    started = time.time()
    try:
        result = core.build_master(
            items, output, tags, chapters=chapters,
            bitrate=bitrate, normalize=normalize,
            gap_ms=int(round(getattr(args, "gap_seconds", 0.0) * 1000)),
            progress=bar.update)
    except core.ChapterForgeError as exc:
        bar.finish()
        _err(f"error: {exc}")
        return 5
    bar.finish()
    elapsed = time.time() - started
    mode = "re-encoded" if result.reencoded else "lossless copy"
    _print(f"Done in {elapsed:.1f}s - {mode}.", quiet)
    _print(f"  {len(result.chapters)} chapter(s), "
           f"{core.format_timestamp(result.total_ms)}", quiet)
    _print(f"  Saved: {result.output_path}", quiet)
    try:
        report = core.write_chapter_report(output, result, tags, items)
        _print(f"  Report: {report}", quiet)
    except OSError:
        pass
    if getattr(args, "pod2", False):
        try:
            sidecar = core.write_pod2_chapters(output, result.chapters, result.total_ms)
            _print(f"  Chapters JSON: {sidecar}", quiet)
        except OSError:
            pass
    return 0


def _check_updates_cli(quiet: bool) -> int:
    from . import updates
    _print(f"{__app_name__} {__version__}", quiet)
    _print("Checking for updates…", quiet)
    try:
        release = updates.check_for_update()
    except updates.UpdateCheckError as exc:
        _err(f"error: could not check for updates: {exc}")
        return 6
    if release is None:
        _print("You are running the latest version.", quiet)
        return 0
    _print(f"Update available: {release.version} (you have {__version__}).", quiet)
    if release.download_url:
        _print(f"Download: {release.download_url}", quiet)
    return 0


def _update_cli(quiet: bool) -> int:
    from . import updates
    _print(f"{__app_name__} {__version__}", quiet)
    _print("Checking for updates…", quiet)
    try:
        release = updates.check_for_update()
    except updates.UpdateCheckError as exc:
        _err(f"error: could not check for updates: {exc}")
        return 6
    if release is None:
        _print("You are running the latest version.", quiet)
        return 0
    _print(f"Update available: {release.version} (you have {__version__}).", quiet)
    if not updates.is_installable_asset(release.download_url):
        _err("error: no installable package is available for this platform; "
             f"download manually from {release.download_url or updates.RELEASES_PAGE}")
        return 6

    last = [0]

    def progress(read, total):
        if quiet or not total:
            return
        pct = int(read * 100 / total)
        if pct != last[0]:
            last[0] = pct
            print(f"\r  Downloading… {pct}%", end="", flush=True)

    try:
        path = updates.download_release_asset(release, progress=progress)
        if not quiet:
            print()
    except updates.UpdateCheckError as exc:
        _err(f"error: could not download the update: {exc}")
        return 6
    _print(f"Downloaded installer to: {path}", quiet)
    try:
        updates.launch_installer(path)
    except updates.UpdateCheckError as exc:
        _err(f"error: {exc}")
        return 6
    _print("Launched the installer. Close ChapterForge to finish updating.", quiet)
    return 0


def _output_ext(args) -> str:
    if args.fmt:
        return {"m4b": ".m4b", "flac": ".flac", "opus": ".opus"}.get(
            args.fmt, ".mp3")
    if args.output:
        ext = os.path.splitext(args.output)[1].lower()
        if ext:
            return ext
    return ".mp3"


def _print_chapter_plan(chapters: Sequence[core.Chapter]) -> None:
    width = max((len(c.title) for c in chapters), default=5)
    width = min(max(width, 5), 60)
    print(f"  {'#':>3}  {'Start':>8}  {'Length':>8}  Title", flush=True)
    print(f"  {'-'*3}  {'-'*8}  {'-'*8}  {'-'*width}", flush=True)
    for i, ch in enumerate(chapters, 1):
        title = ch.title if len(ch.title) <= 60 else ch.title[:57] + "…"
        print(f"  {i:>3}  {core.format_timestamp(ch.start_ms):>8}  "
              f"{core.format_timestamp(ch.duration_ms):>8}  {title}", flush=True)
    total = chapters[-1].end_ms if chapters else 0
    print(f"  Total: {len(chapters)} chapter(s), {core.format_timestamp(total)}",
          flush=True)


def _print_preflight(items: Sequence[core.Mp3Item], quiet: bool) -> None:
    if quiet:
        return
    warnings = core.preflight(items)
    if warnings:
        _print("Pre-flight notes:", quiet)
        for w in warnings:
            _print(f"  ! {w}", quiet)
        _print("", quiet)


def _run_batch(args, quiet: bool) -> int:
    parent = os.path.abspath(args.batch)
    if not os.path.isdir(parent):
        _err(f"error: not a folder: {parent}")
        return 2
    folders = core.find_book_folders(parent)
    if not folders:
        _err("error: no sub-folders containing MP3s found.")
        return 4
    ext = _output_ext(args)
    sticky = core.Tags(artist=args.artist or "", album_artist=args.album_artist or "",
                       genre=args.genre or "", year=args.year or "",
                       comment=args.comment or "")
    _print(f"{__app_name__} {__version__}", quiet)
    _print(f"Batch: {len(folders)} book(s) under {parent}", quiet)
    failures = 0
    for i, folder in enumerate(folders, 1):
        name = os.path.basename(folder)
        _print(f"\n[{i}/{len(folders)}] {name}", quiet)
        bar = _ProgressBar("  Building", enabled=not quiet)
        try:
            result = core.build_folder(
                folder, ext=ext, bitrate=args.bitrate, normalize=args.normalize,
                title_source=args.title_source, auto_cover=args.auto_cover,
                write_pod2=args.pod2,
                gap_ms=int(round(getattr(args, "gap_seconds", 0.0) * 1000)),
                sticky_tags=sticky, progress=bar.update)
            bar.finish()
            _print(f"  Saved: {result.output_path} "
                   f"({len(result.chapters)} chapters, "
                   f"{core.format_timestamp(result.total_ms)})", quiet)
        except core.ChapterForgeError as exc:
            bar.finish()
            failures += 1
            _err(f"  error: {exc}")
    _print(f"\nDone. {len(folders) - failures} built, {failures} failed.", quiet)
    return 0 if failures == 0 else 5


def _run_split_silence(args, src: str, quiet: bool) -> int:
    if not os.path.isfile(src):
        _err(f"error: --split-silence needs an input file, not a folder: {src}")
        return 2
    _print(f"{__app_name__} {__version__}", quiet)
    _print(f"Detecting silences in: {src}", quiet)
    try:
        chapters = core.detect_silence_chapters(
            src, noise_db=args.noise_db, min_silence=args.min_silence)
    except core.ChapterForgeError as exc:
        _err(f"error: {exc}")
        return 5

    item = core.probe_file(src)
    if item.error or item.duration <= 0:
        _err(f"error: {item.error or 'unreadable file'}")
        return 4

    ext = _output_ext(args)
    base = os.path.splitext(os.path.basename(src))[0]
    output = args.output or os.path.join(os.path.dirname(src) or ".",
                                         f"{base} - Chaptered{ext}")
    output = os.path.abspath(output)
    tags = core.Tags(
        title=args.title or base, artist=args.artist or "",
        album=args.album or base, album_artist=args.album_artist or "",
        genre=args.genre or "", year=args.year or "", comment=args.comment or "",
        narrator=args.narrator or "", series_title=args.series or "",
        series_index=args.series_part or "")
    if args.cover:
        tags.cover_path = args.cover

    _print(f"Found {len(chapters)} chapter(s).", quiet)
    if not quiet:
        _print("", quiet)
        _print_chapter_plan(chapters)
        _print("", quiet)
        _print(f"Output: {output}", quiet)
    if args.list or args.dry_run:
        _print("\n(dry run - nothing was written)", quiet)
        return 0
    if os.path.exists(output) and not args.yes:
        if sys.stdin and sys.stdin.isatty():
            resp = input(f'"{output}" exists. Overwrite? [y/N] ').strip().lower()
            if resp not in ("y", "yes"):
                _print("Aborted.", quiet)
                return 1
        else:
            _err(f"error: {output} exists (use --yes to overwrite).")
            return 1

    bar = _ProgressBar("Building", enabled=not quiet)
    started = time.time()
    try:
        result = core.build_master(
            [item], output, tags, chapters=chapters, bitrate=args.bitrate,
            normalize=args.normalize, scale_chapters=False, progress=bar.update)
    except core.ChapterForgeError as exc:
        bar.finish()
        _err(f"error: {exc}")
        return 5
    bar.finish()
    _print(f"Done in {time.time() - started:.1f}s.", quiet)
    _print(f"  Saved: {result.output_path}", quiet)
    try:
        report = core.write_chapter_report(output, result, tags)
        _print(f"  Report: {report}", quiet)
    except OSError:
        pass
    if args.pod2:
        try:
            sidecar = core.write_pod2_chapters(output, result.chapters, result.total_ms)
            _print(f"  Chapters JSON: {sidecar}", quiet)
        except OSError:
            pass
    return 0


def run(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    quiet = args.quiet

    if args.watch:
        from .tray import run_watch_app
        run_watch_app()
        return 0

    if args.check_updates:
        return _check_updates_cli(quiet)

    if args.update:
        return _update_cli(quiet)

    try:
        core._find_tool("ffmpeg")
        core._find_tool("ffprobe")
    except core.FFmpegNotFoundError as exc:
        _err(f"error: {exc}")
        return 3

    if args.job:
        return _run_job(args, quiet)

    if args.batch:
        return _run_batch(args, quiet)

    src = args.input_opt or args.folder
    if not src:
        parser.error("an input folder is required (positional, --input, --job or --batch)")
    src = os.path.abspath(src)

    if args.split_silence:
        return _run_split_silence(args, src, quiet)

    folder = src
    if not os.path.isdir(folder):
        _err(f"error: not a folder: {folder}")
        return 2

    _print(f"{__app_name__} {__version__}", quiet)
    _print(f"Scanning: {folder}", quiet)
    items, skipped_masters = core.scan_folder_detailed(folder)
    good = [it for it in items if not it.error and it.duration > 0]
    skipped = [it for it in items if it.error or it.duration <= 0]

    if not good:
        _err("error: no usable MP3 files found in that folder.")
        return 4

    core.apply_title_source(good, args.title_source, respect_edits=False)
    if args.reverse:
        good.reverse()

    if skipped_masters and not quiet:
        _print(f"Skipped {len(skipped_masters)} existing master file(s): "
               + ", ".join(skipped_masters[:5]), quiet)
    if skipped and not quiet:
        _print(f"Skipped {len(skipped)} unreadable file(s):", quiet)
        for it in skipped[:10]:
            _print(f"  - {it.filename}: {it.error}", quiet)

    base = os.path.basename(os.path.normpath(folder))
    if args.output:
        output = os.path.abspath(args.output)
    else:
        ext = _output_ext(args)
        output = os.path.abspath(os.path.join(folder, f"{base} - Master{ext}"))

    tags = core.Tags(
        title=args.title or base,
        artist=args.artist or "",
        album=args.album or base,
        album_artist=args.album_artist or "",
        genre=args.genre or "",
        year=args.year or "",
        comment=args.comment or "",
        narrator=args.narrator or "",
        series_title=args.series or "",
        series_index=args.series_part or "",
    )
    cover = args.cover
    if not cover and args.auto_cover:
        cover = core.find_cover(folder)
        if cover and not quiet:
            _print(f"Auto-detected cover: {os.path.basename(cover)}", quiet)
    tags.cover_path = cover or ""

    if not quiet:
        total = core.compute_chapters(good)[-1].end_ms
        _print(f"Found {len(good)} MP3 file(s), total "
               f"{core.format_timestamp(total)}.", quiet)
        _print("", quiet)
        _print_chapter_table(good)
        _print("", quiet)
        _print(f"Output: {output}", quiet)
        if args.normalize:
            _print("Loudness normalization: on (re-encode)", quiet)
        _print("", quiet)
        _print_preflight(good, quiet)

    if args.list or args.dry_run:
        _print("\n(dry run - nothing was written)", quiet)
        return 0

    if os.path.exists(output) and not args.yes:
        if sys.stdin and sys.stdin.isatty():
            resp = input(f'"{output}" exists. Overwrite? [y/N] ').strip().lower()
            if resp not in ("y", "yes"):
                _print("Aborted.", quiet)
                return 1
        else:
            _err(f"error: {output} exists (use --yes to overwrite).")
            return 1

    # Optional per-track silence trimming before concatenation.
    build_items = good
    _trim_dir = None
    if getattr(args, "trim_silence", False):
        import tempfile as _tmpmod
        _trim_dir = _tmpmod.mkdtemp(prefix="chapterforge_trim_")
        build_items = [core.trim_silence_item(it, _trim_dir) for it in good]

    bar = _ProgressBar("Building", enabled=not quiet)
    chapters = core.compute_chapters(build_items)
    started = time.time()
    # The two loudness options are mutually exclusive; per-chapter wins.
    _pfn = getattr(args, "per_file_normalize", False)
    try:
        result = core.build_master(
            build_items, output, tags, chapters=chapters,
            bitrate=args.bitrate, normalize=(args.normalize and not _pfn),
            gap_ms=int(round(getattr(args, "gap_seconds", 0.0) * 1000)),
            per_file_normalize=_pfn,
            normalize_lufs=getattr(args, "normalize_lufs", -16.0),
            fade_in_ms=getattr(args, "fade_ms", 0),
            fade_out_ms=getattr(args, "fade_ms", 0),
            progress=bar.update)
    except core.ChapterForgeError as exc:
        bar.finish()
        _err(f"error: {exc}")
        return 5
    except KeyboardInterrupt:
        bar.finish()
        _err("Cancelled.")
        return 130
    finally:
        if _trim_dir:
            import shutil as _shutil
            _shutil.rmtree(_trim_dir, ignore_errors=True)
    bar.finish()

    elapsed = time.time() - started
    mode = "re-encoded" if result.reencoded else "lossless copy"
    _print(f"Done in {elapsed:.1f}s - {mode}.", quiet)
    _print(f"  {len(result.chapters)} chapter(s), "
           f"{core.format_timestamp(result.total_ms)}", quiet)
    _print(f"  Saved: {result.output_path}", quiet)
    try:
        report = core.write_chapter_report(output, result, tags, items)
        _print(f"  Report: {report}", quiet)
    except OSError:
        pass
    if args.pod2:
        try:
            sidecar = core.write_pod2_chapters(output, result.chapters, result.total_ms)
            _print(f"  Chapters JSON: {sidecar}", quiet)
        except OSError:
            pass
    if getattr(args, "rss_url", ""):
        try:
            from . import rss as rss_mod
            rss_path = rss_mod.write_rss(result, tags, args.rss_url,
                                         narrator=tags.narrator,
                                         series_title=tags.series_title,
                                         series_index=tags.series_index)
            _print(f"  RSS feed: {rss_path}", quiet)
        except Exception as exc:
            _err(f"warning: could not write RSS feed: {exc}")
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
