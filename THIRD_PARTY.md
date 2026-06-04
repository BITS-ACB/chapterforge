# Third-party software and attributions

ChapterForge bundles and/or adapts the following third-party components.

## FFmpeg (ffmpeg.exe, ffprobe.exe)
ChapterForge ships the FFmpeg command-line tools (`ffmpeg.exe`, `ffprobe.exe`)
to decode, concatenate and re-encode audio. FFmpeg is licensed under the
GNU LGPL/GPL depending on the build. See https://ffmpeg.org and the license of
the specific build you ship. If you redistribute ChapterForge you must comply
with the FFmpeg license terms (typically: provide the FFmpeg source or a written
offer, and keep the license/notices intact).

## Mutagen
ID3v2 tags and CHAP/CTOC chapter frames are written with Mutagen, licensed under
the GNU GPL v2 or later. https://mutagen.readthedocs.io

## wxPython
The graphical interface uses wxPython (wxWidgets), licensed under the wxWindows
Library Licence. https://www.wxpython.org

## QUILL (accessibility patterns)
The screen-reader bridge and announcement helpers in
`chapterforge/a11y.py` and the notification-log pattern in
`chapterforge/notify.py` are adapted from the QUILL project's accessibility
layer:

* the Prism / Prismatoid screen-reader bridge with graceful "status-only"
  fallback,
* the `announce()` transcript API,
* the announcement grammar (`format_announcement` / `format_progress` /
  `pluralize`),
* the in-app JSON notifications log.

The optional `prismatoid` package provides the actual screen-reader backend on
Windows; when it is not installed, ChapterForge degrades gracefully and relies
on visible status text and standard accessible controls.
