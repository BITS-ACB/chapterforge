# ChapterForge Roadmap

This document captures planned and proposed enhancements to ChapterForge. Items
are grouped by rough horizon, not by strict release commitment. The near-term
section reflects work that is scoped and ready to plan; further-out items are
directional.

Feedback and priorities are tracked on
[GitHub Issues](https://github.com/BITS-ACB/chapterforge/issues).

---

## Near-term

These items have clear scope, are well-understood technically, and address the
most pressing gaps in the current 1.0.0 release.

### Undo / redo

Chapter editing is currently destructive. Accidentally merging, removing, or
reordering a chapter has no recovery path short of reloading the source folder
and starting over. For a screen reader user who may not receive immediate visual
confirmation that an action occurred, this is a meaningful risk.

A multi-level undo/redo stack covering all chapter list operations (add, remove,
rename, reorder, merge, split) would make the editor safe to explore and correct.

### ACX compliance check

Audible's ACX platform rejects files that do not meet specific audio standards:
-23 LUFS integrated loudness, -3 dBFS peak, and a noise floor below -60 dBFS.
ChapterForge already performs loudness normalization but does not report whether
the result will pass the ACX checker. Many audiobook narrators find out their
file is non-compliant only after upload.

A pre-build (or post-build) compliance report with a pass/fail reading for each
requirement - and a recommended action when something fails - would save narrators
significant time and frustration.

### Per-track silence trimming

Most recordings include a second or two of room noise at the beginning and end of
each file. When these are concatenated, the pauses between chapters feel uneven
and unprofessional. An optional automatic trim of leading and trailing silence on
each source track before concatenation would clean up chapter transitions without
any manual work.

The threshold and minimum duration should be configurable, and the trim should use
FFmpeg's lossless copy path where possible.

### Metadata lookup

Typing title, author, album artist, genre, and year manually for every book is
repetitive and error-prone. A search against
[MusicBrainz](https://musicbrainz.org/) or the
[Open Library](https://openlibrary.org/) by title and author that pre-fills the
tag fields would eliminate most of the data entry for audiobook creators. The user
would confirm the match before any fields are written.

---

## Medium-term

These items are well-motivated but require more design or implementation work
before they are ready to build.

### Project templates

A podcaster who produces a weekly show uses the same output format, the same tag
defaults, the same folder naming pattern, and the same watcher configuration every
time. Currently they must set all of this up fresh for each build or maintain a
job file manually.

Named project templates - saved from any current configuration and selectable at
startup or from the File menu - would make recurring workflows hands-free. The
background watcher could select a template per watch folder, fully automating a
repeating production pipeline.

### Waveform display for silence detection

The auto-chapter by silence feature currently requires the user to set a threshold
and minimum gap and then trust that the detected breaks are correct. There is no
way to see where breaks were found before committing to them.

For sighted users, a waveform view showing the detected boundaries with the option
to drag them would make the feature far more trustworthy. For screen reader users,
the equivalent would be a navigable list of detected breaks with start time, gap
duration, and an accept/reject control for each - so every boundary can be
reviewed and corrected before the chapter list is populated.

### OPUS output format

OPUS is the modern open standard for compressed audio. It produces significantly
smaller files than MP3 at equivalent quality and is supported natively by
AntennaPod, VLC, foobar2000, and most contemporary podcast apps. FFmpeg already
handles OPUS encoding, so the addition is primarily a matter of exposing it in
the output format selector and ensuring chapter markers are written correctly in
the container.

### Per-chapter volume leveling

The current loudness normalization applies to the entire output file. When source
recordings come from different sessions or different microphones, individual
chapters can still vary noticeably in perceived volume even after whole-file
normalization.

An option to normalize each source track independently before concatenation - with
a target LUFS and a preview of the gain applied per track - would produce a more
consistent result for mixed-source projects.

### Narrator and series metadata

Audiobook apps that support the Audiobook shelf standard (Prologue, Libro.fm,
Bound) distinguish between author and narrator and understand series name and
series position. ChapterForge currently writes a single Artist field and no series
tags. Adding dedicated narrator, series, and series index fields - written as the
appropriate ID3 and MP4 tags - would make ChapterForge output work correctly in
these apps without manual post-processing.

### Build log viewer

Long builds and background watcher jobs produce detailed logs that are currently
discarded after the session ends. A lightweight log viewer (accessible from the
Help menu or the system tray) that shows recent build history - what ran, when,
how long it took, and whether it succeeded - would help users diagnose watcher
problems and confirm that an overnight batch run completed as expected.

---

## Long-term

These items are directional. They represent significant scope and some have open
design questions.

### macOS GUI port

The ChapterForge core - all file scanning, FFmpeg handling, chapter tagging, and
format conversion - is already cross-platform Python. The wxPython GUI also runs
on macOS. The platform-specific pieces are the system tray, Windows toast
notifications, and the Inno Setup installer.

Porting to macOS would make ChapterForge available to a substantial population of
blind Mac users who currently have no equivalent tool. The tray and notification
code would need macOS equivalents; the installer would need a replacement (likely
a signed .pkg or .dmg); and VoiceOver integration would need to be tested and
tuned.

### Chapter image previews

Podcasting 2.0 supports per-chapter artwork. ChapterForge can already store an
image path per chapter, but the chapter list shows only a file path with no visual
or audio confirmation that the image is correct. A thumbnail preview in the Edit
Chapter dialog, and a way to navigate chapter images by keyboard with a text
description announced to the screen reader, would make this feature usable in
practice.

### Cloud folder watching

The background watcher currently monitors local folders only. A significant
portion of audio production happens with files synced via OneDrive, Dropbox, or
Google Drive. Extending the watcher to treat the local sync folder for any of
these services as a watch target - or, more ambitiously, watching a cloud folder
directly via its API - would let ChapterForge fit into cloud-based production
workflows.

### Podcast RSS feed generation

Podcasters who self-host their feed currently manage the RSS XML separately from
their audio files. ChapterForge already knows the title, author, description,
cover art, and per-episode metadata for every file it builds. Generating or
updating a Podcasting 2.0-compatible RSS feed alongside the built audio file would
let a self-hosted podcaster manage their entire pipeline from a single tool.

### Direct upload to distribution platforms

A finish-and-upload workflow - ACX check passes, build succeeds, file uploads to
ACX, Findaway Voices, or an S3-compatible bucket - would eliminate the manual
step of opening a browser and uploading. This depends on stable APIs from those
platforms and would need secure credential storage. It is a meaningful quality-of-
life improvement for high-volume producers.

---

## Accessibility-specific improvements

These items apply across all release horizons and are tracked separately because
they are subject to the project's binding accessibility-first commitment.

- **System high-contrast theme tracking** - ChapterForge's built-in high-contrast
  theme should activate automatically when Windows high-contrast mode is on, not
  require a manual setting change.
- **Screen reader announcement verbosity control** - a setting to reduce or
  increase how much detail is announced during long builds, for users who find the
  current level either too verbose or not verbose enough.
- **Braille display optimization** - review all control labels and live regions for
  conciseness, since braille displays show far fewer characters per line than
  speech output reads per second.
- **Focus return after dialogs** - audit every dialog and modal to confirm focus
  returns to a meaningful, announced location when dismissed.
