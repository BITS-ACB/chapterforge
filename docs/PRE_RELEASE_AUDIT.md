# ChapterForge Pre-Release Code Audit

A deep review of the codebase ahead of the 1.0.0 release. This document records
what was fixed during the audit, the gaps and rough edges that remain, larger
design considerations, and a recommended path to a confident release.

Status legend: [Fixed] done in this pass - [High] / [Medium] / [Low] remaining
work, by priority and risk.

---

## 1. Rough user-experience edges

- **[Resolved] Two overlapping normalization systems.** The generic `normalize`
  and `per_file_normalize` + `normalize_lufs` controls are now clearly labeled
  ("option 1 of 2 / 2 of 2"), made mutually exclusive (per-chapter wins) in the
  GUI, watcher and CLI so they never double-process, and the LUFS help notes the
  ACX -23 target. A full single-control redesign is still possible later but the
  confusion is addressed.
- **[Low] No cancel on the FFmpeg download or the metadata search.** Both are
  now non-blocking-ish, but a user who started them cannot back out. A Cancel
  button would help on slow or stuck networks.
- **[Low] Opus size estimate is approximate.** The Tags-panel estimate uses
  MP3-bitrate math for Opus; FLAC now correctly shows "lossless (actual size
  varies)." Opus could use a VBR-aware estimate.
- **[Low] Cover art is limited to JPEG/PNG.** `find_cover` and APIC embedding
  ignore common formats like WebP. Either auto-convert or widen support.
- **[Low] MusicBrainz results have no genre, and Open Library genre is the
  first raw subject** (often noisy, e.g. "Fiction, English"). Result quality
  could be improved by mapping/cleaning subjects.

---

## 2. Design / architecture observations

- **[Medium] `app.py` is ~5,400 lines.** The GUI, all dialogs, the build
  orchestration glue, and the app bootstrap live in one file. This makes review
  and testing hard and is the main source of merge friction. A staged split
  (dialogs -> their own modules, then the player wiring, then settings UI) would
  pay for itself. None of the GUI logic currently has unit tests.
- **[Resolved] Dead code / unused imports.** `validation.py` has been deleted
  and the package is now pyflakes-clean. Adding a linter to CI would keep it that
  way.
- **[Low] RSS is single-episode.** `generate_rss` emits one `<item>` and crude
  season/episode values. It is fine for "one audiobook = one feed," but it is
  not a multi-episode feed manager; document the intended scope so expectations
  are set.
- **[Info] ACX re-encode target.** The generic `normalize` re-encode is fixed at
  I=-16. Only the MP3 per-file path can hit -23 LUFS. Since ACX submissions are
  MP3, this is acceptable, but if FLAC/M4B ever need ACX-style targets the
  loudnorm target should become a parameter threaded through `build_master`.

---

## 3. Recommended path to release

Ordered by value-to-effort. Sections 1 and 2 are done; these are what is left.

1. **Verify the lookup and RSS fixes against the live services** with a couple
   of real titles (the unit tests cover the query/markup shape, not the remote
   responses).
2. **Smoke-test the watcher end to end** - drop a folder with a `.flac`/`.opus`
   output template and per-file normalize enabled, and confirm the format and
   sidecars (RSS / Podcasting 2.0).
3. **Add a linter to CI** to keep the package pyflakes-clean (it is clean now).
4. **Plan the `app.py` split** (section 4) as a post-1.0 refactor so it does not
   block the release but is not forgotten.

## 6. How to re-run the checks

```
python -m pytest -q                 # full suite (currently 127 passed, 1 skipped)
python -m pytest tests/test_lookup_rss.py -q   # the new regression tests
python -m pyflakes chapterforge/    # unused imports / obvious issues
```
