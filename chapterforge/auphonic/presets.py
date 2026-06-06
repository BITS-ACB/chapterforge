"""Built-in Auphonic preset library for ChapterForge.

Each preset is a ready-to-use Auphonic JSON payload fragment that can be
submitted as the ``algorithms`` / ``output_files`` / ``speech_recognition``
section of a production request. Users can also load their own Auphonic
account presets by UUID.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .models import AuphonicPreset

# ---------------------------------------------------------------------------
# Output format helpers
# ---------------------------------------------------------------------------

def _audio_out(fmt: str, bitrate: str = "", ending: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {"format": fmt}
    if bitrate:
        out["bitrate"] = bitrate
    if ending:
        out["ending"] = ending
    return out


def _transcript_outs() -> List[Dict[str, Any]]:
    return [
        {"format": "transcript", "ending": "html"},
        {"format": "transcript", "ending": "txt"},
        {"format": "subtitle", "ending": "srt"},
        {"format": "subtitle", "ending": "webvtt"},
    ]


def _stats_out() -> Dict[str, Any]:
    return {"format": "stats", "ending": "json"}


def _chapters_out() -> Dict[str, Any]:
    return {"format": "chapters", "ending": "txt"}


# ---------------------------------------------------------------------------
# Built-in preset definitions
# ---------------------------------------------------------------------------

_PODCAST_CLEANUP_ALGORITHMS = {
    "leveler": True,
    "normloudness": True,
    "loudnesstarget": -16,
    "maxpeak": -1,
    "filtering": True,
    "denoise": True,
    "denoiseamount": 0,
    "silence_cutter": False,
    "filler_cutter": False,
    "cough_cutter": False,
}

_AUDIOBOOK_ALGORITHMS = {
    "leveler": True,
    "normloudness": True,
    "loudnesstarget": -18,
    "maxpeak": -3,
    "filtering": True,
    "denoise": True,
    "denoiseamount": 6,
    "silence_cutter": False,
    "filler_cutter": False,
}

_LECTURE_ALGORITHMS = {
    "leveler": True,
    "normloudness": True,
    "loudnesstarget": -16,
    "maxpeak": -1,
    "filtering": True,
    "denoise": True,
    "denoiseamount": 0,
    "silence_cutter": True,
}

_ARCHIVE_ALGORITHMS = {
    "leveler": False,
    "normloudness": False,
    "filtering": False,
    "denoise": False,
    "silence_cutter": False,
}


BUILTIN_PRESETS: List[AuphonicPreset] = [
    AuphonicPreset(
        uuid="builtin-podcast-cleanup",
        preset_name="Podcast Cleanup",
        is_builtin=True,
        description=(
            "Leveling, loudness normalization (-16 LUFS), noise reduction, "
            "and filtering. No automatic cutting. MP3 + stats output."
        ),
        payload={
            "algorithms": _PODCAST_CLEANUP_ALGORITHMS,
            "output_files": [
                _audio_out("mp3", bitrate="128"),
                _stats_out(),
            ],
        },
    ),
    AuphonicPreset(
        uuid="builtin-podcast-cleanup-transcript",
        preset_name="Podcast Cleanup + Transcript",
        is_builtin=True,
        description=(
            "Same as Podcast Cleanup plus transcript (HTML, TXT), "
            "captions (SRT, WebVTT), and chapter output."
        ),
        payload={
            "algorithms": _PODCAST_CLEANUP_ALGORITHMS,
            "output_files": [
                _audio_out("mp3", bitrate="128"),
                _stats_out(),
                _chapters_out(),
                *_transcript_outs(),
            ],
            "speech_recognition": {"language": "en"},
        },
    ),
    AuphonicPreset(
        uuid="builtin-audiobook-acx",
        preset_name="Audiobook / ACX Draft",
        is_builtin=True,
        description=(
            "RMS-mode loudness (-18 LUFS), careful denoise, "
            "high-quality WAV and FLAC output. Suitable for ACX submission drafts."
        ),
        payload={
            "algorithms": _AUDIOBOOK_ALGORITHMS,
            "output_files": [
                _audio_out("wav"),
                _audio_out("flac"),
                _stats_out(),
            ],
        },
    ),
    AuphonicPreset(
        uuid="builtin-lecture-cleanup",
        preset_name="Lecture Cleanup",
        is_builtin=True,
        description=(
            "Voice-focused denoise and leveling with silence cutting. "
            "MP3 + transcript and captions for accessibility."
        ),
        payload={
            "algorithms": _LECTURE_ALGORITHMS,
            "output_files": [
                _audio_out("mp3", bitrate="96"),
                _stats_out(),
                *_transcript_outs(),
            ],
            "speech_recognition": {"language": "en"},
        },
    ),
    AuphonicPreset(
        uuid="builtin-multitrack-interview",
        preset_name="Meeting / Interview Multitrack",
        is_builtin=True,
        description=(
            "Host and guest track layout with adaptive leveling. "
            "MP3 output with optional transcript."
        ),
        payload={
            "algorithms": _PODCAST_CLEANUP_ALGORITHMS,
            "output_files": [
                _audio_out("mp3", bitrate="128"),
                _stats_out(),
            ],
            "is_multitrack": True,
        },
    ),
    AuphonicPreset(
        uuid="builtin-archive-master",
        preset_name="Archive Master",
        is_builtin=True,
        description=(
            "Minimal processing - no leveling or cutting. "
            "FLAC and WAV output with processing stats. Preserves original dynamics."
        ),
        payload={
            "algorithms": _ARCHIVE_ALGORITHMS,
            "output_files": [
                _audio_out("flac"),
                _audio_out("wav"),
                _stats_out(),
                _chapters_out(),
            ],
        },
    ),
]


def get_builtin(uuid: str) -> "AuphonicPreset | None":
    return next((p for p in BUILTIN_PRESETS if p.uuid == uuid), None)


def all_presets(account_presets: "List[Dict] | None" = None) -> List[AuphonicPreset]:
    """Return built-in presets followed by any account presets."""
    result = list(BUILTIN_PRESETS)
    for ap in (account_presets or []):
        result.append(AuphonicPreset(
            uuid=ap.get("uuid", ""),
            preset_name=ap.get("preset_name", ap.get("uuid", "Unknown")),
            is_builtin=False,
            description=ap.get("description", ""),
            payload=ap,
        ))
    return result
