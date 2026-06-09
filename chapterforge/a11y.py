"""Accessibility / screen-reader announcements for ChapterForge.

The screen-reader bridge and announcement grammar are adapted from the QUILL
project (S:\\quill):

* ``quill/platform/windows/prism_bridge.py`` - the Prism (``prism`` /
  ``prismatoid``) announcement engine that routes spoken output to a running
  screen reader (NVDA / JAWS / Narrator) instead of talking over it, with a
  graceful "status only" fallback when Prism isn't installed.
* ``quill/platform/windows/sr_announce.py`` - the small ``announce`` /
  ``set_announce_handler`` transcript API.
* ``quill/core/announcements.py`` - the shared announcement grammar
  (``format_announcement`` / ``format_progress`` / ``pluralize``).

The goal is identical to QUILL's: every status message follows one predictable
grammar, and we never self-voice over a screen reader that is already speaking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from importlib import import_module
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)

AnnounceHandler = Callable[[str], None]

# ---------------------------------------------------------------------------
# Announcement grammar (adapted from quill/core/announcements.py)
# ---------------------------------------------------------------------------


def pluralize(count: int, unit: str) -> str:
    if count == 1:
        plural = unit
    elif unit.endswith(("s", "sh", "ch", "x", "z")):
        plural = f"{unit}es"
    else:
        plural = f"{unit}s"
    return f"{count:,} {plural}"


def _capitalize_first(text: str) -> str:
    return text[0].upper() + text[1:] if text else text


def format_announcement(verb: str, obj: Optional[str] = None, *,
                        count: Optional[int] = None, unit: str = "item",
                        detail: Optional[str] = None) -> str:
    """``<Verb> <object>[, <count> <unit>(s)][, <detail>].``"""
    head = verb.strip()
    if obj:
        head = f"{head} {obj.strip()}"
    segments = [head]
    if count is not None:
        segments.append(pluralize(count, unit))
    if detail:
        segments.append(detail.strip())
    sentence = ", ".join(s for s in segments if s)
    sentence = _capitalize_first(sentence)
    if not sentence.endswith((".", "!", "?")):
        sentence += "."
    return sentence


def format_progress(verb: str, obj: Optional[str] = None, *,
                    count: Optional[int] = None, unit: str = "item") -> str:
    return format_announcement(verb, obj, count=count, unit=unit)


# ---------------------------------------------------------------------------
# Prism backend (adapted from quill/platform/windows/prism_bridge.py)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BackendState:
    active_backend: str  # 'prism' | 'status_only'
    backend_name: str
    prism_available: bool
    last_error: str = ""


def _import_prism_module() -> Optional[Any]:
    for module_name in ("prism", "prismatoid"):
        try:
            return import_module(module_name)
        except Exception:
            continue
    return None


def _probe_prism_backend() -> tuple:
    module = _import_prism_module()
    if module is None:
        return None, "missing"
    try:
        context = module.Context()
        backend = context.acquire_best()
    except Exception:
        return None, "error"
    features = getattr(backend, "features", None)
    if not getattr(features, "is_supported_at_runtime", True):
        return None, "runtime_unavailable"
    return backend, "ok"


class AnnouncementEngine:
    """Speak through Prism when available; otherwise stay silent (status only).

    Mirrors QUILL's behaviour: when a Prism backend (a running screen reader)
    is present we route speech to it with ``interrupt=False`` so we never cut
    off the user; otherwise we degrade to a no-op and let the host show the
    message visually.
    """

    def __init__(self) -> None:
        backend, probe = _probe_prism_backend()
        self._backend = backend
        self._state = BackendState(
            active_backend="prism" if backend is not None else "status_only",
            backend_name=_backend_name(backend) if backend is not None else "Status Only",
            prism_available=probe != "missing",
            last_error="" if probe in ("ok", "missing") else probe,
        )

    @property
    def state(self) -> BackendState:
        return self._state

    def speak(self, message: str) -> None:
        if self._backend is None:
            return
        try:
            self._backend.speak(message, interrupt=False)
        except TypeError:
            # Older backend without the interrupt keyword argument
            self._backend.speak(message)
        except Exception as exc:  # pragma: no cover
            self._state = replace(self._state, last_error=str(exc))


def _backend_name(backend: Any) -> str:
    raw = getattr(backend, "name", None)
    return raw.strip() if isinstance(raw, str) and raw.strip() else "Prism"


# ---------------------------------------------------------------------------
# Transcript API (adapted from quill/platform/windows/sr_announce.py)
# ---------------------------------------------------------------------------

_engine: Optional[AnnouncementEngine] = None
_handler: Optional[AnnounceHandler] = None
_transcript_enabled = False
_transcript: List[str] = []


def _get_engine() -> AnnouncementEngine:
    global _engine
    if _engine is None:
        _engine = AnnouncementEngine()
    return _engine


def backend_state() -> BackendState:
    return _get_engine().state


def set_announce_handler(handler: Optional[AnnounceHandler]) -> None:
    """Install a host handler (e.g. one that updates a wx status field)."""
    global _handler
    _handler = handler


def enable_transcript_capture(enabled: bool = True) -> None:
    global _transcript_enabled
    _transcript_enabled = enabled


def transcript_entries() -> List[str]:
    return _transcript.copy()


def clear_transcript() -> None:
    _transcript.clear()


def announce(message: str) -> None:
    """Announce *message*: record it, hand it to the host, and speak via Prism.

    Safe to call from any thread for the speech/transcript parts; a host
    handler that touches a GUI must marshal to the UI thread itself.
    """
    message = (message or "").strip()
    if not message:
        return
    if _transcript_enabled:
        _transcript.append(message)
    if _handler is not None:
        try:
            _handler(message)
        except Exception:
            pass
    try:
        _get_engine().speak(message)
    except (RuntimeError, OSError) as exc:
        logger.debug("a11y speak error: %s", exc)
