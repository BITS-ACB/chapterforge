"""Persistent user settings for ChapterForge.

Settings live in a small JSON file under the per-user application-data
directory (``%APPDATA%\\ChapterForge`` on Windows). Loading never raises:
a missing or corrupt file simply yields the defaults, so the app always
starts cleanly.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

APP_FOLDER_NAME = "ChapterForge"

DEFAULTS: Dict[str, Any] = {
    # Sticky tag defaults that usually stay the same between projects.
    "artist": "",
    "album_artist": "",
    "genre": "",
    # Remembered locations for friendlier dialogs.
    "last_input_dir": "",
    "last_output_dir": "",
    "last_cover_dir": "",
    # Build preferences.
    "title_source": "filename",   # 'filename' or 'embedded'
    "output_format": "mp3",       # 'mp3' or 'm4b'
    "bitrate": "192k",
    "normalize": False,
    "auto_cover": True,
    "write_pod2": False,          # also write a Podcasting 2.0 chapters sidecar
    "gap_seconds": 0.0,           # silence inserted between chapters (0 = none)
    # Accessibility / announcements.
    "announce_verbosity": "normal",  # 'quiet', 'normal' or 'verbose'
    "text_scale": 100,            # UI font scaling percent (100 = system default)
    "high_contrast": False,       # high-contrast colour theme
    # Recently opened folders / masters / jobs (most-recent first).
    "recent": [],
    # Player preferences.
    "skip_seconds": 10,           # rewind / fast-forward step
    "default_volume": 80,         # 0-100
    # Silence auto-chaptering defaults.
    "silence_noise_db": -30.0,
    "silence_min_seconds": 0.8,
    # Window geometry.
    "win_w": 940,
    "win_h": 760,
    "win_x": -1,
    "win_y": -1,
    "win_max": False,
}


def config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.join(
        os.path.expanduser("~"), ".config")
    return os.path.join(base, APP_FOLDER_NAME)


def config_path() -> str:
    return os.path.join(config_dir(), "settings.json")


def load() -> Dict[str, Any]:
    """Return settings merged over the defaults (never raises)."""
    data = dict(DEFAULTS)
    try:
        with open(config_path(), "r", encoding="utf-8") as fh:
            stored = json.load(fh)
        if isinstance(stored, dict):
            for key in DEFAULTS:
                if key in stored:
                    data[key] = stored[key]
    except (OSError, ValueError):
        pass
    return data


def save(data: Dict[str, Any]) -> None:
    """Persist *data* (best effort; failures are swallowed)."""
    try:
        os.makedirs(config_dir(), exist_ok=True)
        merged = {key: data.get(key, DEFAULTS[key]) for key in DEFAULTS}
        tmp = config_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, indent=2)
        os.replace(tmp, config_path())
    except OSError:
        pass
