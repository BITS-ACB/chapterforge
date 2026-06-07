"""The ChapterForge job file (``.cfjob``) - a simple, hand-editable manifest.

Format (UTF-8, resolved relative to the job file's own folder)::

    # Lines starting with '#' are comments.
    # '@key = value' lines set tags / build options for the master.
    # Every other non-empty line is a track, in order:
    #     filename | Chapter title
    # The title (and the '|') is optional; it defaults to the filename.

    @title  = My Audiobook
    @artist = Jane Author
    @album  = My Audiobook
    @genre  = Audiobook
    @year   = 2024
    @cover  = cover.jpg
    @output = My Audiobook - Master.mp3
    @bitrate = 192k
    @normalize = false

    01 - Opening.mp3       | Opening
    02 - The First Part.mp3 | The First Part

Parsing is forgiving about unknown ``@keys`` but strict about referenced
files: a track whose file is missing is reported so the caller can refuse to
build a wrong audiobook.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import core

DEFAULT_JOB_NAME = "chapters.cfjob"
JOB_EXTENSION = ".cfjob"

_TAG_KEYS = {
    "title", "artist", "album", "album_artist", "albumartist",
    "genre", "year", "comment", "cover", "output", "bitrate", "normalize",
    "title_source", "titlesource",
    "narrator", "series", "series_title", "series_index", "series_part",
}

_BOOL_TRUE = {"1", "true", "yes", "on"}


@dataclass
class ManifestTrack:
    filename: str
    title: str = ""


@dataclass
class Manifest:
    tracks: List[ManifestTrack] = field(default_factory=list)
    options: Dict[str, str] = field(default_factory=dict)

    # convenience option accessors -------------------------------------
    def option(self, key: str, default: str = "") -> str:
        return self.options.get(key, default)

    @property
    def normalize(self) -> bool:
        return self.options.get("normalize", "").strip().lower() in _BOOL_TRUE

    @property
    def bitrate(self) -> str:
        return self.options.get("bitrate", "") or "192k"


def parse_bool(value: str) -> bool:
    return value.strip().lower() in _BOOL_TRUE


def read_manifest(path: str) -> Manifest:
    """Parse a ``.cfjob`` file into a :class:`Manifest` (never raises on content)."""
    manifest = Manifest()
    with open(path, "r", encoding="utf-8-sig") as fh:
        for raw in fh:
            line = raw.rstrip("\n").strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("@"):
                key, _, value = line[1:].partition("=")
                key = key.strip().lower().replace(" ", "_")
                if key in _TAG_KEYS:
                    if key == "albumartist":
                        key = "album_artist"
                    if key == "titlesource":
                        key = "title_source"
                    manifest.options[key] = value.strip()
                continue
            filename, sep, title = line.partition("|")
            manifest.tracks.append(ManifestTrack(
                filename=filename.strip(),
                title=title.strip() if sep else "",
            ))
    return manifest


def resolve_manifest(manifest: Manifest, folder: str
                     ) -> Tuple[List[Tuple[str, str]], List[str]]:
    """Return ``([(abspath, title), ...], [missing_filenames])`` for *folder*.

    Filenames are resolved relative to *folder*. Absolute paths in the job are
    rejected (reported as missing) to keep jobs portable and safe.
    """
    resolved: List[Tuple[str, str]] = []
    missing: List[str] = []
    for track in manifest.tracks:
        name = track.filename
        if os.path.isabs(name) or name.startswith(("..", "/", "\\")):
            missing.append(name)
            continue
        full = os.path.normpath(os.path.join(folder, name))
        if os.path.commonpath([os.path.abspath(full), os.path.abspath(folder)]) \
                != os.path.abspath(folder):
            missing.append(name)
            continue
        if os.path.isfile(full):
            resolved.append((full, track.title))
        else:
            missing.append(name)
    return resolved, missing


def manifest_tags(manifest: Manifest, folder: str) -> core.Tags:
    """Build :class:`core.Tags` from a manifest's options."""
    opt = manifest.options
    cover = opt.get("cover", "").strip()
    if cover and not os.path.isabs(cover):
        cover = os.path.join(folder, cover)
    return core.Tags(
        title=opt.get("title", ""),
        artist=opt.get("artist", ""),
        album=opt.get("album", ""),
        album_artist=opt.get("album_artist", ""),
        genre=opt.get("genre", ""),
        year=opt.get("year", ""),
        comment=opt.get("comment", ""),
        cover_path=cover if cover and os.path.isfile(cover) else "",
        narrator=opt.get("narrator", ""),
        series_title=opt.get("series") or opt.get("series_title", ""),
        series_index=opt.get("series_part") or opt.get("series_index", ""),
    )


def find_job_file(folder: str) -> Optional[str]:
    """Return a ``.cfjob`` path in *folder*, preferring ``chapters.cfjob``."""
    default = os.path.join(folder, DEFAULT_JOB_NAME)
    if os.path.isfile(default):
        return default
    try:
        for name in sorted(os.listdir(folder)):
            if name.lower().endswith(JOB_EXTENSION):
                return os.path.join(folder, name)
    except OSError:
        pass
    return None


def write_manifest(path: str, items: Sequence[core.Mp3Item], tags: core.Tags,
                   output_name: str = "", bitrate: str = "192k",
                   normalize: bool = False) -> None:
    """Write a human-friendly ``.cfjob`` describing *items* and *tags*."""
    lines: List[str] = [
        "# ChapterForge job file - edit freely, then run it from the app or CLI.",
        "# '@key = value' sets a tag/option; other lines are 'filename | Chapter title'.",
        "# Order below is the order chapters are built.",
        "",
    ]

    def opt(key: str, value: str) -> None:
        lines.append(f"@{key} = {value}")

    opt("title", tags.title)
    opt("artist", tags.artist)
    opt("album", tags.album)
    opt("album_artist", tags.album_artist)
    opt("genre", tags.genre)
    opt("year", tags.year)
    if tags.comment:
        opt("comment", tags.comment)
    if tags.cover_path:
        opt("cover", os.path.basename(tags.cover_path))
    if output_name:
        opt("output", output_name)
    opt("bitrate", bitrate)
    opt("normalize", "true" if normalize else "false")
    lines.append("")

    for it in items:
        lines.append(f"{it.filename} | {it.title}")

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(tmp, path)
