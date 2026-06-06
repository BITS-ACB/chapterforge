"""Data models for the Auphonic integration.

All models are plain dataclasses - no wx, no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Account / credit
# ---------------------------------------------------------------------------

@dataclass
class AuphonicUser:
    username: str
    email: str
    user_id: str
    credits: float           # total hours
    onetime_credits: float
    recurring_credits: float
    recharge_date: str       # ISO date string or ""
    recharge_recurring_credits: float


# ---------------------------------------------------------------------------
# Production status
# ---------------------------------------------------------------------------

class JobStatus:
    DRAFT = "draft"
    UPLOADING = "uploading"
    READY = "ready"
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"
    NEEDS_REVIEW = "needs_review"
    PUBLISHED = "published"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Audio asset (validated local or remote file)
# ---------------------------------------------------------------------------

@dataclass
class AudioAsset:
    source_type: str           # 'upload' | 'url' | 'external_service' | 'app_storage'
    original_filename: str
    content_type: str
    extension: str
    size_bytes: int
    duration_seconds: float
    has_audio_stream: bool
    has_video_stream: bool
    audio_codec: str
    sample_rate: int
    channels: int
    validation_status: str     # 'valid' | 'invalid' | 'pending'
    storage_uri: str = ""
    remote_url: str = ""
    external_service_uuid: str = ""
    external_service_path: str = ""


# ---------------------------------------------------------------------------
# Job track (for multitrack / intro / outro / insert)
# ---------------------------------------------------------------------------

@dataclass
class JobTrack:
    asset: AudioAsset
    track_id: str = ""
    track_name: str = ""
    role: str = "track"        # 'track' | 'intro' | 'outro' | 'insert'
    offset_seconds: float = 0.0
    settings: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Output file result
# ---------------------------------------------------------------------------

@dataclass
class OutputFile:
    format: str
    ending: str
    filename: str
    bitrate: str
    size_bytes: int
    download_url: str
    local_storage_uri: str
    output_type: str           # 'audio'|'transcript'|'subtitle'|'speech-data'|'stats'|'chapters'|'cut-list'|'image'|'description'
    is_allowed: bool = True


# ---------------------------------------------------------------------------
# Production / job
# ---------------------------------------------------------------------------

@dataclass
class AuphonicJob:
    id: Optional[int]
    user_id: str
    auphonic_uuid: str
    title: str
    mode: str                  # 'simple' | 'json'
    is_multitrack: bool
    status: str
    app_status: str
    estimated_credits_hours: float
    used_credits_hours: float
    preset_uuid: str
    preset_name: str
    request_payload: Dict[str, Any]
    response_payload: Dict[str, Any]
    error_message: str
    warning_message: str
    review_before_publishing: bool
    source_asset: Optional[AudioAsset]
    tracks: List[JobTrack] = field(default_factory=list)
    outputs: List[OutputFile] = field(default_factory=list)
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""


# ---------------------------------------------------------------------------
# Preset
# ---------------------------------------------------------------------------

@dataclass
class AuphonicPreset:
    uuid: str
    preset_name: str
    is_builtin: bool
    payload: Dict[str, Any]
    description: str = ""


# ---------------------------------------------------------------------------
# Production request (what we send to Auphonic)
# ---------------------------------------------------------------------------

@dataclass
class ProductionRequest:
    title: str
    input_file: str = ""
    input_url: str = ""
    external_service_uuid: str = ""
    external_service_path: str = ""
    preset_uuid: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    output_files: List[Dict[str, Any]] = field(default_factory=list)
    algorithms: Dict[str, Any] = field(default_factory=dict)
    speech_recognition: Dict[str, Any] = field(default_factory=dict)
    chapters: List[Dict[str, Any]] = field(default_factory=list)
    multi_input_files: List[Dict[str, Any]] = field(default_factory=list)
    output_basename: str = ""
    review_before_publishing: bool = False
    webhook: str = ""
    action: str = "start"
