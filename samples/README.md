# ChapterForge sample / test files

`test.mp3` is a ready-to-use master built by ChapterForge so you can confirm
chapter markers display in your podcast / audiobook player.

It was built from the **ACB Braille Forum, June 2026** chapter recordings and
contains:

* **13 chapters** (titles taken from the source filenames),
* an ordered ID3v2 **CTOC** table of contents + one **CHAP** frame per chapter,
* ID3v2.3 tags (title, artist, album, album-artist, genre, year, comment),
* total running time ~1:25:09, assembled losslessly (no re-encode).

## How to test in a podcast client

1. Open `test.mp3` in a chapter-aware player, for example:
   * **Apple Podcasts** (drag into the Music/Podcasts app),
   * **Overcast**, **Pocket Casts**, **AntennaPod** (sideload),
   * **VLC** → Playback → Chapter menu,
   * **Foobar2000** with the Chapters component.
2. Confirm the player shows **13 chapters** and that selecting one jumps to it.
3. Confirm the title/artist/album metadata appears.

## Rebuilding it

The source recordings live in `..\ACB Braille Forum June 2026\` (the 13 files
named `01 …` through `13 …`). To rebuild from the command line:

```
chapterforge-cli "ACB Braille Forum June 2026" -o "samples\test.mp3" --title "The ACB Braille Forum, June 2026" --artist "American Council of the Blind" --genre Audiobook -y
```

Or open that folder in the ChapterForge GUI and build. ChapterForge
automatically skips the pre-existing full master
(`ACB Braille Forum June 2026.mp3`) so only the 13 chapter files are used.
