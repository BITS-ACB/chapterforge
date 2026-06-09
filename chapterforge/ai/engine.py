"""ASR engine abstraction layer for ChapterForge.

All concrete backends inherit from ``ASREngine`` and are created via
``create_engine(tier, model)``.  The factory performs lazy imports so
only the backend that is actually used needs to be installed.
"""

import abc
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionSegment:
    """A single timestamped segment returned by any ASR backend."""
    start: float        # seconds
    end: float          # seconds
    text: str
    confidence: float   # log-probability or equivalent; higher is better


class ASREngine(abc.ABC):
    """Abstract base class for all ASR backends."""

    @abc.abstractmethod
    def transcribe(
        self,
        audio_path: str,
        progress_callback: Callable[[float], None] = None,
    ) -> List[TranscriptionSegment]:
        """Transcribe *audio_path*, returning timestamped segments.

        *progress_callback* receives a float in [0, 100] periodically.
        Raise ``RuntimeError`` to signal cancellation or failure.
        """

    def suggest_chapters(
        self, segments: List[TranscriptionSegment]
    ) -> List[Dict[str, Any]]:
        """Derive chapter boundaries from *segments*.

        Returns a list of dicts with keys ``title``, ``start`` (seconds),
        and ``end`` (seconds).  Default heuristic: split on gaps > 1.5 s
        or when a chapter exceeds 120 s.
        """
        if not segments:
            return []

        chapters: List[Dict[str, Any]] = []
        current_text: List[str] = []
        start_time = segments[0].start

        for i, s in enumerate(segments):
            current_text.append(s.text)
            is_last = i == len(segments) - 1
            if not is_last:
                gap = segments[i + 1].start - s.end
                chapter_len = s.end - start_time
                if gap > 1.5 or chapter_len > 120:
                    chapters.append({
                        "title": _make_title(current_text),
                        "start": start_time,
                        "end": s.end,
                    })
                    start_time = segments[i + 1].start
                    current_text = []

        if current_text:
            chapters.append({
                "title": _make_title(current_text),
                "start": start_time,
                "end": segments[-1].end,
            })

        return chapters


def _make_title(text_list: List[str]) -> str:
    """Derive a short chapter title from a list of sentence fragments."""
    text = " ".join(text_list).strip()
    if not text:
        return "Untitled Chapter"
    title = text.split(".")[0].split("?")[0].split("!")[0].strip()
    if not title:
        return "Untitled Chapter"
    return (title[:57] + "...") if len(title) > 60 else title


def create_engine(tier: str, model: str) -> ASREngine:
    """Factory: instantiate the appropriate ASR backend.

    Args:
        tier:  "Basic", "Strong", or "Premium".
        model: Model name within that tier (e.g. "small", "medium").

    Returns:
        A concrete ``ASREngine`` instance.

    Raises:
        RuntimeError: If the required package is not installed.
        ValueError:   If *tier* is unrecognised.
    """
    tier = tier.strip()
    if tier == "Basic":
        from .whisper_cpp import WhisperCppEngine
        return WhisperCppEngine(model)
    if tier == "Premium":
        from .parakeet import ParakeetEngine
        return ParakeetEngine(model)
    if tier == "Strong":
        from .faster_whisper_engine import FasterWhisperEngine
        return FasterWhisperEngine(model)
    raise ValueError(f"Unknown AI engine tier: {tier!r}")
