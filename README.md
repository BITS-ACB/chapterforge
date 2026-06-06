# ChapterForge

**Accessible audio chapter management for Windows**

Build a professionally chaptered master MP3 or M4B from a folder of audio files. Fully keyboard-navigable with comprehensive screen reader support (NVDA, JAWS, Narrator) — designed from the ground up for BVI users and sighted users alike.

> See [`samples/README.md`](samples/README.md) for a test walkthrough.

## Highlights

- 📁 Point at a folder; files are discovered and **natural-sorted**
  (`track2` before `track10`).
- 🔖 One **ID3v2 CHAP** chapter per file plus a top-level **CTOC**, recognised
  by podcast/audiobook players (Apple Podcasts, Overcast, Pocket Casts,
  AntennaPod, VLC, foobar2000, AIMP, …).
- ✏️ **Chapter titles come from the filenames**; rename, reorder or remove
  chapters before building. Titles can also be read from each file's embedded
  ID3 title instead.
- 🏷️ Set the master's **Title, Artist, Album, Album artist, Genre, Year,
  Comment** and an optional **cover image** (auto-detected from the folder).
- 🎧 **MP3 or M4B** output — an MP3 with CHAP/CTOC, or an AAC **audiobook**
  with native MP4 chapters and an attached cover.
- ▶️ **Built-in accessible player** — preview the result with Play/Pause, Stop,
  Previous/Next chapter, Rewind/Forward (configurable step), volume and a
  position slider, with the current chapter announced as it plays.
- 🛠️ **Edit existing chaptered files** — open a finished MP3 (or M4B) to fix its
  tags and chapter titles; **merge**, **split at the playhead** or adjust a
  chapter's **start time**; save MP3s in place or any file with **Save As**.
- 🔁 **Import / export chapter lists** — Audacity labels, CUE sheets, plain
  timestamps or Podcasting 2.0 JSON.
- ⏱️ **Inter-chapter gaps**, a live **output size estimate**, and **post-build
  verification** that re-reads the file and confirms the chapter count.
- 🤫 **Auto-chapter by silence** and 📚 **batch-build** an entire library of book
  sub-folders in one pass.
- 🌐 **Podcasting 2.0 chapters** sidecar (`…chapters.json`) with optional
  per-chapter link URLs and images.
- ⚡ **Lossless** concatenation (`ffmpeg -c copy`) when every file shares the
  same format; automatic clean **re-encode** (with optional **loudness
  normalization**) when they don't.
- 🚦 **Pre-flight checks** warn about mixed sample rates / channels before a
  long build.
- 🧰 **Job files** (`.cfjob`): a tiny, hand-editable text file that pins the
  order, titles and tags. Generate one from the GUI, edit in Notepad, reload or
  run from the CLI.
- 👀 **Background watcher**: lives in the system tray, watches folders you
  configure, and **builds any new sub-folder of MP3s automatically** with
  Windows toast + screen-reader notifications.
- 💻 **Rich CLI** with `--help`, a chapter plan table and a live progress bar.
- ♿ **Fully keyboard accessible**, with screen-reader announcements borrowed
  from the QUILL project (graceful fallback when no reader is present), plus
  adjustable **text size**, an optional **high-contrast theme**, and
  **Save Diagnostics** for support.
- 🔄 **Check for updates** built in (GitHub Releases) — download and launch the
  right installer for your platform in one click, and a one-click installer.

## Requirements

- Windows 10/11 (the tray watcher, toasts and installer are Windows-specific;
  the core and CLI are cross-platform).
- Python 3.10+
- [FFmpeg](https://ffmpeg.org/) (`ffmpeg` and `ffprobe`) on your `PATH` — or use
  the packaged build, which bundles them.
- Python packages: `wxPython`, `mutagen` (plus optional `prismatoid` on Windows
  for richer screen-reader output).

```bash
pip install -r requirements.txt
```

## Run from source

```bash
# Option 1: from repository root
python main.py            # graphical app
python main.py --help     # command-line help
python main.py --watch    # background tray watcher

# Option 2: as a Python module (from anywhere)
python -m chapterforge            # graphical app
python -m chapterforge --help     # command-line help
python -m chapterforge --watch    # background tray watcher
```

## Graphical app

1. **Open Folder…** (`Ctrl+O`) and pick a folder of MP3s.
2. Review the **Chapters** list. Use **Edit Title**, **Move Up/Down** or
   **Remove**. The *Selected chapter title* field edits the highlighted row.
3. Fill in the **Master MP3 tags** (Title/Album are pre-filled from the folder
   name) and optionally choose a **cover image**.
4. Pick **Options**: title source (filename / embedded), re-encode quality and
   loudness normalization.
5. **Set Output File…** (`Ctrl+S`), then **Build Master MP3** (`Ctrl+B`).

See **Help → User Guide** and **Help → Keyboard Shortcuts** in the app, or
[`docs/USER_GUIDE.md`](docs/USER_GUIDE.md). The **Help** menu also opens
Release Notes and the full documentation set as HTML in your browser
(generate it with `python tools/build_docs.py`).

## Command line

```bash
chapterforge "C:\Audiobooks\My Book"
chapterforge -i .\chapters -o book.mp3 --title "My Book" --artist "Jane Doe" --normalize
chapterforge .\chapters --list                  # show the chapter plan only
chapterforge --job .\chapters\chapters.cfjob    # build from a job file
chapterforge --check-updates
```

Run `chapterforge --help` for the full option list. When the packaged windowed
app is launched with arguments it attaches to the parent console so output is
visible; a dedicated `chapterforge-cli.exe` is also shipped.

## Job files (`.cfjob`)

A job file is a forgiving UTF-8 text file:

```
# Lines starting with '#' are comments.
@title   = My Audiobook
@artist  = Jane Author
@album   = My Audiobook
@genre   = Audiobook
@year    = 2024
@cover   = cover.jpg
@output  = My Audiobook - Master.mp3
@bitrate = 192k
@normalize = false

01 - Opening.mp3        | Opening
02 - The First Part.mp3 | The First Part
```

The line order is the chapter order; the title after `|` is optional. Filenames
are resolved relative to the job file and must stay inside its folder. Generate
one from **File → Generate Job File…**, or drop a `chapters.cfjob` into a watched
folder to control the automatic build.

## Background watcher

- **Tools → Watch Folders…** manages reusable *processes*: each pairs a watched
  folder with naming templates (`{folder}`, `{parent}`, `{date}`) and tag
  defaults.
- **Tools → Start Background Watcher** minimises to the system tray and builds
  any new, *stable* sub-folder of MP3s automatically. Generated masters go into
  an excluded `_ChapterForge` sub-folder; each folder is built once.
- **Tools → Start Watcher at Sign-in** registers a per-user startup entry.
- `chapterforge --watch` runs the watcher standalone from the tray.

Safety: a folder is only built once its file set has been unchanged for a settle
window; locks and done/failed markers prevent double-processing and re-trigger
loops. You're notified (toast + screen reader) when a build starts, finishes or
fails.

## Packaging & deployment

The app ships as a **PyInstaller one-folder build** (no per-launch temp
extraction) wrapped by an **Inno Setup** installer. See
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the full build, release and update
strategy.

```bash
pip install pyinstaller
pyinstaller ChapterForge.spec
iscc installer\ChapterForge.iss
```

## Accessibility

- Every control has a visible label with a mnemonic and an explicit accessible
  name, so NVDA and Narrator announce them clearly.
- Status, progress and completion are announced; the screen-reader bridge and
  announcement grammar are adapted from the QUILL project (see
  [`THIRD_PARTY.md`](THIRD_PARTY.md)) and degrade gracefully when no reader or
  `prismatoid` backend is present.
- Long work runs on a background thread; the UI never blocks and a
  failed/cancelled build never leaves a half-written file behind.

## Project layout

```
chapterforge/
  core.py            # UI-free: scan, probe, concat, tag + chapter writing
  app.py             # accessible wxPython UI
  cli.py             # command-line interface
  settings.py        # persistent JSON settings
  manifest.py        # .cfjob read/write/resolve
  watcher.py         # background polling build engine
  watcher_config.py  # reusable watch-folder "processes"
  watch_dialogs.py   # accessible process-management dialogs
  tray.py            # system-tray watcher app
  notify.py          # toasts + screen-reader announcements + log
  a11y.py            # screen-reader bridge (adapted from QUILL)
  autostart.py       # per-user run-at-sign-in registration
  updates.py         # GitHub-Releases update check (adapted from QUILL)
main.py / cli_main.py  # entry points
ChapterForge.spec      # PyInstaller one-folder spec (GUI + CLI exes)
installer/ChapterForge.iss   # Inno Setup installer
samples/               # example cover art + test instructions
docs/                  # user guide + deployment guide
tests/
```

## Testing

```bash
python -m pytest -q
```

The tests synthesise small MP3s with FFmpeg and verify scanning, sorting,
chapter computation, both build paths, Unicode titles, cover embedding, chapter
read-back, the `.cfjob` parser, watch-folder templates and the watch engine.

## How chapters are written

For each source file ChapterForge writes a `CHAP` frame whose `start_time` /
`end_time` are the cumulative millisecond boundaries and whose `TIT2` sub-frame
holds the chapter title. A single ordered, top-level `CTOC` frame lists every
chapter. Boundaries are reconciled against the real encoded duration so the
final chapter never overshoots the file. Tags are saved as ID3v2.3 for broad
player compatibility.

## Credits

ChapterForge is developed by **Blind Information Technology Solutions
(BITS)**, a community building accessible software. Explore our services:

- [Join BITS](https://www.joinbits.org)
- [Let It Glow](http://www.letitglow.app)
- [Community Access](https://www.community-access.org)

FFmpeg, Mutagen and wxPython do the heavy lifting; the accessibility and update
patterns are adapted from the **QUILL** project. See
[`THIRD_PARTY.md`](THIRD_PARTY.md) for licenses and attributions.

## License

ChapterForge's own source code is released under the **MIT License** — see
[`LICENSE`](LICENSE). © 2026 Blind Information Technology Solutions (BITS).

Note that the packaged build bundles third-party programs (FFmpeg) and depends
on libraries (Mutagen is GPL-licensed) that carry their own license terms. If
you redistribute a packaged build, review [`THIRD_PARTY.md`](THIRD_PARTY.md) and
comply with those licenses; the MIT license covers only ChapterForge's own code.

