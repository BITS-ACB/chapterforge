# ChapterForge Roadmap

This document captures planned and proposed enhancements to ChapterForge. Items
are grouped by rough horizon, not by strict release commitment. Feedback and
priorities are tracked on
[GitHub Issues](https://github.com/BITS-ACB/chapterforge/issues).

---

## Medium-term

These items are well-motivated but require more design or implementation work
before they are ready to build.

### Waveform display for silence detection

The auto-chapter by silence feature currently requires the user to set a threshold
and minimum gap and then trust that the detected breaks are correct. There is no
way to see where breaks were found before committing to them.

For sighted users, a waveform view showing the detected boundaries with the option
to drag them would make the feature far more trustworthy. For screen reader users,
the equivalent would be a navigable list of detected breaks with start time, gap
duration, and an accept/reject control for each - so every boundary can be
reviewed and corrected before the chapter list is populated.

---

## Long-term

These items are directional. They represent significant scope and some have open
design questions.

### macOS GUI port

The ChapterForge core - all file scanning, FFmpeg handling, chapter tagging, and
format conversion - is already cross-platform Python. The wxPython GUI also runs
on macOS. The platform-specific pieces are the system tray, Windows toast
notifications, and the Inno Setup installer.

Porting to macOS would make ChapterForge available to a substantial population of
blind Mac users who currently have no equivalent tool. The tray and notification
code would need macOS equivalents; the installer would need a replacement (likely
a signed .pkg or .dmg); and VoiceOver integration would need to be tested and
tuned.

### Cloud folder watching

The background watcher currently monitors local folders only. A significant
portion of audio production happens with files synced via OneDrive, Dropbox, or
Google Drive. Extending the watcher to treat the local sync folder for any of
these services as a watch target - or, more ambitiously, watching a cloud folder
directly via its API - would let ChapterForge fit into cloud-based production
workflows.

### Direct upload to distribution platforms

A finish-and-upload workflow - ACX check passes, build succeeds, file uploads to
ACX, Findaway Voices, or an S3-compatible bucket - would eliminate the manual
step of opening a browser and uploading. This depends on stable APIs from those
platforms and would need secure credential storage. It is a meaningful quality-of-
life improvement for high-volume producers.

---

## Accessibility-specific improvements

- **Braille display optimization** - review all control labels and live regions for
  conciseness, since braille displays show far fewer characters per line than
  speech output reads per second.
