# Control Reference

This page is generated from the same descriptions ChapterForge's in-app **Help on This Control** (press F1 on any focused control) shows you - it can't drift out of sync with what the app actually says. The live dialog tailors its wording to your current settings and the app's state at the moment you press F1; the examples below use the application's documented defaults instead, so this page reads sensibly on its own.

## Playback transport

### Play / Pause button

Starts or pauses playback of the loaded audio. Right now playback is stopped.

Currently on chapter 3 of 12: "Chapter Three".

### Stop button

Stops playback entirely and returns to the beginning of the loaded audio (unlike Pause, which keeps your place).

### Previous Chapter button

Jumps the player to the start of the previous chapter and keeps playing if it already was.

Currently on chapter 3 of 12: "Chapter Three".

### Next Chapter button

Jumps the player to the start of the next chapter and keeps playing if it already was.

Currently on chapter 3 of 12: "Chapter Three".

### Rewind button

Skips backward 10 seconds in the loaded audio. Change this amount in Settings under "Skip seconds".

### Forward button

Skips forward 10 seconds in the loaded audio. Change this amount in Settings under "Skip seconds".

### Playback position slider

Drag, or use the arrow keys, Page Up/Down, Home and End, to scrub to any point in the loaded audio.

Currently at 4:12 of 38:47.

Currently on chapter 3 of 12: "Chapter Three".

### Volume slider

Sets the player's playback volume, from 0 to 100 percent. Currently 80 percent. Your default starting volume (set in Settings) is 80 percent.

## Speed and export

### Playback speed

Currently set to 1x. Changes how fast the loaded audio plays back, from 0.5x (half speed) to 4.0x (quadruple speed), without changing its pitch.

Choosing a new speed re-encodes a temporary copy of the file, which takes a few seconds and temporarily disables this control. Use "Save at This Speed..." afterwards to keep a permanent copy at the new speed.

### Save at This Speed button

Writes a permanent copy of the loaded audio at its current playback speed (1x) to a file you choose. Only available once a speed other than the original has finished being applied.

## Trimming

### Set Trim Start button

Marks the player's current position as where the trimmed copy should begin. Trimming removes silence from the edges of the loaded audio before it's used elsewhere (e.g. saving a trimmed copy), without altering the original file.

### Set Trim End button

Marks the player's current position as where the trimmed copy should end. Trimming removes silence from the edges of the loaded audio before it's used elsewhere (e.g. saving a trimmed copy), without altering the original file.

### Clear Trim button

Removes both trim markers, restoring the full length of the audio. Trimming removes silence from the edges of the loaded audio before it's used elsewhere (e.g. saving a trimmed copy), without altering the original file.

### Pre-listen to Cut button

Plays back just the portion that trimming would remove, so you can check the markers before committing to them. Trimming removes silence from the edges of the loaded audio before it's used elsewhere (e.g. saving a trimmed copy), without altering the original file.

### Save Trimmed Copy button

Writes a new audio file containing only the portion between the trim markers. Trimming removes silence from the edges of the loaded audio before it's used elsewhere (e.g. saving a trimmed copy), without altering the original file.

## Chapter list

### Chapter list

Shows the 12 chapter(s) in the current project, one row per chapter. You're in build mode (you're assembling a new master from source files).

Select a row, then use the buttons or right-click / Menu key for what you can do with it - the choices change depending on whether you're building or editing.

### Chapter title field

Shows and edits the title of the selected chapter. Type a new title and press Enter, or move focus away, to apply it.

### Move Up button

In build mode, this moves the selected chapter one position earlier in the list, reordering the underlying source files (and therefore the audio) along with it. In edit mode the same button instead swaps just the chapter titles, leaving the audio in place.

In edit mode, this swaps the selected chapter's title with the one above it - the audio itself does not move, only the labels trade places. This is the more surprising of the two behaviours: in build mode the same button reorders the audio.

### Move Down button

In build mode, this moves the selected chapter one position later in the list, reordering the underlying source files (and therefore the audio) along with it. In edit mode the same button instead swaps just the chapter titles, leaving the audio in place.

In edit mode, this swaps the selected chapter's title with the one below it - the audio itself does not move, only the labels trade places. This is the more surprising of the two behaviours: in build mode the same button reorders the audio.

### Remove / Merge Up button

In build mode this button reads "Remove": it deletes the selected chapter, and its source audio file, from the project. In edit mode the same button instead reads "Merge Up" and merges the chapter into the one above it without discarding any audio.

In edit mode this button reads "Merge Up": it merges the selected chapter into the one immediately above it, removing the boundary between them (the combined audio stays - nothing is deleted). It's disabled when only one chapter remains, since there would be nothing left to merge into. In build mode the same button instead reads "Remove" and deletes the selected chapter (and its source file) from the project outright.

### Set Link & Image button

Opens a dialog to set the selected chapter's link URL and cover image. To rename the chapter itself, type directly into the title field instead - this button doesn't rename.

### Play Chapter button

Loads (if needed) and jumps the player to the selected chapter, then starts playing it immediately.

### Split Here button

Divides the chapter the player is currently inside into two chapters at the player's playhead position - not at whichever row happens to be selected in the list. The player is currently at 4:12. Only available in edit mode.

## Project

### Source folder field

Shows the folder or file ChapterForge is currently working with. Read-only - use File > Open Folder or File > Open Existing Master to change it.
