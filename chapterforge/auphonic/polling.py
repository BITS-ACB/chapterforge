"""Polling-based production status monitor for the desktop app.

Desktop apps can't receive webhooks, so we poll with exponential backoff.
The poller runs on a background thread and calls back into the UI via
the supplied callback (wx.CallAfter or similar).
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from .client import AuphonicClient, AuphonicError

_INITIAL_INTERVAL = 5       # seconds between first polls
_MAX_INTERVAL = 60          # cap backoff at 1 minute
_BACKOFF_FACTOR = 1.5
_TERMINAL_STATUSES = {"Done", "Error", "failed", "error", "done"}


class ProductionPoller:
    """Poll a single production until it reaches a terminal state.

    Parameters
    ----------
    client:
        Authenticated AuphonicClient.
    auphonic_uuid:
        The production UUID returned by Auphonic.
    on_update:
        Called with (status_string, raw_data) from the polling thread.
        Use wx.CallAfter in the callback to safely touch the UI.
    on_done:
        Called with (status_string, raw_data) when a terminal state is reached.
    on_error:
        Called with (error_message,) on network or API failure.
    """

    def __init__(self, client: AuphonicClient, auphonic_uuid: str,
                 on_update: Callable, on_done: Callable, on_error: Callable):
        self._client = client
        self._uuid = auphonic_uuid
        self._on_update = on_update
        self._on_done = on_done
        self._on_error = on_error
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"poll-{self._uuid[:8]}")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        interval = _INITIAL_INTERVAL
        while not self._stop_event.is_set():
            try:
                data = self._client.get_production_status(self._uuid)
                status = data.get("status_string", "")
                self._on_update(status, data)
                if _is_terminal(status, data.get("status", 0)):
                    self._on_done(status, data)
                    return
            except AuphonicError as exc:
                self._on_error(str(exc))
                return
            except Exception as exc:
                self._on_error(f"Unexpected polling error: {exc}")
                return
            self._stop_event.wait(timeout=interval)
            interval = min(interval * _BACKOFF_FACTOR, _MAX_INTERVAL)


def _is_terminal(status_string: str, status_code: int) -> bool:
    s = status_string.lower()
    if any(t in s for t in ("done", "error", "failed", "cancelled")):
        return True
    # Auphonic numeric codes: 3=Done, 9=Error
    if status_code in (3, 9):
        return True
    return False
