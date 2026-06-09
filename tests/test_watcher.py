"""Tests for the job-file (.cfjob) parser and the background watch engine."""

import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chapterforge import core, manifest as manifest_mod, watcher as watcher_mod  # noqa: E402
from chapterforge.watcher_config import OUTPUT_SUBDIR, Process, sanitize_filename  # noqa: E402

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
pytestmark = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg/ffprobe required")


def make_mp3(path, seconds=1, freq=440, sample_rate=44100, channels=2):
    subprocess.run([
        "ffmpeg", "-hide_banner", "-nostdin", "-y", "-f", "lavfi", "-i",
        f"sine=frequency={freq}:duration={seconds}:sample_rate={sample_rate}",
        "-ac", str(channels), "-c:a", "libmp3lame", "-b:a", "128k", path,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
       creationflags=CREATE_NO_WINDOW, check=True)


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def test_manifest_round_trip(tmp_path):
    items = [
        core.Mp3Item(str(tmp_path / "a.mp3"), "Alpha", 1.0),
        core.Mp3Item(str(tmp_path / "b.mp3"), "Beta", 1.0),
    ]
    tags = core.Tags(title="T", artist="Ar", album="Al", genre="G", year="2024")
    job = str(tmp_path / "chapters.cfjob")
    manifest_mod.write_manifest(job, items, tags, output_name="Out.mp3",
                                bitrate="256k", normalize=True)
    m = manifest_mod.read_manifest(job)
    assert [t.filename for t in m.tracks] == ["a.mp3", "b.mp3"]
    assert [t.title for t in m.tracks] == ["Alpha", "Beta"]
    assert m.options["title"] == "T"
    assert m.options["output"] == "Out.mp3"
    assert m.bitrate == "256k"
    assert m.normalize is True


def test_manifest_resolve_reports_missing(tmp_path):
    make_mp3(str(tmp_path / "a.mp3"))
    job = tmp_path / "chapters.cfjob"
    job.write_text("a.mp3 | A\nmissing.mp3 | B\n", encoding="utf-8")
    m = manifest_mod.read_manifest(str(job))
    resolved, missing = manifest_mod.resolve_manifest(m, str(tmp_path))
    assert len(resolved) == 1
    assert missing == ["missing.mp3"]


def test_manifest_rejects_absolute_and_escape(tmp_path):
    job = tmp_path / "chapters.cfjob"
    job.write_text("C:/evil.mp3 | A\n../outside.mp3 | B\n", encoding="utf-8")
    m = manifest_mod.read_manifest(str(job))
    resolved, missing = manifest_mod.resolve_manifest(m, str(tmp_path))
    assert resolved == []
    assert len(missing) == 2


def test_sanitize_filename():
    assert sanitize_filename('a:b/c?.mp3') == "a_b_c_.mp3"
    assert sanitize_filename("") == "Master"
    assert sanitize_filename("CON") == "Master"


# ---------------------------------------------------------------------------
# Watcher
# ---------------------------------------------------------------------------


def _run_until_processed(watcher, max_polls=5):
    events = []
    watcher.on_event = events.append
    for _ in range(max_polls):
        watcher._poll_once()
        if any(e.kind in ("done", "failed") for e in events):
            break
    return events


def test_watcher_builds_stable_folder(tmp_path):
    watch = tmp_path / "watch"
    book = watch / "Book One"
    book.mkdir(parents=True)
    make_mp3(str(book / "01 - Intro.mp3"), 1)
    make_mp3(str(book / "02 - End.mp3"), 1)

    proc = Process(name="T", watch_folder=str(watch), enabled=True)
    w = watcher_mod.FolderWatcher(provider=lambda: [proc], settle_seconds=0)
    events = _run_until_processed(w)

    kinds = [e.kind for e in events]
    assert "started" in kinds and "done" in kinds
    done = [e for e in events if e.kind == "done"][0]
    assert os.path.isfile(done.output_path)
    assert OUTPUT_SUBDIR in done.output_path
    assert "Completed" in done.output_path
    assert os.path.isfile(str(book / watcher_mod.DONE_MARKER))
    # A readable chapter report is written next to the master.
    assert os.path.isfile(core_report := core.chapter_report_path(done.output_path))
    assert "ChapterForge" in open(core_report, encoding="utf-8").read()

    # A subsequent poll must NOT reprocess (one-shot via marker).
    more = []
    w.on_event = more.append
    w._poll_once()
    assert not more


def test_watcher_honours_cfjob_order(tmp_path):
    watch = tmp_path / "watch"
    book = watch / "Ordered"
    book.mkdir(parents=True)
    make_mp3(str(book / "a.mp3"), 1)
    make_mp3(str(book / "b.mp3"), 2)
    (book / "chapters.cfjob").write_text(
        "@title = Ordered Book\nb.mp3 | Second\na.mp3 | First\n", encoding="utf-8")

    proc = Process(name="T", watch_folder=str(watch), enabled=True)
    w = watcher_mod.FolderWatcher(provider=lambda: [proc], settle_seconds=0)
    events = _run_until_processed(w)
    done = [e for e in events if e.kind == "done"]
    assert done, [e.message for e in events]

    from mutagen.id3 import ID3
    chaps = ID3(done[0].output_path).getall("CHAP")
    chaps.sort(key=lambda c: c.start_time)
    titles = [c.sub_frames["TIT2"].text[0] for c in chaps]
    assert titles == ["Second", "First"]


def test_watcher_fails_on_missing_cfjob_file(tmp_path):
    watch = tmp_path / "watch"
    book = watch / "Broken"
    book.mkdir(parents=True)
    make_mp3(str(book / "a.mp3"), 1)
    (book / "chapters.cfjob").write_text("a.mp3 | A\nghost.mp3 | B\n", encoding="utf-8")

    proc = Process(name="T", watch_folder=str(watch), enabled=True)
    w = watcher_mod.FolderWatcher(provider=lambda: [proc], settle_seconds=0)
    events = _run_until_processed(w)
    assert any(e.kind == "failed" for e in events)
    assert os.path.isfile(str(book / watcher_mod.FAIL_MARKER))
    # A visible failure note is written under _ChapterForge\Failed.
    failed_note = os.path.join(str(watch), OUTPUT_SUBDIR, "Failed", "Broken.txt")
    assert os.path.isfile(failed_note)


def test_watcher_waits_for_stability(tmp_path):
    watch = tmp_path / "watch"
    book = watch / "Growing"
    book.mkdir(parents=True)
    make_mp3(str(book / "a.mp3"), 1)

    proc = Process(name="T", watch_folder=str(watch), enabled=True)
    # Large settle so it never becomes stable during the test.
    w = watcher_mod.FolderWatcher(provider=lambda: [proc], settle_seconds=3600)
    events = []
    w.on_event = events.append
    w._poll_once()
    w._poll_once()
    assert not events  # not yet stable -> nothing built


def test_watcher_waits_for_cloud_placeholder_files(tmp_path, monkeypatch):
    """A OneDrive/Dropbox/Google Drive "online-only" placeholder must not be
    mistaken for a ready source - the watcher should report that it's waiting
    and build only once every file is fully downloaded."""
    watch = tmp_path / "watch"
    book = watch / "Cloud Book"
    book.mkdir(parents=True)
    placeholder = book / "01 - Intro.mp3"
    make_mp3(str(placeholder), 1)
    make_mp3(str(book / "02 - End.mp3"), 1)

    placeholder_path = str(placeholder)
    real_is_placeholder = watcher_mod.is_cloud_placeholder
    cloud_only = {"value": True}
    monkeypatch.setattr(
        watcher_mod, "is_cloud_placeholder",
        lambda p: cloud_only["value"] if p == placeholder_path else real_is_placeholder(p))

    proc = Process(name="T", watch_folder=str(watch), enabled=True)
    w = watcher_mod.FolderWatcher(provider=lambda: [proc], settle_seconds=0)
    events = []
    w.on_event = events.append
    w._poll_once()
    w._poll_once()

    kinds = [e.kind for e in events]
    assert "waiting" in kinds
    assert "started" not in kinds and "done" not in kinds
    assert not os.path.isfile(str(book / watcher_mod.DONE_MARKER))

    # Once the file finishes "downloading", the next poll builds normally.
    cloud_only["value"] = False
    events2 = _run_until_processed(w)
    assert "done" in [e.kind for e in events2]
    assert os.path.isfile(str(book / watcher_mod.DONE_MARKER))


def test_is_cloud_placeholder_false_for_normal_file(tmp_path):
    f = tmp_path / "normal.mp3"
    f.write_bytes(b"not really mp3 data")
    assert watcher_mod.is_cloud_placeholder(str(f)) is False
    assert watcher_mod.is_cloud_placeholder(str(tmp_path / "missing.mp3")) is False
