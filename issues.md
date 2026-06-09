# ChapterForge - Code Review Issues

> Comprehensive "spit and polish" review of the entire ChapterForge repository
> (Windows desktop app, CLI and background folder watcher).
>
> Scope: every source file under `chapterforge/` and `tests/`, every
> documentation file under `docs/`, the project-level `*.md`, the
> `requirements.txt` / `requirements-dev.txt` and the PyInstaller / installer
> config. Special attention to the binding accessibility contract documented
> in `CLAUDE.md`.
>
> Severity legend:
>
> * **P0** - bug, crash, data loss, accessibility blocker or security issue.
>   Fix before the next release.
> * **P1** - important UX, design or correctness issue. Fix in this milestone.
> * **P2** - polish, consistency, future-proofing. Fix when touching the file.
> * **P3** - nice-to-have. Track in the backlog.

---

## 3. Code quality / dead code (P1)

### 3.12 `app.py` is 7,361 lines, single file
- **File:** `chapterforge/app.py`.
- **Symptom:** Even with `ai/discovery.py` extracted, `app.py` still
  contains every dialog class (~30+ dialogs), the `MainFrame`, the
  `ChapterForgeApp`, and the `FFmpegSetupDialog`. A future change
  to one dialog risks breaking another via accidental import.
- **Fix:** Split into `chapterforge/app/frame.py` (the main frame +
  menus), `chapterforge/app/dialogs.py` (small dialogs),
  `chapterforge/app/ai_dialogs.py` (the AI dialogs), and
  `chapterforge/app/audio_dialogs.py` (the player + trim/speed
  dialogs). This is a refactor, not a fix; rate as P2.

---

## 10. Summary

| Severity | Count |
|----------|------:|
| P0       |     0 |
| P1       |     0 |
| P2       |     1 |
| P3       |     0 |
| **Total**| **1** |

**Remaining issue:**

1. **3.12** - `app.py` is 7,000+ lines - split into multiple files (P2 refactor).
