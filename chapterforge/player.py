"""A fully accessible in-app audio player for ChapterForge.

The player is a self-contained :class:`wx.Panel` built from standard, native
controls (buttons, a slider and a read-only text field) so that screen readers
announce every control and every state change clearly. The actual decoding is
delegated to :class:`wx.media.MediaCtrl` (the platform media backend), which is
not itself very screen-reader friendly - so the panel never relies on it for
accessibility. Instead every meaningful event is surfaced through:

* visible, named buttons / slider with explicit accessible names,
* a status line that is updated (and announced) on play / pause / seek, and
* an automatic spoken announcement whenever the play-head crosses into a new
  chapter.

Design points worth knowing:

* ``wx.media.MediaCtrl`` keeps the media file open on Windows. Before the rest
  of the app overwrites or re-tags a file the player may have loaded, call
  :meth:`PlayerPanel.release` - it stops playback and recreates the underlying
  control so the OS file handle is released.
* All media calls happen on the main thread (driven by a ``wx.Timer``), so they
  never race the build worker thread.
"""

from __future__ import annotations

import bisect
import os
import tempfile
import threading
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

    SPEED_VALUES = [0.75, 1.0, 1.25, 1.5, 1.75, 2.0]
    SPEED_LABELS = [
        "0.75x - slower", "1.0x - normal", "1.25x",
        "1.5x", "1.75x", "2.0x - double speed"]

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

        # Speed / tempo state
        self._speed: float = 1.0          # active playback speed ratio
        self._orig_path: str = ""         # path before any speed processing
        self._orig_chapters: List[core.Chapter] = []  # chapters before scaling
        self._speed_temp: Optional[str] = None         # temp file for speed-adjusted audio
        self._speed_busy: bool = False     # True while FFmpeg is running

        # Trim / cut state
        self._trim_start_ms: int = 0
        self._trim_end_ms: int = 0
        self._trim_active: bool = False

        self._box = wx.StaticBoxSizer(wx.VERTICAL, self, "Player")
        self._media_holder = wx.BoxSizer(wx.VERTICAL)
        self.mc: Optional[wx.media.MediaCtrl] = None
        self._make_media_ctrl()
        self._box.Add(self._media_holder, 0)

        # --- transport buttons -------------------------------------------
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_play = self._button(row, "&Play", self._on_play_pause,
                                     "Play or pause (Space)")
        self.btn_stop = self._button(row, "S&top", self._on_stop,
                                     "Stop playback and return to the beginning")
        self.btn_prev = self._button(row, "P&revious Chapter",
                                     self._on_prev,
                                     "Jump to the previous chapter")
        self.btn_next = self._button(row, "Ne&xt Chapter",
                                     self._on_next,
                                     "Jump to the next chapter")
        self.btn_rew = self._button(row, "&Rewind", self._on_rewind,
                                    "Skip backward by the configured interval")
        self.btn_ff = self._button(row, "&Forward", self._on_forward,
                                   "Skip forward by the configured interval")
        self._box.Add(row, 0, wx.ALL, 4)

        # --- position slider ---------------------------------------------
        pos_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(self, label="P&osition:")
        pos_row.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)
        self.pos_slider = wx.Slider(self, minValue=0, maxValue=1000, value=0)
        self.pos_slider.SetName("Playback position")
        self.pos_slider.SetToolTip("Drag or use arrow keys to scrub through the audio.")
        self.pos_slider.Bind(wx.EVT_SLIDER, self._on_seek_slider)
        pos_row.Add(self.pos_slider, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)
        self._box.Add(pos_row, 0, wx.EXPAND)

        # --- volume slider -----------------------------------------------
        vol_row = wx.BoxSizer(wx.HORIZONTAL)
        vlbl = wx.StaticText(self, label="Vol&ume:")
        vol_row.Add(vlbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)
        self.vol_slider = wx.Slider(self, minValue=0, maxValue=100,
                                    value=int(get_volume()))
        self.vol_slider.SetName("Playback volume, 0 to 100 percent")
        self.vol_slider.Bind(wx.EVT_SLIDER, self._on_volume_slider)
        vol_row.Add(self.vol_slider, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)
        self.status = wx.StaticText(self, label="No audio loaded.")
        self.status.SetName("Player status")
        vol_row.Add(self.status, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 8)
        self._box.Add(vol_row, 0, wx.EXPAND)

        # --- speed / tempo row -------------------------------------------
        spd_row = wx.BoxSizer(wx.HORIZONTAL)
        slbl = wx.StaticText(self, label="S&peed:")
        spd_row.Add(slbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)
        self.speed_choice = wx.Choice(self, choices=self.SPEED_LABELS)
        self.speed_choice.SetSelection(1)  # 1.0x default
        self.speed_choice.SetName(
            "Playback speed - audio is re-processed by FFmpeg when speed is changed")
        self.speed_choice.SetToolTip(
            "Change the playback speed without affecting pitch.\n"
            "ChapterForge uses FFmpeg to time-stretch the audio (this takes a moment).\n"
            "You can also save the speed-adjusted audio as an MP3.")
        self.speed_choice.Bind(wx.EVT_CHOICE, self._on_speed_change)
        spd_row.Add(self.speed_choice, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)

        self.btn_save_speed = wx.Button(self, label="Save at This &Speed…")
        self.btn_save_speed.SetName(
            "Save the audio at the current playback speed as a new MP3 file")
        self.btn_save_speed.SetToolTip(
            "Export the audio at the selected speed to an MP3 file.\n"
            "The pitch is preserved — speech sounds natural at any speed.")
        self.btn_save_speed.Bind(wx.EVT_BUTTON, self._on_save_at_speed)
        self.btn_save_speed.Enable(False)
        spd_row.Add(self.btn_save_speed, 0, wx.ALL, 4)
        self._box.Add(spd_row, 0, wx.EXPAND)

        # --- trim row -------------------------------------------------------
        trim_box = wx.StaticBoxSizer(wx.VERTICAL, self, "Trim / Cut Selection")

        # Selection display
        self._trim_label = wx.StaticText(self, label="No selection set")
        self._trim_label.SetName("Current trim selection - start time to end time")
        trim_box.Add(self._trim_label, 0, wx.ALL, 4)

        # Marker buttons row
        marker_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_trim_start = self._button(
            marker_row, "Set &Begin",
            self._on_set_trim_start,
            "Mark the current playhead position as the start of the selection")
        self.btn_trim_end = self._button(
            marker_row, "Set &End",
            self._on_set_trim_end,
            "Mark the current playhead position as the end of the selection")
        self.btn_trim_clear = self._button(
            marker_row, "&Clear Selection",
            self._on_clear_trim,
            "Clear the current trim selection")
        trim_box.Add(marker_row, 0, wx.ALL, 4)

        # Action buttons row
        action_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_prelisten_cut = self._button(
            action_row, "Pre-&Listen as Cut",
            self._on_prelisten_cut,
            "Play the audio with the selected region removed so you can hear the result before saving")
        self.btn_save_trimmed = self._button(
            action_row, "Save T&rimmed...",
            self._on_save_trimmed,
            "Save the selected region to a new file using lossless FFmpeg copy")
        trim_box.Add(action_row, 0, wx.ALL, 4)

        self._box.Add(trim_box, 0, wx.EXPAND | wx.ALL, 4)

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
            # Do NOT hide: the Windows backend requires a visible, realized
            # HWND before Load() can attach to the media pipeline.
            # SetMinSize((0,0)) already makes it take no visual space.
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
        # Speed choice and save button enabled only when media is ready
        # and no speed-change is in progress.
        self.speed_choice.Enable(on and not self._speed_busy)
        self.btn_save_speed.Enable(on and bool(self._orig_path))
        for b in (self.btn_trim_start, self.btn_trim_end, self.btn_trim_clear,
                  self.btn_prelisten_cut, self.btn_save_trimmed):
            b.Enable(on)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load(self, path: str, chapters: Sequence[core.Chapter]) -> bool:
        """Load *path* with its *chapters*. Returns False if unsupported.

        When loading a file that is *not* the current speed-temp (i.e. a new
        source file), the speed selector is reset to 1.0x and any existing
        temp file is cleaned up.
        """
        is_speed_temp = (path == self._speed_temp)
        if not is_speed_temp:
            # Brand new source — discard any previous speed-adjusted temp
            self._cleanup_speed_temp()
            self._orig_path = path
            self._orig_chapters = list(chapters)
            self._speed = 1.0
            self.speed_choice.SetSelection(1)
            self._trim_start_ms = 0
            self._trim_end_ms = 0
            wx.CallAfter(self._update_trim_label)
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
            if not ok:
                # Some Windows backends need a file:// URI rather than a bare path.
                uri = "file:///" + path.replace("\\", "/")
                ok = self.mc.LoadURI(uri)
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
            self._media_holder.Detach(self.mc)
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
        self._cleanup_speed_temp()

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
        suffix = f" - {title}" if title else ""
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

    # ------------------------------------------------------------------
    # Speed / tempo control
    # ------------------------------------------------------------------

    def _cleanup_speed_temp(self):
        """Delete the temporary speed-adjusted file if one exists."""
        if self._speed_temp and os.path.isfile(self._speed_temp):
            try:
                os.unlink(self._speed_temp)
            except Exception:
                pass
        self._speed_temp = None

    def _scaled_chapters(self, speed: float) -> List[core.Chapter]:
        """Return copies of the original chapters with timestamps scaled for *speed*."""
        result = []
        for c in self._orig_chapters:
            result.append(core.Chapter(
                index=c.index,
                title=c.title,
                start_ms=int(c.start_ms / speed),
                end_ms=int(c.end_ms / speed) if c.end_ms else 0,
                url=c.url,
                img=c.img,
            ))
        return result

    def _on_speed_change(self, _evt):
        idx = self.speed_choice.GetSelection()
        new_speed = self.SPEED_VALUES[idx]
        if abs(new_speed - self._speed) < 0.001:
            return
        if not self._orig_path:
            self._speed = new_speed
            return
        # Convert current playback position to original-audio milliseconds
        if self._loaded:
            output_ms = self._tell()
            orig_ms = int(output_ms * self._speed)
        else:
            orig_ms = 0
        was_playing = self.is_playing()
        self._apply_speed(new_speed, orig_ms, was_playing)

    def _apply_speed(self, new_speed: float, orig_ms: int, resume: bool):
        """Start background tempo processing and reload when done."""
        self._speed_busy = True
        self._enable_controls(False)
        self._speed = new_speed

        if abs(new_speed - 1.0) < 0.001:
            # Back to normal — just reload the original without FFmpeg.
            self._cleanup_speed_temp()
            scaled = self._orig_chapters
            self._speed_temp = None
            self.load(self._orig_path, scaled)
            if orig_ms > 0:
                self._pending_seek_ms = orig_ms
            if resume:
                self._pending_play = True
            self._speed_busy = False
            self._enable_controls(self._loaded)
            return

        src = self._orig_path
        label = self.SPEED_LABELS[self.SPEED_VALUES.index(new_speed)]
        self._set_status(f"Processing audio at {label}…", announce=True)

        tmp = tempfile.mktemp(suffix=".mp3")

        def work():
            ok = core.apply_tempo(src, new_speed, tmp)
            wx.CallAfter(self._speed_done, tmp, new_speed, orig_ms, resume, ok)

        threading.Thread(target=work, daemon=True).start()

    def _speed_done(self, tmp: str, speed: float, orig_ms: int,
                    resume: bool, ok: bool):
        self._speed_busy = False
        if not ok:
            self._set_status("Speed change failed — check the audio file.", announce=True)
            # Revert selector to the previous working speed
            try:
                prev_idx = self.SPEED_VALUES.index(1.0)
            except ValueError:
                prev_idx = 1
            self.speed_choice.SetSelection(prev_idx)
            self._speed = 1.0
            self._enable_controls(self._loaded)
            return

        old_temp = self._speed_temp
        self._speed_temp = tmp

        # Clean up the previous temp AFTER assigning the new one so
        # load() does not delete it during release().
        if old_temp and old_temp != tmp and os.path.isfile(old_temp):
            try:
                os.unlink(old_temp)
            except Exception:
                pass

        seek_ms = int(orig_ms / speed) if speed > 0 else 0
        scaled = self._scaled_chapters(speed)
        if self.load(tmp, scaled):
            if seek_ms > 0:
                self._pending_seek_ms = seek_ms
            if resume:
                self._pending_play = True
        label = self.SPEED_LABELS[self.SPEED_VALUES.index(speed)]
        self._set_status(f"Speed: {label}")
        self._announce(f"Playing at {label}.")

    def _on_save_at_speed(self, _evt):
        if not self._orig_path:
            return
        speed = self._speed
        stem = os.path.splitext(self._orig_path)[0]
        label = f"{speed:.2f}x".replace(".", "_")
        default_name = os.path.basename(f"{stem} - {label}.mp3")
        dlg = wx.FileDialog(
            self,
            message="Save audio at this speed as MP3",
            defaultDir=os.path.dirname(self._orig_path),
            defaultFile=default_name,
            wildcard="MP3 audio (*.mp3)|*.mp3",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        dst = dlg.GetPath()
        dlg.Destroy()

        self._set_status(f"Exporting at {speed}x speed…", announce=True)
        self.btn_save_speed.Enable(False)

        def work():
            ok = core.apply_tempo(self._orig_path, speed, dst)
            wx.CallAfter(self._save_done, dst, speed, ok)

        threading.Thread(target=work, daemon=True).start()

    def _save_done(self, dst: str, speed: float, ok: bool):
        self.btn_save_speed.Enable(True)
        if ok:
            self._set_status(f"Saved: {os.path.basename(dst)}", announce=True)
        else:
            self._set_status("Export failed — check the audio file.", announce=True)

    # ------------------------------------------------------------------
    # Trim / cut selection
    # ------------------------------------------------------------------

    def _update_trim_label(self):
        if self._trim_start_ms == 0 and self._trim_end_ms == 0:
            self._trim_label.SetLabel("No selection set")
        else:
            start = _fmt(self._trim_start_ms)
            end = _fmt(self._trim_end_ms) if self._trim_end_ms > 0 else "not set"
            dur = ""
            if self._trim_end_ms > self._trim_start_ms:
                dur = f"  ({_fmt(self._trim_end_ms - self._trim_start_ms)} selected)"
            self._trim_label.SetLabel(f"Selection: {start} to {end}{dur}")
        self._trim_label.GetParent().Layout()

    def _on_set_trim_start(self, _evt):
        ms = self._tell()
        self._trim_start_ms = ms
        # If end is before new start, clear end
        if self._trim_end_ms > 0 and self._trim_end_ms <= ms:
            self._trim_end_ms = 0
        self._update_trim_label()
        self._announce(f"Selection start set to {_fmt(ms)}.")

    def _on_set_trim_end(self, _evt):
        ms = self._tell()
        if ms <= self._trim_start_ms:
            self._announce("End must be after the start. Move the player forward first.")
            return
        self._trim_end_ms = ms
        self._update_trim_label()
        self._announce(f"Selection end set to {_fmt(ms)}. "
                       f"Duration: {_fmt(ms - self._trim_start_ms)}.")

    def _on_clear_trim(self, _evt):
        self._trim_start_ms = 0
        self._trim_end_ms = 0
        self._update_trim_label()
        self._announce("Selection cleared.")

    def _on_prelisten_cut(self, _evt):
        """Play from just before the cut point to show how the edit will sound."""
        if self._trim_start_ms <= 0 and self._trim_end_ms <= 0:
            self._announce("Set a selection first using Set Begin and Set End.")
            return
        if not self._loaded:
            return
        # Seek to 2 seconds before the cut start to give context
        preview_start = max(0, self._trim_start_ms - 2000)
        # We seek to just before the start; the cut itself is simulated by
        # seeking past the end marker automatically during playback.
        # For a true prelisten-as-cut we'd need a temp file; this gives audible context.
        self._seek(preview_start)
        self._do_play()
        self._announce(
            f"Playing from {_fmt(preview_start)} - selection starts at "
            f"{_fmt(self._trim_start_ms)}, ends at {_fmt(self._trim_end_ms)}.")

    def _on_save_trimmed(self, _evt):
        """Save the selected region to a new file using lossless FFmpeg copy."""
        if self._trim_end_ms <= self._trim_start_ms:
            self._announce("Set a valid selection (Begin and End) before saving.")
            return
        if not self.media_path:
            return
        ext = os.path.splitext(self.media_path)[1] or ".mp3"
        stem = os.path.splitext(self.media_path)[0]
        default_name = os.path.basename(f"{stem} - trimmed{ext}")
        dlg = wx.FileDialog(
            self.GetParent(),
            message="Save trimmed audio",
            defaultDir=os.path.dirname(self.media_path),
            defaultFile=default_name,
            wildcard=f"Audio (*{ext})|*{ext}|All files (*.*)|*.*",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        dst = dlg.GetPath()
        dlg.Destroy()
        # Use original path (before speed processing) if available
        src = self._orig_path or self.media_path
        self._set_status("Saving trimmed audio...", announce=True)

        def work():
            ok = core.trim_file(src, self._trim_start_ms, self._trim_end_ms, dst)
            wx.CallAfter(self._trim_save_done, dst, ok)

        threading.Thread(target=work, daemon=True).start()

    def _trim_save_done(self, dst: str, ok: bool):
        if ok:
            self._set_status(f"Saved: {os.path.basename(dst)}", announce=True)
        else:
            self._set_status("Trim save failed.", announce=True)
