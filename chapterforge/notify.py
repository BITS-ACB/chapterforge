"""User notifications for ChapterForge.

Combines three channels so both foreground (GUI) and background (tray watcher)
work magically and accessibly:

* a **Windows toast** via ``wx.adv.NotificationMessage`` (no extra dependency);
* a **screen-reader announcement** via :mod:`chapterforge.a11y` (Prism bridge);
* a small **in-app notification log** (atomic JSON), a pattern adapted from
  QUILL's ``quill/core/notifications.py``.

The toast/announce calls are marshalled onto the wx main thread, so the watcher
thread can call :meth:`Notifier.notify` directly and safely.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import List

from . import __app_name__, a11y, settings as settings_mod


# ---------------------------------------------------------------------------
# Persistent log (adapted from quill/core/notifications.py)
# ---------------------------------------------------------------------------


@dataclass
class Notification:
    timestamp: str
    category: str
    title: str
    message: str


def _log_path() -> str:
    return os.path.join(settings_mod.config_dir(), "notifications.json")


def load_notifications() -> List[Notification]:
    try:
        with open(_log_path(), "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return []
    out: List[Notification] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("message"):
                out.append(Notification(
                    timestamp=str(item.get("timestamp", "")),
                    category=str(item.get("category", "info")),
                    title=str(item.get("title", "")),
                    message=str(item.get("message", "")),
                ))
    return out


def _save_notifications(entries: List[Notification], limit: int = 200) -> None:
    trimmed = entries[-limit:]
    try:
        os.makedirs(settings_mod.config_dir(), exist_ok=True)
        tmp = f"{_log_path()}.{os.getpid()}.{threading.get_ident()}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump([asdict(e) for e in trimmed], fh, indent=2)
        os.replace(tmp, _log_path())
    except OSError:
        pass


_log_lock = threading.Lock()


def add_notification(title: str, message: str, category: str = "info") -> None:
    with _log_lock:
        entries = load_notifications()
        entries.append(Notification(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            category=category, title=title, message=message))
        _save_notifications(entries)


# ---------------------------------------------------------------------------
# Live notifier (toast + announce + log)
# ---------------------------------------------------------------------------


class Notifier:
    """Routes notifications to a Windows toast, a screen reader, and the log.

    *enable_toasts* and *enable_speech* let the user turn channels off. A
    ``parent`` wx window (optional) makes toasts associate with the app.
    """

    def __init__(self, parent=None, enable_toasts: bool = True,
                 enable_speech: bool = True) -> None:
        self.parent = parent
        self.enable_toasts = enable_toasts
        self.enable_speech = enable_speech

    def notify(self, title: str, message: str, category: str = "info",
               *, toast: bool = True, speak: bool = True, log: bool = True) -> None:
        if log:
            add_notification(title, message, category)
        if speak and self.enable_speech:
            # a11y.announce is thread-safe for the speech/transcript parts.
            a11y.announce(message if not title else f"{title}. {message}")
        if toast and self.enable_toasts:
            self._toast(title, message, category)

    # -- internal -------------------------------------------------------
    def _toast(self, title: str, message: str, category: str) -> None:
        try:
            import wx
            import wx.adv
        except Exception:
            return

        def show():
            try:
                flag = {
                    "error": wx.ICON_ERROR,
                    "warning": wx.ICON_WARNING,
                }.get(category, wx.ICON_INFORMATION)
                note = wx.adv.NotificationMessage(
                    title or __app_name__, message, self.parent, flag)
                note.Show(timeout=wx.adv.NotificationMessage.Timeout_Auto)
            except Exception:
                pass

        try:
            import wx
            if wx.GetApp() is not None:
                wx.CallAfter(show)
        except Exception:
            pass
