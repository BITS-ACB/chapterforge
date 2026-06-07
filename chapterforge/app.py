"""Accessible wxPython UI for ChapterForge.

Design notes for accessibility:
* Every interactive control has a visible ``wx.StaticText`` label with a
  mnemonic and an explicit accessible name (``SetName``) so screen readers
  (NVDA / Narrator) announce it clearly.
* The whole window is keyboard operable: menus with accelerators, mnemonic
  buttons, list-view keys (Up/Down/Delete/F2) and a logical tab order.
* Long-running work happens on a worker thread; the UI is only ever touched
  from the main thread via ``wx.CallAfter``. Completion, cancellation and
  errors are reported through modal dialogs, which screen readers announce
  reliably, in addition to an always-available status line and progress gauge.
"""

from __future__ import annotations

import copy as _copy
import os
import sys
import threading
import time
from typing import List, Optional

import wx
import wx.media

from . import (
    SERVICES, __app_name__, __copyright__, __org__, __version__, a11y, core,
)
from . import feature_flags
from . import manifest as manifest_mod
from . import settings as settings_mod
from .notify import Notifier
from .player import PlayerPanel
from .auphonic import AuphonicService

# Token for issue submission. Resolved at runtime from environment or
# build-injected constant. Never hardcode a real token here.
# Set CHAPTERFORGE_GITHUB_TOKEN env var or inject via build pipeline.
_FEEDBACK_GITHUB_TOKEN = os.environ.get("CHAPTERFORGE_GITHUB_TOKEN", "")


# ----------------------------------------------------------------------------
# Undo / redo infrastructure
# ----------------------------------------------------------------------------

class _UndoAction:
    """One reversible chapter-list operation."""
    __slots__ = ("description", "undo_fn", "redo_fn")
    def __init__(self, description: str, undo_fn, redo_fn):
        self.description = description
        self.undo_fn = undo_fn
        self.redo_fn = redo_fn


class _UndoStack:
    """Bounded undo/redo stack for chapter list operations."""
    MAX = 50

    def __init__(self):
        self._history: list = []
        self._pos: int = -1   # index of the last *applied* action

    def push(self, action: _UndoAction) -> None:
        """Record a new action, discarding any redo tail."""
        del self._history[self._pos + 1:]
        self._history.append(action)
        if len(self._history) > self.MAX:
            self._history.pop(0)
        else:
            self._pos += 1

    def can_undo(self) -> bool:
        return self._pos >= 0

    def can_redo(self) -> bool:
        return self._pos < len(self._history) - 1

    def undo(self):
        if not self.can_undo():
            return None
        action = self._history[self._pos]
        action.undo_fn()
        self._pos -= 1
        return action.description

    def redo(self):
        if not self.can_redo():
            return None
        self._pos += 1
        action = self._history[self._pos]
        action.redo_fn()
        return action.description

    def undo_label(self) -> str:
        if not self.can_undo():
            return "Undo"
        return f"Undo {self._history[self._pos].description}"

    def redo_label(self) -> str:
        if not self.can_redo():
            return "Redo"
        return f"Redo {self._history[self._pos + 1].description}"

    def clear(self) -> None:
        self._history.clear()
        self._pos = -1


# ----------------------------------------------------------------------------
# Custom events posted from the worker thread
# ----------------------------------------------------------------------------

EVT_PROGRESS = wx.NewEventType()
EVT_DONE = wx.NewEventType()
EVT_FAILED = wx.NewEventType()


class _ThreadEvent(wx.PyEvent):
    def __init__(self, etype, payload=None):
        super().__init__()
        self.SetEventType(etype)
        self.payload = payload


def _windows_high_contrast_active() -> bool:
    """Return True if Windows high-contrast mode is currently on."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        import ctypes.wintypes
        # HIGHCONTRAST structure: cbSize (UINT), dwFlags (DWORD), lpszDefaultScheme (LPTSTR)
        class HIGHCONTRAST(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.wintypes.UINT),
                ("dwFlags", ctypes.wintypes.DWORD),
                ("lpszDefaultScheme", ctypes.c_wchar_p),
            ]
        hc = HIGHCONTRAST()
        hc.cbSize = ctypes.sizeof(HIGHCONTRAST)
        SPI_GETHIGHCONTRAST = 0x0042
        result = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETHIGHCONTRAST, hc.cbSize, ctypes.byref(hc), 0)
        if result:
            HCF_HIGHCONTRASTON = 0x0001
            return bool(hc.dwFlags & HCF_HIGHCONTRASTON)
    except Exception:
        pass
    return False


class MainFrame(wx.Frame):
    _COL_WIDTHS = [44, 260, 80, 80, 200]
    _COL_NAMES_DISPLAY = ["#", "Title", "Start time", "Duration", "Source file"]

    def __init__(self):
        self.settings = settings_mod.load()
        size = (int(self.settings.get("win_w", 940)),
                int(self.settings.get("win_h", 760)))
        super().__init__(None, title=__app_name__, size=size)

        self.items: List[core.Mp3Item] = []
        self.folder: str = ""
        self.output_path: str = ""
        self._output_auto: bool = True
        # Editing mode: 'build' (folder of MP3s) or 'edit' (one existing
        # chaptered file whose tags/chapter titles are being corrected).
        self.mode: str = "build"
        self.edit_path: str = ""
        self.edit_chapters: List[core.Chapter] = []
        self.edit_total_ms: int = 0
        self.edit_dirty: bool = False
        self._audio_order: list = []
        self.canceller: Optional[core.Canceller] = None
        self.worker: Optional[threading.Thread] = None
        self._last_pct = -1
        self.notifier = Notifier(parent=self)
        self._tray = None
        self._watch_controller = None
        self._auphonic = AuphonicService(
            client_id=os.environ.get("AUPHONIC_CLIENT_ID", ""),
            client_secret=os.environ.get("AUPHONIC_CLIENT_SECRET", ""),
        )
        self._force_quit = False
        self._player_revealed = False  # show the player the first time media loads
        self._list_col = 0  # currently announced column for keyboard column navigation
        self._undo = _UndoStack()

        self._build_menu()
        self._build_ui()
        self.CreateStatusBar()
        self.SetStatusText(
            "Open a folder of MP3 files to begin - or press Ctrl+Shift+P for all commands.")

        self._apply_settings_to_ui()

        self.Connect(-1, -1, EVT_PROGRESS, self._on_evt_progress)
        self.Connect(-1, -1, EVT_DONE, self._on_evt_done)
        self.Connect(-1, -1, EVT_FAILED, self._on_evt_failed)
        self.Bind(wx.EVT_CLOSE, self._on_close)

        wx_x = int(self.settings.get("win_x", -1))
        wx_y = int(self.settings.get("win_y", -1))
        if wx_x >= 0 and wx_y >= 0:
            self.SetPosition(wx.Point(wx_x, wx_y))
        else:
            self.Centre()
        if self.settings.get("win_max"):
            self.Maximize(True)
        self._rebuild_recent_menu()
        self._apply_appearance()
        self._update_command_state()
        if self.settings.get("check_updates_startup", True):
            wx.CallAfter(self._check_updates_on_startup)
        if not self.settings.get("wizard_seen", False):
            wx.CallAfter(self._on_wizard, None)
        wx.CallAfter(self.list.SetFocus)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build_menu(self):
        menubar = wx.MenuBar()

        file_menu = wx.Menu()
        self.mi_open = file_menu.Append(wx.ID_OPEN, "&Open Folder…\tCtrl+Shift+O",
                                        "Choose a folder of MP3 files")
        self.mi_open_master = file_menu.Append(
            wx.ID_ANY, "Open &Existing Master…\tCtrl+O",
            "Open a chaptered MP3/M4B to fix its tags and chapter titles")
        self.recent_menu = wx.Menu()
        self.mi_recent = file_menu.AppendSubMenu(
            self.recent_menu, "Open &Recent",
            "Re-open a recently used folder, master or job file")
        self.mi_output = file_menu.Append(wx.ID_ANY, "&Save Master As…",
                                          "Choose where the master file is saved")
        file_menu.AppendSeparator()
        self.mi_build = file_menu.Append(wx.ID_ANY, "&Build Master MP3\tCtrl+B",
                                         "Build the master MP3 with chapters")
        self.mi_save_edit = file_menu.Append(
            wx.ID_ANY, "Sa&ve Changes\tCtrl+Shift+S",
            "Save edited tags and chapter titles back to the open master")
        self.mi_save_as = file_menu.Append(
            wx.ID_SAVEAS, "Save &As…\tCtrl+Shift+A",
            "Save the master (or edited master) to a new file")
        self.mi_split_files = file_menu.Append(
            wx.ID_ANY, "Save as Individual C&hapter Files…",
            "Split the open audio into one file per chapter (lossless FFmpeg copy)")
        self.mi_cancel = file_menu.Append(wx.ID_ANY, "&Cancel Build\tEsc",
                                          "Cancel a build in progress")
        file_menu.AppendSeparator()
        self.mi_load_job = file_menu.Append(
            wx.ID_ANY, "&Load a Saved Setup…\tCtrl+L",
            "Load a .cfjob file that defines order, titles and tags")
        self.mi_gen_job = file_menu.Append(
            wx.ID_ANY, "Sa&ve This Setup as a Template…\tCtrl+Shift+G",
            "Save the current chapters and tags as a reusable .cfjob file")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_EXIT, "E&xit\tAlt+F4", "Close ChapterForge")
        menubar.Append(file_menu, "&File")

        edit_menu = wx.Menu()
        self.mi_undo = edit_menu.Append(wx.ID_UNDO, "&Undo\tCtrl+Z",
                                        "Undo the last chapter list change")
        self.mi_redo = edit_menu.Append(wx.ID_REDO, "&Redo\tCtrl+Y",
                                        "Redo the last undone change")
        edit_menu.AppendSeparator()
        self.mi_edit_chapter = edit_menu.Append(
            wx.ID_ANY, "Edit Chapter &Details…\tF2",
            "Edit the selected chapter's title, link URL and cover image")
        self.mi_batch_titles = edit_menu.Append(
            wx.ID_ANY, "Batch &Edit Titles…",
            "Apply a transformation to all chapter titles at once")
        self.mi_rename_files = edit_menu.Append(
            wx.ID_ANY, "Rename &Source Files…",
            "Rename the source MP3 files using a pattern based on chapter titles")
        edit_menu.AppendSeparator()
        self.mi_play_chapter = edit_menu.Append(
            wx.ID_ANY, "&Play This Chapter",
            "Load the selected chapter in the audio player and begin playback")
        self.mi_split_here = edit_menu.Append(
            wx.ID_ANY, "S&plit Here",
            "Insert a chapter boundary at the player's current position (edit mode only)")
        edit_menu.AppendSeparator()
        self.mi_edit_up = edit_menu.Append(
            wx.ID_ANY, "Move &Up\tAlt+Up",
            "Move the selected chapter one position earlier")
        self.mi_edit_down = edit_menu.Append(
            wx.ID_ANY, "Move &Down\tAlt+Down",
            "Move the selected chapter one position later")
        edit_menu.AppendSeparator()
        self.mi_edit_remove = edit_menu.Append(
            wx.ID_ANY, "Re&move Chapter",
            "Remove the selected chapter (build), or merge it into the one above (edit mode)")
        edit_menu.AppendSeparator()
        self.mi_import_ch = edit_menu.Append(
            wx.ID_ANY, "&Load Chapter List From File…",
            "Replace the chapter markers of the open master from a label file")
        self.mi_export_ch = edit_menu.Append(
            wx.ID_ANY, "Sa&ve Chapter List…",
            "Save the current chapter list as labels, a CUE sheet or JSON")
        menubar.Append(edit_menu, "&Edit")

        view_menu = wx.Menu()
        theme_sub = wx.Menu()
        self.mi_theme_system = theme_sub.AppendRadioItem(
            wx.ID_ANY, "Follow &System",
            "Use your Windows color scheme")
        self.mi_theme_light = theme_sub.AppendRadioItem(
            wx.ID_ANY, "&Light",
            "White background with dark text")
        self.mi_theme_dark = theme_sub.AppendRadioItem(
            wx.ID_ANY, "&Dark",
            "Dark background with light text")
        self.mi_theme_hc = theme_sub.AppendRadioItem(
            wx.ID_ANY, "&High Contrast",
            "Black background with white text for maximum legibility")
        view_menu.AppendSubMenu(theme_sub, "&Theme", "Change the color theme")
        view_menu.AppendSeparator()
        self.mi_go_step1 = view_menu.Append(
            wx.ID_ANY, "Go to &Chapters (Step 1)\tCtrl+1",
            "Show the chapter list - Step 1 of the two-step workflow")
        self.mi_go_step2 = view_menu.Append(
            wx.ID_ANY, "Go to Tags && &Build (Step 2)\tCtrl+2",
            "Show the tags and build page - Step 2 of the two-step workflow")
        self.mi_goto_time = view_menu.Append(
            wx.ID_ANY, "&Go to Time…\tCtrl+G",
            "Jump the player to a specific time position")
        view_menu.AppendSeparator()
        self.mi_text_larger = view_menu.Append(
            wx.ID_ANY, "Larger &Text\tCtrl+=",
            "Increase the text size")
        self.mi_text_smaller = view_menu.Append(
            wx.ID_ANY, "Smaller T&ext\tCtrl+-",
            "Decrease the text size")
        self.mi_text_reset = view_menu.Append(
            wx.ID_ANY, "Reset Text &Size\tCtrl+0",
            "Reset the text size to the default")
        view_menu.AppendSeparator()
        self.mi_show_player = view_menu.AppendCheckItem(
            wx.ID_ANY, "Show Audio &Player",
            "Show or hide the audio player panel")
        # Player starts hidden - it has nothing to show until media is loaded.
        self.mi_show_player.Check(False)
        # Columns submenu (Feature 10)
        col_sub = wx.Menu()
        self.mi_col = []
        for _ci, _cn in enumerate(["Title", "Start", "Duration", "Source File"]):
            _mi_c = col_sub.AppendCheckItem(
                wx.ID_ANY, _cn, f"Show or hide the {_cn} column")
            self.mi_col.append(_mi_c)
        view_menu.AppendSubMenu(col_sub, "&Columns", "Show or hide chapter list columns")
        # Initialise theme radio to match stored setting
        _t = self.settings.get("theme", "system")
        if _t == "system" and self.settings.get("high_contrast", False):
            _t = "high_contrast"
        {
            "system":        self.mi_theme_system,
            "light":         self.mi_theme_light,
            "dark":          self.mi_theme_dark,
            "high_contrast": self.mi_theme_hc,
        }.get(_t, self.mi_theme_system).Check(True)
        menubar.Append(view_menu, "&View")

        tools_menu = wx.Menu()
        self.mi_silence = tools_menu.Append(
            wx.ID_ANY, "Find Chapters in Silent &Gaps…",
            "Detect chapters in an audio file from silent gaps")
        self.mi_batch = tools_menu.Append(
            wx.ID_ANY, "Build &Multiple Books…",
            "Build a master for every sub-folder of books at once")
        tools_menu.AppendSeparator()
        self.mi_watch = tools_menu.Append(
            wx.ID_ANY, "Set Up &Automatic Building…\tCtrl+W",
            "Manage reusable watch-folder processes")
        self.mi_start_watch = tools_menu.Append(
            wx.ID_ANY, "&Auto-Build in Background",
            "Minimize to the system tray and watch folders automatically")
        from . import autostart
        self.mi_autostart = tools_menu.AppendCheckItem(
            wx.ID_ANY, "Auto-Build When I &Sign In",
            "Run the background watcher automatically when you sign in")
        self.mi_autostart.Enable(autostart.is_supported())
        if autostart.is_supported():
            self.mi_autostart.Check(autostart.is_enabled())
        tools_menu.AppendSeparator()
        self.mi_acx_check = tools_menu.Append(
            wx.ID_ANY, "Check &ACX Compliance…",
            "Measure the current output file for ACX loudness and peak requirements")
        self.mi_lookup = tools_menu.Append(
            wx.ID_ANY, "Look Up &Metadata…",
            "Search MusicBrainz or Open Library to pre-fill title, artist and genre")
        self.mi_merge_short = tools_menu.Append(
            wx.ID_ANY, "&Merge Short Chapters…",
            "Collapse chapters shorter than a minimum duration into the previous chapter")
        self.mi_build_log = tools_menu.Append(
            wx.ID_ANY, "View &Build Log…",
            "View a log of recent build activity")
        tools_menu.AppendSeparator()
        self.mi_palette = tools_menu.Append(
            wx.ID_ANY, "Command &Palette…\tCtrl+Shift+P",
            "Search and run any command by name")
        self.mi_settings = tools_menu.Append(
            wx.ID_PREFERENCES, "&Settings…\tCtrl+,",
            "Edit ChapterForge preferences")
        menubar.Append(tools_menu, "&Tools")

        auphonic_menu = wx.Menu()
        self.mi_auphonic_connect = auphonic_menu.Append(
            wx.ID_ANY, "&Connect Account…",
            "Connect your Auphonic account and view your credit balance")
        self.mi_auphonic_new = auphonic_menu.Append(
            wx.ID_ANY, "&New Production…",
            "Submit audio to Auphonic for processing")
        self.mi_auphonic_history = auphonic_menu.Append(
            wx.ID_ANY, "&Job History…",
            "View submitted Auphonic jobs and download results")
        # Only append Auphonic menu if beta features are enabled
        if self.settings.get("beta_features", False):
            menubar.Append(auphonic_menu, "&Auphonic")
            self._auphonic_menu_index = 4  # Store index for later enabling
        else:
            self._auphonic_menu_index = None

        help_menu = wx.Menu()
        self.mi_wizard = help_menu.Append(
            wx.ID_ANY, "Setup &Wizard…",
            "Walk through the guided setup wizard to configure ChapterForge")
        help_menu.AppendSeparator()
        self.mi_guide = help_menu.Append(
            wx.ID_ANY, "&User Guide\tCtrl+F1", "Open the User Guide in your browser")
        self.mi_context_help = help_menu.Append(
            wx.ID_ANY, "&Help on This Control\tF1",
            "Show help for whichever control currently has keyboard focus")
        self.mi_keys = help_menu.Append(
            wx.ID_ANY, "&Keyboard Shortcuts\tCtrl+/",
            "Open the keyboard shortcuts reference in your browser")
        self.mi_changelog = help_menu.Append(
            wx.ID_ANY, "Release &Notes",
            "Open the changelog / release notes")
        self.mi_docs_home = help_menu.Append(
            wx.ID_ANY, "All D&ocumentation…",
            "Open the documentation home page")
        help_menu.AppendSeparator()
        self.mi_report_issue = help_menu.Append(
            wx.ID_ANY, "&Report an Issue…",
            "Submit a bug report or feature request directly to the ChapterForge team")
        self.mi_diagnostics = help_menu.Append(
            wx.ID_ANY, "Get &Help Information…",
            "Save a text report of versions and settings for support")
        self.mi_update = help_menu.Append(
            wx.ID_ANY, "&Look for Updates…",
            "Check online for a newer version of ChapterForge")
        self.mi_download_ffmpeg = help_menu.Append(
            wx.ID_ANY, "&Download FFmpeg…",
            "Download and install FFmpeg if it is missing from your system")
        help_menu.AppendSeparator()
        self.mi_feature_flags = help_menu.Append(
            wx.ID_ANY, "Feature &Flags…",
            "Show or hide optional features")
        self.mi_reset_feature_flags = help_menu.Append(
            wx.ID_ANY, "&Reset Feature Flags to Defaults",
            "Re-enable every optional feature")
        help_menu.AppendSeparator()
        help_menu.Append(wx.ID_ABOUT, "&About ChapterForge")
        menubar.Append(help_menu, "&Help")

        self.SetMenuBar(menubar)
        
        # Enable Auphonic menu after menu bar is attached to frame
        if hasattr(self, '_auphonic_menu_index') and self._auphonic_menu_index is not None:
            self.GetMenuBar().EnableTop(self._auphonic_menu_index, 
                                        bool(self.settings.get("beta_features", False)))

        self.Bind(wx.EVT_MENU, self._on_undo, self.mi_undo)
        self.Bind(wx.EVT_MENU, self._on_redo, self.mi_redo)
        self.Bind(wx.EVT_MENU, self._on_open, self.mi_open)
        self.Bind(wx.EVT_MENU, self._on_open_master, self.mi_open_master)
        self.Bind(wx.EVT_MENU, self._on_set_output, self.mi_output)
        self.Bind(wx.EVT_MENU, self._on_build, self.mi_build)
        self.Bind(wx.EVT_MENU, self._on_save_edit, self.mi_save_edit)
        self.Bind(wx.EVT_MENU, self._on_save_as, self.mi_save_as)
        self.Bind(wx.EVT_MENU, self._on_save_split_files, self.mi_split_files)
        self.Bind(wx.EVT_MENU, self._on_cancel, self.mi_cancel)
        self.Bind(wx.EVT_MENU, self._on_load_job, self.mi_load_job)
        self.Bind(wx.EVT_MENU, self._on_generate_job, self.mi_gen_job)
        self.Bind(wx.EVT_MENU, self._on_edit_chapter, self.mi_edit_chapter)
        self.Bind(wx.EVT_MENU, self._on_batch_edit_titles, self.mi_batch_titles)
        self.Bind(wx.EVT_MENU, self._on_rename_source_files, self.mi_rename_files)
        self.Bind(wx.EVT_MENU, self._on_play_selected, self.mi_play_chapter)
        self.Bind(wx.EVT_MENU, self._on_split_chapter, self.mi_split_here)
        self.Bind(wx.EVT_MENU, lambda e: self._move(-1), self.mi_edit_up)
        self.Bind(wx.EVT_MENU, lambda e: self._move(1), self.mi_edit_down)
        self.Bind(wx.EVT_MENU, lambda e: self._remove_selected(), self.mi_edit_remove)
        self.Bind(wx.EVT_MENU, self._on_import_chapters, self.mi_import_ch)
        self.Bind(wx.EVT_MENU, self._on_export_chapters, self.mi_export_ch)
        self.Bind(wx.EVT_MENU, lambda e: self._apply_theme("system"), self.mi_theme_system)
        self.Bind(wx.EVT_MENU, lambda e: self._apply_theme("light"), self.mi_theme_light)
        self.Bind(wx.EVT_MENU, lambda e: self._apply_theme("dark"), self.mi_theme_dark)
        self.Bind(wx.EVT_MENU, lambda e: self._apply_theme("high_contrast"), self.mi_theme_hc)
        self.Bind(wx.EVT_MENU, self._on_text_larger, self.mi_text_larger)
        self.Bind(wx.EVT_MENU, self._on_text_smaller, self.mi_text_smaller)
        self.Bind(wx.EVT_MENU, self._on_text_reset, self.mi_text_reset)
        self.Bind(wx.EVT_MENU, self._on_back_page, self.mi_go_step1)
        self.Bind(wx.EVT_MENU, self._on_next_page, self.mi_go_step2)
        self.Bind(wx.EVT_MENU, self._on_goto_time, self.mi_goto_time)
        self.Bind(wx.EVT_MENU, self._on_view_player, self.mi_show_player)
        for _ci2, _mi_col in enumerate(self.mi_col):
            self.Bind(wx.EVT_MENU,
                      lambda e, idx=_ci2 + 1: self._on_toggle_column(idx),
                      _mi_col)
        self.Bind(wx.EVT_MENU, self._on_silence, self.mi_silence)
        self.Bind(wx.EVT_MENU, self._on_batch, self.mi_batch)
        self.Bind(wx.EVT_MENU, self._on_acx_check_menu, self.mi_acx_check)
        self.Bind(wx.EVT_MENU, self._on_lookup_metadata, self.mi_lookup)
        self.Bind(wx.EVT_MENU, self._on_merge_short_chapters, self.mi_merge_short)
        self.Bind(wx.EVT_MENU, self._on_view_build_log, self.mi_build_log)
        self.Bind(wx.EVT_MENU, self._on_settings, self.mi_settings)
        self.Bind(wx.EVT_MENU, self._open_command_palette, self.mi_palette)
        self.Bind(wx.EVT_MENU, self._on_watch_folders, self.mi_watch)
        self.Bind(wx.EVT_MENU, self._on_start_watcher, self.mi_start_watch)
        self.Bind(wx.EVT_MENU, self._on_toggle_autostart, self.mi_autostart)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(), id=wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, self._on_wizard, self.mi_wizard)
        self.Bind(wx.EVT_MENU, self._on_guide, self.mi_guide)
        self.Bind(wx.EVT_MENU, self._on_context_help, self.mi_context_help)
        self.Bind(wx.EVT_MENU, self._on_keys, self.mi_keys)
        self.Bind(wx.EVT_MENU, self._on_changelog_doc, self.mi_changelog)
        self.Bind(wx.EVT_MENU, self._on_docs_home, self.mi_docs_home)
        self.Bind(wx.EVT_MENU, self._on_report_issue, self.mi_report_issue)
        self.Bind(wx.EVT_MENU, self._on_save_diagnostics, self.mi_diagnostics)
        self.Bind(wx.EVT_MENU, self._on_check_updates, self.mi_update)
        self.Bind(wx.EVT_MENU, self._on_download_ffmpeg, self.mi_download_ffmpeg)
        self.Bind(wx.EVT_MENU, self._on_feature_flags, self.mi_feature_flags)
        self.Bind(wx.EVT_MENU, self._on_reset_feature_flags, self.mi_reset_feature_flags)
        self.Bind(wx.EVT_MENU, self._on_about, id=wx.ID_ABOUT)

        self.Bind(wx.EVT_MENU, self._on_auphonic_connect, self.mi_auphonic_connect)
        self.Bind(wx.EVT_MENU, self._on_auphonic_new, self.mi_auphonic_new)
        self.Bind(wx.EVT_MENU, self._on_auphonic_history, self.mi_auphonic_history)

        # Ctrl+S = smart save: Build in build mode, Save Changes in edit mode.
        # (Ctrl+B = explicit Build.)
        _smart_save_id = wx.NewIdRef()
        _palette_id = wx.NewIdRef()
        self.Bind(wx.EVT_MENU, self._on_smart_save, id=_smart_save_id)
        self.Bind(wx.EVT_MENU, self._open_command_palette, id=_palette_id)
        self.SetAcceleratorTable(wx.AcceleratorTable([
            (wx.ACCEL_CTRL, ord('S'), _smart_save_id),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('P'), _palette_id),
        ]))

        # Feature flags: detach (not destroy) menu items for disabled features,
        # so they vanish from the user's menus while self.mi_xxx stays a valid
        # MenuItem for any later .Bind()/.Enable()/.Check() calls elsewhere.
        for _menu, _item, _flag_key in (
            (edit_menu, self.mi_play_chapter, "audio_player"),
            (edit_menu, self.mi_split_here, "audio_player"),
            (view_menu, self.mi_goto_time, "audio_player"),
            (view_menu, self.mi_show_player, "audio_player"),
            (tools_menu, self.mi_palette, "command_palette"),
            (tools_menu, self.mi_silence, "silence_chapter_detection"),
            (tools_menu, self.mi_lookup, "metadata_lookup"),
            (tools_menu, self.mi_acx_check, "acx_compliance"),
            (tools_menu, self.mi_batch, "batch_build"),
            (tools_menu, self.mi_merge_short, "merge_short_chapters"),
            (tools_menu, self.mi_watch, "auto_build_watcher"),
            (tools_menu, self.mi_start_watch, "auto_build_watcher"),
            (tools_menu, self.mi_autostart, "auto_build_watcher"),
        ):
            if not feature_flags.is_enabled(self.settings, _flag_key):
                _menu.Remove(_item)

    def _on_smart_save(self, _evt):
        """Ctrl+S: save in whatever way makes sense for the current mode."""
        if self._is_building():
            return
        if self.mode == 'edit':
            if self._edit_is_mp3():
                self._on_save_edit(None)
            else:
                self._announce(
                    "This file is an M4B, so in-place saving is not available. "
                    "Use File → Save As to write a copy with the updated tags.")
        else:
            self._on_build(None)

    def _label(self, parent, text, name=None):
        lbl = wx.StaticText(parent, label=text)
        if name:
            lbl.SetName(name)
        return lbl

    def _build_ui(self):
        panel = wx.Panel(self)
        panel.SetName("ChapterForge")
        outer = wx.BoxSizer(wx.VERTICAL)
        _ACV = wx.ALIGN_CENTER_VERTICAL

        # ── Source row (simplified for accessibility) ───────────────────────────────────
        src_box = wx.StaticBoxSizer(wx.HORIZONTAL, panel, "Source")
        self.src_static_box = src_box.GetStaticBox()
        self.src_label = self._label(panel, "Current file or folder:")
        src_box.Add(self.src_label, 0, _ACV | wx.ALL, 6)
        self.folder_ctrl = wx.TextCtrl(panel, style=wx.TE_READONLY)
        self.folder_ctrl.SetName("Source folder or file")
        self.folder_ctrl.SetHint("No folder chosen yet")
        src_box.Add(self.folder_ctrl, 1, _ACV | wx.ALL, 6)
        outer.Add(src_box, 0, wx.EXPAND | wx.ALL, 8)

        # ── Page 1: Chapter list + options ────────────────────────────────
        self._page_ch = wx.Panel(panel)
        self._page_ch.SetName("Step 1 - Chapters")
        p1 = wx.BoxSizer(wx.VERTICAL)

        ch_box = wx.StaticBoxSizer(wx.VERTICAL, self._page_ch, "Chapters")
        self.ch_list_label = self._label(
            self._page_ch, "Chapter &list (one per source file):")
        ch_box.Add(self.ch_list_label, 0, wx.ALL, 4)
        self.list = wx.ListCtrl(
            self._page_ch, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN)
        self.list.SetName(
            "Chapters list - up and down arrows to move between chapters, "
            "left and right arrows to read across columns")
        self.list.InsertColumn(0, "#", width=44)
        self.list.InsertColumn(1, "Title", width=260)
        self.list.InsertColumn(2, "Start", width=80)
        self.list.InsertColumn(3, "Duration", width=80)
        self.list.InsertColumn(4, "Source file", width=200)
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_list_select)
        self.list.Bind(wx.EVT_LIST_ITEM_DESELECTED, self._on_list_select)
        self.list.Bind(wx.EVT_LIST_ITEM_FOCUSED, self._on_list_focused)
        self.list.Bind(wx.EVT_KEY_DOWN, self._on_list_key)
        self.list.Bind(wx.EVT_CONTEXT_MENU, self._on_list_context_menu)
        ch_box.Add(self.list, 1, wx.EXPAND | wx.ALL, 4)

        edit_row = wx.BoxSizer(wx.HORIZONTAL)
        edit_row.Add(self._label(self._page_ch, "Selected chapter &title:"),
                     0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)
        self.title_ctrl = wx.TextCtrl(self._page_ch, style=wx.TE_PROCESS_ENTER)
        self.title_ctrl.SetName("Selected chapter title - type to rename, press Enter to apply")
        self.title_ctrl.Bind(wx.EVT_TEXT_ENTER, self._on_apply_title)
        self.title_ctrl.Bind(wx.EVT_KILL_FOCUS, self._on_apply_title)
        edit_row.Add(self.title_ctrl, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)
        ch_box.Add(edit_row, 0, wx.EXPAND)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_edit = wx.Button(self._page_ch, label="Set &Link && Image…")
        self.btn_edit.SetName("Set link URL and image for this chapter")
        self.btn_edit.SetToolTip(
            "Open a dialog to set this chapter's link URL and cover image.\n"
            "To rename the chapter, just type in the title field above.")
        self.btn_edit.Bind(wx.EVT_BUTTON, self._on_edit_chapter)
        self.btn_up = wx.Button(self._page_ch, label="Move &Up")
        self.btn_up.SetName("Move selected chapter up one position")
        self.btn_up.Bind(wx.EVT_BUTTON, lambda e: self._move(-1))
        self.btn_down = wx.Button(self._page_ch, label="Move &Down")
        self.btn_down.SetName("Move selected chapter down one position")
        self.btn_down.Bind(wx.EVT_BUTTON, lambda e: self._move(1))
        self.btn_remove = wx.Button(self._page_ch, label="Re&move")
        self.btn_remove.SetName("Remove selected chapter from the list")
        self.btn_remove.Bind(wx.EVT_BUTTON, lambda e: self._remove_selected())
        self.btn_play_sel = wx.Button(self._page_ch, label="&Play Chapter")
        self.btn_play_sel.SetName("Play the selected chapter in the player below")
        self.btn_play_sel.SetToolTip("Jump the player to this chapter and start playing.")
        self.btn_play_sel.Bind(wx.EVT_BUTTON, self._on_play_selected)
        self.btn_split = wx.Button(self._page_ch, label="S&plit Here")
        self.btn_split.SetName("Split the current chapter at the player playhead position")
        self.btn_split.SetToolTip(
            "Divide the chapter the player is currently inside into two "
            "chapters at the playhead position.")
        self.btn_split.Bind(wx.EVT_BUTTON, self._on_split_chapter)
        for b in (self.btn_edit, self.btn_up, self.btn_down, self.btn_remove,
                  self.btn_play_sel, self.btn_split):
            btn_row.Add(b, 0, wx.ALL, 4)
        ch_box.Add(btn_row, 0)
        p1.Add(ch_box, 1, wx.EXPAND | wx.ALL, 8)

        # "Next" button - goes to the tags / build page
        next_row = wx.BoxSizer(wx.HORIZONTAL)
        next_row.AddStretchSpacer()
        self.btn_next_page = wx.Button(self._page_ch, label="Set Tags && Build ->")
        self.btn_next_page.SetName(
            "Continue to step 2 - set title, artist, album and other tags, then build")
        self.btn_next_page.SetToolTip(
            "Move to the next step to set the master file's tags and build.")
        self.btn_next_page.Bind(wx.EVT_BUTTON, self._on_next_page)
        next_row.Add(self.btn_next_page, 0, wx.ALL, 8)
        p1.Add(next_row, 0, wx.EXPAND)

        self._page_ch.SetSizer(p1)
        outer.Add(self._page_ch, 1, wx.EXPAND)

        # ── Page 2: Tags, output, build ───────────────────────────────────
        self._page_tags = wx.Panel(panel)
        self._page_tags.SetName("Step 2 - Tags and Build")
        self._page_tags.Hide()
        p2 = wx.BoxSizer(wx.VERTICAL)

        back_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_back_page = wx.Button(self._page_tags, label="<- Back to Chapters")
        self.btn_back_page.SetName("Back to step 1 - the chapter list")
        self.btn_back_page.Bind(wx.EVT_BUTTON, self._on_back_page)
        back_row.Add(self.btn_back_page, 0, wx.ALL, 8)
        back_row.AddStretchSpacer()
        p2.Add(back_row, 0, wx.EXPAND)

        tag_box = wx.StaticBoxSizer(wx.VERTICAL, self._page_tags, "Master MP3 Tags")
        grid = wx.FlexGridSizer(0, 2, 6, 6)
        grid.AddGrowableCol(1, 1)

        def add_field(label, name, multiline=False):
            grid.Add(self._label(self._page_tags, label), 0, wx.ALIGN_CENTER_VERTICAL)
            style = wx.TE_MULTILINE if multiline else 0
            ctrl = wx.TextCtrl(self._page_tags, style=style,
                               size=(220, 60 if multiline else -1))
            ctrl.SetName(name)
            grid.Add(ctrl, 1, wx.EXPAND)
            return ctrl

        self.tag_title = add_field("&Title:", "Master title")
        self.tag_artist = add_field("&Artist:", "Artist")
        self.tag_album = add_field("Al&bum:", "Album")
        self.tag_album_artist = add_field("Album a&rtist:", "Album artist")
        self.tag_genre = add_field("&Genre:", "Genre")
        self.tag_year = add_field("&Year:", "Year")
        self.tag_comment = add_field("Co&mment:", "Comment", multiline=True)
        self.tag_narrator = add_field("N&arrator:", "Narrator")
        self.tag_series = add_field("Series &title:", "Series title")
        self.tag_series_idx = add_field("Series inde&x:", "Series index")
        tag_box.Add(grid, 0, wx.EXPAND | wx.ALL, 4)

        cover_row = wx.BoxSizer(wx.HORIZONTAL)
        cover_row.Add(self._label(self._page_tags, "Co&ver image:"),
                      0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)
        self.cover_ctrl = wx.TextCtrl(self._page_tags, style=wx.TE_READONLY)
        self.cover_ctrl.SetName("Cover image path")
        self.cover_ctrl.SetHint("Optional JPEG or PNG")
        cover_row.Add(self.cover_ctrl, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)
        self.btn_cover = wx.Button(self._page_tags, label="Browse for &Cover Image…")
        self.btn_cover.SetName("Browse for cover image")
        self.btn_cover.SetToolTip("Choose a JPEG or PNG to embed as album art.")
        self.btn_cover.Bind(wx.EVT_BUTTON, self._on_choose_cover)
        cover_row.Add(self.btn_cover, 0, wx.ALL, 4)
        self.btn_cover_clear = wx.Button(self._page_tags, label="Remove &Cover")
        self.btn_cover_clear.SetName("Remove the cover image from this master file")
        self.btn_cover_clear.SetToolTip(
            "Clear the selected cover art so the master has no album artwork.")
        self.btn_cover_clear.Bind(wx.EVT_BUTTON, self._on_clear_cover)
        cover_row.Add(self.btn_cover_clear, 0, wx.ALL, 4)
        tag_box.Add(cover_row, 0, wx.EXPAND)

        self._placeholder_bmp = wx.Bitmap(96, 96)
        self.cover_preview = wx.StaticBitmap(self._page_tags, bitmap=self._placeholder_bmp)
        self.cover_preview.SetName("Cover preview")
        tag_box.Add(self.cover_preview, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, 4)
        p2.Add(tag_box, 0, wx.EXPAND | wx.ALL, 8)

        out_box = wx.StaticBoxSizer(wx.HORIZONTAL, self._page_tags, "Output")
        out_box.Add(self._label(self._page_tags, "Master &output file:"),
                    0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)
        self.output_ctrl = wx.TextCtrl(self._page_tags, style=wx.TE_READONLY)
        self.output_ctrl.SetName("Output file path - use File menu, Save Master As to change")
        self.output_ctrl.SetHint("Auto-set when you open a folder - or use File → Save Master As… to choose")
        out_box.Add(self.output_ctrl, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)
        self._out_sizer = out_box
        p2.Add(out_box, 0, wx.EXPAND | wx.ALL, 8)

        self.estimate_text = wx.StaticText(self._page_tags, label="")
        self.estimate_text.SetName("Estimated output size")
        p2.Add(self.estimate_text, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        action_row = wx.BoxSizer(wx.HORIZONTAL)
        self.action_row_sizer = action_row
        self.btn_build = wx.Button(self._page_tags, label="Build Master MP&3")
        self.btn_build.SetName("Build master MP3")
        self.btn_build.SetToolTip(
            "Create the chaptered master file from the loaded MP3s.\n"
            "Requires a folder of files and an output path.")
        self.btn_build.Bind(wx.EVT_BUTTON, self._on_build)
        self.btn_build.SetDefault()
        self.btn_save_edit = wx.Button(self._page_tags, label="Sa&ve Changes")
        self.btn_save_edit.SetName("Save changes to the open master")
        self.btn_save_edit.Bind(wx.EVT_BUTTON, self._on_save_edit)
        self.btn_save_edit.Hide()
        self.btn_cancel = wx.Button(self._page_tags, label="Cancel")
        self.btn_cancel.SetName("Cancel build")
        self.btn_cancel.Bind(wx.EVT_BUTTON, self._on_cancel)
        action_row.Add(self.btn_build, 0, wx.ALL, 6)
        action_row.Add(self.btn_save_edit, 0, wx.ALL, 6)
        action_row.Add(self.btn_cancel, 0, wx.ALL, 6)
        self.gauge = wx.Gauge(self._page_tags, range=100, size=(220, -1))
        self.gauge.SetName("Build progress")
        action_row.Add(self.gauge, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)
        p2.Add(action_row, 0, wx.EXPAND | wx.ALL, 4)

        self._page_tags.SetSizer(p2)
        outer.Add(self._page_tags, 1, wx.EXPAND)

        # ── Always visible: status + player ──────────────────────────────
        self.status_text = wx.StaticText(
            panel,
            label="Choose a task above, or press Ctrl+Shift+P to search all commands.")
        self.status_text.SetName("Status")
        outer.Add(self.status_text, 0, wx.EXPAND | wx.ALL, 8)

        self.player = PlayerPanel(
            panel, announce=self._announce,
            get_skip_seconds=lambda: int(self.settings.get("skip_seconds", 10)),
            get_volume=lambda: int(self.settings.get("default_volume", 80)),
            get_pause_at_chapter_end=lambda: bool(
                self.settings.get("pause_at_chapter_end", False)),
            on_volume_change=self._on_player_volume,
            on_load_started=self._reveal_player)
        self.player.Bind(wx.EVT_CONTEXT_MENU, self._on_player_context_menu)
        outer.Add(self.player, 0, wx.EXPAND | wx.ALL, 8)
        # Hidden until a file is loaded - _reveal_player shows it as soon as
        # loading begins (the media backend needs the panel realized before
        # the load can complete, so we can't wait for EVT_MEDIA_LOADED).
        self.player.Hide()

        tray_row = wx.BoxSizer(wx.HORIZONTAL)
        tray_row.AddStretchSpacer()
        self.btn_tray = wx.Button(panel, label="Minimize to &Tray")
        self.btn_tray.SetName("Minimize ChapterForge to the system tray")
        self.btn_tray.SetToolTip(
            "Hide the window and keep ChapterForge running in the system tray.\n"
            "Double-click the tray icon to bring it back.")
        self.btn_tray.Bind(wx.EVT_BUTTON, self._on_minimize_to_tray)
        tray_row.Add(self.btn_tray, 0, wx.RIGHT | wx.BOTTOM, 8)
        outer.Add(tray_row, 0, wx.EXPAND)

        self._outer_sizer = outer
        panel.SetSizer(outer)
        self.panel = panel

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _announce(self, message: str):
        self.status_text.SetLabel(message)
        self.SetStatusText(message)
        a11y.announce(message)

    def _is_building(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def _confirm_discard_edits(self) -> bool:
        """Return True if it is safe to replace the current edit session."""
        if self.mode != "edit" or not self.edit_dirty:
            return True
        return wx.MessageBox(
            "You have unsaved changes. Discard them?",
            "Unsaved changes", wx.YES_NO | wx.ICON_QUESTION, self) == wx.YES

    def _row_count(self) -> int:
        return (len(self.edit_chapters) if self.mode == "edit"
                else len(self.items))

    def _reveal_player(self):
        """Ensure the player is visible whenever media loading is requested.

        Must happen before the load runs - the Windows media backend needs a
        visible, realized HWND to attach to, and EVT_MEDIA_LOADED never fires
        on a hidden panel. The player starts hidden and is shown here on the
        first load; if the user later hides it via the View menu, playing a
        chapter shows it again so playback can attach.
        """
        if not feature_flags.is_enabled(self.settings, "audio_player"):
            return
        if self.player.IsShown():
            return
        self._player_revealed = True
        self.player.Show(True)
        self.mi_show_player.Check(True)
        self.panel.Layout()

    def _update_command_state(self):
        building = self._is_building()
        edit = self.mode == "edit"
        has_items = bool(self.items)
        count = self._row_count()
        sel = self.list.GetFirstSelected() if count else -1
        for ctrl in (self.btn_build, self.btn_cover, self.btn_cover_clear):
            ctrl.Enable(not building)
        # List is always enabled so screen readers can find and navigate it
        self.list.Enable(not building)
        self.title_ctrl.Enable(not building and sel >= 0)
        # Tag fields are only tabbable when in build mode with items or edit mode with content
        for ctrl in (self.tag_title, self.tag_artist, self.tag_album,
                     self.tag_album_artist, self.tag_genre, self.tag_year,
                     self.tag_comment, self.tag_narrator, self.tag_series,
                     self.tag_series_idx):
            ctrl.Enable(not building and count > 0)
        self.btn_build.Enable(not building and not edit and has_items
                              and bool(self.output_path))
        _ofmt = self.settings.get("output_format", "mp3")
        if _ofmt == "m4b":
            self.btn_build.SetLabel("Build M4B &Audiobook")
            self.btn_build.SetName("Build M4B audiobook")
        elif _ofmt == "flac":
            self.btn_build.SetLabel("Build FLAC &Master")
            self.btn_build.SetName("Build FLAC master")
        elif _ofmt == "opus":
            self.btn_build.SetLabel("Build Opus &Master")
            self.btn_build.SetName("Build Opus master")
        else:
            self.btn_build.SetLabel("Build Master MP&3")
            self.btn_build.SetName("Build master MP3")
        self.btn_remove.SetName(
            "Merge selected chapter into the one above it"
            if edit else
            "Remove selected chapter from the list")
        self.btn_edit.Enable(not building and sel >= 0)
        # Reorder works in both modes: build mode reorders source files,
        # edit mode swaps chapter labels while keeping time positions.
        self.btn_up.Enable(not building and sel > 0)
        self.btn_down.Enable(not building and 0 <= sel < count - 1)
        _edit_reorder_tip = (
            "Swap this chapter's name with the one above it.\n"
            "The audio content does not move - only the labels are swapped.")
        self.btn_up.SetToolTip(
            _edit_reorder_tip if edit else
            "Move the selected chapter one position earlier in the list.")
        self.btn_down.SetToolTip(
            _edit_reorder_tip if edit else
            "Move the selected chapter one position later in the list.")
        # Remove deletes a source chapter (build) or merges a boundary (edit).
        self.btn_remove.Enable(not building and sel >= 0
                               and (not edit or count > 1))
        self.btn_remove.SetLabel("Merge &Up" if edit else "Re&move")
        # Play-from-here: edit mode plays the loaded master; build mode auditions
        # the selected source file.
        self.btn_play_sel.Enable(not building and sel >= 0)
        # Split only applies to an existing master that is loaded in the player.
        self.btn_split.Show(edit)
        self.btn_split.Enable(not building and edit
                              and self.player.has_media())
        self.btn_cancel.Enable(building)
        can_save_edit = edit and not building and self._edit_is_mp3()
        self.btn_build.Show(not edit)
        self.btn_save_edit.Show(edit)
        self.btn_save_edit.Enable(can_save_edit)
        if edit and not self._edit_is_mp3():
            self.btn_save_edit.SetToolTip(
                "In-place saving is only supported for MP3 files.\n"
                "This file is an M4B - use File → Save As to save "
                "a copy with the updated chapter titles and tags.")
        else:
            self.btn_save_edit.SetToolTip(
                "Write updated chapter titles and tags directly into the open file.\n"
                "Keyboard shortcut: Ctrl+S or Ctrl+Shift+S.")
        self.action_row_sizer.Layout()
        self.mi_build.Enable(not building and not edit and has_items
                             and bool(self.output_path))
        self.mi_save_edit.Enable(can_save_edit)
        self.mi_save_as.Enable(not building and count > 0)
        self.mi_split_files.Enable(not building and edit and count > 1)
        self.mi_cancel.Enable(building)
        self.mi_open.Enable(not building)
        self.mi_open_master.Enable(not building)
        self.mi_output.Enable(not building and not edit)
        self.mi_load_job.Enable(not building)
        self.mi_gen_job.Enable(not building and not edit and has_items)
        self.mi_silence.Enable(not building)
        self.mi_batch.Enable(not building)
        self.mi_import_ch.Enable(not building and count > 0)
        self.mi_export_ch.Enable(not building and count > 0)
        # Edit menu
        self.mi_edit_chapter.Enable(not building and sel >= 0)
        self.mi_batch_titles.Enable(not building and count > 0)
        self.mi_rename_files.Enable(not building and not edit and count > 0)
        self.mi_play_chapter.Enable(not building and sel >= 0)
        self.mi_split_here.Enable(not building and edit and self.player.has_media())
        self.mi_edit_up.Enable(not building and sel > 0)
        self.mi_edit_down.Enable(not building and 0 <= sel < count - 1)
        self.mi_edit_remove.Enable(not building and sel >= 0
                                    and (not edit or count > 1))
        self.mi_edit_remove.SetItemLabel("Mer&ge Up" if edit else "Re&move Chapter")
        # Undo/redo
        self.mi_undo.Enable(self._undo.can_undo())
        self.mi_redo.Enable(self._undo.can_redo())
        self._update_undo_menu()
        # View menu - page navigation
        on_step2 = self._page_tags.IsShown()
        self.mi_go_step1.Enable(on_step2)
        self.mi_go_step2.Enable(not building and not on_step2 and has_items)
        self.mi_goto_time.Enable(self.player.has_media())

    def _update_undo_menu(self):
        self.mi_undo.SetItemLabel(f"{self._undo.undo_label()}\tCtrl+Z")
        self.mi_redo.SetItemLabel(f"{self._undo.redo_label()}\tCtrl+Y")

    def _on_undo(self, _evt):
        desc = self._undo.undo()
        if desc:
            self._refresh_list(select=self.list.GetFirstSelected())
            self._update_command_state()
            self._announce(f"Undid: {desc}.")

    def _on_redo(self, _evt):
        desc = self._undo.redo()
        if desc:
            self._refresh_list(select=self.list.GetFirstSelected())
            self._update_command_state()
            self._announce(f"Redid: {desc}.")

    def _edit_is_mp3(self) -> bool:
        return bool(self.edit_path) and core.output_format(self.edit_path) == "mp3"

    def _refresh_list(self, select: int = -1):
        self.list.DeleteAllItems()
        if self.mode == "edit":
            chapters = self.edit_chapters
            for i, ch in enumerate(chapters):
                row = self.list.InsertItem(i, str(i + 1))
                self.list.SetItem(row, 1, ch.title)
                self.list.SetItem(row, 2, core.format_timestamp(ch.start_ms))
                self.list.SetItem(row, 3, core.format_timestamp(ch.duration_ms))
                self.list.SetItem(row, 4, ch.url or "")
            count = len(chapters)
        else:
            chapters = core.compute_chapters(self.items)
            for i, (item, ch) in enumerate(zip(self.items, chapters)):
                row = self.list.InsertItem(i, str(i + 1))
                self.list.SetItem(row, 1, item.title)
                self.list.SetItem(row, 2, core.format_timestamp(ch.start_ms))
                self.list.SetItem(row, 3, core.format_timestamp(ch.duration_ms))
                self.list.SetItem(row, 4, item.filename)
            count = len(self.items)
        if 0 <= select < count:
            self.list.Select(select)
            self.list.Focus(select)
            self.list.EnsureVisible(select)
        self._update_command_state()
        self._update_estimate()
        # Auto-size the Title and last columns to their content.
        if self.list.GetItemCount() > 0:
            vis = self.settings.get("list_columns", [True] * 5)
            if len(vis) > 1 and vis[1]:
                self.list.SetColumnWidth(1, wx.LIST_AUTOSIZE)
                self.list.SetColumnWidth(1, max(120, min(self.list.GetColumnWidth(1), 360)))
            if len(vis) > 4 and vis[4]:
                self.list.SetColumnWidth(4, wx.LIST_AUTOSIZE)
                self.list.SetColumnWidth(4, max(80, min(self.list.GetColumnWidth(4), 260)))
        self._apply_column_visibility()
        # Force UI refresh to ensure changes are visible
        self.list.Refresh()
        self.panel.Layout()

    # ------------------------------------------------------------------
    # Folder / output / cover
    # ------------------------------------------------------------------
    def _on_open(self, _evt):
        if self._is_building():
            return
        start_dir = self.settings.get("last_input_dir", "") or ""
        dlg = wx.DirDialog(self, "Choose a folder of MP3 files",
                           defaultPath=start_dir,
                           style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            self._load_folder(dlg.GetPath())
        dlg.Destroy()

    def _load_folder(self, folder: str):
        if not self._confirm_discard_edits():
            return
        self._announce("Scanning folder…")
        wx.BeginBusyCursor()
        try:
            items, skipped_masters = core.scan_folder_detailed(folder)
        except core.ChapterForgeError as exc:
            wx.MessageBox(str(exc), "Could not scan folder",
                          wx.OK | wx.ICON_ERROR, self)
            return
        finally:
            if wx.IsBusy():
                wx.EndBusyCursor()

        good = [it for it in items if not it.error and it.duration > 0]
        skipped = [it for it in items if it.error or it.duration <= 0]

        if not good:
            wx.MessageBox(
                "No usable MP3 files were found in that folder.",
                "Nothing to do", wx.OK | wx.ICON_WARNING, self)
            self._announce("No usable MP3 files found.")
            return

        self.folder = folder
        self.items = good
        self.player.release(recreate=True)
        self._undo.clear()
        self._update_undo_menu()
        self._enter_build_mode()
        self.folder_ctrl.SetValue(folder)
        self.settings["last_input_dir"] = folder

        core.apply_title_source(good, self._current_title_source(),
                                respect_edits=False)
        for i, it in enumerate(good):
            if not it.title.strip():
                it.title = f"Chapter {i + 1}"
                it.file_title = it.title

        base = os.path.basename(os.path.normpath(folder))
        self.tag_title.SetValue(base)
        self.tag_album.SetValue(base)
        if not self.output_path:
            self._set_suggested_output(folder)

        # Auto-detect a cover image unless the user already chose one.
        if self.settings.get("auto_cover", True) and not self.cover_ctrl.GetValue():
            found = core.find_cover(folder)
            if found:
                self._set_cover(found)

        self._refresh_list(select=0)
        total = core.compute_chapters(good)[-1].end_ms
        msg = (f"Loaded {len(good)} file(s), total {core.format_timestamp(total)}."
               f" Ready to build.")
        if skipped_masters:
            msg += f" Skipped {len(skipped_masters)} existing master file(s)."
        if skipped:
            msg += f" Skipped {len(skipped)} unreadable file(s)."
        self._announce(msg)
        self._push_recent(folder)
        self._update_estimate()
        self.list.SetFocus()

    def _current_output_ext(self) -> str:
        fmt = self.settings.get("output_format", "mp3")
        if fmt == "m4b":
            return ".m4b"
        if fmt == "flac":
            return ".flac"
        if fmt == "opus":
            return ".opus"
        return ".mp3"

    def _on_set_output(self, _evt) -> bool:
        if self._is_building():
            return False
        ext = self._current_output_ext()
        default_dir = (os.path.dirname(self.output_path)
                       or self.settings.get("last_output_dir", "")
                       or self.folder or "")
        default_file = os.path.basename(self.output_path) or f"Master{ext}"
        if ext == ".m4b":
            wildcard = "M4B audiobook (*.m4b)|*.m4b"
        elif ext == ".flac":
            wildcard = "FLAC lossless (*.flac)|*.flac"
        else:
            wildcard = "MP3 files (*.mp3)|*.mp3"
        dlg = wx.FileDialog(
            self, "Save master as", defaultDir=default_dir,
            defaultFile=default_file, wildcard=wildcard,
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        confirmed = dlg.ShowModal() == wx.ID_OK
        if confirmed:
            path = dlg.GetPath()
            if not path.lower().endswith(ext):
                path += ext
            self._set_output_path(path, auto=False)
        dlg.Destroy()
        return confirmed

    def _apply_appearance(self):
        """Apply text-scale and colour theme to the whole frame recursively."""
        scale = max(50, min(300, int(self.settings.get("text_scale", 100))))
        base = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        font = wx.Font(base)
        pt = max(6, int(round(base.GetPointSize() * scale / 100.0)))
        font.SetPointSize(pt)

        theme = self.settings.get("theme", "system")
        # Backwards compat: old boolean high_contrast setting
        if theme == "system" and self.settings.get("high_contrast", False):
            theme = "high_contrast"
        # Auto-follow Windows high-contrast mode when theme is "system".
        if theme == "system" and _windows_high_contrast_active():
            theme = "high_contrast"

        _THEMES = {
            "light":         (wx.Colour(255, 255, 255), wx.Colour(0,   0,   0)),
            "dark":          (wx.Colour(30,  30,  30),  wx.Colour(220, 220, 220)),
            "high_contrast": (wx.Colour(0,   0,   0),   wx.Colour(255, 255, 255)),
        }
        if theme in _THEMES:
            bg, fg = _THEMES[theme]
        else:
            bg, fg = wx.NullColour, wx.NullColour

        def walk(win):
            if isinstance(win, wx.media.MediaCtrl):
                return
            try:
                win.SetFont(font)
                win.SetForegroundColour(fg)
                win.SetBackgroundColour(bg)
            except Exception:
                pass
            for child in win.GetChildren():
                walk(child)

        if hasattr(self, "panel"):
            walk(self.panel)
            self.panel.Layout()
            self.panel.Refresh()

    def _set_output_path(self, path: str, auto: bool = False):
        self.output_path = path
        self._output_auto = auto
        self.output_ctrl.SetValue(path)
        self.settings["last_output_dir"] = os.path.dirname(path)
        self._update_command_state()

    def _set_suggested_output(self, folder: str):
        stem = os.path.splitext(core.suggested_output_path(folder))[0]
        self._set_output_path(stem + self._current_output_ext(), auto=True)

    def _on_choose_cover(self, _evt):
        start_dir = (self.settings.get("last_cover_dir", "")
                     or self.folder or "")
        dlg = wx.FileDialog(
            self, "Choose cover image", defaultDir=start_dir, wildcard=
            "Images (*.jpg;*.jpeg;*.png)|*.jpg;*.jpeg;*.png",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            self._set_cover(dlg.GetPath())
            self.settings["last_cover_dir"] = os.path.dirname(dlg.GetPath())
        dlg.Destroy()

    def _on_clear_cover(self, _evt):
        self.cover_ctrl.SetValue("")
        self.cover_preview.SetBitmap(self._placeholder_bmp)
        self.panel.Layout()

    def _set_cover(self, path: str):
        self.cover_ctrl.SetValue(path)
        self._update_cover_preview(path)

    def _update_cover_preview(self, path: str):
        bmp = self._placeholder_bmp
        if path and os.path.isfile(path):
            img = wx.Image()
            if img.LoadFile(path):
                w, h = img.GetWidth(), img.GetHeight()
                scale = min(96 / w, 96 / h) if w and h else 1
                img = img.Scale(max(1, int(w * scale)), max(1, int(h * scale)),
                                wx.IMAGE_QUALITY_HIGH)
                bmp = wx.Bitmap(img)
        self.cover_preview.SetBitmap(bmp)
        self.panel.Layout()

    # ------------------------------------------------------------------
    # Settings <-> UI
    # ------------------------------------------------------------------
    def _current_title_source(self) -> str:
        return self.settings.get("title_source", core.TITLE_SOURCE_FILENAME)

    def _apply_settings_to_ui(self):
        s = self.settings
        self.tag_artist.SetValue(s.get("artist", ""))
        self.tag_album_artist.SetValue(s.get("album_artist", ""))
        self.tag_genre.SetValue(s.get("genre", ""))
        self.tag_narrator.SetValue(s.get("narrator", ""))
        self.tag_series.SetValue(s.get("series_title", ""))
        self.tag_series_idx.SetValue(s.get("series_index", ""))
        self._update_estimate()
        # Feature 10: init column check states from settings
        vis = self.settings.get("list_columns", [True] * 5)
        for i, mi in enumerate(self.mi_col):
            mi.Check(bool(vis[i + 1]) if i + 1 < len(vis) else True)
        self._apply_column_visibility()
        # Feature 13: apply keyboard overrides
        self._apply_key_overrides()
        # Gate the Auphonic menu on the beta_features setting.
        self.GetMenuBar().EnableTop(4, bool(s.get("beta_features", False)))

    def _apply_column_visibility(self):
        """Show or hide list columns based on settings (Feature 10)."""
        vis = self.settings.get("list_columns", [True] * 5)
        for i, show in enumerate(vis):
            if i == 0:
                continue  # # column always visible
            w = self._COL_WIDTHS[i] if show else 0
            self.list.SetColumnWidth(i, w)

    def _on_toggle_column(self, col_idx: int):
        """Toggle visibility of list column *col_idx* (Feature 10)."""
        vis = list(self.settings.get("list_columns", [True] * 5))
        while len(vis) < 5:
            vis.append(True)
        vis[col_idx] = not vis[col_idx]
        self.settings["list_columns"] = vis
        settings_mod.save(self.settings)
        self.mi_col[col_idx - 1].Check(vis[col_idx])
        self._apply_column_visibility()
        col_name = self._COL_NAMES_DISPLAY[col_idx]
        self._announce(f"Column '{col_name}' {'shown' if vis[col_idx] else 'hidden'}.")

    def _gather_settings(self):
        s = self.settings
        s["artist"] = self.tag_artist.GetValue().strip()
        s["album_artist"] = self.tag_album_artist.GetValue().strip()
        s["genre"] = self.tag_genre.GetValue().strip()
        s["narrator"] = self.tag_narrator.GetValue().strip()
        s["series_title"] = self.tag_series.GetValue().strip()
        s["series_index"] = self.tag_series_idx.GetValue().strip()
        if not self.IsIconized():
            s["win_max"] = self.IsMaximized()
            if not self.IsMaximized():
                w, h = self.GetSize()
                x, y = self.GetPosition()
                s["win_w"], s["win_h"] = int(w), int(h)
                s["win_x"], s["win_y"] = int(x), int(y)

    def _save_settings(self):
        self._gather_settings()
        settings_mod.save(self.settings)

    # ------------------------------------------------------------------
    # Chapter list interaction
    # ------------------------------------------------------------------
    def _selected_title(self, sel: int) -> str:
        if self.mode == "edit":
            return self.edit_chapters[sel].title if 0 <= sel < len(self.edit_chapters) else ""
        return self.items[sel].title if 0 <= sel < len(self.items) else ""

    def _on_list_focused(self, evt):
        """Arrow-key navigation focuses without always selecting - force select so
        GetFirstSelected() is reliable and the play button stays enabled."""
        idx = evt.GetIndex()
        if 0 <= idx < self._row_count():
            self.list.Select(idx)
            self._list_col = 0  # reset to row-summary mode on Up/Down navigation
        evt.Skip()

    def _on_list_select(self, _evt):
        sel = self.list.GetFirstSelected()
        if 0 <= sel < self._row_count():
            self.title_ctrl.ChangeValue(self._selected_title(sel))
            if self._list_col == 0:
                a11y.announce(
                    f"Chapter {sel + 1}: {self._selected_title(sel)}")
            else:
                # Column navigation mode - announce the tracked column value.
                self._announce_list_cell(sel)
        else:
            self.title_ctrl.ChangeValue("")
        self._update_command_state()

    def _on_next_page(self, _evt=None):
        self._page_ch.Hide()
        self._page_tags.Show()
        self.panel.Layout()
        self.btn_back_page.SetFocus()
        self._announce("Step 2 of 2 - set tags and build. "
                       "Press Back to return to the chapter list.")

    def _on_back_page(self, _evt=None):
        self._page_tags.Hide()
        self._page_ch.Show()
        self.panel.Layout()
        self.list.SetFocus()
        self._announce("Step 1 of 2 - chapter list.")

    _LIST_COL_NAMES = [
        "Chapter number", "Title", "Start time", "Duration", "Source file"]

    def _announce_list_cell(self, row: int):
        """Speak the value of the currently tracked column for the given row."""
        if row < 0 or row >= self._row_count():
            return
        col = self._list_col
        value = self.list.GetItemText(row, col)
        a11y.announce(f"{self._LIST_COL_NAMES[col]}: {value}")

    def _on_list_key(self, evt):
        key = evt.GetKeyCode()
        sel = self.list.GetFirstSelected()
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and sel >= 0:
            self._on_play_selected(None)
        elif key == wx.WXK_DELETE and sel >= 0:
            self._remove_selected()
        elif key == wx.WXK_F2 and sel >= 0:
            self.title_ctrl.SetFocus()
            self.title_ctrl.SelectAll()
        elif key == wx.WXK_LEFT and sel >= 0:
            self._list_col = max(0, self._list_col - 1)
            self._announce_list_cell(sel)
        elif key == wx.WXK_RIGHT and sel >= 0:
            self._list_col = min(len(self._LIST_COL_NAMES) - 1, self._list_col + 1)
            self._announce_list_cell(sel)
        else:
            evt.Skip()

    def _build_play_controls_menu(self, building: bool) -> wx.Menu:
        """A "Play Controls" menu - one item per transport command, enabled
        and labelled to match the player's current state. Shared by the
        chapter list's context menu and the player's own."""
        p = self.player
        has_media = p.has_media()
        menu = wx.Menu()

        mi_pp = menu.Append(wx.ID_ANY, "Pa&use" if p.is_playing() else "&Play")
        mi_pp.Enable(not building and has_media)
        self.Bind(wx.EVT_MENU, p._on_play_pause, mi_pp)

        mi_stop = menu.Append(wx.ID_ANY, "&Stop")
        mi_stop.Enable(not building and has_media)
        self.Bind(wx.EVT_MENU, p._on_stop, mi_stop)

        mi_prev = menu.Append(wx.ID_ANY, "Pre&vious Chapter")
        mi_prev.Enable(not building and has_media and bool(p.chapters))
        self.Bind(wx.EVT_MENU, p._on_prev, mi_prev)

        mi_next = menu.Append(wx.ID_ANY, "Ne&xt Chapter")
        mi_next.Enable(not building and has_media and bool(p.chapters))
        self.Bind(wx.EVT_MENU, p._on_next, mi_next)

        mi_rew = menu.Append(wx.ID_ANY, "Re&wind")
        mi_rew.Enable(not building and has_media)
        self.Bind(wx.EVT_MENU, p._on_rewind, mi_rew)

        mi_ff = menu.Append(wx.ID_ANY, "&Forward")
        mi_ff.Enable(not building and has_media)
        self.Bind(wx.EVT_MENU, p._on_forward, mi_ff)

        menu.AppendSeparator()
        mi_goto = menu.Append(wx.ID_ANY, "&Go to Time…\tCtrl+G")
        mi_goto.Enable(not building and has_media)
        self.Bind(wx.EVT_MENU, self._on_goto_time, mi_goto)

        return menu

    def _on_list_context_menu(self, _evt):
        sel = self.list.GetFirstSelected()
        if sel < 0:
            sel = self.list.GetNextItem(-1, wx.LIST_NEXT_ALL, wx.LIST_STATE_FOCUSED)
        count = self._row_count()
        edit = self.mode == "edit"
        building = self._is_building()

        menu = wx.Menu()

        mi_edit = menu.Append(wx.ID_ANY, "Edit Chapter…\tF2")
        mi_edit.Enable(not building and sel >= 0)
        self.Bind(wx.EVT_MENU, self._on_edit_chapter, mi_edit)

        if not edit:
            menu.AppendSeparator()
            mi_up = menu.Append(wx.ID_ANY, "Move Up\tAlt+Up")
            mi_up.Enable(not building and sel > 0)
            self.Bind(wx.EVT_MENU, lambda e: self._move(-1), mi_up)

            mi_dn = menu.Append(wx.ID_ANY, "Move Down\tAlt+Down")
            mi_dn.Enable(not building and 0 <= sel < count - 1)
            self.Bind(wx.EVT_MENU, lambda e: self._move(1), mi_dn)

        menu.AppendSeparator()

        mi_play = menu.Append(wx.ID_ANY, "Play Chapter")
        mi_play.Enable(not building and sel >= 0)
        self.Bind(wx.EVT_MENU, self._on_play_selected, mi_play)

        if edit:
            mi_split = menu.Append(wx.ID_ANY, "Split Here")
            mi_split.Enable(not building and self.player.has_media())
            self.Bind(wx.EVT_MENU, self._on_split_chapter, mi_split)

        menu.AppendSubMenu(self._build_play_controls_menu(building), "Play &Controls")

        menu.AppendSeparator()

        rm_label = "Merge Up" if edit else "Remove\tDel"
        mi_rm = menu.Append(wx.ID_ANY, rm_label)
        mi_rm.Enable(not building and sel >= 0 and (not edit or count > 1))
        self.Bind(wx.EVT_MENU, lambda e: self._remove_selected(), mi_rm)

        self.list.PopupMenu(menu)
        menu.Destroy()

    def _on_apply_title(self, evt):
        evt.Skip()
        sel = self.list.GetFirstSelected()
        if not (0 <= sel < self._row_count()):
            return
        new_title = self.title_ctrl.GetValue().strip()
        old_title = self._selected_title(sel)
        if not new_title or new_title == old_title:
            return
        if self.mode == "edit":
            self.edit_chapters[sel].title = new_title
            self.edit_dirty = True
        else:
            self.items[sel].title = new_title
            self.items[sel].edited = True
        self.list.SetItem(sel, 1, new_title)
        self._announce(f"Renamed chapter {sel + 1} to “{new_title}”.")

        # Record undo
        _sel, _new, _old = sel, new_title, old_title

        def _do_rename(title):
            if self.mode == "edit":
                self.edit_chapters[_sel].title = title
                self.edit_dirty = True
            else:
                self.items[_sel].title = title
                self.items[_sel].edited = True
            self.list.SetItem(_sel, 1, title)
            self.list.Select(_sel)
            self._update_command_state()

        self._undo.push(_UndoAction(
            f"Rename Chapter {_sel + 1}",
            undo_fn=lambda: _do_rename(_old),
            redo_fn=lambda: _do_rename(_new),
        ))
        self._update_undo_menu()

    def _move_no_record(self, delta: int, from_idx: int = -1):
        """Perform a chapter move without recording to the undo stack."""
        sel = from_idx if from_idx >= 0 else self.list.GetFirstSelected()
        if sel < 0:
            return
        new = sel + delta
        if self.mode == "edit":
            if not (0 <= new < len(self.edit_chapters)):
                return
            a, b = self.edit_chapters[sel], self.edit_chapters[new]
            a.title, b.title = b.title, a.title
            a.url,   b.url   = b.url,   a.url
            a.img,   b.img   = b.img,   a.img
            self._audio_order[sel], self._audio_order[new] = (
                self._audio_order[new], self._audio_order[sel])
            self.edit_dirty = True
            self._refresh_list(select=new)
            self.player.set_chapters(self.edit_chapters)
            self._announce(
                f"Swapped labels: now chapter {sel + 1} is '{b.title}', "
                f"chapter {new + 1} is '{a.title}'.")
        else:
            if not (0 <= new < len(self.items)):
                return
            self.items[sel], self.items[new] = self.items[new], self.items[sel]
            self._refresh_list(select=new)
            self._announce(f"Moved chapter to position {new + 1} of {len(self.items)}.")

        _from, _to, _delta = sel, new, delta
        self._undo.push(_UndoAction(
            f"Move Chapter {_from + 1} {'Down' if _delta > 0 else 'Up'}",
            undo_fn=lambda: self._move_no_record(-_delta, from_idx=_to),
            redo_fn=lambda: self._move_no_record(_delta, from_idx=_from),
        ))
        self._update_undo_menu()

    def _remove_no_record(self, sel):
        # Perform a remove/merge without recording to the undo stack.
        _edit = (self.mode == 'edit')
        if _edit:
            try:
                self.edit_chapters = core.merge_chapter(self.edit_chapters, sel)
            except core.ChapterForgeError:
                return
            self.edit_dirty = True
            nxt = max(0, min(sel, len(self.edit_chapters) - 1))
            self._refresh_list(select=nxt)
            self.player.set_chapters(self.edit_chapters)
            self._update_command_state()
        else:
            if 0 <= sel < len(self.items):
                self.items.pop(sel)
                nxt = min(sel, len(self.items) - 1)
                self._refresh_list(select=nxt)
                self._update_command_state()

    def _remove_selected(self):
        sel = self.list.GetFirstSelected()
        if sel < 0:
            return
        _in_edit_mode = (self.mode == 'edit')
        if _in_edit_mode:
            _saved_chapters = _copy.deepcopy(self.edit_chapters)
            try:
                self.edit_chapters = core.merge_chapter(self.edit_chapters, sel)
            except core.ChapterForgeError as exc:
                wx.MessageBox(str(exc), 'Cannot merge',
                              wx.OK | wx.ICON_INFORMATION, self)
                return
            self.edit_dirty = True
            nxt = max(0, min(sel, len(self.edit_chapters) - 1))
            self._refresh_list(select=nxt)
            self.player.set_chapters(self.edit_chapters)
            self._announce(
                'Merged. ' + str(len(self.edit_chapters)) + ' chapter(s) remain.')
            _sel = sel

            def _undo_merge():
                self.edit_chapters = _copy.deepcopy(_saved_chapters)
                self.edit_dirty = True
                self._refresh_list(select=_sel)
                self.player.set_chapters(self.edit_chapters)
                self._update_command_state()

            self._undo.push(_UndoAction(
                'Merge Chapter ' + str(_sel + 1),
                undo_fn=_undo_merge,
                redo_fn=lambda: self
            ))
            self._update_undo_menu()
            return

        _sel = sel
        _saved_item = _copy.copy(self.items[sel])

        def _undo_remove():
            self.items.insert(_sel, _saved_item)
            self._refresh_list(select=_sel)
            self._update_command_state()

        def _redo_remove():
            if 0 <= _sel < len(self.items):
                self.items.pop(_sel)
                nxt = min(_sel, len(self.items) - 1)
                self._refresh_list(select=nxt)
                self._update_command_state()

        removed = self.items.pop(sel)
        nxt = min(sel, len(self.items) - 1)
        self._refresh_list(select=nxt)
        self._announce(
            'Removed “' + removed.title + '”. '
            + str(len(self.items)) + ' chapter(s) left.')
        if not self.items:
            self.title_ctrl.ChangeValue('')

        self._undo.push(_UndoAction(
            'Remove Chapter ' + str(_sel + 1),
            undo_fn=_undo_remove,
            redo_fn=_redo_remove,
        ))
        self._update_undo_menu()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def _collect_tags(self) -> core.Tags:
        return core.Tags(
            title=self.tag_title.GetValue().strip(),
            artist=self.tag_artist.GetValue().strip(),
            album=self.tag_album.GetValue().strip(),
            album_artist=self.tag_album_artist.GetValue().strip(),
            genre=self.tag_genre.GetValue().strip(),
            year=self.tag_year.GetValue().strip(),
            comment=self.tag_comment.GetValue().strip(),
            cover_path=self.cover_ctrl.GetValue().strip(),
            narrator=self.tag_narrator.GetValue().strip(),
            series_title=self.tag_series.GetValue().strip(),
            series_index=self.tag_series_idx.GetValue().strip(),
        )

    def _on_build(self, _evt):
        if self._is_building() or not self.items or not self.output_path:
            return
        # Make sure a pending title edit is captured.
        if self.title_ctrl.HasFocus():
            fake = wx.CommandEvent()
            self._on_apply_title(fake)

        # Surface quality / compatibility warnings before a long build.
        warnings = core.preflight(self.items)
        if warnings:
            msg = ("ChapterForge found some things worth checking:\n\n"
                   + "\n".join(f"• {w}" for w in warnings)
                   + "\n\nBuild anyway?")
            if wx.MessageBox(msg, "Pre-flight warnings",
                             wx.YES_NO | wx.ICON_WARNING, self) != wx.YES:
                self._announce("Build cancelled before starting.")
                return

        if os.path.exists(self.output_path):
            if wx.MessageBox(
                    f"“{self.output_path}” already exists. Overwrite it?",
                    "Confirm overwrite", wx.YES_NO | wx.ICON_QUESTION,
                    self) != wx.YES:
                return

        # The preview player may hold a handle on the file we are about to
        # overwrite; releasing it frees the OS lock on Windows.
        self.player.release(recreate=True)

        items = list(self.items)
        chapters = core.compute_chapters(items)
        tags = self._collect_tags()
        output = self.output_path
        write_pod2 = bool(self.settings.get("write_pod2", False))
        write_rss = bool(self.settings.get("write_rss", False))
        rss_media_url = self.settings.get("rss_media_url", "")
        acx_check_after = bool(self.settings.get("acx_check_after_build", False))
        trim_silence = bool(self.settings.get("trim_silence", False))
        trim_silence_db = float(self.settings.get("trim_silence_db", -50.0))
        trim_silence_min_ms = float(self.settings.get("trim_silence_min_ms", 100.0))
        bitrate = self.settings.get("bitrate", "192k")
        normalize = bool(self.settings.get("normalize", False))
        per_file_normalize = bool(self.settings.get("per_file_normalize", False))
        # The two loudness options are mutually exclusive; per-chapter wins so we
        # never normalize twice.
        if per_file_normalize:
            normalize = False
        normalize_lufs = float(self.settings.get("normalize_lufs", -16.0))
        fade_ms = int(self.settings.get("fade_ms", 0))
        gap_ms = self._gap_ms()
        self._save_settings()
        self._undo.clear()
        self._update_undo_menu()
        self.canceller = core.Canceller()
        self._last_pct = -1
        self.gauge.SetValue(0)
        _ofmt2 = core.output_format(output)
        verb = ("audiobook" if _ofmt2 == "m4b" else
                "FLAC master" if _ofmt2 == "flac" else "master MP3")
        self._announce(f"Building {verb}…")
        self._update_command_state_building(True)

        def progress(frac):
            wx.PostEvent(self, _ThreadEvent(EVT_PROGRESS, frac))

        # Per-chapter peak announcements flood a screen reader on a long book,
        # so only emit them when the user has opted into verbose announcements.
        announce_levels = self.settings.get("announce_verbosity") == "verbose"

        def _on_chapter_level(idx: int, peak_db: float):
            wx.CallAfter(self._announce,
                         f"Chapter {idx + 1} peak level: {peak_db:.1f} dB.")

        def run():
            import tempfile as _tmpmod
            try:
                build_items = list(items)
                _trim_dir = None
                if trim_silence:
                    _trim_dir = _tmpmod.mkdtemp(prefix="chapterforge_trim_")
                    trimmed = []
                    for it in build_items:
                        trimmed.append(core.trim_silence_item(
                            it, _trim_dir,
                            noise_db=trim_silence_db,
                            min_silence_ms=trim_silence_min_ms))
                    build_items = trimmed

                result = core.build_master(
                    build_items, output, tags, chapters=chapters,
                    bitrate=bitrate, normalize=normalize, gap_ms=gap_ms,
                    canceller=self.canceller, progress=progress,
                    per_file_normalize=per_file_normalize,
                    normalize_lufs=normalize_lufs,
                    fade_in_ms=fade_ms, fade_out_ms=fade_ms,
                    on_chapter_level=(_on_chapter_level if announce_levels else None))
                # The chapter report (with audio stats) is written on the main
                # thread in _on_evt_done so the figures match the final file.
                if write_pod2:
                    try:
                        core.write_pod2_chapters(
                            output, result.chapters, result.total_ms)
                    except OSError:
                        pass
                if write_rss and rss_media_url:
                    try:
                        from . import rss as rss_mod
                        rss_mod.write_rss(result, tags, rss_media_url,
                                          narrator=tags.narrator,
                                          series_title=tags.series_title,
                                          series_index=tags.series_index)
                    except Exception:
                        pass
                wx.PostEvent(self, _ThreadEvent(EVT_DONE,
                                                (result, acx_check_after)))
            except core.BuildCancelled:
                wx.PostEvent(self, _ThreadEvent(EVT_FAILED, None))
            except Exception as exc:  # surfaced to the user
                wx.PostEvent(self, _ThreadEvent(EVT_FAILED, str(exc)))
            finally:
                if _trim_dir:
                    import shutil as _shutil
                    _shutil.rmtree(_trim_dir, ignore_errors=True)

        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()

    def _on_batch_done(self, results, errors):
        self.gauge.SetValue(100)
        self._update_command_state()
        built = len(results)
        summary = f"Batch finished: built {built} master(s)."
        if errors:
            summary += f" {len(errors)} failed."
        self._announce(summary)
        self.notifier.notify("ChapterForge - batch done", summary, "info",
                             speak=False)
        detail = "\n".join(os.path.basename(r.output_path) for r in results[:20])
        if errors:
            detail += "\n\nFailed:\n" + "\n".join(errors[:20])
        wx.MessageBox(f"{summary}\n\n{detail}", "Batch build complete",
                      wx.OK | (wx.ICON_WARNING if errors else wx.ICON_INFORMATION),
                      self)

    def _update_command_state_building(self, building: bool):
        # Called on the main thread around a build.
        self._update_command_state()
        if building:
            self.btn_cancel.Enable(True)
            self.btn_cancel.SetFocus()

    def _on_cancel(self, _evt):
        if self.canceller and self._is_building():
            self._announce("Cancelling…")
            self.canceller.cancel()

    # ------------------------------------------------------------------
    # Worker-thread events (main thread)
    # ------------------------------------------------------------------
    def _on_evt_progress(self, evt):
        pct = int(evt.payload * 100)
        if pct != self._last_pct:
            self._last_pct = pct
            self.gauge.SetValue(max(0, min(100, pct)))
            self.SetStatusText(f"Building… {pct}%")

    def _on_evt_done(self, evt):
        self.worker = None
        if isinstance(evt.payload, tuple) and evt.payload and evt.payload[0] == "batch":
            self._on_batch_done(evt.payload[1], evt.payload[2])
            return
        # Unpack (result, run_acx_check) or plain result for backward compat.
        if isinstance(evt.payload, tuple) and len(evt.payload) == 2 and isinstance(evt.payload[1], bool):
            result, _run_acx = evt.payload
        else:
            result, _run_acx = evt.payload, False
        self.gauge.SetValue(100)
        mode = "re-encoded" if result.reencoded else "lossless copy"
        _rfmt = core.output_format(result.output_path)
        kind = ("audiobook" if _rfmt == "m4b" else
                "FLAC master" if _rfmt == "flac" else "master MP3")
        # Post-build verification: re-read the file and confirm the chapters.
        verified_note = ""
        try:
            ok, n, _vt, issues = core.verify_output(
                result.output_path, expected_n=len(result.chapters))
            if ok:
                verified_note = f" Verified {n} chapter(s)."
            else:
                verified_note = " Verify warning: " + "; ".join(issues)
        except Exception:
            pass
        summary = (
            f"Done. Built {len(result.chapters)} chapter(s), total "
            f"{core.format_timestamp(result.total_ms)} ({mode}).{verified_note}")
        self._announce(summary)
        self._push_recent(result.output_path)
        self._update_command_state()
        self.notifier.notify("ChapterForge - done", summary, "info", speak=False)
        if self.settings.get("log_build_history", True):
            import time as _time
            log_entry = (f"[{_time.strftime('%Y-%m-%d %H:%M:%S')}] "
                         f"{os.path.basename(result.output_path)} - "
                         f"{len(result.chapters)} chapter(s), "
                         f"{core.format_timestamp(result.total_ms)} ({mode})")
            self._append_build_log(log_entry)
        # Probe the finished file for audio statistics.
        astats = core.probe_audio_stats(result.output_path)
        stats_lines = []
        if astats.get("file_size_bytes"):
            stats_lines.append(f"File size  : {core.format_size(astats['file_size_bytes'])}")
        if astats.get("bit_rate_kbps"):
            stats_lines.append(f"Bit rate   : {astats['bit_rate_kbps']} kbps")
        if astats.get("sample_rate"):
            stats_lines.append(f"Sample rate: {astats['sample_rate']} Hz")
        if astats.get("channels"):
            ch = astats["channels"]
            stats_lines.append(f"Channels   : {ch} ({'mono' if ch == 1 else 'stereo' if ch == 2 else str(ch)})")
        stats_block = ("\n\nAudio stats:\n" + "\n".join(stats_lines)) if stats_lines else ""

        # Update build log entry with file size.
        if self.settings.get("log_build_history", True) and astats.get("file_size_bytes"):
            pass  # already written above; stats are in the dialog only

        # Write chapter report with audio stats.
        try:
            core.write_chapter_report(result.output_path, result,
                                      self._collect_tags(), self.items,
                                      audio_stats=astats)
        except (OSError, Exception):
            pass

        # Offer to preview the finished file in the in-app player.
        if _run_acx:
            wx.CallAfter(self._run_acx_check, result.output_path)

        if wx.MessageBox(
                f"{summary}{stats_block}\n\nSaved {kind} to:\n{result.output_path}\n\n"
                "Load it into the player now?",
                "Master created", wx.YES_NO | wx.ICON_INFORMATION,
                self) == wx.YES:
            if self.player.load(result.output_path, result.chapters):
                self.player.btn_play.SetFocus()
                self.panel.Layout()
            else:
                self.btn_build.SetFocus()
        else:
            self.btn_build.SetFocus()

    def _on_evt_failed(self, evt):
        self.worker = None
        self.gauge.SetValue(0)
        self._update_command_state()
        if evt.payload is None:
            self._announce("Build cancelled.")
            wx.MessageBox("The build was cancelled.", "Cancelled",
                          wx.OK | wx.ICON_INFORMATION, self)
        else:
            self._announce("Build failed.")
            self.notifier.notify("ChapterForge - failed", str(evt.payload),
                                 "error", speak=False)
            wx.MessageBox(str(evt.payload), "Build failed",
                          wx.OK | wx.ICON_ERROR, self)
        self.btn_build.SetFocus()

    # ------------------------------------------------------------------
    # Chapter editing / job files / watcher
    # ------------------------------------------------------------------

    def _apply_key_overrides(self):
        """Apply any user-configured keyboard shortcut overrides from settings."""
        overrides = self.settings.get("key_overrides", {})
        if not overrides:
            return
        _menu_map = {
            "Open Folder…":        (self.mi_open,      "Ctrl+Shift+O"),
            "Open Existing Master…": (self.mi_open_master, "Ctrl+O"),
            "Save As…":            (self.mi_save_as,   "Ctrl+Shift+A"),
            "Build Master MP3":    (self.mi_build,     "Ctrl+B"),
            "Save Changes":        (self.mi_save_edit, "Ctrl+Shift+S"),
            "Settings…":           (self.mi_settings,  "Ctrl+,"),
        }
        for cmd, new_key in overrides.items():
            if cmd in _menu_map:
                mi, _ = _menu_map[cmd]
                base = mi.GetItemLabelText().split("\t")[0]
                mi.SetItemLabel(f"{base}\t{new_key}")

    def _on_batch_edit_titles(self, _evt):
        """Open the Batch Edit Titles dialog and apply the chosen transformations."""
        if self._is_building() or not self._row_count():
            return
        if self.mode == "edit":
            current_titles = [c.title for c in self.edit_chapters]
        else:
            current_titles = [it.title for it in self.items]

        dlg = BatchTitleDialog(self, current_titles)
        if dlg.ShowModal() == wx.ID_OK:
            new_titles = dlg.result_titles()
            old_titles = list(current_titles)

            def _apply(titles):
                for i, t in enumerate(titles):
                    if self.mode == "edit":
                        if i < len(self.edit_chapters):
                            self.edit_chapters[i].title = t
                            self.edit_dirty = True
                    else:
                        if i < len(self.items):
                            self.items[i].title = t
                            self.items[i].edited = True
                    self.list.SetItem(i, 1, t)
                self._update_command_state()

            _apply(new_titles)
            self._undo.push(_UndoAction(
                "Batch Edit Titles",
                undo_fn=lambda: _apply(old_titles),
                redo_fn=lambda: _apply(new_titles)))
            self._update_undo_menu()
            self._announce(f"Applied title edits to {len(new_titles)} chapter(s).")
        dlg.Destroy()

    def _on_rename_source_files(self, _evt):
        if self._is_building() or self.mode == "edit" or not self.items:
            return
        dlg = RenameSourceFilesDialog(self, self.items)
        if dlg.ShowModal() == wx.ID_OK:
            pairs = dlg.planned_renames()
            errors = []
            renamed = 0
            for old, new in pairs:
                if old == new:
                    continue
                try:
                    os.rename(old, new)
                    renamed += 1
                except OSError as exc:
                    errors.append(f"{os.path.basename(old)}: {exc}")
            # Update item paths in memory
            for i, (old, new) in enumerate(pairs):
                if i < len(self.items):
                    self.items[i].path = new
            self._refresh_list()
            msg = f"Renamed {renamed} file(s)."
            if errors:
                msg += f" {len(errors)} error(s): " + "; ".join(errors[:3])
            self._announce(msg)
        dlg.Destroy()

    def _on_edit_chapter(self, _evt):
        sel = self.list.GetFirstSelected()
        if sel < 0:
            sel = self.list.GetNextItem(-1, wx.LIST_NEXT_ALL, wx.LIST_STATE_FOCUSED)
        if sel < 0 or sel >= self._row_count():
            return
        if self.mode == "edit":
            ch = self.edit_chapters[sel]
            title, url, img = ch.title, ch.url, ch.img
            start_ms = ch.start_ms
        else:
            it = self.items[sel]
            title, url, img = it.title, it.url, it.img
            start_ms = None
        dlg = ChapterEditDialog(self, sel + 1, title, url, img, start_ms=start_ms)
        if dlg.ShowModal() == wx.ID_OK:
            new_title, new_url, new_img = dlg.result()
            new_title = new_title or title
            if self.mode == "edit":
                start_text = dlg.start_text()
                if start_text is not None:
                    new_start = core._ts_to_ms(start_text)
                    if new_start is None:
                        wx.MessageBox("Start time must look like H:MM:SS.",
                                      "Invalid start time",
                                      wx.OK | wx.ICON_ERROR, self)
                        dlg.Destroy()
                        return
                    if new_start != ch.start_ms:
                        try:
                            self.edit_chapters = core.set_chapter_start(
                                self.edit_chapters, sel, new_start)
                        except core.ChapterForgeError as exc:
                            wx.MessageBox(str(exc), "Cannot move start",
                                          wx.OK | wx.ICON_ERROR, self)
                            dlg.Destroy()
                            return
                        ch = self.edit_chapters[sel]
                ch.title, ch.url, ch.img = new_title, new_url, new_img
                self.edit_dirty = True
                self._refresh_list(select=sel)
                self.player.set_chapters(self.edit_chapters)
                self.title_ctrl.ChangeValue(new_title)
                self._announce(f"Updated chapter {sel + 1}: {new_title}.")
                dlg.Destroy()
                self.list.SetFocus()
                return
            else:
                it.title, it.url, it.img = new_title, new_url, new_img
                it.edited = True
            self.list.SetItem(sel, 1, new_title)
            self.title_ctrl.ChangeValue(new_title)
            self._announce(f"Updated chapter {sel + 1}: {new_title}.")
        dlg.Destroy()
        self.list.SetFocus()

    # ------------------------------------------------------------------
    # Settings / player
    # ------------------------------------------------------------------
    def _on_settings(self, _evt):
        self._gather_settings()
        dlg = SettingsDialog(self, dict(self.settings))
        if dlg.ShowModal() == wx.ID_OK:
            self.settings.update(dlg.result())
            settings_mod.save(self.settings)
            self._apply_settings_to_ui()
            self._apply_appearance()
            self._sync_theme_menu()
            self.player.vol_slider.SetValue(
                int(self.settings.get("default_volume", 80)))
            self._announce("Settings saved.")
        dlg.Destroy()

    # ------------------------------------------------------------------
    # ACX compliance, metadata lookup, build log
    # ------------------------------------------------------------------

    def _run_acx_check(self, path: str):
        """Run ACX compliance measurement on *path* and show results."""
        if not path or not os.path.isfile(path):
            wx.MessageBox("No file to check. Build a master first.",
                          "ACX Check", wx.OK | wx.ICON_INFORMATION, self)
            return
        wx.BeginBusyCursor()
        try:
            from . import acx as acx_mod
            acx_result = acx_mod.measure_file(path)
        except Exception as exc:
            wx.EndBusyCursor()
            wx.MessageBox(f"ACX check failed:\n{exc}", "ACX Check",
                          wx.OK | wx.ICON_ERROR, self)
            return
        wx.EndBusyCursor()
        dlg = AcxResultDialog(self, acx_result)
        dlg.ShowModal()
        fix = dlg.fix_and_rebuild
        dlg.Destroy()
        self.btn_build.SetFocus()
        if fix:
            self._acx_fix_and_rebuild()

    def _acx_fix_and_rebuild(self):
        """Enable -23 LUFS per-file normalization and rebuild, with guards."""
        if self._is_building():
            return
        # We can only rebuild from source files (build mode), not from an
        # already-finished master opened for chapter editing.
        if self.mode == "edit" or not self.items or not self.output_path:
            wx.MessageBox(
                "To fix loudness, ChapterForge needs the original source files.\n\n"
                "Open the folder of source audio (File > Open Folder), set the "
                "output file, then run the ACX check again and choose "
                "Fix and Rebuild.",
                "Fix and Rebuild", wx.OK | wx.ICON_INFORMATION, self)
            return
        # ACX submissions must be MP3; per-file normalization only applies to
        # the MP3 build path. Warn if the chosen output is something else.
        if core.output_format(self.output_path) != "mp3":
            if wx.MessageBox(
                    "ACX requires MP3 files, and the automatic loudness fix only "
                    "applies to MP3 output. Your current output is not MP3.\n\n"
                    "Switch the output to MP3 and rebuild now?",
                    "Fix and Rebuild", wx.YES_NO | wx.ICON_QUESTION,
                    self) != wx.YES:
                return
            self.output_path = os.path.splitext(self.output_path)[0] + ".mp3"
            self.settings["output_format"] = "mp3"
            self._update_command_state()
        self.settings["per_file_normalize"] = True
        self.settings["normalize_lufs"] = -23.0
        settings_mod.save(self.settings)
        self._announce(
            "Loudness normalization to -23 LUFS enabled. Rebuilding now.")
        wx.CallAfter(self._on_build, None)

    def _on_acx_check_menu(self, _evt):
        """Run ACX check from the Tools menu."""
        path = self.output_path or (self.edit_path if self.mode == "edit" else "")
        if not path:
            wx.MessageBox(
                "Open or build a master file first.",
                "ACX Check", wx.OK | wx.ICON_INFORMATION, self)
            return
        self._run_acx_check(path)

    def _on_lookup_metadata(self, _evt):
        """Open the metadata lookup dialog."""
        dlg = MetadataLookupDialog(self,
                                   title=self.tag_title.GetValue().strip(),
                                   artist=self.tag_artist.GetValue().strip())
        if dlg.ShowModal() == wx.ID_OK:
            r = dlg.selected_result
            if r:
                if r.title:
                    self.tag_title.SetValue(r.title)
                    self.tag_album.SetValue(r.title)
                if r.artist:
                    self.tag_artist.SetValue(r.artist)
                    self.tag_album_artist.SetValue(r.album_artist or r.artist)
                if r.genre:
                    self.tag_genre.SetValue(r.genre)
                if r.year:
                    self.tag_year.SetValue(r.year)
                if r.narrator:
                    self.tag_narrator.SetValue(r.narrator)
                if r.series_title:
                    self.tag_series.SetValue(r.series_title)
                if r.series_index:
                    self.tag_series_idx.SetValue(r.series_index)
                self._announce("Metadata applied.")
        dlg.Destroy()
        self.tag_title.SetFocus()

    def _on_merge_short_chapters(self, _evt):
        """Collapse chapters shorter than a threshold into the previous chapter."""
        if self._is_building():
            return
        if self.mode != "edit":
            # In build mode each source file is exactly one chapter, so there is
            # no chapter boundary to merge away. Offer the two ways to reduce
            # short chapters that fit this model.
            wx.MessageBox(
                "You are building from a folder, where each file is one chapter, "
                "so there are no chapter boundaries to merge yet.\n\n"
                "To combine short chapters you can either:\n"
                "1. Remove or re-order the short files now (select a row and "
                "press Delete), or\n"
                "2. Build the master, then open it with Open Existing Master and "
                "run Merge Short Chapters on the finished file.",
                "Merge Short Chapters", wx.OK | wx.ICON_INFORMATION, self)
            return
        if not self.edit_chapters:
            wx.MessageBox("No chapters to merge.", "Merge Short Chapters",
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        dlg = wx.TextEntryDialog(
            self,
            "Merge chapters shorter than (seconds):",
            "Merge Short Chapters", "30")
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        try:
            min_sec = float(dlg.GetValue().strip())
        except ValueError:
            dlg.Destroy()
            wx.MessageBox("Enter a number of seconds.", "Invalid input",
                          wx.OK | wx.ICON_WARNING, self)
            return
        dlg.Destroy()
        if min_sec <= 0:
            return
        min_ms = int(min_sec * 1000)
        old_chapters = list(self.edit_chapters)
        merged: list = [old_chapters[0]]
        for ch in old_chapters[1:]:
            dur = ch.end_ms - ch.start_ms
            if dur < min_ms:
                prev = merged[-1]
                merged[-1] = core.Chapter(
                    index=prev.index, title=prev.title,
                    start_ms=prev.start_ms, end_ms=ch.end_ms,
                    url=prev.url, img=prev.img)
            else:
                merged.append(ch)
        n_merged = len(old_chapters) - len(merged)
        if n_merged == 0:
            wx.MessageBox(
                f"No chapters shorter than {min_sec:.0f}s found.",
                "Merge Short Chapters", wx.OK | wx.ICON_INFORMATION, self)
            return
        new_chapters = [
            core.Chapter(index=i, title=ch.title, start_ms=ch.start_ms,
                         end_ms=ch.end_ms, url=ch.url, img=ch.img)
            for i, ch in enumerate(merged)
        ]
        self.edit_chapters = new_chapters
        self.edit_dirty = True
        self._refresh_list(select=0)
        self.player.set_chapters(self.edit_chapters)
        self._undo.push(_UndoAction(
            "Merge Short Chapters",
            undo_fn=lambda oc=old_chapters: (
                setattr(self, 'edit_chapters', list(oc)) or
                setattr(self, 'edit_dirty', True) or
                self._refresh_list(select=0) or
                self.player.set_chapters(self.edit_chapters)),
            redo_fn=lambda nc=new_chapters: (
                setattr(self, 'edit_chapters', list(nc)) or
                setattr(self, 'edit_dirty', True) or
                self._refresh_list(select=0) or
                self.player.set_chapters(self.edit_chapters))))
        self._update_undo_menu()
        self._announce(
            f"Merged {n_merged} short chapter(s). "
            f"{len(new_chapters)} chapter(s) remain. Use Save Changes to keep them.")

    def _on_view_build_log(self, _evt):
        """Show the build log file if one exists."""
        log_dir = settings_mod.config_dir()
        log_path = os.path.join(log_dir, "build_log.txt")
        if not os.path.isfile(log_path):
            wx.MessageBox(
                "No build log found yet. Build a master to create one.",
                "Build Log", wx.OK | wx.ICON_INFORMATION, self)
            return
        dlg = BuildLogDialog(self, log_path)
        dlg.ShowModal()
        dlg.Destroy()
        self.SetFocus()

    def _append_build_log(self, entry: str):
        """Append *entry* to the rolling build log file (best-effort)."""
        log_dir = settings_mod.config_dir()
        log_path = os.path.join(log_dir, "build_log.txt")
        try:
            os.makedirs(log_dir, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(entry + "\n")
        except OSError:
            pass

    def _apply_theme(self, theme: str):
        self.settings["theme"] = theme
        self.settings["high_contrast"] = (theme == "high_contrast")
        settings_mod.save(self.settings)
        self._apply_appearance()
        label = {"system": "System", "light": "Light",
                 "dark": "Dark", "high_contrast": "High Contrast"}.get(theme, theme)
        self._announce(f"Theme: {label}.")

    def _sync_theme_menu(self):
        t = self.settings.get("theme", "system")
        if t == "system" and self.settings.get("high_contrast", False):
            t = "high_contrast"
        self.mi_theme_system.Check(t == "system")
        self.mi_theme_light.Check(t == "light")
        self.mi_theme_dark.Check(t == "dark")
        self.mi_theme_hc.Check(t == "high_contrast")

    def _on_text_larger(self, _evt=None):
        scale = min(200, int(self.settings.get("text_scale", 100)) + 10)
        self.settings["text_scale"] = scale
        settings_mod.save(self.settings)
        self._apply_appearance()
        self._announce(f"Text size {scale}%.")

    def _on_text_smaller(self, _evt=None):
        scale = max(60, int(self.settings.get("text_scale", 100)) - 10)
        self.settings["text_scale"] = scale
        settings_mod.save(self.settings)
        self._apply_appearance()
        self._announce(f"Text size {scale}%.")

    def _on_text_reset(self, _evt=None):
        self.settings["text_scale"] = 100
        settings_mod.save(self.settings)
        self._apply_appearance()
        self._announce("Text size reset to default.")

    def _on_view_player(self, _evt=None):
        visible = not self.player.IsShown()
        self.player.Show(visible)
        self.mi_show_player.Check(visible)
        self.panel.Layout()
        self._announce("Player " + ("shown." if visible else "hidden."))

    def _on_player_volume(self, vol: int):
        self.settings["default_volume"] = int(vol)

    def _on_player_context_menu(self, _evt):
        """Right-click or Menu key anywhere on the player: a Play Controls
        menu, same items as the chapter list's submenu, just promoted to
        the top level since the player has no other context actions."""
        menu = self._build_play_controls_menu(self._is_building())
        self.player.PopupMenu(menu)
        menu.Destroy()

    # ------------------------------------------------------------------
    # Play-from-here / split / estimate
    # ------------------------------------------------------------------
    def _on_play_selected(self, _evt):
        sel = self.list.GetFirstSelected()
        if sel < 0:
            sel = self.list.GetNextItem(-1, wx.LIST_NEXT_ALL, wx.LIST_STATE_FOCUSED)
        if sel < 0 or sel >= self._row_count():
            return
        if self.mode == "edit":
            if not self.player.has_media():
                self.player.load(self.edit_path, self.edit_chapters)
            self.player.play_chapter(sel)
            self._announce(f"Playing chapter {sel + 1}.")
        else:
            # Audition a single source file in the player.
            item = self.items[sel]
            one = [core.Chapter(index=0, title=item.title, start_ms=0,
                                end_ms=item.duration_ms)]
            if self.player.load(item.path, one):
                self.player.play_chapter(0)
                self.panel.Layout()
                self._announce(f"Playing chapter {sel + 1}.")
            else:
                self._announce(
                    f"Could not load chapter {sel + 1}. "
                    "Check that the file exists and is a valid MP3.")

    def _on_goto_time(self, _evt):
        if not self.player.has_media():
            self._announce("No audio is loaded. Open a file and play it first.")
            return
        length_ms = self.player._length()
        dlg = GoToTimeDialog(self, length_ms)
        if dlg.ShowModal() == wx.ID_OK:
            ms = dlg.time_ms()
            if 0 <= ms <= length_ms:
                self.player._seek(ms)
                self._announce(f"Jumped to {core.format_timestamp(ms)}.")
            else:
                self._announce("That time is outside the audio length.")
        dlg.Destroy()

    def _on_split_chapter(self, _evt):
        if self.mode != "edit" or not self.player.has_media():
            return
        at_ms = self.player.playhead_ms()
        if at_ms <= 0:
            wx.MessageBox(
                "Move the player to the point where the new chapter should "
                "begin, then split.", "Split at playhead",
                wx.OK | wx.ICON_INFORMATION, self)
            return
        title = wx.GetTextFromUser(
            "Title for the new chapter:", "Split chapter",
            "New chapter", self)
        if not title:
            return
        try:
            self.edit_chapters = core.split_chapter(
                self.edit_chapters, at_ms, title=title)
        except core.ChapterForgeError as exc:
            wx.MessageBox(str(exc), "Cannot split",
                          wx.OK | wx.ICON_ERROR, self)
            return
        self.edit_dirty = True
        # Select the freshly created chapter.
        new_idx = next((i for i, c in enumerate(self.edit_chapters)
                        if c.start_ms == at_ms), 0)
        self._refresh_list(select=new_idx)
        self.player.set_chapters(self.edit_chapters)
        self._announce(
            f"Split at {core.format_timestamp(at_ms)}. "
            f"{len(self.edit_chapters)} chapter(s).")

    def _on_estimate_inputs(self, evt):
        if evt is not None:
            evt.Skip()
        self._update_estimate()

    def _gap_ms(self) -> int:
        try:
            return int(round(float(self.settings.get("gap_seconds", 0.0)) * 1000))
        except (ValueError, TypeError):
            return 0

    def _update_estimate(self):
        if self.mode == "edit" or not self.items:
            self.estimate_text.SetLabel("")
            return
        bitrate = self.settings.get("bitrate", "192k")
        total_ms, est_bytes = core.estimate_output(
            self.items, bitrate=bitrate, gap_ms=self._gap_ms())
        _efmt = self.settings.get("output_format", "mp3")
        if _efmt == "m4b":
            fmt = "M4B"
        elif _efmt == "flac":
            fmt = "FLAC"
        elif _efmt == "opus":
            fmt = "Opus"
        else:
            fmt = "MP3"
        if _efmt == "flac":
            size_note = "lossless (actual size varies)"
        else:
            size_note = f"about {core.format_size(est_bytes)}"
        self.estimate_text.SetLabel(
            f"Estimated {fmt}: {core.format_timestamp(total_ms)}, "
            f"{size_note} "
            f"({len(self.items)} chapter(s)).")

    # ------------------------------------------------------------------
    # Import / export chapter lists
    # ------------------------------------------------------------------
    def _current_chapters_and_total(self):
        """Return (chapters, total_ms, audio_name) for the active mode."""
        if self.mode == "edit":
            return (list(self.edit_chapters), self.edit_total_ms,
                    os.path.basename(self.edit_path))
        chapters = core.compute_chapters(self.items)
        total = chapters[-1].end_ms if chapters else 0
        name = os.path.basename(self.output_path) if self.output_path else "master.mp3"
        return chapters, total, name

    def _on_export_chapters(self, _evt):
        if self._is_building():
            return
        chapters, total_ms, audio_name = self._current_chapters_and_total()
        if not chapters:
            wx.MessageBox("There are no chapters to export yet.",
                          "Nothing to export", wx.OK | wx.ICON_INFORMATION, self)
            return
        wildcard = ("Audacity labels (*.txt)|*.txt|"
                    "CUE sheet (*.cue)|*.cue|"
                    "Timestamps (*.txt)|*.txt|"
                    "Podcasting 2.0 JSON (*.json)|*.json|"
                    "CSV spreadsheet (*.csv)|*.csv")
        fmt_by_index = ["audacity", "cue", "timestamps", "pod2", "csv"]
        ext_by_index = [".txt", ".cue", ".txt", ".json", ".csv"]
        default_dir = self.settings.get("last_output_dir", "") or self.folder
        dlg = wx.FileDialog(
            self, "Export chapters", defaultDir=default_dir,
            defaultFile="chapters", wildcard=wildcard,
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        idx = dlg.GetFilterIndex()
        dest = dlg.GetPath()
        dlg.Destroy()
        if not os.path.splitext(dest)[1]:
            dest += ext_by_index[idx]
        try:
            core.export_chapter_labels(
                dest, chapters, fmt_by_index[idx],
                audio_filename=audio_name, tags=self._collect_tags(),
                total_ms=total_ms)
        except (core.ChapterForgeError, OSError) as exc:
            wx.MessageBox(str(exc), "Could not export",
                          wx.OK | wx.ICON_ERROR, self)
            return
        self._announce(f"Exported chapters to {os.path.basename(dest)}.")

    def _on_import_chapters(self, _evt):
        if self._is_building():
            return
        count = self._row_count()
        if count == 0:
            wx.MessageBox(
                "Open a folder of MP3 files or an existing master first, "
                "then import a chapter list to apply chapter titles.",
                "Import chapters", wx.OK | wx.ICON_INFORMATION, self)
            return
        default_dir = self.settings.get("last_input_dir", "") or self.folder
        dlg = wx.FileDialog(
            self, "Import chapter list", defaultDir=default_dir,
            wildcard=("Chapter lists (*.txt;*.cue;*.json;*.csv)"
                      "|*.txt;*.cue;*.json;*.csv|"
                      "All files (*.*)|*.*"),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        path = dlg.GetPath()
        dlg.Destroy()

        # CSV batch metadata import (titles only, matched by row order).
        if path.lower().endswith(".csv"):
            self._on_import_csv(path)
            return

        if self.mode == "edit":
            # Edit mode: replace all chapter markers from the file
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
                chapters = core.parse_chapter_text(text, self.edit_total_ms)
            except (core.ChapterForgeError, OSError, UnicodeDecodeError) as exc:
                wx.MessageBox(str(exc), "Could not import",
                              wx.OK | wx.ICON_ERROR, self)
                return
            self.edit_chapters = chapters
            self.edit_dirty = True
            self._refresh_list(select=0)
            self.player.set_chapters(self.edit_chapters)
            self._announce(
                f"Imported {len(chapters)} chapter(s) from "
                f"{os.path.basename(path)}. Use Save Changes to keep them.")
        else:
            # Build mode: use chapter titles from the file to rename source items
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
                # Use a large total_ms so all timestamps are accepted
                chapters = core.parse_chapter_text(text, total_ms=86_400_000)
            except (core.ChapterForgeError, OSError, UnicodeDecodeError) as exc:
                wx.MessageBox(str(exc), "Could not import",
                              wx.OK | wx.ICON_ERROR, self)
                return
            n = min(len(chapters), len(self.items))
            old_titles = [it.title for it in self.items]
            for i in range(n):
                self.items[i].title = chapters[i].title
                self.items[i].edited = True
            self._refresh_list(select=0)
            new_titles = [it.title for it in self.items]
            self._undo.push(_UndoAction(
                "Import Chapter Titles",
                undo_fn=lambda: [
                    setattr(self.items[j], 'title', old_titles[j]) or
                    setattr(self.items[j], 'url', old_urls[j]) or
                    self.list.SetItem(j, 1, old_titles[j])
                    for j in range(len(old_titles))],
                redo_fn=lambda: [
                    setattr(self.items[j], 'title', new_titles[j]) or
                    setattr(self.items[j], 'url', new_urls[j]) or
                    self.list.SetItem(j, 1, new_titles[j])
                    for j in range(n)]))
            self._update_undo_menu()
            self._announce(
                f"Applied {n} chapter title(s) from {os.path.basename(path)}.")

    def _on_import_csv(self, path: str):
        """Import chapter titles (and optional URLs) from a CSV file.

        Columns are detected from an optional header row. Recognised names:
        number/chapter/# , title/name , url/link , filename/file. Rows are
        matched to chapters by filename (build mode) when a filename column is
        present, otherwise by chapter number, otherwise by row order.
        """
        import csv as _csv_mod
        try:
            with open(path, encoding="utf-8-sig", newline="") as fh:
                reader = _csv_mod.reader(fh)
                rows = list(reader)
        except (OSError, UnicodeDecodeError) as exc:
            wx.MessageBox(f"Could not read CSV:\n{exc}", "Import CSV",
                          wx.OK | wx.ICON_ERROR, self)
            return
        rows = [r for r in rows if any(c.strip() for c in r)]
        if not rows:
            wx.MessageBox("The CSV file is empty.", "Import CSV",
                          wx.OK | wx.ICON_INFORMATION, self)
            return

        # Column mapping. Default: col 0 = number, col 1 = title.
        num_col, title_col, url_col, file_col = 0, 1, -1, -1
        data_rows = rows
        try:
            int(rows[0][0])
        except (ValueError, IndexError):
            # First row is a header - map columns by name.
            header = [c.strip().lower() for c in rows[0]]
            data_rows = rows[1:]
            num_col = -1
            for hi, h in enumerate(header):
                if h in ("title", "chapter title", "name"):
                    title_col = hi
                elif h in ("url", "link", "href"):
                    url_col = hi
                elif h in ("filename", "file", "file name"):
                    file_col = hi
                elif h in ("number", "chapter", "#", "no", "num", "index"):
                    num_col = hi

        # Parse rows into (number, title, url, filename) records.
        records = []
        for row in data_rows:
            def _cell(i):
                return row[i].strip() if 0 <= i < len(row) else ""
            num = None
            if num_col >= 0:
                try:
                    num = int(_cell(num_col))
                except ValueError:
                    num = None
            records.append((num, _cell(title_col), _cell(url_col), _cell(file_col)))

        # Decide how many chapters we are filling and align titles/urls to them.
        target_n = (len(self.edit_chapters) if self.mode == "edit"
                    else len(self.items))
        titles = [""] * target_n
        urls = [""] * target_n
        have_files = any(rec[3] for rec in records)
        have_nums = any(rec[0] is not None for rec in records)

        def _norm(name):
            return os.path.splitext(os.path.basename(name))[0].strip().lower()

        if have_files and self.mode != "edit":
            # Match by source filename (most robust against re-ordering).
            by_name = {_norm(it.path): i for i, it in enumerate(self.items)}
            for num, title, url, fname in records:
                idx = by_name.get(_norm(fname))
                if idx is not None:
                    titles[idx] = title
                    urls[idx] = url
        elif have_nums:
            # Match by 1-based chapter number.
            for num, title, url, _f in records:
                if num is not None and 1 <= num <= target_n:
                    titles[num - 1] = title
                    urls[num - 1] = url
        else:
            # Fall back to row order.
            for i, (num, title, url, _f) in enumerate(records):
                if i < target_n:
                    titles[i] = title
                    urls[i] = url

        applied = sum(1 for i in range(target_n) if titles[i] or urls[i])
        if applied == 0:
            wx.MessageBox(
                "No rows in the CSV matched the current chapters.\n\n"
                "Check that the file has a title column, and a filename or "
                "chapter-number column to match on.",
                "Import CSV", wx.OK | wx.ICON_INFORMATION, self)
            return

        if self.mode == "edit":
            n = len(self.edit_chapters)
            old_chapters = list(self.edit_chapters)
            for i in range(n):
                if titles[i]:
                    self.edit_chapters[i].title = titles[i]
                if urls[i]:
                    self.edit_chapters[i].url = urls[i]
            self.edit_dirty = True
            self._refresh_list(select=0)
            self.player.set_chapters(self.edit_chapters)
            self._undo.push(_UndoAction(
                "Import CSV Titles",
                undo_fn=lambda oc=old_chapters: (
                    setattr(self, 'edit_chapters', list(oc)) or
                    setattr(self, 'edit_dirty', True) or
                    self._refresh_list(select=0) or
                    self.player.set_chapters(self.edit_chapters)),
                redo_fn=lambda nc=list(self.edit_chapters): (
                    setattr(self, 'edit_chapters', list(nc)) or
                    setattr(self, 'edit_dirty', True) or
                    self._refresh_list(select=0) or
                    self.player.set_chapters(self.edit_chapters))))
            self._update_undo_menu()
        else:
            n = len(self.items)
            old_titles = [it.title for it in self.items]
            old_urls = [it.url for it in self.items]
            for i in range(n):
                if titles[i]:
                    self.items[i].title = titles[i]
                    self.items[i].edited = True
                if urls[i]:
                    self.items[i].url = urls[i]
            self._refresh_list(select=0)
            new_titles = [it.title for it in self.items]
            new_urls = [it.url for it in self.items]
            self._undo.push(_UndoAction(
                "Import CSV Titles",
                undo_fn=lambda: [
                    setattr(self.items[j], 'title', old_titles[j]) or
                    setattr(self.items[j], 'url', old_urls[j]) or
                    self.list.SetItem(j, 1, old_titles[j])
                    for j in range(len(old_titles))],
                redo_fn=lambda: [
                    setattr(self.items[j], 'title', new_titles[j]) or
                    setattr(self.items[j], 'url', new_urls[j]) or
                    self.list.SetItem(j, 1, new_titles[j])
                    for j in range(n)]))
            self._update_undo_menu()
        self._announce(
            f"Applied {applied} title(s) from {os.path.basename(path)}.")

    # ------------------------------------------------------------------
    # Auphonic integration
    # ------------------------------------------------------------------
    def _on_auphonic_connect(self, _evt):
        from .auphonic_dialogs import AuphonicConnectDialog
        dlg = AuphonicConnectDialog(self, self._auphonic)
        dlg.ShowModal()

    def _on_auphonic_new(self, _evt):
        if not self._auphonic.is_connected():
            if wx.MessageBox(
                "You are not connected to Auphonic.\n\nConnect your account now?",
                "Auphonic - Not Connected",
                wx.YES_NO | wx.ICON_QUESTION,
                self,
            ) == wx.YES:
                from .auphonic_dialogs import AuphonicConnectDialog
                dlg = AuphonicConnectDialog(self, self._auphonic)
                dlg.ShowModal()
                if not self._auphonic.is_connected():
                    return
            else:
                return
        from .auphonic_dialogs import NewProductionDialog
        dlg = NewProductionDialog(self, self._auphonic)
        dlg.ShowModal()

    def _on_auphonic_history(self, _evt):
        from .auphonic_dialogs import JobHistoryDialog
        dlg = JobHistoryDialog(self, self._auphonic)
        dlg.ShowModal()

    # Diagnostics
    # ------------------------------------------------------------------
    def _on_report_issue(self, _evt):
        from pathlib import Path
        try:
            from feedback_hub import load_schema
            from feedback_hub.wx_dialog import FeedbackDialog
        except ImportError:
            wx.MessageBox(
                "The feedback-hub library is not installed.\n"
                "Please visit https://github.com/BITS-ACB/chapterforge/issues to report this issue.",
                "Report an Issue",
                wx.OK | wx.ICON_INFORMATION,
                self,
            )
            return

        schema_path = Path(__file__).parent.parent / "schemas" / "chapterforge.json"
        if not schema_path.exists():
            schema_path = Path(__file__).parent / "schemas" / "chapterforge.json"

        schema = load_schema(schema_path)
        dlg = FeedbackDialog(
            self,
            schema=schema,
            github_token=_FEEDBACK_GITHUB_TOKEN,
            app_version=__version__,
        )
        dlg.ShowModal()
        dlg.Destroy()

    def _on_save_diagnostics(self, _evt):
        dlg = wx.FileDialog(
            self, "Save diagnostics", defaultFile="chapterforge-diagnostics.txt",
            wildcard="Text files (*.txt)|*.txt",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        dest = dlg.GetPath()
        dlg.Destroy()
        self._announce("Gathering diagnostic information...")
        self.canceller = core.Canceller()
        self.worker = threading.Thread(
            target=self._gather_and_save_diagnostics,
            args=(dest,),
            daemon=True)
        self.worker.start()

    def _gather_and_save_diagnostics(self, dest: str):
        """Background thread: build diagnostics and save to file."""
        try:
            report = self._build_diagnostics()
            wx.CallAfter(self._finalize_diagnostics_save, dest, report, None)
        except Exception as exc:
            wx.CallAfter(self._finalize_diagnostics_save, dest, None, str(exc))

    def _finalize_diagnostics_save(self, dest: str, report: Optional[str], error: Optional[str]):
        """Called from main thread to finalize diagnostics save."""
        self.worker = None
        if error:
            wx.MessageBox(error, "Could not gather diagnostics",
                          wx.OK | wx.ICON_ERROR, self)
            return
        try:
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(report)
        except OSError as exc:
            wx.MessageBox(str(exc), "Could not save",
                          wx.OK | wx.ICON_ERROR, self)
            return
        self._announce(f"Saved diagnostics to {os.path.basename(dest)}.")
        wx.MessageBox(f"Saved diagnostics to:\n{dest}", "Diagnostics saved",
                      wx.OK | wx.ICON_INFORMATION, self)

    def _build_diagnostics(self) -> str:
        import platform
        from . import __version__
        lines = [
            f"ChapterForge {__version__}",
            f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"Python: {sys.version.split()[0]} ({platform.architecture()[0]})",
            f"Platform: {platform.platform()}",
            f"wxPython: {wx.version()}",
        ]
        try:
            lines.append(f"ffmpeg: {core._tool_version('ffmpeg')}")
            lines.append(f"ffprobe: {core._tool_version('ffprobe')}")
        except Exception as exc:  # pragma: no cover - environment dependent
            lines.append(f"ffmpeg/ffprobe: error - {exc}")
        lines.append("")
        lines.append("Settings:")
        for key in sorted(self.settings):
            if key == "recent":
                continue
            lines.append(f"  {key} = {self.settings[key]!r}")
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Recent items
    # ------------------------------------------------------------------
    def _push_recent(self, path: str):
        if not path:
            return
        recent = [p for p in self.settings.get("recent", []) if p != path]
        recent.insert(0, path)
        self.settings["recent"] = recent[:10]
        settings_mod.save(self.settings)
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self):
        for item in list(self.recent_menu.GetMenuItems()):
            self.recent_menu.Delete(item)
        recent = self.settings.get("recent", [])
        if not recent:
            mi = self.recent_menu.Append(wx.ID_ANY, "(none yet)")
            mi.Enable(False)
            return
        for path in recent:
            mi = self.recent_menu.Append(wx.ID_ANY, path)
            self.Bind(wx.EVT_MENU, lambda e, p=path: self._on_open_recent(p), mi)

    def _on_open_recent(self, path: str):
        if self._is_building():
            return
        if not os.path.exists(path):
            wx.MessageBox(f"No longer found:\n{path}", "Missing item",
                          wx.OK | wx.ICON_WARNING, self)
            recent = [p for p in self.settings.get("recent", []) if p != path]
            self.settings["recent"] = recent
            settings_mod.save(self.settings)
            self._rebuild_recent_menu()
            return
        if os.path.isdir(path):
            self._load_folder(path)
        elif path.lower().endswith(".cfjob"):
            self._load_job_file(path)
        else:
            self._open_master_path(path)


    # ------------------------------------------------------------------
    # Edit-existing-master mode
    # ------------------------------------------------------------------
    def _on_open_master(self, _evt):
        if self._is_building():
            return
        start_dir = (self.settings.get("last_input_dir", "")
                     or self.folder or "")
        dlg = wx.FileDialog(
            self, "Open an existing chaptered file", defaultDir=start_dir,
            wildcard=("Audio with chapters (*.mp3;*.m4b;*.m4a;*.mp4)|"
                      "*.mp3;*.m4b;*.m4a;*.mp4|All files (*.*)|*.*"),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        path = dlg.GetPath()
        dlg.Destroy()
        self._open_master_path(path)

    def _open_master_path(self, path: str):
        if not self._confirm_discard_edits():
            return
        self._announce("Reading chapters…")
        wx.BeginBusyCursor()
        try:
            tags, chapters, total_ms = core.read_master(path)
        except core.ChapterForgeError as exc:
            wx.MessageBox(str(exc), "Could not read file",
                          wx.OK | wx.ICON_ERROR, self)
            return
        finally:
            if wx.IsBusy():
                wx.EndBusyCursor()
        self._undo.clear()
        self._update_undo_menu()
        self._enter_edit_mode(path, tags, chapters, total_ms)
        self._push_recent(path)

    def _enter_edit_mode(self, path, tags, chapters, total_ms):
        self.player.release(recreate=True)
        self.mode = "edit"
        # Always land on the chapter list page when opening a file.
        if self._page_tags.IsShown():
            self._page_tags.Hide()
            self._page_ch.Show()
            self.panel.Layout()
        self.edit_path = path
        self.edit_chapters = list(chapters)
        self.edit_total_ms = total_ms
        self.edit_dirty = False
        self._audio_order = list(range(len(chapters)))
        self.items = []
        self.folder = os.path.dirname(path)
        self.folder_ctrl.ChangeValue(path)
        self._apply_tags_to_ui(tags)
        self._refresh_list(select=0 if chapters else -1)
        self.ch_list_label.SetLabel("Chapter &list:")
        col4 = wx.ListItem()
        col4.SetText("URL / Link")
        self.list.SetColumn(4, col4)
        is_mp3 = core.output_format(path) == "mp3"
        note = ("" if is_mp3 else
                " This is an M4B/MP4 file, so use Save As to write a new file"
                " (in-place saving is MP3 only).")
        self._announce(
            f"Editing {os.path.basename(path)}: {len(chapters)} chapter(s). "
            f"Edit titles, links, images and tags. In this mode, Move Up and "
            f"Move Down swap chapter titles without moving the audio, and "
            f"Remove is replaced by Merge Up, which combines a chapter into "
            f"the one above it. Press F1 on a button for more." + note)
        if self.player.load(path, chapters):
            self.panel.Layout()
        self.list.SetFocus()

    def _enter_build_mode(self):
        self.mode = "build"
        self.edit_path = ""
        self.edit_chapters = []
        self.edit_total_ms = 0
        self.edit_dirty = False
        self._audio_order = []
        if self._page_tags.IsShown():
            self._page_tags.Hide()
            self._page_ch.Show()
            self.panel.Layout()
        self.ch_list_label.SetLabel("Chapter &list (one per source file):")
        col4 = wx.ListItem()
        col4.SetText("Source file")
        self.list.SetColumn(4, col4)
        self._update_command_state()

    def _apply_tags_to_ui(self, tags: core.Tags):
        self.tag_title.ChangeValue(tags.title)
        self.tag_artist.ChangeValue(tags.artist)
        self.tag_album.ChangeValue(tags.album)
        self.tag_album_artist.ChangeValue(tags.album_artist)
        self.tag_genre.ChangeValue(tags.genre)
        self.tag_year.ChangeValue(tags.year)
        self.tag_comment.ChangeValue(tags.comment)

    def _audio_reordered(self) -> bool:
        return (bool(self._audio_order) and
                self._audio_order != list(range(len(self._audio_order))))

    def _on_save_edit(self, _evt):
        if self.mode != "edit" or not self._edit_is_mp3():
            return
        if self.title_ctrl.HasFocus():
            self._on_apply_title(wx.CommandEvent())
        if self._audio_reordered():
            ans = wx.MessageBox(
                "You have reordered the chapters. Should the audio also be "
                "reordered in the saved file?\n\n"
                "Yes - create a new MP3 with audio in the new order (original unchanged)\n"
                "No  - save labels and tags only (audio stays in its current order)",
                "Reorder audio?",
                wx.YES_NO | wx.ICON_QUESTION, self)
            if ans == wx.YES:
                self._start_reorder_audio()
                return
        tags = self._collect_tags()
        # The player holds the file open; release before re-tagging.
        self.player.release(recreate=True)
        try:
            core.save_tags_chapters_inplace(
                self.edit_path, self.edit_chapters, tags)
        except core.ChapterForgeError as exc:
            wx.MessageBox(str(exc), "Could not save",
                          wx.OK | wx.ICON_ERROR, self)
            self.player.load(self.edit_path, self.edit_chapters)
            return
        self.edit_dirty = False
        if bool(self.settings.get("write_pod2", False)):
            try:
                core.write_pod2_chapters(
                    self.edit_path, self.edit_chapters, self.edit_total_ms)
            except OSError:
                pass
        self._announce(f"Saved changes to {os.path.basename(self.edit_path)}.")
        wx.MessageBox(f"Saved changes to:\n{self.edit_path}",
                      "Saved", wx.OK | wx.ICON_INFORMATION, self)
        # Reload so the player reflects the new tags/chapters.
        self.player.load(self.edit_path, self.edit_chapters)

    def _on_save_split_files(self, _evt):
        """Split the open master into one file per chapter using lossless FFmpeg copy."""
        if self._is_building() or self.mode != "edit" or len(self.edit_chapters) < 2:
            return
        dlg = wx.DirDialog(
            self, "Choose a folder to save the chapter files",
            defaultPath=os.path.dirname(self.edit_path) if self.edit_path else "",
            style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        output_dir = dlg.GetPath()
        dlg.Destroy()
        chapters = list(self.edit_chapters)
        src = self.edit_path
        self._announce(f"Splitting {len(chapters)} chapter(s) into {output_dir}...")
        self.canceller = core.Canceller()

        def work():
            try:
                paths = core.split_into_files(src, chapters, output_dir,
                                              progress=lambda f: None)
                wx.CallAfter(self._split_files_done, paths, None)
            except core.ChapterForgeError as exc:
                wx.CallAfter(self._split_files_done, [], str(exc))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _split_files_done(self, paths: list, error):
        self.worker = None
        self.canceller = None
        if error:
            wx.MessageBox(str(error), "Split failed", wx.OK | wx.ICON_ERROR, self)
            self._announce("Split failed.")
        else:
            self._announce(f"Saved {len(paths)} chapter file(s).")
            wx.MessageBox(
                f"Saved {len(paths)} chapter file(s) successfully.",
                "Split complete", wx.OK | wx.ICON_INFORMATION, self)

    def _on_save_as(self, _evt):
        if self._is_building():
            return
        if self.title_ctrl.HasFocus():
            self._on_apply_title(wx.CommandEvent())
        if self.mode == "edit":
            self._save_edit_as()
        else:
            # In build mode, Save As is a convenient "build to a chosen file".
            if self._on_set_output(None):
                self._on_build(None)

    def _save_edit_as(self):
        if not self.edit_path:
            return
        ext = os.path.splitext(self.edit_path)[1] or ".mp3"
        default_dir = self.settings.get("last_output_dir", "") or self.folder
        stem = os.path.splitext(os.path.basename(self.edit_path))[0]
        dlg = wx.FileDialog(
            self, "Save edited master as", defaultDir=default_dir,
            defaultFile=f"{stem} (edited){ext}",
            wildcard=f"Audio (*{ext})|*{ext}|All files (*.*)|*.*",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        dest = dlg.GetPath()
        dlg.Destroy()
        if not os.path.splitext(dest)[1]:
            dest += ext
        if self._audio_reordered():
            ans = wx.MessageBox(
                "You have reordered the chapters. Should the audio also be "
                "reordered in the new file?\n\n"
                "Yes - write audio in the new chapter order\n"
                "No  - copy audio as-is, only labels change",
                "Reorder audio?",
                wx.YES_NO | wx.ICON_QUESTION, self)
            if ans == wx.YES:
                self._start_reorder_audio(dest)
                return
        tags = self._collect_tags()
        self._announce("Saving a copy…")
        wx.BeginBusyCursor()
        try:
            core.save_master_as(self.edit_path, dest, self.edit_chapters, tags)
        except core.ChapterForgeError as exc:
            wx.MessageBox(str(exc), "Could not save", wx.OK | wx.ICON_ERROR, self)
            return
        finally:
            if wx.IsBusy():
                wx.EndBusyCursor()
        if bool(self.settings.get("write_pod2", False)):
            try:
                core.write_pod2_chapters(dest, self.edit_chapters, self.edit_total_ms)
            except OSError:
                pass
        self._announce(f"Saved a copy to {os.path.basename(dest)}.")
        wx.MessageBox(f"Saved to:\n{dest}", "Saved",
                      wx.OK | wx.ICON_INFORMATION, self)

    def _start_reorder_audio(self, dest: str = ""):
        """Prompt for output path if needed, then reorder audio on a worker thread."""
        if not dest:
            ext = os.path.splitext(self.edit_path)[1] or ".mp3"
            default_dir = self.settings.get("last_output_dir", "") or self.folder
            stem = os.path.splitext(os.path.basename(self.edit_path))[0]
            dlg = wx.FileDialog(
                self, "Save reordered audio as", defaultDir=default_dir,
                defaultFile=f"{stem} (reordered){ext}",
                wildcard=f"Audio (*{ext})|*{ext}|All files (*.*)|*.*",
                style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
            if dlg.ShowModal() != wx.ID_OK:
                dlg.Destroy()
                return
            dest = dlg.GetPath()
            dlg.Destroy()
            if not os.path.splitext(dest)[1]:
                dest += ext
        tags = self._collect_tags()
        order = list(self._audio_order)
        chapters = list(self.edit_chapters)
        self.canceller = core.Canceller()
        self._update_command_state()
        self._announce("Reordering audio chapters - please wait…")
        self.worker = threading.Thread(
            target=self._thread_reorder_audio,
            args=(dest, chapters, order, tags),
            daemon=True)
        self.worker.start()

    def _thread_reorder_audio(self, dest, chapters, order, tags):
        try:
            result = core.reorder_audio_chapters(
                self.edit_path, chapters, order, dest, tags,
                self.canceller,
                progress=lambda pct: wx.CallAfter(
                    self.gauge.SetValue, int(pct * 100)))
            wx.CallAfter(self._on_reorder_audio_done, dest, result)
        except core.ChapterForgeError as exc:
            wx.CallAfter(self._on_reorder_audio_failed, str(exc))

    def _on_reorder_audio_done(self, dest: str, result):
        self.worker = None
        self.gauge.SetValue(0)
        self._audio_order = list(range(len(self._audio_order)))
        self._update_command_state()
        self._announce(f"Reordered audio saved as {os.path.basename(dest)}.")
        wx.MessageBox(
            f"Reordered audio saved to:\n{dest}",
            "Saved", wx.OK | wx.ICON_INFORMATION, self)

    def _on_reorder_audio_failed(self, msg: str):
        self.worker = None
        self.gauge.SetValue(0)
        self._update_command_state()
        self._announce("Audio reorder failed.")
        wx.MessageBox(msg, "Could not reorder audio", wx.OK | wx.ICON_ERROR, self)

    # ------------------------------------------------------------------
    # Silence auto-chaptering / batch
    # ------------------------------------------------------------------
    def _on_silence(self, _evt):
        if self._is_building():
            return
        if not self._confirm_discard_edits():
            return
        start_dir = self.settings.get("last_input_dir", "") or self.folder or ""
        dlg = wx.FileDialog(
            self, "Choose an audio file to analyse for silence",
            defaultDir=start_dir,
            wildcard=("Audio (*.mp3;*.m4b;*.m4a;*.mp4;*.wav)|"
                      "*.mp3;*.m4b;*.m4a;*.mp4;*.wav|All files (*.*)|*.*"),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        path = dlg.GetPath()
        dlg.Destroy()
        noise = float(self.settings.get("silence_noise_db", -30.0))
        min_sil = float(self.settings.get("silence_min_seconds", 0.8))
        self._announce("Analyzing audio for silent gaps...")
        self.canceller = core.Canceller()
        self.worker = threading.Thread(
            target=self._analyze_silence,
            args=(path, noise, min_sil),
            daemon=True)
        self.worker.start()

    def _analyze_silence(self, path: str, noise_db: float, min_silence: float):
        """Background thread: analyze audio for silent gaps."""
        try:
            tags, _, total_ms = core.read_master(path)
            chapters = core.detect_silence_chapters(
                path, noise_db=noise_db, min_silence=min_silence)
            wx.CallAfter(self._silence_analysis_done, path, tags, total_ms, chapters, None)
        except Exception as exc:
            wx.CallAfter(self._silence_analysis_done, path, None, None, None, str(exc))

    def _silence_analysis_done(self, path: str, tags, total_ms: int, chapters, error: Optional[str]):
        """Called from main thread with silence analysis results."""
        self.worker = None
        if error:
            wx.MessageBox(str(error), "Could not analyze file",
                          wx.OK | wx.ICON_ERROR, self)
            return
        if not chapters:
            wx.MessageBox(
                "No silent gaps long enough to split on were found.\n\n"
                "Try lowering the minimum silence length or raising the "
                "threshold in Tools - Settings.",
                "No chapters detected", wx.OK | wx.ICON_INFORMATION, self)
            return
        self._enter_edit_mode(path, tags or core.Tags(), chapters, total_ms)
        self._announce(
            f"Detected {len(chapters)} chapter(s) from silence. Rename them, "
            "then Save Changes (MP3) or Save As.")

    def _on_batch(self, _evt):
        if self._is_building():
            return
        dlg = wx.DirDialog(
            self, "Choose a parent folder containing one sub-folder per book",
            style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        parent = dlg.GetPath()
        dlg.Destroy()
        folders = core.find_book_folders(parent)
        if not folders:
            wx.MessageBox(
                "No sub-folders containing MP3 files were found there.",
                "Nothing to build", wx.OK | wx.ICON_INFORMATION, self)
            return
        fmt = self.settings.get("output_format", "mp3")
        names = "\n".join(f"• {os.path.basename(f)}" for f in folders[:20])
        more = "" if len(folders) <= 20 else f"\n…and {len(folders) - 20} more"
        if wx.MessageBox(
                f"Build a {fmt.upper()} master for each of these "
                f"{len(folders)} folder(s)?\n\n{names}{more}",
                "Batch build", wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
            return
        self._run_batch(folders, fmt)

    def _run_batch(self, folders, fmt):
        bitrate = self.settings.get("bitrate", "192k")
        normalize = bool(self.settings.get("normalize", False))
        write_pod2 = bool(self.settings.get("write_pod2", False))
        gap_ms = self._gap_ms()
        self.canceller = core.Canceller()
        self._last_pct = -1
        self.gauge.SetValue(0)
        self._announce(f"Batch building {len(folders)} folder(s)…")
        self._update_command_state_building(True)
        total = len(folders)

        def progress_for(i):
            def cb(frac):
                overall = (i + frac) / total
                wx.PostEvent(self, _ThreadEvent(EVT_PROGRESS, overall))
            return cb

        def run():
            results = []
            errors = []
            try:
                for i, folder in enumerate(folders):
                    if self.canceller.cancelled:
                        break
                    try:
                        res = core.build_folder(
                            folder, ext=("." + fmt), bitrate=bitrate,
                            normalize=normalize, write_pod2=write_pod2,
                            gap_ms=gap_ms, canceller=self.canceller,
                            progress=progress_for(i))
                        results.append(res)
                    except core.BuildCancelled:
                        break
                    except Exception as exc:
                        errors.append(f"{os.path.basename(folder)}: {exc}")
                wx.PostEvent(self, _ThreadEvent(
                    EVT_DONE, ("batch", results, errors)))
            except Exception as exc:
                wx.PostEvent(self, _ThreadEvent(EVT_FAILED, str(exc)))

        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()

    def _on_generate_job(self, _evt):
        if not self.items:
            return
        if self.title_ctrl.HasFocus():
            self._on_apply_title(wx.CommandEvent())
        default_dir = self.folder or self.settings.get("last_input_dir", "") or ""
        dlg = wx.FileDialog(
            self, "Save job file", defaultDir=default_dir,
            defaultFile=manifest_mod.DEFAULT_JOB_NAME,
            wildcard="ChapterForge job (*.cfjob)|*.cfjob",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        path = dlg.GetPath()
        dlg.Destroy()
        output_name = os.path.basename(self.output_path) if self.output_path else ""
        try:
            manifest_mod.write_manifest(
                path, self.items, self._collect_tags(),
                output_name=output_name,
                bitrate=self.settings.get("bitrate", "192k"),
                normalize=bool(self.settings.get("normalize", False)))
        except OSError as exc:
            wx.MessageBox(str(exc), "Could not save job file",
                          wx.OK | wx.ICON_ERROR, self)
            return
        self._announce(f"Saved job file to {path}.")

    def _on_load_job(self, _evt):
        if self._is_building():
            return
        start_dir = self.folder or self.settings.get("last_input_dir", "") or ""
        dlg = wx.FileDialog(
            self, "Load job file", defaultDir=start_dir,
            wildcard="ChapterForge job (*.cfjob)|*.cfjob|All files (*.*)|*.*",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        path = dlg.GetPath()
        dlg.Destroy()
        self._load_job_file(path)

    def _load_job_file(self, path: str):
        folder = os.path.dirname(path)
        if not self._confirm_discard_edits():
            return
        try:
            manifest = manifest_mod.read_manifest(path)
        except OSError as exc:
            wx.MessageBox(str(exc), "Could not read job file",
                          wx.OK | wx.ICON_ERROR, self)
            return
        entries, missing = manifest_mod.resolve_manifest(manifest, folder)
        if missing:
            wx.MessageBox(
                "These files listed in the job file were not found:\n\n" +
                "\n".join(missing[:12]),
                "Missing files", wx.OK | wx.ICON_ERROR, self)
            return
        if not entries:
            wx.MessageBox("The job file lists no usable tracks.",
                          "Empty job file", wx.OK | wx.ICON_ERROR, self)
            return
        self._announce("Loading job file and probing audio...")
        self.canceller = core.Canceller()
        self.worker = threading.Thread(
            target=self._probe_job_entries,
            args=(path, folder, entries, manifest),
            daemon=True)
        self.worker.start()

    def _probe_job_entries(self, path: str, folder: str, entries, manifest):
        """Background thread: probe files from job manifest."""
        try:
            items = core.items_from_entries(entries)
            wx.CallAfter(self._job_loaded, path, folder, items, manifest, None)
        except Exception as exc:
            wx.CallAfter(self._job_loaded, path, folder, None, manifest, str(exc))

    def _job_loaded(self, path: str, folder: str, items, manifest, error: Optional[str]):
        """Called from main thread with probed job file data."""
        self.worker = None
        if error:
            wx.MessageBox(str(error), "Could not load job file",
                          wx.OK | wx.ICON_ERROR, self)
            return
        self.items = items
        self.folder = folder
        self.player.release(recreate=True)
        self._enter_build_mode()
        self.folder_ctrl.ChangeValue(folder)
        self._apply_manifest_options(manifest, folder)
        self._refresh_list(select=0 if items else -1)
        if not self.output_path:
            out_name = manifest.option("output", "")
            if out_name:
                self._set_output_path(os.path.join(folder, out_name), auto=True)
            else:
                self._set_suggested_output(folder)
        self._announce(f"Loaded {len(items)} chapter(s) from job file.")
        self._push_recent(path)
        self._update_estimate()

    def _apply_manifest_options(self, manifest, folder: str):
        tags = manifest_mod.manifest_tags(manifest, folder)
        self.tag_title.ChangeValue(tags.title)
        self.tag_artist.ChangeValue(tags.artist)
        self.tag_album.ChangeValue(tags.album)
        self.tag_album_artist.ChangeValue(tags.album_artist)
        self.tag_genre.ChangeValue(tags.genre)
        self.tag_year.ChangeValue(tags.year)
        self.tag_comment.ChangeValue(tags.comment)
        if tags.cover_path:
            self._set_cover(tags.cover_path)
        self.settings["bitrate"] = manifest.bitrate
        self.settings["normalize"] = manifest.normalize
        settings_mod.save(self.settings)

    def _on_watch_folders(self, _evt):
        from .watch_dialogs import manage_processes
        manage_processes(self)

    def _on_toggle_autostart(self, _evt):
        from . import autostart
        want = self.mi_autostart.IsChecked()
        if not autostart.set_enabled(want):
            self.mi_autostart.Check(autostart.is_enabled())
            wx.MessageBox("Could not update the sign-in setting.",
                          "Autostart", wx.OK | wx.ICON_WARNING, self)
            return
        self._announce("Watcher will start at sign-in." if want
                       else "Watcher will no longer start at sign-in.")

    def _on_start_watcher(self, _evt):
        from .tray import ChapterForgeTaskBarIcon, WatcherController
        if self._watch_controller is not None:
            if not self._watch_controller.running:
                self._watch_controller.start()
                if self._tray:
                    self._tray.refresh()
                self.notifier.notify(__app_name__, "Watching resumed.",
                                     "info", speak=True)
            self.Hide()
            return
        self._watch_controller = WatcherController(self.notifier)
        self._tray = ChapterForgeTaskBarIcon(
            self._watch_controller,
            on_open=self._restore_from_tray,
            on_manage=lambda: self._on_watch_folders(None),
            on_quit=self._quit_from_tray,
            get_player=lambda: self.player)
        self._watch_controller.start()
        self.notifier.notify(
            __app_name__, "Background watcher started. ChapterForge is in the "
            "system tray.", "info", speak=True)
        self.Hide()

    def _restore_from_tray(self):
        self.Show()
        self.Raise()

    def _shutdown_tray(self):
        if self._watch_controller:
            self._watch_controller.stop(join=False)
            self._watch_controller = None
        if self._tray:
            self._tray.RemoveIcon()
            self._tray.Destroy()
            self._tray = None

    def _quit_from_tray(self):
        self._shutdown_tray()
        try:
            self.player.shutdown()
        except Exception:
            pass
        self.Destroy()

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------
    def _on_wizard(self, _evt=None):
        from . import wizard
        wizard.show_wizard(
            self, self.settings,
            on_open_folder=lambda: self._on_open(None),
            on_setup_watch=lambda: self._on_watch_folders(None))
        self.settings["wizard_seen"] = True
        settings_mod.save(self.settings)

    def _on_context_help(self, _evt):
        """F1: explain whichever control currently has keyboard focus."""
        from . import context_help
        title, body = context_help.describe_focused(self)
        focused = wx.Window.FindFocus()
        dlg = context_help.ContextHelpDialog(self, title, body)
        dlg.ShowModal()
        dlg.Destroy()
        if focused:
            focused.SetFocus()

    def _on_guide(self, _evt):
        from . import docs
        if docs.open_doc(docs.USER_GUIDE):
            self._announce("Opening the User Guide in your browser.")
            return
        guide = (
            "ChapterForge - Quick Start\n"
            "\n"
            "The Task dropdown at the top controls what you are doing:\n"
            "\n"
            "Build new master from MP3 files:\n"
            "1. Choose 'Build new master' in the Task dropdown, then click "
            "Browse (or Ctrl+Shift+O) to select a folder of MP3 files. Each file "
            "becomes one chapter, sorted in natural (1, 2, 10) order.\n"
            "2. Review chapters in the list. Right-click for a context menu. "
            "Rename with Edit Chapter, reorder with Move Up/Down or "
            "Alt+Up/Down, remove with Delete.\n"
            "3. Fill in the master tags (title, artist, album, cover, etc.).\n"
            "4. Click 'Save to' to choose where to save, "
            "then Build (Ctrl+B or just Ctrl+S).\n"
            "\n"
            "Edit chapters in an existing file:\n"
            "Choose 'Edit chapters in an existing file' in the Task dropdown "
            "(or Ctrl+O). Open a chaptered MP3 or M4B. Rename chapters, fix "
            "tags, merge or split boundaries, then Save Changes (Ctrl+S) "
            "for MP3 or File → Save As for M4B.\n"
            "\n"
            "Tip: press Ctrl+Shift+P to search all commands by name.\n"
            "\n"
            "Job files (.cfjob): save the current order, titles and tags with "
            "File → Generate Job File, hand-edit it, and reload with File → "
            "Load Job File. Drop one named chapters.cfjob into a watched folder "
            "to control a background build.\n"
            "\n"
            "Background watcher: Tools → Watch Folders defines reusable "
            "processes. Tools → Start Background Watcher minimises ChapterForge "
            "to the system tray and builds any new sub-folder of MP3s "
            "automatically, with notifications.\n"
            "\n"
            "Everything is keyboard accessible - see Help → Keyboard Shortcuts.")
        self._scroll_dialog("User Guide", guide)

    def _on_changelog_doc(self, _evt):
        self._open_doc_page("CHANGELOG", "Release Notes")

    def _on_docs_home(self, _evt):
        self._open_doc_page("HOME", "Documentation")

    def _open_doc_page(self, page_attr: str, label: str):
        from . import docs
        page = getattr(docs, page_attr, docs.HOME)
        if docs.open_doc(page):
            self._announce(f"Opening {label} in your browser.")
        else:
            wx.MessageBox(
                f"The {label} could not be found in this build.\n\n"
                "You can read the documentation online at the project website "
                "(Help → Visit Project Website).",
                "Documentation not found", wx.OK | wx.ICON_INFORMATION, self)

    def _on_keys(self, _evt):
        from . import docs
        docs.open_doc(docs.USER_GUIDE, anchor="2-keyboard-shortcuts")
        self._announce("Opening keyboard shortcuts in your browser.")

    def _scroll_dialog(self, title: str, text: str):
        dlg = wx.Dialog(self, title=title,
                        style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        sizer = wx.BoxSizer(wx.VERTICAL)
        ctrl = wx.TextCtrl(
            dlg, value=text,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP)
        ctrl.SetName(title)
        sizer.Add(ctrl, 1, wx.EXPAND | wx.ALL, 8)
        sizer.Add(dlg.CreateButtonSizer(wx.OK), 0, wx.EXPAND | wx.ALL, 8)
        dlg.SetSizer(sizer)
        dlg.SetSize((620, 460))
        ctrl.SetInsertionPoint(0)
        ctrl.SetFocus()
        dlg.ShowModal()
        dlg.Destroy()

    def _on_download_ffmpeg(self, _evt):
        """Download FFmpeg from the Help menu."""
        try:
            core._find_tool("ffmpeg")
            core._find_tool("ffprobe")
            wx.MessageBox(
                "FFmpeg is already installed and working. No download needed.",
                "FFmpeg Found", wx.OK | wx.ICON_INFORMATION, self)
            return
        except core.FFmpegNotFoundError:
            pass
        result = wx.MessageBox(
            "FFmpeg was not found on this system.\n\n"
            "ChapterForge will download FFmpeg now. "
            "The download is free and takes about 1-2 minutes.",
            "Download FFmpeg",
            wx.YES_NO | wx.ICON_QUESTION, self)
        if result != wx.YES:
            return
        dlg = FFmpegSetupDialog(self)
        import threading as _threading
        def work():
            try:
                dlg.update_status("Downloading FFmpeg from gyan.dev - please wait...")
                import importlib.util
                spec = importlib.util.spec_from_file_location(
                    "get_ffmpeg",
                    os.path.join(os.path.dirname(__file__), "..", "tools", "get_ffmpeg.py"))
                get_ffmpeg = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(get_ffmpeg)
                if get_ffmpeg.download_ffmpeg():
                    dlg.download_complete(True,
                        "FFmpeg downloaded successfully. "
                        "Restart ChapterForge to apply.")
                else:
                    dlg.download_complete(False,
                        "Download failed. Visit ffmpeg.org to install manually.")
            except Exception as exc:
                dlg.download_complete(False, f"Download error: {exc}")
        _threading.Thread(target=work, daemon=True).start()
        dlg.ShowModal()
        dlg.Destroy()
        self.SetFocus()

    def _on_feature_flags(self, _evt):
        """Choose a release channel and show or hide optional features."""
        dlg = feature_flags.FeatureFlagsDialog(self, self.settings)
        if dlg.ShowModal() == wx.ID_OK:
            overrides = dlg.get_overrides()
            channel = dlg.get_channel()
            changed = (overrides != self.settings.get("feature_flags", {})
                       or channel != feature_flags.get_channel(self.settings))
            if changed:
                self.settings["feature_flags"] = overrides
                feature_flags.set_channel(self.settings, channel)
                settings_mod.save(self.settings)
                self._announce(
                    "Feature flags updated. Restart ChapterForge for the "
                    "change to take effect.")
        dlg.Destroy()
        self.SetFocus()

    def _on_reset_feature_flags(self, _evt):
        """Re-enable every optional feature from the Help menu."""
        if not self.settings.get("feature_flags", {}):
            wx.MessageBox(
                "Every optional feature is already enabled.",
                "Reset Feature Flags", wx.OK | wx.ICON_INFORMATION, self)
            return
        result = wx.MessageBox(
            "Re-enable every optional feature?\n\n"
            "Restart ChapterForge for the change to take effect.",
            "Reset Feature Flags to Defaults",
            wx.YES_NO | wx.ICON_QUESTION, self)
        if result != wx.YES:
            return
        feature_flags.reset_to_defaults(self.settings)
        settings_mod.save(self.settings)
        self._announce(
            "Feature flags reset to defaults. Restart ChapterForge for the "
            "change to take effect.")

    def _on_check_updates(self, _evt):
        from . import updates
        self.mi_update.Enable(False)
        self._announce("Checking for updates…")

        def work():
            try:
                release = updates.check_for_update()
                wx.CallAfter(self._update_check_done, release, None)
            except updates.UpdateCheckError as exc:
                wx.CallAfter(self._update_check_done, None, str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _check_updates_on_startup(self):
        """Silent background update check at launch - only notifies if an update is found."""
        from . import updates

        def work():
            try:
                release = updates.check_for_update()
                if release is not None:
                    wx.CallAfter(self._show_update_dialog, release)
            except updates.UpdateCheckError:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _update_check_done(self, release, error):
        self.mi_update.Enable(True)
        if error:
            self._announce("Update check failed.")
            wx.MessageBox(
                f"Could not check for updates:\n\n{error}",
                "Update check failed", wx.OK | wx.ICON_WARNING, self)
            return
        if release is None:
            self._announce("ChapterForge is up to date.")
            wx.MessageBox(
                f"You are running the latest version ({__version__}).",
                "No updates", wx.OK | wx.ICON_INFORMATION, self)
            return
        self._show_update_dialog(release)

    def _show_update_dialog(self, release):
        """Show the 'update available' dialog; shared by manual and startup checks."""
        from . import updates
        self._announce(f"Update available: {release.version}.")
        notes = release.notes.strip()
        if len(notes) > 600:
            notes = notes[:600] + "…"
        installable = updates.is_installable_asset(release.download_url)
        if installable:
            msg = (f"A new version is available: {release.version} "
                   f"(you have {__version__}).\n\n{notes}\n\n"
                   "ChapterForge can download and install it for you, or just "
                   "open the download page.")
            dlg = wx.MessageDialog(self, msg, "Update available",
                                   wx.YES_NO | wx.CANCEL | wx.ICON_INFORMATION)
            dlg.SetYesNoCancelLabels("&Download && Install", "Open &Page",
                                     "&Later")
            result = dlg.ShowModal()
            dlg.Destroy()
            if result == wx.ID_YES:
                self._download_and_install(release)
            elif result == wx.ID_NO:
                wx.LaunchDefaultBrowser(
                    release.download_url or updates.RELEASES_PAGE)
            return
        msg = (f"A new version is available: {release.version} "
               f"(you have {__version__}).\n\n"
               f"{notes}\n\nOpen the download page now?")
        if wx.MessageBox(msg, "Update available",
                         wx.YES_NO | wx.ICON_INFORMATION, self) == wx.YES:
            wx.LaunchDefaultBrowser(release.download_url or updates.RELEASES_PAGE)

    def _download_and_install(self, release):
        from . import updates
        prog = wx.ProgressDialog(
            "Downloading update",
            f"Downloading ChapterForge {release.version}…",
            maximum=100, parent=self,
            style=(wx.PD_APP_MODAL | wx.PD_AUTO_HIDE | wx.PD_CAN_ABORT
                   | wx.PD_ELAPSED_TIME))
        state = {"cancelled": False, "path": None, "error": None}

        def on_progress(read, total):
            def upd():
                if total > 0:
                    pct = min(100, int(read * 100 / total))
                    cont, _ = prog.Update(
                        pct, f"Downloaded {core.format_size(read)} of "
                             f"{core.format_size(total)} ({pct}%).")
                else:
                    cont, _ = prog.Pulse(
                        f"Downloaded {core.format_size(read)}…")
                if not cont:
                    state["cancelled"] = True
            wx.CallAfter(upd)
            if state["cancelled"]:
                raise updates.UpdateCheckError("Download cancelled.")

        def work():
            try:
                state["path"] = updates.download_release_asset(
                    release, progress=on_progress)
            except updates.UpdateCheckError as exc:
                state["error"] = str(exc)
            except Exception as exc:  # defensive
                state["error"] = str(exc)
            wx.CallAfter(finish)

        def finish():
            try:
                prog.Destroy()
            except Exception:
                pass
            if state["cancelled"] or state["error"] == "Download cancelled.":
                self._announce("Update download cancelled.")
                return
            if state["error"]:
                self._announce("Update download failed.")
                wx.MessageBox(
                    f"Could not download the update:\n\n{state['error']}",
                    "Download failed", wx.OK | wx.ICON_ERROR, self)
                return
            self._announce("Update downloaded.")
            if wx.MessageBox(
                    "The update has been downloaded. ChapterForge will now "
                    "close so the installer can replace it.\n\nContinue?",
                    "Install update", wx.YES_NO | wx.ICON_INFORMATION,
                    self) != wx.YES:
                self._announce("Update ready to install later.")
                return
            try:
                updates.launch_installer(state["path"])
            except updates.UpdateCheckError as exc:
                wx.MessageBox(str(exc), "Could not start installer",
                              wx.OK | wx.ICON_ERROR, self)
                return
            self._force_quit = True
            self.Close()

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    def _on_about(self, _evt):
        dlg = AboutDialog(self)
        dlg.ShowModal()
        dlg.Destroy()

    def _open_command_palette(self, _evt=None):
        CommandPaletteDialog(self).show()

    def _setup_startup_tray(self):
        """Create a tray icon for start-minimized mode (no watcher started)."""
        from .tray import ChapterForgeTaskBarIcon
        self._tray = ChapterForgeTaskBarIcon(
            None,
            on_open=self._restore_from_tray,
            on_manage=lambda: self._on_watch_folders(None),
            on_quit=self._quit_from_tray,
            get_player=lambda: self.player)

    def _on_minimize_to_tray(self, _evt=None):
        """Hide the window and show a tray icon so the user can restore later."""
        if self._tray is None:
            self._setup_startup_tray()
        self._announce("Minimized to system tray. Double-click the tray icon to restore.")
        self.Hide()

    def _on_close(self, evt):
        # When the background watcher is active, closing hides to the tray
        # instead of quitting, so watching continues. An update install forces
        # a real quit so the installer can replace the running files.
        if (self._tray is not None and not self._is_building()
                and not self._force_quit):
            self.Hide()
            evt.Veto()
            return
        if not self._force_quit and not self._confirm_discard_edits():
            evt.Veto()
            return
        if self._is_building():
            if wx.MessageBox(
                    "A build is in progress. Cancel it and quit?",
                    "Quit ChapterForge", wx.YES_NO | wx.ICON_QUESTION,
                    self) != wx.YES:
                evt.Veto()
                return
            if self.canceller:
                self.canceller.cancel()
            if self.worker:
                self.worker.join(timeout=5)
        try:
            self.player.shutdown()
        except Exception:
            pass
        self._shutdown_tray()
        evt.Skip()


class AboutDialog(wx.Dialog):
    """Accessible About window: app/version, developing organization, copyright
    and buttons that open each of the organization's services in a browser."""

    def __init__(self, parent):
        super().__init__(parent, title=f"About {__app_name__}",
                         style=wx.DEFAULT_DIALOG_STYLE)
        outer = wx.BoxSizer(wx.VERTICAL)

        def label(text, *, bold=False):
            st = wx.StaticText(self, label=text)
            if bold:
                f = st.GetFont()
                f.MakeBold()
                st.SetFont(f)
            outer.Add(st, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
            return st

        title = label(f"{__app_name__} {__version__}", bold=True)
        title.SetName(f"{__app_name__} version {__version__}")
        f = title.GetFont()
        f.SetPointSize(f.GetPointSize() + 3)
        f.MakeBold()
        title.SetFont(f)

        label("Combine a folder of MP3 files into a single master MP3 with "
              "embedded ID3v2 chapter markers, one per source file.")
        label("Fully keyboard accessible. Powered by FFmpeg and Mutagen.")

        outer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.ALL, 10)

        label("Developed by", bold=True)
        label(__org__)
        label(__copyright__)

        outer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.ALL, 10)

        services_lbl = label("Our services", bold=True)
        services_lbl.SetName("Our services. Activate a button to open it in "
                             "your browser.")

        for text, desc, url in SERVICES:
            btn = wx.Button(self, label=f"{text} - {desc}")
            btn.SetName(f"{text}. {desc}. Opens {url} in your browser.")
            btn.SetToolTip(url)
            btn.Bind(wx.EVT_BUTTON, lambda _e, u=url: wx.LaunchDefaultBrowser(u))
            outer.Add(btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 12)

        outer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.ALL, 10)

        website_btn = wx.Button(self, label="Visit Project Website")
        website_btn.SetName("Visit ChapterForge project website")
        website_btn.SetToolTip("https://chapterforge.app")
        website_btn.Bind(wx.EVT_BUTTON, lambda _e: wx.LaunchDefaultBrowser(
            "https://chapterforge.app"))
        outer.Add(website_btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 12)

        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        outer.Add(btns, 0, wx.EXPAND | wx.ALL, 12)
        self.SetSizerAndFit(outer)
        self.SetSize((540, 440))
        self.CentreOnParent()
        self._title_ctrl.SetFocus()


class _NamedAccessible(wx.Accessible):
    """Supplies a custom accessible name for composite Win32 controls (e.g.
    SpinCtrl) whose inner edit field is what NVDA focuses but has no label."""
    def __init__(self, ctrl, name):
        super().__init__(ctrl)
        self._name = name

    def GetName(self, childId):
        return (wx.ACC_OK, self._name)


class SettingsDialog(wx.Dialog):
    """Accessible preferences dialog. Reads from and writes back to a settings
    dict (the caller persists it). Every control has a label + accessible name."""

    def __init__(self, parent, settings: dict):
        super().__init__(parent, title="ChapterForge Settings",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.settings = settings
        outer = wx.BoxSizer(wx.VERTICAL)
        nb = wx.Notebook(self)
        nb.SetName("Settings categories")

        # ----------------------------------------------------------------
        # Preset bar (Feature 4)
        # ----------------------------------------------------------------
        preset_row = wx.BoxSizer(wx.HORIZONTAL)
        preset_lbl = wx.StaticText(self, label="&Preset:")
        preset_row.Add(preset_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        _built_in_names = sorted(BUILT_IN_PRESETS.keys())
        self._preset_names = (["-- Select a preset --"] + _built_in_names
                              + sorted(settings.get("presets", {}).keys()))
        self._preset_choice = wx.Choice(self, choices=self._preset_names)
        self._preset_choice.SetSelection(0)
        self._preset_choice.SetName("Load a saved preset to restore all build settings at once")
        self._preset_choice.Bind(wx.EVT_CHOICE, self._on_load_preset)
        preset_row.Add(self._preset_choice, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        btn_save_preset = wx.Button(self, label="&Save as Preset…")
        btn_save_preset.SetName("Save the current settings as a named preset")
        btn_save_preset.Bind(wx.EVT_BUTTON, self._on_save_preset)
        preset_row.Add(btn_save_preset, 0, wx.RIGHT, 4)

        btn_del_preset = wx.Button(self, label="&Delete Preset")
        btn_del_preset.SetName("Delete the currently selected preset")
        btn_del_preset.Bind(wx.EVT_BUTTON, self._on_delete_preset)
        preset_row.Add(btn_del_preset, 0)

        outer.Add(preset_row, 0, wx.EXPAND | wx.ALL, 8)

        def make_row(panel, grid, label_text, ctrl_factory, name, tip="",
                     use_accessible=False):
            lbl = wx.StaticText(panel, label=label_text)
            ctrl = ctrl_factory()
            ctrl.SetName(name)
            if use_accessible:
                ctrl.SetAccessible(_NamedAccessible(ctrl, name))
            if tip:
                ctrl.SetToolTip(tip)
            grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(ctrl, 1, wx.EXPAND)
            return ctrl

        def make_check(panel, grid, label_text, name, tip=""):
            """Checkbox row: column 1 is empty, column 2 is the checkbox with
            its full descriptive label= (NVDA reads button window text, not SetName)."""
            grid.Add((0, 0))
            cb = wx.CheckBox(panel, label=label_text)
            cb.SetName(name)
            if tip:
                cb.SetToolTip(tip)
            grid.Add(cb, 0, wx.ALIGN_CENTER_VERTICAL)
            return cb

        # ----------------------------------------------------------------
        # Tab 1 - General (player, appearance, startup)
        # ----------------------------------------------------------------
        gp = wx.Panel(nb)
        gg = wx.FlexGridSizer(0, 2, 10, 10)
        gg.AddGrowableCol(1, 1)

        def grow(label, factory, name, tip="", use_accessible=False):
            return make_row(gp, gg, label, factory, name, tip, use_accessible)

        def gcheck(label, name, tip=""):
            return make_check(gp, gg, label, name, tip)

        self.skip = grow(
            "Player &skip interval (seconds):",
            lambda: wx.SpinCtrl(gp, min=1, max=300,
                                initial=int(settings.get("skip_seconds", 10))),
            "Player skip interval in seconds",
            "How many seconds the Rewind and Forward buttons jump in the player.",
            use_accessible=True)

        self.volume = grow(
            "Default &volume (percent):",
            lambda: wx.SpinCtrl(gp, min=0, max=100,
                                initial=int(settings.get("default_volume", 80))),
            "Default playback volume percent",
            "Starting volume when a file is loaded. Can also be adjusted in the player.",
            use_accessible=True)

        self.pause_at_chapter_end = gcheck(
            "&Pause at the end of each chapter",
            "Pause at the end of each chapter",
            "When playing, stop at each chapter boundary instead of continuing\n"
            "into the next chapter. Press Play again to continue.")
        self.pause_at_chapter_end.SetValue(
            bool(settings.get("pause_at_chapter_end", False)))

        self.verbosity = grow(
            "Announcement &detail:",
            lambda: wx.Choice(gp, choices=["Quiet", "Normal", "Verbose"]),
            "Announcement detail",
            "How much ChapterForge announces via the screen reader.\n"
            "Quiet reduces repetitive messages; Verbose adds extra context.")
        vmap = {"quiet": 0, "normal": 1, "verbose": 2}
        self.verbosity.SetSelection(
            vmap.get(str(settings.get("announce_verbosity", "normal")), 1))

        self.text_scale = grow(
            "&Text size (percent):",
            lambda: wx.SpinCtrl(gp, min=50, max=300,
                                initial=int(settings.get("text_scale", 100))),
            "User interface text size percent",
            "Scale all text in the app. 100 is the default; 150 is 50% larger.\n"
            "Takes effect after clicking OK.",
            use_accessible=True)

        self.theme_choice = grow(
            "&Theme:",
            lambda: wx.Choice(gp, choices=["Follow system", "Light", "Dark",
                                            "High contrast"]),
            "Color theme",
            "Follow system: uses your Windows color scheme.\n"
            "Light: white background with dark text.\n"
            "Dark: dark background with light text.\n"
            "High contrast: black background with white text.\n"
            "Note: native list and text controls may not fully adopt the chosen\n"
            "theme on Windows. Takes effect after clicking OK.")
        _tmap = {"system": 0, "light": 1, "dark": 2, "high_contrast": 3}
        _stored_theme = str(settings.get("theme", "system"))
        # Migrate old high_contrast boolean
        if _stored_theme == "system" and settings.get("high_contrast", False):
            _stored_theme = "high_contrast"
        self.theme_choice.SetSelection(_tmap.get(_stored_theme, 0))

        self.start_minimized = gcheck(
            "Start &minimized in system tray",
            "Start minimized in system tray",
            "Hide the main window on launch and show a system tray icon instead.\n"
            "Double-click the icon to open ChapterForge. Takes effect at next launch.")
        self.start_minimized.SetValue(bool(settings.get("start_minimized", False)))

        self.check_updates_startup = gcheck(
            "Check for &updates on startup",
            "Check for updates on startup",
            "Silently check for a new version when ChapterForge launches.\n"
            "Only notifies you if an update is available.")
        self.check_updates_startup.SetValue(
            bool(settings.get("check_updates_startup", True)))

        self.beta_features = gcheck(
            "Enable &beta features (Auphonic integration)",
            "Enable beta features",
            "Enables the Auphonic menu for audio post-production.\n"
            "Beta features may change in future releases.\n"
            "Requires an Auphonic account (auphonic.com).")
        self.beta_features.SetValue(bool(settings.get("beta_features", False)))

        gp_sizer = wx.BoxSizer(wx.VERTICAL)
        gp_sizer.Add(gg, 1, wx.EXPAND | wx.ALL, 14)
        gp.SetSizer(gp_sizer)
        nb.AddPage(gp, "General")

        # ----------------------------------------------------------------
        # Tab 2 - Build (audio/encoding settings)
        # ----------------------------------------------------------------
        bp = wx.Panel(nb)
        bg = wx.FlexGridSizer(0, 2, 10, 10)
        bg.AddGrowableCol(1, 1)

        def brow(label, factory, name, tip="", use_accessible=False):
            return make_row(bp, bg, label, factory, name, tip, use_accessible)

        def bcheck(label, name, tip=""):
            return make_check(bp, bg, label, name, tip)

        self.fmt = brow(
            "Default output &format:",
            lambda: wx.Choice(bp, choices=["MP3 (.mp3)", "M4B audiobook (.m4b)",
                                            "FLAC lossless (.flac)",
                                            "Opus (.opus)"]),
            "Default output format",
            "MP3 works everywhere. M4B is the Apple audiobook format, supported by most "
            "podcast and audiobook apps. FLAC is lossless with Vorbis comment chapters. "
            "Opus produces smaller files than MP3 at equivalent quality.")
        _fmt_stored = settings.get("output_format", "mp3")
        self.fmt.SetSelection(
            1 if _fmt_stored == "m4b" else
            2 if _fmt_stored == "flac" else
            3 if _fmt_stored == "opus" else 0)

        self.title_src = brow(
            "Chapter titles fro&m:",
            lambda: wx.Choice(bp, choices=["Filename", "Embedded tag"]),
            "Chapter title source",
            "Filename: use each MP3's file name as its chapter title.\n"
            "Embedded tag: read the title tag already stored inside each MP3.")
        self.title_src.SetSelection(
            1 if settings.get("title_source") == core.TITLE_SOURCE_EMBEDDED else 0)

        self.bitrate = brow(
            "Re-encode &quality:",
            lambda: wx.Choice(bp, choices=["128k", "160k", "192k", "256k", "320k"]),
            "Re-encode quality",
            "Higher quality sounds better but produces a larger file.\n"
            "192k is the recommended setting for most audiobooks.")
        self.bitrate.SetStringSelection(str(settings.get("bitrate", "192k")))

        self.normalize = bcheck(
            "&Normalize loudness across the whole book (one pass)",
            "Normalize loudness across the whole book in one pass",
            "Loudness option 1 of 2. Applies a single loudness pass to the "
            "finished master at -16 LUFS.\n"
            "Simple and fast, but does not even out chapters that were recorded "
            "at very different volumes. For that, use the per-chapter option "
            "below instead.")
        self.normalize.SetValue(bool(settings.get("normalize", False)))

        self.gap = brow(
            "&Gap between chapters (seconds):",
            lambda: wx.SpinCtrlDouble(bp, min=0.0, max=30.0, inc=0.5,
                                     initial=float(settings.get("gap_seconds", 0.0))),
            "Gap of silence between chapters in seconds",
            "Insert a moment of silence between each chapter.\n"
            "0 means chapters play back-to-back with no pause.",
            use_accessible=True)
        self.gap.SetDigits(1)

        self.auto_cover = bcheck(
            "Auto-detect &cover image",
            "Auto-detect cover image",
            "Automatically find cover.jpg or folder.jpg in the source folder "
            "and use it as the album art.")
        self.auto_cover.SetValue(bool(settings.get("auto_cover", True)))

        self.write_pod2 = bcheck(
            "Write chapters &JSON (Podcasting 2.0)",
            "Write Podcasting 2.0 chapters JSON sidecar",
            "Save a .chapters.json file alongside the master.\n"
            "Required for chapter art and links in Podcasting 2.0 apps.")
        self.write_pod2.SetValue(bool(settings.get("write_pod2", False)))

        # Per-file LUFS normalization (the more thorough of the two options).
        self.per_file_norm = bcheck(
            "Normalize each chapter &individually to a target (MP3, recommended for uneven recordings)",
            "Normalize each chapter individually to a loudness target",
            "Loudness option 2 of 2. Normalizes every source file to the target "
            "below before joining them (MP3 output).\n"
            "Use this instead of the whole-book option when chapters were "
            "recorded at very different volumes. If both are on, this one wins.")
        self.per_file_norm.SetValue(bool(settings.get("per_file_normalize", False)))

        self.lufs_target = brow(
            "Per-chapter target loudness (&LUFS):",
            lambda: wx.SpinCtrlDouble(bp, min=-32.0, max=-6.0, inc=0.5,
                                      initial=float(settings.get("normalize_lufs", -16.0))),
            "Target loudness in LUFS for per-chapter normalization",
            "Applies to the per-chapter option above. Podcasts: -16 LUFS. "
            "Audiobooks: -18 LUFS. ACX submissions: -23 LUFS.",
            use_accessible=True)
        self.lufs_target.SetDigits(1)

        self.fade_dur = brow(
            "Chapter transition &fade (seconds):",
            lambda: wx.SpinCtrlDouble(bp, min=0.0, max=5.0, inc=0.25,
                                      initial=float(settings.get("fade_ms", 0)) / 1000.0),
            "Chapter transition fade duration in seconds",
            "Add a fade-out then fade-in at each chapter boundary.\n"
            "0 means no fade. 0.5 to 1 second is typical.\n"
            "Forces re-encoding of the faded portions.",
            use_accessible=True)
        self.fade_dur.SetDigits(2)

        self.trim_silence = bcheck(
            "Trim leading/trailing silence from each &track",
            "Trim leading and trailing silence from each source track before building",
            "Automatically strips room noise from the start and end of each file.\n"
            "Uses FFmpeg's silencedetect filter; configurable below.")
        self.trim_silence.SetValue(bool(settings.get("trim_silence", False)))

        self.trim_silence_db = brow(
            "Silence trim threshold (d&B):",
            lambda: wx.SpinCtrlDouble(bp, min=-90.0, max=0.0, inc=1.0,
                                      initial=float(settings.get("trim_silence_db", -50.0))),
            "Silence trim threshold in dB - audio quieter than this is considered silence",
            "Audio quieter than this level is considered silence.\n"
            "-50 dB works well for most studio recordings.",
            use_accessible=True)
        self.trim_silence_db.SetDigits(0)

        self.write_rss = bcheck(
            "Write RSS feed sidecar after each build",
            "Write a podcast RSS 2.0 feed file alongside each built master",
            "Generates a .rss file alongside the audio for self-hosted podcasters.\n"
            "Set your media hosting URL in the field below.")
        self.write_rss.SetValue(bool(settings.get("write_rss", False)))

        self.rss_media_url = brow(
            "Media hosting &URL (for RSS):",
            lambda: wx.TextCtrl(bp, value=settings.get("rss_media_url", "")),
            "Base URL where your audio files are hosted publicly",
            "The public URL where the built audio file can be downloaded.\n"
            "Used in the RSS enclosure tag. Example: https://media.example.com/podcast/")

        self.acx_check = bcheck(
            "Check &ACX compliance after each build",
            "Run ACX compliance check automatically after each successful build",
            "Measures integrated loudness, true peak, and noise floor.\n"
            "Reports pass/fail against ACX requirements immediately after building.")
        self.acx_check.SetValue(bool(settings.get("acx_check_after_build", False)))

        bp_sizer = wx.BoxSizer(wx.VERTICAL)
        bp_sizer.Add(bg, 1, wx.EXPAND | wx.ALL, 14)
        bp.SetSizer(bp_sizer)
        nb.AddPage(bp, "Build")

        # ----------------------------------------------------------------
        # Tab 3 - Advanced (silence detection, rarely changed)
        # ----------------------------------------------------------------
        ap = wx.Panel(nb)
        ag = wx.FlexGridSizer(0, 2, 10, 10)
        ag.AddGrowableCol(1, 1)

        def arow(label, factory, name, tip="", use_accessible=False):
            return make_row(ap, ag, label, factory, name, tip, use_accessible)

        hint_lbl = wx.StaticText(
            ap,
            label="These settings affect Tools → Auto-chapter by Silence.")
        hint_lbl.SetForegroundColour(
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))

        self.noise_db = arow(
            "Silence &threshold (dB):",
            lambda: wx.SpinCtrlDouble(ap, min=-90.0, max=0.0, inc=1.0,
                                     initial=float(settings.get("silence_noise_db", -30.0))),
            "Silence detection threshold in decibels",
            "Audio quieter than this level counts as silence.\n"
            "-30 dB is a good starting point for most recordings.",
            use_accessible=True)

        self.min_silence = arow(
            "Minimum silence &length (seconds):",
            lambda: wx.SpinCtrlDouble(ap, min=0.1, max=30.0, inc=0.1,
                                     initial=float(settings.get("silence_min_seconds", 0.8))),
            "Minimum silence length in seconds",
            "A gap shorter than this will not be treated as a chapter boundary.",
            use_accessible=True)

        ap_sizer = wx.BoxSizer(wx.VERTICAL)
        ap_sizer.Add(hint_lbl, 0, wx.ALL, 14)
        ap_sizer.Add(ag, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 14)
        ap.SetSizer(ap_sizer)
        nb.AddPage(ap, "Advanced")

        # ----------------------------------------------------------------
        # Tab 4 - Shortcuts (Feature 13)
        # ----------------------------------------------------------------
        sp = wx.Panel(nb)
        sp_sizer = wx.BoxSizer(wx.VERTICAL)
        _sc_hint = wx.StaticText(
            sp, label="Select a command and click Change Key to rebind it.")
        _sc_hint.SetForegroundColour(
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
        sp_sizer.Add(_sc_hint, 0, wx.ALL, 10)
        self._shortcut_list = wx.ListCtrl(
            sp, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN)
        self._shortcut_list.SetName(
            "Keyboard shortcuts list - select a command to change its key")
        self._shortcut_list.InsertColumn(0, "Command", width=270)
        self._shortcut_list.InsertColumn(1, "Shortcut", width=140)
        sp_sizer.Add(self._shortcut_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        _sc_btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self._sc_change_btn = wx.Button(sp, label="Change &Key...")
        self._sc_change_btn.SetName("Change key for selected command")
        self._sc_change_btn.Bind(wx.EVT_BUTTON, self._on_sc_change)
        _sc_btn_row.Add(self._sc_change_btn, 0, wx.ALL, 6)
        self._sc_reset_btn = wx.Button(sp, label="Reset to &Default")
        self._sc_reset_btn.SetName("Reset shortcut to default for selected command")
        self._sc_reset_btn.Bind(wx.EVT_BUTTON, self._on_sc_reset)
        _sc_btn_row.Add(self._sc_reset_btn, 0, wx.ALL, 6)
        sp_sizer.Add(_sc_btn_row, 0)
        sp.SetSizer(sp_sizer)
        nb.AddPage(sp, "Shortcuts")
        # Known shortcuts list: (display_name, default_key)
        self._KNOWN_SHORTCUTS = [
            ("Open Folder…",         "Ctrl+Shift+O"),
            ("Open Existing Master…", "Ctrl+O"),
            ("Build Master MP3",     "Ctrl+B"),
            ("Save Changes",         "Ctrl+S"),
            ("Save As…",             "Ctrl+Shift+A"),
            ("Load a Saved Setup…",  "Ctrl+L"),
            ("Save This Setup as a Template…", "Ctrl+Shift+G"),
            ("Settings…",            "Ctrl+,"),
            ("Command Palette",      "Ctrl+Shift+P"),
            ("Help on This Control", "F1"),
            ("User Guide",           "Ctrl+F1"),
            ("Keyboard Shortcuts",   "Ctrl+/"),
            ("Larger Text",          "Ctrl+="),
            ("Smaller Text",         "Ctrl+-"),
            ("Reset Text Size",      "Ctrl+0"),
            ("Go to Chapters (Step 1)",       "Ctrl+1"),
            ("Go to Tags and Build (Step 2)", "Ctrl+2"),
            ("Set Up Automatic Building…",    "Ctrl+W"),
        ]
        self._key_overrides = dict(settings.get("key_overrides", {}))
        for _sn, _sk in self._KNOWN_SHORTCUTS:
            _idx = self._shortcut_list.InsertItem(
                self._shortcut_list.GetItemCount(), _sn)
            self._shortcut_list.SetItem(
                _idx, 1, self._key_overrides.get(_sn, _sk))

        outer.Add(nb, 1, wx.EXPAND | wx.ALL, 8)
        outer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL),
                  0, wx.EXPAND | wx.ALL, 12)
        self.SetSizerAndFit(outer)
        self.SetMinSize((480, -1))
        self.CentreOnParent()
        self.skip.SetFocus()

    def _on_load_preset(self, _evt):
        """Load the selected preset and apply its values to the dialog controls."""
        sel = self._preset_choice.GetSelection()
        if sel <= 0:
            return
        name = self._preset_names[sel]
        if name in BUILT_IN_PRESETS:
            values = BUILT_IN_PRESETS[name]
        else:
            values = self.settings.get("presets", {}).get(name, {})
        if not values:
            return
        fmt = values.get("output_format", "mp3")
        self.fmt.SetSelection(
            1 if fmt == "m4b" else
            2 if fmt == "flac" else
            3 if fmt == "opus" else 0)
        br = str(values.get("bitrate", "192k"))
        self.bitrate.SetStringSelection(br)
        self.normalize.SetValue(bool(values.get("normalize", False)))
        self.gap.SetValue(float(values.get("gap_seconds", 0.0)))
        self.write_pod2.SetValue(bool(values.get("write_pod2", False)))
        self.per_file_norm.SetValue(bool(values.get("per_file_normalize", False)))
        self.lufs_target.SetValue(float(values.get("normalize_lufs", -16.0)))

    def _on_save_preset(self, _evt):
        """Save current control values as a named preset."""
        name = wx.GetTextFromUser(
            "Enter a name for this preset:", "Save Preset", "", self)
        name = name.strip()
        if not name:
            return
        if name.startswith("Built-in:"):
            wx.MessageBox("Preset names cannot start with 'Built-in:'.",
                          "Invalid name", wx.OK | wx.ICON_WARNING, self)
            return
        fmt = ("m4b" if self.fmt.GetSelection() == 1
               else "flac" if self.fmt.GetSelection() == 2
               else "opus" if self.fmt.GetSelection() == 3 else "mp3")
        preset = {
            "output_format": fmt,
            "bitrate": self.bitrate.GetStringSelection() or "192k",
            "normalize": self.normalize.GetValue(),
            "gap_seconds": float(self.gap.GetValue()),
            "write_pod2": self.write_pod2.GetValue(),
            "per_file_normalize": self.per_file_norm.GetValue(),
            "normalize_lufs": float(self.lufs_target.GetValue()),
        }
        if "presets" not in self.settings:
            self.settings["presets"] = {}
        self.settings["presets"][name] = preset
        settings_mod.save(self.settings)
        # Refresh choice list
        _built_in_names = sorted(BUILT_IN_PRESETS.keys())
        self._preset_names = (["-- Select a preset --"] + _built_in_names
                              + sorted(self.settings["presets"].keys()))
        self._preset_choice.Set(self._preset_names)
        try:
            idx = self._preset_names.index(name)
            self._preset_choice.SetSelection(idx)
        except ValueError:
            self._preset_choice.SetSelection(0)

    def _on_delete_preset(self, _evt):
        """Delete the currently selected custom preset."""
        sel = self._preset_choice.GetSelection()
        if sel <= 0:
            return
        name = self._preset_names[sel]
        if name in BUILT_IN_PRESETS:
            wx.MessageBox("Built-in presets cannot be deleted.",
                          "Cannot delete", wx.OK | wx.ICON_WARNING, self)
            return
        presets = self.settings.get("presets", {})
        presets.pop(name, None)
        self.settings["presets"] = presets
        settings_mod.save(self.settings)
        _built_in_names = sorted(BUILT_IN_PRESETS.keys())
        self._preset_names = (["-- Select a preset --"] + _built_in_names
                              + sorted(presets.keys()))
        self._preset_choice.Set(self._preset_names)
        self._preset_choice.SetSelection(0)

    def _get_current_presets(self) -> dict:
        """Return the current presets dict from settings."""
        return dict(self.settings.get("presets", {}))

    def _on_sc_change(self, _evt):
        """Open key-capture dialog for selected shortcut (Feature 13)."""
        sel = self._shortcut_list.GetFirstSelected()
        if sel < 0 or sel >= len(self._KNOWN_SHORTCUTS):
            return
        cmd_name, _default = self._KNOWN_SHORTCUTS[sel]
        dlg = _KeyCaptureDialog(self, cmd_name)
        if dlg.ShowModal() == wx.ID_OK and dlg.captured_key:
            self._key_overrides[cmd_name] = dlg.captured_key
            self._shortcut_list.SetItem(sel, 1, dlg.captured_key)
        dlg.Destroy()

    def _on_sc_reset(self, _evt):
        """Reset selected shortcut to its default (Feature 13)."""
        sel = self._shortcut_list.GetFirstSelected()
        if sel < 0 or sel >= len(self._KNOWN_SHORTCUTS):
            return
        cmd_name, default_key = self._KNOWN_SHORTCUTS[sel]
        self._key_overrides.pop(cmd_name, None)
        self._shortcut_list.SetItem(sel, 1, default_key)

    def result(self) -> dict:
        """Return the edited settings as a dict (call after ShowModal == OK)."""
        d = {
            "output_format": (
                "m4b" if self.fmt.GetSelection() == 1 else
                "flac" if self.fmt.GetSelection() == 2 else
                "opus" if self.fmt.GetSelection() == 3 else "mp3"),
            "title_source": (core.TITLE_SOURCE_EMBEDDED
                             if self.title_src.GetSelection() == 1
                             else core.TITLE_SOURCE_FILENAME),
            "bitrate": self.bitrate.GetStringSelection() or "192k",
            "normalize": self.normalize.GetValue(),
            "auto_cover": self.auto_cover.GetValue(),
            "write_pod2": self.write_pod2.GetValue(),
            "skip_seconds": int(self.skip.GetValue()),
            "default_volume": int(self.volume.GetValue()),
            "pause_at_chapter_end": self.pause_at_chapter_end.GetValue(),
            "announce_verbosity": ["quiet", "normal", "verbose"][
                self.verbosity.GetSelection()],
            "silence_noise_db": float(self.noise_db.GetValue()),
            "silence_min_seconds": float(self.min_silence.GetValue()),
            "gap_seconds": float(self.gap.GetValue()),
            "text_scale": int(self.text_scale.GetValue()),
            "theme": ["system", "light", "dark", "high_contrast"][
                self.theme_choice.GetSelection()],
            "high_contrast": self.theme_choice.GetSelection() == 3,
            "start_minimized": self.start_minimized.GetValue(),
            "check_updates_startup": self.check_updates_startup.GetValue(),
            "beta_features": self.beta_features.GetValue(),
            # Feature 8
            "per_file_normalize": self.per_file_norm.GetValue(),
            "normalize_lufs": float(self.lufs_target.GetValue()),
            # Fades
            "fade_ms": int(round(float(self.fade_dur.GetValue()) * 1000)),
            # Silence trimming
            "trim_silence": self.trim_silence.GetValue(),
            "trim_silence_db": float(self.trim_silence_db.GetValue()),
            # RSS
            "write_rss": self.write_rss.GetValue(),
            "rss_media_url": self.rss_media_url.GetValue().strip(),
            # ACX
            "acx_check_after_build": self.acx_check.GetValue(),
            # Feature 13
            "key_overrides": {row: override
                              for row, override in self._key_overrides.items()},
            # Feature 4
            "presets": self._get_current_presets(),
        }
        return d


class _KeyCaptureDialog(wx.Dialog):
    """Captures a single key combination for shortcut rebinding (Feature 13)."""

    def __init__(self, parent, cmd_name: str):
        super().__init__(parent, title="Press New Key",
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.captured_key: str = ""
        outer = wx.BoxSizer(wx.VERTICAL)
        msg = wx.StaticText(
            self,
            label=f"Press the key combination to use for:\n\"{cmd_name}\"\n\n"
                  "Press Escape to cancel.")
        msg.SetName("Key capture instruction")
        outer.Add(msg, 0, wx.ALL, 18)
        self._status = wx.StaticText(self, label="Waiting for key press...")
        self._status.SetName("Captured key status")
        outer.Add(self._status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 14)
        self.SetSizer(outer)
        self.SetMinSize((400, 150))
        self.CentreOnScreen()

    def _on_key(self, evt):
        key = evt.GetKeyCode()
        if key == wx.WXK_ESCAPE:
            self.captured_key = ""
            self.EndModal(wx.ID_CANCEL)
            return
        parts = []
        if evt.ControlDown():
            parts.append("Ctrl")
        if evt.AltDown():
            parts.append("Alt")
        if evt.ShiftDown():
            parts.append("Shift")
        _special = {
            wx.WXK_F1: "F1", wx.WXK_F2: "F2", wx.WXK_F3: "F3",
            wx.WXK_F4: "F4", wx.WXK_F5: "F5", wx.WXK_F6: "F6",
            wx.WXK_F7: "F7", wx.WXK_F8: "F8", wx.WXK_F9: "F9",
            wx.WXK_F10: "F10", wx.WXK_F11: "F11", wx.WXK_F12: "F12",
            wx.WXK_DELETE: "Del", wx.WXK_INSERT: "Ins",
            wx.WXK_HOME: "Home", wx.WXK_END: "End",
            wx.WXK_PAGEUP: "PgUp", wx.WXK_PAGEDOWN: "PgDn",
            wx.WXK_UP: "Up", wx.WXK_DOWN: "Down",
            wx.WXK_LEFT: "Left", wx.WXK_RIGHT: "Right",
            wx.WXK_SPACE: "Space", wx.WXK_TAB: "Tab",
            wx.WXK_RETURN: "Enter", wx.WXK_BACK: "Backspace",
        }
        if key in _special:
            parts.append(_special[key])
        elif 32 <= key <= 126:
            parts.append(chr(key).upper() if evt.ShiftDown() else chr(key))
        else:
            evt.Skip()
            return
        key_str = "+".join(parts)
        self.captured_key = key_str
        self._status.SetLabel(f"Captured: {key_str}")
        self.EndModal(wx.ID_OK)


class BatchTitleDialog(wx.Dialog):
    """Apply bulk transformations to all chapter titles at once."""

    def __init__(self, parent, titles: list):
        super().__init__(parent, title="Batch Edit Titles",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._titles = list(titles)
        outer = wx.BoxSizer(wx.VERTICAL)

        xform_box = wx.StaticBoxSizer(wx.VERTICAL, self, "Quick Transforms")
        self.chk_titlecase = wx.CheckBox(self, label="Apply &title case to all chapters")
        self.chk_titlecase.SetName("Apply title case to all chapter titles")
        self.chk_strip_num = wx.CheckBox(self, label="Strip leading &track numbers (01, 02 -)")
        self.chk_strip_num.SetName("Strip leading track numbers from chapter titles")
        self.chk_underscores = wx.CheckBox(self, label="Replace &underscores with spaces")
        self.chk_underscores.SetName("Replace underscores with spaces in chapter titles")
        self.chk_spaces = wx.CheckBox(self, label="Remove e&xtra spaces")
        self.chk_spaces.SetName("Remove duplicate and trailing spaces from chapter titles")
        for chk in (self.chk_titlecase, self.chk_strip_num,
                    self.chk_underscores, self.chk_spaces):
            xform_box.Add(chk, 0, wx.ALL, 4)
        outer.Add(xform_box, 0, wx.EXPAND | wx.ALL, 8)

        fr_box = wx.StaticBoxSizer(wx.VERTICAL, self, "Find and Replace")
        fr_grid = wx.FlexGridSizer(0, 2, 6, 8)
        fr_grid.AddGrowableCol(1, 1)
        fr_grid.Add(wx.StaticText(self, label="&Find:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.find_ctrl = wx.TextCtrl(self)
        self.find_ctrl.SetName("Find text in chapter titles")
        fr_grid.Add(self.find_ctrl, 1, wx.EXPAND)
        fr_grid.Add(wx.StaticText(self, label="&Replace with:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.replace_ctrl = wx.TextCtrl(self)
        self.replace_ctrl.SetName("Replacement text for chapter titles")
        fr_grid.Add(self.replace_ctrl, 1, wx.EXPAND)
        fr_box.Add(fr_grid, 0, wx.EXPAND | wx.ALL, 4)
        outer.Add(fr_box, 0, wx.EXPAND | wx.ALL, 8)

        pat_box = wx.StaticBoxSizer(wx.VERTICAL, self, "Number Pattern (replaces all titles)")
        self.chk_pattern = wx.CheckBox(self, label="Apply &number pattern:")
        self.chk_pattern.SetName("Apply a number pattern to replace all chapter titles")
        self.pattern_ctrl = wx.TextCtrl(self, value="Chapter {n}")
        self.pattern_ctrl.SetName(
            "Number pattern - use {n} for chapter number, {title} for current title")
        self.pattern_ctrl.Enable(False)
        hint = wx.StaticText(
            self, label="Use {n} for chapter number, {title} for current title")
        pat_box.Add(self.chk_pattern, 0, wx.ALL, 4)
        pat_box.Add(self.pattern_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
        pat_box.Add(hint, 0, wx.LEFT | wx.BOTTOM, 4)
        outer.Add(pat_box, 0, wx.EXPAND | wx.ALL, 8)

        prev_box = wx.StaticBoxSizer(wx.VERTICAL, self, "Preview (first 8 chapters)")
        self.preview_ctrl = wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.NO_BORDER, size=(-1, 120))
        self.preview_ctrl.SetName("Preview of title changes - before and after")
        self.preview_ctrl.SetBackgroundColour(self.GetBackgroundColour())
        prev_box.Add(self.preview_ctrl, 1, wx.EXPAND | wx.ALL, 4)
        outer.Add(prev_box, 0, wx.EXPAND | wx.ALL, 8)

        outer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizer(outer)
        self.SetMinSize((480, -1))
        self.SetSize((560, -1))
        self.Fit()
        self.CentreOnParent()

        for ctrl in (self.chk_titlecase, self.chk_strip_num,
                     self.chk_underscores, self.chk_spaces):
            ctrl.Bind(wx.EVT_CHECKBOX, self._refresh_preview)
        self.chk_pattern.Bind(wx.EVT_CHECKBOX, self._on_pattern_toggle)
        for ctrl in (self.find_ctrl, self.replace_ctrl, self.pattern_ctrl):
            ctrl.Bind(wx.EVT_TEXT, self._refresh_preview)
        self._refresh_preview(None)
        self.find_ctrl.SetFocus()

    def _on_pattern_toggle(self, _evt):
        self.pattern_ctrl.Enable(self.chk_pattern.GetValue())
        self._refresh_preview(None)

    def _transform(self, title: str, n: int) -> str:
        import re as _re
        t = title
        if self.chk_underscores.GetValue():
            t = t.replace("_", " ")
        if self.chk_spaces.GetValue():
            t = " ".join(t.split())
        if self.chk_strip_num.GetValue():
            t = _re.sub(r"^\s*\d{1,3}\s*(?:[-._)]+\s*|\s+(?=[A-Za-z]))", "", t).strip()
        if self.chk_titlecase.GetValue():
            t = t.title()
        find = self.find_ctrl.GetValue()
        if find:
            t = t.replace(find, self.replace_ctrl.GetValue())
        if self.chk_pattern.GetValue():
            pat = self.pattern_ctrl.GetValue()
            t = pat.replace("{n}", str(n)).replace("{title}", t)
        return t

    def _refresh_preview(self, _evt):
        lines = []
        for i, orig in enumerate(self._titles[:8], start=1):
            new = self._transform(orig, i)
            marker = " -> " if new != orig else "    "
            lines.append(f"{orig}{marker}{new}")
        self.preview_ctrl.SetValue("\n".join(lines))

    def result_titles(self) -> list:
        return [self._transform(t, i + 1) for i, t in enumerate(self._titles)]


class AcxResultDialog(wx.Dialog):
    """Show ACX compliance results with an optional Fix and Rebuild action."""

    def __init__(self, parent, acx_result):
        super().__init__(parent, title="ACX Compliance Check",
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.fix_and_rebuild = False
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        recs = acx_result.recommendations()
        body = acx_result.summary()
        if recs:
            body += "\n\nRecommendations:\n" + "\n".join(f"- {r}" for r in recs)

        txt = wx.StaticText(panel, label=body)
        txt.Wrap(500)
        sizer.Add(txt, 0, wx.ALL, 14)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        if not acx_result.passes:
            btn_fix = wx.Button(panel, label="&Fix and Rebuild")
            btn_fix.SetName(
                "Normalize loudness to ACX target (-23 LUFS) and rebuild master")
            btn_fix.Bind(wx.EVT_BUTTON, self._on_fix)
            btn_row.Add(btn_fix, 0, wx.RIGHT, 8)
        btn_close = wx.Button(panel, id=wx.ID_CLOSE, label="Close")
        btn_close.SetName("Close ACX compliance report")
        btn_close.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        btn_row.Add(btn_close, 0)
        sizer.Add(btn_row, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        panel.SetSizer(sizer)
        sizer.SetSizeHints(self)
        btn_close.SetFocus()

    def _on_fix(self, _evt):
        self.fix_and_rebuild = True
        self.EndModal(wx.ID_OK)


class MetadataLookupDialog(wx.Dialog):
    """Search MusicBrainz and Open Library to pre-fill tag fields."""

    def __init__(self, parent, title: str = "", artist: str = ""):
        super().__init__(parent, title="Look Up Metadata",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.selected_result = None
        outer = wx.BoxSizer(wx.VERTICAL)

        search_grid = wx.FlexGridSizer(0, 2, 8, 8)
        search_grid.AddGrowableCol(1, 1)

        def sfield(label, value, name):
            lbl = wx.StaticText(self, label=label)
            ctrl = wx.TextCtrl(self, value=value or "")
            ctrl.SetName(name)
            search_grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            search_grid.Add(ctrl, 1, wx.EXPAND)
            return ctrl

        self._title_ctrl = sfield("&Title:", title, "Search title")
        self._artist_ctrl = sfield("&Author / Artist:", artist,
                                   "Search author or artist name")

        self._books_chk = wx.CheckBox(self, label="Prefer &book results (Open Library)")
        self._books_chk.SetName("Prefer book results from Open Library over music results")
        self._books_chk.SetValue(True)
        search_grid.Add((0, 0))
        search_grid.Add(self._books_chk, 0, wx.ALIGN_CENTER_VERTICAL)

        outer.Add(search_grid, 0, wx.EXPAND | wx.ALL, 12)

        btn_search = wx.Button(self, label="&Search")
        btn_search.SetName("Search for metadata")
        btn_search.Bind(wx.EVT_BUTTON, self._on_search)
        btn_search.SetDefault()
        outer.Add(btn_search, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self._results_list = wx.ListCtrl(
            self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN,
            size=(-1, 180))
        self._results_list.SetName("Search results - select a result and click Apply")
        self._results_list.InsertColumn(0, "Title", width=200)
        self._results_list.InsertColumn(1, "Author / Artist", width=140)
        self._results_list.InsertColumn(2, "Year", width=55)
        self._results_list.InsertColumn(3, "Source", width=100)
        outer.Add(self._results_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        self._status_lbl = wx.StaticText(self, label="Enter a title and click Search.")
        self._status_lbl.SetName("Lookup status")
        outer.Add(self._status_lbl, 0, wx.ALL, 8)

        btn_row = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        outer.Add(btn_row, 0, wx.EXPAND | wx.ALL, 12)
        self._ok_btn = self.FindWindowById(wx.ID_OK)
        if self._ok_btn:
            self._ok_btn.SetLabel("&Apply")
            self._ok_btn.SetName("Apply selected metadata to tag fields")
        self._results = []
        self._results_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_activate)
        self._results_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_select)

        self.SetSizerAndFit(outer)
        self.SetSize((540, 440))
        self.CentreOnParent()
        self._title_ctrl.SetFocus()

    def _on_search(self, _evt):
        title = self._title_ctrl.GetValue().strip()
        artist = self._artist_ctrl.GetValue().strip()
        if not title:
            self._status_lbl.SetLabel("Enter a title to search.")
            return
        # The lookup makes network calls that can take many seconds. Run it on
        # a background thread so the UI (and screen reader) never freezes.
        self._status_lbl.SetLabel("Searching online, please wait...")
        self._results_list.DeleteAllItems()
        self._results = []
        prefer_books = self._books_chk.GetValue()

        def work():
            try:
                from . import lookup as lookup_mod
                results = lookup_mod.search(title, artist,
                                            prefer_books=prefer_books)
                wx.CallAfter(self._search_done, results, None)
            except Exception as exc:
                wx.CallAfter(self._search_done, None, str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _search_done(self, results, error):
        if error is not None:
            self._status_lbl.SetLabel(f"Search failed: {error}")
            return
        self._results = results or []
        if not self._results:
            self._status_lbl.SetLabel("No results found.")
            return
        for r in self._results:
            idx = self._results_list.InsertItem(
                self._results_list.GetItemCount(), r.title)
            self._results_list.SetItem(idx, 1, r.artist)
            self._results_list.SetItem(idx, 2, r.year)
            self._results_list.SetItem(idx, 3, r.source)
        self._status_lbl.SetLabel(
            f"Found {len(self._results)} result(s). Select one and click Apply.")
        self.selected_result = self._results[0]
        self._results_list.Select(0)
        self._results_list.Focus(0)
        self._results_list.SetFocus()

    def _on_select(self, evt):
        idx = evt.GetIndex()
        if 0 <= idx < len(self._results):
            self.selected_result = self._results[idx]

    def _on_activate(self, _evt):
        self.EndModal(wx.ID_OK)


class BuildLogDialog(wx.Dialog):
    """Show the rolling build log."""

    def __init__(self, parent, log_path: str):
        super().__init__(parent, title="Build Log",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        outer = wx.BoxSizer(wx.VERTICAL)
        try:
            with open(log_path, encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError:
            content = "(Could not read log file.)"

        self._text = wx.TextCtrl(
            self, value=content,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL | wx.TE_RICH2,
            size=(600, 360))
        self._text.SetName("Build log contents")
        self._text.SetFont(wx.Font(wx.FontInfo(9).FaceName("Courier New")))
        outer.Add(self._text, 1, wx.EXPAND | wx.ALL, 8)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        clear_btn = wx.Button(self, label="&Clear Log")
        clear_btn.SetName("Clear the build log file")
        clear_btn.Bind(wx.EVT_BUTTON, lambda e: self._clear(log_path))
        btn_row.Add(clear_btn, 0, wx.RIGHT, 8)
        btn_row.Add(self.CreateButtonSizer(wx.OK), 0)
        outer.Add(btn_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        self.SetSizerAndFit(outer)
        self.SetSize((640, 420))
        self.CentreOnParent()
        self._text.SetFocus()
        self._text.SetInsertionPointEnd()

    def _clear(self, log_path: str):
        try:
            with open(log_path, "w", encoding="utf-8") as fh:
                fh.write("")
            self._text.SetValue("")
        except OSError:
            pass


class ChapterEditDialog(wx.Dialog):
    """Edit a single chapter's title, and optional link URL and image - the
    rich per-chapter metadata carried into the chapters JSON sidecar."""

    def __init__(self, parent, number: int, title: str, url: str, img: str,
                 start_ms: Optional[int] = None):
        super().__init__(parent, title=f"Edit Chapter {number}",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        outer = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(0, 2, 8, 10)
        grid.AddGrowableCol(1, 1)

        def field(label_text, value, name):
            lbl = wx.StaticText(self, label=label_text)
            ctrl = wx.TextCtrl(self, value=value or "")
            ctrl.SetName(name)
            grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(ctrl, 1, wx.EXPAND)
            return ctrl

        self.title_ctrl = field("Chapter &title:", title, "Chapter title")
        self.start_ctrl = None
        if start_ms is not None:
            self.start_ctrl = field(
                "&Start time (H:MM:SS):", core.format_timestamp(start_ms),
                "Chapter start time")
            if number == 1:
                self.start_ctrl.Enable(False)
                self.start_ctrl.SetToolTip(
                    "The first chapter always starts at the beginning.")
        self.url_ctrl = field("Link &URL (optional):", url, "Chapter link URL")

        lbl = wx.StaticText(self, label="&Image (optional):")
        img_row = wx.BoxSizer(wx.HORIZONTAL)
        self.img_ctrl = wx.TextCtrl(self, value=img or "")
        self.img_ctrl.SetName("Chapter image path")
        img_row.Add(self.img_ctrl, 1, wx.ALIGN_CENTER_VERTICAL)
        browse = wx.Button(self, label="&Browse…")
        browse.SetName("Browse for chapter image")
        browse.Bind(wx.EVT_BUTTON, self._on_browse)
        img_row.Add(browse, 0, wx.LEFT, 6)
        grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(img_row, 1, wx.EXPAND)

        outer.Add(grid, 1, wx.EXPAND | wx.ALL, 14)

        # Image preview
        self._placeholder_bmp = wx.Bitmap(80, 80)
        self._img_preview = wx.StaticBitmap(self, bitmap=self._placeholder_bmp)
        self._img_preview.SetName("Chapter image preview")
        outer.Add(self._img_preview, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM, 8)
        self.img_ctrl.Bind(wx.EVT_TEXT, self._on_img_text)
        if img:
            wx.CallAfter(self._update_img_preview, img)

        outer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL),
                  0, wx.EXPAND | wx.ALL, 12)
        self.SetSizerAndFit(outer)
        self.SetSize((520, self.GetSize().height))
        self.title_ctrl.SetFocus()
        self.title_ctrl.SelectAll()
        self.CentreOnParent()

    def _on_img_text(self, _evt):
        self._update_img_preview(self.img_ctrl.GetValue().strip())

    def _update_img_preview(self, path: str):
        bmp = self._placeholder_bmp
        if path and os.path.isfile(path):
            img = wx.Image()
            if img.LoadFile(path):
                w, h = img.GetWidth(), img.GetHeight()
                scale = min(80 / w, 80 / h) if w and h else 1
                img = img.Scale(max(1, int(w * scale)), max(1, int(h * scale)),
                                wx.IMAGE_QUALITY_HIGH)
                bmp = img.ConvertToBitmap()
        self._img_preview.SetBitmap(bmp)
        self.Layout()

    def _on_browse(self, _evt):
        dlg = wx.FileDialog(
            self, "Choose chapter image",
            wildcard="Images (*.jpg;*.jpeg;*.png)|*.jpg;*.jpeg;*.png",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            self.img_ctrl.SetValue(dlg.GetPath())
        dlg.Destroy()

    def result(self):
        return (self.title_ctrl.GetValue().strip(),
                self.url_ctrl.GetValue().strip(),
                self.img_ctrl.GetValue().strip())

    def start_text(self) -> Optional[str]:
        if self.start_ctrl is None or not self.start_ctrl.IsEnabled():
            return None
        return self.start_ctrl.GetValue().strip()


class GoToTimeDialog(wx.Dialog):
    """Enter a timestamp to jump the player to."""

    def __init__(self, parent, length_ms: int):
        super().__init__(parent, title="Go to Time",
                         style=wx.DEFAULT_DIALOG_STYLE)
        self._length_ms = length_ms
        outer = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(
            self,
            label=f"Enter a time to jump to (audio is {core.format_timestamp(length_ms)} long).\n"
                  "Formats accepted: HH:MM:SS, MM:SS, or seconds (e.g. 90.5)")
        outer.Add(lbl, 0, wx.ALL, 12)

        self.time_ctrl = wx.TextCtrl(self, value="0:00")
        self.time_ctrl.SetName("Time to jump to - enter as HH:MM:SS, MM:SS, or seconds")
        outer.Add(self.time_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        outer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.EXPAND | wx.ALL, 12)
        self.SetSizer(outer)
        self.Fit()
        self.CentreOnParent()
        self.time_ctrl.SetFocus()
        self.time_ctrl.SelectAll()

    def time_ms(self) -> int:
        """Parse the entered time string and return milliseconds, or -1 on error."""
        raw = self.time_ctrl.GetValue().strip()
        ms = core._ts_to_ms(raw)
        if ms is not None:
            return ms
        # Try plain seconds
        try:
            return int(float(raw) * 1000)
        except ValueError:
            return -1


class RenameSourceFilesDialog(wx.Dialog):
    """Rename source MP3 files using a pattern."""

    def __init__(self, parent, items):
        super().__init__(parent, title="Rename Source Files",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._items = items
        outer = wx.BoxSizer(wx.VERTICAL)

        help_lbl = wx.StaticText(self,
            label="Placeholders: {n} = chapter number, {n:02d} = zero-padded,\n"
                  "{title} = chapter title, {ext} = original extension.")
        outer.Add(help_lbl, 0, wx.ALL, 10)

        pat_row = wx.BoxSizer(wx.HORIZONTAL)
        pat_row.Add(wx.StaticText(self, label="&Pattern:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.pattern = wx.TextCtrl(self, value="{n:02d} - {title}")
        self.pattern.SetName("File naming pattern - use {n} for number, {title} for chapter title")
        self.pattern.Bind(wx.EVT_TEXT, self._refresh)
        pat_row.Add(self.pattern, 1)
        outer.Add(pat_row, 0, wx.EXPAND | wx.ALL, 8)

        # Preview list
        self.preview = wx.ListCtrl(self, style=wx.LC_REPORT | wx.BORDER_SUNKEN, size=(-1, 200))
        self.preview.SetName("Preview of file renames - current name and new name")
        self.preview.InsertColumn(0, "Current filename", width=260)
        self.preview.InsertColumn(1, "New filename", width=260)
        outer.Add(self.preview, 1, wx.EXPAND | wx.ALL, 8)

        outer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizer(outer)
        self.SetMinSize((560, 400))
        self.Fit()
        self.CentreOnParent()
        self._refresh(None)
        self.pattern.SetFocus()

    def _make_name(self, item, n: int) -> str:
        import re as _re
        ext = os.path.splitext(item.path)[1]
        pat = self.pattern.GetValue()
        try:
            name = pat.format(n=n, title=item.title, ext=ext)
        except (KeyError, ValueError):
            name = pat
        # Sanitise
        name = _re.sub(r'[\\/:*?"<>|]', "_", name)
        if not name.endswith(ext):
            name += ext
        return name

    def _refresh(self, _evt):
        self.preview.DeleteAllItems()
        for i, it in enumerate(self._items, start=1):
            new_name = self._make_name(it, i)
            row = self.preview.InsertItem(i - 1, os.path.basename(it.path))
            self.preview.SetItem(row, 1, new_name)

    def planned_renames(self):
        """Return list of (old_path, new_path) tuples."""
        pairs = []
        for i, it in enumerate(self._items, start=1):
            new_name = self._make_name(it, i)
            new_path = os.path.join(os.path.dirname(it.path), new_name)
            pairs.append((it.path, new_path))
        return pairs


class CommandPaletteDialog:
    """Searchable command palette (Ctrl+Shift+P), modelled on Quill's palette.

    All currently registered commands are listed and filtered by substring as
    the user types.  Commands that are unavailable given the current app state
    are shown dimmed so the user can still discover them.  Down/Up arrows
    navigate the results list; Enter runs the selected command; Escape closes.
    """

    def __init__(self, frame: "MainFrame") -> None:
        self._frame = frame
        self._commands = self._build_commands()
        self._visible: list = []

        dlg = wx.Dialog(frame, title="Command Palette",
                        style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        dlg.SetName("Command Palette - type to search, Enter to run, Escape to close")
        outer = wx.BoxSizer(wx.VERTICAL)

        self.search = wx.SearchCtrl(dlg, style=wx.TE_PROCESS_ENTER)
        self.search.SetName("Search commands")
        self.search.SetDescriptiveText("Type a command name…")
        self.search.ShowSearchButton(True)
        self.search.ShowCancelButton(True)
        outer.Add(self.search, 0, wx.EXPAND | wx.ALL, 8)

        self.results = wx.ListBox(dlg, style=wx.LB_SINGLE)
        self.results.SetName("Command results - use arrows to navigate, Enter to run")
        outer.Add(self.results, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        self.status = wx.StaticText(dlg, label="")
        self.status.SetName("Command palette status")
        outer.Add(self.status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 8)
        outer.AddSpacer(8)

        dlg.SetSizer(outer)
        dlg.SetSize((580, 440))
        dlg.CentreOnParent()
        self.dialog = dlg

        self.search.Bind(wx.EVT_TEXT, self._on_text)
        self.search.Bind(wx.EVT_TEXT_ENTER, self._on_accept)
        self.search.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, lambda e: self.search.Clear())
        self.results.Bind(wx.EVT_LISTBOX_DCLICK, self._on_accept)
        dlg.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

        self._refresh("")
        self.search.SetFocus()

    # ------------------------------------------------------------------
    # Command registry
    # ------------------------------------------------------------------
    def _build_commands(self):
        f = self._frame
        nb = lambda: not f._is_building()
        edit = lambda: f.mode == "edit"
        no_edit = lambda: not edit()
        has_items = lambda: bool(f.items)
        has_out = lambda: bool(f.output_path)
        sel = lambda: f.list.GetFirstSelected()
        n = lambda: f._row_count()

        return [
            ("Open Folder…",                 "Ctrl+Shift+O",   lambda: f._on_open(None),               lambda: nb()),
            ("Open Existing Master…",         "Ctrl+O",         lambda: f._on_open_master(None),         lambda: nb()),
            ("Save Master As…",               None,             lambda: f._on_set_output(None),          lambda: nb() and no_edit()),
            ("Build Master MP3",              "Ctrl+B",         lambda: f._on_build(None),               lambda: nb() and no_edit() and has_items() and has_out()),
            ("Save Changes",                  "Ctrl+S",         lambda: f._on_save_edit(None),           lambda: edit() and nb() and f._edit_is_mp3()),
            ("Save As…",                      "Ctrl+Shift+A",   lambda: f._on_save_as(None),             lambda: nb() and n() > 0),
            ("Save as Individual Chapter Files…", None,          lambda: f._on_save_split_files(None),    lambda: nb() and edit() and n() > 1),
            ("Cancel Build",                  "Esc",            lambda: f._on_cancel(None),              lambda: f._is_building()),
            ("Load a Saved Setup…",           "Ctrl+L",         lambda: f._on_load_job(None),            lambda: nb()),
            ("Save This Setup as a Template…", "Ctrl+Shift+G",   lambda: f._on_generate_job(None),        lambda: nb() and no_edit() and has_items()),
            ("Load Chapter List From File…",  None,             lambda: f._on_import_chapters(None),     lambda: nb() and n() > 0),
            ("Save Chapter List…",            None,             lambda: f._on_export_chapters(None),     lambda: nb() and n() > 0),
            ("Find Chapters in Silent Gaps…", None,             lambda: f._on_silence(None),             lambda: nb()),
            ("Build Multiple Books…",        None,             lambda: f._on_batch(None),               lambda: nb()),
            ("Set Up Automatic Building…",    "Ctrl+W",         lambda: f._on_watch_folders(None),       lambda: True),
            ("Auto-Build in Background",      None,             lambda: f._on_start_watcher(None),       lambda: True),
            ("Settings…",                     "Ctrl+,",         lambda: f._on_settings(None),            lambda: True),
            ("Edit Chapter Details…",          "F2",             lambda: f._on_edit_chapter(None),        lambda: nb() and sel() >= 0),
            ("Batch Edit Titles…",             None,             lambda: f._on_batch_edit_titles(None),   lambda: nb() and n() > 0),
            ("Rename Source Files…",           None,             lambda: f._on_rename_source_files(None), lambda: nb() and no_edit() and n() > 0),
            ("Play This Chapter",             None,             lambda: f._on_play_selected(None),       lambda: nb() and sel() >= 0),
            ("Split Here",                    None,             lambda: f._on_split_chapter(None),       lambda: nb() and edit() and f.player.has_media()),
            ("Move Up",                       "Alt+Up",         lambda: f._move(-1),                     lambda: nb() and sel() > 0),
            ("Move Down",                     "Alt+Down",       lambda: f._move(1),                      lambda: nb() and 0 <= sel() < n() - 1),
            ("Remove / Merge Up",             "Delete",         lambda: f._remove_selected(),             lambda: nb() and sel() >= 0 and (no_edit() or n() > 1)),
            ("Go to Chapters (Step 1)",       "Ctrl+1",         lambda: f._on_back_page(None),           lambda: f._page_tags.IsShown()),
            ("Go to Tags and Build (Step 2)", "Ctrl+2",         lambda: f._on_next_page(None),           lambda: nb() and not f._page_tags.IsShown() and has_items()),
            ("Go to Time…",                   "Ctrl+G",         lambda: f._on_goto_time(None),           lambda: f.player.has_media()),
            ("Minimize to System Tray",       None,             lambda: f._on_minimize_to_tray(None),    lambda: True),
            ("Command Palette",               "Ctrl+Shift+P",   lambda: f._open_command_palette(),       lambda: True),
            ("Setup Wizard…",                 None,             lambda: f._on_wizard(None),              lambda: True),
            ("Help on This Control",          "F1",             lambda: f._on_context_help(None),        lambda: True),
            ("User Guide",                    "Ctrl+F1",        lambda: f._on_guide(None),               lambda: True),
            ("Keyboard Shortcuts",            "Ctrl+/",         lambda: f._on_keys(None),                lambda: True),
            ("Get Help Information…",         None,             lambda: f._on_save_diagnostics(None),    lambda: True),
            ("Look for Updates…",             None,             lambda: f._on_check_updates(None),       lambda: True),
            ("About ChapterForge",            None,             lambda: f._on_about(None),               lambda: True),
        ]

    # ------------------------------------------------------------------
    # Search and display
    # ------------------------------------------------------------------
    def _score(self, title: str, query: str) -> int:
        tl = title.lower()
        if tl == query:
            return 100
        if tl.startswith(query):
            return 80
        if query in tl:
            return 60
        # Subsequence match
        idx = 0
        for ch in query:
            idx = tl.find(ch, idx)
            if idx == -1:
                return 0
            idx += 1
        return 20

    def _filtered(self, query: str):
        q = query.strip().lower()
        if not q:
            return list(self._commands)
        scored = [(self._score(title, q), title, key, handler, en)
                  for title, key, handler, en in self._commands
                  if self._score(title, q) > 0]
        scored.sort(key=lambda r: -r[0])
        return [(t, k, h, e) for _s, t, k, h, e in scored]

    def _refresh(self, query: str) -> None:
        self._visible = self._filtered(query)
        self.results.Clear()
        for title, key, handler, enabled_fn in self._visible:
            available = enabled_fn()
            label = f"{title}  [{key}]" if key else title
            if not available:
                label = f"- {label}"  # em-dash prefix for unavailable
            self.results.Append(label)
        n = len(self._visible)
        if n:
            self.results.SetSelection(0)
            first_title = self._visible[0][0]
            self.status.SetLabel(
                f"{n} command(s). Top match: {first_title}. "
                "Down/Up to navigate, Enter to run.")
        else:
            self.status.SetLabel("No matching commands.")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _on_text(self, _evt) -> None:
        self._refresh(self.search.GetValue())

    def _on_char_hook(self, evt) -> None:
        key = evt.GetKeyCode()
        if key == wx.WXK_ESCAPE:
            self.dialog.EndModal(wx.ID_CANCEL)
            return
        n = self.results.GetCount()
        if key in (wx.WXK_DOWN, wx.WXK_UP) and n:
            cur = self.results.GetSelection()
            if key == wx.WXK_DOWN:
                nxt = min(cur + 1, n - 1) if cur >= 0 else 0
            else:
                nxt = max(cur - 1, 0) if cur >= 0 else n - 1
            self.results.SetSelection(nxt)
            self.results.SetFocus()
            if 0 <= nxt < len(self._visible):
                a11y.announce(self._visible[nxt][0])
            return
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._on_accept(None)
            return
        evt.Skip()

    def _on_accept(self, _evt) -> None:
        sel = self.results.GetSelection()
        if sel < 0 or sel >= len(self._visible):
            return
        title, key, handler, enabled_fn = self._visible[sel]
        if not enabled_fn():
            a11y.announce(f"{title} is not available right now.")
            return
        self.dialog.EndModal(wx.ID_OK)
        wx.CallAfter(handler)

    def show(self) -> None:
        self.dialog.ShowModal()
        self.dialog.Destroy()


class FFmpegSetupDialog(wx.Dialog):
    """Progress dialog shown while FFmpeg is downloading."""

    def __init__(self, parent=None):
        super().__init__(parent, title="Downloading FFmpeg",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.success = False

        outer = wx.BoxSizer(wx.VERTICAL)

        # Title
        title = wx.StaticText(self, label="Downloading FFmpeg...")
        f = title.GetFont()
        f.MakeItalic()
        title.SetFont(f)
        outer.Add(title, 0, wx.ALL, 12)

        # Status text
        self.status = wx.StaticText(self, label="Initializing download...")
        self.status.SetName("Setup status")
        outer.Add(self.status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        # Gauge (indeterminate while downloading)
        self.gauge = wx.Gauge(self, range=100, style=wx.GA_HORIZONTAL)
        self.gauge.Pulse()
        self.gauge.SetName("Setup progress")
        outer.Add(self.gauge, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        # OK button (hidden until done)
        btn_sizer = self.CreateButtonSizer(wx.OK)
        self.ok_btn = self.FindWindow(wx.ID_OK)
        self.ok_btn.Hide()
        outer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 12)

        self.SetSizerAndFit(outer)
        self.SetMinSize((400, 150))
        self.CentreOnScreen()

    def update_status(self, message: str):
        """Update status text and pulse gauge."""
        wx.CallAfter(self._do_update, message)

    def _do_update(self, message: str):
        """Run on main thread."""
        self.status.SetLabel(message)
        self.gauge.Pulse()
        self.Layout()

    def download_complete(self, success: bool, message: str):
        """Call when download is done."""
        wx.CallAfter(self._show_completion, success, message)

    def _show_completion(self, success: bool, message: str):
        """Run on main thread."""
        self.success = success
        self.status.SetLabel(message)
        self.gauge.SetValue(100)
        self.ok_btn.Show()
        self.Layout()


class ChapterForgeApp(wx.App):
    def OnInit(self):
        try:
            core._find_tool("ffmpeg")
            core._find_tool("ffprobe")
            ffmpeg_ready = True
        except core.FFmpegNotFoundError:
            ffmpeg_ready = False

        if not ffmpeg_ready:
            result = wx.MessageBox(
                "FFmpeg was not found on this system. FFmpeg is required to build "
                "audiobooks.\n\n"
                "Would you like ChapterForge to download and install FFmpeg now? "
                "The download is free and takes about 1-2 minutes.",
                "FFmpeg Not Found",
                wx.YES_NO | wx.ICON_QUESTION)

            if result == wx.YES:
                setup_dlg = FFmpegSetupDialog()
                self.SetTopWindow(setup_dlg)
                self.worker = threading.Thread(
                    target=self._download_ffmpeg,
                    args=(setup_dlg,),
                    daemon=True)
                self.worker.start()
                setup_dlg.ShowModal()
                setup_dlg.Destroy()

                if not setup_dlg.success:
                    wx.MessageBox(
                        "FFmpeg could not be downloaded automatically.\n\n"
                        "ChapterForge will open, but you will not be able to build "
                        "audiobooks until FFmpeg is installed.\n\n"
                        "To install FFmpeg manually: visit ffmpeg.org, download the "
                        "Windows build, and add the bin folder to your system PATH. "
                        "Then restart ChapterForge.",
                        "FFmpeg Download Failed",
                        wx.OK | wx.ICON_WARNING)
                # Continue to launch the main window regardless.
            else:
                wx.MessageBox(
                    "ChapterForge will open now. To build audiobooks you will need "
                    "FFmpeg installed on your system.\n\n"
                    "Visit ffmpeg.org to download FFmpeg for Windows, or use "
                    "Help > Download FFmpeg inside the app.",
                    "FFmpeg Required for Building",
                    wx.OK | wx.ICON_INFORMATION)
                # Continue to launch the main window regardless.

        frame = MainFrame()
        if frame.settings.get("start_minimized", False):
            frame._setup_startup_tray()
        else:
            frame.Show()
        self.SetTopWindow(frame)
        return True

    def _download_ffmpeg(self, dlg):
        """Background thread: download and extract FFmpeg."""
        try:
            dlg.update_status("Downloading FFmpeg from gyan.dev - please wait...")
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "get_ffmpeg",
                os.path.join(os.path.dirname(__file__), "..", "tools", "get_ffmpeg.py"))
            get_ffmpeg = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(get_ffmpeg)
            if get_ffmpeg.download_ffmpeg():
                dlg.download_complete(True, "FFmpeg downloaded successfully. Click OK to continue.")
            else:
                dlg.download_complete(False,
                    "Download failed. ChapterForge will open but build features "
                    "will not work until FFmpeg is installed.")
        except Exception as exc:
            dlg.download_complete(False, f"Download error: {exc}")


def main():
    app = ChapterForgeApp(False)
    app.MainLoop()


if __name__ == "__main__":
    main()
