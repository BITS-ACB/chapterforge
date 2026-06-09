"""Unit tests for the unified AI Model dialog.

These tests construct ``AIModelUnifiedDialog`` directly (without calling
``ShowModal``) and exercise:

* mode auto-detection (settings vs wizard),
* footer button visibility per step,
* the mode-switch hot path (settings -> wizard),
* ``_on_save`` writes the right settings keys and sets
  ``ai_setup_done=False`` when the chosen model is not on disk,
* every control carries an accessible name (``SetName``) or a fully
  descriptive ``label=`` so screen readers announce it.

GUI tests require Windows; on other platforms they are skipped (mirrors
``test_app_initialization.py``). The tests redirect ``Path.home`` and
the HuggingFace env vars into ``tmp_path`` so they never touch the
real on-disk cache.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# wxWidgets import: skip the whole module on non-Windows / no display.
pytestmark = pytest.mark.skipif(
    os.environ.get("CI") == "true" or os.name != "nt",
    reason="GUI tests require Windows with display",
)


@pytest.fixture(scope="module")
def wx_app():
    import wx
    app = wx.App()
    yield app
    app.Destroy()


@pytest.fixture()
def frame(wx_app):
    import wx
    f = wx.Frame(None)
    yield f
    f.Destroy()


@pytest.fixture()
def fake_home(monkeypatch, tmp_path):
    """Point both ``Path.home`` and the HF env vars at *tmp_path*."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def _make_faster_whisper_repo(home: Path, model: str = "small") -> Path:
    """Drop a fake faster-whisper repo into the flat HF cache layout."""
    repo = home / ".cache" / "huggingface" / (
        "models--Systran--faster-whisper-" + model
    ) / "snapshots" / "main"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "config.json").write_text("{}", encoding="utf-8")
    return home / ".cache" / "huggingface" / (
        "models--Systran--faster-whisper-" + model
    )


def _sizer_state(dlg) -> dict:
    """Read each footer button's sizer-item IsShown flag."""
    foot = dlg._footer_sizer
    state = {}
    for n in ("back", "next", "setup", "save", "wizard", "close"):
        btn = getattr(dlg, f"_btn_{n}")
        # Find the sizer item that owns this button.
        for i in range(foot.GetItemCount()):
            item = foot.GetItem(i)
            try:
                if item.GetWindow() is btn:
                    state[n] = item.IsShown()
                    break
            except Exception:
                pass
        else:
            state[n] = None
    return state


# ---------------------------------------------------------------------------
# Mode detection
# ---------------------------------------------------------------------------


def test_settings_mode_when_model_on_disk(fake_home, frame):
    """If a model is on disk the dialog opens in settings mode (1 step)."""
    _make_faster_whisper_repo(fake_home, "small")
    from chapterforge.app import AIModelUnifiedDialog

    dlg = AIModelUnifiedDialog(
        frame,
        {"ai_engine_tier": "Strong", "ai_model_name": "small",
         "ai_setup_done": False},
    )
    try:
        assert dlg._has_model is True
        assert len(dlg._steps) == 1
        # ``_steps`` is a list of bound methods; compare by underlying
        # function. The methods on ``dlg`` are the canonical identity:
        # we look up the function attribute directly on the class.
        from chapterforge.app import AIModelUnifiedDialog as Cls
        assert dlg._steps[0].__func__ is Cls._make_settings_step
        # Header reads "Settings", not "Step N of M".
        assert dlg._hdr_step.GetLabel() == "Settings"
    finally:
        dlg.Destroy()


def test_wizard_mode_when_nothing_on_disk(fake_home, frame):
    """Empty cache + ai_setup_done=False must open the 3-page wizard."""
    from chapterforge.app import AIModelUnifiedDialog

    dlg = AIModelUnifiedDialog(
        frame,
        {"ai_engine_tier": "Strong", "ai_model_name": "small",
         "ai_setup_done": False},
    )
    try:
        assert dlg._has_model is False
        assert len(dlg._steps) == 3
        from chapterforge.app import AIModelUnifiedDialog as Cls
        assert dlg._steps[0].__func__ is Cls._make_intro_step
        assert dlg._steps[1].__func__ is Cls._make_selection_step
        assert dlg._steps[2].__func__ is Cls._make_completion_step
        # Wizard header says "Step 1 of 3".
        assert dlg._hdr_step.GetLabel() == "Step 1 of 3"
    finally:
        dlg.Destroy()


# ---------------------------------------------------------------------------
# Footer button visibility
# ---------------------------------------------------------------------------


def test_settings_mode_buttons(fake_home, frame):
    """Settings mode shows Save / Run Setup Wizard / Close, hides the rest."""
    _make_faster_whisper_repo(fake_home, "small")
    from chapterforge.app import AIModelUnifiedDialog

    dlg = AIModelUnifiedDialog(
        frame,
        {"ai_engine_tier": "Strong", "ai_model_name": "small",
         "ai_setup_done": True},
    )
    try:
        # The dialog's __init__ already called _go_to(0), but walk it
        # again so we exercise the sizer-level Show() path explicitly.
        dlg._go_to(0)
        # Inspect each button's own IsShown() (what screen readers see)
        # and the sizer item's IsShown() (the source of truth for layout).
        win_state = {
            n: getattr(dlg, f"_btn_{n}").IsShown()
            for n in ("back", "next", "setup", "save", "wizard", "close")
        }
        sizer_state = _sizer_state(dlg)
        expected = {
            "back": False, "next": False, "setup": False,
            "save": True, "wizard": True, "close": True,
        }
        assert win_state == expected, ("window state", win_state)
        assert sizer_state == expected, ("sizer state", sizer_state)
    finally:
        dlg.Destroy()


def test_wizard_middle_step_buttons(fake_home, frame):
    """Middle wizard step shows Back + Next only."""
    from chapterforge.app import AIModelUnifiedDialog

    dlg = AIModelUnifiedDialog(
        frame,
        {"ai_engine_tier": "Strong", "ai_model_name": "small",
         "ai_setup_done": False},
    )
    try:
        dlg._go_to(1)
        visible = {n: getattr(dlg, f"_btn_{n}").IsShown()
                   for n in ("back", "next", "setup", "save",
                             "wizard", "close")}
        assert visible == {
            "back": True, "next": True, "setup": False,
            "save": False, "wizard": False, "close": False,
        }, visible
    finally:
        dlg.Destroy()


def test_wizard_completion_step_buttons(fake_home, frame):
    """Final wizard step shows Back + Setup AI Model."""
    from chapterforge.app import AIModelUnifiedDialog

    dlg = AIModelUnifiedDialog(
        frame,
        {"ai_engine_tier": "Strong", "ai_model_name": "small",
         "ai_setup_done": False},
    )
    try:
        dlg._go_to(2)
        visible = {n: getattr(dlg, f"_btn_{n}").IsShown()
                   for n in ("back", "next", "setup", "save",
                             "wizard", "close")}
        assert visible == {
            "back": True, "next": False, "setup": True,
            "save": False, "wizard": False, "close": False,
        }, visible
    finally:
        dlg.Destroy()


# ---------------------------------------------------------------------------
# Mode switching
# ---------------------------------------------------------------------------


def test_settings_to_wizard_switch(fake_home, frame):
    """The "Run Setup Wizard" button drops the settings card and walks back."""
    _make_faster_whisper_repo(fake_home, "small")
    from chapterforge.app import AIModelUnifiedDialog

    dlg = AIModelUnifiedDialog(
        frame,
        {"ai_engine_tier": "Strong", "ai_model_name": "small",
         "ai_setup_done": True},
    )
    try:
        assert len(dlg._steps) == 1
        dlg._on_switch_to_wizard(None)
        assert len(dlg._steps) == 3
        from chapterforge.app import AIModelUnifiedDialog as Cls
        assert dlg._steps[0].__func__ is Cls._make_intro_step
        # After the switch, Back is disabled on step 0.
        assert dlg._btn_back.IsEnabled() is False
    finally:
        dlg.Destroy()


# ---------------------------------------------------------------------------
# _on_save semantics
# ---------------------------------------------------------------------------


def test_on_save_preserves_matching_picks(fake_home, frame):
    """If the user keeps the same tier+model that's already on disk, no flip."""
    _make_faster_whisper_repo(fake_home, "small")
    from chapterforge.app import AIModelUnifiedDialog

    s = {"ai_engine_tier": "Strong", "ai_model_name": "small",
         "ai_setup_done": True}
    dlg = AIModelUnifiedDialog(frame, s)
    try:
        dlg._on_save()
        # _on_save is a no-op on the wx state when not modal, but the
        # in-memory settings dict is what the caller reads.
        assert s["ai_engine_tier"] == "Strong"
        assert s["ai_model_name"] == "small"
        # The matching model IS on disk, so ai_setup_done stays True.
        assert s["ai_setup_done"] is True
    finally:
        dlg.Destroy()


def test_on_save_clears_done_when_pick_missing(fake_home, frame):
    """If the user picks a model that is not on disk, ai_setup_done flips False."""
    _make_faster_whisper_repo(fake_home, "small")
    from chapterforge.app import AIModelUnifiedDialog

    s = {"ai_engine_tier": "Strong", "ai_model_name": "small",
         "ai_setup_done": True}
    dlg = AIModelUnifiedDialog(frame, s)
    try:
        # Force a tier change to a model that is NOT on disk.
        for val, rb in dlg.rb_tiers:
            if val == "Strong":
                rb.SetValue(True)
                rb.ProcessEvent(
                    type(rb.GetEventObject())  # placeholder, real path below
                ) if False else None
                break
        # Pick "medium" (no repo on disk for it).
        rb_models = getattr(dlg, "rb_models", [])
        for opt, rb in rb_models:
            if opt == "medium":
                rb.SetValue(True)
                break
        dlg._on_save()
        assert s["ai_engine_tier"] == "Strong"
        assert s["ai_model_name"] == "medium"
        # The medium model is not in tmp_path -> ai_setup_done must be False.
        assert s["ai_setup_done"] is False
    finally:
        dlg.Destroy()


# ---------------------------------------------------------------------------
# Accessibility (binding contract)
# ---------------------------------------------------------------------------


def test_every_control_has_accessible_name(fake_home, frame):
    """Every control must have a non-empty name (SetName) or a non-empty label.

    The ChapterForge accessibility contract says: radio buttons get a full
    descriptive label baked into ``label=``; all other controls get a
    ``SetName``. Verify both. We do NOT assert on specific strings, only
    that the value is present and non-empty.
    """
    _make_faster_whisper_repo(fake_home, "small")
    from chapterforge.app import AIModelUnifiedDialog

    dlg = AIModelUnifiedDialog(
        frame,
        {"ai_engine_tier": "Strong", "ai_model_name": "small",
         "ai_setup_done": True},
    )
    try:
        named_buttons = (
            dlg._hdr_title, dlg._hdr_step,
            dlg._btn_back, dlg._btn_next, dlg._btn_setup,
            dlg._btn_save, dlg._btn_wizard, dlg._btn_close,
        )
        for ctrl in named_buttons:
            assert ctrl.GetName().strip(), (
                f"{type(ctrl).__name__} missing accessible name")
        # Tier radios: full label is the contract.
        for _val, rb in dlg.rb_tiers:
            assert rb.GetLabel().strip(), "tier radio missing label"
            assert rb.GetName().strip(), "tier radio missing accessible name"
        # Model radios: same.
        for _opt, rb in dlg.rb_models:
            assert rb.GetLabel().strip(), "model radio missing label"
            assert rb.GetName().strip(), "model radio missing accessible name"
    finally:
        dlg.Destroy()
