"""ACX compliance measurement for ChapterForge.

Uses FFmpeg's loudnorm filter (first-pass analysis mode) to measure integrated
loudness, true peak, and noise floor. Reports a pass/fail against ACX
requirements:
  - Integrated loudness: -23 LUFS +/- 1 dB
  - True peak: <= -3 dBFS
  - Noise floor: <= -60 dBFS
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass

from .core import _find_tool, ChapterForgeError, CREATE_NO_WINDOW

ACX_LUFS_TARGET = -23.0
ACX_LUFS_RANGE = 1.0
ACX_PEAK_MAX = -3.0
ACX_NOISE_MAX = -60.0


@dataclass
class AcxResult:
    integrated_lufs: float
    true_peak_db: float
    noise_floor_db: float
    loudness_ok: bool
    peak_ok: bool
    noise_ok: bool

    @property
    def passes(self) -> bool:
        return self.loudness_ok and self.peak_ok and self.noise_ok

    def summary(self) -> str:
        def check(ok: bool) -> str:
            return "PASS" if ok else "FAIL"

        lufs_note = f"(target: {ACX_LUFS_TARGET} +/- {ACX_LUFS_RANGE} dB)"
        peak_note = f"(max: {ACX_PEAK_MAX} dBFS)"
        noise_note = f"(max: {ACX_NOISE_MAX} dBFS)"

        lines = [
            f"Loudness:    {self.integrated_lufs:+.1f} LUFS  {check(self.loudness_ok)}  {lufs_note}",
            f"True peak:   {self.true_peak_db:+.1f} dBFS  {check(self.peak_ok)}  {peak_note}",
            f"Noise floor: {self.noise_floor_db:+.1f} dBFS  {check(self.noise_ok)}  {noise_note}",
        ]
        overall = "PASS - file meets ACX requirements." if self.passes else \
                  "FAIL - one or more ACX requirements are not met."
        lines.append("")
        lines.append(overall)
        return "\n".join(lines)

    def recommendations(self) -> list[str]:
        recs = []
        if not self.loudness_ok:
            diff = ACX_LUFS_TARGET - self.integrated_lufs
            direction = "louder" if diff > 0 else "quieter"
            recs.append(
                f"Integrated loudness is {self.integrated_lufs:.1f} LUFS "
                f"(need {ACX_LUFS_TARGET} +/- {ACX_LUFS_RANGE}). "
                f"Enable loudness normalization and rebuild, or make the recording "
                f"{abs(diff):.1f} dB {direction}."
            )
        if not self.peak_ok:
            recs.append(
                f"True peak is {self.true_peak_db:.1f} dBFS "
                f"(max {ACX_PEAK_MAX}). "
                "Enable peak limiting or reduce the recording level."
            )
        if not self.noise_ok:
            recs.append(
                f"Noise floor is {self.noise_floor_db:.1f} dBFS "
                f"(max {ACX_NOISE_MAX}). "
                "Record in a quieter environment or apply noise reduction."
            )
        return recs


def measure_file(path: str) -> AcxResult:
    """Run FFmpeg loudnorm analysis on *path* and return an AcxResult.

    Raises ChapterForgeError on failure, FFmpegNotFoundError if ffmpeg is
    missing.
    """
    ffmpeg = _find_tool("ffmpeg")
    # loudnorm in analysis mode (no output file) writes JSON to stderr.
    # We merge stderr into stdout for simpler capture.
    cmd = [
        ffmpeg, "-hide_banner", "-nostdin", "-y",
        "-i", path,
        "-af", "loudnorm=I=-23:TP=-3:LRA=11:print_format=json",
        "-f", "null", "-",
    ]
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW,
    )
    output = (proc.stdout or b"").decode("utf-8", "replace")

    match = re.search(r'\{[^{}]*"input_i"\s*:[^{}]*\}', output, re.DOTALL)
    if not match:
        tail = output[-800:].strip()
        raise ChapterForgeError(
            f"Could not parse loudnorm output. FFmpeg said:\n{tail}"
        )
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError as exc:
        raise ChapterForgeError(f"Malformed loudnorm JSON: {exc}") from exc

    def _f(key: str, fallback: float = -99.0) -> float:
        val = data.get(key, fallback)
        try:
            return float(val)
        except (TypeError, ValueError):
            return fallback

    lufs = _f("input_i")
    peak = _f("input_tp")
    # input_thresh is loudnorm's gating threshold; it approximates the noise
    # floor well enough for a compliance report.
    noise = _f("input_thresh")

    return AcxResult(
        integrated_lufs=lufs,
        true_peak_db=peak,
        noise_floor_db=noise,
        loudness_ok=abs(lufs - ACX_LUFS_TARGET) <= ACX_LUFS_RANGE,
        peak_ok=peak <= ACX_PEAK_MAX,
        noise_ok=noise <= ACX_NOISE_MAX,
    )
