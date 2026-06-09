"""whisper.cpp backend - Basic tier.

Invokes the whisper.cpp CLI binary (``whisper`` or ``whisper-cpp`` on PATH)
and parses its JSON output.  Lowest RAM footprint; good for tiny/base/small.

whisper.cpp releases: https://github.com/ggerganov/whisper.cpp/releases
"""

import json
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Callable, List

from .engine import ASREngine, TranscriptionSegment

logger = logging.getLogger(__name__)


class WhisperCppEngine(ASREngine):
    """Basic-tier ASR backend using the whisper.cpp CLI."""

    def __init__(self, model: str = "base"):
        self.model = model
        self._bin = shutil.which("whisper") or shutil.which("whisper-cpp")
        if not self._bin:
            raise RuntimeError(
                "whisper.cpp binary not found on PATH. "
                "Download from https://github.com/ggerganov/whisper.cpp/releases "
                "and place 'whisper.exe' on your PATH."
            )
        logger.info("WhisperCpp init: binary=%s model=%s", self._bin, model)

    def transcribe(
        self,
        audio_path: str,
        progress_callback: Callable[[float], None] = None,
    ) -> List[TranscriptionSegment]:
        with tempfile.TemporaryDirectory() as tmp:
            out_base = os.path.join(tmp, "out")
            cmd = [
                self._bin,
                "-m", f"ggml-{self.model}.bin",
                "-f", audio_path,
                "-oj",              # JSON output
                "-of", out_base,
                "--no-prints",
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=3600)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("whisper.cpp timed out after 1 hour") from exc
            except subprocess.CalledProcessError as exc:
                raise RuntimeError(
                    f"whisper.cpp failed: {exc.stderr.decode(errors='replace')}"
                ) from exc

            out_json = out_base + ".json"
            if not os.path.exists(out_json):
                raise RuntimeError(
                    "whisper.cpp produced no output JSON. "
                    "Check that the model file is present next to the binary."
                )

            with open(out_json, encoding="utf-8") as fh:
                data = json.load(fh)

        results: List[TranscriptionSegment] = []
        raw = data.get("transcription", [])
        total = max(len(raw), 1)
        for i, seg in enumerate(raw):
            ts = seg.get("timestamps", {})
            # whisper.cpp timestamps are in ms
            start = ts.get("from", 0) / 1000.0
            end = ts.get("to", 0) / 1000.0
            results.append(
                TranscriptionSegment(
                    start=start,
                    end=end,
                    text=seg.get("text", "").strip(),
                    confidence=-0.5,
                )
            )
            if progress_callback:
                progress_callback((i + 1) / total * 100.0)

        if progress_callback:
            progress_callback(100.0)
        return results
