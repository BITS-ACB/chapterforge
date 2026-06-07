# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ChapterForge** is a Windows desktop application (with CLI and background folder watcher) that converts a folder of MP3 files into a single master MP3 with embedded ID3v2 chapter markers (CHAP/CTOC). It targets fully accessible, screen-reader-compatible operation (keyboard-only, high-contrast theme, Prism bridge).

## Common Commands

```bash
# Run the GUI
python main.py

# Run CLI
python -m chapterforge.cli --help

# Launch background tray watcher
python main.py --watch

# Run all tests
python -m pytest -q

# Run a single test file
python -m pytest tests/test_core.py -q

# Generate HTML help docs
python tools/build_docs.py

# Build distributable (requires PyInstaller)
pyinstaller ChapterForge.spec
```

Tests synthesize small MP3s via FFmpeg and are skipped if FFmpeg is not on PATH.

## Architecture

The app is organized as a Python package under `chapterforge/` with a clean separation between core logic, GUI, CLI, and background services:

- **`core.py`** - All UI-free audio logic: folder scanning, FFmpeg probing/concatenation, chapter tagging via Mutagen. This is the heart of the app.
- **`app.py`** - The wxPython GUI (large single-file). Long operations run on a background worker thread; the UI never blocks. Communicates with core via results posted back to the main thread.
- **`cli.py`** - argparse-based CLI that calls into `core.py` directly.
- **`player.py`** - In-app audio player (wx-based, fully keyboard accessible, chapter-aware).
- **`watcher.py` / `watcher_config.py` / `watch_dialogs.py` / `tray.py`** - Background folder-watching engine, system-tray controller, and associated dialogs.
- **`settings.py`** - Persistent JSON user settings at `%APPDATA%\ChapterForge\settings.json`.
- **`manifest.py`** - `.cfjob` job file (hand-editable UTF-8 text) parsing and writing.
- **`notify.py`** - Toast, screen-reader, and JSON log notifications.
- **`a11y.py`** - Accessibility/screen-reader bridge (Prism backend, optional `prismatoid` package).
- **`updates.py`** - GitHub Releases update checker.

Entry points: `main.py` (GUI/watcher), `cli_main.py` (CLI console).

## Key Constraints

- **Accessibility is a first-class requirement.** This is a binding contract. Every interactive control MUST have an accessible name and a visible label. How to supply the accessible name depends on the control type - `SetName()` is NOT the screen-reader name for all controls:
  - **`wx.CheckBox`**: NVDA reads the `label=` constructor text (Win32 button window text). Never use `label=""` or `label="Enabled"`. Put the full descriptive label in `label=` and omit the `wx.StaticText` for that row - use `make_check()` in `SettingsDialog` for this pattern.
  - **`wx.SpinCtrl` / `wx.SpinCtrlDouble`**: composite Win32 controls; their inner edit field has no label by default. Always attach `ctrl.SetAccessible(_NamedAccessible(ctrl, "description"))` (class defined in `app.py` just above `SettingsDialog`). In `SettingsDialog` pass `use_accessible=True` to `make_row()`.
  - **All other controls**: `ctrl.SetName("description")` sets the accessible name via IAccessible and is the correct call.
  - Keyboard access: never disable keyboard navigation, tabbing, or shortcuts.
  - When a dialog opens, set focus on the first meaningful control via `ctrl.SetFocus()`.
  - Announce background operations (start, progress, completion) via `a11y.announce()`.
  - Test: launch with NVDA and verify all controls are announced clearly.
- **No m-dashes or emojis in the product.** Use regular hyphens (-) and plain text. This ensures cross-platform compatibility and readability.
- **Worker thread model:** Long operations (build, probe, file I/O, diagnostics) must run on the background thread in `app.py`. Post results back to the main thread with wx events - never call wx UI methods from a worker thread.
- **Natural sort:** Track ordering uses natural sort (`track2` before `track10`). See `core.py` for the sort key used; don't swap in a lexicographic sort.
- **FFmpeg is external.** In development FFmpeg must be on PATH. It is NOT bundled in releases; ChapterForge downloads an official Windows build on first run via `tools/get_ffmpeg.py` (also Help > Download FFmpeg). The `core.py` helper `_find_tool` resolves the binary by searching a bundled `bin/`, the app/`_MEIPASS` dir, then PATH - don't hardcode paths.
- **Chapter format:** Chapters are written as ID3v2 CHAP + CTOC frames via Mutagen. The format must remain compatible with podcast apps (Overcast, Pocket Casts, AntennaPod). Don't change frame structure without testing playback.

## Build & Release

See `docs/DEPLOYMENT.md` for the full release checklist. Version is set in five places: `pyproject.toml`, `chapterforge/__init__.py`, `installer/ChapterForge.iss`, `installer/ChapterForge-Portable.iss`, and `CHANGELOG.md`. The PyInstaller spec (`ChapterForge.spec`) produces a one-folder build under `dist/ChapterForge/` with two executables (`ChapterForge.exe` windowed, `chapterforge-cli.exe` console) and a shared `_internal/` runtime. FFmpeg is not included in the build; it is fetched on first run.
