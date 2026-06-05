# ChapterForge Roadmap

Ranked by user impact, highest to lowest. All items are viable with the
existing FFmpeg-based architecture and wxPython UI. Online services are
explicitly excluded — ChapterForge is and will remain a fully local,
privacy-respecting tool.

Items marked **Accessibility Priority** are features where existing tools
(mp3DirectCut, Mp3tag) have poor or no screen-reader support, giving
ChapterForge an opportunity to be the only fully accessible option.

---

## Tier 1 — Core Workflow Gaps (ship these next)

### 1. Lossless MP3 Trim and Cut Without Re-encoding
**Accessibility Priority**

mp3DirectCut is the only widely-used tool for this, and it has serious
keyboard and screen-reader limitations. ChapterForge with FFmpeg can do
frame-accurate lossless cutting via `-c copy` and `-ss`/`-to` flags.

What this enables:
- Trim silence or unwanted audio from the head and tail of a source file
  before building
- Remove a section from the middle of a chapter without re-encoding
- Clean up recordings directly inside ChapterForge — no external tool needed
- "Pre-listen as cut" so the user hears what the result will sound like
  before saving

Implementation path: FFmpeg `-c copy -ss START -to END` for lossless segment
extraction. UI: a Trim panel in the player with accessible Begin/End markers,
fine-adjust with arrow keys, and a preview-then-save workflow.

---

### 2. FLAC, WAV, OGG, M4A, and AAC Source File Support

ChapterForge currently requires MP3 source files. Many users record in FLAC
or WAV, or have files in M4A from purchases. FFmpeg already handles all of
these formats.

What this enables:
- Accept any format FFmpeg supports as a source chapter file
- Transcode automatically during build (already happens for re-encode; just
  remove the MP3-only filter at scan time)
- Open FLAC audiobooks for editing in edit mode

Implementation path: Remove the `.mp3`-only filter in `core.scan_folder()`.
Update `probe_file()` to accept all FFmpeg-supported containers. Test M4A/FLAC
round-trip in build and edit modes.

---

### 3. Split One Long Recording into Chapters

**Accessibility Priority**

The inverse of the current workflow: instead of combining many files into one,
let the user open one long recording and divide it into chapters inside
ChapterForge. This is the primary use case for mp3DirectCut and a common need
for lecture recordings, meeting captures, and raw podcast recordings.

What this enables:
- Open one long MP3 or FLAC
- Use silence detection, the player, or manual time entry to place chapter
  boundaries
- Name each chapter
- Save to multiple files or build the chaptered master directly
- Lossless split via FFmpeg `-c copy`

Implementation path: New "Split Recording" task mode (alongside Build and Edit
in the task selector). Uses the existing chapter editor UI with a different
source model. Silence detection already exists in `core.py`.

---

### 4. Batch Chapter Metadata Editing

Currently, renaming a chapter title requires selecting it and typing in the
title field — one at a time. For audiobooks with 60+ chapters, bulk operations
are essential.

What this enables:
- Select multiple chapters and apply the same title transformation to all
  (capitalize, strip leading numbers, find-and-replace)
- Apply a title pattern like "Chapter {n}" to a range of selected chapters
- Auto-number chapters with configurable format
- Find and replace text across all chapter titles at once

Implementation path: Multi-select in the chapter list, a Batch Edit dialog
with pattern options, and `core.apply_title_source()` extended with
transformation rules.

---

## Tier 2 — High Impact

### 5. Lossless Fade In and Fade Out for MP3 Chapters

mp3DirectCut can apply simple fades to MP3 data without re-encoding by
manipulating frame-level gain values. This is useful for smoothing abrupt
chapter starts and ends.

What this enables:
- Add a short fade-in to a chapter's beginning
- Add a fade-out to a chapter's end
- Create professional-sounding transitions without re-encoding

Implementation path: FFmpeg `afade` filter with `-c:a copy` where possible, or
very short re-encode only at the fade boundary. Expose as a per-chapter option
in the chapter editor.

---

### 6. Cover Art Management — Resize, Convert, Crop

Mp3tag has extensive cover art tools. ChapterForge's cover art support is
currently limited to selecting a file. Many users have cover images that are
too large (multi-MB), wrong aspect ratio, or in PNG when JPEG is preferred.

What this enables:
- Resize cover art to a target pixel dimension before embedding
- Convert PNG to JPEG (smaller file size for embedded art)
- Crop to square if the cover is not already square
- Preview before embedding

Implementation path: Python `Pillow` library (already widely available) or
FFmpeg's image scaling filters. UI: options in the cover art section of the
Tags page.

---

### 7. Reusable Build Presets

Users who build audiobooks regularly with the same settings (format, quality,
normalize, gap) should not have to re-enter them. Named presets extend the
existing `.cfjob` job file concept to settings profiles.

What this enables:
- Save the current build settings as a named preset
- Load a preset to restore format, bitrate, normalize, gap, and JSON settings
- Ship with sensible built-in presets: "Podcast MP3", "Audiobook M4B", "High
  Quality Archive"

Implementation path: Extend `settings.py` with a `presets` dict. UI in the
Settings dialog with a preset picker and Save/Delete buttons.

---

### 8. Export Metadata as CSV or Plain Text

Mp3tag's export feature produces auditable metadata reports. ChapterForge
already saves a text chapter report alongside the master, but a structured
export of all chapter metadata (title, duration, start time, link URL, image)
would be useful for review, archiving, and accessibility descriptions.

What this enables:
- Audit all chapter titles and times before distributing
- Export to CSV for integration with spreadsheets or accessible databases
- Generate a plain-text transcript-friendly report with chapter timing

Implementation path: Extend the existing "Save Chapter List" export formats.
Add CSV and formatted HTML export options. Very low implementation cost.

---

### 9. FLAC Output with Embedded Chapters

ChapterForge outputs MP3 or M4B. Adding FLAC output would serve users who
want a lossless archive copy of their audiobook with chapter markers.

What this enables:
- Build a lossless FLAC master with chapters using Vorbis Comment CHAPTER
  markers (standard for FLAC audiobooks)
- Keep the MP3/M4B option for distribution, FLAC for archiving

Implementation path: FFmpeg already supports FLAC output with chapters via
`-c:a flac` and Matroska/OGG chapter metadata. Mutagen supports Vorbis Comment
chapter writing.

---

### 10. Undo and Redo for Chapter List Operations

Currently, any chapter operation (rename, remove, reorder, merge) is permanent
until the session is discarded. A lightweight undo stack would dramatically
reduce the cost of mistakes.

What this enables:
- Undo an accidental rename, remove, or merge
- Step back through a series of edits
- Redo an undone change
- Clear the undo stack when the build completes

Implementation path: Store a list of (operation, inverse_operation) tuples.
Operations are already discrete function calls in `app.py`. Announce each
undo/redo via `a11y.announce()`.

---

## Tier 3 — Medium Impact

### 11. File Renaming from Chapter Titles and Tags

Mp3tag's Tag -> Filename converter is one of its most-used features. For
ChapterForge users who need source files consistently named, a rename tool
that reads from the chapter title, artist, year, and chapter number would
save significant manual work.

What this enables:
- Rename source files to match their chapter titles
- Apply a naming pattern like `{n:02d} - {title}.mp3` to all source files
- Preview renames before applying

Implementation path: A rename dialog accessible from the Edit menu with a
pattern field, a preview list, and an Apply button. Uses `os.rename()` on the
source paths.

---

### 12. Chapter-Level Per-File Loudness Normalization

The current normalize option applies global normalization across the whole
build. Per-chapter normalization targets each source file individually to a
consistent level before concatenation, giving more even results when source
files have very different recording levels.

What this enables:
- Target each source file to the same loudness (e.g. -16 LUFS) before joining
- More consistent listening experience across chapters
- Configurable target level

Implementation path: FFmpeg `loudnorm` filter applied per-file in the probe
and build pipeline. Add a "Per-file loudness target" option to Settings.

---

### 13. MP3 Recording Directly into ChapterForge

**Accessibility Priority**

mp3DirectCut includes a built-in recorder. For users who create content
directly (spoken-word recordings, interviews), recording directly into a source
chapter without leaving the app removes a major workflow gap.

What this enables:
- Record a new chapter directly into the chapter list
- Each recording session creates a new source MP3
- Level meter and status during recording
- Immediate preview after recording

Implementation path: `sounddevice` or `PyAudio` for capture; FFmpeg or LAME
for encoding. Requires careful accessible UI for device selection, level
monitoring, and recording state.

---

### 14. Advanced Chapter List Filtering and Search

Mp3tag's filter expressions are one of its most powerful features. A simpler
version for ChapterForge would let users find chapters by title text, flag
chapters with missing data, or isolate a range for batch operations.

What this enables:
- Search chapter titles as you type
- Filter to chapters with empty titles
- Filter to chapters with no link URL or image (for Podcasting 2.0 workflows)
- Select filtered chapters for batch operations

Implementation path: A search/filter bar above the chapter list. Filter is
applied client-side against the in-memory chapter list. No new dependencies.

---

### 15. CUE Sheet Round-Trip Improvements

ChapterForge already exports CUE sheets. Importing a CUE sheet to define
chapter points (for a single long source file) and round-tripping edits back
to CUE would complete the workflow for users who already use CUE-based tools.

What this enables:
- Import a CUE sheet to define chapters in a single long source file
- Edit chapter points and re-export the CUE
- Use ChapterForge as a CUE-to-chaptered-MP3 converter

Implementation path: Extend the existing `manifest.py` CUE parser. Map CUE
INDEX points to chapter start times. Combine with the "Split One Long
Recording" feature for a complete workflow.

---

### 16. Configurable Chapter List Columns

Power users may want to show fewer or more columns, or reorder them. The
current fixed five-column layout (number, title, start, duration, source file)
does not allow customization.

What this enables:
- Show or hide columns (e.g. hide Source file for a cleaner view)
- Reorder columns
- Persist column configuration in settings

Implementation path: Column configuration stored in `settings.py`. A
right-click context menu on column headers (with keyboard alternative in the
View menu) to toggle columns.

---

## Tier 4 — Lower Priority but Viable

### 17. Simple Batch Tag Cleanup Actions

Mp3tag's action groups are a power-user superpower. A simpler, curated set of
common cleanup actions for ChapterForge's chapter titles would cover 80% of
the use cases without the complexity of a scripting engine.

Actions to include:
- Capitalize all chapter titles (title case)
- Strip leading track numbers from titles
- Replace underscores with spaces
- Trim leading and trailing whitespace
- Remove duplicate consecutive spaces
- Find and replace text across all titles

Implementation path: An "Edit - Clean Up Titles" menu item that opens a
dialog with checkboxes for each cleanup action and a preview before applying.

---

### 18. Accessible Audio Level Meter During Build

Currently the build shows a progress gauge but no audio level feedback. A
real-time or per-file peak level display during the build would help users
verify their normalization is working as intended.

What this enables:
- See (or hear announced) the peak level of each chapter as it is processed
- Detect chapters that are clipping or very quiet before the build finishes
- Build confidence that normalization is working

Implementation path: Parse FFmpeg's `loudnorm` or `astats` filter output
during build. Announce per-chapter levels via `a11y.announce()`.

---

### 19. Keyboard-Configurable Shortcuts

ChapterForge has a fixed set of keyboard shortcuts. Power users who want to
customize the command palette bindings or add their own shortcuts should be
able to do so.

What this enables:
- Reassign any command palette action to a different key
- Add keyboard shortcuts to commands that currently have none
- Persist customizations in settings

Implementation path: Extend the command palette registry with a
configurable key map stored in `settings.py`. A "Keyboard Shortcuts" section
in Settings with a list of commands and editable key fields.

---

## Out of Scope

The following features were considered and excluded:

- **Online metadata lookup** (Discogs, MusicBrainz, freedb) - ChapterForge
  is a local, privacy-respecting tool with no network calls except update
  checking.
- **Multi-track mixing or DAW features** - Outside the single-stream
  audiobook/podcast workflow.
- **Noise reduction, click repair, spectral editing** - Requires a full DSP
  library (iZotope/SoX-level); out of scope for this tool's mission.
- **EQ, compression, reverb** - Same reason.
- **Pitch correction** - Out of scope; speed-with-pitch-preservation (already
  shipped in 1.90) covers the real use case.
- **MP4/MKV video chapter editing** - ChapterForge is audio-only.
- **Library/music-collection management** - ChapterForge builds individual
  audiobooks, not a whole music library.
- **Web scraping or browser automation** - Not appropriate for a local desktop
  tool.
