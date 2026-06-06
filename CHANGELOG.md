# Changelog

All notable changes to ChapterForge are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).


## [1.95] - 2026-06-05

### Added

- **Lossless MP3 Trim and Cut** - The player panel now includes a "Trim /
  Cut Selection" section with Set Begin, Set End, and Clear Selection buttons
  that mark a time range using the current playhead position. "Pre-Listen as
  Cut" plays from just before the cut point so you can hear the edit in
  context. "Save Trimmed..." saves the selected region to a new file using
  FFmpeg lossless copy — no quality loss. The trim state resets automatically
  when a new file is loaded. `core.trim_file()` implements the FFmpeg pass.

- **Split One Long Recording into Chapters** - A new "Split one long
  recording into chapters" task in the task dropdown. Opens a single long
  audio file in edit mode. Use the player and the existing "Split Here" button
  to mark chapter boundaries, then File - "Save as Individual Chapter Files"
  to save each chapter as a separate file using lossless FFmpeg copy.
  `core.split_into_files()` handles the splitting with an optional per-chapter
  progress callback.

- **File - Save as Individual Chapter Files** - Available in edit mode when
  two or more chapters exist. Opens a folder picker, then splits the open
  master into one file per chapter. Runs on a background thread with
  announcement on completion. Accessible from the command palette.

- **Chapter Transition Fades** - Settings - Build - "Chapter transition fade
  (seconds)" sets a fade-out then fade-in duration applied at each chapter
  boundary during the build. Range 0-5 seconds, default 0 (no fade).
  Implemented via FFmpeg `afade` filter; forces re-encoding of the faded
  boundary portions. `core.apply_fades()` is the per-file helper.

- **Reusable Build Presets** - Settings dialog now opens with a preset bar
  at the top. Three built-in presets are available immediately: Podcast MP3,
  Audiobook M4B, and FLAC Archive. Users can save any combination of build
  settings as a named preset and reload or delete it at any time. Presets are
  stored in settings.json under "presets".

- **CSV Chapter Export** - "Save Chapter List" now includes a CSV format
  (comma-separated: chapter number, title, start, duration, link URL, image
  path). Useful for importing into spreadsheets, databases, or generating
  transcripts. `core.chapters_to_csv()` implements the export.

- **File Renaming from Chapter Titles** - Edit menu - "Rename Source Files"
  opens a dialog where a naming pattern (using `{n}`, `{n:02d}`, `{title}`,
  `{ext}`) is applied to all source files. A two-column preview shows the
  current and new filename for each item before applying. The rename is
  undo-aware.

- **Go to Time (Ctrl+G)** - A new View menu item and keyboard shortcut opens
  a "Go to Time" dialog. Enter a timestamp in HH:MM:SS, MM:SS, or decimal
  seconds format and the player jumps to that position. Available whenever
  audio is loaded. The previous Ctrl+G shortcut (Save This Setup as Template)
  has moved to Ctrl+Shift+G.

- **Per-Chapter Audio Level Announcements During Build** - When a build is
  running, the peak dB level of each source chapter is probed via FFmpeg
  `astats` and announced to the screen reader as each chapter is processed.
  Helps verify normalization is working correctly across chapters.
  `core.get_file_peak_db()` implements the FFmpeg probe.

- **GoToTimeDialog class** - Accessible dialog that accepts time in multiple
  formats; parses via `core._ts_to_ms`.

- **RenameSourceFilesDialog class** - Pattern-based rename with live preview
  list showing old and new filenames.

### Changed

- **Ctrl+G** reassigned — Save This Setup as Template moved to Ctrl+Shift+G.
  Ctrl+G is now Go to Time (player must have audio loaded).

- **Task dropdown** — third option "Split one long recording into chapters"
  added; no existing task indices changed.

### Fixed

- **CI failure: pyproject.toml BOM** — `sed -i` on Windows injected a
  UTF-8 BOM into pyproject.toml, which TOML parsers reject. File rewritten
  without BOM; all future version bumps use the Edit tool directly.

## [1.92] - 2026-06-05

### Added

- **FLAC, WAV, OGG, M4A, AAC, and Opus source file support** - ChapterForge
  now accepts any audio format FFmpeg supports as a chapter source file. Source
  folders can contain a mix of formats; each is probed with FFprobe and encoded
  to the chosen output format during the build. The folder scanner now uses a
  broad `AUDIO_EXTS` constant covering .mp3, .flac, .wav, .ogg, .m4a, .aac,
  .opus, .wma, and .mp2.

- **FLAC output with embedded chapters** - A third output format option
  (Settings - Build - Output format: FLAC lossless .flac) builds a lossless
  FLAC master with Vorbis Comment chapter markers (CHAPTER001/CHAPTER001NAME
  convention). Cover art is embedded as a FLAC picture block. The build button
  label changes to "Build FLAC Master" when FLAC output is selected.

- **Undo and Redo for chapter list operations** - Ctrl+Z undoes the last
  chapter operation; Ctrl+Y redoes it. The Edit menu shows dynamic labels
  ("Undo Rename Chapter 1", "Redo Move Chapter Up") and enables/disables based
  on stack state. Operations covered: rename, move up/down, remove/merge, batch
  edit titles, and import chapter titles. The stack holds up to 50 actions and
  is cleared when a new file is loaded or a build starts.

- **Batch Edit Titles dialog** - Edit menu - "Batch Edit Titles" opens a dialog
  that applies transformations to all chapter titles at once. Transforms: title
  case, strip leading track numbers, replace underscores with spaces, remove
  extra spaces, find-and-replace, and a number pattern (Chapter {n}). A live
  preview shows before/after for the first 8 chapters before applying.

- **Per-file chapter loudness normalization** - Settings - Build - "Normalize
  each chapter individually" applies FFmpeg loudnorm to each source file before
  concatenating, targeting a configurable LUFS level (default -16.0 LUFS).
  More consistent than global normalize when source files were recorded at very
  different levels.

- **CUE sheet import in build mode** - Load Chapter List From File now works in
  both edit mode (replaces all chapter markers) and build mode (applies chapter
  titles from the CUE or timestamp file to the loaded source items by position).
  The menu item and command palette entry are now enabled whenever chapters are
  loaded, not only in edit mode.

- **Configurable chapter list columns** - View - Columns submenu toggles
  individual columns (Title, Start, Duration, Source file) on or off.
  Column visibility is saved in settings and restored at startup. The # column
  is always visible.

- **Keyboard shortcut overrides** - Settings stores a key_overrides dict that
  maps command names to custom key strings. Overrides are applied to menu items
  at startup via _apply_key_overrides(). The settings infrastructure and
  application logic are in place for a future settings UI.

- **Product roadmap** (from 1.91) - docs/ROADMAP.md with 13 viable features
  ranked by impact. Waveform visualization, MP3 recording, advanced filtering,
  cover art tools, and out-of-scope items removed per product decisions.

## [1.91] - 2026-06-05

### Added

- **Watch folder setup step in the Startup Wizard** - The wizard now has
  eleven steps. The new "Automatic Building in the Background" step explains
  the watch folder feature and offers a "Set Up Automatic Building Now" button
  that launches the watch folder configuration dialog directly from the wizard.
  Users can also skip or use Next to continue without setting it up.

### Added

- **Product roadmap** - `docs/ROADMAP.md` added with 20 viable features ranked
  by impact. Covers lossless trim/cut, broad source format support, waveform
  visualization, recording splitting, batch metadata editing, cover art tools,
  presets, metadata export, FLAC output, undo/redo, file renaming, and more.
  Features are self-contained (no online services). Original inventory file
  removed.

## [1.90] - 2026-06-05

### Added

- **Playback speed control with pitch preservation** - Speed selector (0.75x, 1.0x, 1.25x,
  1.5x, 1.75x, 2.0x) in the audio player. Uses FFmpeg `atempo` for time-stretching that
  preserves pitch at any speed - no chipmunk effect. Chapter boundaries are automatically
  scaled so Prev/Next navigation stays accurate. Resumes playback from the equivalent
  position after a speed change.
- **"Save at This Speed" export** - Button beside the speed selector saves the audio at
  any speed as a new MP3 file. Uses the same FFmpeg `atempo` pipeline as playback.
  The original file is always the source, so any speed can be exported regardless of
  what is currently loaded.
- **Startup Wizard** - Ten-step guided setup experience shown on first launch and
  available at any time from Help - Setup Wizard. Each step explains a key concept and,
  where relevant, lets the user configure the matching setting right there. Every step
  is skippable. Settings are saved incrementally as the user advances. Fully accessible:
  dialog title announces the current step, body text is a navigable read-only control,
  and a11y.announce fires on every step change. Steps: Welcome, Two-Step Workflow,
  Opening Files, Chapter Titles, Output Format, Audio Quality, Podcasting 2.0 Chapters,
  Cover Art, Keyboard Shortcuts, and a personalized summary on the final step.
- **Column navigation in the chapter list** - Left and Right arrow keys now navigate
  between columns (Chapter number, Title, Start time, Duration, Source file), announcing
  each column name and value. Compatible with JAWS and NVDA table navigation. Up/Down
  resets to row-summary mode. Accessible name updated to describe the feature.
- **Go to Chapters (Ctrl+1) and Go to Tags and Build (Ctrl+2)** - New View menu items
  and frame-level keyboard shortcuts to jump between the two workflow pages from anywhere
  in the app. Both are in the command palette and greyed out when already on that page.
- **Check for updates on startup** - New setting on the General tab (on by default).
  Runs a silent background check at launch; only notifies when an update is available.
  Never shows a "you are up to date" message at startup.
- **Minimize to System Tray button** - Permanently visible button at the bottom-right of
  the main window (last in tab order). Hides the window and shows a tray icon so
  ChapterForge keeps running while out of the way.
- **Play This Chapter and Split Here in Edit menu** - Both actions were previously only
  in the right-click context menu. They are now also in the Edit menu for keyboard and
  menu-bar users.

### Changed

- **Options panel removed from the main page** - Output format, re-encode quality,
  normalize, gap, and Podcasting 2.0 JSON settings have been removed from the chapter
  list page. These settings live only in Settings (Ctrl+comma), eliminating the
  duplication and simplifying the main screen. Values are read directly from the saved
  settings when building.
- **"Save to" button removed from output section** - Identical to File - Save Master As;
  the menu item is sufficient. The output path display field and its hint text remain.
- **Browse button renamed "Open Folder" / "Open File"** - Matches the standard label
  pattern used elsewhere and describes the action instead of the mechanism.
- **General tab is now the first tab in Settings** - Player, appearance, and startup
  options are more commonly adjusted than build encoding settings; General tab opens first.
- **Alt+Up / Alt+Down are now frame-level accelerators** - Move Up and Move Down in the
  chapter list now work from anywhere in the window, not only when the list has focus.
  The redundant key handler in the list has been removed to prevent double-firing.
- **Ctrl+/ opens keyboard shortcuts in the browser** - Was a plain-text scroll dialog.
  Now opens the User Guide at the keyboard shortcuts section using the same browser-based
  help as F1.
- **Save As shortcut changed from Ctrl+Alt+S to Ctrl+Shift+A** - Ctrl+Alt combinations
  conflict with AltGr on international keyboards and with some screen reader commands.
- **Organization name corrected** - "Blind Information Technology Specialists" corrected
  to "Blind Information Technology Solutions" across all source files, docs, and metadata.
- **Deployment Guide hidden from user-facing navigation** - The HTML page is still
  generated for developers but is no longer listed in the documentation nav or Help menu.

### Fixed

- **Play button not working in build mode** - Windows media backends (WMP, DirectShow,
  Media Foundation) require a visible, realized HWND before Load() will accept a file.
  The MediaCtrl was being hidden after creation, silently causing Load() to fail.
  The control now remains visible at zero size, which is visually identical.
- **"Playing chapter X" announced even when audio load fails** - The announce was outside
  the success branch. It now only fires when load succeeds; on failure a descriptive
  error is announced instead.
- **Chapter title numbers not stripped** - Files named with only digits (e.g. "01.mp3",
  "1.mp3") were falling back to the bare number as the chapter title. Pure-numeric stems
  now return an empty title, which is then replaced with "Chapter N" automatically.
- **Checkbox accessible names not read by NVDA** - `SetName()` sets wxPython's internal
  Python name, not the Win32 button window text that NVDA reads. All checkboxes in
  Settings now use a descriptive `label=` parameter and are created without a separate
  static-text label for that row (`make_check` pattern). CLAUDE.md updated to document
  the correct per-control-type rules permanently.
- **Spinner accessible names not read by NVDA** - `wx.SpinCtrl` and `wx.SpinCtrlDouble`
  are composite Win32 controls; NVDA focuses the inner edit field which has no
  associated label. All spinners in Settings now use `ctrl.SetAccessible(_NamedAccessible(ctrl, name))`.
- **LoadURI fallback for media loading** - Some Windows configurations accept a
  `file:///` URI but not a bare path in `wx.media.MediaCtrl.Load()`. A fallback to
  `LoadURI()` is now tried automatically when `Load()` returns False.
- **Multi-line list items broken in HTML documentation** - The custom Markdown converter
  did not collect continuation lines for list items. Lines that wrapped past the first
  line were split into separate paragraphs, breaking screen reader reading. Fixed by
  collecting continuation lines before emitting each `<li>`.
- **Ctrl+Alt+S removed** - Conflicts with AltGr on international keyboards and with
  screen reader keyboard commands. Save As is now Ctrl+Shift+A.

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
- **About window** crediting **Blind Information Technology Solutions
  (BITS)**, showing the version and a 2026 copyright, with buttons linking to
  Join BITS, Let It Glow and Community Access.
- Documentation: README, User Guide, Deployment guide, third-party notices,
  MIT license. The in-app **Help** menu opens accessible HTML versions
  (generated by `tools/build_docs.py`) in the browser.

[1.7.0]: https://github.com/bits-acb/chapterforge/releases/tag/v1.7.0
[1.6.0]: https://github.com/bits-acb/chapterforge/releases/tag/v1.6.0
[1.1.0]: https://github.com/bits-acb/chapterforge/releases/tag/v1.1.0
[1.0.0]: https://github.com/bits-acb/chapterforge/releases/tag/v1.0.0
