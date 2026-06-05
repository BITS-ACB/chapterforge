# Third-party software and attributions

ChapterForge bundles and/or incorporates the following third-party components. Where applicable, license text and source code are provided alongside the distribution.

## FFmpeg (`ffmpeg.exe`, `ffprobe.exe`)

**License:** GNU LGPL 2.1+ or GPL 2.0+ (depending on build configuration)

ChapterForge ships the FFmpeg command-line tools to decode, concatenate, and re-encode audio files. FFmpeg is maintained by the FFmpeg project and is available at https://ffmpeg.org.

The FFmpeg binaries included with ChapterForge use the GPL 2.0 license and are built with GPL-licensed components. If you redistribute ChapterForge, you must comply with the GPLv2 license terms:

- Provide the FFmpeg source code (or a written offer of the source)
- Keep the FFmpeg license notice intact
- Preserve all copyright and license notices in the binaries

For detailed information about FFmpeg licensing and the specific configuration of your build, visit https://ffmpeg.org/legal.html.

## Mutagen

**License:** GNU GPL v2.0 or later

ID3v2 tags and chapter frames (CHAP/CTOC) are written using the Mutagen Python library, a pure-Python library for reading and writing audio metadata. Mutagen is maintained at https://mutagen.readthedocs.io.

ChapterForge uses Mutagen to:
- Parse and write ID3v2 tags in MP3 files
- Create and embed CHAP/CTOC chapter frame structures
- Maintain podcast app compatibility (Overcast, Pocket Casts, AntennaPod, etc.)

## wxPython (wxWidgets)

**License:** wxWindows Library Licence (compatible with LGPL)

The ChapterForge graphical interface is built with wxPython, a cross-platform Python binding for wxWidgets. wxPython is maintained at https://www.wxpython.org.

The wxWindows Library Licence permits both commercial and open-source use, with the requirement that you acknowledge wxWidgets and provide a copy of the license with your application.

## Prismatoid (optional, Windows)

**License:** Unlicensed / proprietary (optional graceful degradation)

The optional `prismatoid` package provides enhanced screen-reader output on Windows for NVDA compatibility. When installed, ChapterForge integrates with Windows Automation/MSAA to announce chapter progress and status. If `prismatoid` is not installed, ChapterForge gracefully falls back to visible status text and standard accessible controls.

## QUILL (accessibility patterns)

**Attribution:** BITS (Blind Information Technology Specialists)

The screen-reader announcement and accessibility layer in ChapterForge (`chapterforge/a11y.py` and `chapterforge/notify.py`) is adapted from the QUILL project's accessibility design. This includes:

- The Prism/Prismatoid screen-reader bridge with graceful fallback
- The `announce()` transcript API for screen-reader feedback
- The announcement formatting grammar (`format_announcement()`, `format_progress()`, `pluralize()`)
- The in-app JSON notification log pattern for accessibility and debugging

QUILL is an accessible document editor developed by BITS. ChapterForge reuses these proven patterns to ensure full screen-reader compatibility and keyboard-first operation.

## Build & packaging tools

The following tools are used to build and package ChapterForge but are not bundled with the application:

- **PyInstaller** (GitHub Installers) — creates the self-contained Windows executable
- **Inno Setup** — builds the Windows installer
- **Python 3.10+** — runtime and build environment

---

**© 2026 Blind Information Technology Specialists (BITS)**

ChapterForge is an accessible audiobook builder for Windows. For more information, visit https://github.com/bits-acb/chapterforge.
