# ChapterForge — User Guide

ChapterForge turns a folder of MP3 files into a single **master MP3** with
embedded chapter markers (ID3v2 `CHAP`/`CTOC`). Each source file becomes one
chapter, titled from its filename. It is designed to be fully usable with a
keyboard and a screen reader.

---

## 1. Quick start (graphical app)

1. Launch **ChapterForge** (Start menu shortcut, or `chapterforge` with no
   arguments).
2. **File → Open Folder…** (`Ctrl+Shift+O`) and choose the folder of MP3s.
   - Files are listed in natural order (`01`, `02`, `10`, `11`).
   - If a previously built master is found in the folder, it is skipped
     automatically and reported in the status line.
3. Review the **Chapters** list. Adjust as needed (see §3).
4. Fill in the **Tags** (title, artist, album, year, cover, etc.).
5. **File → Build Master MP3** (`Ctrl+B`).
6. Choose/confirm the output file, then Build (`Ctrl+S` is smart save).

The build runs on a background thread; progress and status are announced to
your screen reader. When it finishes, a master MP3 and a readable
`… - chapters.txt` report are written next to each other.

---

## 2. Keyboard shortcuts

| Key | Action |
| --- | --- |
| `Ctrl+Shift+O` | Open folder (build mode) |
| `Ctrl+O` | Open an existing chaptered file to edit |
| `Ctrl+S` | Build (build mode) or Save Changes (edit mode) |
| `Ctrl+B` | Build master (MP3 or M4B) - explicit |
| `Ctrl+Shift+S` | Save changes to the open master - explicit |
| `Ctrl+Alt+S` | Save As (a new file) |
| `Ctrl+L` | Load a Saved Setup (`.cfjob`) |
| `Ctrl+G` | Save This Setup as a Template |
| `Ctrl+W` | Set Up Automatic Building |
| `Ctrl+,` | Settings |
| `Ctrl+/` | Keyboard shortcuts help |
| `Alt+F4` | Exit |

**In the Chapters list:**

| Key | Action |
| --- | --- |
| `Up` / `Down` | Move selection |
| `F2` / `Enter` | Edit the selected chapter title |
| `Delete` | Remove the selected chapter (build mode) |
| `Alt+Up` / `Alt+Down` | Reorder the selected chapter (build mode) |

The **Edit Title** button opens a dialog for the chapter's title, an optional
link **URL** and an optional **image** (carried into the chapters JSON sidecar).

All actions are also available as labeled buttons (Edit Title, Move Up,
Move Down, Remove) and via the menus.

---

## 3. Working with chapters

- **Rename** a chapter: select it and press `F2` (or the **Edit Title**
  button). Titles default to the filename, with optional stripping of a leading
  track number.
- **Reorder**: `Alt+Up`/`Alt+Down` or the **Move Up**/**Move Down** buttons.
- **Remove**: `Delete` or the **Remove** button.
- Chapter start/end times are computed automatically from each file's duration.

---

## 4. Tags & cover art

Set the master's ID3 tags in the **Tags** panel: title, artist, album-artist,
album (defaults to the folder name), genre, year, comment and cover image.
ChapterForge auto-detects a cover image in the folder (e.g. `cover.jpg`) and
shows a preview; you can replace or clear it.

---

## 5. Output format: MP3 or M4B

On the **Options** bar choose the **Output format**:

- **MP3** — a single master MP3 with ID3v2 `CHAP`/`CTOC` chapters. Lossless
  `-c copy` when sources are uniform.
- **M4B** — an AAC audiobook with native MP4 chapter metadata and an attached
  cover image. Ideal for audiobook apps (Apple Books, BookPlayer, etc.).

The default output extension follows your choice. Tick **Write chapters JSON**
to also emit a Podcasting 2.0 `…chapters.json` sidecar with each chapter's
start time, title, and any link URL or image you set.

---

## 6. Previewing with the built-in player

A fully accessible player sits at the bottom of the window so you can check the
result without leaving ChapterForge. After a build you can load the file
straight into it; in edit mode the opened file loads automatically.

- **Play/Pause** (also `Space` when focused), **Stop**.
- **Previous / Next Chapter** — jump between chapters. *Previous* restarts the
  current chapter unless you are within the first few seconds, when it jumps to
  the previous one (familiar audiobook behaviour).
- **Rewind / Forward** — skip by the interval set in **Settings** (default 10s).
- **Volume** and **Position** sliders — adjust with the arrow keys.

The current chapter is announced to your screen reader as playback crosses each
boundary, and seeks/skip announce the new time.

---

## 7. Editing an existing chaptered file

**File → Open Existing Master…** (`Ctrl+O`) loads a finished file so you can fix
its ID3 tags and chapter titles (and link URLs/images).

- For **MP3**, **Save Changes** (`Ctrl+Shift+S`) rewrites the tags and chapters
  in place — no re-encode.
- For any file, **Save As** (`Ctrl+Alt+S`) writes a new file (the only way to
  save an M4B, which can't be re-tagged in place).

You can also reshape the chapter map (the audio itself is never changed):

- **Merge Up** (the Remove button / `Delete` in edit mode) folds a chapter into
  its neighbour, removing that boundary.
- **Split at Playhead** adds a new boundary at the player's current position —
  pause where the new chapter should begin, then split and give it a title.
- **Edit Title** also lets you type a precise **start time** (`H:MM:SS`) for any
  chapter except the first.
- **Play Selected** jumps the player straight to the highlighted chapter.

These edits update the player immediately without interrupting playback.

### Loading and saving chapter lists

- **File → Save Chapter List…** saves the current list as **Audacity labels**, a
  **CUE sheet**, plain **timestamps**, or **Podcasting 2.0 JSON**.
- **File → Load Chapter List From File…** (in edit mode) reads any of those formats and
  replaces the open master's markers; use **Save Changes** to keep them.

---

## 8. Find chapters in silent gaps

**Tools → Find Chapters in Silent Gaps…** analyses one long recording and proposes
chapter breaks at its silent gaps. Tune the **silence threshold** and **minimum
silence length** in **Settings**. The detected chapters open in edit mode so you
can rename them and then **Save Changes** (MP3) or **Save As**.

---

## 9. Build multiple books at once

**Tools → Build Multiple Books…** points ChapterForge at a *parent* folder and
builds a master for **every** book sub-folder that contains MP3s, using your
current format/quality options. Progress covers the whole run and a summary
reports successes and any failures.

Before each build, the main window shows a **live estimate** of the master's
duration and approximate file size. After a build, ChapterForge **verifies** the
result by re-reading it and announcing the confirmed chapter count.

---

## 10. Settings

**Tools → Settings** (`Ctrl+,`) collects your preferences: default output
format, re-encode quality, loudness normalization, cover auto-detect, chapters
JSON, an optional **gap of silence between chapters**, the player **skip
interval** and **default volume**, announcement detail, silence-detection
tuning, and accessibility appearance — **UI text size** and a **high-contrast
theme**. They persist between sessions.

The **File → Open Recent** submenu remembers the folders, masters and job files
you used most recently. **Help → Save Diagnostics…** writes a support report
(version, Python/wxPython/OS and FFmpeg details, and your settings) to a text
file.

---

## 11. Saved setups (`.cfjob` files)

A saved setup is a small, hand-editable text file that records the **order** and
**chapter titles** for a build (plus optional tags). Use it to script repeatable
builds or to prepare a build for the auto-builder.

- **Save** one from the current folder: **File → Save This Setup as a Template…**
  (`Ctrl+G`).
- **Load** one to rebuild: **File → Load a Saved Setup…** (`Ctrl+L`).
- From the CLI: `chapterforge-cli -j mybook.cfjob`.

The format is intentionally simple — open it in any text editor to change the
order of files or the chapter names.

---

## 12. Auto-building in the background

ChapterForge can sit in the **system tray** and build new folders of MP3s for
you automatically.

- **Tools → Set Up Automatic Building…** (`Ctrl+W`) — define reusable *processes*: a watch
  folder plus a naming template for the output master.
- **Tools → Auto-Build in Background** — minimises to the tray and watches.
- **Tools → Auto-Build When I Sign In** — registers a per-user startup entry so
  the auto-builder runs automatically when you log in.
- `chapterforge-cli --watch` runs the auto-builder standalone.

**How it stays safe:**

- A folder is only built once its set of files has been **unchanged** for a
  short settle window (so it won't grab a half-copied folder).
- Output goes into an excluded `_ChapterForge\Completed\<book>\` folder, so the
  watcher never re-processes its own output.
- Each folder is built **once**; done/failed markers and a lock file prevent
  double-processing.
- Failures are recorded under `_ChapterForge\Failed\<book>.txt`.
- You get a toast + screen-reader announcement when a build starts, finishes or
  fails.

---

## 13. Output organization

After a build you'll find, next to (or under `_ChapterForge\Completed\` for the
watcher):

- `<book> - Master.mp3` — the master with chapter markers.
- `<book> - Master - chapters.txt` — a readable report listing the tags and the
  start/end time and title of every chapter.

This makes it easy to confirm what was produced without opening an audio player.

---

## 14. Command line

Run `chapterforge-cli --help` for the full list. Common examples:

```bash
# Build a master from a folder
chapterforge-cli "C:\Audiobooks\My Book"

# Export an M4B audiobook and a Podcasting 2.0 chapters sidecar
chapterforge-cli "C:\Audiobooks\My Book" --format m4b --pod2-chapters

# Set tags and normalize
chapterforge-cli -i ./chapters -o book.mp3 --title "My Book" --artist "Jane Doe" --normalize

# Just preview the chapter plan
chapterforge-cli ./chapters --list

# Build a master for every book sub-folder of a library
chapterforge-cli --batch "C:\Audiobooks" --format m4b

# Find chapters in silent gaps of a long recording
chapterforge-cli --split-silence recording.mp3 --noise-db -30 --min-silence 0.8

# Build from a saved setup
chapterforge-cli -j mybook.cfjob

# Run the auto-builder / check for updates
chapterforge-cli --watch
chapterforge-cli --check-updates
```

---

## 15. Updates

**Help → Look for Updates** queries GitHub Releases and tells you if a newer
version is available. When an installer for your platform is published, you can
choose **Download & Install** — ChapterForge downloads it over a verified
HTTPS/GitHub connection, then launches the installer and closes so it can be
replaced. You can instead choose **Open Page** to download manually, or
**Later** to dismiss.

From a terminal, `chapterforge-cli --check-updates` reports the latest version,
and `chapterforge-cli --update` downloads and launches the installer.

---

## 16. Troubleshooting

- **A stray master became a chapter** — name your previously built master after
  the folder (e.g. `My Book.mp3`) or end it with `- Master.mp3`; ChapterForge
  skips those automatically.
- **The build re-encoded instead of copying** — this happens when source files
  have mismatched sample rates/channels, or when `--normalize` is used. The
  result is still correct; only the encode path differs.
- **The watcher didn't pick up a folder** — make sure copying has fully
  finished; the settle window waits for the files to stop changing.
- **The player won't play an M4B** — in-app playback uses the system media
  backend, whose M4B/AAC support varies by machine. The exported file is still
  valid; play it in your audiobook app, or preview the MP3 build instead.
