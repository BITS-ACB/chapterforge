# Third-party software and attributions

ChapterForge incorporates or relies on the following third-party components. The Python libraries below are bundled inside the application, as is `libmpv-2.dll` (see below); FFmpeg is downloaded at runtime rather than shipped with ChapterForge.

## FFmpeg (`ffmpeg.exe`, `ffprobe.exe`)

**License:** GNU LGPL 2.1+ or GPL 2.0+ (depending on build configuration)

ChapterForge uses the FFmpeg command-line tools to decode, concatenate, and re-encode audio files. FFmpeg is maintained by the FFmpeg project and is available at https://ffmpeg.org.

ChapterForge does not bundle or redistribute FFmpeg. If FFmpeg is not already on your system, ChapterForge offers to download an official Windows build on first run (and via Help > Download FFmpeg). Those binaries are obtained directly from the third-party builder and remain under their own license.

If you choose to redistribute ChapterForge together with FFmpeg binaries, you become a redistributor of FFmpeg and must comply with FFmpeg's license terms (GPL or LGPL, depending on the build), which generally require:

- Providing the FFmpeg source code (or a written offer of the source)
- Keeping the FFmpeg license notice intact
- Preserving all copyright and license notices in the binaries

For detailed information about FFmpeg licensing, visit https://ffmpeg.org/legal.html.

## libmpv (`bin/mpv/libmpv-2.dll`)

**License:** GNU LGPL 2.1+ or GPL 2.0+ (depending on build configuration)

ChapterForge's in-app player uses libmpv, the playback engine of the mpv media player, via the `python-mpv` Python binding, to decode and play audio with sample-accurate seeking. libmpv is maintained by the mpv project (https://mpv.io) and is built for Windows by the mpv-player-windows project (https://github.com/shinchiro/mpv-winbuild-cmake, distributed via https://sourceforge.net/projects/mpv-player-windows/).

Unlike FFmpeg, ChapterForge does bundle and redistribute `libmpv-2.dll` (under `bin/mpv/`). As a redistributor, ChapterForge complies with libmpv's license terms (GPL or LGPL, depending on the build) by:

- Providing this notice and a written offer of the corresponding source code: the exact build redistributed with ChapterForge is `mpv-dev-x86_64` from the mpv-player-windows project's release channel; its source is the public mpv project source (https://github.com/mpv-player/mpv) plus the mpv-winbuild-cmake build scripts linked above. Contact the address in this project's README to request a copy.
- Keeping libmpv's and mpv's license notices intact and available at https://github.com/mpv-player/mpv/blob/master/Copyright and https://www.gnu.org/licenses/.
- Preserving all copyright and license notices in the binary.

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

**Attribution:** BITS (Blind Information Technology Solutions)

The screen-reader announcement and accessibility layer in ChapterForge (`chapterforge/a11y.py` and `chapterforge/notify.py`) is adapted from the QUILL project's accessibility design. This includes:

- The Prism/Prismatoid screen-reader bridge with graceful fallback
- The `announce()` transcript API for screen-reader feedback
- The announcement formatting grammar (`format_announcement()`, `format_progress()`, `pluralize()`)
- The in-app JSON notification log pattern for accessibility and debugging

QUILL is an accessible document editor developed by BITS. ChapterForge reuses these proven patterns to ensure full screen-reader compatibility and keyboard-first operation.

## Build & packaging tools

The following tools are used to build and package ChapterForge but are not bundled with the application:

- **PyInstaller** (GitHub Installers) - creates the self-contained Windows executable
- **Inno Setup** - builds the Windows installer
- **Python 3.10+** - runtime and build environment

---

**© 2026 Blind Information Technology Solutions (BITS)**

ChapterForge is an accessible audiobook builder for Windows. For more information, visit https://github.com/bits-acb/chapterforge.
