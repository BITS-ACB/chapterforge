"""Tests for the audio-only validation pipeline."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chapterforge.auphonic.validate import (
    ALLOWED_AUDIO_EXTS,
    BLOCKED_VIDEO_EXTS,
    AudioValidationError,
    _check_ssrf,
    _ext_from_url,
    estimate_duration_hours,
)


def test_allowed_audio_exts_present():
    for ext in (".mp3", ".wav", ".flac", ".ogg", ".opus", ".m4a", ".aac"):
        assert ext in ALLOWED_AUDIO_EXTS


def test_blocked_video_exts_present():
    for ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
        assert ext in BLOCKED_VIDEO_EXTS


def test_no_overlap_in_strict_audio():
    # mp4 / mov are in BLOCKED but also ambiguous; pure video exts must be blocked
    pure_video = {".avi", ".mkv", ".webm", ".flv", ".mpeg", ".mpg", ".vob", ".ogv"}
    for ext in pure_video:
        assert ext in BLOCKED_VIDEO_EXTS
        assert ext not in ALLOWED_AUDIO_EXTS


class TestSsrfCheck:
    def test_rejects_http(self):
        with pytest.raises(AudioValidationError, match="HTTPS"):
            _check_ssrf("http://example.com/audio.mp3")

    def test_rejects_localhost(self):
        with pytest.raises(AudioValidationError, match="not allowed"):
            _check_ssrf("https://localhost/audio.mp3")

    def test_rejects_127(self):
        with pytest.raises(AudioValidationError, match="not allowed"):
            _check_ssrf("https://127.0.0.1/audio.mp3")

    def test_rejects_private_10(self):
        with pytest.raises(AudioValidationError, match="not allowed"):
            _check_ssrf("https://10.0.0.1/audio.mp3")

    def test_accepts_public_https(self):
        _check_ssrf("https://example.com/audio.mp3")  # should not raise


class TestExtFromUrl:
    def test_mp3(self):
        assert _ext_from_url("https://example.com/podcast/ep1.mp3") == ".mp3"

    def test_no_ext(self):
        assert _ext_from_url("https://example.com/stream") == ""

    def test_query_string_ignored(self):
        assert _ext_from_url("https://example.com/file.wav?token=abc") == ".wav"


class TestCreditEstimate:
    def test_minimum_applied_for_short_file(self):
        # 90 seconds -> 3-minute minimum -> 0.05 hours
        est = estimate_duration_hours(90)
        assert abs(est - (3 * 60 / 3600)) < 1e-6

    def test_long_file_not_capped(self):
        # 1-hour file -> 1 hour
        est = estimate_duration_hours(3600)
        assert abs(est - 1.0) < 1e-6

    def test_exactly_3_minutes(self):
        est = estimate_duration_hours(180)
        assert abs(est - (180 / 3600)) < 1e-6
