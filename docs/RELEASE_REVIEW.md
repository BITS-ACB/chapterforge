# ChapterForge Release Review

A single review sheet covering the pre-release audit. Part A is what has been
fixed and verified. Part B is what still needs work, split into "improve"
(parity / clarity gaps) and "enhance" (new capability). Each item lists where it
lives and roughly how much effort it is.

Tests at time of writing: 127 passed, 1 skipped. Nothing has been committed.

For the narrative version with code detail, see `PRE_RELEASE_AUDIT.md`.

---

# Part A - Needs work

## A1 - Enhance (new capability / polish)

| # | Item | Priority | Effort | Where |
|---|------|----------|--------|-------|

| B2.1 | **app.py is ~5,400 lines** with no GUI unit tests. Stage a split (dialogs -> modules, then player wiring, then settings UI) and add a CI linter. Post-1.0. | Medium | Large | `app.py` |
| B2.2 | **Cancel buttons** for the FFmpeg download and the metadata search (now async but not cancellable). | Low | Small | `app.py` |
| B2.3 | **Opus size estimate** uses MP3-bitrate math; make it VBR-aware. (FLAC already shows "lossless".) | Low | Small | `app.py`, `core.py` |
| B2.4 | **Cover art** limited to JPEG/PNG; widen to WebP or auto-convert. | Low | Small | `core.py` |
| B2.5 | **Lookup result quality.** MusicBrainz returns no genre; Open Library genre is the raw first subject (noisy). Map/clean subjects. | Low | Medium | `lookup.py` |
| B2.6 | **RSS is single-episode** with crude season/episode values. Fine for "one book = one feed"; document the scope or grow into a multi-episode manager. | Low | Medium | `rss.py` |
| B2.7 | **Parametrize the loudnorm target** through `build_master` so FLAC/M4B can also hit ACX-style targets if ever needed. | Low | Medium | `core.py` |

---

# Recommended order to release

1. Spot-check A1/A2 against the live services with real titles (the tests cover
   query/markup shape, not remote responses).
2. Smoke-test the watcher end to end (A10): drop a folder with a `.flac`/`.opus`
   template and per-file-normalize on, confirm the sidecars and format.
3. Add a linter to CI to keep the package pyflakes-clean (it is clean now).
4. Tackle the Part B "Enhance" items as post-1.0 polish; B2.1 (app.py split) is
   the main longer-term investment.

# Re-run checks

```
python -m pytest -q
python -m pytest tests/test_lookup_rss.py -q
python -m pyflakes chapterforge/
```


