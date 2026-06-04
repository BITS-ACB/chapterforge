# Changelog

All notable changes to ChapterForge are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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

[1.1.0]: https://github.com/bits-acb/chapterforge/releases/tag/v1.1.0
[1.0.0]: https://github.com/bits-acb/chapterforge/releases/tag/v1.0.0
