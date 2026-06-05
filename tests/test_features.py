"""Tests for the feature-expansion engine: M4B export, Podcasting 2.0 chapter
sidecars, silence auto-chaptering, reading existing chaptered files, in-place
editing, ``save_master_as`` and batch folder discovery/build.

Like ``test_core``, these synthesize small MP3s with ffmpeg and are skipped when
ffmpeg/ffprobe are not on PATH.
"""

import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chapterforge import core  # noqa: E402

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
HAVE_FFMPEG = (shutil.which("ffmpeg") is not None
               and shutil.which("ffprobe") is not None)

pytestmark = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg/ffprobe required")


def make_mp3(path, seconds, freq=440, sample_rate=44100, channels=2,
             bitrate="128k"):
    cmd = [
        "ffmpeg", "-hide_banner", "-nostdin", "-y", "-f", "lavfi", "-i",
        f"sine=frequency={freq}:duration={seconds}:sample_rate={sample_rate}",
        "-ac", str(channels), "-c:a", "libmp3lame", "-b:a", bitrate, path,
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   creationflags=CREATE_NO_WINDOW, check=True)


def make_book(folder, titles=("01 Intro", "02 Body", "03 End")):
    os.makedirs(folder, exist_ok=True)
    freqs = [300, 500, 700, 900, 1100]
    for i, title in enumerate(titles):
        make_mp3(os.path.join(folder, f"{title}.mp3"), 1,
                 freq=freqs[i % len(freqs)])
    items, _ = core.scan_folder_detailed(folder)
    good = [it for it in items if not it.error and it.duration > 0]
    core.apply_title_source(good, "filename", respect_edits=False)
    return good


# ---------------------------------------------------------------------------
# Output format helpers
# ---------------------------------------------------------------------------


def test_output_format_detection():
    assert core.output_format("x.mp3") == "mp3"
    assert core.output_format("x.MP3") == "mp3"
    assert core.output_format("x.m4b") == "m4b"
    assert core.output_format("x.m4a") == "m4b"
    assert core.output_format("x.mp4") == "m4b"


# ---------------------------------------------------------------------------
# M4B export + read-back
# ---------------------------------------------------------------------------


def test_build_m4b_roundtrip(tmp_path):
    good = make_book(str(tmp_path / "book"))
    out = str(tmp_path / "out.m4b")
    result = core.build_master(good, out, core.Tags(title="Audiobook",
                               artist="Author"),
                               chapters=core.compute_chapters(good))
    assert os.path.isfile(out)
    assert len(result.chapters) == 3
    tags, chapters, total = core.read_master(out)
    assert tags.title == "Audiobook"
    assert tags.artist == "Author"
    assert [c.title for c in chapters] == ["Intro", "Body", "End"]
    assert total > 0


# ---------------------------------------------------------------------------
# Podcasting 2.0 sidecar
# ---------------------------------------------------------------------------


def test_write_pod2_chapters(tmp_path):
    good = make_book(str(tmp_path / "book"))
    chapters = core.compute_chapters(good)
    out = str(tmp_path / "master.mp3")
    sidecar = core.write_pod2_chapters(out, chapters, chapters[-1].end_ms)
    assert os.path.isfile(sidecar)
    data = json.loads(open(sidecar, encoding="utf-8").read())
    assert "chapters" in data
    assert len(data["chapters"]) == 3
    assert data["chapters"][0]["title"] == "Intro"
    # startTime is in seconds, ascending.
    starts = [c["startTime"] for c in data["chapters"]]
    assert starts == sorted(starts)
    assert starts[0] == 0


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


def test_preflight_flags_mismatch(tmp_path):
    folder = str(tmp_path / "mixed")
    os.makedirs(folder)
    make_mp3(os.path.join(folder, "01.mp3"), 1, sample_rate=44100, channels=2)
    make_mp3(os.path.join(folder, "02.mp3"), 1, sample_rate=22050, channels=1)
    items, _ = core.scan_folder_detailed(folder)
    good = [it for it in items if not it.error and it.duration > 0]
    warnings = core.preflight(good)
    assert any("sample rate" in w.lower() or "channel" in w.lower()
               for w in warnings)


def test_preflight_uniform_is_clean(tmp_path):
    good = make_book(str(tmp_path / "book"))
    assert core.preflight(good) == []


# ---------------------------------------------------------------------------
# Silence detection
# ---------------------------------------------------------------------------


def test_detect_silence_chapters(tmp_path):
    # tone - silence - tone - silence - tone, gaps long enough to split on.
    folder = tmp_path / "s"
    folder.mkdir()
    parts = []
    for i, freq in enumerate((300, 600, 900)):
        p = str(folder / f"tone{i}.mp3")
        make_mp3(p, 1.2, freq=freq)
        parts.append(p)
        if i < 2:
            sil = str(folder / f"sil{i}.mp3")
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-f", "lavfi",
                 "-i", "anullsrc=r=44100:cl=stereo", "-t", "1.2",
                 "-c:a", "libmp3lame", "-b:a", "128k", sil],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW, check=True)
            parts.append(sil)
    joined = str(folder / "joined.mp3")
    list_file = str(folder / "list.txt")
    with open(list_file, "w", encoding="utf-8") as fh:
        for p in parts:
            fh.write(f"file '{p}'\n")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-f", "concat", "-safe",
         "0", "-i", list_file, "-c", "copy", joined],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW, check=True)
    chapters = core.detect_silence_chapters(joined, noise_db=-30.0,
                                            min_silence=0.4,
                                            min_chapter_ms=500)
    assert len(chapters) >= 2
    assert chapters[0].start_ms == 0
    starts = [c.start_ms for c in chapters]
    assert starts == sorted(starts)


# ---------------------------------------------------------------------------
# In-place edit + save_master_as
# ---------------------------------------------------------------------------


def test_save_tags_chapters_inplace(tmp_path):
    good = make_book(str(tmp_path / "book"))
    out = str(tmp_path / "m.mp3")
    core.build_master(good, out, core.Tags(title="Orig"),
                      chapters=core.compute_chapters(good))
    _, chapters, _ = core.read_master(out)
    for c in chapters:
        c.title = "Z-" + c.title
    core.save_tags_chapters_inplace(out, chapters, core.Tags(title="New",
                                    artist="A"))
    tags2, chapters2, _ = core.read_master(out)
    assert tags2.title == "New"
    assert tags2.artist == "A"
    assert [c.title for c in chapters2] == ["Z-Intro", "Z-Body", "Z-End"]


def test_save_tags_chapters_inplace_rejects_m4b(tmp_path):
    good = make_book(str(tmp_path / "book"))
    out = str(tmp_path / "m.m4b")
    core.build_master(good, out, core.Tags(title="Orig"),
                      chapters=core.compute_chapters(good))
    _, chapters, _ = core.read_master(out)
    with pytest.raises(core.ChapterForgeError):
        core.save_tags_chapters_inplace(out, chapters, core.Tags(title="x"))


def test_save_master_as_mp3(tmp_path):
    good = make_book(str(tmp_path / "book"))
    src = str(tmp_path / "src.mp3")
    core.build_master(good, src, core.Tags(title="Src"),
                      chapters=core.compute_chapters(good))
    _, chapters, _ = core.read_master(src)
    for c in chapters:
        c.title = "C-" + c.title
    dest = str(tmp_path / "dest.mp3")
    core.save_master_as(src, dest, chapters, core.Tags(title="Dest"))
    assert os.path.isfile(src)  # original untouched
    tags, chapters2, _ = core.read_master(dest)
    assert tags.title == "Dest"
    assert chapters2[0].title == "C-Intro"


def test_save_master_as_m4b(tmp_path):
    good = make_book(str(tmp_path / "book"))
    src = str(tmp_path / "src.mp3")
    core.build_master(good, src, core.Tags(title="Src"),
                      chapters=core.compute_chapters(good))
    _, chapters, _ = core.read_master(src)
    dest = str(tmp_path / "dest.m4b")
    core.save_master_as(src, dest, chapters, core.Tags(title="Booky"))
    tags, chapters2, total = core.read_master(dest)
    assert tags.title == "Booky"
    assert len(chapters2) == 3
    assert total > 0


# ---------------------------------------------------------------------------
# Per-chapter url/img propagation through the sidecar
# ---------------------------------------------------------------------------


def test_chapter_url_img_in_sidecar(tmp_path):
    good = make_book(str(tmp_path / "book"))
    good[0].url = "https://example.com/1"
    good[1].img = "https://example.com/cover.jpg"
    chapters = core.compute_chapters(good)
    assert chapters[0].url == "https://example.com/1"
    assert chapters[1].img == "https://example.com/cover.jpg"
    out = str(tmp_path / "m.mp3")
    sidecar = core.write_pod2_chapters(out, chapters, chapters[-1].end_ms)
    data = json.loads(open(sidecar, encoding="utf-8").read())
    assert data["chapters"][0].get("url") == "https://example.com/1"
    assert data["chapters"][1].get("img") == "https://example.com/cover.jpg"


# ---------------------------------------------------------------------------
# Batch discovery + build
# ---------------------------------------------------------------------------


def test_find_book_folders(tmp_path):
    parent = tmp_path / "library"
    parent.mkdir()
    make_book(str(parent / "Book One"))
    make_book(str(parent / "Book Two"))
    (parent / "_ChapterForge").mkdir()  # output folder, should be skipped
    (parent / "empty").mkdir()
    folders = core.find_book_folders(str(parent))
    names = sorted(os.path.basename(f) for f in folders)
    assert names == ["Book One", "Book Two"]


def test_build_folder(tmp_path):
    folder = str(tmp_path / "A Book")
    make_book(folder)
    result = core.build_folder(folder, ext=".mp3", write_pod2=True)
    assert os.path.isfile(result.output_path)
    assert len(result.chapters) == 3
    # pod2 sidecar written alongside.
    stem = os.path.splitext(result.output_path)[0]
    assert os.path.isfile(core.pod2_sidecar_path(result.output_path)) or \
        os.path.isfile(stem + ".chapters.json")
