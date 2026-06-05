# ChapterForge — Deployment Guide

This document describes how to build, package, release and update ChapterForge
on Windows.

---

## 1. Prerequisites

- **Python 3.10+** (developed on 3.12).
- **FFmpeg** — Automatically downloaded by the build process if missing. The
  script `tools/get_ffmpeg.py` fetches prebuilt binaries from gyan.dev and
  places them in `bin/` at the repo root. For a self-contained build, PyInstaller
  bundles them and the app resolves them from `_internal\bin\` at runtime.
- Python build dependencies:

  ```bash
  pip install -r requirements.txt
  pip install pyinstaller
  ```

- **Inno Setup 6** for the installer. `ISCC.exe` is typically at:

  ```
  C:\Users\<you>\AppData\Local\Programs\Inno Setup 6\ISCC.exe
  ```

  (It is usually **not** on `PATH`; call it by full path.)

---

## 2. Versioning

ChapterForge follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

When cutting a release, update the version in **all** of these places:

- `pyproject.toml` → `[project] version`
- `chapterforge/__init__.py` (or wherever `__version__` is defined)
- `installer/ChapterForge.iss` → `AppVersion` / `MyAppVersion`
- `CHANGELOG.md` (add a dated section)

The GitHub tag should be `vMAJOR.MINOR.PATCH` (e.g. `v1.0.0`).

---

## 3. Run the tests

```bash
python -m pytest -q
```

The audio tests synthesize tiny MP3s with FFmpeg and are skipped if FFmpeg is
not on `PATH`. All tests must pass before building a release.

---

## 4. Build the executables (PyInstaller)

First, ensure FFmpeg binaries are present (automatically downloaded if missing):

```bash
python tools/get_ffmpeg.py
```

Then generate the HTML help that the app's **Help** menu opens (the spec
bundles `docs/html`):

```bash
python tools/build_docs.py
```

Then build:

```bash
pyinstaller ChapterForge.spec
```

This produces a **one-folder** build under `dist\ChapterForge\`:

- `ChapterForge.exe` — the GUI app (windowed, `console=False`).
- `chapterforge-cli.exe` — the CLI (console, `console=True`).
- `_internal\` — Python runtime, dependencies, and `_internal\bin\ffmpeg.exe` /
  `ffprobe.exe`.

The one-folder layout is deliberate: there is **no per-launch temp extraction**,
which avoids the temp-folder cleanup problems of one-file builds when the app
closes.

Smoke-test the build before packaging:

```bash
dist\ChapterForge\chapterforge-cli.exe "C:\path\to\sample\folder" --list
dist\ChapterForge\ChapterForge.exe
```

---

## 5. Build the installer (Inno Setup)

```bash
& "C:\Users\<you>\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer\ChapterForge.iss
```

This wraps `dist\ChapterForge\` into a single `ChapterForge-Setup.exe` under the
installer's output directory. The installer is **per-user** (no admin required),
creates Start-menu shortcuts for the GUI and adds the CLI to the install folder.
Autostart of the watcher is handled **in-app** (per-user `HKCU\…\Run`), not by
the installer, so the installer needs no elevation.

---

## 6. Publish a GitHub Release

1. Commit and tag: `git tag v1.0.0 && git push --tags`.
2. Create a Release for the tag on GitHub.
3. Attach `ChapterForge-Setup.exe` as a release asset.
4. Paste the relevant `CHANGELOG.md` section as the release notes.

---

## 7. The update feed

The in-app **Check for Updates** feature (`chapterforge/updates.py`) queries the
**GitHub Releases API** for the configured repository, compares the latest tag
to the running version, and points users at the download.

Before the first public release, replace the placeholders in
`chapterforge/updates.py`:

```python
GITHUB_OWNER = "bits-acb"   # -> your GitHub org/user
GITHUB_REPO  = "chapterforge"
```

Notes on the implementation (adapted from QUILL):

- Versions are compared with a tuple ranking so finals outrank pre-releases.
- Only **HTTPS** URLs on trusted GitHub hosts are accepted for the download
  link.
- Network/parse failures are reported gracefully; they never crash the app.

So each release is picked up automatically by existing installs once the tag is
published — no separate update server is required.

---

## 8. Release checklist

- [ ] Version bumped in `pyproject.toml`, `__init__`, `.iss`, `CHANGELOG.md`.
- [ ] `python -m pytest -q` passes.
- [ ] `GITHUB_OWNER`/`GITHUB_REPO` set correctly in `updates.py`.
- [ ] `pyinstaller ChapterForge.spec` succeeds; both exes smoke-tested.
- [ ] `ISCC.exe installer\ChapterForge.iss` produces `ChapterForge-Setup.exe`.
- [ ] Installer test-installed and launched on a clean user profile.
- [ ] Git tag `vX.Y.Z` pushed.
- [ ] GitHub Release created with installer asset + changelog notes.
- [ ] **Check for Updates** in the previous version detects the new release.
