# ChapterForge Roadmap

This document captures planned and proposed enhancements to ChapterForge. Items
are grouped by rough horizon, not by strict release commitment. Feedback and
priorities are tracked on
[GitHub Issues](https://github.com/BITS-ACB/chapterforge/issues).

---

## Medium-term

These items are well-motivated but require more design or implementation work
before they are ready to build.

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

Revisit what would be needed for other areas as well here as much has changed in the product. Be complete as much as you can in your implementation. Keep code separated as much as possible for easier maintenance.

---

## Accessibility-specific improvements

- **Braille display optimization** - review all control labels and live regions for
  conciseness, since braille displays show far fewer characters per line than
  speech output reads per second.
