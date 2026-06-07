# ChapterForge

**Turn a folder of audio files into a chaptered audiobook or podcast**

[Download for Windows](https://chapterforge.app) - Free, no subscription required

ChapterForge takes a folder of MP3s and combines them into a single master file with chapters - the kind your podcast or audiobook app can navigate track by track. Point it at a folder, fill in a few details, press Build.

Built from the ground up for blind and low-vision users, with full screen reader support (NVDA, JAWS, Narrator) and keyboard-only navigation.

## Download and install

Visit **[chapterforge.app](https://chapterforge.app)** to download. Windows 10 and 11 are supported.

Two options are available:

- **Standard installer** - installs to Program Files with Start menu and desktop shortcuts
- **Portable** - runs from any folder or USB drive, no installation needed

## Getting started

1. Open ChapterForge from the Start menu or your desktop shortcut.
2. Choose a task from the startup wizard, or go to **File > Open Folder** and pick a folder of MP3s.
3. Review the chapter list - titles are filled in from your file names. Edit, reorder, or remove chapters as needed.
4. Fill in the book's title, author, and other details. A cover image found in the folder is picked up automatically.
5. Choose your output format (MP3, M4B, FLAC, or Opus) and where to save the file.
6. Press **Build** and ChapterForge puts everything together.

The built-in player lets you preview the result before you share or distribute it.

## What you can do

- **Build a chaptered audiobook or podcast** from a folder of MP3s
- **Works with all major players** - Apple Podcasts, Overcast, Pocket Casts, AntennaPod, VLC, foobar2000, AIMP, and more
- **Edit before you build** - adjust chapter titles, reorder tracks, and set the title, author, narrator, series, cover art, genre, and year
- **MP3, M4B, FLAC, or Opus output** - standard MP3 with chapter markers, Apple's M4B audiobook format with native chapters, lossless FLAC, or compact Opus
- **Preview in the built-in player** before you share
- **Fix existing chaptered files** - open a finished MP3 or M4B to correct chapters and tags without rebuilding from scratch
- **Look up metadata** - search MusicBrainz and Open Library to fill in title, author, narrator, and series
- **Check ACX compliance** - measure loudness, peak, and noise floor against ACX audiobook requirements, with a one-click loudness fix
- **Import and export chapter lists** - Audacity labels, CUE sheets, timestamp text, Podcasting 2.0 JSON, and CSV
- **Auto-chapter by silence** - ChapterForge can detect chapter breaks in a single long recording automatically
- **Generate a podcast RSS feed** alongside the audio for self-hosted shows
- **Background watcher** - set a folder to watch and ChapterForge builds new books automatically when you drop files in, with a Windows notification when it finishes
- **Updates built in** - checks for new versions and downloads the right installer in one click

## Accessibility

ChapterForge is designed first for blind and low-vision users:

- Every control has a visible label and a keyboard shortcut
- NVDA, JAWS, and Narrator all announce controls, status, and progress clearly
- High-contrast theme and adjustable text size available in Tools > Settings
- The app never blocks while building - you stay in control throughout

## Credits

ChapterForge is developed by **Blind Information Technology Solutions
(BITS)**, a community building accessible software. Explore our services:

- [Join BITS](https://www.joinbits.org)
- [Let It Glow](http://www.letitglow.app)
- [Community Access](https://www.community-access.org)

## License

ChapterForge is free and open source, released under the **MIT License** - see
[LICENSE](LICENSE). (c) 2026 Blind Information Technology Solutions (BITS).

ChapterForge uses FFmpeg for audio processing. If FFmpeg is not already on your
system, ChapterForge offers to download it automatically the first time you run
it (also available any time from Help > Download FFmpeg). See
[THIRD_PARTY.md](THIRD_PARTY.md) for license details and attributions.

## For developers

The codebase lives under `chapterforge/`. Build and release instructions are in
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md). Issues and pull requests are welcome
on [GitHub](https://github.com/BITS-ACB/chapterforge).
