"""libmpv-based audio playback engine.

Replaces ``wx.media.MediaCtrl`` (unreliable DirectShow/WMP10 backends - see
git history) and a since-removed FFmpeg-subprocess + sounddevice engine
(rapid load/seek cycles destabilised PortAudio and produced audible glitches
and a native crash). libmpv decodes and outputs audio natively and supports
fast, accurate in-stream seeking, so a single long-lived player instance can
simply load, seek, and pause/resume - no subprocess plumbing, no feeder
threads, no pipeline teardown/rebuild on every seek.

ChapterForge bundles ``libmpv-2.dll`` under ``bin/mpv/`` (see THIRD_PARTY.md
for the LGPL/GPL redistribution notice this requires) and drives it through
the ``python-mpv`` ctypes wrapper. The DLL's directory must be added to the
DLL search path *before* ``import mpv`` runs, since that import probes for
the library immediately and raises ``OSError`` if it can't find one.

mpv's event and property-observer callbacks fire on its own internal event
thread. All public methods on this class must be called from the wx main
thread; state changes mpv reports are marshalled back with ``wx.CallAfter``,
matching the rest of the app's worker-thread model.
"""

from __future__ import annotations

import os
import sys
from typing import Callable, Optional

import wx


def _libmpv_dir() -> Optional[str]:
    """Locate the folder holding the bundled ``libmpv-2.dll``.

    Mirrors ``core._candidate_dirs`` (frozen exe dir, ``_MEIPASS``, source
    tree) but looks specifically in a ``bin/mpv`` subfolder.
    """
    dirs = []
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        dirs.append(os.path.join(exe_dir, "bin", "mpv"))
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            dirs.append(os.path.join(meipass, "bin", "mpv"))
    here = os.path.dirname(os.path.abspath(__file__))
    dirs.append(os.path.join(here, "..", "bin", "mpv"))
    for d in dirs:
        d = os.path.abspath(d)
        if os.path.isfile(os.path.join(d, "libmpv-2.dll")):
            return d
    return None


_libmpv_dir_found = _libmpv_dir()
if _libmpv_dir_found and os.name == "nt":
    os.add_dll_directory(_libmpv_dir_found)
    os.environ["PATH"] = _libmpv_dir_found + os.pathsep + os.environ.get("PATH", "")

import mpv  # noqa: E402  (must follow the DLL search path setup above)


class MpvAudioEngine:
    """Loads and plays one media file at a time via a long-lived libmpv core.

    Seeking is native (``seek absolute+exact``) and does not restart decoding
    or change the pause state, so chapter navigation, fast-forward and
    rewind are just property/command calls - no race-prone teardown.
    """

    def __init__(self, on_loaded: Callable[[int], None],
                 on_finished: Callable[[], None],
                 on_error: Callable[[str], None]):
        self._on_loaded = on_loaded
        self._on_finished = on_finished
        self._on_error = on_error

        self._length_ms = 0
        self._loaded = False
        self._finished = False
        self._volume = 1.0
        self._gen = 0

        self._mpv = mpv.MPV(video=False, ytdl=False, keep_open=True, idle=True)
        self._mpv.pause = True
        self._mpv.volume = self._volume * 100.0
        self._mpv.event_callback('file-loaded')(self._on_file_loaded_event)
        self._mpv.event_callback('end-file')(self._on_end_file_event)
        self._mpv.observe_property('eof-reached', self._on_eof_reached)

    # ------------------------------------------------------------------
    # Public API (main thread only)
    # ------------------------------------------------------------------
    def load(self, path: str) -> bool:
        """Begin loading *path* from the start. Always returns True;
        failure is reported asynchronously via the on_error callback."""
        self._gen += 1
        gen = self._gen
        self._length_ms = 0
        self._loaded = False
        self._finished = False
        try:
            self._mpv.pause = True
            self._mpv.command('loadfile', path, 'replace')
        except Exception:
            wx.CallAfter(self._fail, gen, "This file could not be loaded for playback.")
            return False
        return True

    def close(self):
        """Stop playback and fully release the file handle."""
        self._gen += 1
        self._loaded = False
        self._finished = False
        self._length_ms = 0
        try:
            self._mpv.command('stop')
        except Exception:
            pass

    def play(self):
        if not self._loaded:
            return
        if self._finished:
            self.seek(0, resume=True)
            return
        self._mpv.pause = False

    def pause(self):
        if not self._loaded:
            return
        self._mpv.pause = True

    def stop(self):
        """Halt playback and return to the beginning, paused."""
        if not self._loaded:
            return
        self.seek(0, resume=False)

    def seek(self, ms: int, resume: Optional[bool] = None):
        """Seek to *ms*. By default playback resumes iff it was already
        playing; pass *resume* explicitly to override (e.g. to seek and
        start playing in one atomic step right after a load)."""
        if not self._loaded:
            return
        target = max(0, min(self._length_ms, int(ms)))
        if resume is None:
            resume = self.is_playing()
        try:
            self._mpv.command('seek', target / 1000.0, 'absolute+exact')
        except Exception:
            return
        self._finished = False
        self._mpv.pause = not resume

    def set_volume(self, level: float):
        self._volume = max(0.0, min(1.0, float(level)))
        try:
            self._mpv.volume = self._volume * 100.0
        except Exception:
            pass

    def is_loaded(self) -> bool:
        return self._loaded

    def is_playing(self) -> bool:
        if not self._loaded or self._finished:
            return False
        try:
            return not self._mpv.pause
        except Exception:
            return False

    def tell(self) -> int:
        if not self._loaded:
            return 0
        if self._finished:
            return self._length_ms
        try:
            pos = self._mpv.time_pos
        except Exception:
            pos = None
        if pos is None:
            return 0
        return max(0, int(pos * 1000))

    def length(self) -> int:
        return self._length_ms

    def shutdown(self):
        """Fully release the libmpv core. Call once, on app/player teardown."""
        self._gen += 1
        self._loaded = False
        try:
            self._mpv.terminate()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internals - mpv event/property callbacks (mpv event thread)
    # ------------------------------------------------------------------
    def _on_file_loaded_event(self, event):
        gen = self._gen
        try:
            duration = self._mpv.duration or 0.0
        except Exception:
            duration = 0.0
        wx.CallAfter(self._finish_load, gen, int(duration * 1000))

    def _on_end_file_event(self, event):
        gen = self._gen
        try:
            reason = event.data.reason
        except Exception:
            reason = None
        if reason == mpv.MpvEventEndFile.ERROR and not self._loaded:
            wx.CallAfter(self._fail, gen, "This file could not be loaded for playback.")

    def _on_eof_reached(self, name, value):
        if value:
            wx.CallAfter(self._announce_finished, self._gen)

    # ------------------------------------------------------------------
    # Internals - marshalled onto the wx main thread
    # ------------------------------------------------------------------
    def _finish_load(self, gen: int, length_ms: int):
        if gen != self._gen:
            return
        self._length_ms = length_ms
        self._loaded = True
        self._finished = False
        self._on_loaded(length_ms)

    def _fail(self, gen: int, message: str):
        if gen != self._gen:
            return
        self._loaded = False
        self._on_error(message)

    def _announce_finished(self, gen: int):
        if gen != self._gen or not self._loaded or self._finished:
            return
        self._finished = True
        self._on_finished()
