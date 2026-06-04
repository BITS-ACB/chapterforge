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

- **`core.py`** — All UI-free audio logic: folder scanning, FFmpeg probing/concatenation, chapter tagging via Mutagen. This is the heart of the app.
- **`app.py`** — The wxPython GUI (large single-file). Long operations run on a background worker thread; the UI never blocks. Communicates with core via results posted back to the main thread.
- **`cli.py`** — Click-based CLI that calls into `core.py` directly.
- **`player.py`** — In-app audio player (wx-based, fully keyboard accessible, chapter-aware).
- **`watcher.py` / `watcher_config.py` / `watch_dialogs.py` / `tray.py`** — Background folder-watching engine, system-tray controller, and associated dialogs.
- **`settings.py`** — Persistent JSON user settings at `%APPDATA%\ChapterForge\settings.json`.
- **`manifest.py`** — `.cfjob` job file (hand-editable UTF-8 text) parsing and writing.
- **`notify.py`** — Toast, screen-reader, and JSON log notifications.
- **`a11y.py`** — Accessibility/screen-reader bridge (Prism backend, optional `prismatoid` package).
- **`updates.py`** — GitHub Releases update checker.

Entry points: `main.py` (GUI/watcher), `cli_main.py` (CLI console).

## Key Constraints

- **Accessibility is a first-class requirement.** All UI controls must have accessible names. Use `ctrl.SetName()` / `ctrl.SetLabel()`. Never remove keyboard access from any feature. Announce background-thread results via `a11y.announce()`.
- **Worker thread model:** Long operations (build, probe, file I/O) must run on the background thread in `app.py`. Post results back to the main thread with wx events — never call wx UI methods from a worker thread.
- **Natural sort:** Track ordering uses natural sort (`track2` before `track10`). See `core.py` for the sort key used; don't swap in a lexicographic sort.
- **FFmpeg is external.** In development FFmpeg must be on PATH. In releases it is bundled under `_internal/`. The `core.py` functions resolve the FFmpeg binary path via a helper — don't hardcode paths.
- **Chapter format:** Chapters are written as ID3v2 CHAP + CTOC frames via Mutagen. The format must remain compatible with podcast apps (Overcast, Pocket Casts, AntennaPod). Don't change frame structure without testing playback.

## Build & Release

See `docs/DEPLOYMENT.md` for the full release checklist. Version is set in four places: `pyproject.toml`, `chapterforge/__init__.py`, `installer/ChapterForge.iss`, and `CHANGELOG.md`. The PyInstaller spec (`ChapterForge.spec`) produces a one-folder build under `dist/ChapterForge/` with two executables (`ChapterForge.exe` windowed, `chapterforge-cli.exe` console) and a shared `_internal/` runtime including bundled FFmpeg.
