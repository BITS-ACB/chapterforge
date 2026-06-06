"""Auphonic integration for ChapterForge.

Primary entry point: AuphonicService in service.py.
"""
from .service import AuphonicService
from .client import AuphonicError
from .validate import AudioValidationError
from .models import AuphonicUser, AuphonicJob, JobStatus, ProductionRequest
from .presets import BUILTIN_PRESETS, all_presets

__all__ = [
    "AuphonicService",
    "AuphonicError",
    "AudioValidationError",
    "AuphonicUser",
    "AuphonicJob",
    "JobStatus",
    "ProductionRequest",
    "BUILTIN_PRESETS",
    "all_presets",
]
