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


_ICON_CACHE: dict = {}


def make_app_icon(size: int = 32) -> wx.Icon:
    """Draw a simple, dependency-free app icon (a play triangle on a disc)."""
    if size in _ICON_CACHE:
        return _ICON_CACHE[size]
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
    _ICON_CACHE[size] = icon
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
        if event.kind in ("started", "done", "failed", "waiting", "published"):
            title = {
                "started": "ChapterForge - working",
                "done": "ChapterForge - done",
                "failed": "ChapterForge - failed",
                "waiting": "ChapterForge - waiting",
                "published": "ChapterForge - publish",
            }[event.kind]
            self.notifier.notify(title, event.message, category)
        if self.extra_on_event:
            wx.CallAfter(self.extra_on_event, event)


class ChapterForgeTaskBarIcon(wx.adv.TaskBarIcon):
    def __init__(self, controller: Optional[WatcherController],
                 on_open: Callable[[], None],
                 on_manage: Callable[[], None],
                 on_quit: Callable[[], None],
                 get_player: Optional[Callable[[], Optional[object]]] = None,
                 get_status_window: Optional[Callable[[], object]] = None) -> None:
        super().__init__()
        self.controller = controller
        self.on_open = on_open
        self.on_manage = on_manage
        self.on_quit = on_quit
        # Returns the main app's PlayerPanel, or None - only the main app's
        # tray icon supplies this; the standalone watcher has no player.
        self.get_player = get_player
        # Returns the shared StatusWindow (or None for standalone watcher).
        self.get_status_window = get_status_window
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

        # --- Background Activity ---
        menu.AppendSeparator()
        act_item = menu.Append(wx.ID_ANY, "&Background Activity...")
        self.Bind(wx.EVT_MENU, self._on_show_activity, act_item)
        if self.get_status_window is not None:
            from .activity import ActivityManager
            n = ActivityManager.get().active_count()
            if n > 0:
                ai_cancel_item = menu.Append(wx.ID_ANY, f"Cancel All AI Tasks ({n} running)")
                self.Bind(wx.EVT_MENU, self._on_cancel_all_ai, ai_cancel_item)

        player = self.get_player() if self.get_player else None
        if player is not None and player.has_media():
            menu.AppendSeparator()
            pp = menu.Append(wx.ID_ANY, "Pa&use" if player.is_playing() else "&Play")
            self.Bind(wx.EVT_MENU, player._on_play_pause, pp)
            stop = menu.Append(wx.ID_ANY, "&Stop")
            self.Bind(wx.EVT_MENU, player._on_stop, stop)
            prev = menu.Append(wx.ID_ANY, "Pre&vious Chapter")
            prev.Enable(bool(player.chapters))
            self.Bind(wx.EVT_MENU, player._on_prev, prev)
            nxt = menu.Append(wx.ID_ANY, "Ne&xt Chapter")
            nxt.Enable(bool(player.chapters))
            self.Bind(wx.EVT_MENU, player._on_next, nxt)

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

    def _on_show_activity(self, _evt):
        if self.get_status_window is not None:
            wx.CallAfter(self.get_status_window().show_and_raise)
        else:
            wx.CallAfter(self.on_open)

    def _on_cancel_all_ai(self, _evt):
        from .activity import ActivityManager, ActivityState
        for act in ActivityManager.get().all():
            if act.state == ActivityState.RUNNING and act.can_cancel:
                act.request_cancel()


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
