"""wxPython dialogs for the Auphonic integration.

All dialogs are fully keyboard accessible and screen-reader compatible.
Accessibility rules (from CLAUDE.md):
  - wx.CheckBox: put the full label in the label= constructor arg.
  - wx.SpinCtrl/SpinCtrlDouble: attach _NamedAccessible.
  - All other controls: ctrl.SetName("description").
  - Open dialogs: set focus on first meaningful control.
  - Announce background operations via a11y.announce().
  - No m-dashes or emojis.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Callable, Dict, List, Optional

import wx

from .auphonic import AuphonicService, AuphonicError, AudioValidationError
from .auphonic.models import JobStatus, ProductionRequest
from .auphonic.presets import BUILTIN_PRESETS, all_presets
from .auphonic.estimate import estimate_credits, credits_sufficient, format_credits, format_duration
from .auphonic.output_filter import classify_output, ALLOWED_OUTPUT_TYPES
from . import a11y


# ---------------------------------------------------------------------------
# Accessible SpinCtrl helper (matches pattern in app.py)
# ---------------------------------------------------------------------------

class _NamedAccessible(wx.Accessible):
    def __init__(self, ctrl, name):
        super().__init__(ctrl)
        self._name = name

    def GetName(self, childId):
        return wx.ACC_OK, self._name


# ---------------------------------------------------------------------------
# Connect / Account dialog
# ---------------------------------------------------------------------------

class AuphonicConnectDialog(wx.Dialog):
    """Shows connection status, credit balance, and Connect/Disconnect buttons."""

    def __init__(self, parent, service: AuphonicService):
        super().__init__(parent, title="Auphonic - Connect Account",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._service = service
        self._build_ui()
        self._refresh_status()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Status section
        status_box = wx.StaticBox(panel, label="Connection Status")
        status_sizer = wx.StaticBoxSizer(status_box, wx.VERTICAL)

        self._lbl_status = wx.StaticText(panel, label="Checking...")
        self._lbl_status.SetName("Connection status")
        self._lbl_credits = wx.StaticText(panel, label="")
        self._lbl_credits.SetName("Available credits")
        self._lbl_recharge = wx.StaticText(panel, label="")
        self._lbl_recharge.SetName("Recharge information")

        status_sizer.Add(self._lbl_status, 0, wx.ALL, 6)
        status_sizer.Add(self._lbl_credits, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        status_sizer.Add(self._lbl_recharge, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        sizer.Add(status_sizer, 0, wx.EXPAND | wx.ALL, 8)

        # Info text
        info = wx.StaticText(
            panel,
            label=(
                "Connect your Auphonic account to process audio using your own credits.\n"
                "Your browser will open to complete authorization."
            ),
        )
        info.Wrap(380)
        sizer.Add(info, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._btn_connect = wx.Button(panel, label="&Connect Auphonic")
        self._btn_connect.SetName("Connect Auphonic account")
        self._btn_disconnect = wx.Button(panel, label="&Disconnect")
        self._btn_disconnect.SetName("Disconnect Auphonic account")
        self._btn_refresh = wx.Button(panel, label="&Refresh Balance")
        self._btn_refresh.SetName("Refresh credit balance")
        btn_close = wx.Button(panel, wx.ID_CLOSE, label="Close")

        btn_sizer.Add(self._btn_connect, 0, wx.RIGHT, 4)
        btn_sizer.Add(self._btn_disconnect, 0, wx.RIGHT, 4)
        btn_sizer.Add(self._btn_refresh, 0, wx.RIGHT, 4)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(btn_close, 0)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 8)

        panel.SetSizer(sizer)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        self.SetSizerAndFit(outer)
        self.SetMinSize((420, 240))

        self._btn_connect.Bind(wx.EVT_BUTTON, self._on_connect)
        self._btn_disconnect.Bind(wx.EVT_BUTTON, self._on_disconnect)
        self._btn_refresh.Bind(wx.EVT_BUTTON, lambda _: self._refresh_status())
        btn_close.Bind(wx.EVT_BUTTON, lambda _: self.Close())
        self.Bind(wx.EVT_CLOSE, lambda _: self.Destroy())

        self._btn_connect.SetFocus()

    def _refresh_status(self):
        connected = self._service.is_connected()
        if connected:
            self._lbl_status.SetLabel("Status: Connected")
            user = self._service.get_user()
            if user:
                total = format_credits(user.credits)
                self._lbl_credits.SetLabel(
                    f"Credits: {total} total  "
                    f"({format_credits(user.recurring_credits)} recurring, "
                    f"{format_credits(user.onetime_credits)} one-time)"
                )
                recharge = (
                    f"Recharge: {format_credits(user.recharge_recurring_credits)} on {user.recharge_date}"
                    if user.recharge_date else ""
                )
                self._lbl_recharge.SetLabel(recharge)
            else:
                self._lbl_credits.SetLabel("Could not retrieve credit balance.")
        else:
            self._lbl_status.SetLabel("Status: Not connected")
            self._lbl_credits.SetLabel("")
            self._lbl_recharge.SetLabel("")

        self._btn_connect.Enable(not connected)
        self._btn_disconnect.Enable(connected)
        self._btn_refresh.Enable(connected)
        self.Layout()

    def _on_connect(self, _):
        self._btn_connect.Disable()
        self._lbl_status.SetLabel("Status: Waiting for browser authorization...")
        a11y.announce("Opening browser for Auphonic authorization. Complete the login and return here.")

        def _do_connect():
            ok, err = self._service.connect()
            wx.CallAfter(self._after_connect, ok, err)

        threading.Thread(target=_do_connect, daemon=True).start()

    def _after_connect(self, ok: bool, err: str):
        if ok:
            a11y.announce("Connected to Auphonic successfully.")
        else:
            a11y.announce(f"Auphonic connection failed: {err}")
            wx.MessageBox(f"Connection failed:\n\n{err}", "Auphonic Connection",
                          wx.OK | wx.ICON_ERROR, self)
        self._refresh_status()

    def _on_disconnect(self, _):
        if wx.MessageBox(
            "Disconnect your Auphonic account? Active jobs will no longer update.",
            "Disconnect Auphonic",
            wx.YES_NO | wx.ICON_QUESTION,
            self,
        ) == wx.YES:
            self._service.disconnect()
            a11y.announce("Disconnected from Auphonic.")
            self._refresh_status()


# ---------------------------------------------------------------------------
# New Production dialog
# ---------------------------------------------------------------------------

class NewProductionDialog(wx.Dialog):
    """Main production builder: source, preset, outputs, and submit."""

    def __init__(self, parent, service: AuphonicService):
        super().__init__(parent, title="New Auphonic Production",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._service = service
        self._probe_result = None
        self._account_presets: List[Dict] = []
        self._build_ui()
        self._load_presets()

    def _build_ui(self):
        panel = wx.Panel(self)
        main = wx.BoxSizer(wx.VERTICAL)

        # -- Source section --
        src_box = wx.StaticBox(panel, label="Audio Source")
        src_sizer = wx.StaticBoxSizer(src_box, wx.VERTICAL)

        src_row = wx.BoxSizer(wx.HORIZONTAL)
        self._txt_source = wx.TextCtrl(panel, style=wx.TE_READONLY)
        self._txt_source.SetName("Audio source file path")
        self._btn_browse = wx.Button(panel, label="&Browse...")
        self._btn_browse.SetName("Browse for audio file")
        self._lbl_duration = wx.StaticText(panel, label="")
        self._lbl_duration.SetName("File duration")
        src_row.Add(wx.StaticText(panel, label="File:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        src_row.Add(self._txt_source, 1, wx.EXPAND | wx.RIGHT, 4)
        src_row.Add(self._btn_browse, 0)
        src_sizer.Add(src_row, 0, wx.EXPAND | wx.ALL, 4)
        src_sizer.Add(self._lbl_duration, 0, wx.LEFT | wx.BOTTOM, 4)

        # Credit estimate
        self._lbl_estimate = wx.StaticText(panel, label="")
        self._lbl_estimate.SetName("Credit estimate")
        src_sizer.Add(self._lbl_estimate, 0, wx.LEFT | wx.BOTTOM, 4)

        main.Add(src_sizer, 0, wx.EXPAND | wx.ALL, 8)

        # -- Title --
        title_row = wx.BoxSizer(wx.HORIZONTAL)
        title_lbl = wx.StaticText(panel, label="&Title:")
        self._txt_title = wx.TextCtrl(panel)
        self._txt_title.SetName("Production title")
        title_row.Add(title_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        title_row.Add(self._txt_title, 1, wx.EXPAND)
        main.Add(title_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # -- Preset section --
        preset_box = wx.StaticBox(panel, label="Preset")
        preset_sizer = wx.StaticBoxSizer(preset_box, wx.VERTICAL)
        self._lst_presets = wx.ListBox(panel, style=wx.LB_SINGLE)
        self._lst_presets.SetName("Select a processing preset")
        self._lbl_preset_desc = wx.StaticText(panel, label="Select a preset to see its description.")
        self._lbl_preset_desc.SetName("Preset description")
        self._lbl_preset_desc.Wrap(380)
        preset_sizer.Add(self._lst_presets, 1, wx.EXPAND | wx.ALL, 4)
        preset_sizer.Add(self._lbl_preset_desc, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
        main.Add(preset_sizer, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # -- Options --
        self._chk_review = wx.CheckBox(
            panel, label="&Review outputs before publishing"
        )
        self._chk_review.SetName("Review outputs before publishing")
        main.Add(self._chk_review, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # -- Credit warning --
        self._lbl_warning = wx.StaticText(panel, label="")
        self._lbl_warning.SetName("Credit warning")
        self._lbl_warning.SetForegroundColour(wx.Colour(180, 0, 0))
        main.Add(self._lbl_warning, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # -- Buttons --
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._btn_submit = wx.Button(panel, label="&Submit Production")
        self._btn_submit.SetName("Submit production to Auphonic")
        self._btn_submit.Disable()
        btn_cancel = wx.Button(panel, wx.ID_CANCEL, label="Cancel")
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self._btn_submit, 0, wx.RIGHT, 4)
        btn_sizer.Add(btn_cancel, 0)
        main.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 8)

        panel.SetSizer(main)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        self.SetSizerAndFit(outer)
        self.SetMinSize((480, 560))

        self._btn_browse.Bind(wx.EVT_BUTTON, self._on_browse)
        self._lst_presets.Bind(wx.EVT_LISTBOX, self._on_preset_select)
        self._btn_submit.Bind(wx.EVT_BUTTON, self._on_submit)

        self._btn_browse.SetFocus()

    def _load_presets(self):
        self._account_presets = self._service.list_account_presets()
        all_p = all_presets(self._account_presets)
        self._presets = all_p
        self._lst_presets.Clear()
        for p in all_p:
            self._lst_presets.Append(p.preset_name)
        if all_p:
            self._lst_presets.SetSelection(0)
            self._update_preset_desc(0)

    def _update_preset_desc(self, idx: int):
        if 0 <= idx < len(self._presets):
            p = self._presets[idx]
            self._lbl_preset_desc.SetLabel(p.description or "(No description)")
            self._lbl_preset_desc.Wrap(380)
            self.Layout()

    def _on_preset_select(self, evt):
        self._update_preset_desc(evt.GetSelection())

    def _on_browse(self, _):
        wildcard = (
            "Audio files|*.mp3;*.wav;*.flac;*.m4a;*.aac;*.ogg;*.opus;*.aif;*.aiff;*.wma|"
            "All files|*.*"
        )
        dlg = wx.FileDialog(self, "Select audio file", wildcard=wildcard,
                             style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            dlg.Destroy()
            self._validate_and_set_file(path)
        else:
            dlg.Destroy()

    def _validate_and_set_file(self, path: str):
        self._txt_source.SetValue("Validating...")
        self._lbl_duration.SetLabel("")
        self._lbl_estimate.SetLabel("")
        self._lbl_warning.SetLabel("")
        self._btn_submit.Disable()
        a11y.announce("Validating audio file, please wait.")

        def _validate():
            try:
                probe = self._service.validate_file(path)
                wx.CallAfter(self._after_validate, path, probe, None)
            except AudioValidationError as exc:
                wx.CallAfter(self._after_validate, path, None, str(exc))

        threading.Thread(target=_validate, daemon=True).start()

    def _after_validate(self, path, probe, error):
        if error:
            self._txt_source.SetValue("")
            self._lbl_duration.SetLabel("")
            a11y.announce(f"Validation failed: {error}")
            wx.MessageBox(error, "Audio Validation Failed", wx.OK | wx.ICON_WARNING, self)
            return

        self._probe_result = probe
        self._txt_source.SetValue(path)
        dur_str = format_duration(probe.duration_seconds)
        self._lbl_duration.SetLabel(
            f"Duration: {dur_str}  |  {probe.audio_codec.upper()}  "
            f"{probe.sample_rate // 1000}kHz  {probe.channels}ch"
        )

        est = estimate_credits(probe.duration_seconds)
        self._lbl_estimate.SetLabel(f"Estimated credit usage: {format_credits(est)}")

        user = self._service.get_user()
        if user and not credits_sufficient(user.credits, est):
            self._lbl_warning.SetLabel(
                f"Warning: estimated usage ({format_credits(est)}) may exceed "
                f"available credits ({format_credits(user.credits)})."
            )
            a11y.announce("Warning: estimated credit usage may exceed your available balance.")
        else:
            self._lbl_warning.SetLabel("")

        if not self._txt_title.GetValue():
            self._txt_title.SetValue(os.path.splitext(os.path.basename(path))[0])

        self._btn_submit.Enable()
        a11y.announce(f"File validated. Duration {dur_str}. Ready to submit.")

    def _on_submit(self, _):
        path = self._txt_source.GetValue()
        title = self._txt_title.GetValue().strip()
        if not path or not title:
            wx.MessageBox("Please select an audio file and enter a title.", "Missing Information",
                           wx.OK | wx.ICON_WARNING, self)
            return

        idx = self._lst_presets.GetSelection()
        preset = self._presets[idx] if 0 <= idx < len(self._presets) else None

        payload: Dict[str, Any] = {}
        if preset:
            if not preset.is_builtin:
                payload["preset"] = preset.uuid
            else:
                payload.update(preset.payload)

        req = ProductionRequest(
            title=title,
            output_files=payload.get("output_files", [{"format": "mp3", "bitrate": "128"}]),
            algorithms=payload.get("algorithms", {}),
            speech_recognition=payload.get("speech_recognition", {}),
            review_before_publishing=self._chk_review.GetValue(),
            action="start",
        )

        self._btn_submit.Disable()
        a11y.announce("Submitting production to Auphonic, please wait.")

        parent = self.GetParent()

        def _on_update(status, data):
            wx.CallAfter(lambda: None)  # wake event loop

        def _on_done(status, data):
            wx.CallAfter(_show_done, status)

        def _on_error(msg):
            wx.CallAfter(_show_error, msg)

        def _show_done(status):
            a11y.announce(f"Production complete: {status}")
            if parent:
                wx.MessageBox(
                    f"Production finished with status: {status}\n\nOpen History to download results.",
                    "Auphonic - Done",
                    wx.OK | wx.ICON_INFORMATION,
                    parent,
                )

        def _show_error(msg):
            a11y.announce(f"Production error: {msg}")
            if parent:
                wx.MessageBox(f"Production error:\n\n{msg}", "Auphonic Error",
                              wx.OK | wx.ICON_ERROR, parent)

        def _submit():
            job_id, err = self._service.submit_production(
                req, local_file_path=path,
                on_update=_on_update,
                on_done=_on_done,
                on_error=_on_error,
            )
            if err:
                wx.CallAfter(lambda: wx.MessageBox(
                    f"Submission failed:\n\n{err}",
                    "Auphonic Error", wx.OK | wx.ICON_ERROR, self,
                ))
                wx.CallAfter(self._btn_submit.Enable)
            else:
                wx.CallAfter(self.Close)

        threading.Thread(target=_submit, daemon=True).start()


# ---------------------------------------------------------------------------
# Job history dialog
# ---------------------------------------------------------------------------

class JobHistoryDialog(wx.Dialog):
    """Shows a list of submitted Auphonic jobs with status and download options."""

    _COLS = ["Title", "Status", "Credits Used", "Created"]

    def __init__(self, parent, service: AuphonicService):
        super().__init__(parent, title="Auphonic - Job History",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._service = service
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        self._list = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN)
        self._list.SetName("Auphonic job history")
        for i, col in enumerate(self._COLS):
            self._list.InsertColumn(i, col, width=140 if i == 0 else 100)
        sizer.Add(self._list, 1, wx.EXPAND | wx.ALL, 8)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._btn_download = wx.Button(panel, label="&Download Results")
        self._btn_download.SetName("Download results for selected job")
        self._btn_download.Disable()
        self._btn_publish = wx.Button(panel, label="&Publish")
        self._btn_publish.SetName("Publish selected job")
        self._btn_publish.Disable()
        btn_refresh = wx.Button(panel, label="&Refresh")
        btn_refresh.SetName("Refresh job list")
        btn_close = wx.Button(panel, wx.ID_CLOSE, label="Close")
        btn_sizer.Add(self._btn_download, 0, wx.RIGHT, 4)
        btn_sizer.Add(self._btn_publish, 0, wx.RIGHT, 4)
        btn_sizer.Add(btn_refresh, 0, wx.RIGHT, 4)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(btn_close, 0)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        panel.SetSizer(sizer)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        self.SetSizerAndFit(outer)
        self.SetMinSize((620, 400))

        self._list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_select)
        self._btn_download.Bind(wx.EVT_BUTTON, self._on_download)
        self._btn_publish.Bind(wx.EVT_BUTTON, self._on_publish)
        btn_refresh.Bind(wx.EVT_BUTTON, lambda _: self._refresh())
        btn_close.Bind(wx.EVT_BUTTON, lambda _: self.Close())
        self.Bind(wx.EVT_CLOSE, lambda _: self.Destroy())

        self._list.SetFocus()

    def _refresh(self):
        self._jobs = self._service.list_jobs()
        self._list.DeleteAllItems()
        for row in self._jobs:
            idx = self._list.InsertItem(self._list.GetItemCount(), row["title"] or "(untitled)")
            self._list.SetItem(idx, 1, row["app_status"])
            used = row["used_credits_hours"]
            self._list.SetItem(idx, 2, format_credits(used) if used else "-")
            self._list.SetItem(idx, 3, (row["created_at"] or "")[:16])
        self._btn_download.Disable()
        self._btn_publish.Disable()

    def _on_select(self, evt):
        idx = evt.GetIndex()
        if 0 <= idx < len(self._jobs):
            row = self._jobs[idx]
            status = row["app_status"]
            self._btn_download.Enable(status in (JobStatus.DONE, JobStatus.PUBLISHED))
            self._btn_publish.Enable(status == JobStatus.NEEDS_REVIEW)

    def _on_download(self, _):
        idx = self._list.GetFirstSelected()
        if idx < 0 or idx >= len(self._jobs):
            return
        row = self._jobs[idx]
        outputs = self._service.get_outputs(row["id"])
        if not outputs:
            wx.MessageBox("No downloadable outputs found for this job.",
                           "No Outputs", wx.OK | wx.ICON_INFORMATION, self)
            return

        dlg = wx.DirDialog(self, "Choose download folder", style=wx.DD_DEFAULT_STYLE)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        dest_dir = dlg.GetPath()
        dlg.Destroy()

        a11y.announce("Downloading output files, please wait.")
        errors = []
        for out in outputs:
            url = out["download_url"]
            filename = out["filename"] or f"output.{out['ending']}"
            data, err = self._service.download_output(url)
            if err:
                errors.append(f"{filename}: {err}")
                continue
            dest = os.path.join(dest_dir, filename)
            try:
                with open(dest, "wb") as fh:
                    fh.write(data)
            except OSError as exc:
                errors.append(f"{filename}: {exc}")

        if errors:
            a11y.announce("Some downloads failed.")
            wx.MessageBox("Some downloads failed:\n\n" + "\n".join(errors),
                           "Download Errors", wx.OK | wx.ICON_WARNING, self)
        else:
            a11y.announce(f"Downloaded {len(outputs)} file(s) to {dest_dir}.")
            wx.MessageBox(f"Downloaded {len(outputs)} file(s) to:\n{dest_dir}",
                           "Download Complete", wx.OK | wx.ICON_INFORMATION, self)

    def _on_publish(self, _):
        idx = self._list.GetFirstSelected()
        if idx < 0 or idx >= len(self._jobs):
            return
        row = self._jobs[idx]
        auphonic_uuid = row["auphonic_uuid"]
        if not auphonic_uuid:
            wx.MessageBox("No Auphonic production UUID for this job.",
                           "Cannot Publish", wx.OK | wx.ICON_ERROR, self)
            return
        ok, err = self._service.publish_production(auphonic_uuid)
        if ok:
            a11y.announce("Production published.")
            self._refresh()
        else:
            a11y.announce(f"Publish failed: {err}")
            wx.MessageBox(f"Publish failed:\n{err}", "Publish Error",
                           wx.OK | wx.ICON_ERROR, self)
