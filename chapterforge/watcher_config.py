"""Reusable "processes" (watch-folder profiles) for ChapterForge.

A *process* couples a watched folder with naming templates and tag defaults so
that any new sub-folder of MP3s dropped inside is built automatically. Stored
as atomic JSON in the per-user config dir, tolerant of corruption, and safe for
the GUI and the background watcher to share.

Template tokens (expanded per detected sub-folder):
    {folder}  the sub-folder name        {parent}  the watched folder's name
    {date}    today's date (YYYY-MM-DD)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import date
from typing import Dict, List

from . import settings as settings_mod

OUTPUT_SUBDIR = "_ChapterForge"  # generated masters live here (excluded from scans)

_INVALID_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | \
            {f"LPT{i}" for i in range(1, 10)}


@dataclass
class Process:
    name: str = "New process"
    watch_folder: str = ""
    enabled: bool = True
    output_template: str = "{folder} - Master.mp3"
    album_template: str = "{folder}"
    title_template: str = "{folder}"
    artist: str = ""
    album_artist: str = ""
    genre: str = ""
    title_source: str = "filename"   # 'filename' | 'embedded'
    bitrate: str = "192k"
    normalize: bool = False
    narrator: str = ""
    series_title: str = ""
    series_index: str = ""
    preset: str = ""   # named build preset from settings; overrides bitrate/normalize/format if set
    publish_destinations: str = ""  # "" (don't publish), "default", or comma-separated destination ids
    run_transcription: bool = False  # run AI whisper transcription after a successful build

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "Process":
        proc = cls()
        for f in proc.__dataclass_fields__:  # type: ignore[attr-defined]
            if f in data:
                setattr(proc, f, data[f])
        proc.enabled = bool(proc.enabled)
        proc.normalize = bool(proc.normalize)
        return proc


def sanitize_filename(name: str, fallback: str = "Master") -> str:
    """Make *name* a safe Windows filename component."""
    cleaned = _INVALID_FS.sub("_", name).strip().rstrip(". ")
    stem = os.path.splitext(cleaned)[0].upper()
    if not cleaned or stem in _RESERVED:
        return fallback
    return cleaned


def expand_template(template: str, *, folder: str, parent: str = "") -> str:
    return (template
            .replace("{folder}", folder)
            .replace("{parent}", parent)
            .replace("{date}", date.today().isoformat()))


def _processes_path() -> str:
    return os.path.join(settings_mod.config_dir(), "processes.json")


def load_processes() -> List[Process]:
    try:
        with open(_processes_path(), "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return []
    items = raw.get("processes") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []
    return [Process.from_dict(d) for d in items if isinstance(d, dict)]


def save_processes(processes: List[Process]) -> None:
    try:
        os.makedirs(settings_mod.config_dir(), exist_ok=True)
        tmp = _processes_path() + ".tmp"
        payload = {"processes": [p.to_dict() for p in processes]}
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(tmp, _processes_path())
    except OSError:
        pass
