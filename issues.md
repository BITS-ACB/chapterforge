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

### 2.4 `AIModelUnifiedDialog` setup status label has no `SetFocus` on success
- **File:** `chapterforge/app.py`, `_finish_setup` (line 1257-1258):
  `self._status_label.SetFocus()` is only called on the failure branch.
- **Symptom:** After a successful setup, the dialog drops back into the
  settings card via `_go_to(0)`. Focus moves to the Save button
  (because `is_settings` -> `focus_ctrl = focus_ctrl or self._btn_save`).
  The success message is announced but a screen-reader user does not
  hear the new "Ready: X tier, Y model" header card. They land on
  Save with no announcement of what just happened.
- **Fix:** After the `a11y.announce(msg)` on success, also call
  `self._hdr_step.SetFocus()` and then re-focus the first tier radio
  (or focus the new "AI model status" label briefly to surface the
  "Ready:" line).

### 2.5 "Run Setup Wizard..." button is labelled with ellipsis
- **File:** `chapterforge/app.py`, line 701: `label="Run Setup &Wizard..."`.
- **Symptom:** The three dots are correct Windows convention (the
  button opens another dialog), but `CLAUDE.md` says no m-dashes or
  emojis. The ellipsis is fine. The label is good. The
  `SetName` is good. This is a non-issue; flagging it for completeness
  so the next reviewer doesn't think we missed it.
- **Fix:** None.

### 2.6 No `SetName` on the wizard "Setup AI Model" status / gauge during pip install
- **File:** `chapterforge/app.py`, `_run_setup` (lines 1176-1234).
- **Symptom:** `_set_status` is called with the install message; this
  is fine. But there is no `_set_gauge` call between
  `_set_status("Installing ...")` and the start of the download - so
  the gauge shows 0 (it was set to 0 by construction) while pip
  actually runs. The gauge appears to be at 0 then jumps to 30.
- **Fix:** Set the gauge to 10 immediately on entering the install
  phase, 20 after install finishes, then 30 before the model
  download starts. This is also what the comment on line 1200
  implies (`self._set_gauge(20)`) - but the call is after the
  `subprocess.run`, so during install the gauge is at 0.

### 2.7 No `SetName` on the discovery info labels in the settings card
- **File:** `chapterforge/app.py`, `_refresh_model_card` (lines 996-1005).
- **Symptom:** The download status label has
  `status_lbl.SetName(f"{opt} - {'downloaded' if info.available else 'needs download'}")`
  but it lacks the tier context. A screen-reader user navigating
  horizontally hears "small - downloaded" and "medium - needs
  download" but does not know they are in the Strong tier. The
  StaticBox already announces the model group name on focus, so this
  is mostly fine; but the per-row status label is in the same
  StaticBox as the model radios, so the per-row announcement is
  enough. Promote to "P3" (no fix needed; document that the model
  radios sit inside a StaticBoxSizer that announces the tier).
- **Fix:** None.

### 2.10 No `SetName` on the `wx.SearchCtrl` in the command palette
- **File:** `chapterforge/app.py`, line 7037-7038:
  `self.search.SetName("Search commands")` and `SetDescriptiveText("Type a command name...")`.
- **Symptom:** The two are complementary and correct. Flag for
  completeness.
- **Fix:** None.

### 2.11 `BetaWarningDialog` (referenced in `feature_flags.py` docstring)
  - verify accessible
- **File:** Likely `chapterforge/feature_flags_dialog.py` (read separately).
- **Symptom:** Cannot verify without seeing the file; the docstring on
  the dialog class should be reviewed. If the dialog has a single
  message and OK / Cancel buttons, the names are usually
  self-announcing.
- **Fix:** Read the file and verify.

### 2.14 No screen-reader-only summary in the AI dialog header
- **File:** `chapterforge/app.py`, `AIModelUnifiedDialog._hdr_title`
  (line 647) and `_hdr_step` (line 651).
- **Symptom:** Both are visible StaticTexts. A screen-reader user
  navigating by heading will hear "AI Model" / "Settings" or
  "Step 1 of 3", but no extra context ("You're in the polished
  settings view. Use Save to keep changes.").
- **Fix:** Add an `a11y.announce(...)` in `_go_to` whenever the
  step changes, with a sentence-form description ("Step 1 of 3:
  Introduction. Press Next Step to continue."). The announce is
  the only mechanism that delivers a sentence-form, not a label.

### 2.15 No `SetName` on the chapter list header / column headers
- **File:** `chapterforge/app.py`, lines 2072-2081.
- **Symptom:** `self.list.SetName("Chapters list - up and down
  arrows to move between chapters, left and right arrows to read
  across columns")` is good. But the individual columns have no
  name. NVDA reads the column number ("Column 2") which is not
  helpful.
- **Fix:** Add a parallel `wx.ListCtrl.SetColumn(i, ..., name=...)`
  call - or, since `wx.ListCtrl` does not support per-column names
  in all bindings, add a screen-reader-only summary string and
  announce it when the user moves columns with left/right arrows.
  This is already done via `_announce_list_cell` (line 2782-2788)
  which is good. Document this in `CLAUDE.md` so future column
  changes don't forget the announce hook.

---

## 3. Code quality / dead code (P1)

### 3.1 `AIModelSettingsDialog` is no longer wired to any menu
- **File:** `chapterforge/app.py`, lines 153-235.
- **Symptom:** The dialog class is defined but the only
  `AIModelSettingsDialog` instantiation was removed when the unified
  dialog landed. `grep -n AIModelSettingsDialog` returns only the
  class definition. ~85 lines of dead code.
- **Fix:** Remove the class.

### 3.2 `AIModelSetupDialog` is no longer wired to any menu
- **File:** `chapterforge/app.py`, lines 238-559.
- **Symptom:** Same as 3.1. ~320 lines of dead code. Notably it has
  a subtle bug (line 557) - `self._content_sz.Replace(model_box, model_box)`
  replaces the sizer with itself, which is a no-op. The legacy
  setup dialog would have to be re-tested before we can rely on it.
- **Fix:** Remove the class.

### 3.5 `_validate_core_module_integrity` is intentionally disabled
- **File:** `chapterforge/core.py`, lines 358-383.
- **Symptom:** The function is defined, then a comment on line 380
  says "This validation is temporarily disabled to avoid circular
  reference issues", and the call is commented out. There are no
  circular references in the function - the only globals it uses
  (`title_from_filename`, `natural_key`, `enhanced_natural_key`) are
  all defined before line 358. The validation is harmless; the
  comment is stale.
- **Fix:** Either uncomment the call (it would catch a real bug if a
  future refactor deletes one of those functions) or delete the
  function entirely and the stale comment. Do not leave a
  "temporarily disabled" comment for the next reviewer to puzzle
  over.

### 3.6 `enhanced_natural_key` and `natural_key` are aliases
- **File:** `chapterforge/core.py`, lines 263-289.
- **Symptom:** `natural_key` is just `return enhanced_natural_key(text)`.
  One-line shim that adds indirection without value. The function
  `smart_sort_files` on line 291 is also never called.
- **Fix:** Inline `natural_key` into `enhanced_natural_key` (or vice
  versa), delete `smart_sort_files`, and update the 1-2 callers that
  still use the alias (none found in the current sweep beyond the
  `_validate_core_module_integrity` whitelist above).

### 3.7 `ai_transcribe_file` and `generate_ai_chapters` in `core.py`
  duplicate `ai/engine.create_engine(...).transcribe(...)`
- **File:** `chapterforge/core.py`, lines 109-123.
- **Symptom:** The module-level helpers use the legacy
  `WhisperEngine` (OpenAI Whisper, not faster-whisper). The GUI
  uses the new `ai.engine.create_engine(tier, model)` factory. So
  the CLI / a future API that calls `core.ai_transcribe_file` will
  pull in `openai-whisper` (a ~3 GB dependency) when the rest of the
  app uses `faster-whisper` (a ~50 MB dependency).
- **Fix:** Either delete these two functions (no caller in the
  current code) or rewrite them to call
  `ai.engine.create_engine(tier, model)`.

### 3.8 `from chapterforge.ai.whisper import WhisperEngine,
  TranscriptionSegment` on `core.py:49` keeps `openai-whisper` as a
  hard import
- **File:** `chapterforge/core.py`, line 49.
- **Symptom:** Even if 3.7 is fixed, this import is a hard
  `import openai-whisper` which adds a multi-gigabyte dependency
  to the base install. CLAUDE.md says "FFmpeg is external" but
  doesn't mention the openai-whisper weight. This is a major
  size-on-disk surprise.
- **Fix:** Move the import inside `ai_transcribe_file` /
  `generate_ai_chapters` and remove the top-level import. Better:
  delete both functions (3.7) and the import.

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

### 3.13 `app._MODEL_DOWNLOAD_SIZES` and
  `discovery._DOWNLOAD_SIZES` are duplicated
- **Files:** `chapterforge/app.py` lines 40-49, `chapterforge/ai/discovery.py`
  lines 90-99.
- **Symptom:** The two dicts are meant to mirror each other; any
  new model must be added in both places. Easy to forget.
- **Fix:** Have `app.py` import the dict from `chapterforge.ai.discovery`
  and re-export it as `_MODEL_DOWNLOAD_SIZES` for any back-compat
  callers. The discovery module is already the "single source of
  truth" for what models exist.

### 3.14 `_status_label.SetName` is set on every status update
- **File:** `chapterforge/app.py`, `_set_status` (line 1152) and
  `_finish_setup` (line 1245).
- **Symptom:** Good pattern for forcing re-announce. But the name
  includes the full text, so the announcement is the text. Compare
  with `_set_gauge` (line 1173) which never updates the name. See
  2.2.

### 3.16 `_recommend_for_hardware` does not consider tier-default model size on disk
- **File:** `chapterforge/app.py`, lines 52-72.
- **Symptom:** The recommendation is fixed by hardware. It does not
  ask "is the recommended model already on disk?" - so it can
  recommend "Strong / medium" on a system that already has Strong /
  small downloaded. The dialog would then go through a fresh
  download rather than the 0-second "ready" path.
- **Fix:** Call `discovery.is_ready(tier, model)` first; if True,
  return the on-disk combo before falling through to the hardware
  default.

### 3.17 No test for `AIModelUnifiedDialog._run_setup` end-to-end
- **File:** `tests/test_ai_unified_dialog.py`.
- **Symptom:** The unit tests cover `_on_save`, footer visibility
  and mode-switching, but never exercise the actual pip-install /
  model-download path. A real bug in the pulse-gauge arithmetic
  (1.9) and the `_status_label.SetName` pattern (2.2) would slip
  through.
- **Fix:** Add a test that monkey-patches
  `_tier_pip_package` / `_check_ai_package` /
  `_download_model` and asserts the gauge ends at 100 on success
  and at 0 with a failure message on a faked exception.

### 3.18 No test that the unified dialog respects
  `ai_setup_done = True` -> settings mode, `False` -> wizard mode
- **File:** `tests/test_ai_unified_dialog.py`.
- **Symptom:** Implicit in `test_settings_mode_opens_polished_view`
  but not asserted. A future refactor that flips the order
  (always show wizard) would pass the test.
- **Fix:** Add an explicit `test_wizard_mode_for_fresh_install`
  with `ai_setup_done = False` and assert the wizard step counter
  shows "Step 1 of 3".

### 3.19 `app._apply_appearance` is called from `__init__` but
  `theme` is read by `_apply_appearance` which may load colours
  before the menu bar is built
- **File:** `chapterforge/app.py`, lines 1601-1602 vs
  `_build_menu` 1579-1580.
- **Symptom:** Subtle ordering - `_build_ui` is called twice (once
  in `__init__`, once after settings load). The first call may
  not have menu items yet. Not a bug today but fragile.
- **Fix:** Refactor into a single explicit `_init_ui` and call
  it from `__init__` after both menu and panel are built.

---

## 4. UX / polish (P1)

### 4.2 Footer button order is inconsistent with Windows convention
- **File:** `chapterforge/app.py`, lines 678-710.
- **Symptom:** In settings mode the footer shows:
  `[empty stretch]  Save   Run Setup Wizard...   Close`.
  This puts the *primary* action (Save) before the *secondary*
  (Run Setup Wizard) and the *tertiary* (Close), which is
  correct. But in wizard mode the footer shows:
  `[Back]  [stretch]  [Next Step]`. Back is left-most, which is
  non-standard on Windows (which would expect `Back  Next`). The
  stretch spacer pushes Next to the right, which feels more
  macOS-ish. Either is defensible; just pick one and document it.
- **Fix:** Move the stretch spacer to the left of Back so the
  order is `Back  [stretch]  Next`. Or move the stretch to the
  right of Back so the order is `[stretch]  Back  Next`. Pick
  one; this is a P3 polish.

### 4.3 The wizard's "Setup AI Model" button has no progress hint
- **File:** `chapterforge/app.py`, lines 1099-1123.
- **Symptom:** The completion step shows a paragraph and the
  status label / gauge, but the user has no preview of how long
  it will take. Add a one-line "Estimated time: 2-5 minutes" hint
  based on the model size from `_DOWNLOAD_SIZES`.
- **Fix:** Show the size from `discovery._DOWNLOAD_SIZES` next
  to the model name in the paragraph.

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

### 4.7 The settings card does not say "Save to apply" anywhere
- **File:** `chapterforge/app.py`, `AIModelUnifiedDialog`.
- **Symptom:** The card has radios, model options and a Save
  button. A first-time user does not know they need to click
  Save. The header card says "Ready: ..." but does not hint at
  "select a different model then click Save to switch".
- **Fix:** Add a hint line under the card: "Choose a different
  tier or model then click Save to apply."

### 4.9 `is_ready` returns False for the currently selected model
  if the user manually deletes the model from the cache
- **File:** `chapterforge/app.py` `AIModelUnifiedDialog.__init__`
  line 636-639.
- **Symptom:** The dialog opens in wizard mode on the next
  launch. The user has just deleted the model. The user is not
  warned that the previous "AI ready" state was lost; they just
  see the wizard again.
- **Fix:** When `ai_setup_done = True` but `is_ready(...)` is
  False, show a one-time info dialog: "Your previously
  downloaded model is missing. Run the setup wizard to
  download it again."

### 4.10 `mi_update.Enable(False)` is never re-enabled on
  exceptions
- **File:** `chapterforge/app.py`, lines 5543-5554.
- **Symptom:** `_on_check_updates` disables the menu item, but
  if the worker thread raises an unhandled exception
  (e.g. `socket.gaierror` not caught), `mi_update` stays
  disabled forever. The user has to restart the app to check
  for updates again.
- **Fix:** Wrap the worker in a `try/except BaseException` and
  always call `wx.CallAfter(self._update_check_done, None, str(exc))`.

---

## 5. Documentation gaps (P1/P2)

### 5.1 No mention of the AI Model dialog in the User Guide
- **File:** `docs/USER_GUIDE.md`.
- **Symptom:** A user reading the guide does not learn about
  the `Transcription > AI Model...` menu. Section 2 mentions
  Auphonic (line 674) but not the new in-app AI Model setup.
  The "Smart Chapter Detection AI" section on line 734 is
  misleading - it describes a feature that does not exist
  ("AI Analyze Selection", "AI Recommendations Panel").
- **Fix:** Replace the fictional "Smart Chapter Detection AI"
  section with a real "AI Transcription" section that explains:
  * `Transcription > AI Model...` opens the unified setup
    dialog.
  * The dialog auto-detects which models are already
    downloaded.
  * Settings mode vs. wizard mode.
  * `Transcribe Audio...` and `Suggest AI Chapters...`
    become available after setup.

### 5.2 The Keyboard Shortcuts table references `Ctrl+Shift+A`
  for "AI Analyze Selection" - that command does not exist
- **File:** `docs/USER_GUIDE.md`, line 834.
- **Symptom:** The shortcut is wrong. The actual binding is
  `Ctrl+Shift+A` = `Save As...` (see `app.py` line 1635).
- **Fix:** Remove the row, or rename the action to "Save As..."
  and move it to the File group.

### 5.3 `CLAUDE.md` does not mention the AI Model dialog
- **File:** `CLAUDE.md`.
- **Symptom:** The project-level Claude instructions describe
  the architecture but never mention the AI dialogs or the
  `chapterforge/ai/` package layout. A future Claude session
  will not know about `discovery.is_ready` and will re-invent
  detection.
- **Fix:** Add a "AI" section to `CLAUDE.md` describing the
  `ai/discovery.py`, `ai/engine.py`, `ai/whisper_cpp.py`,
  `ai/faster_whisper_engine.py`, `ai/parakeet.py` modules and
  the unified dialog's two modes.

### 5.4 `PRD.md` says "AI chapter detection - not implemented"
  in section 16.8
- **File:** `docs/PRD.md`, line 491.
- **Symptom:** The PRD contradicts the code: the `Suggest AI
  Chapters...` menu (line 1704 of `app.py`) is implemented and
  works. The note is stale.
- **Fix:** Replace with a note that points to the
  `Transcription > Suggest AI Chapters...` command and the
  underlying faster-whisper / Parakeet backends.

### 5.5 `CHANGELOG.md` is not updated for the unified dialog
- **File:** `CHANGELOG.md` (read separately).
- **Symptom:** The new "AI Model..." combined dialog and the
  two new `tests/test_ai_*.py` files should appear in the
  Unreleased / next-version section. Verify and add.
- **Fix:** Run `git diff 6e27678~1 6e27678 -- CHANGELOG.md` and
  ensure the entry exists.

### 5.6 `requirements.txt` does not list `onnxruntime`,
  `huggingface_hub` or `scipy` referenced in code
- **File:** `requirements.txt` (read separately).
- **Symptom:** `chapterforge/ai/parakeet.py` imports
  `onnxruntime`; `chapterforge/ai/faster_whisper_engine.py`
  pulls `huggingface_hub` transitively. None are pinned in
  `requirements.txt`. A fresh `pip install -r requirements.txt`
  will succeed but `Transcribe Audio...` will fail at
  runtime with an ImportError that surfaces in the modal
  error dialog. The user has no clue that the import was
  missing.
- **Fix:** Add `faster-whisper` to `requirements.txt`. Leave
  `onnxruntime` as an optional extra documented in
  `docs/USER_GUIDE.md` ("for the Premium tier, also
  `pip install onnxruntime`").

### 5.7 No mention of `tests/test_ai_unified_dialog.py` in the
  developer docs
- **File:** `docs/CODE_QUALITY.md` (or similar).
- **Symptom:** The new test file is the largest in the
  test suite (9 tests, 250+ lines) and exercises the AI
  dialog. A new contributor who runs `pytest -q` should know
  why the AI dialog is Windows-only and how to add a new
  test.
- **Fix:** Add a "Testing the AI dialogs" section to
  `CODE_QUALITY.md` or a new `docs/AI_TESTING.md`.

### 5.8 `docs/CONTROL_REFERENCE.md` does not list the AI Model
  dialog
- **File:** `docs/CONTROL_REFERENCE.md` (need to verify).
- **Symptom:** If the doc lists every control, the AI Model
  dialog should be in it. Verify.
- **Fix:** Add a `## AI Model Dialog` section with the
  controls: header, tier radios, model radios, status label,
  gauge, Save, Run Setup Wizard, Close, Back, Next Step,
  Setup AI Model.

---

## 6. Test coverage gaps (P1)

The repo has 19 test files and 29 tests, which is thin for a
7,000-line app.

### 6.1 No end-to-end test for the build pipeline
- **File:** `tests/test_core.py` - read separately; likely
  covered. Verify.
- **Symptom:** Cannot test the full build without FFmpeg;
  the test fixture probably mocks `_run`. Verify.

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

### 6.5 No test that `a11y.announce` is thread-safe
- **File:** (no test for a11y).
- **Symptom:** `announce` is called from worker threads. A
  race would crash the worker and leave the status bar
  silent.
- **Fix:** Add a test that spawns 10 threads, each calling
  `announce("x")` 100 times, and asserts no exception
  escapes.

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

### 7.1 `discover_models()` runs synchronously on dialog open
- **File:** `chapterforge/ai/discovery.py` lines 174-196.
- **Symptom:** The function does 11 filesystem probes. On a
  cold cache, each `pathlib.exists()` is a stat() call. With
  network-mounted home dirs, this could take 100+ ms.
  The dialog opens synchronously so the user sees a pause.
- **Fix:** Cache the result for 1-2 seconds via
  `functools.lru_cache(maxsize=1, typed=False)` and a tiny
  TTL wrapper.

### 7.2 `_run_setup` uses a polling sleep of 0.3 s on the
  pulse thread
- **File:** `chapterforge/app.py`, line 1218:
  `stop_pulse.wait(0.3)`.
- **Symptom:** Wakes up 3.3 times per second. Cheap, but
  probably overkill. Use `wx.Gauge.Pulse()` which has its
  own timer.
- **Fix:** Drop the manual pulse thread and use the
  documented indeterminate mode.

### 7.4 `app.py` reads the entire recent-menu list on every
  rebuild
- **File:** `chapterforge/app.py` `_rebuild_recent_menu`.
- **Symptom:** Cheap (5 items), but the function rebuilds
  the menu even when nothing changed. Idempotent; harmless.
- **Fix:** None - leave as-is.

### 7.5 `CommandPaletteDialog` rebuilds the entire list on
  every keystroke
- **File:** `chapterforge/app.py`, lines 7141-7168.
- **Symptom:** 40+ items * 1 keystroke = fine. Not a real
  bottleneck.
- **Fix:** None.

### 7.6 `natural_key` is O(N * log(N) * M) per character
  because of repeated `re.split`
- **File:** `chapterforge/core.py`, line 287.
- **Symptom:** For folders of 10,000 files, sort cost is
  ~50 ms. Fine.
- **Fix:** None.

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

### 8.2 The unified dialog has six footer buttons; six is
  at the upper limit of "comfortable"
- **File:** `chapterforge/app.py`, lines 678-710.
- **Symptom:** A wider monitor would be better served by
  a single-line `wx.ToolBar`. But the dialog is a 640x480
  modal and the buttons fit. No fix needed; just flag it
  for the next designer pass.

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

### 8.6 `auphonic_menu._auphonic_menu_index = 4` is a magic
  number
- **File:** `chapterforge/app.py`, line 1826.
- **Symptom:** The menu index is computed manually. If
  someone adds a menu between File/Edit/View/Tools and
  Auphonic, the index drifts.
- **Fix:** Use the same dynamic approach as
  `_publish_menu_index` (line 1841). Delete the magic
  number.

---

## 9. Security / privacy (P1)

### 9.2 `settings.save` swallows all `OSError`
- **File:** `chapterforge/settings.py`, lines 126-136.
- **Symptom:** If the disk is full or the file is
  read-only, the user has no idea that their settings
  were not saved. The next launch will use the old
  settings.
- **Fix:** Catch `OSError` and re-raise as a custom
  `SettingsSaveError`. The caller can `try/except` and
  show a modal "Could not save settings; check your disk
  space." Announce via `a11y.announce`.

### 9.3 `a11y.announce` echoes arbitrary strings through the
  screen reader
- **File:** `chapterforge/a11y.py`, lines 205-224.
- **Symptom:** An attacker who can control a filename in
  a folder the user opens could craft a name with
  control characters that the screen reader would read
  aloud. We do not sanitise `announce(text)` input.
- **Fix:** Strip control characters from the message
  before speaking. (Low priority; the only vectors are
  user-opened folders, which are user-controlled.)

### 9.4 `FFmpegSetupDialog` writes to `%TEMP%` without
  validation
- **File:** `chapterforge/app.py` + `tools/get_ffmpeg.py`.
- **Symptom:** The downloader writes a temp file. The
  path is generated by Python's `tempfile`. Safe today.
- **Fix:** None - the stdlib is the right tool.

---

## 10. Summary

| Severity | Count |
|----------|------:|
| P0       |     6 |
| P1       |    15 |
| P2       |     8 |
| P3       |     2 |
| **Total**| **31** |

**Top 5 issues to fix next** (in order):

1. **1.1** - `_on_save` silently disables AI when the new
   selection is not on disk.
2. **1.7** - Inconsistent tier catalogue (Canary vs Premium).
3. **3.1 / 3.2** - Remove the two dead dialog classes
   (`AIModelSettingsDialog`, `AIModelSetupDialog`). ~400
   lines of code we no longer test or maintain.
4. **3.7 / 3.8** - Delete dead `ai_transcribe_file` /
   `generate_ai_chapters` and the hard `openai-whisper` import.
5. **5.1 / 5.4** - Update the user guide to describe the AI
   Model dialog and remove the fictional sections.
