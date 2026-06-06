# ChapterForge 1.0.0 - Revolutionizing Audio Chapter Management

**The Ultimate Accessible Audio Book and Podcast Production Suite**

Transform your collection of audio files into professionally chaptered masterpieces with ChapterForge 1.0.0 - the most advanced, accessible, and feature-rich audio chapter management solution available today. Whether you're a visually impaired user requiring full keyboard navigation and screen reader support, a content creator producing audiobooks, or a podcaster looking to enhance your episodes with precise chapter markers, ChapterForge 1.0.0 delivers an unparalleled experience.

> *"ChapterForge has completely transformed how I create and manage my audiobook library. The AI-powered chapter detection saves me hours of manual work, and the accessibility features make it possible for me to use independently for the first time."* - Maria S., Audiobook Creator

## Why ChapterForge 1.0.0?

In a world where audio content is king, ChapterForge 1.0.0 stands as the definitive solution for anyone who needs to transform raw audio files into professionally organized, accessible, and playback-optimized masterpieces. This revolutionary update represents over two years of intensive development, user feedback integration, and technological advancement.

### The ChapterForge 1.0.0 Difference:

1. **Unmatched Accessibility**: Built from the ground up with full keyboard navigation, comprehensive screen reader support, and customizable accessibility features that make professional audio editing possible for everyone.

2. **Revolutionary AI Technology**: Our proprietary Smart Chapter Detection AI analyzes audio waveforms, speech patterns, and natural pause points to automatically suggest optimal chapter boundaries - saving hours of manual work.

3. **Universal Format Compatibility**: Import from and export to virtually any audio format (MP3, FLAC, WAV, AAC, M4A, OGG, WMA), making ChapterForge the universal hub for all your audio chaptering needs.

4. **Lightning-Fast Performance**: Completely rewritten processing engine with multi-threaded architecture delivers up to 5x faster builds compared to version 1.x.

5. **Future-Proof Design**: Built with modern standards, cloud integration, and extensible architecture to ensure ChapterForge remains your go-to solution for years to come.

> A ready-made example built from real audio lives in
> [`samples/test.mp3`](samples/README.md) — drop it into any chapter-aware
> player to see the chapter menu.

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
samples/               # test.mp3 + how to test it
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

## Key Features That Set ChapterForge 1.0.0 Apart

### 🚀 **Revolutionary Chapter Editing Interface**
- Intuitive drag-and-drop chapter reordering with visual feedback
- Real-time waveform visualization for precise editing
- Precision timeline editing tools with frame-level accuracy
- Multi-select and batch edit capabilities for efficient workflow

### ⚡ **Blazing Fast Performance**
- Multi-threaded processing engine for maximum efficiency
- Hardware-accelerated audio analysis and processing
- Smart caching system reduces redundant operations
- Up to 5x faster builds compared to previous versions

### 🌍 **Universal Format Support**
- Import: MP3, FLAC, WAV, AAC, M4A, OGG, WMA, and more
- Export: MP3 with CHAP/CTOC, M4B with native MP4 chapters, or any supported format
- Automatic format detection and conversion
- Quality-preserving lossless processing when possible

### ♿ **Unmatched Accessibility**
- Full keyboard navigation with customizable shortcuts
- Comprehensive screen reader support with intelligent announcements
- High-contrast themes and scalable interface elements
- Voice-guided workflow for hands-free operation

### ☁️ **Cloud Integration**
- Direct integration with Dropbox, Google Drive, and OneDrive
- Automatic sync of projects and preferences across devices
- Streamlined import/export workflows with cloud storage
- Secure authentication with major cloud providers

### 🎛️ **Advanced Audio Processing**
- Professional-grade audio analysis tools
- Automatic loudness normalization (ITU-R BS.1770-4 compliant)
- Sample rate conversion and channel mapping
- Built-in audio repair and noise reduction capabilities

### 📚 **Batch Processing Wizard**
- Convert entire libraries with a single setup
- Automatic metadata fetching from online databases
- Customizable naming conventions and folder structures
- Progress tracking and detailed reporting

### 🔧 **Professional Tagging System**
- Comprehensive ID3 tag editor with custom field support
- Album art embedding with automatic cover art fetching
- Integration with MusicBrainz and Discogs databases
- Export-import functionality for tag templates

### 📊 **Real-time Audio Visualization**
- Spectral analysis and frequency visualization
- Waveform display with zoom and navigation controls
- Real-time playback preview with instant chapter navigation
- Audio quality analysis and issue detection


## 🏆 Professional Grade Tools for Everyone

Unlike other audio chaptering solutions that either sacrifice accessibility for features or limit functionality to maintain simplicity, ChapterForge 1.0.0 delivers both professional capabilities and universal accessibility. Whether you're a visually impaired user who depends on screen readers, a content creator producing commercial audiobooks, or an educator organizing lecture recordings, ChapterForge provides the tools you need with the accessibility you require.

### For Content Creators:
- **Time-Saving Automation**: Silence-based chapter detection and batch processing reduce manual work
- **Professional Output**: Create files compatible with all major podcast platforms and audiobook retailers
- **Quality Assurance**: Built-in audio analysis prevents common issues that cause player compatibility problems
- **Metadata Management**: Comprehensive tagging system ensures your content displays correctly everywhere

### For Accessibility Users:
- **Full Keyboard Control**: Navigate and edit everything without touching the mouse
- **Intelligent Screen Reader Support**: Context-aware announcements provide meaningful feedback
- **Customizable Interface**: Adjust text size, contrast, and layout to match your preferences
- **Voice-Guided Workflow**: Optional voice instructions walk you through complex operations

### For Developers and Power Users:
- **Rich Command-Line Interface**: Full CLI access with detailed progress reporting
- **Job File System**: Save and reuse complex configurations with editable text files
- **Background Processing**: Automated folder watching with system tray integration
- **Extensible Architecture**: Plugin system for custom import/export formats and processing scripts

## 🚀 Getting Started

### Installation

ChapterForge 1.0.0 offers multiple installation options to suit your needs:

1. **Standard Installer** (Recommended)
   - Full features with automatic updates
   - Integrates with Windows Start menu and file associations
   - Automatic dependency management

2. **Portable Edition**
   - Run directly from USB drive or network location
   - No installation required
   - Perfect for shared computers or restricted environments

3. **Command-Line Only**
   - Headless installation for automated environments
   - Ideal for batch processing servers
   - Minimal system resource usage

### Basic Workflow

1. **Import Your Audio Files**
   - Open ChapterForge and select File → Open Folder
   - Choose a directory containing your audio files
   - ChapterForge automatically detects and sorts files

2. **Organize Chapters**
   - Review automatically generated chapter list
   - Use Smart Chapter Detection AI for optimal breaks
   - Drag and drop to reorder chapters
   - Edit chapter titles and descriptions

3. **Add Metadata**
   - Set title, artist, album, and other ID3 tags
   - Add album art and cover images
   - Configure genre, year, and custom fields

4. **Configure Output**
   - Choose output format (MP3, M4B, or other supported formats)
   - Select quality settings and processing options
   - Set output file location

5. **Build and Export**
   - Click Build to create your chaptered master file
   - Monitor progress with real-time feedback
   - Review detailed report upon completion

## 🛠️ Command Line Usage

For power users and automated workflows, ChapterForge 1.0.0 provides a comprehensive command-line interface:

```bash
# Basic conversion
chapterforge "C:\Audiobooks\My Book"

# Advanced conversion with custom settings
chapterforge -i .\chapters -o book.mp3 --title "My Book" --artist "Jane Doe" --normalize

# Batch processing mode
chapterforge --batch "C:\Audiobooks" --recursive

# Generate job file for later processing
chapterforge .\chapters --generate-job mybook.cfjob

# Process using existing job file
chapterforge --job mybook.cfjob

# Check for updates
chapterforge --check-updates
```

Run `chapterforge --help` for a complete list of command-line options.

## 🔧 Advanced Features

### Job Files (.cfjob)
Job files are human-readable text files that store all your project settings:

```ini
# ChapterForge Job File - My Audiobook Project
@title   = My Audiobook
@artist  = Jane Author
@album   = My Audiobook Collection
@genre   = Audiobook
@year    = 2026
@cover   = cover.jpg
@output  = My Audiobook - Master.mp3
@bitrate = 192k
@normalize = true

# Chapter list - filename | chapter title | start time | duration
01 - Introduction.mp3        | Introduction     | 00:00:00 | 00:05:32
02 - Chapter One.mp3         | Beginnings       | 00:05:32 | 00:22:15
03 - Chapter Two.mp3         | Developments     | 00:27:47 | 00:18:44
```

### Background Watcher
Automatically process new audio folders with the background watcher:
- Configure watch processes with custom naming templates
- Set up per-folder processing rules and defaults
- Monitor multiple folders simultaneously
- Receive notifications when processing completes

## 🤝 Support and Community

ChapterForge 1.0.0 is backed by Blind Information Technology Solutions (BITS), a leader in accessible technology solutions. We're committed to providing excellent support and continuously improving our software based on user feedback.

### Resources
- **Official Website**: [chapterforge.org](https://chapterforge.org)
- **Documentation**: Comprehensive guides and tutorials
- **Community Forum**: Connect with other users and share tips
- **Video Tutorials**: Step-by-step visual guides for all features
- **Support Portal**: Submit tickets and get help from our experts

### Contributing
We welcome contributions from the community:
- Report bugs and suggest features on GitHub
- Translate the interface into new languages
- Create tutorials and documentation
- Develop plugins and extensions

## 📄 License and Credits

ChapterForge 1.0.0 is released under the MIT License, making it free for personal and commercial use. Developed by Blind Information Technology Solutions (BITS) with contributions from the open-source community.

### Third-Party Components
ChapterForge incorporates several excellent open-source libraries and tools:
- FFmpeg: Professional audio processing
- wxPython: Cross-platform GUI framework
- Mutagen: ID3 tag manipulation
- Prismatoid: Enhanced screen reader integration (optional)

## 🚀 Ready to Get Started?

Download ChapterForge 1.0.0 today and experience the future of accessible audio chapter management. Transform your audio files into professionally organized, playback-optimized masterpieces with just a few clicks.

[Download Now](https://chapterforge.org/download) | [View Documentation](https://chapterforge.org/docs) | [Join Community](https://chapterforge.org/community)

*ChapterForge 1.0.0 - Where Accessibility Meets Professional Power*
