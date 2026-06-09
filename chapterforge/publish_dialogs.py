"""Accessible dialogs for managing publishing destinations and publishing
built masters to them.

A *destination* (see :mod:`chapterforge.publish.destinations`) is a saved
remote location - currently an SFTP server - that ChapterForge can upload a
finished master to. These dialogs mirror the watch-folder "processes" manager
in :mod:`chapterforge.watch_dialogs`: a list manager with Add/Edit/Remove/
Toggle, plus a per-item edit form, all fully keyboard accessible.

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
from typing import List, Optional

import wx

from . import a11y
from .core import Canceller
from .publish import Destination, PublishService, load_destinations, save_destinations
from .publish import sftp


# ---------------------------------------------------------------------------
# Accessible SpinCtrl helper (matches the pattern in app.py)
# ---------------------------------------------------------------------------

class _NamedAccessible(wx.Accessible):
    def __init__(self, ctrl, name):
        super().__init__(ctrl)
        self._name = name

    def GetName(self, childId):
        return wx.ACC_OK, self._name


_AUTH_METHODS = ["Password", "Private key file"]


# ---------------------------------------------------------------------------
# Destination edit dialog
# ---------------------------------------------------------------------------

class DestinationEditDialog(wx.Dialog):
    """Create or edit a single publishing destination."""

    def __init__(self, parent, destination: Destination):
        super().__init__(parent, title="Publishing destination",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.destination = destination
        self._service = PublishService()
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        grid = wx.FlexGridSizer(0, 2, 6, 8)
        grid.AddGrowableCol(1, 1)

        def field(label, value, name, hint="", password=False):
            lbl = wx.StaticText(panel, label=label)
            grid.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
            style = wx.TE_PASSWORD if password else 0
            ctrl = wx.TextCtrl(panel, value=value or "", style=style)
            ctrl.SetName(name)
            if hint:
                ctrl.SetHint(hint)
            grid.Add(ctrl, 1, wx.EXPAND)
            return ctrl

        self.name_ctrl = field("&Name:", destination.name, "Destination name")
        self.host_ctrl = field("&Host or address:", destination.host, "Host or address",
                               "sftp.example.com")

        grid.Add(wx.StaticText(panel, label="&Port:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.port_ctrl = wx.SpinCtrl(panel, min=1, max=65535,
                                     initial=destination.port or 22)
        self.port_ctrl.SetAccessible(_NamedAccessible(self.port_ctrl, "Port"))
        grid.Add(self.port_ctrl, 0)

        self.user_ctrl = field("&Username:", destination.username, "Username")

        grid.Add(wx.StaticText(panel, label="&Authentication:"),
                 0, wx.ALIGN_CENTER_VERTICAL)
        self.auth_method = wx.Choice(panel, choices=_AUTH_METHODS)
        self.auth_method.SetName("Authentication method")
        self.auth_method.SetSelection(1 if destination.auth_method == "key" else 0)
        self.auth_method.Bind(wx.EVT_CHOICE, self._on_auth_method)
        grid.Add(self.auth_method, 0)

        self.password_lbl = wx.StaticText(panel, label="&Password:")
        grid.Add(self.password_lbl, 0, wx.ALIGN_CENTER_VERTICAL)
        self.password_ctrl = wx.TextCtrl(panel, style=wx.TE_PASSWORD)
        self.password_ctrl.SetName("Password")
        self.password_ctrl.SetHint(
            "Leave blank to keep the saved password" if destination.has_password
            else "")
        grid.Add(self.password_ctrl, 1, wx.EXPAND)

        self.key_lbl = wx.StaticText(panel, label="Pri&vate key file:")
        grid.Add(self.key_lbl, 0, wx.ALIGN_CENTER_VERTICAL)
        key_row = wx.BoxSizer(wx.HORIZONTAL)
        self.key_ctrl = wx.TextCtrl(panel, value=destination.key_path or "")
        self.key_ctrl.SetName("Private key file path")
        self.key_ctrl.SetHint("OpenSSH-format private key (PuTTY/.ppk needs converting first)")
        key_row.Add(self.key_ctrl, 1, wx.ALIGN_CENTER_VERTICAL)
        browse = wx.Button(panel, label="&Browse…")
        browse.SetName("Browse for the private key file")
        browse.Bind(wx.EVT_BUTTON, self._on_browse_key)
        key_row.Add(browse, 0, wx.LEFT, 6)
        grid.Add(key_row, 1, wx.EXPAND)

        self.passphrase_lbl = wx.StaticText(panel, label="Key pa&ssphrase:")
        grid.Add(self.passphrase_lbl, 0, wx.ALIGN_CENTER_VERTICAL)
        self.passphrase_ctrl = wx.TextCtrl(panel, style=wx.TE_PASSWORD)
        self.passphrase_ctrl.SetName("Private key passphrase")
        self.passphrase_ctrl.SetHint(
            "Leave blank to keep the saved passphrase, or if the key has none"
            if destination.has_passphrase else "Leave blank if the key has no passphrase")
        grid.Add(self.passphrase_ctrl, 1, wx.EXPAND)

        self.remote_dir_ctrl = field("&Remote directory:", destination.remote_dir,
                                     "Remote directory",
                                     "Optional - created automatically if missing")

        sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 12)

        self.default_chk = wx.CheckBox(panel, label="Set as &default destination")
        self.default_chk.SetName("Set as default destination")
        self.default_chk.SetValue(destination.is_default)
        sizer.Add(self.default_chk, 0, wx.LEFT | wx.BOTTOM, 12)

        self.enabled_chk = wx.CheckBox(panel, label="&Enabled")
        self.enabled_chk.SetName("Destination enabled")
        self.enabled_chk.SetValue(destination.enabled)
        sizer.Add(self.enabled_chk, 0, wx.LEFT | wx.BOTTOM, 12)

        test_row = wx.BoxSizer(wx.HORIZONTAL)
        self.test_btn = wx.Button(panel, label="&Test connection")
        self.test_btn.SetName("Test connection")
        self.test_btn.Bind(wx.EVT_BUTTON, self._on_test)
        test_row.Add(self.test_btn, 0)
        self.test_status = wx.StaticText(panel, label="")
        self.test_status.SetName("Connection test result")
        test_row.Add(self.test_status, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 10)
        sizer.Add(test_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.EXPAND | wx.ALL, 8)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

        panel.SetSizer(sizer)
        sizer.SetSizeHints(self)
        self.SetMinSize((520, -1))
        self._update_auth_visibility()
        self.name_ctrl.SetFocus()

    # -- Auth method visibility ---------------------------------------------

    def _on_auth_method(self, _evt):
        self._update_auth_visibility()

    def _update_auth_visibility(self):
        is_key = self.auth_method.GetSelection() == 1
        for ctrl in (self.password_lbl, self.password_ctrl):
            ctrl.Show(not is_key)
        for ctrl in (self.key_lbl, self.key_ctrl, self.passphrase_lbl, self.passphrase_ctrl):
            ctrl.Show(is_key)
        self.Layout()

    def _on_browse_key(self, _evt):
        dlg = wx.FileDialog(self, "Choose a private key file",
                            defaultDir=os.path.dirname(self.key_ctrl.GetValue() or ""),
                            wildcard="All files (*.*)|*.*",
                            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            self.key_ctrl.SetValue(dlg.GetPath())
        dlg.Destroy()

    # -- Validation / connection test ----------------------------------------

    def _on_test(self, _evt):
        host = self.host_ctrl.GetValue().strip()
        username = self.user_ctrl.GetValue().strip()
        if not host or not username:
            wx.MessageBox("Enter at least a host and username before testing.",
                          "Test connection", wx.OK | wx.ICON_WARNING, self)
            return

        is_key = self.auth_method.GetSelection() == 1
        port = self.port_ctrl.GetValue()
        key_path = self.key_ctrl.GetValue().strip()

        # Use whatever the user just typed; fall back to the saved secret so
        # re-testing an existing destination without retyping it still works.
        password = self.password_ctrl.GetValue() or (self.destination.password() or "")
        passphrase = self.passphrase_ctrl.GetValue() or (self.destination.passphrase() or "")

        self.test_btn.Disable()
        self.test_status.SetLabel("Testing…")
        a11y.announce(f"Testing connection to {host}.")

        def _do_test():
            try:
                if is_key:
                    sftp.test_connection(host, port, username, key_path=key_path,
                                         passphrase=passphrase or None)
                else:
                    sftp.test_connection(host, port, username, password=password or None)
                wx.CallAfter(self._after_test, True, f"Connected to {host} successfully.")
            except sftp.SftpError as exc:
                wx.CallAfter(self._after_test, False, str(exc))

        threading.Thread(target=_do_test, daemon=True).start()

    def _after_test(self, ok: bool, message: str):
        self.test_btn.Enable()
        self.test_status.SetLabel(message)
        a11y.announce(message)

    def _on_ok(self, evt):
        if not self.name_ctrl.GetValue().strip():
            wx.MessageBox("Please give the destination a name.", "Name required",
                          wx.OK | wx.ICON_WARNING, self)
            return
        if not self.host_ctrl.GetValue().strip():
            wx.MessageBox("Please enter a host or address.", "Host required",
                          wx.OK | wx.ICON_WARNING, self)
            return
        if not self.user_ctrl.GetValue().strip():
            wx.MessageBox("Please enter a username.", "Username required",
                          wx.OK | wx.ICON_WARNING, self)
            return
        if self.auth_method.GetSelection() == 1 and not self.key_ctrl.GetValue().strip():
            wx.MessageBox("Please choose a private key file, or switch to password authentication.",
                          "Private key required", wx.OK | wx.ICON_WARNING, self)
            return
        evt.Skip()

    def result(self) -> Destination:
        """The edited Destination, with any newly-typed secrets persisted."""
        is_key = self.auth_method.GetSelection() == 1
        dest = self.destination
        dest.name = self.name_ctrl.GetValue().strip()
        dest.host = self.host_ctrl.GetValue().strip()
        dest.port = self.port_ctrl.GetValue()
        dest.username = self.user_ctrl.GetValue().strip()
        dest.auth_method = "key" if is_key else "password"
        dest.key_path = self.key_ctrl.GetValue().strip()
        dest.remote_dir = self.remote_dir_ctrl.GetValue().strip()
        dest.is_default = self.default_chk.GetValue()
        dest.enabled = self.enabled_chk.GetValue()

        typed_password = self.password_ctrl.GetValue()
        if typed_password:
            dest.set_password(typed_password)
        elif not is_key and not dest.has_password:
            dest.set_password("")

        typed_passphrase = self.passphrase_ctrl.GetValue()
        if typed_passphrase:
            dest.set_passphrase(typed_passphrase)
        elif not is_key and dest.has_passphrase:
            dest.set_passphrase("")

        return dest


# ---------------------------------------------------------------------------
# Destinations manager dialog
# ---------------------------------------------------------------------------

class DestinationsDialog(wx.Dialog):
    """Manage the list of saved publishing destinations."""

    def __init__(self, parent):
        super().__init__(parent, title="Publishing destinations",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.destinations: List[Destination] = load_destinations()

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(panel, label="Saved publishing &destinations:"),
                  0, wx.ALL, 8)

        self.listbox = wx.ListBox(panel, style=wx.LB_SINGLE)
        self.listbox.SetName("Publishing destinations")
        self.listbox.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self._on_edit(e))
        sizer.Add(self.listbox, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        row = wx.BoxSizer(wx.HORIZONTAL)
        for label, name, handler in (
                ("&Add…", "Add destination", self._on_add),
                ("&Edit…", "Edit destination", self._on_edit),
                ("&Remove", "Remove destination", self._on_remove),
                ("&Toggle enabled", "Toggle destination enabled", self._on_toggle),
                ("Set as &default", "Set destination as default", self._on_set_default)):
            btn = wx.Button(panel, label=label)
            btn.SetName(name)
            btn.Bind(wx.EVT_BUTTON, handler)
            row.Add(btn, 0, wx.ALL, 4)
        sizer.Add(row, 0, wx.ALL, 4)

        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.EXPAND | wx.ALL, 8)
        self.Bind(wx.EVT_BUTTON, self._on_save, id=wx.ID_OK)

        panel.SetSizer(sizer)
        self.SetSize((620, 420))
        self._refresh()
        self.listbox.SetFocus()

    def _refresh(self, select: int = -1):
        self.listbox.Set([d.describe() for d in self.destinations])
        if 0 <= select < len(self.destinations):
            self.listbox.SetSelection(select)
        elif self.destinations:
            self.listbox.SetSelection(0)

    def _on_add(self, _evt):
        dlg = DestinationEditDialog(self, Destination())
        if dlg.ShowModal() == wx.ID_OK:
            new_dest = dlg.result()
            if new_dest.is_default:
                self._clear_other_defaults(new_dest)
            self.destinations.append(new_dest)
            self._refresh(len(self.destinations) - 1)
        dlg.Destroy()

    def _on_edit(self, _evt):
        i = self.listbox.GetSelection()
        if i < 0:
            return
        dlg = DestinationEditDialog(self, self.destinations[i])
        if dlg.ShowModal() == wx.ID_OK:
            edited = dlg.result()
            if edited.is_default:
                self._clear_other_defaults(edited)
            self.destinations[i] = edited
            self._refresh(i)
        dlg.Destroy()

    def _on_remove(self, _evt):
        i = self.listbox.GetSelection()
        if i < 0:
            return
        dest = self.destinations[i]
        if wx.MessageBox(f"Remove “{dest.name}”? Any saved credentials for it will "
                         "also be deleted.", "Confirm",
                         wx.YES_NO | wx.ICON_QUESTION, self) == wx.YES:
            dest.forget_credentials()
            del self.destinations[i]
            self._refresh(min(i, len(self.destinations) - 1))

    def _on_toggle(self, _evt):
        i = self.listbox.GetSelection()
        if i < 0:
            return
        dest = self.destinations[i]
        dest.enabled = not dest.enabled
        self._refresh(i)
        a11y.announce(f"{dest.name} {'enabled' if dest.enabled else 'disabled'}.")

    def _on_set_default(self, _evt):
        i = self.listbox.GetSelection()
        if i < 0:
            return
        dest = self.destinations[i]
        self._clear_other_defaults(dest)
        dest.is_default = True
        self._refresh(i)
        a11y.announce(f"{dest.name} set as the default destination.")

    def _clear_other_defaults(self, keep: Destination):
        for d in self.destinations:
            if d is not keep and d.id != keep.id:
                d.is_default = False

    def _on_save(self, evt):
        save_destinations(self.destinations)
        evt.Skip()


def manage_destinations(parent: Optional[wx.Window]) -> bool:
    """Open the destinations manager. Returns True if the user saved changes."""
    dlg = DestinationsDialog(parent)
    saved = dlg.ShowModal() == wx.ID_OK
    dlg.Destroy()
    return saved


# ---------------------------------------------------------------------------
# Manual publish dialog
# ---------------------------------------------------------------------------

class PublishDialog(wx.Dialog):
    """Pick destinations and upload a built master to them."""

    def __init__(self, parent, local_path: str, service: Optional[PublishService] = None):
        super().__init__(parent, title="Publish",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.local_path = local_path
        self._service = service or PublishService()
        self._canceller: Optional[Canceller] = None
        self._destinations = [d for d in self._service.destinations() if d.enabled]
        self._publishing = False

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        file_lbl = wx.StaticText(panel, label=f"File to publish: {os.path.basename(local_path)}")
        file_lbl.SetName("File to publish")
        sizer.Add(file_lbl, 0, wx.ALL, 10)

        if not self._destinations:
            empty = wx.StaticText(
                panel,
                label="No publishing destinations are saved yet. Use "
                      "Publishing Destinations… to add one.")
            empty.Wrap(420)
            sizer.Add(empty, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
            self.checklist = None
        else:
            sizer.Add(wx.StaticText(panel, label="Publish &to:"), 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
            self.checklist = wx.CheckListBox(
                panel, choices=[d.describe() for d in self._destinations])
            self.checklist.SetName("Destinations to publish to")
            for i, dest in enumerate(self._destinations):
                self.checklist.Check(i, dest.is_default or len(self._destinations) == 1)
            sizer.Add(self.checklist, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.gauge = wx.Gauge(panel, range=100)
        self.gauge.SetName("Upload progress")
        sizer.Add(self.gauge, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.status = wx.StaticText(panel, label="")
        self.status.SetName("Publish status")
        sizer.Add(self.status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.publish_btn = wx.Button(panel, label="&Publish")
        self.publish_btn.SetName("Publish")
        self.publish_btn.Bind(wx.EVT_BUTTON, self._on_publish)
        self.publish_btn.Enable(bool(self._destinations))
        btn_row.Add(self.publish_btn, 0, wx.RIGHT, 6)

        self.cancel_btn = wx.Button(panel, wx.ID_CANCEL, label="Cancel")
        self.cancel_btn.Bind(wx.EVT_BUTTON, self._on_cancel)
        btn_row.Add(self.cancel_btn, 0)
        sizer.Add(btn_row, 0, wx.ALL, 10)

        panel.SetSizer(sizer)
        sizer.SetSizeHints(self)
        self.SetMinSize((460, 320))
        self.Bind(wx.EVT_CLOSE, self._on_close)

        if self.checklist:
            self.checklist.SetFocus()
        else:
            self.publish_btn.SetFocus()

    def _selected_destinations(self) -> List[Destination]:
        if not self.checklist:
            return []
        return [d for i, d in enumerate(self._destinations) if self.checklist.IsChecked(i)]

    def _on_publish(self, _evt):
        targets = self._selected_destinations()
        if not targets:
            wx.MessageBox("Select at least one destination to publish to.",
                          "Nothing selected", wx.OK | wx.ICON_WARNING, self)
            return

        self._publishing = True
        self._canceller = Canceller()
        self.publish_btn.Disable()
        if self.checklist:
            self.checklist.Disable()
        self.gauge.SetValue(0)
        self.status.SetLabel(f"Publishing to {len(targets)} destination(s)…")
        a11y.announce(f"Publishing {os.path.basename(self.local_path)} "
                      f"to {len(targets)} destination(s).")

        def _progress(dest: Destination, transferred: int, total: int):
            pct = int(transferred * 100 / total) if total else 0
            wx.CallAfter(self._on_progress, dest, pct)

        def _do_publish():
            results = self._service.publish(self.local_path, targets,
                                             progress=_progress, canceller=self._canceller)
            wx.CallAfter(self._after_publish, results)

        threading.Thread(target=_do_publish, daemon=True).start()

    def _on_progress(self, dest: Destination, pct: int):
        self.gauge.SetValue(pct)
        self.status.SetLabel(f"Uploading to {dest.name}: {pct}%")

    def _after_publish(self, results):
        self._publishing = False
        self.gauge.SetValue(100 if results and all(r.success for r in results) else 0)
        ok = sum(1 for r in results if r.success)
        failed = [r for r in results if not r.success]
        if not results:
            summary = "Publish cancelled before any uploads completed."
        elif not failed:
            summary = f"Published successfully to {ok} of {ok} destination(s)."
        else:
            summary = f"Published to {ok} of {len(results)} destination(s); {len(failed)} failed."
        self.status.SetLabel(summary)
        a11y.announce(summary)
        for r in failed:
            a11y.announce(r.message)
        if failed:
            details = "\n".join(r.message for r in failed)
            wx.MessageBox(f"{summary}\n\n{details}", "Publish results",
                          wx.OK | wx.ICON_WARNING, self)

        self.publish_btn.Enable()
        if self.checklist:
            self.checklist.Enable()
        self.cancel_btn.SetLabel("Close")

    def _on_cancel(self, evt):
        if self._publishing and self._canceller:
            self._canceller.cancel()
            self.status.SetLabel("Cancelling…")
            a11y.announce("Cancelling publish.")
            return
        evt.Skip()

    def _on_close(self, evt):
        if self._publishing and self._canceller:
            self._canceller.cancel()
        self.Destroy()


def publish_master(parent: Optional[wx.Window], local_path: str) -> None:
    """Open the manual publish dialog for *local_path*."""
    dlg = PublishDialog(parent, local_path)
    dlg.ShowModal()
    dlg.Destroy()
