# ChapterForge 1.0.0 - Product Requirements Document

**Product**: ChapterForge  
**Version**: 1.0.0  
**Date**: 2026-06-06  
**Status**: Shipped  

---

## 1. Executive Summary

ChapterForge is a Windows desktop application that converts a folder of audio files into a single master audio file with embedded, navigable chapter markers. It targets content creators - audiobook producers, podcasters, and lecture archivists - with a first-class requirement that the tool be fully operable by blind and low-vision users using only a keyboard and screen reader.

The application ships with a GUI (wxPython), a CLI (Click), a background folder-watching engine with system-tray controller, and a beta Auphonic audio post-production integration. All core audio work is delegated to FFmpeg and Mutagen; ChapterForge provides the workflow, accessibility layer, and chapter-format expertise on top.

---

## 2. Goals

1. Make professional-grade chapter-marked audio production accessible to users who cannot use a mouse.
2. Produce chapter markers that are compatible with major podcast and audiobook players (Overcast, Pocket Casts, AntennaPod, Apple Books, Prologue).
3. Keep the core build pipeline headless so that CLI and background-watcher workflows are first-class, not afterthoughts.
4. Never block the GUI thread; all long operations run on a background worker thread.
5. Provide an upgrade path to Auphonic cloud post-production for users who want leveling, noise reduction, and transcripts without a separate tool.

---

## 3. Non-Goals

- ChapterForge is not a DAW. It does not support real-time recording, mixing tracks, or non-destructive editing beyond lossless copy operations.
- ChapterForge is not a podcast hosting platform. It does not publish to RSS feeds or podcast directories.
- ChapterForge does not resell or proxy third-party services. The Auphonic integration uses the user's own Auphonic account and credits.
- ChapterForge does not support video input or video output at any point in its pipeline.

---

## 4. Target Users

### 4.1 Blind / Low-Vision Audiobook Producer

Needs full keyboard navigation, accurate screen-reader announcements at every step, and a tool that works without a mouse. This user is the accessibility constraint: if a feature cannot be used by this person, it is not done.

### 4.2 Sighted Podcast Creator

Uses the GUI for quick chapter editing, cover art, and one-click builds. May use the watcher system to automate weekly episode processing.

### 4.3 Lecture / Conference Archivist

Processes large batches of recordings via the CLI or batch watcher. Values natural sort, silence-based auto-chaptering, and reliable output naming.

### 4.4 Audiobook Publisher (Small Studio)

Produces ACX-spec audiobooks. Needs per-file normalization to LUFS targets, FLAC output for archiving, and reproducible builds via job files. May use the Auphonic beta integration for final audio cleanup.

---

## 5. System Requirements

- **OS**: Windows 10 / 11 (64-bit)
- **RAM**: 4 GB minimum, 8 GB recommended
- **Disk**: 500 MB for application plus space for audio files and temporary processing
- **FFmpeg**: Bundled in production releases under `_internal/`; must be on PATH in development
- **Screen readers**: NVDA, JAWS, Windows Narrator (NVDA is the primary test target)
- **Python runtime**: Bundled in production releases via PyInstaller

---

## 6. Architecture

The app is structured as a Python package under `chapterforge/` with clean separation between layers:

| Module | Responsibility |
|---|---|
| `core.py` | All UI-free audio logic: scan, probe, concatenate, tag |
| `app.py` | wxPython GUI; long ops on background thread, results via wx events |
| `cli.py` | Click CLI that calls `core.py` directly |
| `player.py` | In-app chapter-aware audio player |
| `watcher.py` / `tray.py` | Background folder watcher and system-tray controller |
| `settings.py` | Persistent JSON settings at `%APPDATA%\ChapterForge\settings.json` |
| `manifest.py` | `.cfjob` job-file parsing and writing |
| `notify.py` | Toast, screen-reader, and JSON-log notifications |
| `a11y.py` | Prism screen-reader bridge (optional `prismatoid` package) |
| `updates.py` | GitHub Releases update checker |
| `auphonic/` | Auphonic integration: client, auth, service, models, DB, polling |
| `auphonic_dialogs.py` | Auphonic wxPython dialogs |

Entry points: `main.py` (GUI / watcher), `cli_main.py` (CLI console).

---

## 7. Core Features

### 7.1 Folder-to-Master Build

The primary workflow: open a folder of audio files, review the automatically assembled chapter list, set metadata, and build a single master file with embedded chapter markers.

- Supported input formats: MP3, FLAC, WAV, OGG, M4A, AAC, Opus, WMA, MP2
- Output formats: MP3 (ID3v2 CHAP/CTOC), M4B (native MP4 chapters), FLAC lossless (Vorbis Comment chapters), Opus (Ogg Opus, Vorbis Comment chapters)
- Bitrate options: 128k to 320k for lossy outputs; lossless copy for FLAC source-to-FLAC output
- Cover art: auto-detected from folder or manually selected; embedded in output
- Natural sort for track ordering (`track2` before `track10`)
- Progress announced to screen reader via `a11y.announce()`
- Build runs on background thread; UI remains responsive

### 7.2 Chapter Management

- Add, remove, reorder (Alt+Up / Alt+Down), merge adjacent chapters
- Inline title editing (F2) and batch title editing (transforms: title case, strip track numbers, strip underscores, find-and-replace, number pattern)
- Undo / Redo (Ctrl+Z / Ctrl+Y) for all chapter list operations; stack depth 50; cleared on new load or build
- Chapter list column visibility: toggle #, Title, Start, Duration, Source columns (View > Columns)
- CUE sheet import (applies chapter titles by position in both build and edit modes)
- CSV chapter export (chapter number, title, start, duration, link URL, image path)
- File renaming from chapter titles (pattern: `{n}`, `{n:02d}`, `{title}`, `{ext}`; live preview before applying)
- Chapter validation: automatic checking for boundary issues

### 7.3 Edit Mode (Single-File Editing)

Open an existing chaptered master file to re-edit chapter boundaries and titles without rebuilding from source files.

- Split a chapter at the current playhead position
- Merge chapters up
- Save changes back to the open file (lossless ID3 rewrite via Mutagen)

### 7.4 In-App Audio Player

Fully keyboard-accessible, chapter-aware audio player:

- Play / Pause (Space), Stop, Previous/Next Chapter
- Rewind / Fast-forward by configurable step (default 10 seconds)
- Volume control
- Go to Time dialog (Ctrl+G): accepts HH:MM:SS, MM:SS, or decimal seconds

### 7.5 Lossless Trim and Cut

- Set begin and end trim markers from the current playhead position
- Pre-listen as cut: plays from just before the cut point
- Save trimmed selection to a new file using FFmpeg lossless copy (no quality loss)
- Trim state resets when a new file is loaded

### 7.6 Split One Long Recording into Chapters

- Open a single long recording in edit mode
- Mark chapter boundaries using Split Here
- File > Save as Individual Chapter Files: splits into one file per chapter using FFmpeg lossless copy

### 7.7 Silence-Based Auto-Chaptering

Automatically detect chapter boundaries by analyzing silence gaps:

- Configurable noise threshold (default -30 dB)
- Configurable minimum silence duration (default 0.8 seconds)
- Available in GUI and CLI

### 7.8 Metadata Tagging

Full ID3v2 and MP4/FLAC metadata support:

- Standard fields: Title, Artist, Album Artist, Genre, Year, Comment, Narrator, Series
- Cover art (embedded)
- Metadata lookup from MusicBrainz and Open Library
- Podcasting 2.0 chapter sidecar (optional)
- Sticky tag defaults: remembered between projects in settings

### 7.9 Audio Processing Options

- **Global normalization**: FFmpeg loudnorm pass over the final output
- **Per-file normalization**: normalize each source file individually before concatenating (target LUFS configurable, default -16.0)
- **Chapter transition fades**: fade-out then fade-in at each chapter boundary (0-5 seconds, default 0); forces re-encoding of boundary portions

### 7.10 Reusable Build Presets

Settings dialog includes a preset bar:

- Three built-in presets: Podcast MP3, Audiobook M4B, FLAC Archive
- Users can save any combination of build settings as a named preset
- Presets stored in `settings.json` under `"presets"`

### 7.11 Job Files (.cfjob)

Human-readable, UTF-8 text files storing complete project configurations:

- Version-controllable; can be shared or committed to Git
- Supports all metadata fields, output configuration, and chapter list
- Load via File > Open Job File (Ctrl+L); save via File > Save Job

### 7.12 Background Folder Watcher

Automated processing engine with system-tray integration:

- Watch one or more folders for new audio content
- Configurable naming templates for output files (`{folder}`, `{date}`, `{datetime}`, etc.)
- Stability detection: waits for folder content to stabilize before processing
- Atomic `.chapterforge_processing` lock files prevent double-processing
- `.chapterforge_done` markers make folders one-shot
- `.chapterforge_failed` files retry only after content changes
- Output written to `_ChapterForge` sub-folder to avoid re-triggering the watch
- Start at sign-in option for persistent watching
- Progress via toast and screen-reader notifications

### 7.13 Command Line Interface

Full-featured CLI for automation and scripting (Click-based):

```
chapterforge <folder>                        # Build from folder
chapterforge -i .\chapters -o book.mp3       # Explicit in/out
chapterforge .\chapters --normalize          # With loudness normalization
chapterforge .\chapters --dry-run --list     # Preview without building
chapterforge --job mybook.cfjob              # Process from job file
chapterforge --batch "C:\Audiobooks"         # Batch mode (every book sub-folder)
chapterforge --split-silence --noise-db -30 --min-silence 0.8 long.mp3
```

Return codes: 0 success, 1 general error, 2 invalid arguments, 3 processing error, 4 file not found, 5 insufficient permissions.

### 7.14 Diagnostics

Tools > Save Diagnostics: exports a report for support including FFmpeg version, Python version, settings, and system info.

---

## 8. Accessibility Requirements

Accessibility is a first-class, binding requirement. Every interactive control must have an accessible name and a visible label.

### 8.1 Screen Reader Compatibility

- Primary target: NVDA on Windows 10/11
- Secondary targets: JAWS, Windows Narrator
- Prism screen-reader bridge via optional `prismatoid` package
- `a11y.announce()` used for all background operation milestones (start, progress, completion, errors)
- Verbosity configurable: quiet, normal, verbose

### 8.2 Accessible Name Rules (wxPython)

These rules are binding and must not be violated:

| Control type | How to set the accessible name |
|---|---|
| `wx.CheckBox` | `label=` constructor parameter (Win32 button window text) |
| `wx.SpinCtrl` / `wx.SpinCtrlDouble` | `ctrl.SetAccessible(_NamedAccessible(ctrl, "description"))` |
| All other controls | `ctrl.SetName("description")` |

### 8.3 Keyboard Navigation

- All features reachable without a mouse
- Tab order follows logical visual order
- No keyboard traps
- First meaningful control receives focus when a dialog opens (`ctrl.SetFocus()`)
- Command palette (Ctrl+Shift+P): search all commands by name

### 8.4 Visual Accessibility

- High-contrast color theme option
- Text scaling: 80-150% (Ctrl+= / Ctrl+-)
- System theme, light, dark, and high-contrast theme modes
- Color alone is never used as the sole indicator of state

### 8.5 Keyboard Shortcuts (primary)

| Shortcut | Action |
|---|---|
| Ctrl+Shift+O | Open folder of audio files |
| Ctrl+O | Open existing chaptered file |
| Ctrl+B | Build master file |
| Ctrl+S | Build (build mode) / Save changes (edit mode) |
| Ctrl+L | Load job file |
| Ctrl+G | Go to time (player) |
| Ctrl+W | Set up automatic building (watcher) |
| Ctrl+, | Settings |
| Ctrl+Shift+P | Command palette |
| Ctrl+Z / Ctrl+Y | Undo / Redo |
| F2 | Edit selected chapter title |
| Alt+Up / Alt+Down | Move chapter up / down |
| Space | Play / Pause |
| Ctrl+Left / Ctrl+Right | Previous / Next chapter |

Keyboard shortcut overrides: users can remap any command via Settings (stored in `settings.json` under `"key_overrides"`).

---

## 9. Chapter Format Compatibility

Chapter markers are written as ID3v2 CHAP + CTOC frames (MP3) and native MP4 chapter atoms (M4B) via Mutagen. The format must remain compatible with:

- Overcast (iOS)
- Pocket Casts (iOS, Android, web)
- AntennaPod (Android)
- Apple Books / Prologue (M4B)
- Podlove Web Player (HTML5)

FLAC output uses Vorbis Comment chapters (CHAPTER001 / CHAPTER001NAME convention).

Do not alter the frame structure without testing playback compatibility.

---

## 10. Settings

All settings persist in `%APPDATA%\ChapterForge\settings.json`. Loading never raises; a missing or corrupt file yields defaults.

Key configurable settings:

| Setting | Default | Description |
|---|---|---|
| `output_format` | `"mp3"` | mp3, m4b, or flac |
| `bitrate` | `"192k"` | Output bitrate for lossy formats |
| `normalize` | `false` | Global loudness normalization |
| `per_file_normalize` | `false` | Per-file normalization before concat |
| `normalize_lufs` | `-16.0` | LUFS target for per-file normalization |
| `gap_seconds` | `0.0` | Silence inserted between chapters |
| `fade_ms` | `0` | Chapter transition fade duration (ms) |
| `write_pod2` | `false` | Also write Podcasting 2.0 chapters sidecar |
| `announce_verbosity` | `"normal"` | Screen reader verbosity |
| `text_scale` | `100` | UI font scaling percent |
| `theme` | `"system"` | system, light, dark, high_contrast |
| `skip_seconds` | `10` | Player rewind/fast-forward step |
| `start_minimized` | `false` | Hide window on launch, show tray icon |
| `check_updates_startup` | `true` | Silent update check at launch |
| `beta_features` | `false` | Enables beta features (Auphonic integration) |
| `silence_noise_db` | `-30.0` | Silence detection threshold |
| `silence_min_seconds` | `0.8` | Minimum silence duration for chapter break |

---

## 11. Build and Distribution

- **PyInstaller spec**: `ChapterForge.spec`, produces one-folder build under `dist/ChapterForge/`
- **Two executables**: `ChapterForge.exe` (windowed GUI), `chapterforge-cli.exe` (console CLI)
- **Shared runtime**: `_internal/` contains Python runtime, all packages, and bundled FFmpeg
- **Installer**: Inno Setup (`installer/ChapterForge.iss`), produces `ChapterForge-Setup-x.x.x.exe`
- **Portable installer**: `installer/ChapterForge-Portable.iss`, produces a portable zip
- **Version**: Set in four places - `pyproject.toml`, `chapterforge/__init__.py`, `installer/ChapterForge.iss`, `CHANGELOG.md`
- **Build workflow**: GitHub Actions `build-release.yml`; injects `CHAPTERFORGE_GITHUB_TOKEN` and Auphonic OAuth credentials from BITS-ACB org secrets at build time
- **Update checker**: `updates.py` compares against GitHub Releases; runs silently at startup if `check_updates_startup` is true
- **Feedback**: Help > Report an Issue opens an in-app dialog that files a GitHub issue on BITS-ACB/chapterforge via the `feedback-hub` library

---

## 12. Auphonic Integration (Beta)

Auphonic integration is an opt-in beta feature. Enable it under **Tools > Settings > General > Enable beta features**. The Auphonic menu appears between View and Help after saving.

### 12.1 Purpose

Connect a user's own Auphonic account to apply professional audio post-production (leveling, noise reduction, transcripts, captions) to audio files without leaving ChapterForge. Auphonic charges the user's own credits directly; ChapterForge does not resell or proxy Auphonic billing.

### 12.2 Authentication

- OAuth 2.0 RFC 8252 loopback redirect pattern for desktop apps
- Opens browser for Auphonic login; a local HTTP server on a random port captures the authorization code
- Access and refresh tokens stored encrypted at rest using Windows DPAPI (ctypes) with a base64 + machine-key fallback
- Token stored at `%APPDATA%\ChapterForge\auphonic_token.bin`
- Disconnect removes stored tokens

### 12.3 Menu Actions

| Menu item | Action |
|---|---|
| Auphonic > Connect Account | OAuth connect / view credit balance / disconnect |
| Auphonic > New Production | Submit an audio file for Auphonic processing |
| Auphonic > Job History | View submitted jobs and download results |

### 12.4 New Production Workflow

1. Browse for a local audio file
2. File validated: extension check + ffprobe inspection; any file containing a video stream is rejected
3. Choose a preset (built-in or from Auphonic account)
4. Enter a production title
5. Credit estimate calculated (3-minute minimum applied for short files); warning shown if credits appear insufficient
6. Submit: creates Auphonic production, uploads file, starts processing
7. Background polling with exponential backoff (5s initial, 1.5x factor, 60s cap)
8. On completion: open Job History to download results

### 12.5 Built-in Presets

| Preset | Target | Outputs |
|---|---|---|
| Podcast Cleanup | -16 LUFS, denoise, leveler | MP3 |
| Podcast Cleanup + Transcript | same | MP3 + SRT + WebVTT + transcript HTML/TXT |
| Audiobook / ACX Draft | -18 LUFS, careful denoise | WAV + FLAC |
| Lecture Cleanup | denoise, silence cutting | MP3 + captions |
| Meeting / Interview Multitrack | host/guest tracks | MP3 |
| Archive Master | minimal processing | FLAC + WAV + stats |

### 12.6 Audio-Only Policy

- Only audio file extensions accepted (MP3, FLAC, WAV, OGG, M4A, AAC, Opus, etc.)
- `ffprobe` inspection confirms at least one audio stream and zero video streams before submission
- Video output formats blocked in results even if Auphonic returns them
- SSRF protection on remote URLs: HTTPS only, blocks localhost, private IP ranges, link-local addresses

### 12.7 Local Storage

- Job history and output metadata: SQLite at `%APPDATA%\ChapterForge\auphonic.db`
- Tables: `auphonic_jobs`, `auphonic_outputs`, `auphonic_schema_cache`, `auphonic_credit_snapshots`
- Downloaded result files: written to user-chosen folder via Job History > Download Results

### 12.8 Credential Injection

Production builds inject `AUPHONIC_CLIENT_ID` and `AUPHONIC_CLIENT_SECRET` from BITS-ACB org secrets at build time (same pattern as the GitHub feedback token). Development: set as environment variables before launching.

---

## 13. Notifications

`notify.py` provides three notification channels:

- **Toast**: Windows system toast notifications (build complete, watcher events)
- **Screen reader**: `a11y.announce()` calls via Prism bridge
- **JSON log**: Machine-readable log of all notifications at `%APPDATA%\ChapterForge\notify.log`

---

## 14. Security Considerations

- OAuth tokens encrypted at rest (DPAPI)
- GitHub feedback token injected at build time; never stored in source
- Auphonic OAuth credentials injected at build time; never stored in source
- SSRF protection in Auphonic URL validation
- No credentials in logs or diagnostic exports

---

## 15. Testing

Tests live in `tests/`. The suite synthesizes small MP3s via FFmpeg and is skipped if FFmpeg is not on PATH.

```
python -m pytest -q          # All tests
python -m pytest tests/test_core.py -q  # Single file
```

Test coverage areas:
- Core audio logic (scan, probe, concatenate, tag, trim, split, fades, normalization)
- Auphonic client (mocked HTTP)
- Auphonic models and dataclasses
- Auphonic audio validation (extension allowlist, ffprobe inspection, SSRF blocking)
- GitHub token integration (skipped unless `CHAPTERFORGE_GITHUB_TOKEN` env var is set)

---

## 16. Open Items and Future Work

The following are known gaps or areas for future consideration. They are not requirements for 1.0.0.

1. **Auphonic multitrack UI** - the service layer supports multitrack submissions, but the New Production dialog is singletrack-only in 1.0.0.
2. **Auphonic advanced algorithm controls** - basic preset selection only; per-algorithm tuning UI not yet built.
3. **Auphonic review-before-publish** - polling and download work; the Publish button in Job History is present but publishing to external Auphonic services is not exposed in the UI.
4. **Transcript viewer** - downloaded transcript files open in the system default app; no in-app viewer.
5. **Webhooks** - the polling fallback is implemented; a proper webhook receiver for faster status updates is not (desktop apps are not well-suited to this; polling is the right default).
6. **macOS / Linux** - the codebase is cross-platform Python but the installer, DPAPI encryption, and system-tray integration are Windows-only.
7. **Waveform visualization** - referenced in some documentation but not implemented in 1.0.0.
8. **AI chapter detection** - not implemented; referenced in early documentation drafts only.
