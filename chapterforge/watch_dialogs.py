"""Accessible dialogs for managing reusable watch-folder *processes*.

A *process* (see :mod:`chapterforge.watcher_config`) couples a watched folder
with naming templates and tag defaults. These dialogs let the user create and
edit them entirely from the keyboard; the background watcher and the tray menu
both read the same persisted list.
"""

from __future__ import annotations

from typing import List, Optional

import wx

from . import a11y, feature_flags, settings as settings_mod
from .publish import load_destinations
from .watcher_config import Process, load_processes, save_processes


_TEMPLATE_HELP = ("Templates may use {folder} (the dropped sub-folder's name), "
                  "{parent} (the watched folder), and {date}.")


class ProcessEditDialog(wx.Dialog):
    """Create or edit a single watch-folder process."""

    def __init__(self, parent, process: Process):
        super().__init__(parent, title="Watch-folder process",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.process = process
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        grid = wx.FlexGridSizer(0, 2, 6, 8)
        grid.AddGrowableCol(1, 1)

        def field(label, value, name, hint=""):
            lbl = wx.StaticText(panel, label=label)
            grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            ctrl = wx.TextCtrl(panel, value=value or "")
            ctrl.SetName(name)
            if hint:
                ctrl.SetHint(hint)
            grid.Add(ctrl, 1, wx.EXPAND)
            return ctrl

        self.name_ctrl = field("&Name:", process.name, "Process name")

        # Watch folder with a Browse button.
        grid.Add(wx.StaticText(panel, label="&Watch folder:"),
                 0, wx.ALIGN_CENTER_VERTICAL)
        wf_row = wx.BoxSizer(wx.HORIZONTAL)
        self.folder_ctrl = wx.TextCtrl(panel, value=process.watch_folder or "")
        self.folder_ctrl.SetName("Watch folder")
        self.folder_ctrl.SetHint("Folder that will receive sub-folders of MP3s")
        wf_row.Add(self.folder_ctrl, 1, wx.ALIGN_CENTER_VERTICAL)
        browse = wx.Button(panel, label="B&rowse…")
        browse.SetName("Browse for the folder to watch for new MP3 sub-folders")
        browse.Bind(wx.EVT_BUTTON, self._on_browse)
        wf_row.Add(browse, 0, wx.LEFT, 6)
        grid.Add(wf_row, 1, wx.EXPAND)

        self.output_ctrl = field("&Output name template:", process.output_template,
                                 "Output name template", "{folder} - Master.mp3")
        self.album_ctrl = field("Al&bum template:", process.album_template,
                                "Album template", "{folder}")
        self.title_ctrl = field("&Title template:", process.title_template,
                                "Title template", "{folder}")
        self.artist_ctrl = field("&Artist:", process.artist, "Artist")
        self.album_artist_ctrl = field("Album a&rtist:", process.album_artist,
                                       "Album artist")
        self.genre_ctrl = field("&Genre:", process.genre, "Genre")
        self.narrator_ctrl = field("&Narrator:", process.narrator, "Narrator")
        self.series_ctrl = field("&Series:", process.series_title, "Series title")
        self.series_idx_ctrl = field("Series &part:", process.series_index,
                                     "Series part or number")

        # Choices / checkboxes.
        grid.Add(wx.StaticText(panel, label="Chapter titles fro&m:"),
                 0, wx.ALIGN_CENTER_VERTICAL)
        self.title_source = wx.Choice(panel, choices=["Filename", "Embedded tag"])
        self.title_source.SetName("Chapter title source")
        self.title_source.SetSelection(
            1 if process.title_source == "embedded" else 0)
        grid.Add(self.title_source, 0)

        grid.Add(wx.StaticText(panel, label="Re-encode &quality:"),
                 0, wx.ALIGN_CENTER_VERTICAL)
        self.bitrate = wx.Choice(
            panel, choices=["128k", "160k", "192k", "256k", "320k"])
        self.bitrate.SetName("Re-encode quality")
        self.bitrate.SetStringSelection(process.bitrate or "192k")
        grid.Add(self.bitrate, 0)

        # Build preset selector: if a preset is chosen it overrides bitrate and normalize.
        self._preset_names = ["(none)"] + sorted(
            settings_mod.load().get("presets", {}).keys())
        grid.Add(wx.StaticText(panel, label="Build &preset:"),
                 0, wx.ALIGN_CENTER_VERTICAL)
        self.preset = wx.Choice(panel, choices=self._preset_names)
        self.preset.SetName(
            "Build preset - overrides quality and normalize settings when selected")
        sel = (self._preset_names.index(process.preset)
               if process.preset and process.preset in self._preset_names else 0)
        self.preset.SetSelection(sel)
        grid.Add(self.preset, 0)

        # Per-process publish destination, only when the publishing beta
        # feature is opted into - mirrors the picker in SettingsDialog.
        self._dest_ids: List[str] = []
        self.publish_dest = None
        if feature_flags.is_enabled(settings_mod.load(), "publishing"):
            self._dest_ids = ["", "default"] + [d.id for d in load_destinations()]
            dest_choices = (["Don't publish automatically", "Default destination"]
                            + [d.describe() for d in load_destinations()])
            grid.Add(wx.StaticText(panel, label="Publish &after building:"),
                     0, wx.ALIGN_CENTER_VERTICAL)
            self.publish_dest = wx.Choice(panel, choices=dest_choices)
            self.publish_dest.SetName(
                "Destination to publish to automatically after each build "
                "from this process")
            spec = process.publish_destinations
            try:
                self.publish_dest.SetSelection(self._dest_ids.index(spec))
            except ValueError:
                self.publish_dest.SetSelection(0)
            grid.Add(self.publish_dest, 0)

        sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 12)

        self.enabled_chk = wx.CheckBox(panel, label="&Enabled")
        self.enabled_chk.SetName("Process enabled")
        self.enabled_chk.SetValue(process.enabled)
        sizer.Add(self.enabled_chk, 0, wx.LEFT | wx.BOTTOM, 12)

        self.normalize_chk = wx.CheckBox(panel, label="Nor&malize loudness")
        self.normalize_chk.SetName("Normalize loudness")
        self.normalize_chk.SetValue(process.normalize)
        sizer.Add(self.normalize_chk, 0, wx.LEFT | wx.BOTTOM, 12)

        help_lbl = wx.StaticText(panel, label=_TEMPLATE_HELP)
        help_lbl.Wrap(460)
        sizer.Add(help_lbl, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.EXPAND | wx.ALL, 8)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

        panel.SetSizer(sizer)
        sizer.SetSizeHints(self)
        self.SetMinSize((520, -1))
        self.name_ctrl.SetFocus()

    def _on_browse(self, _evt):
        dlg = wx.DirDialog(self, "Choose the folder to watch",
                           defaultPath=self.folder_ctrl.GetValue() or "",
                           style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            self.folder_ctrl.SetValue(dlg.GetPath())
        dlg.Destroy()

    def _on_ok(self, evt):
        name = self.name_ctrl.GetValue().strip()
        folder = self.folder_ctrl.GetValue().strip()
        if not name:
            wx.MessageBox("Please give the process a name.", "Name required",
                          wx.OK | wx.ICON_WARNING, self)
            return
        if not folder:
            wx.MessageBox("Please choose a folder to watch.", "Folder required",
                          wx.OK | wx.ICON_WARNING, self)
            return
        evt.Skip()

    def result(self) -> Process:
        preset_sel = self.preset.GetSelection()
        preset_name = (self._preset_names[preset_sel]
                       if preset_sel > 0 else "")
        if self.publish_dest is not None:
            sel = self.publish_dest.GetSelection()
            publish_destinations = (self._dest_ids[sel]
                                    if 0 <= sel < len(self._dest_ids) else "")
        else:
            publish_destinations = self.process.publish_destinations
        return Process(
            name=self.name_ctrl.GetValue().strip(),
            watch_folder=self.folder_ctrl.GetValue().strip(),
            enabled=self.enabled_chk.GetValue(),
            output_template=self.output_ctrl.GetValue().strip() or "{folder} - Master.mp3",
            album_template=self.album_ctrl.GetValue().strip() or "{folder}",
            title_template=self.title_ctrl.GetValue().strip() or "{folder}",
            artist=self.artist_ctrl.GetValue().strip(),
            album_artist=self.album_artist_ctrl.GetValue().strip(),
            genre=self.genre_ctrl.GetValue().strip(),
            title_source="embedded" if self.title_source.GetSelection() == 1 else "filename",
            bitrate=self.bitrate.GetStringSelection() or "192k",
            normalize=self.normalize_chk.GetValue(),
            narrator=self.narrator_ctrl.GetValue().strip(),
            series_title=self.series_ctrl.GetValue().strip(),
            series_index=self.series_idx_ctrl.GetValue().strip(),
            preset=preset_name,
            publish_destinations=publish_destinations,
        )


class ProcessesDialog(wx.Dialog):
    """Manage the list of watch-folder processes."""

    def __init__(self, parent):
        super().__init__(parent, title="Watch folders",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.processes: List[Process] = load_processes()

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(panel, label="Watch-folder &processes:"),
                  0, wx.ALL, 8)

        self.listbox = wx.ListBox(panel, style=wx.LB_SINGLE)
        self.listbox.SetName("Watch folder processes")
        self.listbox.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self._on_edit(e))
        sizer.Add(self.listbox, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        row = wx.BoxSizer(wx.HORIZONTAL)
        for label, name, handler in (
                ("&Add…", "Add process", self._on_add),
                ("&Edit…", "Edit process", self._on_edit),
                ("&Remove", "Remove process", self._on_remove),
                ("&Toggle enabled", "Toggle enabled", self._on_toggle)):
            btn = wx.Button(panel, label=label)
            btn.SetName(name)
            btn.Bind(wx.EVT_BUTTON, handler)
            row.Add(btn, 0, wx.ALL, 4)
        sizer.Add(row, 0, wx.ALL, 4)

        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.EXPAND | wx.ALL, 8)
        self.Bind(wx.EVT_BUTTON, self._on_save, id=wx.ID_OK)

        panel.SetSizer(sizer)
        self.SetSize((560, 420))
        self._refresh()

    def _refresh(self, select: int = -1):
        self.listbox.Set([self._describe(p) for p in self.processes])
        if 0 <= select < len(self.processes):
            self.listbox.SetSelection(select)
        elif self.processes:
            self.listbox.SetSelection(0)

    @staticmethod
    def _describe(p: Process) -> str:
        state = "enabled" if p.enabled else "disabled"
        return f"{p.name} - {state} - {p.watch_folder}"

    def _on_add(self, _evt):
        dlg = ProcessEditDialog(self, Process())
        if dlg.ShowModal() == wx.ID_OK:
            self.processes.append(dlg.result())
            self._refresh(len(self.processes) - 1)
        dlg.Destroy()

    def _on_edit(self, _evt):
        i = self.listbox.GetSelection()
        if i < 0:
            return
        dlg = ProcessEditDialog(self, self.processes[i])
        if dlg.ShowModal() == wx.ID_OK:
            self.processes[i] = dlg.result()
            self._refresh(i)
        dlg.Destroy()

    def _on_remove(self, _evt):
        i = self.listbox.GetSelection()
        if i < 0:
            return
        if wx.MessageBox(f"Remove “{self.processes[i].name}”?", "Confirm",
                         wx.YES_NO | wx.ICON_QUESTION, self) == wx.YES:
            del self.processes[i]
            self._refresh(min(i, len(self.processes) - 1))

    def _on_toggle(self, _evt):
        i = self.listbox.GetSelection()
        if i < 0:
            return
        self.processes[i].enabled = not self.processes[i].enabled
        self._refresh(i)
        state = "enabled" if self.processes[i].enabled else "disabled"
        a11y.announce(f"{self.processes[i].name} {state}.")

    def _on_save(self, evt):
        save_processes(self.processes)
        evt.Skip()


def manage_processes(parent: Optional[wx.Window]) -> bool:
    """Open the processes manager. Returns True if the user saved changes."""
    dlg = ProcessesDialog(parent)
    saved = dlg.ShowModal() == wx.ID_OK
    dlg.Destroy()
    return saved
