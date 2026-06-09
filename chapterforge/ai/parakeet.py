"""Parakeet ONNX backend - Premium tier.

Planned backend using NVIDIA Parakeet-TDT 0.6B via ONNX Runtime int8.

Requirements (not in default install):
    pip install onnxruntime
    # Download ONNX weights from HuggingFace:
    # https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3

This module raises ``NotImplementedError`` for actual inference until
the ONNX inference path is implemented in a future milestone.
"""

import logging
from typing import Callable, List

from .engine import ASREngine, TranscriptionSegment

logger = logging.getLogger(__name__)


class ParakeetEngine(ASREngine):
    """Premium-tier ASR backend using Parakeet ONNX int8."""

    def __init__(self, model: str = "parakeet-onnx"):
        self.model = model
        try:
            import onnxruntime  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "onnxruntime is not installed. "
                "Run: pip install onnxruntime"
            ) from exc

        # Model path will be read from settings in a future milestone.
        self._session = None
        logger.info("ParakeetEngine init (model=%s) - session not yet loaded", model)

    def transcribe(
        self,
        audio_path: str,
        progress_callback: Callable[[float], None] = None,
    ) -> List[TranscriptionSegment]:
        if self._session is None:
            raise NotImplementedError(
                "Parakeet ONNX inference is not yet implemented. "
                "Use the Strong tier (faster-whisper) for now."
            )
        raise NotImplementedError("Parakeet inference path not yet complete.")
