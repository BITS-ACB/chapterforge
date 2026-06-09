"""faster-whisper backend - Strong tier.

Wraps the ``faster_whisper`` package with hardware-aware initialisation
via ``HardwareCapabilities``.  Falls back to CPU int8 if GPU init fails.
"""

import logging
from typing import Callable, List

from .engine import ASREngine, TranscriptionSegment
from .hardware import HardwareCapabilities

logger = logging.getLogger(__name__)

# Map user-facing model names to the IDs used by faster-whisper.
_MODEL_IDS: dict = {
    "tiny": "tiny",
    "base": "base",
    "small": "small",
    "medium": "medium",
    "large-v3": "large-v3",
    "large-v3-turbo": "large-v3",   # fall back until turbo is stable
}


class FasterWhisperEngine(ASREngine):
    """faster-whisper backend for Strong-tier transcription."""

    def __init__(self, model: str = "small"):
        try:
            from faster_whisper import WhisperModel  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper is not installed. "
                "Run: pip install faster-whisper"
            ) from exc

        from faster_whisper import WhisperModel

        hw = HardwareCapabilities()
        cfg = hw.get_config()
        model_id = _MODEL_IDS.get(model, model)

        logger.info(
            "FasterWhisper init: model=%s device=%s compute=%s",
            model_id, cfg["device"], cfg["compute_type"],
        )
        try:
            self._model = WhisperModel(
                model_id,
                device=cfg["device"],
                compute_type=cfg["compute_type"],
            )
        except Exception:
            logger.warning("GPU init failed - falling back to CPU int8")
            self._model = WhisperModel(model_id, device="cpu", compute_type="int8")

    def transcribe(
        self,
        audio_path: str,
        progress_callback: Callable[[float], None] = None,
    ) -> List[TranscriptionSegment]:
        duration = _audio_duration(audio_path)
        segments_iter, info = self._model.transcribe(audio_path, beam_size=5)
        logger.info(
            "Detected language: %s (%.0f%%)",
            info.language, info.language_probability * 100,
        )
        results: List[TranscriptionSegment] = []
        for s in segments_iter:
            results.append(
                TranscriptionSegment(s.start, s.end, s.text.strip(), s.avg_logprob)
            )
            if progress_callback and duration > 0:
                progress_callback(min(s.end / duration * 100.0, 99.0))

        if progress_callback:
            progress_callback(100.0)
        return results


def _audio_duration(path: str) -> float:
    """Return audio duration in seconds, or 0.0 on failure."""
    try:
        import mutagen
        f = mutagen.File(path)
        return f.info.length if f else 0.0
    except Exception:
        return 0.0
