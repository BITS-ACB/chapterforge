"""A fully accessible in-app audio player for ChapterForge.

The player is a self-contained :class:`wx.Panel` built from standard, native
controls (buttons, a slider and a read-only text field) so that screen readers
announce every control and every state change clearly. The actual decoding is
delegated to :class:`wx.media.MediaCtrl` (the platform media backend), which is
not itself very screen-reader friendly — so the panel never relies on it for
accessibility. Instead every meaningful event is surfaced through:

* visible, named buttons / slider with explicit accessible names,
* a status line that is updated (and announced) on play / pause / seek, and
* an automatic spoken announcement whenever the play-head crosses into a new
  chapter.

Design points worth knowing:

* ``wx.media.MediaCtrl`` keeps the media file open on Windows. Before the rest
  of the app overwrites or re-tags a file the player may have loaded, call
  :meth:`PlayerPanel.release` — it stops playback and recreates the underlying
  control so the OS file handle is released.
* All media calls happen on the main thread (driven by a ``wx.Timer``), so they
  never race the build worker thread.
"""

from __future__ import annotations

import bisect
from typing import Callable, List, Optional, Sequence

import wx
import wx.media

from . import core


def _fmt(ms: int) -> str:
    return core.format_timestamp(max(0, int(ms)))


class PlayerPanel(wx.Panel):
    """An accessible transport for previewing the chaptered master."""

    #: how often (ms) the position is polled / the status refreshed.
    TICK_MS = 400
    #: pressing Previous within this many ms of a chapter start jumps to the
    #: previous chapter; later than this it restarts the current chapter.
    PREV_RESTART_MS = 3000

    def __init__(self, parent, announce: Callable[[str], None],
                 get_skip_seconds: Callable[[], int],
                 get_volume: Callable[[], int],
                 on_volume_change: Optional[Callable[[int], None]] = None):
        super().__init__(parent)
        self._announce = announce
        self._get_skip = get_skip_seconds
        self._get_volume = get_volume
        self._on_volume_change = on_volume_change

        self.media_path: str = ""
        self.chapters: List[core.Chapter] = []
        self._starts: List[int] = []
        self._announced_idx: int = -1
        self._loaded = False
        self._pending_play = False
        self._pending_seek_ms: Optional[int] = None
        self._suppress_announce = False

        self._box = wx.StaticBoxSizer(wx.VERTICAL, self, "Player")
        self._media_holder = wx.BoxSizer(wx.VERTICAL)
        self.mc: Optional[wx.media.MediaCtrl] = None
        self._make_media_ctrl()
        self._box.Add(self._media_holder, 0)

        # --- transport buttons -------------------------------------------
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_play = self._button(row, "&Play", self._on_play_pause,
                                     "Play or pause. Space.")
        self.btn_stop = self._button(row, "S&top", self._on_stop, "Stop.")
        self.btn_prev = self._button(row, "P&revious Chapter",
                                     self._on_prev, "Previous chapter.")
        self.btn_next = self._button(row, "Ne&xt Chapter",
                                     self._on_next, "Next chapter.")
        self.btn_rew = self._button(row, "&Rewind", self._on_rewind,
                                    "Skip backward.")
        self.btn_ff = self._button(row, "&Forward", self._on_forward,
                                   "Skip forward.")
        self._box.Add(row, 0, wx.ALL, 4)

        # --- position slider ---------------------------------------------
        pos_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(self, label="P&osition:")
        pos_row.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)
        self.pos_slider = wx.Slider(self, minValue=0, maxValue=1000, value=0)
        self.pos_slider.SetName("Playback position")
        self.pos_slider.Bind(wx.EVT_SLIDER, self._on_seek_slider)
        pos_row.Add(self.pos_slider, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)
        self._box.Add(pos_row, 0, wx.EXPAND)

        # --- volume slider -----------------------------------------------
        vol_row = wx.BoxSizer(wx.HORIZONTAL)
        vlbl = wx.StaticText(self, label="Vol&ume:")
        vol_row.Add(vlbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)
        self.vol_slider = wx.Slider(self, minValue=0, maxValue=100,
                                    value=int(get_volume()))
        self.vol_slider.SetName("Volume")
        self.vol_slider.Bind(wx.EVT_SLIDER, self._on_volume_slider)
        vol_row.Add(self.vol_slider, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)
        self.status = wx.StaticText(self, label="No audio loaded.")
        self.status.SetName("Player status")
        vol_row.Add(self.status, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 8)
        self._box.Add(vol_row, 0, wx.EXPAND)

        self.SetSizer(self._box)

        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_tick, self._timer)

        self._enable_controls(False)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    def _make_media_ctrl(self):
        mc = wx.media.MediaCtrl()
        ok = mc.Create(self, style=wx.SIMPLE_BORDER)
        if not ok:
            mc.Destroy()
            mc = None
        else:
            mc.SetMinSize((0, 0))
            mc.Hide()
            mc.Bind(wx.media.EVT_MEDIA_LOADED, self._on_media_loaded)
            mc.Bind(wx.media.EVT_MEDIA_FINISHED, self._on_media_finished)
            self._media_holder.Add(mc, 0)
        self.mc = mc

    def _button(self, sizer, label, handler, name):
        btn = wx.Button(self, label=label)
        btn.SetName(name)
        btn.Bind(wx.EVT_BUTTON, handler)
        sizer.Add(btn, 0, wx.ALL, 3)
        return btn

    def _enable_controls(self, on: bool):
        for b in (self.btn_play, self.btn_stop, self.btn_prev, self.btn_next,
                  self.btn_rew, self.btn_ff, self.pos_slider):
            b.Enable(on)
        # Volume always usable so it can be pre-set.
        self.vol_slider.Enable(True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load(self, path: str, chapters: Sequence[core.Chapter]) -> bool:
        """Load *path* with its *chapters*. Returns False if unsupported."""
        self.release(recreate=True)
        if self.mc is None:
            self._set_status("Audio playback is unavailable on this system.")
            return False
        self.media_path = path
        self.chapters = list(chapters)
        self._starts = [c.start_ms for c in self.chapters]
        self._announced_idx = -1
        self._loaded = False
        self._pending_play = False
        self._pending_seek_ms = None
        try:
            ok = self.mc.Load(path)
        except Exception:
            ok = False
        if not ok:
            self._set_status("This file could not be loaded for playback.")
            self._enable_controls(False)
            return False
        self._set_status("Loading audio…")
        return True

    def release(self, recreate: bool = True):
        """Stop playback and free the OS file handle on the loaded media.

        Recreating the underlying control is the only reliable way on Windows
        to make the media backend close the file so it can be overwritten or
        re-tagged.
        """
        if self._timer.IsRunning():
            self._timer.Stop()
        if self.mc is not None:
            try:
                self.mc.Stop()
            except Exception:
                pass
            self.mc.Destroy()
            self.mc = None
        self._loaded = False
        self.media_path = ""
        self.chapters = []
        self._starts = []
        self._pending_play = False
        self._pending_seek_ms = None
        if recreate:
            self._make_media_ctrl()
            self.Layout()
        self._enable_controls(False)
        self.btn_play.SetLabel("&Play")
        self._set_status("No audio loaded.")

    def shutdown(self):
        self.release(recreate=False)

    def is_playing(self) -> bool:
        return (self.mc is not None
                and self.mc.GetState() == wx.media.MEDIASTATE_PLAYING)

    def play_chapter(self, idx: int) -> bool:
        """Public: jump to chapter *idx* and start playing. Honours a load that
        is still in flight by queueing the seek + play."""
        if self.mc is None or not self.chapters:
            return False
        if not (0 <= idx < len(self.chapters)):
            return False
        if not self._loaded:
            self._pending_seek_ms = self.chapters[idx].start_ms
            self._pending_play = True
            return True
        self._seek_chapter(idx)
        self._do_play()
        return True

    def playhead_ms(self) -> int:
        """Public: current playback position in milliseconds (0 if unloaded)."""
        if self.mc is None or not self._loaded:
            return 0
        return self._tell()

    def has_media(self) -> bool:
        return self.mc is not None and self._loaded

    def set_chapters(self, chapters: Sequence[core.Chapter]):
        """Update the chapter map WITHOUT reloading the media file, so playback
        and position are preserved while chapters are edited."""
        self.chapters = list(chapters)
        self._starts = [c.start_ms for c in self.chapters]
        self._announced_idx = -1
        if self._loaded:
            self._refresh_position(announce_chapter=False)

    # ------------------------------------------------------------------
    # Media events
    # ------------------------------------------------------------------
    def _on_media_loaded(self, _evt):
        # Ignore a late event from a control we have since recreated.
        if _evt.GetEventObject() is not self.mc:
            return
        self._loaded = True
        self._enable_controls(True)
        self._apply_volume(self.vol_slider.GetValue())
        length = self._length()
        self._set_status(f"Ready. {_fmt(length)} total"
                         + (f", {len(self.chapters)} chapter(s)."
                            if self.chapters else "."))
        self._refresh_position(announce_chapter=False)
        if self._pending_seek_ms is not None:
            self._seek(self._pending_seek_ms)
            self._pending_seek_ms = None
        if self._pending_play:
            self._pending_play = False
            self._do_play()

    def _on_media_finished(self, _evt):
        if self._timer.IsRunning():
            self._timer.Stop()
        self.btn_play.SetLabel("&Play")
        self._set_status("Finished.")
        self._announce("Playback finished.")

    # ------------------------------------------------------------------
    # Transport handlers
    # ------------------------------------------------------------------
    def _on_play_pause(self, _evt):
        if self.mc is None or not self._loaded:
            return
        if self.is_playing():
            self.mc.Pause()
            self.btn_play.SetLabel("&Play")
            if self._timer.IsRunning():
                self._timer.Stop()
            self._announce(f"Paused at {_fmt(self._tell())}.")
        else:
            self._do_play()

    def _do_play(self):
        if self.mc is None:
            return
        self.mc.Play()
        self._apply_volume(self.vol_slider.GetValue())
        self.btn_play.SetLabel("Pa&use")
        if not self._timer.IsRunning():
            self._timer.Start(self.TICK_MS)
        self._announce("Playing.")

    def _on_stop(self, _evt):
        if self.mc is None:
            return
        self.mc.Stop()
        self.btn_play.SetLabel("&Play")
        if self._timer.IsRunning():
            self._timer.Stop()
        self._announced_idx = -1
        self._refresh_position(announce_chapter=False)
        self._announce("Stopped.")

    def _on_prev(self, _evt):
        if not self._loaded:
            return
        pos = self._tell()
        idx = self._chapter_index(pos)
        if idx < 0:
            return
        if pos - self._starts[idx] > self.PREV_RESTART_MS or idx == 0:
            target = idx
        else:
            target = idx - 1
        self._seek_chapter(target)

    def _on_next(self, _evt):
        if not self._loaded:
            return
        idx = self._chapter_index(self._tell())
        if idx < 0:
            return
        if idx + 1 < len(self.chapters):
            self._seek_chapter(idx + 1)
        else:
            self._announce("Already at the last chapter.")

    def _on_rewind(self, _evt):
        self._skip(-self._get_skip() * 1000)

    def _on_forward(self, _evt):
        self._skip(self._get_skip() * 1000)

    def _skip(self, delta_ms: int):
        if not self._loaded:
            return
        target = max(0, min(self._length(), self._tell() + delta_ms))
        self._seek(target)
        self._announce(f"{_fmt(target)} of {_fmt(self._length())}.")

    def _on_seek_slider(self, _evt):
        if not self._loaded:
            return
        frac = self.pos_slider.GetValue() / 1000.0
        target = int(frac * self._length())
        self._seek(target)
        self._announce(f"{_fmt(target)} of {_fmt(self._length())}.")

    def _on_volume_slider(self, _evt):
        vol = self.vol_slider.GetValue()
        self._apply_volume(vol)
        if self._on_volume_change:
            self._on_volume_change(vol)
        self._announce(f"Volume {vol} percent.")

    # ------------------------------------------------------------------
    # Position / chapter tracking
    # ------------------------------------------------------------------
    def _on_tick(self, _evt):
        self._refresh_position(announce_chapter=True)

    def _refresh_position(self, announce_chapter: bool):
        if self.mc is None or not self._loaded:
            return
        length = self._length()
        pos = self._tell()
        if length > 0:
            self.pos_slider.SetValue(max(0, min(1000, int(pos / length * 1000))))
        idx = self._chapter_index(pos)
        title = ""
        if 0 <= idx < len(self.chapters):
            title = self.chapters[idx].title
        suffix = f" — {title}" if title else ""
        self._set_status(f"{_fmt(pos)} / {_fmt(length)}{suffix}",
                         announce=False)
        if announce_chapter and idx != self._announced_idx and idx >= 0:
            self._announced_idx = idx
            if not self._suppress_announce:
                self._announce(
                    f"Chapter {idx + 1} of {len(self.chapters)}: {title}.")
        self._suppress_announce = False

    def _seek_chapter(self, idx: int):
        if not (0 <= idx < len(self.chapters)):
            return
        self._announced_idx = idx
        self._suppress_announce = True
        self._seek(self.chapters[idx].start_ms)
        self._announce(
            f"Chapter {idx + 1} of {len(self.chapters)}: "
            f"{self.chapters[idx].title}.")

    def _chapter_index(self, pos_ms: int) -> int:
        if not self._starts:
            return -1
        i = bisect.bisect_right(self._starts, pos_ms) - 1
        return max(0, i)

    # ------------------------------------------------------------------
    # Thin MediaCtrl wrappers (all main-thread)
    # ------------------------------------------------------------------
    def _length(self) -> int:
        try:
            return int(self.mc.Length()) if self.mc else 0
        except Exception:
            return 0

    def _tell(self) -> int:
        try:
            return int(self.mc.Tell()) if self.mc else 0
        except Exception:
            return 0

    def _seek(self, ms: int):
        if self.mc is None:
            return
        try:
            self.mc.Seek(int(ms))
        except Exception:
            pass
        self._refresh_position(announce_chapter=False)

    def _apply_volume(self, vol: int):
        if self.mc is None:
            return
        try:
            self.mc.SetVolume(max(0.0, min(1.0, vol / 100.0)))
        except Exception:
            pass

    def _set_status(self, text: str, announce: bool = False):
        self.status.SetLabel(text)
        if announce:
            self._announce(text)
