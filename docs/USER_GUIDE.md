# ChapterForge — User Guide

ChapterForge turns a folder of MP3 files into a single **master MP3** with
embedded chapter markers (ID3v2 `CHAP`/`CTOC`). Each source file becomes one
chapter, titled from its filename. It is designed to be fully usable with a
keyboard and a screen reader.

---

## 1. Quick start

1. Launch **ChapterForge** (Start menu shortcut, or `chapterforge` on the command line).
2. **File → Open Folder** (`Ctrl+Shift+O`) and choose a folder of MP3s.
   - Files are listed in natural order (`01`, `02`, `10`, `11`).
   - Leading track numbers are automatically stripped from chapter titles
     (`01 Chapter One.mp3` becomes *Chapter One*).
   - If a previously built master exists in the folder it is skipped automatically.
3. Review and adjust the **Chapters** list (Step 1 of the workflow).
4. Click **Set Tags & Build ->** to move to Step 2.
5. Fill in the **Tags** (title, artist, album, year, cover art, etc.).
6. Set the output file location and click **Build Master MP3** (or `Ctrl+B`).

The build runs on a background thread; progress is shown in the gauge and
announced to your screen reader. When it finishes a master MP3 and a
human-readable `… - chapters.txt` report are saved next to each other.

---

## 2. Keyboard shortcuts

| Key | Action |
| --- | --- |
| `Ctrl+Shift+O` | Open folder of MP3 files |
| `Ctrl+O` | Open an existing chaptered file to edit |
| `Ctrl+S` | Build (build mode) or Save Changes (edit mode) |
| `Ctrl+B` | Build master — explicit |
| `Ctrl+Shift+S` | Save changes to the open master — explicit |
| `Ctrl+Alt+S` | Save As (new file) |
| `Ctrl+L` | Load a Saved Setup (`.cfjob`) |
| `Ctrl+G` | Save This Setup as a Template |
| `Ctrl+W` | Set Up Automatic Building |
| `Ctrl+,` | Settings |
| `Ctrl+Shift+P` | Command Palette — search all commands |
| `Ctrl+/` | Keyboard shortcuts help |
| `Ctrl+=` | Larger text |
| `Ctrl+-` | Smaller text |
| `Ctrl+0` | Reset text size |
| `F1` | User Guide |
| `Alt+F4` | Exit |

**In the Chapters list:**

| Key | Action |
| --- | --- |
| `Up` / `Down` | Move selection (also selects the focused item) |
| `F2` | Edit the selected chapter title inline |
| `Delete` | Remove chapter (build) or merge up (edit mode) |
| `Alt+Up` / `Alt+Down` | Move chapter up or down |

All actions are also available as labeled buttons and via the menus.

---

## 3. The two-step workflow

ChapterForge uses a two-page layout to keep the screen uncluttered:

**Step 1 — Chapters:** browse for your source folder, review and edit the
chapter list, set options (format, quality, gap, normalize).  
Click **Set Tags & Build ->** when the chapter list looks right.

**Step 2 — Tags & Build:** set the master file's metadata (title, artist,
album, cover art) and the output path, then click **Build**.  
Click **<- Back to Chapters** to return and make more changes.

The status bar and audio player are always visible at the bottom of both pages.

---

## 4. Working with chapters

- **Rename** a chapter: select it, type a new name in the *Selected chapter
  title* field, then press `Enter` or click away. Or press `F2` to jump
  straight to the title field.
- **Set Link & Image**: the **Set Link & Image…** button opens a dialog to set
  the chapter's optional podcast link URL and per-chapter cover image.
- **Reorder**: `Alt+Up`/`Alt+Down` or the **Move Up**/**Move Down** buttons.
  Works in both build mode (reorders source files) and edit mode (swaps
  chapter labels — see §7 for full audio reordering).
- **Remove**: `Delete` or the **Remove** button removes a chapter in build mode,
  or merges it with the one above in edit mode.
- Chapter start and end times are computed automatically from each file's
  duration.

---

## 5. Tags and cover art

Set the master's ID3 tags on the Tags page (Step 2): title, artist,
album-artist, album, genre, year, comment and cover image. ChapterForge
auto-detects a cover image in the folder (e.g. `cover.jpg`) and shows a
preview; you can replace it or click **Remove Cover** to clear it.

---

## 6. Output format: MP3 or M4B

On the **Options** panel choose the **Output format**:

- **MP3** — a single master MP3 with ID3v2 `CHAP`/`CTOC` chapters. Uses
  lossless `-c copy` when sources are uniform; re-encodes only when needed.
- **M4B** — an AAC audiobook with native MP4 chapter metadata and an attached
  cover image. Ideal for Apple Books, BookPlayer, and similar apps.

Tick **Write chapters JSON** to also save a Podcasting 2.0 `…chapters.json`
sidecar containing each chapter's start time, title, and any link URL or image.

---

## 7. Editing an existing chaptered file

**File → Open Existing Master…** (`Ctrl+O`) opens a finished file so you can
correct its tags, chapter titles, link URLs, and images.

- **Save Changes** (`Ctrl+Shift+S`) rewrites tags and chapters in-place for
  MP3 files — no re-encode, no quality loss.
- **Save As** (`Ctrl+Alt+S`) writes a new file (required for M4B, which cannot
  be re-tagged in place).

### Reshaping the chapter map

- **Merge Up** (`Delete` in edit mode) folds a chapter into its neighbour.
- **Split at Playhead** adds a new boundary at the player's current position —
  pause at the right spot, click **Split Here**, and give it a title.
- **Set Link & Image…** also lets you type a precise **start time** for any
  chapter except the first.
- **Move Up / Move Down** swap chapter labels while keeping audio positions
  fixed. Useful for correcting a mislabelled or misordered chapter list.

### Reordering the audio itself

When you reorder chapters in edit mode and then click **Save Changes** or
**Save As**, ChapterForge asks:

> *You have reordered the chapters. Should the audio also be reordered?*

- **Yes** — opens a Save As dialog (defaulting to `filename (reordered).mp3`).
  FFmpeg extracts each chapter segment and concatenates them in the new order.
  The original file is **never** modified. No re-encode — audio quality is
  preserved.
- **No** — saves tags and chapter labels only; the audio plays in its original
  order.

### Loading and saving chapter lists

- **Edit → Save Chapter List…** exports the current list as **Audacity labels**,
  a **CUE sheet**, plain **timestamps**, or **Podcasting 2.0 JSON**.
- **Edit → Load Chapter List From File…** (edit mode) reads any of those
  formats and replaces the open master's markers; use **Save Changes** to keep
  them.

---

## 8. The View menu

The **View** menu gives you instant control over the app's appearance:

- **Theme** submenu: **Follow System**, **Light**, **Dark**, **High Contrast**.
  Changes apply immediately without opening Settings.
- **Larger Text** (`Ctrl+=`), **Smaller Text** (`Ctrl+-`), **Reset Text Size**
  (`Ctrl+0`) — adjusts the font size for all text in the app.
- **Show Audio Player** — toggle the player panel on or off.

---

## 9. The Command Palette

Press `Ctrl+Shift+P` (or **Tools → Command Palette**) to search and run any
command by name. Type any part of the name — the list filters as you type.
Unavailable commands are shown with a dash prefix so you can still discover
them. Use `Down`/`Up` to navigate, `Enter` to run, `Escape` to close.

The **Quick Actions** dropdown in the source bar also provides one-click
access to Command Palette, Look for Updates, Settings, and Get Help.

---

## 10. Find chapters in silent gaps

**Tools → Find Chapters in Silent Gaps…** analyses one long recording and
proposes chapter breaks at its silent gaps. Tune the **silence threshold** and
**minimum silence length** in **Settings → Advanced**. The detected chapters
open in edit mode so you can rename them and save.

---

## 11. Build multiple books at once

**Tools → Build Multiple Books…** points ChapterForge at a *parent* folder and
builds a master for **every** book sub-folder that contains MP3 files, using
your current settings. Completed masters land under `_ChapterForge/Completed/`
and failures under `_ChapterForge/Failed/`.

---

## 12. Auto-building in the background

**Tools → Set Up Automatic Building…** (`Ctrl+W`) lets you define watch
folders. ChapterForge monitors them; when a new folder of MP3s appears it
builds the master automatically.

**Tools → Auto-Build in Background** minimises ChapterForge to the system
tray and starts watching. Enable **Auto-Build When I Sign In** to have it
start automatically at login.

---

## 13. Job files (saved setups)

**File → Save This Setup as a Template…** (`Ctrl+G`) saves the current source
folder, chapter order, titles and tag values as a `.cfjob` file — a simple
hand-editable text file. **File → Load a Saved Setup…** (`Ctrl+L`) restores
it later, or share it with a colleague.

---

## 14. FFmpeg

On first launch, ChapterForge will offer to download FFmpeg automatically if
it is not already installed. FFmpeg handles all audio probing and encoding. It
is stored in `%APPDATA%\ChapterForge\bin\` and is never installed system-wide.

---

## 15. Accessibility

ChapterForge is built to be fully usable with NVDA, JAWS, Narrator, and any
other Windows screen reader:

- Every control has a descriptive accessible name and a visible label.
- All operations are keyboard-accessible via menus, buttons, and shortcuts.
- Long operations (build, download, reorder) run on background threads and
  announce start, progress, and completion to your screen reader.
- The chapter list announces the selected chapter's number and title on each
  navigation keystroke.
- Arrow-key navigation in the chapter list automatically selects the focused
  item so the Play button and other actions stay enabled.

---

## 16. Getting help

- **Help → User Guide** (`F1`) — this document.
- **Help → Keyboard Shortcuts** (`Ctrl+/`) — shortcut reference.
- **Help → Get Help Information…** — saves a diagnostic report for support.
- **Help → Look for Updates…** — checks for a newer version and offers to
  download and install it.
- Issues and questions: https://github.com/BITS-ACB/chapterforge
