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
from . import manifest as manifest_mod
from . import settings as settings_mod
from .notify import Notifier
from .player import PlayerPanel


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


class MainFrame(wx.Frame):
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
        self.canceller: Optional[core.Canceller] = None
        self.worker: Optional[threading.Thread] = None
        self._last_pct = -1
        self.notifier = Notifier(parent=self)
        self._tray = None
        self._watch_controller = None
        self._force_quit = False

        self._build_menu()
        self._build_ui()
        self.CreateStatusBar()
        self.SetStatusText("Open a folder of MP3 files to begin.")

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

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def _build_menu(self):
        menubar = wx.MenuBar()

        file_menu = wx.Menu()
        self.mi_open = file_menu.Append(wx.ID_OPEN, "&Open Folder…\tCtrl+O",
                                        "Choose a folder of MP3 files")
        self.mi_open_master = file_menu.Append(
            wx.ID_ANY, "Open &Existing Master…\tCtrl+E",
            "Open a chaptered MP3/M4B to fix its tags and chapter titles")
        self.recent_menu = wx.Menu()
        self.mi_recent = file_menu.AppendSubMenu(
            self.recent_menu, "Open &Recent",
            "Re-open a recently used folder, master or job file")
        self.mi_output = file_menu.Append(wx.ID_ANY, "Set Out&put File…\tCtrl+S",
                                          "Choose where the master MP3 is saved")
        file_menu.AppendSeparator()
        self.mi_build = file_menu.Append(wx.ID_ANY, "&Build Master MP3\tCtrl+B",
                                         "Build the master MP3 with chapters")
        self.mi_save_edit = file_menu.Append(
            wx.ID_ANY, "Sa&ve Changes\tCtrl+Shift+S",
            "Save edited tags and chapter titles back to the open master")
        self.mi_save_as = file_menu.Append(
            wx.ID_SAVEAS, "Save &As…\tCtrl+Alt+S",
            "Save the master (or edited master) to a new file")
        self.mi_cancel = file_menu.Append(wx.ID_ANY, "&Cancel Build\tEsc",
                                          "Cancel a build in progress")
        file_menu.AppendSeparator()
        self.mi_load_job = file_menu.Append(
            wx.ID_ANY, "&Load Job File…\tCtrl+L",
            "Load a .cfjob file that defines order, titles and tags")
        self.mi_gen_job = file_menu.Append(
            wx.ID_ANY, "&Generate Job File…\tCtrl+G",
            "Save the current chapters and tags as a reusable .cfjob file")
        file_menu.AppendSeparator()
        self.mi_import_ch = file_menu.Append(
            wx.ID_ANY, "&Import Chapters…",
            "Replace the chapter markers of the open master from a label file")
        self.mi_export_ch = file_menu.Append(
            wx.ID_ANY, "E&xport Chapters…",
            "Save the current chapter list as labels, a CUE sheet or JSON")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_EXIT, "E&xit\tAlt+F4", "Close ChapterForge")
        menubar.Append(file_menu, "&File")

        tools_menu = wx.Menu()
        self.mi_silence = tools_menu.Append(
            wx.ID_ANY, "Auto-chapter by &Silence…",
            "Detect chapters in an audio file from silent gaps")
        self.mi_batch = tools_menu.Append(
            wx.ID_ANY, "&Batch Build Folder…",
            "Build a master for every sub-folder of books at once")
        tools_menu.AppendSeparator()
        self.mi_watch = tools_menu.Append(
            wx.ID_ANY, "&Watch Folders…\tCtrl+W",
            "Manage reusable watch-folder processes")
        self.mi_start_watch = tools_menu.Append(
            wx.ID_ANY, "Start &Background Watcher",
            "Minimize to the system tray and watch folders automatically")
        from . import autostart
        self.mi_autostart = tools_menu.AppendCheckItem(
            wx.ID_ANY, "Start Watcher at Sign-&in",
            "Run the background watcher automatically when you sign in")
        self.mi_autostart.Enable(autostart.is_supported())
        if autostart.is_supported():
            self.mi_autostart.Check(autostart.is_enabled())
        tools_menu.AppendSeparator()
        self.mi_settings = tools_menu.Append(
            wx.ID_PREFERENCES, "&Settings…\tCtrl+,",
            "Edit ChapterForge preferences")
        menubar.Append(tools_menu, "&Tools")

        help_menu = wx.Menu()
        self.mi_guide = help_menu.Append(
            wx.ID_ANY, "&User Guide\tF1", "Open the User Guide in your browser")
        self.mi_keys = help_menu.Append(
            wx.ID_ANY, "&Keyboard Shortcuts\tCtrl+/",
            "List the keyboard shortcuts")
        self.mi_deploy = help_menu.Append(
            wx.ID_ANY, "&Deployment Guide",
            "Open the build, packaging and release guide")
        self.mi_changelog = help_menu.Append(
            wx.ID_ANY, "Release &Notes",
            "Open the changelog / release notes")
        self.mi_docs_home = help_menu.Append(
            wx.ID_ANY, "All D&ocumentation…",
            "Open the documentation home page")
        help_menu.AppendSeparator()
        self.mi_diagnostics = help_menu.Append(
            wx.ID_ANY, "Save &Diagnostics…",
            "Save a text report of versions and settings for support")
        self.mi_update = help_menu.Append(
            wx.ID_ANY, "Check for &Updates…",
            "Check online for a newer version of ChapterForge")
        self.mi_website = help_menu.Append(
            wx.ID_ANY, "Visit Project &Website",
            "Open the ChapterForge project page in your browser")
        help_menu.AppendSeparator()
        help_menu.Append(wx.ID_ABOUT, "&About ChapterForge")
        menubar.Append(help_menu, "&Help")

        self.SetMenuBar(menubar)

        self.Bind(wx.EVT_MENU, self._on_open, self.mi_open)
        self.Bind(wx.EVT_MENU, self._on_open_master, self.mi_open_master)
        self.Bind(wx.EVT_MENU, self._on_set_output, self.mi_output)
        self.Bind(wx.EVT_MENU, self._on_build, self.mi_build)
        self.Bind(wx.EVT_MENU, self._on_save_edit, self.mi_save_edit)
        self.Bind(wx.EVT_MENU, self._on_save_as, self.mi_save_as)
        self.Bind(wx.EVT_MENU, self._on_cancel, self.mi_cancel)
        self.Bind(wx.EVT_MENU, self._on_load_job, self.mi_load_job)
        self.Bind(wx.EVT_MENU, self._on_generate_job, self.mi_gen_job)
        self.Bind(wx.EVT_MENU, self._on_import_chapters, self.mi_import_ch)
        self.Bind(wx.EVT_MENU, self._on_export_chapters, self.mi_export_ch)
        self.Bind(wx.EVT_MENU, self._on_silence, self.mi_silence)
        self.Bind(wx.EVT_MENU, self._on_batch, self.mi_batch)
        self.Bind(wx.EVT_MENU, self._on_settings, self.mi_settings)
        self.Bind(wx.EVT_MENU, self._on_watch_folders, self.mi_watch)
        self.Bind(wx.EVT_MENU, self._on_start_watcher, self.mi_start_watch)
        self.Bind(wx.EVT_MENU, self._on_toggle_autostart, self.mi_autostart)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(), id=wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, self._on_guide, self.mi_guide)
        self.Bind(wx.EVT_MENU, self._on_keys, self.mi_keys)
        self.Bind(wx.EVT_MENU, self._on_deployment_doc, self.mi_deploy)
        self.Bind(wx.EVT_MENU, self._on_changelog_doc, self.mi_changelog)
        self.Bind(wx.EVT_MENU, self._on_docs_home, self.mi_docs_home)
        self.Bind(wx.EVT_MENU, self._on_save_diagnostics, self.mi_diagnostics)
        self.Bind(wx.EVT_MENU, self._on_check_updates, self.mi_update)
        self.Bind(wx.EVT_MENU, self._on_website, self.mi_website)
        self.Bind(wx.EVT_MENU, self._on_about, id=wx.ID_ABOUT)

    def _label(self, parent, text, name=None):
        lbl = wx.StaticText(parent, label=text)
        if name:
            lbl.SetName(name)
        return lbl

    def _build_ui(self):
        panel = wx.Panel(self)
        panel.SetName("ChapterForge")
        outer = wx.BoxSizer(wx.VERTICAL)

        # --- Source folder row -----------------------------------------
        src_box = wx.StaticBoxSizer(wx.HORIZONTAL, panel, "Source")
        src_box.Add(self._label(panel, "Folder of MP3 &files:"),
                    0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)
        self.folder_ctrl = wx.TextCtrl(panel, style=wx.TE_READONLY)
        self.folder_ctrl.SetName("Source folder")
        self.folder_ctrl.SetHint("No folder chosen yet")
        src_box.Add(self.folder_ctrl, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)
        self.btn_browse = wx.Button(panel, label="&Browse…")
        self.btn_browse.SetName("Browse for folder")
        self.btn_browse.Bind(wx.EVT_BUTTON, self._on_open)
        src_box.Add(self.btn_browse, 0, wx.ALL, 6)
        outer.Add(src_box, 0, wx.EXPAND | wx.ALL, 8)

        # --- Main split: chapters (left) and tags (right) --------------
        cols = wx.BoxSizer(wx.HORIZONTAL)

        # Chapters group
        ch_box = wx.StaticBoxSizer(wx.VERTICAL, panel, "Chapters")
        ch_box.Add(self._label(panel, "Chapter &list (one per source file):"),
                   0, wx.ALL, 4)
        self.list = wx.ListCtrl(
            panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN)
        self.list.SetName("Chapters list")
        self.list.InsertColumn(0, "#", width=44)
        self.list.InsertColumn(1, "Title", width=240)
        self.list.InsertColumn(2, "Start", width=80)
        self.list.InsertColumn(3, "Duration", width=80)
        self.list.InsertColumn(4, "Source file", width=200)
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_list_select)
        self.list.Bind(wx.EVT_LIST_ITEM_DESELECTED, self._on_list_select)
        self.list.Bind(wx.EVT_KEY_DOWN, self._on_list_key)
        ch_box.Add(self.list, 1, wx.EXPAND | wx.ALL, 4)

        # Chapter editing controls
        edit_row = wx.BoxSizer(wx.HORIZONTAL)
        edit_row.Add(self._label(panel, "Selected chapter &title:"),
                     0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)
        self.title_ctrl = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.title_ctrl.SetName("Selected chapter title")
        self.title_ctrl.Bind(wx.EVT_TEXT_ENTER, self._on_apply_title)
        self.title_ctrl.Bind(wx.EVT_KILL_FOCUS, self._on_apply_title)
        edit_row.Add(self.title_ctrl, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)
        ch_box.Add(edit_row, 0, wx.EXPAND)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_edit = wx.Button(panel, label="&Edit Title")
        self.btn_edit.SetName("Edit chapter title")
        self.btn_edit.Bind(wx.EVT_BUTTON, self._on_edit_chapter)
        self.btn_up = wx.Button(panel, label="Move &Up")
        self.btn_up.SetName("Move chapter up")
        self.btn_up.Bind(wx.EVT_BUTTON, lambda e: self._move(-1))
        self.btn_down = wx.Button(panel, label="Move &Down")
        self.btn_down.SetName("Move chapter down")
        self.btn_down.Bind(wx.EVT_BUTTON, lambda e: self._move(1))
        self.btn_remove = wx.Button(panel, label="Re&move")
        self.btn_remove.SetName("Remove chapter")
        self.btn_remove.Bind(wx.EVT_BUTTON, lambda e: self._remove_selected())
        self.btn_play_sel = wx.Button(panel, label="&Play Selected")
        self.btn_play_sel.SetName("Play selected chapter")
        self.btn_play_sel.Bind(wx.EVT_BUTTON, self._on_play_selected)
        self.btn_split = wx.Button(panel, label="S&plit at Playhead")
        self.btn_split.SetName("Split chapter at the player position")
        self.btn_split.Bind(wx.EVT_BUTTON, self._on_split_chapter)
        for b in (self.btn_edit, self.btn_up, self.btn_down, self.btn_remove,
                  self.btn_play_sel, self.btn_split):
            btn_row.Add(b, 0, wx.ALL, 4)
        ch_box.Add(btn_row, 0)
        cols.Add(ch_box, 1, wx.EXPAND | wx.ALL, 8)

        # Tags group
        tag_box = wx.StaticBoxSizer(wx.VERTICAL, panel, "Master MP3 tags")
        grid = wx.FlexGridSizer(0, 2, 6, 6)
        grid.AddGrowableCol(1, 1)

        def add_field(label, name, multiline=False):
            grid.Add(self._label(panel, label), 0, wx.ALIGN_CENTER_VERTICAL)
            style = wx.TE_MULTILINE if multiline else 0
            ctrl = wx.TextCtrl(panel, style=style,
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
        tag_box.Add(grid, 0, wx.EXPAND | wx.ALL, 4)

        cover_row = wx.BoxSizer(wx.HORIZONTAL)
        cover_row.Add(self._label(panel, "Co&ver image:"),
                      0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)
        self.cover_ctrl = wx.TextCtrl(panel, style=wx.TE_READONLY)
        self.cover_ctrl.SetName("Cover image path")
        self.cover_ctrl.SetHint("Optional JPEG or PNG")
        cover_row.Add(self.cover_ctrl, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)
        self.btn_cover = wx.Button(panel, label="Ch&oose…")
        self.btn_cover.SetName("Choose cover image")
        self.btn_cover.Bind(wx.EVT_BUTTON, self._on_choose_cover)
        cover_row.Add(self.btn_cover, 0, wx.ALL, 4)
        self.btn_cover_clear = wx.Button(panel, label="Cl&ear")
        self.btn_cover_clear.SetName("Clear cover image")
        self.btn_cover_clear.Bind(wx.EVT_BUTTON, self._on_clear_cover)
        cover_row.Add(self.btn_cover_clear, 0, wx.ALL, 4)
        tag_box.Add(cover_row, 0, wx.EXPAND)

        self._placeholder_bmp = wx.Bitmap(96, 96)
        self.cover_preview = wx.StaticBitmap(panel, bitmap=self._placeholder_bmp)
        self.cover_preview.SetName("Cover preview")
        tag_box.Add(self.cover_preview, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, 4)
        cols.Add(tag_box, 1, wx.EXPAND | wx.ALL, 8)

        outer.Add(cols, 1, wx.EXPAND)

        # --- Options row -----------------------------------------------
        opt_box = wx.StaticBoxSizer(wx.HORIZONTAL, panel, "Options")
        opt_box.Add(self._label(panel, "Chapter titles fro&m:"),
                    0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)
        self.title_source = wx.Choice(panel, choices=["Filename", "Embedded tag"])
        self.title_source.SetName("Chapter title source")
        self.title_source.SetSelection(0)
        self.title_source.Bind(wx.EVT_CHOICE, self._on_title_source)
        opt_box.Add(self.title_source, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)

        opt_box.Add(self._label(panel, "Re-encode &quality:"),
                    0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)
        self.bitrate_choice = wx.Choice(
            panel, choices=["128k", "160k", "192k", "256k", "320k"])
        self.bitrate_choice.SetName("Re-encode quality")
        self.bitrate_choice.SetStringSelection("192k")
        opt_box.Add(self.bitrate_choice, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)

        self.normalize_chk = wx.CheckBox(panel, label="&Normalize loudness")
        self.normalize_chk.SetName("Normalize loudness")
        opt_box.Add(self.normalize_chk, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)

        opt_box.Add(self._label(panel, "Output for&mat:"),
                    0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)
        self.format_choice = wx.Choice(panel, choices=["MP3", "M4B"])
        self.format_choice.SetName("Output format")
        self.format_choice.SetSelection(0)
        self.format_choice.Bind(wx.EVT_CHOICE, self._on_format_change)
        opt_box.Add(self.format_choice, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)

        self.pod2_chk = wx.CheckBox(panel, label="Write chapters &JSON")
        self.pod2_chk.SetName("Also write a Podcasting 2.0 chapters JSON sidecar")
        opt_box.Add(self.pod2_chk, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)

        opt_box.Add(self._label(panel, "&Gap between chapters (s):"),
                    0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)
        self.gap_ctrl = wx.SpinCtrlDouble(
            panel, min=0.0, max=30.0, inc=0.5,
            initial=float(self.settings.get("gap_seconds", 0.0)))
        self.gap_ctrl.SetDigits(1)
        self.gap_ctrl.SetName("Gap between chapters in seconds")
        self.gap_ctrl.Bind(wx.EVT_SPINCTRLDOUBLE, self._on_estimate_inputs)
        self.bitrate_choice.Bind(wx.EVT_CHOICE, self._on_estimate_inputs)
        opt_box.Add(self.gap_ctrl, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)
        outer.Add(opt_box, 0, wx.EXPAND | wx.ALL, 8)

        # --- Output + build row ----------------------------------------
        out_box = wx.StaticBoxSizer(wx.HORIZONTAL, panel, "Output")
        out_box.Add(self._label(panel, "Master &output file:"),
                    0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)
        self.output_ctrl = wx.TextCtrl(panel, style=wx.TE_READONLY)
        self.output_ctrl.SetName("Output file")
        self.output_ctrl.SetHint("Choose where to save the master MP3")
        out_box.Add(self.output_ctrl, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)
        self.btn_output = wx.Button(panel, label="&Set…")
        self.btn_output.SetName("Set output file")
        self.btn_output.Bind(wx.EVT_BUTTON, self._on_set_output)
        out_box.Add(self.btn_output, 0, wx.ALL, 6)
        outer.Add(out_box, 0, wx.EXPAND | wx.ALL, 8)

        self.estimate_text = wx.StaticText(panel, label="")
        self.estimate_text.SetName("Estimated output size")
        outer.Add(self.estimate_text, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)

        action_row = wx.BoxSizer(wx.HORIZONTAL)
        self.action_row_sizer = action_row
        self.btn_build = wx.Button(panel, label="Build Master MP&3")
        self.btn_build.SetName("Build master MP3")
        self.btn_build.Bind(wx.EVT_BUTTON, self._on_build)
        self.btn_build.SetDefault()
        self.btn_save_edit = wx.Button(panel, label="Sa&ve Changes")
        self.btn_save_edit.SetName("Save changes to the open master")
        self.btn_save_edit.Bind(wx.EVT_BUTTON, self._on_save_edit)
        self.btn_save_edit.Hide()
        self.btn_cancel = wx.Button(panel, label="Cancel")
        self.btn_cancel.SetName("Cancel build")
        self.btn_cancel.Bind(wx.EVT_BUTTON, self._on_cancel)
        action_row.Add(self.btn_build, 0, wx.ALL, 6)
        action_row.Add(self.btn_save_edit, 0, wx.ALL, 6)
        action_row.Add(self.btn_cancel, 0, wx.ALL, 6)
        self.gauge = wx.Gauge(panel, range=100, size=(220, -1))
        self.gauge.SetName("Build progress")
        action_row.Add(self.gauge, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 6)
        outer.Add(action_row, 0, wx.EXPAND | wx.ALL, 4)

        self.status_text = wx.StaticText(panel, label="Ready.")
        self.status_text.SetName("Status")
        outer.Add(self.status_text, 0, wx.EXPAND | wx.ALL, 8)

        # --- Accessible preview player ---------------------------------
        self.player = PlayerPanel(
            panel, announce=self._announce,
            get_skip_seconds=lambda: int(self.settings.get("skip_seconds", 10)),
            get_volume=lambda: int(self.settings.get("default_volume", 80)),
            on_volume_change=self._on_player_volume)
        outer.Add(self.player, 0, wx.EXPAND | wx.ALL, 8)

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

    def _row_count(self) -> int:
        return (len(self.edit_chapters) if self.mode == "edit"
                else len(self.items))

    def _update_command_state(self):
        building = self._is_building()
        edit = self.mode == "edit"
        has_items = bool(self.items)
        count = self._row_count()
        sel = self.list.GetFirstSelected() if count else -1
        for ctrl in (self.btn_browse, self.btn_output, self.btn_build,
                     self.btn_cover, self.btn_cover_clear, self.list,
                     self.title_ctrl, self.tag_title, self.tag_artist,
                     self.tag_album, self.tag_album_artist, self.tag_genre,
                     self.tag_year, self.tag_comment,
                     self.title_source, self.bitrate_choice, self.normalize_chk,
                     self.format_choice, self.pod2_chk, self.gap_ctrl):
            ctrl.Enable(not building)
        # Build-only widgets are meaningless while editing an existing master.
        for ctrl in (self.btn_browse, self.btn_output, self.btn_build,
                     self.title_source, self.bitrate_choice, self.normalize_chk,
                     self.format_choice, self.pod2_chk, self.gap_ctrl):
            ctrl.Enable(not building and not edit)
        self.btn_build.Enable(not building and not edit and has_items
                              and bool(self.output_path))
        self.btn_edit.Enable(not building and sel >= 0)
        # Reorder only makes sense when assembling from source files.
        self.btn_up.Enable(not building and not edit and sel > 0)
        self.btn_down.Enable(not building and not edit
                             and 0 <= sel < count - 1)
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
        self.action_row_sizer.Layout()
        self.mi_build.Enable(not building and not edit and has_items
                             and bool(self.output_path))
        self.mi_save_edit.Enable(can_save_edit)
        self.mi_save_as.Enable(not building and count > 0)
        self.mi_cancel.Enable(building)
        self.mi_open.Enable(not building)
        self.mi_open_master.Enable(not building)
        self.mi_output.Enable(not building and not edit)
        self.mi_load_job.Enable(not building)
        self.mi_gen_job.Enable(not building and not edit and has_items)
        self.mi_silence.Enable(not building)
        self.mi_batch.Enable(not building)
        self.mi_import_ch.Enable(not building and edit)
        self.mi_export_ch.Enable(not building and count > 0)

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
        self._announce("Scanning folder…")
        wx.BeginBusyCursor()
        try:
            items, skipped_masters = core.scan_folder_detailed(folder)
        except core.ChapterForgeError as exc:
            wx.EndBusyCursor()
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
        self._enter_build_mode()
        self.folder_ctrl.SetValue(folder)
        self.settings["last_input_dir"] = folder

        core.apply_title_source(good, self._current_title_source(),
                                respect_edits=False)

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
        self.title_ctrl.SetFocus()

    def _current_output_ext(self) -> str:
        return ".m4b" if self.format_choice.GetSelection() == 1 else ".mp3"

    def _on_set_output(self, _evt):
        if self._is_building():
            return
        ext = self._current_output_ext()
        default_dir = (os.path.dirname(self.output_path)
                       or self.settings.get("last_output_dir", "")
                       or self.folder or "")
        default_file = os.path.basename(self.output_path) or f"Master{ext}"
        wildcard = ("M4B audiobook (*.m4b)|*.m4b" if ext == ".m4b"
                    else "MP3 files (*.mp3)|*.mp3")
        dlg = wx.FileDialog(
            self, "Save master as", defaultDir=default_dir,
            defaultFile=default_file, wildcard=wildcard,
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            if not path.lower().endswith(ext):
                path += ext
            self._set_output_path(path, auto=False)
        dlg.Destroy()

    def _on_format_change(self, _evt):
        # Only rewrite an auto-generated output path; never silently move a
        # destination the user chose by hand.
        ext = self._current_output_ext()
        if self.output_path and self._output_auto:
            stem = os.path.splitext(self.output_path)[0]
            self._set_output_path(stem + ext, auto=True)
        self._announce(
            "Output format set to "
            + ("M4B audiobook." if ext == ".m4b" else "MP3."))
        self._update_estimate()

    def _apply_appearance(self):
        """Apply the text-scale and high-contrast accessibility preferences to
        the whole frame, recursively."""
        scale = max(50, min(300, int(self.settings.get("text_scale", 100))))
        base = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        font = wx.Font(base)
        pt = max(6, int(round(base.GetPointSize() * scale / 100.0)))
        font.SetPointSize(pt)
        high = bool(self.settings.get("high_contrast", False))
        fg = wx.Colour(255, 255, 255) if high else wx.NullColour
        bg = wx.Colour(0, 0, 0) if high else wx.NullColour

        def walk(win):
            # Leave the hidden native media control to OS theming.
            if isinstance(win, wx.media.MediaCtrl):
                return
            try:
                win.SetFont(font)
                if high:
                    win.SetForegroundColour(fg)
                    win.SetBackgroundColour(bg)
                else:
                    win.SetForegroundColour(wx.NullColour)
                    win.SetBackgroundColour(wx.NullColour)
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
        return (core.TITLE_SOURCE_EMBEDDED if self.title_source.GetSelection() == 1
                else core.TITLE_SOURCE_FILENAME)

    def _on_title_source(self, _evt):
        source = self._current_title_source()
        core.apply_title_source(self.items, source, respect_edits=True)
        sel = self.list.GetFirstSelected()
        self._refresh_list(select=sel if sel >= 0 else (0 if self.items else -1))
        self._on_list_select(None)
        self._announce("Chapter titles updated from "
                       + ("embedded tags." if source == core.TITLE_SOURCE_EMBEDDED
                          else "filenames."))

    def _apply_settings_to_ui(self):
        s = self.settings
        self.tag_artist.SetValue(s.get("artist", ""))
        self.tag_album_artist.SetValue(s.get("album_artist", ""))
        self.tag_genre.SetValue(s.get("genre", ""))
        self.title_source.SetSelection(
            1 if s.get("title_source") == core.TITLE_SOURCE_EMBEDDED else 0)
        self.bitrate_choice.SetStringSelection(s.get("bitrate", "192k"))
        self.normalize_chk.SetValue(bool(s.get("normalize", False)))
        self.format_choice.SetSelection(
            1 if s.get("output_format") == "m4b" else 0)
        self.pod2_chk.SetValue(bool(s.get("write_pod2", False)))
        try:
            self.gap_ctrl.SetValue(float(s.get("gap_seconds", 0.0)))
        except (ValueError, AttributeError):
            pass
        self._update_estimate()

    def _gather_settings(self):
        s = self.settings
        s["artist"] = self.tag_artist.GetValue().strip()
        s["album_artist"] = self.tag_album_artist.GetValue().strip()
        s["genre"] = self.tag_genre.GetValue().strip()
        s["title_source"] = self._current_title_source()
        s["bitrate"] = self.bitrate_choice.GetStringSelection() or "192k"
        s["normalize"] = self.normalize_chk.GetValue()
        s["output_format"] = "m4b" if self.format_choice.GetSelection() == 1 else "mp3"
        s["write_pod2"] = self.pod2_chk.GetValue()
        s["gap_seconds"] = float(self.gap_ctrl.GetValue())
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

    def _on_list_select(self, _evt):
        sel = self.list.GetFirstSelected()
        if 0 <= sel < self._row_count():
            self.title_ctrl.ChangeValue(self._selected_title(sel))
        else:
            self.title_ctrl.ChangeValue("")
        self._update_command_state()

    def _on_list_key(self, evt):
        key = evt.GetKeyCode()
        sel = self.list.GetFirstSelected()
        edit = self.mode == "edit"
        if key == wx.WXK_DELETE and sel >= 0:
            self._remove_selected()
        elif key == wx.WXK_F2 and sel >= 0:
            self.title_ctrl.SetFocus()
            self.title_ctrl.SelectAll()
        elif key == wx.WXK_UP and evt.AltDown() and not edit:
            self._move(-1)
        elif key == wx.WXK_DOWN and evt.AltDown() and not edit:
            self._move(1)
        else:
            evt.Skip()

    def _on_apply_title(self, evt):
        evt.Skip()
        sel = self.list.GetFirstSelected()
        if not (0 <= sel < self._row_count()):
            return
        new_title = self.title_ctrl.GetValue().strip()
        if not new_title or new_title == self._selected_title(sel):
            return
        if self.mode == "edit":
            self.edit_chapters[sel].title = new_title
            self.edit_dirty = True
        else:
            self.items[sel].title = new_title
            self.items[sel].edited = True
        self.list.SetItem(sel, 1, new_title)
        self._announce(f"Renamed chapter {sel + 1} to “{new_title}”.")

    def _move(self, delta: int):
        if self.mode == "edit":
            return
        sel = self.list.GetFirstSelected()
        new = sel + delta
        if sel < 0 or not (0 <= new < len(self.items)):
            return
        self.items[sel], self.items[new] = self.items[new], self.items[sel]
        self._refresh_list(select=new)
        self._announce(f"Moved chapter to position {new + 1} of {len(self.items)}.")

    def _remove_selected(self):
        sel = self.list.GetFirstSelected()
        if sel < 0:
            return
        if self.mode == "edit":
            try:
                self.edit_chapters = core.merge_chapter(self.edit_chapters, sel)
            except core.ChapterForgeError as exc:
                wx.MessageBox(str(exc), "Cannot merge",
                              wx.OK | wx.ICON_INFORMATION, self)
                return
            self.edit_dirty = True
            nxt = max(0, min(sel, len(self.edit_chapters) - 1))
            self._refresh_list(select=nxt)
            self.player.set_chapters(self.edit_chapters)
            self._announce(
                f"Merged. {len(self.edit_chapters)} chapter(s) remain.")
            return
        removed = self.items.pop(sel)
        nxt = min(sel, len(self.items) - 1)
        self._refresh_list(select=nxt)
        self._announce(f"Removed “{removed.title}”. {len(self.items)} chapter(s) left.")
        if not self.items:
            self.title_ctrl.ChangeValue("")

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
        write_pod2 = self.pod2_chk.GetValue()
        bitrate = self.bitrate_choice.GetStringSelection() or "192k"
        normalize = self.normalize_chk.GetValue()
        gap_ms = self._gap_ms()
        self._save_settings()
        self.canceller = core.Canceller()
        self._last_pct = -1
        self.gauge.SetValue(0)
        verb = "audiobook" if core.output_format(output) == "m4b" else "master MP3"
        self._announce(f"Building {verb}…")
        self._update_command_state_building(True)

        def progress(frac):
            wx.PostEvent(self, _ThreadEvent(EVT_PROGRESS, frac))

        def run():
            try:
                result = core.build_master(
                    items, output, tags, chapters=chapters,
                    bitrate=bitrate, normalize=normalize, gap_ms=gap_ms,
                    canceller=self.canceller, progress=progress)
                try:
                    core.write_chapter_report(output, result, tags, items)
                except OSError:
                    pass
                if write_pod2:
                    try:
                        core.write_pod2_chapters(
                            output, result.chapters, result.total_ms)
                    except OSError:
                        pass
                wx.PostEvent(self, _ThreadEvent(EVT_DONE, result))
            except core.BuildCancelled:
                wx.PostEvent(self, _ThreadEvent(EVT_FAILED, None))
            except Exception as exc:  # surfaced to the user
                wx.PostEvent(self, _ThreadEvent(EVT_FAILED, str(exc)))

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
        self.notifier.notify("ChapterForge — batch done", summary, "info",
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
        result = evt.payload
        self.gauge.SetValue(100)
        mode = "re-encoded" if result.reencoded else "lossless copy"
        kind = "audiobook" if core.output_format(result.output_path) == "m4b" else "master MP3"
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
        self.notifier.notify("ChapterForge — done", summary, "info", speak=False)
        # Offer to preview the finished file in the in-app player.
        if wx.MessageBox(
                f"{summary}\n\nSaved {kind} to:\n{result.output_path}\n\n"
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
            self.notifier.notify("ChapterForge — failed", str(evt.payload),
                                 "error", speak=False)
            wx.MessageBox(str(evt.payload), "Build failed",
                          wx.OK | wx.ICON_ERROR, self)
        self.btn_build.SetFocus()

    # ------------------------------------------------------------------
    # Chapter editing / job files / watcher
    # ------------------------------------------------------------------
    def _on_edit_chapter(self, _evt):
        sel = self.list.GetFirstSelected()
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
            self.player.vol_slider.SetValue(
                int(self.settings.get("default_volume", 80)))
            self._announce("Settings saved.")
        dlg.Destroy()

    def _on_player_volume(self, vol: int):
        self.settings["default_volume"] = int(vol)

    # ------------------------------------------------------------------
    # Play-from-here / split / estimate
    # ------------------------------------------------------------------
    def _on_play_selected(self, _evt):
        sel = self.list.GetFirstSelected()
        if sel < 0 or sel >= self._row_count():
            return
        if self.mode == "edit":
            if not self.player.has_media():
                self.player.load(self.edit_path, self.edit_chapters)
                # Load is async; queue the chapter to play once ready.
                self.player.play_chapter(sel)
            else:
                self.player.play_chapter(sel)
        else:
            # Audition a single source file in the player.
            item = self.items[sel]
            one = [core.Chapter(index=0, title=item.title, start_ms=0,
                                end_ms=item.duration_ms)]
            if self.player.load(item.path, one):
                self.player.play_chapter(0)
                self.panel.Layout()
        self._announce(f"Playing chapter {sel + 1}.")

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
            return int(round(float(self.gap_ctrl.GetValue()) * 1000))
        except (ValueError, AttributeError):
            return 0

    def _update_estimate(self):
        if self.mode == "edit" or not self.items:
            self.estimate_text.SetLabel("")
            return
        bitrate = self.bitrate_choice.GetStringSelection() or "192k"
        total_ms, est_bytes = core.estimate_output(
            self.items, bitrate=bitrate, gap_ms=self._gap_ms())
        fmt = "M4B" if self.format_choice.GetSelection() == 1 else "MP3"
        self.estimate_text.SetLabel(
            f"Estimated {fmt}: {core.format_timestamp(total_ms)}, "
            f"about {core.format_size(est_bytes)} "
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
                    "Podcasting 2.0 JSON (*.json)|*.json")
        fmt_by_index = ["audacity", "cue", "timestamps", "pod2"]
        ext_by_index = [".txt", ".cue", ".txt", ".json"]
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
        if self.mode != "edit":
            wx.MessageBox(
                "Open an existing master first (File → Open Existing Master), "
                "then import a chapter list to replace its markers.",
                "Import chapters", wx.OK | wx.ICON_INFORMATION, self)
            return
        if self._is_building():
            return
        default_dir = self.settings.get("last_input_dir", "") or self.folder
        dlg = wx.FileDialog(
            self, "Import chapter list", defaultDir=default_dir,
            wildcard=("Chapter lists (*.txt;*.cue;*.json)|*.txt;*.cue;*.json|"
                      "All files (*.*)|*.*"),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        path = dlg.GetPath()
        dlg.Destroy()
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

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def _on_save_diagnostics(self, _evt):
        report = self._build_diagnostics()
        dlg = wx.FileDialog(
            self, "Save diagnostics", defaultFile="chapterforge-diagnostics.txt",
            wildcard="Text files (*.txt)|*.txt",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        dest = dlg.GetPath()
        dlg.Destroy()
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
        self._announce("Reading chapters…")
        wx.BeginBusyCursor()
        try:
            tags, chapters, total_ms = core.read_master(path)
        except core.ChapterForgeError as exc:
            if wx.IsBusy():
                wx.EndBusyCursor()
            wx.MessageBox(str(exc), "Could not read file",
                          wx.OK | wx.ICON_ERROR, self)
            return
        finally:
            if wx.IsBusy():
                wx.EndBusyCursor()
        self._enter_edit_mode(path, tags, chapters, total_ms)
        self._push_recent(path)

    def _enter_edit_mode(self, path, tags, chapters, total_ms):
        self.player.release(recreate=True)
        self.mode = "edit"
        self.edit_path = path
        self.edit_chapters = list(chapters)
        self.edit_total_ms = total_ms
        self.edit_dirty = False
        self.items = []
        self.folder = os.path.dirname(path)
        self.folder_ctrl.ChangeValue(path)
        self._apply_tags_to_ui(tags)
        self._refresh_list(select=0 if chapters else -1)
        is_mp3 = core.output_format(path) == "mp3"
        note = ("" if is_mp3 else
                " This is an M4B/MP4 file, so use Save As to write a new file"
                " (in-place saving is MP3 only).")
        self._announce(
            f"Editing {os.path.basename(path)}: {len(chapters)} chapter(s). "
            f"Edit titles, links, images and tags." + note)
        if self.player.load(path, chapters):
            self.panel.Layout()
        self.list.SetFocus()

    def _enter_build_mode(self):
        self.mode = "build"
        self.edit_path = ""
        self.edit_chapters = []
        self.edit_total_ms = 0
        self.edit_dirty = False
        self._update_command_state()

    def _apply_tags_to_ui(self, tags: core.Tags):
        self.tag_title.ChangeValue(tags.title)
        self.tag_artist.ChangeValue(tags.artist)
        self.tag_album.ChangeValue(tags.album)
        self.tag_album_artist.ChangeValue(tags.album_artist)
        self.tag_genre.ChangeValue(tags.genre)
        self.tag_year.ChangeValue(tags.year)
        self.tag_comment.ChangeValue(tags.comment)

    def _on_save_edit(self, _evt):
        if self.mode != "edit" or not self._edit_is_mp3():
            return
        if self.title_ctrl.HasFocus():
            self._on_apply_title(wx.CommandEvent())
        tags = self._collect_tags()
        # The player holds the file open; release before re-tagging.
        self.player.release(recreate=True)
        try:
            core.save_tags_chapters_inplace(
                self.edit_path, self.edit_chapters, tags)
        except core.ChapterForgeError as exc:
            wx.MessageBox(str(exc), "Could not save",
                          wx.OK | wx.ICON_ERROR, self)
            return
        self.edit_dirty = False
        if self.pod2_chk.GetValue():
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

    def _on_save_as(self, _evt):
        if self._is_building():
            return
        if self.title_ctrl.HasFocus():
            self._on_apply_title(wx.CommandEvent())
        if self.mode == "edit":
            self._save_edit_as()
        else:
            # In build mode, Save As is a convenient "build to a chosen file".
            self._on_set_output(None)
            if self.output_path:
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
        tags = self._collect_tags()
        self._announce("Saving a copy…")
        wx.BeginBusyCursor()
        try:
            core.save_master_as(self.edit_path, dest, self.edit_chapters, tags)
        except core.ChapterForgeError as exc:
            if wx.IsBusy():
                wx.EndBusyCursor()
            wx.MessageBox(str(exc), "Could not save", wx.OK | wx.ICON_ERROR, self)
            return
        finally:
            if wx.IsBusy():
                wx.EndBusyCursor()
        if self.pod2_chk.GetValue():
            try:
                core.write_pod2_chapters(dest, self.edit_chapters, self.edit_total_ms)
            except OSError:
                pass
        self._announce(f"Saved a copy to {os.path.basename(dest)}.")
        wx.MessageBox(f"Saved to:\n{dest}", "Saved",
                      wx.OK | wx.ICON_INFORMATION, self)

    # ------------------------------------------------------------------
    # Silence auto-chaptering / batch
    # ------------------------------------------------------------------
    def _on_silence(self, _evt):
        if self._is_building():
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
        self._announce("Detecting chapters from silence…")
        wx.BeginBusyCursor()
        try:
            tags, _, total_ms = core.read_master(path)
            chapters = core.detect_silence_chapters(
                path, noise_db=noise, min_silence=min_sil)
        except core.ChapterForgeError as exc:
            if wx.IsBusy():
                wx.EndBusyCursor()
            wx.MessageBox(str(exc), "Could not analyse file",
                          wx.OK | wx.ICON_ERROR, self)
            return
        finally:
            if wx.IsBusy():
                wx.EndBusyCursor()
        if not chapters:
            wx.MessageBox(
                "No silent gaps long enough to split on were found.\n\n"
                "Try lowering the minimum silence length or raising the "
                "threshold in Tools → Settings.",
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
        fmt = "m4b" if self.format_choice.GetSelection() == 1 else "mp3"
        names = "\n".join(f"• {os.path.basename(f)}" for f in folders[:20])
        more = "" if len(folders) <= 20 else f"\n…and {len(folders) - 20} more"
        if wx.MessageBox(
                f"Build a {fmt.upper()} master for each of these "
                f"{len(folders)} folder(s)?\n\n{names}{more}",
                "Batch build", wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
            return
        self._run_batch(folders, fmt)

    def _run_batch(self, folders, fmt):
        bitrate = self.bitrate_choice.GetStringSelection() or "192k"
        normalize = self.normalize_chk.GetValue()
        write_pod2 = self.pod2_chk.GetValue()
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
                bitrate=self.bitrate_choice.GetStringSelection() or "192k",
                normalize=self.normalize_chk.GetValue())
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
        self._announce("Loading job file…")
        wx.BeginBusyCursor()
        try:
            items = core.items_from_entries(entries)
        finally:
            wx.EndBusyCursor()
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
        self.bitrate_choice.SetStringSelection(manifest.bitrate)
        self.normalize_chk.SetValue(manifest.normalize)

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
            on_quit=self._quit_from_tray)
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
        self.Destroy()

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------
    def _on_guide(self, _evt):
        from . import docs
        if docs.open_doc(docs.USER_GUIDE):
            self._announce("Opening the User Guide in your browser.")
            return
        guide = (
            "ChapterForge — Quick Start\n"
            "\n"
            "1. Open Folder (Ctrl+O): choose a folder of MP3 files. Each file "
            "becomes one chapter, in natural (1, 2, 10) order.\n"
            "2. Review chapters in the list. Rename with Edit Title, reorder "
            "with Move Up/Down, drop one with Remove.\n"
            "3. Fill in the master tags (title, artist, album, cover, …).\n"
            "4. Set Output File (Ctrl+S), then Build Master MP3 (Ctrl+B).\n"
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
            "Everything is keyboard accessible — see Help → Keyboard Shortcuts.")
        self._scroll_dialog("User Guide", guide)

    def _on_deployment_doc(self, _evt):
        self._open_doc_page("DEPLOYMENT", "Deployment Guide")

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
        keys = (
            "Keyboard shortcuts\n"
            "\n"
            "Ctrl+O\tOpen folder of MP3 files\n"
            "Ctrl+E\tOpen an existing chaptered file to edit\n"
            "Ctrl+S\tSet output file\n"
            "Ctrl+B\tBuild master (MP3 or M4B)\n"
            "Ctrl+Shift+S\tSave changes to the open master\n"
            "Ctrl+Alt+S\tSave As (a new file)\n"
            "Esc\tCancel a build in progress\n"
            "Ctrl+L\tLoad a .cfjob job file\n"
            "Ctrl+G\tGenerate a .cfjob job file\n"
            "Ctrl+W\tManage watch folders\n"
            "Ctrl+,\tSettings\n"
            "F1\tUser guide\n"
            "Ctrl+/\tThis shortcut list\n"
            "\n"
            "In the chapter list:\n"
            "Up/Down\tMove between chapters\n"
            "F2 / Enter\tEdit the selected chapter title\n"
            "Edit Title button\tEdit title, link URL and image\n"
            "Delete\tRemove the selected chapter (build mode)\n"
            "Alt+Up / Alt+Down\tReorder the selected chapter (build mode)\n"
            "\n"
            "In the player (Alt+letter access keys):\n"
            "Play/Pause, Stop\tStart, pause or stop playback\n"
            "Previous / Next Chapter\tJump between chapters\n"
            "Rewind / Forward\tSkip by the configured interval\n"
            "Position / Volume\tArrow keys adjust the sliders\n"
            "\n"
            "Most buttons also have an underlined access key (Alt+letter).")
        self._scroll_dialog("Keyboard Shortcuts", keys)

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

    def _on_website(self, _evt):
        from . import updates
        wx.LaunchDefaultBrowser(updates.PROJECT_URL)

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

    def _update_check_done(self, release, error):
        self.mi_update.Enable(True)
        from . import updates
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

    def _on_close(self, evt):
        # When the background watcher is active, closing hides to the tray
        # instead of quitting, so watching continues. An update install forces
        # a real quit so the installer can replace the running files.
        if (self._tray is not None and not self._is_building()
                and not self._force_quit):
            self.Hide()
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
            btn = wx.Button(self, label=f"{text} \u2014 {desc}")
            btn.SetName(f"{text}. {desc}. Opens {url} in your browser.")
            btn.SetToolTip(url)
            btn.Bind(wx.EVT_BUTTON, lambda _e, u=url: wx.LaunchDefaultBrowser(u))
            outer.Add(btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 12)

        btns = self.CreateButtonSizer(wx.OK)
        outer.Add(btns, 0, wx.EXPAND | wx.ALL, 12)

        self.SetSizerAndFit(outer)
        ok = self.FindWindow(wx.ID_OK)
        if ok:
            ok.SetFocus()
        self.CentreOnParent()


class SettingsDialog(wx.Dialog):
    """Accessible preferences dialog. Reads from and writes back to a settings
    dict (the caller persists it). Every control has a label + accessible name."""

    def __init__(self, parent, settings: dict):
        super().__init__(parent, title="ChapterForge Settings",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.settings = settings
        outer = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(0, 2, 8, 10)
        grid.AddGrowableCol(1, 1)

        def row(label_text, ctrl, name):
            lbl = wx.StaticText(self, label=label_text)
            ctrl.SetName(name)
            grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(ctrl, 1, wx.EXPAND)
            return ctrl

        self.fmt = wx.Choice(self, choices=["MP3 (.mp3)", "M4B audiobook (.m4b)"])
        self.fmt.SetSelection(1 if settings.get("output_format") == "m4b" else 0)
        row("Default output &format:", self.fmt, "Default output format")

        self.title_src = wx.Choice(self, choices=["Filename", "Embedded tag"])
        self.title_src.SetSelection(
            1 if settings.get("title_source") == core.TITLE_SOURCE_EMBEDDED else 0)
        row("Chapter titles fro&m:", self.title_src, "Chapter title source")

        self.bitrate = wx.Choice(
            self, choices=["128k", "160k", "192k", "256k", "320k"])
        self.bitrate.SetStringSelection(str(settings.get("bitrate", "192k")))
        row("Re-encode &quality:", self.bitrate, "Re-encode quality")

        self.normalize = wx.CheckBox(self, label="")
        self.normalize.SetValue(bool(settings.get("normalize", False)))
        row("&Normalize loudness:", self.normalize, "Normalize loudness")

        self.auto_cover = wx.CheckBox(self, label="")
        self.auto_cover.SetValue(bool(settings.get("auto_cover", True)))
        row("Auto-detect &cover image:", self.auto_cover, "Auto-detect cover image")

        self.write_pod2 = wx.CheckBox(self, label="")
        self.write_pod2.SetValue(bool(settings.get("write_pod2", False)))
        row("Also write chapters &JSON (Podcasting 2.0):", self.write_pod2,
            "Also write a Podcasting 2.0 chapters JSON sidecar")

        self.skip = wx.SpinCtrl(self, min=1, max=300,
                                initial=int(settings.get("skip_seconds", 10)))
        row("Player &skip interval (seconds):", self.skip,
            "Player skip interval in seconds")

        self.volume = wx.SpinCtrl(self, min=0, max=100,
                                  initial=int(settings.get("default_volume", 80)))
        row("Default &volume (percent):", self.volume,
            "Default playback volume percent")

        self.verbosity = wx.Choice(self, choices=["Quiet", "Normal", "Verbose"])
        vmap = {"quiet": 0, "normal": 1, "verbose": 2}
        self.verbosity.SetSelection(
            vmap.get(str(settings.get("announce_verbosity", "normal")), 1))
        row("Announcement &detail:", self.verbosity, "Announcement detail")

        self.noise_db = wx.SpinCtrlDouble(
            self, min=-90.0, max=0.0, inc=1.0,
            initial=float(settings.get("silence_noise_db", -30.0)))
        row("Silence &threshold (dB):", self.noise_db,
            "Silence detection threshold in decibels")

        self.min_silence = wx.SpinCtrlDouble(
            self, min=0.1, max=30.0, inc=0.1,
            initial=float(settings.get("silence_min_seconds", 0.8)))
        row("Minimum silence &length (seconds):", self.min_silence,
            "Minimum silence length in seconds")

        self.gap = wx.SpinCtrlDouble(
            self, min=0.0, max=30.0, inc=0.5,
            initial=float(settings.get("gap_seconds", 0.0)))
        self.gap.SetDigits(1)
        row("&Gap between chapters (seconds):", self.gap,
            "Gap of silence between chapters in seconds")

        self.text_scale = wx.SpinCtrl(
            self, min=50, max=300,
            initial=int(settings.get("text_scale", 100)))
        row("&Text size (percent):", self.text_scale,
            "User interface text size percent")

        self.high_contrast = wx.CheckBox(self, label="")
        self.high_contrast.SetValue(bool(settings.get("high_contrast", False)))
        row("&High-contrast theme:", self.high_contrast, "High-contrast theme")

        outer.Add(grid, 1, wx.EXPAND | wx.ALL, 14)
        outer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL),
                  0, wx.EXPAND | wx.ALL, 12)
        self.SetSizerAndFit(outer)
        self.CentreOnParent()

    def result(self) -> dict:
        """Return the edited settings as a dict (call after ShowModal == OK)."""
        return {
            "output_format": "m4b" if self.fmt.GetSelection() == 1 else "mp3",
            "title_source": (core.TITLE_SOURCE_EMBEDDED
                             if self.title_src.GetSelection() == 1
                             else core.TITLE_SOURCE_FILENAME),
            "bitrate": self.bitrate.GetStringSelection() or "192k",
            "normalize": self.normalize.GetValue(),
            "auto_cover": self.auto_cover.GetValue(),
            "write_pod2": self.write_pod2.GetValue(),
            "skip_seconds": int(self.skip.GetValue()),
            "default_volume": int(self.volume.GetValue()),
            "announce_verbosity": ["quiet", "normal", "verbose"][
                self.verbosity.GetSelection()],
            "silence_noise_db": float(self.noise_db.GetValue()),
            "silence_min_seconds": float(self.min_silence.GetValue()),
            "gap_seconds": float(self.gap.GetValue()),
            "text_scale": int(self.text_scale.GetValue()),
            "high_contrast": self.high_contrast.GetValue(),
        }


class ChapterEditDialog(wx.Dialog):
    """Edit a single chapter's title, and optional link URL and image — the
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
        outer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL),
                  0, wx.EXPAND | wx.ALL, 12)
        self.SetSizerAndFit(outer)
        self.SetSize((520, self.GetSize().height))
        self.title_ctrl.SetFocus()
        self.title_ctrl.SelectAll()
        self.CentreOnParent()

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


class ChapterForgeApp(wx.App):
    def OnInit(self):
        try:
            core._find_tool("ffmpeg")
            core._find_tool("ffprobe")
        except core.FFmpegNotFoundError as exc:
            wx.MessageBox(str(exc), "FFmpeg required",
                          wx.OK | wx.ICON_ERROR)
            return False
        frame = MainFrame()
        frame.Show()
        self.SetTopWindow(frame)
        return True


def main():
    app = ChapterForgeApp(False)
    app.MainLoop()


if __name__ == "__main__":
    main()
