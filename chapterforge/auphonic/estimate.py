"""Credit estimation for Auphonic productions.

Auphonic bills by processed output duration with a 3-minute minimum.
For multitrack productions the estimate is based on the expected output
duration (not the sum of all parallel tracks).
"""
from __future__ import annotations

from typing import List, Optional

_MIN_SECONDS = 3 * 60  # 3-minute Auphonic billing minimum


def estimate_credits(
    duration_seconds: float,
    is_multitrack: bool = False,
    track_durations: Optional[List[float]] = None,
) -> float:
    """Return estimated credit usage in hours.

    For multitrack the output duration is approximately the length of the
    longest track (parallel processing), not the sum.
    """
    if is_multitrack and track_durations:
        effective = max(track_durations)
    else:
        effective = duration_seconds
    billed = max(effective, _MIN_SECONDS)
    return billed / 3600


def credits_sufficient(available_hours: float, estimated_hours: float,
                        buffer_factor: float = 1.05) -> bool:
    """Return True if available credits cover the estimate with a small buffer."""
    return available_hours >= estimated_hours * buffer_factor


def format_duration(seconds: float) -> str:
    """Format seconds as 'Xh Ym' or 'Zm' for display."""
    minutes = int(seconds / 60)
    hours, mins = divmod(minutes, 60)
    if hours:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def format_credits(hours: float) -> str:
    """Format credit hours for display."""
    if hours >= 1:
        return f"{hours:.2f} hours"
    minutes = hours * 60
    return f"{minutes:.1f} minutes"
