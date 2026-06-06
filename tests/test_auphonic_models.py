"""Tests for Auphonic data models and estimate logic."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chapterforge.auphonic.models import (
    AuphonicUser,
    JobStatus,
    ProductionRequest,
    AuphonicPreset,
)
from chapterforge.auphonic.estimate import (
    estimate_credits,
    credits_sufficient,
    format_credits,
    format_duration,
)
from chapterforge.auphonic.presets import BUILTIN_PRESETS, all_presets, get_builtin


class TestJobStatus:
    def test_constants_are_strings(self):
        assert isinstance(JobStatus.DONE, str)
        assert isinstance(JobStatus.ERROR, str)

    def test_known_statuses(self):
        statuses = {
            JobStatus.DRAFT, JobStatus.UPLOADING, JobStatus.READY,
            JobStatus.QUEUED, JobStatus.PROCESSING, JobStatus.DONE,
            JobStatus.ERROR, JobStatus.NEEDS_REVIEW, JobStatus.PUBLISHED,
            JobStatus.CANCELLED,
        }
        assert len(statuses) == 10


class TestProductionRequest:
    def test_defaults(self):
        req = ProductionRequest(title="Test")
        assert req.action == "start"
        assert req.review_before_publishing is False
        assert req.output_files == []

    def test_custom_fields(self):
        req = ProductionRequest(
            title="My Episode",
            input_url="https://example.com/ep.mp3",
            algorithms={"leveler": True},
            review_before_publishing=True,
        )
        assert req.title == "My Episode"
        assert req.algorithms["leveler"] is True


class TestEstimate:
    def test_three_minute_minimum(self):
        assert estimate_credits(60) == estimate_credits(180)

    def test_one_hour_audio(self):
        assert abs(estimate_credits(3600) - 1.0) < 1e-9

    def test_multitrack_uses_longest(self):
        single = estimate_credits(3600)
        multi = estimate_credits(3600, is_multitrack=True, track_durations=[3600, 1800, 900])
        assert abs(single - multi) < 1e-9

    def test_credits_sufficient_with_buffer(self):
        assert credits_sufficient(1.0, 0.9)
        assert not credits_sufficient(0.9, 0.9)  # buffer = 1.05, so 0.9*1.05 > 0.9

    def test_format_credits_minutes(self):
        result = format_credits(0.5)
        assert "30.0" in result or "minute" in result.lower()

    def test_format_credits_hours(self):
        result = format_credits(2.0)
        assert "2.00" in result or "hour" in result.lower()

    def test_format_duration_minutes(self):
        assert "30" in format_duration(1800)

    def test_format_duration_hours(self):
        result = format_duration(3661)
        assert "1h" in result


class TestBuiltinPresets:
    def test_six_presets_defined(self):
        assert len(BUILTIN_PRESETS) == 6

    def test_all_have_names(self):
        for p in BUILTIN_PRESETS:
            assert p.preset_name

    def test_all_have_payloads(self):
        for p in BUILTIN_PRESETS:
            assert isinstance(p.payload, dict)
            assert p.payload  # not empty

    def test_all_are_builtin(self):
        for p in BUILTIN_PRESETS:
            assert p.is_builtin

    def test_get_builtin_exists(self):
        p = get_builtin("builtin-podcast-cleanup")
        assert p is not None
        assert p.preset_name == "Podcast Cleanup"

    def test_get_builtin_missing(self):
        assert get_builtin("nonexistent-uuid") is None

    def test_all_presets_no_account(self):
        presets = all_presets(None)
        assert presets == BUILTIN_PRESETS

    def test_all_presets_with_account(self):
        account = [{"uuid": "user-001", "preset_name": "My Preset"}]
        presets = all_presets(account)
        assert len(presets) == len(BUILTIN_PRESETS) + 1
        assert presets[-1].uuid == "user-001"
        assert not presets[-1].is_builtin

    def test_podcast_cleanup_has_algorithms(self):
        p = get_builtin("builtin-podcast-cleanup")
        assert "algorithms" in p.payload
        assert p.payload["algorithms"].get("leveler") is True

    def test_transcript_preset_has_speech_recognition(self):
        p = get_builtin("builtin-podcast-cleanup-transcript")
        assert "speech_recognition" in p.payload

    def test_no_video_outputs_in_any_builtin(self):
        for p in BUILTIN_PRESETS:
            for out in p.payload.get("output_files", []):
                assert out.get("format") not in ("video", "audiogram")
