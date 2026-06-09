"""Feature-flag registry and release channels for optional ChapterForge features.

Lets users hide optional features they don't want cluttering menus and the
interface, and choose how early they want access to newer ones, without
uninstalling or recompiling anything.

Two settings work together:

* ``release_channel`` - one of "general" or "beta". Each flag in the
  registry below names the channel it first becomes available on; a feature
  marked "beta" is only available on the beta channel. Moving to an
  earlier-access channel can reveal features that were previously hidden
  entirely - the Feature Flags dialog rebuilds its list live as the channel
  changes, showing each newly available feature's description so the user
  can decide whether to opt in.
* ``feature_flags`` - a ``{flag_key: bool}`` dict of overrides layered on the
  registry defaults, for opting individual available features in or out.

Both are read once at startup (when the menu bar and panels are built). The
Help menu's "Feature Flags..." dialog edits them; "Reset Feature Flags to
Defaults" clears the overrides (leaving the chosen channel untouched, since
that's a separate, deliberate choice). Changes take effect after restarting
ChapterForge, since the menu bar and panels are only built once at startup.

Only genuinely optional, cleanly separable features are listed here - core
workflow (opening folders, building, editing chapters and tags) is not
flaggable, since disabling it would leave the app unusable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import wx

# Release channels, from most to least stable. A flag's ``channel`` is the
# earliest (least-stable) channel it appears on; users on a later entry in
# this list see everything from the entries before it too.
CHANNELS: List[Tuple[str, str, str]] = [
    ("general", "General",
     "Stable, fully tested features. Recommended for most users."),
    ("beta", "Beta",
     "Everything in General, plus newer features that are still being "
     "refined and may have occasional rough edges."),
]
_CHANNEL_RANK: Dict[str, int] = {key: rank for rank, (key, _, _) in enumerate(CHANNELS)}
_CHANNEL_DESCRIPTIONS: Dict[str, str] = {key: desc for key, _, desc in CHANNELS}
DEFAULT_CHANNEL = CHANNELS[0][0]


def channel_rank(channel: str) -> int:
    """Stability rank of *channel* (0 = most stable). Unknown -> most stable."""
    return _CHANNEL_RANK.get(channel, 0)


def get_channel(settings) -> str:
    """The user's chosen release channel, falling back to the default."""
    channel = settings.get("release_channel", DEFAULT_CHANNEL)
    return channel if channel in _CHANNEL_RANK else DEFAULT_CHANNEL


def set_channel(settings, channel: str) -> None:
    """Switch the user's release channel (no-op for an unknown channel)."""
    if channel in _CHANNEL_RANK:
        settings["release_channel"] = channel


@dataclass(frozen=True)
class Flag:
    key: str
    label: str
    description: str
    default: bool = True
    channel: str = DEFAULT_CHANNEL  # earliest channel this feature appears on


# Order here is the display order in the Feature Flags dialog.
_FLAGS = [
    Flag("audio_player", "Audio player",
         "The in-app audio player panel, and the Play This Chapter, "
         "Split Here and Go to Time commands that depend on it."),
    Flag("mp3_editing", "Edit existing master files",
         "\"Open Existing Master…\" - fixes the tags and chapter titles "
         "of a chaptered MP3/M4B you already built, without re-encoding it. "
         "Off by default - opt in from Help > Feature Flags.",
         default=False, channel="beta"),
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
    Flag("chapter_file_splitting", "Split master into chapter files",
         "\"Save as Individual Chapter Files…\" - splits the open audio "
         "into one file per chapter with a lossless FFmpeg copy."),
    Flag("batch_title_editing", "Batch title editing",
         "\"Batch Edit Titles…\" - applies a transformation to all "
         "chapter titles at once."),
    Flag("source_file_renaming", "Source file renaming",
         "\"Rename Source Files…\" - renames the source MP3 files using "
         "a pattern based on chapter titles."),
    Flag("chapter_list_import_export", "Chapter list import/export",
         "\"Load Chapter List From File…\" and \"Save Chapter List…\" - "
         "exchanges chapter markers with label files, CUE sheets or JSON."),
    Flag("job_templates", "Setup templates",
         "\"Load a Saved Setup…\" and \"Save This Setup as a Template…\" "
         "- reusable .cfjob files that capture chapter order, titles and tags."),
    Flag("build_log", "Build log viewer",
         "\"View Build Log…\" - shows a log of recent build activity."),
    Flag("setup_wizard", "Setup wizard",
         "\"Setup Wizard…\" - a guided walkthrough for configuring ChapterForge."),
    Flag("diagnostics_report", "Diagnostics report",
         "\"Get Help Information…\" - saves a text report of versions and "
         "settings for support."),
    Flag("auphonic", "Auphonic integration",
         "The Auphonic menu - submits audio to Auphonic for AI-assisted "
         "post-production (leveling, noise reduction, loudness). Requires "
         "an Auphonic account (auphonic.com). Off by default - opt in from "
         "Help > Feature Flags.",
         default=False, channel="beta"),
    Flag("publishing", "Direct publishing to remote destinations",
         "The Publish menu - uploads a finished master to saved SFTP "
         "destinations, manually or automatically after a build. Off by "
         "default - opt in once you've configured a destination.",
         default=False, channel="beta"),
]

REGISTRY: Dict[str, Flag] = {flag.key: flag for flag in _FLAGS}


def is_available(settings, key: str) -> bool:
    """True if *key* appears at all on the user's chosen channel.

    Unknown keys are treated as available (fail open) so a flag that's
    removed in a future version doesn't silently hide something else.
    """
    flag = REGISTRY.get(key)
    if flag is None:
        return True
    return channel_rank(get_channel(settings)) >= channel_rank(flag.channel)


def is_enabled(settings, key: str) -> bool:
    """True if the feature named *key* should be shown/available.

    A feature must both be on the user's channel and not be turned off by
    an override (or, lacking an override, be enabled by default).
    """
    if not is_available(settings, key):
        return False
    flag = REGISTRY[key]
    overrides = settings.get("feature_flags", {})
    return bool(overrides.get(key, flag.default))


def any_beta_enabled(settings) -> bool:
    """True if any feature beyond the stable/general channel is enabled.

    Used to decide whether to show the one-time "you're running beta
    features" warning - it should appear the moment the user opts into
    something experimental, not on every launch once they have.
    """
    return any(channel_rank(flag.channel) > 0 and is_enabled(settings, flag.key)
               for flag in _FLAGS)


def reset_to_defaults(settings) -> None:
    """Clear all overrides, restoring every available feature to its default.

    Leaves the release channel untouched - that's a separate, deliberate
    choice, not something a flag reset should undo.
    """
    settings["feature_flags"] = {}


class FeatureFlagsDialog(wx.Dialog):
    """Lets the user choose a release channel and show or hide its features.

    Disabled features are removed from menus and the interface entirely
    (not just greyed out) the next time ChapterForge starts. Switching to
    an earlier-access channel can reveal features that were previously
    hidden - the list below rebuilds immediately to show them, along with
    their descriptions, so the user can decide whether to opt in.
    """

    def __init__(self, parent, settings):
        super().__init__(parent, title="Feature Flags",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._settings = settings
        # Keep every override (even for flags hidden on the current channel)
        # so switching channels back and forth doesn't discard preferences.
        self._pending_overrides: Dict[str, bool] = dict(settings.get("feature_flags", {}))
        self._checks: Dict[str, wx.CheckBox] = {}

        outer = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(self, label=(
            "Choose how early you want access to new features, and turn "
            "individual ones on or off. A disabled feature's menus and "
            "controls are removed from the interface entirely.\n"
            "Restart ChapterForge for changes to take effect."))
        intro.Wrap(460)
        outer.Add(intro, 0, wx.EXPAND | wx.ALL, 12)

        self.channel_box = wx.RadioBox(
            self, label="Update channel",
            choices=[label for _, label, _ in CHANNELS],
            majorDimension=1, style=wx.RA_SPECIFY_ROWS)
        self.channel_box.SetSelection(channel_rank(get_channel(settings)))
        self.channel_box.Bind(wx.EVT_RADIOBOX, self._on_channel_changed)
        outer.Add(self.channel_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.channel_desc = wx.StaticText(self, label="")
        self.channel_desc.Wrap(460)
        outer.Add(self.channel_desc, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.flags_panel = wx.Panel(self)
        outer.Add(self.flags_panel, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_reset = wx.Button(self, label="&Reset Features to Defaults")
        self.btn_reset.SetToolTip(
            "Re-enable every feature available on the selected channel "
            "(without closing this dialog)")
        self.btn_reset.Bind(wx.EVT_BUTTON, self._on_reset)
        btn_row.Add(self.btn_reset, 0)
        btn_row.AddStretchSpacer()
        btn_row.Add(self.CreateSeparatedButtonSizer(wx.OK | wx.CANCEL), 1, wx.EXPAND)
        outer.Add(btn_row, 0, wx.EXPAND | wx.ALL, 12)

        self._outer = outer
        self._rebuild_flags()
        self.SetSizerAndFit(outer)
        self.SetMinSize((520, -1))
        self.CentreOnParent()
        self.channel_box.SetFocus()

    def _selected_channel(self) -> str:
        return CHANNELS[self.channel_box.GetSelection()][0]

    def _on_channel_changed(self, _evt):
        self._rebuild_flags()

    def _rebuild_flags(self):
        """Rebuild the feature checklist for the currently selected channel."""
        channel = self._selected_channel()
        rank = channel_rank(channel)
        self.channel_desc.SetLabel(_CHANNEL_DESCRIPTIONS[channel])
        self.channel_desc.Wrap(460)

        self.flags_panel.DestroyChildren()
        self._checks = {}
        sizer = wx.BoxSizer(wx.VERTICAL)
        visible = [f for f in _FLAGS if channel_rank(f.channel) <= rank]
        if not visible:
            msg = wx.StaticText(
                self.flags_panel,
                label="No optional features are available on this channel.")
            sizer.Add(msg, 0, wx.ALL, 6)
        for flag in visible:
            cb = wx.CheckBox(self.flags_panel, label=flag.label)
            cb.SetValue(bool(self._pending_overrides.get(flag.key, flag.default)))
            cb.SetName(flag.label)
            cb.Bind(wx.EVT_CHECKBOX,
                    lambda evt, key=flag.key: self._pending_overrides.__setitem__(
                        key, evt.IsChecked()))
            self._checks[flag.key] = cb
            sizer.Add(cb, 0, wx.TOP, 6)
            desc = wx.StaticText(self.flags_panel, label=flag.description)
            desc.Wrap(430)
            sizer.Add(desc, 0, wx.LEFT | wx.BOTTOM, 24)
        self.flags_panel.SetSizer(sizer)
        self.flags_panel.Layout()
        self._outer.Layout()
        self.Fit()

    def _on_reset(self, _evt):
        rank = channel_rank(self._selected_channel())
        for flag in _FLAGS:
            if channel_rank(flag.channel) <= rank:
                self._pending_overrides.pop(flag.key, None)
                self._checks[flag.key].SetValue(flag.default)

    def get_channel(self) -> str:
        return self._selected_channel()

    def get_overrides(self) -> Dict[str, bool]:
        """Return a ``{flag_key: bool}`` dict of values that differ from
        their registry default - the form stored in settings."""
        return {key: value for key, value in self._pending_overrides.items()
                if key in REGISTRY and value != REGISTRY[key].default}


class BetaWarningDialog(wx.Dialog):
    """One-time heads-up shown the moment the user opts into a beta feature.

    Beta features can change or misbehave between releases; this tells
    people that plainly, in their own words, right when it becomes true for
    them - with a way to silence it permanently once they've seen it.
    """

    def __init__(self, parent):
        super().__init__(parent, title="Beta Features Enabled",
                         style=wx.DEFAULT_DIALOG_STYLE)

        outer = wx.BoxSizer(wx.VERTICAL)

        message = wx.StaticText(self, label=(
            "You've turned on one or more beta features.\n\n"
            "Beta features are newer parts of ChapterForge that are still "
            "being refined. They may behave unexpectedly, change in a "
            "future update, or be removed - you're trying them at your own "
            "risk. Your books and audio files are never at risk; only the "
            "optional feature itself might be rough around the edges.\n\n"
            "You can turn any feature back off at any time from "
            "Help > Feature Flags."))
        message.Wrap(420)
        outer.Add(message, 0, wx.EXPAND | wx.ALL, 16)

        self.dont_show_check = wx.CheckBox(
            self, label="&Don't show this warning again")
        outer.Add(self.dont_show_check, 0,
                  wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)

        outer.Add(self.CreateSeparatedButtonSizer(wx.OK), 0,
                  wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.SetSizerAndFit(outer)
        self.SetMinSize((460, -1))
        self.CentreOnParent()
        self.dont_show_check.SetFocus()

    def dont_show_again(self) -> bool:
        return self.dont_show_check.GetValue()
