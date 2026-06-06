"""Audio-only validation pipeline.

Uses ffprobe (already on PATH / bundled for ChapterForge) to inspect files.
Raises AudioValidationError for anything containing a video stream or with
an unsupported container.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional, Tuple

from ..core import _find_tool, CREATE_NO_WINDOW

# ---------------------------------------------------------------------------
# Allowed audio extensions (source-of-truth for this integration)
# ---------------------------------------------------------------------------

ALLOWED_AUDIO_EXTS: frozenset = frozenset({
    ".mp2", ".mp3", ".m4a", ".m4b", ".aac", ".wav", ".wave",
    ".ogg", ".oga", ".opus", ".flac", ".alac", ".aif", ".aiff",
    ".aifc", ".au", ".caf", ".wma", ".ac3", ".eac3", ".ape",
    ".spx", ".vox", ".voc", ".snd", ".tta", ".w64",
})

# Containers that look like audio but can carry video - inspect before accepting
_AMBIGUOUS_EXTS: frozenset = frozenset({".mp4", ".m4v", ".mov"})

# Explicitly blocked video extensions (fast-fail without ffprobe)
BLOCKED_VIDEO_EXTS: frozenset = frozenset({
    ".mp4", ".m4v", ".mov", ".avi", ".mkv", ".webm", ".flv",
    ".mpeg", ".mpg", ".ts", ".vob", ".ogv", ".mxf",
})

# SSRF-safe: block private/loopback ranges in remote URLs
_BLOCKED_HOSTS: tuple = (
    "localhost", "127.", "0.0.0.0", "169.254.", "10.", "192.168.",
)


class AudioValidationError(Exception):
    pass


@dataclass
class AudioProbeResult:
    has_audio: bool
    has_video: bool
    duration_seconds: float
    audio_codec: str
    sample_rate: int
    channels: int
    size_bytes: int
    extension: str
    content_type: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_local_file(path: str) -> AudioProbeResult:
    """Validate a local file. Raises AudioValidationError on rejection."""
    ext = os.path.splitext(path)[1].lower()
    if ext in BLOCKED_VIDEO_EXTS and ext not in _AMBIGUOUS_EXTS:
        raise AudioValidationError(
            f"This product accepts audio-only sources. "
            f"'{ext}' is a video container and cannot be used."
        )
    result = _probe_file(path)
    _assert_audio_only(result, os.path.basename(path))
    return result


def validate_remote_url(url: str, max_bytes: int = 50 * 1024 * 1024) -> AudioProbeResult:
    """Validate a remote URL. Downloads to a temp file for inspection."""
    _check_ssrf(url)
    ext = _ext_from_url(url)
    if ext in BLOCKED_VIDEO_EXTS and ext not in _AMBIGUOUS_EXTS:
        raise AudioValidationError(
            f"This product accepts audio-only sources. "
            f"The URL appears to reference a video file ('{ext}')."
        )
    import tempfile
    req = urllib.request.Request(url, headers={"User-Agent": "ChapterForge/2"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "video" in content_type:
                raise AudioValidationError(
                    f"Remote URL reports Content-Type '{content_type}', which is not audio."
                )
            data = resp.read(max_bytes)
    except urllib.error.URLError as exc:
        raise AudioValidationError(f"Could not fetch remote URL: {exc.reason}") from exc

    suffix = ext or ".tmp"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        result = _probe_file(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
    _assert_audio_only(result, url)
    return result


def estimate_duration_hours(duration_seconds: float) -> float:
    """Apply Auphonic's 3-minute minimum billing rule."""
    minimum = 3 * 60
    return max(duration_seconds, minimum) / 3600


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _probe_file(path: str) -> AudioProbeResult:
    try:
        ffprobe = _find_tool("ffprobe")
    except Exception as exc:
        raise AudioValidationError(f"ffprobe not found: {exc}") from exc

    cmd = [
        ffprobe, "-v", "quiet", "-print_format", "json",
        "-show_streams", "-show_format", path,
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=CREATE_NO_WINDOW,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise AudioValidationError("ffprobe timed out inspecting the file.") from exc

    try:
        info = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        raise AudioValidationError(f"Could not parse ffprobe output: {exc}") from exc

    streams = info.get("streams", [])
    fmt = info.get("format", {})
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    has_video = any(s.get("codec_type") == "video" for s in streams)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})

    try:
        duration = float(fmt.get("duration") or audio_stream.get("duration") or 0)
    except (ValueError, TypeError):
        duration = 0.0

    size = int(fmt.get("size", 0) or 0)
    ext = os.path.splitext(path)[1].lower()

    return AudioProbeResult(
        has_audio=has_audio,
        has_video=has_video,
        duration_seconds=duration,
        audio_codec=audio_stream.get("codec_name", ""),
        sample_rate=int(audio_stream.get("sample_rate", 0) or 0),
        channels=int(audio_stream.get("channels", 0) or 0),
        size_bytes=size,
        extension=ext,
        content_type="audio/" + audio_stream.get("codec_name", "unknown"),
    )


def _assert_audio_only(result: AudioProbeResult, label: str) -> None:
    if result.has_video:
        raise AudioValidationError(
            f"'{label}' contains a video stream. "
            "This product currently accepts audio-only sources."
        )
    if not result.has_audio:
        raise AudioValidationError(
            f"'{label}' does not appear to contain an audio stream."
        )


def _ext_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    _, ext = os.path.splitext(path)
    return ext.lower()


def _check_ssrf(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise AudioValidationError("Remote URLs must use HTTPS.")
    host = (parsed.hostname or "").lower()
    for blocked in _BLOCKED_HOSTS:
        if host == blocked or host.startswith(blocked):
            raise AudioValidationError(
                f"Remote URL host '{host}' is not allowed (private/loopback address)."
            )
