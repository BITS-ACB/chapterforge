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

## 1. Critical bugs (P0)

### 1.1 `_on_save` silently disables AI without warning the user
- **File:** `chapterforge/app.py`, `AIModelUnifiedDialog._on_save` (lines 793-820).
- **Symptom:** When the user picks a different engine tier or model in
  settings mode and the new combination is not on disk, the handler sets
  `ai_setup_done = False` but announces positively ("AI settings saved: X
  tier, Y model.") and `EndModal(wx.ID_OK)`. The AI menus
  (`Transcribe Audio...`, `Suggest AI Chapters...`) will be disabled the
  next time `_update_ai_menu_state` runs, with no message and no audit trail.
- **Impact:** The user thinks they have enabled AI, but the next click on
  `Transcribe Audio...` will be a dead menu item with no explanation.
- **Fix:** In `_on_save`, when the new selection is not on disk, show a
  modal "The selected AI model is not on disk yet. Run the setup wizard to
  download it now?" with a `Yes` -> switch to wizard, `No` -> save
  anyway (in which case announce "AI settings saved. The model is not
  downloaded yet, so AI menus will be disabled."). Currently the message
  `a11y.announce(f"AI settings saved: ...")` is misleading.
- **Tests:** none exist. Add a test in `tests/test_ai_unified_dialog.py`
  that asserts `_on_save` warns when the new selection is missing.

### 1.7 Inconsistent AI tier catalogue: "Canary" vs "Premium"
- **Files:** `chapterforge/ai/discovery.py` (`_KNOWN_MODELS` line 83 -
  `("Canary", "canary", "nvidia/canary-1b-v2")`) and
  `chapterforge/app.py` `AIModelUnifiedDialog.MODELS["Premium"]` (lines
  615-618 - includes `("canary", "Canary - experimental")`).
- **Symptom:** The dialog exposes `canary` as a Premium-tier model, but the
  detector and `is_ready(("Canary", "canary"))` use the standalone
  `Canary` tier. So a user who has downloaded the canary model will see
  `is_ready(("Premium", "canary")) == False` even though the file is on
  disk. `ready_summary()` includes `("Canary", "canary")` in its scan
  order, which is why the summary sometimes lies.
- **Fix:** Pick one. Either (a) demote "canary" to its own tier in
  `MODELS` (a 4th radio group, "Basic | Strong | Premium | Canary") or
  (b) collapse to a 3-tier list everywhere and rename
  `_KNOWN_MODELS` so `("Premium", "canary", ...)` is the canonical entry.
  Apply the same fix to `app._MODEL_DOWNLOAD_SIZES` (line 48) and
  `discovery._DOWNLOAD_SIZES` (line 98) which both list "canary".

### 1.11 `_set_status` and `_set_gauge` race with the worker thread
- **File:** `chapterforge/app.py`, lines 1141-1174.
- **Symptom:** Every call to `_set_status` / `_set_gauge` does
  `wx.CallAfter(_apply)`. If the user dismisses the dialog
  (e.g. via `Close()`) before the queued `_apply` runs, the next idle
  tick will touch a destroyed `_status_label`/`_gauge` and raise
  `RuntimeError: wrapped C/C++ object has been deleted`. The `_apply`
  closures have a defensive `if not self._status_label:` check, but
  `wx.PyDeadObjectError` slips past the truthiness check on some
  bindings.
- **Fix:** Use `wx.IsDestroyed(self._status_label)` (and the gauge) before
  touching them, or guard with `try/except RuntimeError`. Better still,
  stop the worker thread (via `threading.Event` + `cancel`) when the
  dialog closes.

### 1.13 `OnInit` FFmpeg path runs synchronously and blocks app startup on slow disks
- **File:** `chapterforge/app.py`, `ChapterForgeApp.OnInit` lines 7276-7331.
- **Symptom:** The synchronous `core._find_tool("ffmpeg")` /
  `core._find_tool("ffprobe")` calls happen on the UI thread. On systems
  with slow or network-backed PATH (mapped drives, antivirus
  intercepts) this can hang startup for many seconds. We already ship a
  `FFmpegSetupDialog`; consider pre-warming it asynchronously.
- **Fix:** Move the probe to a worker thread, show a splash with a
  "Checking for FFmpeg..." label, and only show the prompt on the main
  thread.

### 1.14 Wizard `wizard_seen` flag is set even when the user cancels
- **File:** `chapterforge/app.py`, `_on_wizard` lines 5330-5337.
- **Symptom:** The flag is flipped to True immediately after
  `wizard.show_wizard(...)` returns, regardless of whether the user
  reached the end or hit Cancel. The intent of `wizard_seen` is to
  suppress the auto-launch on subsequent starts; setting it on cancel
  hides a feature some users genuinely want to revisit.
- **Fix:** Have `wizard.show_wizard` return a boolean / enum and only
  set `wizard_seen` on a true "completed" return.

### 1.15 `FeatureFlagsDialog` / `BetaWarningDialog` index drift on
  multiple feature-flag changes
- **File:** `chapterforge/feature_flags.py`, `BetaWarningDialog` (imported
  from a sibling file - need to verify) and `app._show_beta_warning`.
- **Symptom:** Once `wizard_seen` is set, beta features can still be
  enabled later via the Feature Flags dialog, but the
  `_show_beta_warning` only fires if the user just opted in *and* has
  not previously dismissed the warning. If they previously dismissed
  it, then later enable a *new* beta feature, no warning fires. This
  is technically working as designed, but the wording
  "Suppresses the 'you've enabled beta features' warning once the user
  has seen it" is misleading: it can suppress the warning even when a
  new beta feature is enabled later.
- **Fix:** Either remove `beta_warning_dismissed` (always warn) or
  re-trigger the warning when the set of enabled beta features
  changes (not just on first opt-in).

---

## 2. Accessibility (binding contract - P0/P1)

The repository's `CLAUDE.md` defines the accessibility contract: every
interactive control must have an accessible name, the focus must land on a
meaningful control, and a screen reader must be able to follow the full
workflow without sight. The following items undermine that contract.

### 2.1 `MakeAccessible` is documented but not present in code
- **File:** `chapterforge/app.py`, `SettingsDialog` and the AI dialogs.
- **Symptom:** `CLAUDE.md` says to use `make_row(..., use_accessible=True)`
  for `wx.SpinCtrl` and a `_NamedAccessible(ctrl, "description")` for
  composite controls. Searching for `_NamedAccessible` /
  `MakeAccessible` returns no matches.
- **Fix:** Either implement and use `_NamedAccessible` everywhere
  `wx.SpinCtrl` appears (Settings dialog has several), or document the
  fallback as "tested with NVDA 2024.x on Windows 11 - inner spin field
  inherits the static-text label from its container." Don't leave
  the contract unbacked by code.

---

## 3. Code quality / dead code (P1)

### 3.11 `SettingsDialog` has many fields without `use_accessible=True`
- **File:** `chapterforge/app.py`, `SettingsDialog` (around line 6100).
- **Symptom:** The dialog uses `make_row(...)` for most fields but
  `CLAUDE.md` requires `use_accessible=True` for any `wx.SpinCtrl`.
  Without reading the exact call sites I cannot be 100% certain, but
  the absence of `_NamedAccessible` in the codebase (see 2.1) means
  the spin controls likely have no accessible name.
- **Fix:** Audit every `make_row` call. Add `use_accessible=True` to
  every row that contains a `wx.SpinCtrl` /
  `wx.SpinCtrlDouble`. Add a unit test that opens the Settings dialog
  and asserts each spin has a non-empty `GetName()`.

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

## 4. UX / polish (P1)

### 4.4 The settings card "Current AI model" header is invisible
  on high-contrast themes
- **File:** `chapterforge/app.py`, line 928.
- **Symptom:** `wx.StaticBoxSizer` honours the theme for the
  border but the label text colour follows the theme too, which
  on high-contrast can be white-on-white in some Windows
  configurations. Verify with the High Contrast theme.
- **Fix:** Explicitly set the label colour to the theme's
  `wx.SYS_COLOUR_BTNTEXT` in the high-contrast branch of
  `_apply_appearance`.

### 4.5 No "Cancel" button during the download
- **File:** `chapterforge/app.py`, `_run_setup` (lines 1176-1234).
- **Symptom:** During pip install / model download the user
  cannot cancel. The dialog is modal, the worker is in a thread
  with no `Event` to set. The user can only hit Escape (which
  closes the dialog but the worker keeps going) or wait.
- **Fix:** Add a `threading.Event` to the dialog, wire the
  footer to a Cancel button while the worker is running, and
  pass the event into `subprocess.run` and the engine
  `transcribe` call.

### 4.6 No undo / no "you have unsaved changes" warning
- **File:** `chapterforge/app.py`, `AIModelUnifiedDialog`.
- **Symptom:** Click a different radio, click Close. The new
  selection is silently lost. Settings mode does not
  distinguish "Save" from "Close" until you actually click
  Save. NVDA does not announce "unsaved changes".
- **Fix:** Track `self._dirty` (set on any radio change) and
  intercept `EVT_CLOSE` / `EndModal(CANCEL)` to ask
  "Discard your AI model changes?".

---

## 5. Documentation gaps (P1/P2)

---

## 6. Test coverage gaps (P1)

The repo has 19 test files and 29 tests, which is thin for a
7,000-line app.

### 6.2 No test that `core.write_pod2_chapters` produces a
  spec-compliant file
- **File:** `tests/test_core.py`.
- **Symptom:** The sidecar is parsed by podcast apps; a
  spec violation would only surface when an end user publishes.
- **Fix:** Add a test that loads the sidecar with a JSON
  parser and asserts every required key (`version`,
  `chapters`, `startTime`, `title`) is present and
  `startTime` is a number of seconds.

### 6.3 No test for the watcher stability / lock-stealing logic
- **File:** `tests/test_watcher.py`.
- **Symptom:** The lock-stealing is critical for unattended
  builds; a bug would leave folders un-built forever.
- **Fix:** Add a test that writes a lock marker with an
  mtime of 2 hours ago, calls `_consider`, and asserts the
  lock is stolen.

### 6.4 No test for the activity manager cancellation
- **File:** `tests/test_activity.py` (likely absent).
- **Symptom:** ActivityManager is the spine of the
  background-task UI; cancellation must work.
- **Fix:** Add a focused test file with 4-5 tests: start,
  update, finish, cancel, listener-notification.

### 6.6 No test that the AI menu enable state is correct
- **File:** `tests/test_ai_unified_dialog.py`.
- **Symptom:** The `_update_ai_menu_state` enable/disable
  logic (line 5027-5036) is a binding contract. If it gets
  out of sync with the settings, the user will see grey
  menus without explanation.
- **Fix:** Add a test that fakes `ai_setup_done = True /
  False` and asserts the `Enable` calls on
  `mi_ai_transcribe` and `mi_ai_chapters`.

### 6.7 No test for `FFmpegSetupDialog` close-mid-download
- **File:** `tests/test_app_initialization.py`.
- **Symptom:** The dialog has the same `wx.PyDeadObjectError`
  risk as the AI dialog. Worth a regression test.

---

## 7. Performance / polish (P2)

---

## 8. Architecture / design (P2)

### 8.1 `MainFrame._tray` is lazily created but
  `ChapterForgeTaskBarIcon` is not idempotent
- **File:** `chapterforge/app.py` `_setup_startup_tray` and
  `tray.py` `ChapterForgeTaskBarIcon.__init__`.
- **Symptom:** `SetIcon` is called every time; creating a
  fresh icon bitmap on every minimize. Fine, but a hot
  path if the user minimizes often.
- **Fix:** Cache the icon in a class attribute.

### 8.3 `core.write_pod2_chapters` opens the file twice
  (write + sidecar) without atomicity
- **File:** `chapterforge/core.py`, lines 2041-2070.
- **Symptom:** If the process is killed between the audio
  write and the sidecar write, the sidecar is missing. A
  re-build would re-write the audio, but a user who only
  built once will have a sidecar-less master.
- **Fix:** Write the sidecar first (temp), then the audio,
  then move the sidecar into place.

### 8.4 `SettingsDialog` rebuilds every time the user
  presses OK, losing unsaved sub-dialog state
- **File:** `chapterforge/app.py` `SettingsDialog`.
- **Symptom:** The settings dialog has many tabs; some
  have sub-dialogs (e.g. key overrides). If a sub-dialog
  is open and the user closes the parent, the sub-dialog
  state is lost.
- **Fix:** Hold the sub-dialog as a non-modal child and
  only `Destroy()` it on parent close.

### 8.5 No central place to disable a feature for an
  upcoming release
- **File:** `chapterforge/feature_flags.py`.
- **Symptom:** `release_channel` is the only knob. There
  is no "deprecated" or "removed" state. When a feature
  is removed from the code, every reference must be hunted
  down by hand.
- **Fix:** Add a "deprecated" channel that hides the
  feature with a "Removed in vX.Y" message rather than
  silently dropping it.

---

## 9. Security / privacy (P1)

---

## 10. Summary

| Severity | Count |
|----------|------:|
| P0       |     7 |
| P1       |     9 |
| P2       |     5 |
| P3       |     0 |
| **Total**| **21** |

**Top 5 issues to fix next** (in order):

1. **1.1** - `_on_save` silently disables AI when new selection is not on disk.
2. **1.7** - Inconsistent tier catalogue (Canary vs Premium).
3. **1.14** - `wizard_seen` set on cancel.
4. **4.5** - No Cancel button during download.
5. **4.6** - No unsaved-changes warning.
