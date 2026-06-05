# ChapterForge Roadmap

Ranked by user impact, highest to lowest. All items are viable with the
existing FFmpeg-based architecture and wxPython UI. ChapterForge is and will
remain fully local — no online services, no network calls beyond update
checking.

Items marked **Accessibility Priority** are features where existing tools
have poor or no screen-reader support, giving ChapterForge an opportunity to
be the only fully accessible option.

---

## Tier 1 — Core Workflow Gaps

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
- Pre-listen as cut so the user hears what the result will sound like before
  saving

Implementation path: FFmpeg `-c copy -ss START -to END` for lossless segment
extraction. UI: a Trim panel in the player with accessible Begin/End markers,
fine-adjust with arrow keys, and a preview-then-save workflow.

---

### 2. Split One Long Recording into Chapters

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

Implementation path: New "Split Recording" task mode alongside Build and Edit
in the task selector. Uses the existing chapter editor UI with a different
source model. Silence detection already exists in `core.py`.

---

### 3. Batch Chapter Metadata Editing

Currently, renaming a chapter title requires selecting it and typing in the
title field — one at a time. For audiobooks with 60+ chapters, bulk operations
are essential.

What this enables:
- Select multiple chapters and apply the same title transformation to all
  (capitalize, strip leading numbers, find-and-replace)
- Apply a title pattern like "Chapter {n}" to a range of selected chapters
- Auto-number chapters with a configurable format
- Find and replace text across all chapter titles at once

Implementation path: Multi-select in the chapter list, a Batch Edit dialog
with pattern options, and `core.apply_title_source()` extended with
transformation rules.

---

## Tier 2 — High Impact

### 4. Lossless Fade In and Fade Out for MP3 Chapters

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

### 5. Reusable Build Presets

Users who build audiobooks regularly with the same settings (format, quality,
normalize, gap) should not have to re-enter them. Named presets extend the
existing `.cfjob` job file concept to settings profiles.

What this enables:
- Save the current build settings as a named preset
- Load a preset to restore format, bitrate, normalize, gap, and JSON settings
- Ship with sensible built-in presets: "Podcast MP3", "Audiobook M4B",
  "Lossless FLAC Archive"

Implementation path: Extend `settings.py` with a `presets` dict. UI in the
Settings dialog with a preset picker and Save/Delete buttons.

---

### 6. Export Metadata as CSV or Plain Text

ChapterForge already saves a text chapter report alongside the master, but a
structured export of all chapter metadata (title, duration, start time, link
URL, image path) would be useful for review, archiving, and accessibility
descriptions.

What this enables:
- Audit all chapter titles and times before distributing
- Export to CSV for integration with spreadsheets or accessible databases
- Generate a plain-text transcript-friendly report with chapter timing

Implementation path: Extend the existing "Save Chapter List" export formats.
Add CSV and formatted HTML export options. Very low implementation cost.

---

## Tier 3 — Medium Impact

### 7. File Renaming from Chapter Titles and Tags

For users who need source files consistently named, a rename tool that reads
from the chapter title, artist, year, and chapter number saves significant
manual work.

What this enables:
- Rename source files to match their chapter titles
- Apply a naming pattern like `{n:02d} - {title}.mp3` to all source files
- Preview renames before applying

Implementation path: A rename dialog accessible from the Edit menu with a
pattern field, a preview list, and an Apply button. Uses `os.rename()` on the
source paths.

---

### 8. Chapter-Level Per-File Loudness Normalization

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

### 9. CUE Sheet Round-Trip Improvements

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

### 10. Configurable Chapter List Columns

Power users may want to show fewer or more columns, or reorder them. The
current fixed five-column layout does not allow customization.

What this enables:
- Show or hide columns (e.g. hide Source file for a cleaner view)
- Reorder columns
- Persist column configuration in settings

Implementation path: Column configuration stored in `settings.py`. A
right-click context menu on column headers (with keyboard alternative in the
View menu) to toggle columns.

---

## Tier 4 — Lower Priority but Viable

### 11. Simple Batch Title Cleanup Actions

A curated set of common cleanup actions for chapter titles covers 80% of
Mp3tag-style use cases without the complexity of a scripting engine.

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

### 12. Accessible Audio Level Meter During Build

Currently the build shows a progress gauge but no audio level feedback. A
per-file peak level display during the build would help users verify
normalization is working as intended.

What this enables:
- Hear announced peak level of each chapter as it is processed
- Detect chapters that are clipping or very quiet before the build finishes
- Build confidence that normalization is working

Implementation path: Parse FFmpeg's `loudnorm` or `astats` filter output
during build. Announce per-chapter levels via `a11y.announce()`.

---

### 13. Keyboard-Configurable Shortcuts

Power users who want to customize the command palette bindings or add their
own shortcuts should be able to do so.

What this enables:
- Reassign any command palette action to a different key
- Add keyboard shortcuts to commands that currently have none
- Persist customizations in settings

Implementation path: Extend the command palette registry with a configurable
key map stored in `settings.py`. A "Keyboard Shortcuts" section in Settings
with a list of commands and editable key fields.
