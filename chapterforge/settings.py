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
    "prefer_id3_tags": False,     # when True, prefer ID3 tags over filename when available
    "output_format": "mp3",       # 'mp3', 'm4b', 'flac' or 'opus'
    "bitrate": "192k",
    "normalize": False,
    "auto_cover": True,
    "write_pod2": False,          # also write a Podcasting 2.0 chapters sidecar
    "gap_seconds": 0.0,           # silence inserted between chapters (0 = none)
    # Accessibility / announcements.
    "announce_verbosity": "normal",  # 'quiet', 'normal' or 'verbose'
    "text_scale": 100,            # UI font scaling percent (100 = system default)
    # Recently opened folders / masters / jobs (most-recent first).
    "recent": [],
    # Player preferences.
    "skip_seconds": 10,           # rewind / fast-forward step
    "default_volume": 80,         # 0-100
    "pause_at_chapter_end": False,  # pause playback at each chapter boundary instead of continuing
    # Silence auto-chaptering defaults.
    "silence_noise_db": -30.0,
    "silence_min_seconds": 0.8,
    # Window geometry.
    "win_w": 940,
    "win_h": 760,
    "win_x": -1,
    "win_y": -1,
    "win_max": True,
    # Startup behaviour.
    "start_minimized": False,       # hide window on launch; show tray icon instead
    "check_updates_startup": True,  # silently check for updates at launch
    "wizard_seen": False,           # True once the setup wizard has been completed
    # Colour theme.
    "theme": "system",         # 'system', 'light', 'dark', 'high_contrast'
    "high_contrast": False,    # kept for backwards compatibility with older settings files
    # Per-file loudness normalization (Feature 8).
    "per_file_normalize": False,   # normalize each source file individually
    "normalize_lufs": -16.0,       # LUFS target for per-file normalization
    # Chapter list column visibility (Feature 10): [#, Title, Start, Duration, Source]
    "list_columns": [True, True, True, True, True],
    # Keyboard shortcut overrides (Feature 13): maps command name -> key string
    "key_overrides": {},
    # Reusable build presets (Feature 4): {name: {format, bitrate, normalize, ...}}
    "presets": {},
    # Chapter transition fade duration in milliseconds (0 = no fade).
    "fade_ms": 0,
    # Beta features opt-in: enables experimental functionality (e.g. Auphonic integration).
    "beta_features": False,
    # Silence trimming: strip leading/trailing silence from each track before concat.
    "trim_silence": False,
    "trim_silence_db": -50.0,    # dBFS threshold
    "trim_silence_min_ms": 100.0,  # minimum silence duration to detect at edges
    # Narrator and series metadata fields.
    "narrator": "",
    "series_title": "",
    "series_index": "",
    # RSS feed export: write a .rss sidecar after a successful build.
    "write_rss": False,
    "rss_media_url": "",   # base URL where the audio file will be hosted
    # ACX compliance check: run automatically after every build.
    "acx_check_after_build": False,
    # Build log: keep a rolling log of recent builds.
    "log_build_history": True,
    # Feature flags: {flag_key: bool} overrides layered on chapterforge.feature_flags.REGISTRY defaults.
    "feature_flags": {},
    # Release channel: 'general', 'beta' or 'alpha'. Controls which optional
    # features in the registry are available to opt into at all.
    "release_channel": "general",
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
