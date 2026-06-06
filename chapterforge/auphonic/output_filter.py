"""Filter Auphonic output file lists to allowed audio-only outputs.

Auphonic may return video/audiogram outputs for accounts with video features.
This module strips them before presenting to the user.
"""
from __future__ import annotations

from typing import Any, Dict, List

# Output format types that are allowed in audio-only mode
ALLOWED_OUTPUT_TYPES: frozenset = frozenset({
    "audio",
    "transcript",
    "subtitle",
    "speech-data",
    "stats",
    "chapters",
    "cut-list",
    "image",          # cover image and waveform image (metadata, not video)
    "description",
})

# Format strings explicitly blocked even if type looks innocuous
_BLOCKED_FORMATS: frozenset = frozenset({
    "video", "audiogram", "youtube", "mp4_video", "webm_video",
})

# Output type strings that indicate video
_BLOCKED_TYPES: frozenset = frozenset({
    "video", "audiogram",
})


def is_allowed_output(output: Dict[str, Any]) -> bool:
    """Return True if an Auphonic output dict is allowed in audio-only mode."""
    fmt = str(output.get("format", "")).lower()
    out_type = str(output.get("output_type", output.get("type", ""))).lower()
    if fmt in _BLOCKED_FORMATS:
        return False
    if out_type in _BLOCKED_TYPES:
        return False
    return True


def filter_outputs(outputs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return only allowed outputs from an Auphonic result list."""
    return [o for o in outputs if is_allowed_output(o)]


def classify_output(output: Dict[str, Any]) -> str:
    """Return a human-readable output type label."""
    fmt = str(output.get("format", "")).lower()
    ending = str(output.get("ending", "")).lower()
    type_map = {
        "transcript": "Transcript",
        "subtitle": "Captions",
        "speech": "Speech Data",
        "stats": "Processing Stats",
        "chapters": "Chapters",
        "cutlist": "Cut List",
        "cut-list": "Cut List",
        "waveform": "Waveform Image",
        "cover": "Cover Image",
    }
    for key, label in type_map.items():
        if key in fmt or key in ending:
            return label
    return "Audio"
