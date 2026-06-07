"""Feature-flag registry for optional ChapterForge features.

Lets users hide optional features they don't want cluttering menus and the
interface, without uninstalling or recompiling anything. Flags are read once
at startup (when the menu bar and panels are built) and stored as overrides
in settings under the ``feature_flags`` key - a ``{flag_key: bool}`` dict
layered on top of the registry defaults below, so adding a new flag never
requires migrating existing settings files.

Only genuinely optional, cleanly separable features are listed here - core
workflow (opening folders, building, editing chapters and tags) is not
flaggable, since disabling it would leave the app unusable.

The Help menu's "Feature Flags..." dialog edits the overrides; "Reset
Feature Flags to Defaults" clears them, restoring every feature. Both write
through to ``chapterforge.settings``. Changes take effect after restarting
ChapterForge, since the menu bar and panels are only built once at startup.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import wx


@dataclass(frozen=True)
class Flag:
    key: str
    label: str
    description: str
    default: bool = True


# Order here is the display order in the Feature Flags dialog.
_FLAGS = [
    Flag("audio_player", "Audio player",
         "The in-app audio player panel, and the Play This Chapter, "
         "Split Here and Go to Time commands that depend on it."),
    Flag("command_palette", "Command palette",
         "The Ctrl+Shift+P command palette for searching and running any command."),
    Flag("silence_chapter_detection", "Silence-based chapter detection",
         "\"Find Chapters in Silent Gaps\" - detects chapter boundaries "
         "from quiet passages in the audio."),
    Flag("metadata_lookup", "Metadata lookup",
         "\"Look Up Metadata\" - searches MusicBrainz or Open Library "
         "to pre-fill title, artist and genre."),
    Flag("acx_compliance", "ACX compliance check",
         "\"Check ACX Compliance\" - measures output files against "
         "Audible/ACX loudness and peak requirements."),
    Flag("batch_build", "Batch building",
         "\"Build Multiple Books\" - builds a master for every "
         "sub-folder of books at once."),
    Flag("merge_short_chapters", "Merge short chapters",
         "\"Merge Short Chapters\" - collapses chapters shorter than "
         "a minimum duration into the previous chapter."),
    Flag("auto_build_watcher", "Automatic folder watching",
         "Background watch-folder setup, auto-build in the system tray, "
         "and running the watcher automatically at sign-in."),
]

REGISTRY: Dict[str, Flag] = {flag.key: flag for flag in _FLAGS}


def is_enabled(settings, key: str) -> bool:
    """True if the feature named *key* should be shown/available.

    Unknown keys are treated as enabled (fail open) so a flag that's
    removed in a future version doesn't silently hide something else.
    """
    flag = REGISTRY.get(key)
    if flag is None:
        return True
    overrides = settings.get("feature_flags", {})
    return bool(overrides.get(key, flag.default))


def reset_to_defaults(settings) -> None:
    """Clear all overrides, restoring every feature to its registry default."""
    settings["feature_flags"] = {}


class FeatureFlagsDialog(wx.Dialog):
    """Lets the user show or hide optional features.

    Disabled features are removed from menus and the interface entirely
    (not just greyed out) the next time ChapterForge starts.
    """

    def __init__(self, parent, settings):
        super().__init__(parent, title="Feature Flags",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        outer = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(self, label=(
            "Turn optional features on or off. A disabled feature's menus "
            "and controls are removed from the interface entirely.\n"
            "Restart ChapterForge for changes to take effect."))
        intro.Wrap(440)
        outer.Add(intro, 0, wx.EXPAND | wx.ALL, 12)

        overrides = settings.get("feature_flags", {})
        self._checks: Dict[str, wx.CheckBox] = {}
        for flag in _FLAGS:
            cb = wx.CheckBox(self, label=flag.label)
            cb.SetValue(bool(overrides.get(flag.key, flag.default)))
            cb.SetName(flag.label)
            cb.SetToolTip(flag.description)
            self._checks[flag.key] = cb
            outer.Add(cb, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_reset = wx.Button(self, label="&Reset to Defaults")
        self.btn_reset.SetToolTip("Re-enable every feature in this dialog (without closing it)")
        self.btn_reset.Bind(wx.EVT_BUTTON, self._on_reset)
        btn_row.Add(self.btn_reset, 0)
        btn_row.AddStretchSpacer()
        btn_row.Add(self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL), 1, wx.EXPAND)
        outer.Add(btn_row, 0, wx.EXPAND | wx.ALL, 12)

        self.SetSizerAndFit(outer)
        self.SetMinSize((480, -1))
        self.CentreOnParent()
        self._checks[_FLAGS[0].key].SetFocus()

    def _on_reset(self, _evt):
        for flag in _FLAGS:
            self._checks[flag.key].SetValue(flag.default)
        self._checks[_FLAGS[0].key].SetFocus()

    def get_overrides(self) -> Dict[str, bool]:
        """Return a ``{flag_key: bool}`` dict of values that differ from
        their registry default - the form stored in settings."""
        result = {}
        for flag in _FLAGS:
            value = self._checks[flag.key].GetValue()
            if value != flag.default:
                result[flag.key] = value
        return result
