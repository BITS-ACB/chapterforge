"""Context-sensitive help: press F1 to hear what the focused control does.

Unlike the static Keyboard Shortcuts / User Guide pages, this looks at
*which* control currently has keyboard focus and shows a short, live
explanation of it - including its current state (speed, volume, chapter,
playback position, build vs. edit mode, ...) and the settings that shape its
behaviour (skip seconds, default volume, ...). The aim is to answer "what is
this, and what will happen if I activate it right now?" rather than "what are
all the controls in this dialog?".

The actual descriptions - what to say about each control, and which bits of
that should reflect live settings and state - live in
:mod:`chapterforge.control_help`, as a token-driven schema shared with the
generated Control Reference documentation page (``tools/build_docs.py``).
That sharing is the point: the in-app answer and the documented answer are
rendered from the very same templates, so they can't say different things.
This module supplies the wx-specific half - finding the focused control,
mapping it to a schema entry, the dialog chrome, and a generic fallback for
anything not in the schema, so F1 always answers *something* useful.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import wx

from . import control_help

_Locator = Tuple[str, Callable[[], Optional[wx.Window]]]


def _locators(frame) -> List[_Locator]:
    """Pair each schema control id with a function that finds its current
    wx widget. Rebuilt on every lookup - cheap, and means a control swapped
    out from under us (e.g. the player reloading) is never stale."""
    p = frame.player
    return [
        ("btn_play", lambda: p.btn_play),
        ("btn_stop", lambda: p.btn_stop),
        ("btn_prev", lambda: p.btn_prev),
        ("btn_next", lambda: p.btn_next),
        ("btn_rew", lambda: p.btn_rew),
        ("btn_ff", lambda: p.btn_ff),
        ("pos_slider", lambda: p.pos_slider),
        ("vol_slider", lambda: p.vol_slider),
        ("speed_choice", lambda: p.speed_choice),
        ("btn_save_speed", lambda: p.btn_save_speed),
        ("btn_trim_start", lambda: p.btn_trim_start),
        ("btn_trim_end", lambda: p.btn_trim_end),
        ("btn_trim_clear", lambda: p.btn_trim_clear),
        ("btn_prelisten_cut", lambda: p.btn_prelisten_cut),
        ("btn_save_trimmed", lambda: p.btn_save_trimmed),
        ("list", lambda: frame.list),
        ("title_ctrl", lambda: frame.title_ctrl),
        ("btn_up", lambda: frame.btn_up),
        ("btn_down", lambda: frame.btn_down),
        ("btn_remove", lambda: frame.btn_remove),
        ("btn_edit", lambda: frame.btn_edit),
        ("btn_play_sel", lambda: frame.btn_play_sel),
        ("btn_split", lambda: frame.btn_split),
        ("folder_ctrl", lambda: frame.folder_ctrl),
    ]


_GENERIC_BY_CLASS = {
    "wxButton": "This is a button. Activate it with Space or Enter.",
    "wxCheckBox": "This is a checkbox. Toggle it with Space.",
    "wxRadioButton": "This is a radio button. Select it with Space, or "
                     "move between options in its group with the arrow keys.",
    "wxTextCtrl": "This is a text field. Type to edit its contents.",
    "wxComboBox": "This is a combo box. Type to filter, or use the arrow "
                  "keys to choose from its list.",
    "wxChoice": "This is a drop-down list. Use the arrow keys, or Alt+Down "
                "to open it, to choose an option.",
    "wxSlider": "This is a slider. Use the arrow keys, Page Up/Down, Home "
                "and End to change its value.",
    "wxListCtrl": "This is a list. Use the arrow keys to move between rows, "
                  "and the Menu key or Shift+F10 for a context menu of "
                  "actions on the selected row.",
    "wxSpinCtrl": "This is a number field with up/down steppers. Type a "
                  "value, or use the arrow keys to step it.",
}


def _generic_description(ctrl: wx.Window) -> Tuple[str, str]:
    name = ctrl.GetName() or ctrl.GetLabel() or "This control"
    parts = []
    tip = ctrl.GetToolTipText() if hasattr(ctrl, "GetToolTipText") else ""
    if tip:
        parts.append(tip)
    parts.append(_GENERIC_BY_CLASS.get(
        ctrl.GetClassName(),
        "No specific help is available for this control yet - its "
        "accessible name and tooltip (if any) are shown above. See the "
        "User Guide (Ctrl+F1) for a fuller walkthrough."))
    return (name, "\n\n".join(parts))


def _describe_idle(frame) -> Tuple[str, str]:
    return ("Getting started",
            "No file is open yet. ChapterForge works in two modes:\n\n"
            "Build mode - Open Folder (Ctrl+Shift+O) combines a folder of "
            "source MP3 files into one master MP3 with chapter markers.\n\n"
            "Edit mode - Open Existing Master (Ctrl+O) fixes the tags and "
            "chapter titles of a chaptered MP3/M4B you already built, "
            "without re-encoding it.\n\n"
            "Use Tab or click a control, then press F1 again to learn what "
            "it does.")


def describe_focused(frame, ctrl: Optional[wx.Window] = None) -> Tuple[str, str]:
    """Return (title, body) help text for whichever control has focus.

    *ctrl* lets the caller supply the control to describe directly - useful
    when the real keyboard focus has moved somewhere unhelpful (e.g. onto the
    menu bar, while choosing "Help on This Control" from the Help menu rather
    than pressing its F1 accelerator). Defaults to ``wx.Window.FindFocus()``.

    Falls back to a generic, still-useful description (built from the
    control's accessible name, tooltip and type) for anything not covered
    by the control_help schema.
    """
    if ctrl is None:
        ctrl = wx.Window.FindFocus()
    if ctrl is None:
        if frame.mode == "build" and not frame.items:
            return _describe_idle(frame)
        return ("No control is focused",
                "Use Tab or click a control, then press F1 again to learn "
                "what it does.")
    for control_id, locate in _locators(frame):
        try:
            target = locate()
        except AttributeError:
            continue
        if target is not None and target is ctrl:
            return control_help.render_live(control_id, frame)
    return _generic_description(ctrl)


class ContextHelpDialog(wx.Dialog):
    """A small read-only "what's this" panel, styled like the setup wizard:
    a multi-line description plus a single Close button - simple to dismiss
    and friendly to screen readers (NVDA reads the title, then the body line
    by line)."""

    def __init__(self, parent, title: str, body: str):
        super().__init__(parent, title=f"Help: {title}",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        outer = wx.BoxSizer(wx.VERTICAL)

        body_ctrl = wx.TextCtrl(
            self, value=body,
            style=(wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_BESTWRAP
                   | wx.TE_NO_VSCROLL | wx.NO_BORDER))
        body_ctrl.SetName(f"{title} - help")
        body_ctrl.SetBackgroundColour(self.GetBackgroundColour())
        outer.Add(body_ctrl, 1, wx.EXPAND | wx.ALL, 14)

        btn_close = wx.Button(self, wx.ID_CLOSE, label="&Close")
        btn_close.SetName("Close this help window")
        btn_close.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        outer.Add(btn_close, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.BOTTOM, 14)

        self.SetEscapeId(wx.ID_CLOSE)
        self.SetSizer(outer)
        self.SetSize((480, 360))
        self.CentreOnParent()
        body_ctrl.SetFocus()
