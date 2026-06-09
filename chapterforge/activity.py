"""Thread-safe activity registry for ChapterForge background tasks.

Any code that runs a long operation in a worker thread registers an
``Activity`` here.  The ``StatusWindow`` subscribes to changes and
reflects the live state to the user.

Usage::

    from chapterforge.activity import ActivityManager
    act = ActivityManager.get()
    token = act.start("Transcribing audio", can_cancel=True)
    try:
        token.update(50, "Transcribing... 50%")
        ...
        token.finish("Done.")
    except SomethingCancelled:
        token.cancel()
    finally:
        act.remove(token)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional


class ActivityState(str, Enum):
    RUNNING = "running"
    PAUSED  = "paused"
    DONE    = "done"
    FAILED  = "failed"
    CANCELLED = "cancelled"


@dataclass
class Activity:
    """Represents one background task visible in the status window."""

    id: int
    label: str
    state: ActivityState = ActivityState.RUNNING
    progress: float = 0.0          # 0-100
    status_text: str = ""
    can_cancel: bool = False
    can_pause: bool = False
    started_at: float = field(default_factory=time.monotonic)
    finished_at: Optional[float] = None

    # Internal callbacks set by ActivityManager - not part of the public API.
    _on_cancel: Optional[Callable[[], None]] = field(default=None, repr=False)
    _on_pause: Optional[Callable[[], None]] = field(default=None, repr=False)
    _on_resume: Optional[Callable[[], None]] = field(default=None, repr=False)

    def update(self, progress: float, text: str = "") -> None:
        """Update progress and status text (call from any thread)."""
        self.progress = max(0.0, min(100.0, progress))
        if text:
            self.status_text = text

    def finish(self, text: str = "Done.") -> None:
        self.state = ActivityState.DONE
        self.progress = 100.0
        self.status_text = text
        self.finished_at = time.monotonic()

    def fail(self, text: str = "Failed.") -> None:
        self.state = ActivityState.FAILED
        self.status_text = text
        self.finished_at = time.monotonic()

    def cancel(self, text: str = "Cancelled.") -> None:
        self.state = ActivityState.CANCELLED
        self.status_text = text
        self.finished_at = time.monotonic()

    def request_cancel(self) -> None:
        """Request cancellation; invokes the registered cancel callback."""
        if self.can_cancel and self._on_cancel:
            self._on_cancel()

    def request_pause(self) -> None:
        """Toggle pause; invokes the registered pause/resume callback."""
        if self.can_pause:
            if self.state == ActivityState.PAUSED:
                self.state = ActivityState.RUNNING
                if self._on_resume:
                    self._on_resume()
            else:
                self.state = ActivityState.PAUSED
                if self._on_pause:
                    self._on_pause()


class ActivityManager:
    """Singleton registry for all background activities."""

    _instance: Optional[ActivityManager] = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self._activities: List[Activity] = []
        self._next_id: int = 1
        self._lock = threading.Lock()
        self._listeners: List[Callable[[Activity], None]] = []

    @classmethod
    def get(cls) -> ActivityManager:
        """Return the process-wide singleton, creating it if needed."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def start(
        self,
        label: str,
        *,
        can_cancel: bool = False,
        can_pause: bool = False,
        on_cancel: Optional[Callable[[], None]] = None,
        on_pause: Optional[Callable[[], None]] = None,
        on_resume: Optional[Callable[[], None]] = None,
    ) -> Activity:
        """Register a new activity and return its token."""
        with self._lock:
            act = Activity(
                id=self._next_id,
                label=label,
                can_cancel=can_cancel,
                can_pause=can_pause,
                _on_cancel=on_cancel,
                _on_pause=on_pause,
                _on_resume=on_resume,
            )
            self._next_id += 1
            self._activities.append(act)
        self._notify(act)
        return act

    def remove(self, activity: Activity) -> None:
        """Deregister an activity (call after it finishes or is cancelled)."""
        with self._lock:
            try:
                self._activities.remove(activity)
            except ValueError:
                pass
        self._notify(activity)

    def notify_update(self, activity: Activity) -> None:
        """Explicitly push an update notification (optional - for progress)."""
        self._notify(activity)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def all(self) -> List[Activity]:
        with self._lock:
            return list(self._activities)

    def active_count(self) -> int:
        with self._lock:
            return sum(
                1 for a in self._activities
                if a.state in (ActivityState.RUNNING, ActivityState.PAUSED)
            )

    # ------------------------------------------------------------------
    # Listeners (called from any thread via wx.CallAfter in the window)
    # ------------------------------------------------------------------

    def add_listener(self, fn: Callable[[Activity], None]) -> None:
        with self._lock:
            if fn not in self._listeners:
                self._listeners.append(fn)

    def remove_listener(self, fn: Callable[[Activity], None]) -> None:
        with self._lock:
            try:
                self._listeners.remove(fn)
            except ValueError:
                pass

    def _notify(self, activity: Activity) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for fn in listeners:
            try:
                fn(activity)
            except Exception:
                pass
