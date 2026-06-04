"""Tests for chapterforge.core.

These generate small synthetic MP3 files with ffmpeg (sine tones) and exercise
the scan -> compute -> build -> read-back pipeline, including the lossless
`-c copy` path, the re-encode path (mismatched sample rates), unicode titles
and chapter read-back via mutagen.
"""

import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chapterforge import core  # noqa: E402
from mutagen.id3 import ID3, CHAP, CTOC  # noqa: E402

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

pytestmark = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg/ffprobe required")


def make_mp3(path, seconds, freq=440, sample_rate=44100, channels=2, bitrate="128k"):
    cmd = [
        "ffmpeg", "-hide_banner", "-nostdin", "-y",
        "-f", "lavfi", "-i",
        f"sine=frequency={freq}:duration={seconds}:sample_rate={sample_rate}",
        "-ac", str(channels), "-c:a", "libmp3lame", "-b:a", bitrate,
        path,
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   creationflags=CREATE_NO_WINDOW, check=True)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_natural_key_orders_numerically():
    names = ["track10.mp3", "track2.mp3", "track1.mp3"]
    names.sort(key=core.natural_key)
    assert names == ["track1.mp3", "track2.mp3", "track10.mp3"]


def test_title_from_filename_strips_track_prefix():
    assert core.title_from_filename("01 - The Beginning.mp3") == "The Beginning"
    assert core.title_from_filename("02_Another_One.mp3") == "Another One"
    assert core.title_from_filename("Plain Name.mp3") == "Plain Name"


def test_format_timestamp():
    assert core.format_timestamp(0) == "0:00"
    assert core.format_timestamp(65_000) == "1:05"
    assert core.format_timestamp(3_725_000) == "1:02:05"


def test_compute_chapters_are_contiguous():
    items = [
        core.Mp3Item("a.mp3", "A", 1.0),
        core.Mp3Item("b.mp3", "B", 2.0),
        core.Mp3Item("c.mp3", "C", 0.5),
    ]
    chapters = core.compute_chapters(items)
    assert [c.start_ms for c in chapters] == [0, 1000, 3000]
    assert [c.end_ms for c in chapters] == [1000, 3000, 3500]
    for a, b in zip(chapters, chapters[1:]):
        assert a.end_ms == b.start_ms


def test_suggested_output_path(tmp_path):
    folder = tmp_path / "My Book"
    folder.mkdir()
    out = core.suggested_output_path(str(folder))
    assert out.endswith("My Book - Master.mp3")


def test_is_probable_master():
    folder = r"C:\Audiobooks\My Book"
    assert core.is_probable_master("My Book.mp3", folder)
    assert core.is_probable_master("My Book - Master.mp3", folder)
    assert core.is_probable_master("Anything - Master.mp3", folder)
    assert not core.is_probable_master("01 Chapter One.mp3", folder)
    assert not core.is_probable_master("My Book Notes.mp3", folder)


def test_chapter_report_path():
    p = core.chapter_report_path(r"C:\out\Book - Master.mp3")
    assert p.endswith("Book - Master - chapters.txt")


def test_write_chapter_report(tmp_path):
    chapters = [core.Chapter(0, "Intro", 0, 1000),
                core.Chapter(1, "Outro", 1000, 3000)]
    result = core.BuildResult(output_path=str(tmp_path / "m.mp3"),
                              chapters=chapters, total_ms=3000, reencoded=False)
    tags = core.Tags(title="My Book", artist="Jane")
    report = core.write_chapter_report(str(tmp_path / "m.mp3"), result, tags)
    text = open(report, encoding="utf-8").read()
    assert "My Book" in text
    assert "Intro" in text and "Outro" in text
    assert "Chapters     : 2" in text


# ---------------------------------------------------------------------------
# Probing & scanning
# ---------------------------------------------------------------------------


def test_scan_folder_sorted_and_probed(tmp_path):
    make_mp3(str(tmp_path / "track1.mp3"), 1)
    make_mp3(str(tmp_path / "track10.mp3"), 1)
    make_mp3(str(tmp_path / "track2.mp3"), 1)
    items = core.scan_folder(str(tmp_path))
    assert [it.filename for it in items] == ["track1.mp3", "track2.mp3", "track10.mp3"]
    for it in items:
        assert it.error == ""
        assert it.duration > 0
        assert it.codec_name == "mp3"
        assert it.sample_rate == 44100


def test_scan_folder_skips_existing_master(tmp_path):
    book = tmp_path / "My Book"
    book.mkdir()
    make_mp3(str(book / "01 Intro.mp3"), 1)
    make_mp3(str(book / "02 Outro.mp3"), 1)
    # A previously-built master named after the folder must not become a chapter.
    make_mp3(str(book / "My Book.mp3"), 1)
    items, skipped = core.scan_folder_detailed(str(book))
    names = [it.filename for it in items]
    assert "My Book.mp3" not in names
    assert names == ["01 Intro.mp3", "02 Outro.mp3"]
    assert skipped == ["My Book.mp3"]


def test_scan_folder_keeps_all_when_only_master(tmp_path):
    book = tmp_path / "Solo"
    book.mkdir()
    make_mp3(str(book / "Solo.mp3"), 1)
    # Skipping would remove everything, so the file is kept.
    items, skipped = core.scan_folder_detailed(str(book))
    assert [it.filename for it in items] == ["Solo.mp3"]
    assert skipped == []


# ---------------------------------------------------------------------------
# Build pipeline
# ---------------------------------------------------------------------------


def _read_chapters(path):
    id3 = ID3(path)
    chaps = id3.getall("CHAP")
    chaps.sort(key=lambda c: c.start_time)
    toc = id3.getall("CTOC")
    return id3, chaps, toc


def test_build_master_copy_path(tmp_path):
    make_mp3(str(tmp_path / "01 - Intro.mp3"), 1)
    make_mp3(str(tmp_path / "02 - Middle.mp3"), 2)
    make_mp3(str(tmp_path / "03 - End.mp3"), 1)
    items = core.scan_folder(str(tmp_path))

    progress_values = []
    out = str(tmp_path / "master.mp3")
    tags = core.Tags(title="My Master", artist="Me", album="My Album")
    result = core.build_master(items, out, tags,
                               progress=lambda f: progress_values.append(f))

    assert os.path.isfile(out)
    assert result.reencoded is False
    assert progress_values and progress_values[-1] == 1.0

    id3, chaps, toc = _read_chapters(out)
    assert id3["TIT2"].text[0] == "My Master"
    assert id3["TPE1"].text[0] == "Me"
    assert len(chaps) == 3
    titles = [c.sub_frames["TIT2"].text[0] for c in chaps]
    assert titles == ["Intro", "Middle", "End"]
    # Chapters are contiguous and monotonic.
    for a, b in zip(chaps, chaps[1:]):
        assert a.end_time == b.start_time
        assert a.start_time < a.end_time
    assert len(toc) == 1
    assert len(toc[0].child_element_ids) == 3
    # Final chapter ends near the real file duration (within 250 ms).
    actual_ms = int(round(core.MP3(out).info.length * 1000))
    assert abs(chaps[-1].end_time - actual_ms) <= 250


def test_build_master_reencode_path_mismatched(tmp_path):
    make_mp3(str(tmp_path / "a.mp3"), 1, sample_rate=44100, channels=2)
    make_mp3(str(tmp_path / "b.mp3"), 1, sample_rate=22050, channels=1)
    items = core.scan_folder(str(tmp_path))
    assert not core._streams_uniform(items)

    out = str(tmp_path / "master.mp3")
    result = core.build_master(items, out, core.Tags(title="Mixed"))
    assert result.reencoded is True
    assert os.path.isfile(out)
    _, chaps, _ = _read_chapters(out)
    assert len(chaps) == 2


def test_build_master_unicode_titles(tmp_path):
    make_mp3(str(tmp_path / "Café Déjà.mp3"), 1)
    make_mp3(str(tmp_path / "日本語.mp3"), 1)
    items = core.scan_folder(str(tmp_path))
    out = str(tmp_path / "master.mp3")
    core.build_master(items, out, core.Tags(title="Unicode"))
    _, chaps, _ = _read_chapters(out)
    titles = [c.sub_frames["TIT2"].text[0] for c in chaps]
    assert "Café Déjà" in titles
    assert "日本語" in titles


def test_build_respects_reordered_items(tmp_path):
    make_mp3(str(tmp_path / "01 - First.mp3"), 1)
    make_mp3(str(tmp_path / "02 - Second.mp3"), 2)
    items = core.scan_folder(str(tmp_path))
    reordered = [items[1], items[0]]
    chapters = core.compute_chapters(reordered)
    out = str(tmp_path / "master.mp3")
    core.build_master(reordered, out, core.Tags(), chapters=chapters)
    _, chaps, _ = _read_chapters(out)
    titles = [c.sub_frames["TIT2"].text[0] for c in chaps]
    assert titles == ["Second", "First"]


def test_build_empty_raises(tmp_path):
    with pytest.raises(core.NoAudioFilesError):
        core.build_master([], str(tmp_path / "out.mp3"), core.Tags())


def test_cancel_before_build_raises(tmp_path):
    make_mp3(str(tmp_path / "a.mp3"), 1)
    items = core.scan_folder(str(tmp_path))
    canceller = core.Canceller()
    canceller.cancel()
    with pytest.raises(core.BuildCancelled):
        core.build_master(items, str(tmp_path / "out.mp3"), core.Tags(),
                          canceller=canceller)


def test_cover_art_embedded(tmp_path):
    make_mp3(str(tmp_path / "a.mp3"), 1)
    cover = tmp_path / "cover.png"
    # 1x1 PNG
    cover.write_bytes(bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d4944415478da6364f8cf000000ff00ff3f00050001ff7f7a2b0000"
        "00004945" "4e44ae426082"
    ))
    items = core.scan_folder(str(tmp_path))
    out = str(tmp_path / "master.mp3")
    core.build_master(items, out, core.Tags(title="WithCover", cover_path=str(cover)))
    id3 = ID3(out)
    assert id3.getall("APIC")
