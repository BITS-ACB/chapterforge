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

## Tier 2 — High Impact

### 3. Lossless Fade In and Fade Out for MP3 Chapters

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

### 4. Reusable Build Presets

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

### 5. Export Metadata as CSV or Plain Text

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

### 6. File Renaming from Chapter Titles and Tags

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

### 7. Accessible Audio Level Meter During Build

Currently the build shows a progress gauge but no audio level feedback. A
per-file peak level display during the build would help users verify
normalization is working as intended.

What this enables:
- Hear announced peak level of each chapter as it is processed
- Detect chapters that are clipping or very quiet before the build finishes
- Build confidence that normalization is working

Implementation path: Parse FFmpeg's `loudnorm` or `astats` filter output
during build. Announce per-chapter levels via `a11y.announce()`.
