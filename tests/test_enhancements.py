"""Tests for the v1.2 enhancement helpers: inter-chapter gaps, output size
estimate, post-build verification, chapter list import/export, and the
merge/split/adjust chapter-editing operations.

The chapter-editing, label I/O and estimate tests are pure (no ffmpeg); the
gap-build and verify tests synthesize MP3s and are skipped without ffmpeg.
"""

import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chapterforge import core  # noqa: E402
from chapterforge.core import Chapter, Mp3Item, Tags  # noqa: E402

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
HAVE_FFMPEG = (shutil.which("ffmpeg") is not None
               and shutil.which("ffprobe") is not None)


def make_chapters(*spans):
    """spans: (start_ms, end_ms, title) tuples."""
    return [Chapter(index=i, title=t, start_ms=s, end_ms=e)
            for i, (s, e, t) in enumerate(spans)]


# ---------------------------------------------------------------------------
# Estimate + gap timeline (pure)
# ---------------------------------------------------------------------------


def test_merge_last_of_two():
    chs = make_chapters((0, 1000, "A"), (1000, 2000, "B"))
    out = core.merge_chapter(chs, 1)
    assert [c.title for c in out] == ["A"]
    assert out[0].start_ms == 0 and out[0].end_ms == 2000


def test_gap_requires_parallel_chapters():
    items = [Mp3Item(path=f"{i}.mp3", title=f"t{i}", duration=5.0)
             for i in range(3)]
    mismatched = make_chapters((0, 5000, "A"), (5000, 10000, "B"))
    with pytest.raises(core.ChapterForgeError):
        core.build_mp3(items, "out.mp3", Tags(), chapters=mismatched,
                       gap_ms=1000)


def test_estimate_output_with_gap():
    items = [Mp3Item(path=f"{i}.mp3", title=f"t{i}", duration=10.0)
             for i in range(3)]
    total_ms, est_bytes = core.estimate_output(items, bitrate="192k",
                                               gap_ms=2000)
    # 3 x 10s + 2 gaps x 2s = 34s
    assert total_ms == 34000
    assert est_bytes == int(192 * 1000 / 8 * 34.0)


def test_format_size():
    assert core.format_size(512) == "512 bytes"
    assert core.format_size(1536).endswith("KB")
    assert core.format_size(5 * 1024 * 1024).endswith("MB")


def test_chapters_with_gaps_preserves_titles():
    items = [Mp3Item(path=f"{i}.mp3", title=f"orig{i}", duration=5.0)
             for i in range(3)]
    base = make_chapters((0, 5000, "Edited A"), (5000, 10000, "Edited B"),
                         (10000, 15000, "Edited C"))
    chs = core._chapters_with_gaps(items, 1000, base=base)
    assert [c.title for c in chs] == ["Edited A", "Edited B", "Edited C"]
    assert chs[0].start_ms == 0 and chs[0].end_ms == 5000
    assert chs[1].start_ms == 6000 and chs[1].end_ms == 11000
    assert chs[2].start_ms == 12000 and chs[2].end_ms == 17000


# ---------------------------------------------------------------------------
# Edit operations: merge / split / adjust (pure)
# ---------------------------------------------------------------------------


def test_merge_middle_into_previous():
    chs = make_chapters((0, 1000, "A"), (1000, 2000, "B"), (2000, 3000, "C"))
    out = core.merge_chapter(chs, 1)
    assert [c.title for c in out] == ["A", "C"]
    assert out[0].start_ms == 0 and out[0].end_ms == 2000
    assert out[1].start_ms == 2000 and out[1].end_ms == 3000
    assert [c.index for c in out] == [0, 1]


def test_merge_first_into_second():
    chs = make_chapters((0, 1000, "A"), (1000, 2000, "B"))
    out = core.merge_chapter(chs, 0)
    assert [c.title for c in out] == ["A"]
    assert out[0].start_ms == 0 and out[0].end_ms == 2000


def test_merge_requires_two():
    with pytest.raises(core.ChapterForgeError):
        core.merge_chapter(make_chapters((0, 1000, "A")), 0)


def test_split_chapter():
    chs = make_chapters((0, 10000, "A"), (10000, 20000, "B"))
    out = core.split_chapter(chs, 5000, title="A2")
    assert [c.title for c in out] == ["A", "A2", "B"]
    assert out[0].end_ms == 5000
    assert out[1].start_ms == 5000 and out[1].end_ms == 10000
    assert [c.index for c in out] == [0, 1, 2]


def test_split_rejects_boundary():
    chs = make_chapters((0, 10000, "A"))
    with pytest.raises(core.ChapterForgeError):
        core.split_chapter(chs, 500)  # too close to start
    with pytest.raises(core.ChapterForgeError):
        core.split_chapter(chs, 99999)  # outside


def test_set_chapter_start():
    chs = make_chapters((0, 10000, "A"), (10000, 20000, "B"))
    out = core.set_chapter_start(chs, 1, 8000)
    assert out[0].end_ms == 8000
    assert out[1].start_ms == 8000 and out[1].end_ms == 20000


def test_set_chapter_start_validates():
    chs = make_chapters((0, 10000, "A"), (10000, 20000, "B"))
    with pytest.raises(core.ChapterForgeError):
        core.set_chapter_start(chs, 0, 1000)  # first chapter
    with pytest.raises(core.ChapterForgeError):
        core.set_chapter_start(chs, 1, 25000)  # out of range


# ---------------------------------------------------------------------------
# Chapter list import / export (pure)
# ---------------------------------------------------------------------------


def test_export_import_audacity_roundtrip(tmp_path):
    chs = make_chapters((0, 5000, "Intro"), (5000, 12000, "Body"),
                        (12000, 20000, "End"))
    p = str(tmp_path / "labels.txt")
    core.export_chapter_labels(p, chs, "audacity")
    with open(p, encoding="utf-8") as fh:
        parsed = core.parse_chapter_text(fh.read(), 20000)
    assert [c.title for c in parsed] == ["Intro", "Body", "End"]
    assert [c.start_ms for c in parsed] == [0, 5000, 12000]
    assert parsed[-1].end_ms == 20000


def test_import_timestamps():
    text = "0:00 Intro\n0:05 Body\n0:12 - End\n"
    parsed = core.parse_chapter_text(text, 20000)
    assert [c.title for c in parsed] == ["Intro", "Body", "End"]
    assert [c.start_ms for c in parsed] == [0, 5000, 12000]


def test_import_cue(tmp_path):
    chs = make_chapters((0, 5000, "One"), (5000, 10000, "Two"))
    p = str(tmp_path / "list.cue")
    core.export_chapter_labels(p, chs, "cue", audio_filename="master.mp3",
                               tags=Tags(artist="Me", album="Book"))
    with open(p, encoding="utf-8") as fh:
        parsed = core.parse_chapter_text(fh.read(), 10000)
    assert [c.title for c in parsed] == ["One", "Two"]
    assert parsed[0].start_ms == 0
    assert parsed[1].start_ms == 5000


def test_import_inserts_leading_chapter():
    parsed = core.parse_chapter_text("0:05 Later\n", 20000)
    assert parsed[0].start_ms == 0
    assert parsed[1].start_ms == 5000


def test_import_empty_raises():
    with pytest.raises(core.ChapterForgeError):
        core.parse_chapter_text("nothing here\n", 10000)


# ---------------------------------------------------------------------------
# Gap build + verify (need ffmpeg)
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg/ffprobe required")


def _make_mp3(path, seconds, freq=440):
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-f", "lavfi", "-i",
           f"sine=frequency={freq}:duration={seconds}:sample_rate=44100",
           "-ac", "2", "-c:a", "libmp3lame", "-b:a", "128k", path]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   creationflags=CREATE_NO_WINDOW, check=True)


def test_build_with_gap_and_verify(tmp_path):
    folder = str(tmp_path / "book")
    os.makedirs(folder)
    for i, freq in enumerate((300, 500, 700)):
        _make_mp3(os.path.join(folder, f"0{i + 1} Track.mp3"), 2, freq=freq)
    items, _ = core.scan_folder_detailed(folder)
    good = [it for it in items if not it.error and it.duration > 0]
    core.apply_title_source(good, "filename", respect_edits=False)
    out = str(tmp_path / "master.mp3")
    result = core.build_master(good, out, Tags(title="Gapped"), gap_ms=1000)
    # 3 x ~2s + 2 x 1s gap ~= 8s
    assert result.total_ms >= 7000
    assert result.reencoded is True
    ok, n, total_ms, issues = core.verify_output(out, expected_n=3)
    assert ok, issues
    assert n == 3
