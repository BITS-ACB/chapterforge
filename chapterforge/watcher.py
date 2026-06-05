"""Background watch-folder engine for ChapterForge.

A lightweight polling watcher (no extra dependencies) that detects new, *stable*
sub-folders of MP3s inside each enabled process's watch folder and builds a
master automatically. Designed to be safe (see the rubber-duck-driven notes
below) rather than clever:

* **Stability** - a folder is only built once its source set
  ``(count, total size, newest mtime)`` has been unchanged for ``settle``
  seconds *and* no source file was modified within the last ``settle`` seconds.
  The settle timer resets whenever the set changes, so a paused copy can't be
  grabbed early.
* **No re-trigger loops** - generated masters are written into an excluded
  ``_ChapterForge`` sub-folder, the resolved output path is excluded from
  scans, and a ``.chapterforge_done`` marker makes a folder one-shot.
* **No double processing** - a ``.chapterforge_processing`` lock is created
  atomically (``O_CREAT|O_EXCL``); stale locks are stolen after an hour.
* **Failure backoff** - a failed folder records ``.chapterforge_failed`` and is
  retried only after its source signature changes.

All wx work belongs to the host: the watcher only calls the ``on_event``
callback with plain :class:`WatchEvent` data.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from . import core, manifest as manifest_mod
from .watcher_config import (
    OUTPUT_SUBDIR,
    Process,
    expand_template,
    load_processes,
    sanitize_filename,
)

DONE_MARKER = ".chapterforge_done"
FAIL_MARKER = ".chapterforge_failed"
LOCK_MARKER = ".chapterforge_processing"
STALE_LOCK_SECONDS = 3600


@dataclass
class WatchEvent:
    kind: str           # 'started' | 'done' | 'failed' | 'error'
    process_name: str
    folder: str
    message: str = ""
    output_path: str = ""


Signature = Tuple[int, int, float]
ProcessProvider = Callable[[], List[Process]]
EventHandler = Callable[[WatchEvent], None]


def _source_mp3s(subfolder: str, output_path: str) -> List[str]:
    out = os.path.abspath(output_path)
    files = []
    try:
        for name in os.listdir(subfolder):
            if not name.lower().endswith(".mp3"):
                continue
            full = os.path.join(subfolder, name)
            if not os.path.isfile(full):
                continue
            if os.path.abspath(full) == out:
                continue
            files.append(full)
    except OSError:
        return []
    files.sort(key=lambda p: core.natural_key(os.path.basename(p)))
    return files


def _signature(paths: List[str]) -> Signature:
    count = len(paths)
    total = 0
    newest = 0.0
    for p in paths:
        try:
            st = os.stat(p)
        except OSError:
            continue
        total += st.st_size
        newest = max(newest, st.st_mtime)
    return (count, total, newest)


def _read_marker_signature(path: str) -> Optional[list]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        sig = data.get("signature")
        return list(sig) if isinstance(sig, list) else None
    except (OSError, ValueError):
        return None


def _write_marker(path: str, payload: dict) -> None:
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(tmp, path)
    except OSError:
        pass


class FolderWatcher:
    def __init__(self, on_event: Optional[EventHandler] = None,
                 provider: Optional[ProcessProvider] = None,
                 poll_seconds: float = 5.0, settle_seconds: float = 15.0) -> None:
        self.on_event = on_event
        self.provider = provider or load_processes
        self.poll_seconds = poll_seconds
        self.settle_seconds = settle_seconds
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._canceller: Optional[core.Canceller] = None
        # folder -> (signature, last_change_monotonic)
        self._pending: Dict[str, Tuple[Signature, float]] = {}

    # -- lifecycle ------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="cf-watcher",
                                        daemon=True)
        self._thread.start()

    def stop(self, join: bool = True, timeout: float = 10.0) -> None:
        self._stop.set()
        if self._canceller:
            self._canceller.cancel()
        if join and self._thread:
            self._thread.join(timeout=timeout)

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- main loop ------------------------------------------------------
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._poll_once()
            except Exception as exc:  # never let the loop die
                self._emit(WatchEvent("error", "", "", str(exc)))
            self._stop.wait(self.poll_seconds)

    def _poll_once(self) -> None:
        for process in self.provider():
            if self._stop.is_set():
                return
            if not process.enabled or not process.watch_folder:
                continue
            if not os.path.isdir(process.watch_folder):
                continue
            for sub in self._subfolders(process.watch_folder):
                if self._stop.is_set():
                    return
                self._consider(process, sub)

    def _subfolders(self, watch_folder: str) -> List[str]:
        out = []
        try:
            for name in os.listdir(watch_folder):
                if name == OUTPUT_SUBDIR or name.startswith("."):
                    continue
                full = os.path.join(watch_folder, name)
                if os.path.isdir(full):
                    out.append(full)
        except OSError:
            return []
        return out

    def _consider(self, process: Process, subfolder: str) -> None:
        output_path = self._output_path(process, subfolder)
        sources = _source_mp3s(subfolder, output_path)
        if not sources:
            self._pending.pop(subfolder, None)
            return

        sig = _signature(sources)

        done_path = os.path.join(subfolder, DONE_MARKER)
        if os.path.isfile(done_path):
            return  # already built; one-shot

        fail_path = os.path.join(subfolder, FAIL_MARKER)
        if os.path.isfile(fail_path):
            # Retry only if the source signature changed since the failure.
            if _read_marker_signature(fail_path) == list(sig):
                return

        # Stability tracking: reset the settle timer whenever the set changes.
        now = time.monotonic()
        prev = self._pending.get(subfolder)
        if prev is None or prev[0] != sig:
            self._pending[subfolder] = (sig, now)
            return
        if now - prev[1] < self.settle_seconds:
            return
        # Also require that nothing was touched within the settle window.
        if time.time() - sig[2] < self.settle_seconds:
            return

        self._process(process, subfolder, sources, output_path, sig)

    # -- processing -----------------------------------------------------
    def _output_path(self, process: Process, subfolder: str) -> str:
        folder_name = os.path.basename(os.path.normpath(subfolder))
        out_name = sanitize_filename(
            expand_template(process.output_template, folder=folder_name,
                            parent=os.path.basename(os.path.normpath(process.watch_folder))),
            fallback=f"{folder_name} - Master")
        if not out_name.lower().endswith(".mp3"):
            out_name += ".mp3"
        # Collect every result under a single, visible "_ChapterForge\Completed"
        # area at the watch-folder level, one sub-folder per book, so a user can
        # see at a glance what has been produced.
        return os.path.join(process.watch_folder, OUTPUT_SUBDIR, "Completed",
                            folder_name, out_name)

    def _acquire_lock(self, subfolder: str) -> Optional[str]:
        lock_path = os.path.join(subfolder, LOCK_MARKER)
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(time.time()).encode("ascii"))
            os.close(fd)
            return lock_path
        except FileExistsError:
            try:
                age = time.time() - os.path.getmtime(lock_path)
                if age > STALE_LOCK_SECONDS:
                    os.remove(lock_path)
                    return self._acquire_lock(subfolder)
            except OSError:
                pass
            return None
        except OSError:
            return None

    def _process(self, process: Process, subfolder: str, sources: List[str],
                 output_path: str, sig: Signature) -> None:
        lock_path = self._acquire_lock(subfolder)
        if lock_path is None:
            return

        folder_name = os.path.basename(os.path.normpath(subfolder))
        self._pending.pop(subfolder, None)
        self._emit(WatchEvent("started", process.name, subfolder,
                              f"Processing “{folder_name}”…"))
        self._canceller = core.Canceller()
        try:
            items, tags, bitrate, normalize = self._plan(process, subfolder,
                                                          sources, output_path)
            chapters = core.compute_chapters(items)
            result = core.build_master(
                items, output_path, tags, chapters=chapters, bitrate=bitrate,
                normalize=normalize, canceller=self._canceller)
            try:
                core.write_chapter_report(output_path, result, tags, items)
            except OSError:
                pass
            self._clear_marker(os.path.join(subfolder, FAIL_MARKER))
            self._clear_failed_note(process, folder_name)
            _write_marker(os.path.join(subfolder, DONE_MARKER), {
                "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "output": result.output_path,
                "chapters": len(result.chapters),
                "duration": core.format_timestamp(result.total_ms),
                "signature": list(sig),
            })
            self._emit(WatchEvent(
                "done", process.name, subfolder,
                f"Built “{folder_name}”: {len(result.chapters)} chapters, "
                f"{core.format_timestamp(result.total_ms)}.",
                output_path=result.output_path))
        except core.BuildCancelled:
            self._cleanup_partial(output_path)
        except Exception as exc:
            self._cleanup_partial(output_path)
            _write_marker(os.path.join(subfolder, FAIL_MARKER), {
                "failed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "error": str(exc),
                "signature": list(sig),
            })
            self._write_failed_note(process, folder_name, str(exc))
            self._emit(WatchEvent("failed", process.name, subfolder,
                                  f"Failed “{folder_name}”: {exc}"))
        finally:
            self._canceller = None
            self._clear_marker(lock_path)

    def _failed_note_path(self, process: Process, folder_name: str) -> str:
        return os.path.join(process.watch_folder, OUTPUT_SUBDIR, "Failed",
                            f"{sanitize_filename(folder_name)}.txt")

    def _write_failed_note(self, process: Process, folder_name: str,
                           error: str) -> None:
        path = self._failed_note_path(process, folder_name)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(f"ChapterForge could not build “{folder_name}”.\n"
                         f"Time : {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                         f"Error: {error}\n")
        except OSError:
            pass

    def _clear_failed_note(self, process: Process, folder_name: str) -> None:
        try:
            path = self._failed_note_path(process, folder_name)
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    def _plan(self, process: Process, subfolder: str, sources: List[str],
              output_path: str):
        """Decide items + tags, honouring a .cfjob if present."""
        folder_name = os.path.basename(os.path.normpath(subfolder))
        job_path = manifest_mod.find_job_file(subfolder)
        if job_path:
            manifest = manifest_mod.read_manifest(job_path)
            entries, missing = manifest_mod.resolve_manifest(manifest, subfolder)
            if missing:
                raise core.ChapterForgeError(
                    "Job file references missing files: " + ", ".join(missing[:5]))
            if not entries:
                raise core.ChapterForgeError("Job file lists no usable tracks.")
            items = core.items_from_entries(entries)
            tags = manifest_mod.manifest_tags(manifest, subfolder)
            bitrate = manifest.bitrate
            normalize = manifest.normalize
        else:
            items = [core.probe_file(p) for p in sources]
            core.apply_title_source(items, process.title_source, respect_edits=False)
            tags = core.Tags(
                title=expand_template(process.title_template, folder=folder_name),
                album=expand_template(process.album_template, folder=folder_name),
                artist=process.artist,
                album_artist=process.album_artist,
                genre=process.genre,
            )
            bitrate = process.bitrate
            normalize = process.normalize

        bad = [it for it in items if it.error or it.duration <= 0]
        if bad:
            raise core.ChapterForgeError(
                "Unreadable files: " + ", ".join(it.filename for it in bad[:5]))
        return items, tags, bitrate, normalize

    # -- helpers --------------------------------------------------------
    def _cleanup_partial(self, output_path: str) -> None:
        # build_master already removes its own temp file; ensure no stray output.
        try:
            if os.path.exists(output_path) and os.path.getsize(output_path) == 0:
                os.remove(output_path)
        except OSError:
            pass

    def _clear_marker(self, path: Optional[str]) -> None:
        if not path:
            return
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    def _emit(self, event: WatchEvent) -> None:
        if self.on_event:
            try:
                self.on_event(event)
            except Exception:
                pass
