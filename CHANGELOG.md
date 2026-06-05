# Changelog

All notable changes to ChapterForge are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.82] - 2026-06-05

### Fixed
- **Audio reorder crash** - `write_id3_chapters` was called instead of the
  correct `write_tags_and_chapters`; would have crashed on first audio reorder.
- **Command Palette entry** - selecting "Command Palette" from within the
  palette itself raised `AttributeError` (called method on dialog, not frame).
- **FFmpeg error messages** - segment extraction errors now show FFmpeg's
  `stderr` output instead of the empty `stdout`.
- **Page stays on Step 2 when opening a new file** - loading a file in edit
  mode or switching to build mode now always resets back to the chapters page.
- **Edit This Chapter uses focused item** - F2 / Edit Chapter now correctly
  acts on the keyboard-focused item even when the list selection state lags.

### Changed
- **User Guide completely rewritten** to reflect the two-page workflow, Edit
  menu, View menu, audio reorder, and all features added since 1.0.

## [1.81] - 2026-06-05

### Added
- **Edit menu** - Dedicated Edit menu with chapter operations: Edit This Chapter (F2),
  Move Up, Move Down, Remove/Merge Up, Load Chapter List, Save Chapter List.
  Chapter import/export moved here from the File menu where they belong logically.
- **View menu** - New View menu with live theme switching (Follow System, Light, Dark,
  High Contrast), text size controls (Larger Ctrl+=, Smaller Ctrl+-, Reset Ctrl+0),
  and Show/Hide Player toggle. Theme changes apply instantly without opening Settings.
- **Quick Actions dropdown** - A "Quick Actions..." combo in the source bar gives
  one-click access to Command Palette, Look for Updates, Settings, and Get Help.
- **Portable installation mode** - The single installer now lets you choose Standard
  (installs to Program Files with Start Menu) or Portable (extracts to any folder -
  USB drive, network share, no registry writes, no uninstaller).
- **GitHub Pages documentation** - https://bits-acb.github.io/chapterforge/ is now live.

## [1.80] - 2026-06-04

### Added
- **Auto-download FFmpeg on first launch** - Beautiful progress dialog shows while FFmpeg 
  downloads in the background. Main window only appears when ready. Seamless experience.
- **GitHub Pages documentation site** - Docs automatically served online. App opens local 
  files in development, falls back to GitHub Pages in releases. Users always have access.

### Changed
- **Bundle size reduced 90%** - Removed FFmpeg (390MB) and documentation from installer.
  Bundle shrinks from 435MB to 45MB. FFmpeg auto-downloads as needed. Friendly UX!
- **Friendlier, less technical language throughout the app:**
  * "Auto-chapter by Silence" → "Find Chapters in Silent Gaps"
  * "Batch Build Folder" → "Build Multiple Books"
  * "Watch Folders" → "Set Up Automatic Building"
  * "Start Background Watcher" → "Auto-Build in Background"
  * "Start Watcher at Sign-in" → "Auto-Build When I Sign In"
  * "Load Job File" → "Load a Saved Setup"
  * "Generate Job File" → "Save This Setup as a Template"
  * "Import/Export Chapters" → "Load/Save Chapter List"
  * "Edit Selected Chapter" → "Edit This Chapter"
  * "Play Selected Chapter" → "Listen to This Chapter"
  * "Split Chapter at Playhead" → "Split Here"
  * "Choose Output File" → "Save Master As"
  * "Check for Updates" → "Look for Updates"
  * "Save Diagnostics" → "Get Help Information"
- Makes ChapterForge feel more accessible and less technical for new users.

## [1.7.3] - 2026-06-04

### Fixed
- **Accessibility hardened across all dialogs:**
  * All checkboxes on Build and General settings tabs now have visible labels
  * Preferences dialog puts focus on first control when opened
  * Settings controls verified to have proper accessible names
- **Diagnostics menu no longer locks up** - now runs on background thread
  while announcing progress
- **Removed all m-dashes** (replaced with regular hyphens) for better compatibility
- **Added Visit Project Website button** to About dialog

## [1.7.2] - 2026-06-04

### Fixed
- **Cover image browse button label** now reads "Browse for Cover Image" instead 
  of just "Browse" for clearer accessibility.

## [1.7.1] - 2026-06-04

### Fixed
- **Task mode selector no longer auto-opens dialogs.** Switching between "Build" 
  and "Edit" modes now just changes the UI; users click Browse to open files/folders.
- **Edit fields and chapter list are non-tabbable when empty.** The chapter list, 
  title field, and tag fields are now disabled (and excluded from tab order) until 
  there is content to edit.
- **Browse button tooltip simplified** for clearer accessibility.
- **Bundled FFmpeg binaries** in the repo so builds work out-of-the-box without 
  manual FFmpeg download/setup.

## [1.7.0] - 2026-06-04

A UI polish and accessibility release. The app now shows only what is relevant
to the task you are doing, the chapter list tells you more without you having
to ask, and light and dark themes are available.

### Added
- **Task selector combo on the main window.** A dropdown at the top of the
  Source section now says "Build new master from MP3 files" or "Edit chapters
  in an existing file." Choosing one switches the mode and opens the right
  dialog automatically. The combo also acts as a visible mode indicator so you
  always know which mode you are in, which a screen reader will read on focus.
- **Build-only sections hide in edit mode.** The Options section (bitrate,
  format, normalize, gap) and the Output section disappear entirely when you
  open an existing file to edit. They are not useful in edit mode and were
  previously just a row of dimmed controls taking up space. They reappear when
  you switch back to build mode.
- **Source box adapts its labels and button to the current mode.** In edit mode
  the box is titled "Current file," the path label reads "Open file:," and the
  Browse button becomes "Open File…" and opens a file picker instead of a
  folder picker. In build mode everything reads as before.
- **Light and dark themes.** Settings > General now has a Theme dropdown with
  four options: Follow system (default, uses your Windows color scheme), Light
  (white background with dark text), Dark (dark background with light text),
  and High contrast (black background with white text). The old High-contrast
  checkbox is replaced by this single control; existing settings migrate
  automatically.
- **Move Up and Move Down have informative tooltips in edit mode.** Instead of
  just saying "unavailable," hovering over either button when editing an
  existing master now reads "Reordering is not available in edit mode — chapter
  order is determined by start times."

### Changed
- **Focus after loading a folder goes to the chapter list**, not the title
  field. The title field is empty until a chapter is selected, so landing focus
  there first was confusing for keyboard and screen-reader users. The list is
  the primary content control and is where focus belongs.
- **Chapter list columns auto-size after every load.** The Title column and the
  Source file or URL column resize themselves to fit the widest value, capped
  at reasonable maximums so no other column gets pushed off screen.
- **Status bar and status label updated** to mention Ctrl+Shift+P so new users
  discover the command palette immediately on first launch.

## [1.6.0] - 2026-06-04

A keyboard accessibility and discoverability release. Every command in the app
is now reachable from one place, the chapter list has a right-click menu, the
Alt+F shortcut conflict is resolved, and ChapterForge can start quietly in the
system tray.

### Added
- **Command Palette (Ctrl+Shift+P)** — type any part of a command name to find
  and run it without touching the mouse. All menu and button actions are listed.
  Commands that are not available in the current state are shown with a dash
  prefix so you can still discover them. Down and Up arrows move through results;
  Enter runs the selected command; Escape closes without doing anything. The
  palette is also reachable from Tools > Command Palette.
- **Right-click context menu on the chapter list** — right-clicking (or pressing
  the application key) on any row in the chapter list pops up a small menu with
  the actions that make sense right now: Edit Chapter, Move Up, Move Down, Play
  Chapter, Split Here (edit mode), and Remove or Merge Up depending on the mode.
  Only relevant items are shown; items that cannot be used are dimmed.
- **Start minimized in system tray** — a new checkbox in Settings > General lets
  ChapterForge launch directly to the system tray without showing the main window.
  Double-click the tray icon to open it. The setting takes effect the next time
  you start the app. This is separate from the background watcher; no watch
  folders need to be configured.

### Fixed
- **Alt+F now opens the File menu** as expected. The source folder label had an
  ampersand on the letter F, which caused Windows to route Alt+F to that label's
  associated text field instead of dropping down the File menu. The mnemonic has
  been removed from the label; the Browse button still has its own shortcut.
- **Build-Release.ps1 step 3 no longer fails** when ffmpeg is on the system PATH
  but not copied into the project's bin folder. The PyInstaller spec file now
  looks for ffmpeg and ffprobe in the local bin folder first, then falls back to
  whatever is on the PATH. If neither location has the tool it reports a clear
  error message instead of a cryptic PyInstaller path-not-found.

## [1.5.0] - 2026-06-04

An accessibility and usability overhaul. Every control is now fully described
when tabbing with a screen reader, the settings dialog is reorganised into
logical tabs, and the keyboard shortcut model matches standard app conventions.

### Added
- **Build-Release.ps1** — a single PowerShell script that runs tests, builds
  HTML docs, runs PyInstaller and packages the Inno Setup installer in one step.
  Accepts `-SkipTests`, `-SkipDocs`, `-SkipInstaller` and `-Open` flags.
- **Smart Ctrl+S** — `Ctrl+S` now does the right thing in context: triggers
  Build in build mode and Save Changes in edit mode (M4B files redirect you to
  Save As with a spoken explanation). `Ctrl+Shift+O` is the new shortcut for
  choosing the output file location.
- **Tooltips on every control** — every button, checkbox, dropdown and spinner
  on the main window and the settings dialog has a plain-English tooltip that
  explains what it does and why you'd change it. Useful for new users and
  screen-reader users who explore with the mouse.

### Changed
- **Settings dialog** restructured into three tabs: *Build* (encoding choices),
  *General* (player, appearance, announcements) and *Advanced* (silence
  detection). Related settings are grouped; unrelated ones no longer share a
  crowded flat list.
- **Options row** on the main window split into two rows: the three encoding
  dropdowns on top, and the three toggles/values below. Reduces horizontal
  crowding and makes the tab order easier to follow.
- **Button names** throughout carry their full context when read by a screen
  reader (e.g. "Browse for source folder of MP3 files", "Save master file to a
  chosen location", "Edit selected chapter title, link and image"). Trailing
  punctuation removed from player button names.
- **"Set…" → "Save to…"** on the output-file button — the label now reads as
  intent rather than a generic imperative.
- **"Edit Title" → "Edit Chapter…"** — the ellipsis signals a dialog and the
  name reflects that it edits title, URL *and* image.
- **"Play Selected" → "Play Chapter"** — shorter and unambiguous.
- **"Split at Playhead" → "Split Here"** — shorter label, tooltip carries the
  explanation.
- **Build button label** updates dynamically: "Build Master MP3" when MP3 is
  selected, "Build M4B Audiobook" when M4B is selected.
- **"Remove" / "Merge Up"** button's accessible name updates in edit mode to
  "Merge selected chapter into the one above it".
- **Save Changes button tooltip** explains the greyed-out state for M4B files.
- **Settings dialog z-order fix** — `StaticText` labels are now created before
  their associated controls so NVDA's preceding-static-text heuristic maps each
  label to the correct control.
- **Chapter list** label and column 4 header switch dynamically between build
  mode ("Chapter list, one per source file" / "Source file") and edit mode
  ("Chapter list" / "URL / Link").
- **Unsaved-changes guards** — switching mode, opening a folder, or loading a
  job file while in edit mode with unsaved edits now prompts before discarding.
- **Player sizer leak fixed** — repeated load/release cycles no longer
  accumulate dead sizer items.
- **Volume slider name** updated to "Playback volume, 0 to 100 percent" for
  clearer screen-reader announcement.
- **Initial status text** is now a welcoming instruction rather than "Ready."

## [1.2.0] - 2026-06-20

A polish release that deepens editing, playback and accessibility. Everything
remains fully keyboard accessible with screen-reader announcements.

### Added
- **Play from a chosen chapter** — a "Play Selected" button (and the player's
  chapter map) lets you jump straight to any chapter. In build mode it auditions
  the selected source file.
- **Real chapter editing of existing masters** — merge a chapter into its
  neighbour (Remove/Delete becomes "Merge Up" in edit mode), **Split at
  Playhead** to add a boundary where the player is paused, and adjust a
  chapter's **start time** from the Edit dialog. Edits update the player without
  interrupting playback.
- **Import / Export chapter lists** — export the chapter list as Audacity
  labels, a CUE sheet, plain timestamps or Podcasting 2.0 JSON; import any of
  those into an open master to replace its markers.
- **Inter-chapter gaps** — insert a configurable amount of silence between
  chapters when building (also `--gap-seconds` on the command line).
- **Post-build verification** — after each build ChapterForge re-reads the file
  and confirms the chapter count, announcing "Verified N chapters."
- **Output size estimate** — a live estimate of the master's duration and
  approximate file size is shown before you build.
- **Open Recent** — the File menu remembers recently opened folders, masters and
  job files.
- **Accessibility appearance options** — adjustable UI text size and an optional
  high-contrast theme (Tools → Settings).
- **Save Diagnostics** (Help menu) — write a support report with version,
  Python/wxPython/OS and FFmpeg details, and your current settings.
- **Download & install updates** — "Check for Updates" can now download the
  right installer for your platform (over a verified HTTPS/GitHub connection)
  and launch it, instead of only opening the releases page. The CLI gains a
  matching `--update`.

### Changed
- Editing chapters of an open master now updates the in-app player in place
  rather than reloading the file, so playback and position are preserved.

## [1.1.0] - 2026-06-15

A big "maximum magic" feature release. Everything stays fully keyboard
accessible with screen-reader announcements.

### Added
- **M4B audiobook export** — choose MP3 or M4B output. M4B writes proper MP4
  chapter metadata and an attached cover, ideal for audiobook players.
- **In-app accessible player** — preview the master without leaving the app:
  Play/Pause, Stop, Previous/Next chapter, Rewind/Forward (by a configurable
  interval), a volume control and a position slider. The current chapter is
  announced as the play-head crosses each boundary; Previous restarts the
  current chapter unless you are within the first few seconds.
- **Edit existing chaptered files** — open a finished MP3 (or M4B) to correct
  its ID3 tags and chapter titles. MP3 edits save in place (no re-encode);
  any file can be written to a new file with **Save As**.
- **Save As** — write the master, or an edited master, to a new file without
  touching the original.
- **Auto-chapter by silence** — detect chapter breaks in a single long
  recording from its silent gaps, then rename and save them.
- **Batch build a library** — point ChapterForge at a parent folder and build a
  master for every book sub-folder in one pass.
- **Podcasting 2.0 chapters** — optionally write a `…chapters.json` sidecar with
  per-chapter titles, and optional link URLs and images.
- **Rich per-chapter metadata** — the Edit dialog now sets a chapter's title,
  link URL and image.
- **Pre-flight checks** — before a build, ChapterForge warns about mixed sample
  rates or channel counts so you can decide whether to continue.
- **Settings dialog** (Tools → Settings, `Ctrl+,`) — defaults for output format,
  re-encode quality, normalization, cover auto-detect, chapters JSON, the player
  skip interval and volume, announcement detail and silence-detection tuning.

### Changed
- The output format and a "write chapters JSON" option are now on the main
  Options bar; the default output extension follows your chosen format.

## [1.0.0] - 2026-06-01

First public release.

### Added
- **Master builder** — concatenate a folder of MP3s into one master MP3 with
  embedded ID3v2 `CHAP` chapter frames and an ordered `CTOC`. Uses lossless
  `-c copy` when source streams are uniform; re-encodes only when required.
- **Accessible wxPython GUI** — fully keyboard-navigable, labeled controls,
  menus with mnemonics and accelerators, and screen-reader announcements for
  status and progress. Chapter list supports edit (F2), reorder (Alt+Up/Down)
  and remove (Delete).
- **ID3 tagging** — title, artist, album-artist, album, genre, year, comment,
  cover art (APIC), with auto-detected cover preview.
- **Chapter titles from filenames**, with an option to keep or strip leading
  track numbers.
- **Rich CLI** (`chapterforge-cli`) with `--help`, live terminal progress, and
  flags for tags, output path, job files, watching and update checks.
- **Job files (`.cfjob`)** — simple, hand-editable definitions of file order
  and chapter titles. Generate, edit and load from the GUI or CLI.
- **Reusable processes & folder watcher** — define watch folders with naming
  templates; a system-tray app processes new MP3 folders automatically in the
  background.
- **Windows notifications** — toast + screen-reader announcements when jobs
  start and complete, in both foreground and background modes.
- **Visible output organization** — completed masters land in
  `_ChapterForge\Completed\<book>\` with a readable `… - chapters.txt` report;
  failures are recorded under `_ChapterForge\Failed\<book>.txt`.
- **Existing-master detection** — a previously built master in the source
  folder is skipped instead of being added as an extra chapter.
- **Check for updates** via GitHub Releases.
- **Run watcher at sign-in** (per-user) toggle.
- **Packaging** — PyInstaller one-folder build (GUI + CLI exes, ffmpeg bundled)
  and an Inno Setup installer.
- **About window** crediting **Blind Information Technology Specialists
  (BITS)**, showing the version and a 2026 copyright, with buttons linking to
  Join BITS, Let It Glow and Community Access.
- Documentation: README, User Guide, Deployment guide, third-party notices,
  MIT license. The in-app **Help** menu opens accessible HTML versions
  (generated by `tools/build_docs.py`) in the browser.

[1.7.0]: https://github.com/bits-acb/chapterforge/releases/tag/v1.7.0
[1.6.0]: https://github.com/bits-acb/chapterforge/releases/tag/v1.6.0
[1.1.0]: https://github.com/bits-acb/chapterforge/releases/tag/v1.1.0
[1.0.0]: https://github.com/bits-acb/chapterforge/releases/tag/v1.0.0
