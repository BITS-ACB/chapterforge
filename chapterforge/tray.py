"""System-tray background watcher for ChapterForge.

Runs the :class:`~chapterforge.watcher.FolderWatcher` from a tray icon so a
folder dropped into a watched location is built automatically in the
background, announcing start/finish via Windows toasts and the screen reader.

Reused by both ``chapterforge --watch`` (standalone) and the GUI's
"Start background watcher" command.
"""

from __future__ import annotations

from typing import Callable, List, Optional

import wx
import wx.adv

from . import __app_name__, watcher_config
from .notify import Notifier
from .watcher import FolderWatcher, WatchEvent


def make_app_icon(size: int = 32) -> wx.Icon:
    """Draw a simple, dependency-free app icon (a play triangle on a disc)."""
    bmp = wx.Bitmap(size, size)
    dc = wx.MemoryDC(bmp)
    dc.SetBackground(wx.Brush(wx.Colour(28, 32, 48)))
    dc.Clear()
    dc.SetBrush(wx.Brush(wx.Colour(64, 132, 223)))
    dc.SetPen(wx.Pen(wx.Colour(64, 132, 223)))
    dc.DrawCircle(size // 2, size // 2, size // 2 - 2)
    dc.SetBrush(wx.Brush(wx.Colour(255, 255, 255)))
    dc.SetPen(wx.Pen(wx.Colour(255, 255, 255)))
    m = size // 4
    dc.DrawPolygon([(m, m), (m, size - m), (size - m, size // 2)])
    dc.SelectObject(wx.NullBitmap)
    icon = wx.Icon()
    icon.CopyFromBitmap(bmp)
    return icon


class WatcherController:
    """Glue between the watcher thread and user-facing notifications."""

    def __init__(self, notifier: Notifier,
                 provider: Optional[Callable[[], List]] = None,
                 on_event: Optional[Callable[[WatchEvent], None]] = None) -> None:
        self.notifier = notifier
        self.extra_on_event = on_event
        self.watcher = FolderWatcher(on_event=self._handle,
                                     provider=provider or watcher_config.load_processes)

    def start(self) -> None:
        self.watcher.start()

    def stop(self, join: bool = False) -> None:
        # Never join from a wx event handler: the watcher may be mid-build.
        self.watcher.stop(join=join)

    @property
    def running(self) -> bool:
        return self.watcher.running

    def _handle(self, event: WatchEvent) -> None:
        category = {"failed": "error", "error": "error"}.get(event.kind, "info")
        if event.kind in ("started", "done", "failed"):
            title = {
                "started": "ChapterForge - working",
                "done": "ChapterForge - done",
                "failed": "ChapterForge - failed",
            }[event.kind]
            self.notifier.notify(title, event.message, category)
        if self.extra_on_event:
            wx.CallAfter(self.extra_on_event, event)


class ChapterForgeTaskBarIcon(wx.adv.TaskBarIcon):
    def __init__(self, controller: Optional[WatcherController],
                 on_open: Callable[[], None],
                 on_manage: Callable[[], None],
                 on_quit: Callable[[], None]) -> None:
        super().__init__()
        self.controller = controller
        self.on_open = on_open
        self.on_manage = on_manage
        self.on_quit = on_quit
        self.SetIcon(make_app_icon(), self._tooltip())
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DCLICK, lambda e: self.on_open())

    def _tooltip(self) -> str:
        if self.controller is None:
            return __app_name__
        state = "watching" if self.controller.running else "paused"
        return f"{__app_name__} - {state}"

    def refresh(self) -> None:
        self.SetIcon(make_app_icon(), self._tooltip())

    def CreatePopupMenu(self):  # noqa: N802 (wx API)
        menu = wx.Menu()
        open_item = menu.Append(wx.ID_ANY, "&Open ChapterForge")
        self.Bind(wx.EVT_MENU, lambda e: self.on_open(), open_item)
        if self.controller is not None:
            toggle = menu.Append(
                wx.ID_ANY,
                "&Pause watching" if self.controller.running else "&Start watching")
            self.Bind(wx.EVT_MENU, self._toggle, toggle)
        manage = menu.Append(wx.ID_ANY, "&Manage watch folders…")
        self.Bind(wx.EVT_MENU, lambda e: self.on_manage(), manage)
        menu.AppendSeparator()
        quit_item = menu.Append(wx.ID_EXIT, "&Quit")
        self.Bind(wx.EVT_MENU, lambda e: self.on_quit(), quit_item)
        return menu

    def _toggle(self, _evt):
        if self.controller is not None:
            if self.controller.running:
                self.controller.stop()
            else:
                self.controller.start()
        self.refresh()


class _TrayApp(wx.App):
    """Standalone tray-only application used by ``--watch``."""

    def OnInit(self):
        self.SetExitOnFrameDelete(False)
        # A hidden owner frame keeps the wx event loop alive.
        self._frame = wx.Frame(None, title=__app_name__)
        self._frame.Hide()
        self.notifier = Notifier(parent=self._frame)
        self.controller = WatcherController(self.notifier)
        self.tray = ChapterForgeTaskBarIcon(
            self.controller, on_open=self._open_gui,
            on_manage=self._manage, on_quit=self._quit)
        self.controller.start()
        self.notifier.notify(__app_name__,
                             "Background watcher started.", "info", speak=True)
        return True

    def _open_gui(self):
        from .app import MainFrame
        frame = MainFrame()
        frame.Show()
        frame.Raise()

    def _manage(self):
        from .watch_dialogs import manage_processes
        manage_processes(self._frame)

    def _quit(self):
        try:
            self.controller.stop(join=False)
        finally:
            self.tray.RemoveIcon()
            self.tray.Destroy()
            self._frame.Destroy()


def run_watch_app() -> None:
    app = _TrayApp(False)
    app.MainLoop()
