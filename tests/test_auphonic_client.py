"""Tests for AuphonicClient - all network calls are mocked."""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chapterforge.auphonic.client import AuphonicClient, AuphonicError, _encode_multipart


def _make_client(token: str = "test-token") -> AuphonicClient:
    return AuphonicClient(token=token)


def _mock_response(data: dict, status: int = 200):
    resp = MagicMock()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    resp.read.return_value = json.dumps({"data": data}).encode()
    resp.status = status
    return resp


class TestAuphonicClientAuth:
    def test_bearer_header_set(self):
        client = _make_client("my-secret-token")
        headers = client._headers()
        assert headers["Authorization"] == "Bearer my-secret-token"

    def test_set_token_updates_header(self):
        client = _make_client("")
        client.set_token("new-token")
        assert client._headers()["Authorization"] == "Bearer new-token"


class TestGetUser:
    def test_parses_user_fields(self):
        user_data = {
            "username": "testuser",
            "email": "test@example.com",
            "user_id": "testuser",
            "credits": 2.5,
            "onetime_credits": 0.5,
            "recurring_credits": 2.0,
            "recharge_date": "2026-07-01",
            "recharge_recurring_credits": 2.0,
        }
        client = _make_client()
        with patch("urllib.request.urlopen", return_value=_mock_response(user_data)):
            user = client.get_user()
        assert user.username == "testuser"
        assert user.credits == 2.5
        assert user.recurring_credits == 2.0

    def test_raises_on_http_error(self):
        import urllib.error
        client = _make_client()
        err = urllib.error.HTTPError(url="", code=401, msg="Unauthorized", hdrs=None, fp=None)
        err.read = lambda: b'{"status_string": "Invalid token"}'
        with patch("urllib.request.urlopen", side_effect=err):
            with pytest.raises(AuphonicError) as exc_info:
                client.get_user()
        assert exc_info.value.status_code == 401


class TestCreateProduction:
    def test_sends_payload(self):
        prod_data = {"uuid": "abc-123", "status_string": "Draft"}
        client = _make_client()
        captured = []

        def _fake_open(req, timeout=None):
            captured.append(req)
            return _mock_response(prod_data)

        with patch("urllib.request.urlopen", side_effect=_fake_open):
            result = client.create_production({"title": "Test", "action": "start"})

        assert result["uuid"] == "abc-123"
        body = json.loads(captured[0].data)
        assert body["title"] == "Test"


class TestOutputFilter:
    def test_allowed_audio(self):
        from chapterforge.auphonic.output_filter import is_allowed_output
        assert is_allowed_output({"format": "mp3", "ending": "mp3"})

    def test_blocked_video(self):
        from chapterforge.auphonic.output_filter import is_allowed_output
        assert not is_allowed_output({"format": "video", "ending": "mp4"})

    def test_blocked_audiogram(self):
        from chapterforge.auphonic.output_filter import is_allowed_output
        assert not is_allowed_output({"format": "audiogram", "ending": "mp4"})

    def test_allowed_transcript(self):
        from chapterforge.auphonic.output_filter import is_allowed_output
        assert is_allowed_output({"format": "transcript", "ending": "html"})

    def test_filter_removes_video(self):
        from chapterforge.auphonic.output_filter import filter_outputs
        outputs = [
            {"format": "mp3", "ending": "mp3"},
            {"format": "video", "ending": "mp4"},
            {"format": "transcript", "ending": "txt"},
        ]
        allowed = filter_outputs(outputs)
        assert len(allowed) == 2
        assert all(o["format"] != "video" for o in allowed)


class TestMultipartEncoding:
    def test_contains_boundary(self):
        result = _encode_multipart(
            "testboundary", {}, "input_file", "test.mp3", b"audio data", "audio/mpeg"
        )
        assert b"testboundary" in result

    def test_contains_filename(self):
        result = _encode_multipart(
            "b", {}, "input_file", "my_episode.mp3", b"data", "audio/mpeg"
        )
        assert b"my_episode.mp3" in result

    def test_contains_file_data(self):
        result = _encode_multipart(
            "b", {}, "input_file", "f.mp3", b"BINARY_AUDIO_DATA", "audio/mpeg"
        )
        assert b"BINARY_AUDIO_DATA" in result
