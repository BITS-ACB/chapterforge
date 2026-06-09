"""Detect AI models that are already downloaded to disk.

Used by the unified AI Model dialog to decide whether the user sees the
polished settings view (model is on disk) or the wizard (needs to
download). The rest of the app reads this through ``chapterforge.ai``;
keeping the detection here means the dialog and any future CLI /
status window can use the same answer.

The module deliberately does *not* import ``faster_whisper``,
``onnxruntime`` or any of the heavy ML dependencies. The detection is
purely a filesystem check on the HuggingFace cache (where faster-whisper
stores its models) plus a PATH check for the whisper.cpp binary used by
the Basic tier. That makes it safe to call at app startup, from a unit
test, or from a headless test environment.

Locations inspected:

* ``$HF_HOME`` / ``$XDG_CACHE_HOME``-aware HuggingFace hub cache. The
  default on Windows is ``%USERPROFILE%\\.cache\\huggingface\\hub`` -
  same layout faster-whisper itself uses.
* ``$PATH`` for the whisper.cpp binary (``whisper`` or ``whisper-cpp``).
* A small fixed set of Premium / Canary model directory names under
  the same HuggingFace cache, so the dialog can still say "this model
  is on disk" once Premium lands.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

#: HuggingFace hub cache root, where faster-whisper downloads land.
#: Mirrors the path faster-whisper itself uses when ``HF_HOME`` is unset.
_HF_CACHE_DIRNAME = ".cache"
_HF_HUB_DIRNAME = "huggingface"
_HF_HUB_DIRNAME_LEGACY = "hub"
_HF_HUB_MODELS = "models"
#: Some Windows installs of faster-whisper land one level shallower
#: (``.cache/huggingface/models--...`` rather than
#: ``.cache/huggingface/hub/models--...``). Probe both so the detector
#: reports the right thing on the systems the app is most likely to see.


@dataclass(frozen=True)
class ModelInfo:
    """What we know about one (tier, model) pair.

    ``available`` is True only if the model is actually on disk (or, for
    the Basic tier, the binary plus the model file is reachable). The
    dialog uses this to decide whether to show the polished settings
    view or the wizard.
    """

    tier: str            # "Basic" | "Strong" | "Premium" | "Canary"
    model: str           # e.g. "small", "medium", "parakeet-onnx"
    path: Optional[str]  # absolute path on disk, or None
    available: bool
    size_hint: str       # "461 MB" etc., or "?" if unknown


#: Canonical list of models the dialog knows about, ordered for display.
#: Sizes are best-effort; the engine itself reports the real number.
_KNOWN_MODELS: List[tuple] = [
    # (tier, model, hf_repo_id)
    ("Basic",   "tiny",            "ggerganov/whisper.cpp"),
    ("Basic",   "base",            "ggerganov/whisper.cpp"),
    ("Basic",   "small",           "ggerganov/whisper.cpp"),
    ("Strong",  "tiny",            "Systran/faster-whisper-tiny"),
    ("Strong",  "base",            "Systran/faster-whisper-base"),
    ("Strong",  "small",           "Systran/faster-whisper-small"),
    ("Strong",  "medium",          "Systran/faster-whisper-medium"),
    ("Strong",  "large-v3",        "Systran/faster-whisper-large-v3"),
    ("Strong",  "large-v3-turbo",  "Systran/faster-whisper-large-v3"),
    ("Premium", "parakeet-onnx",   "nvidia/parakeet-tdt-0.6b-v3"),
    ("Canary",  "canary",          "nvidia/canary-1b-v2"),
]

#: Single source of truth for model download sizes.
#: ``app._MODEL_DOWNLOAD_SIZES`` is a re-export alias pointing here. If a value is missing the dialog
#: simply shows "?" instead of a size.
_DOWNLOAD_SIZES: Dict[str, str] = {
    "tiny": "75 MB",
    "base": "145 MB",
    "small": "461 MB",
    "medium": "1.5 GB",
    "large-v3": "3 GB",
    "large-v3-turbo": "3 GB",
    "parakeet-onnx": "~2 GB",
    "canary": "~1 GB",
}


# ---------------------------------------------------------------------------
# Filesystem probes
# ---------------------------------------------------------------------------


def _hf_hub_root() -> Path:
    """Return the root directory the HuggingFace hub uses for downloads.

    Honours ``$HF_HOME`` and ``$XDG_CACHE_HOME`` so tests and CI can
    redirect it without monkey-patching ``Path.home``. Falls back to
    ``~/.cache/huggingface`` (the parent of both ``hub/`` and the
    direct ``models--*`` layout) so the detector works on systems where
    faster-whisper drops its files at either depth.
    """
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        return Path(hf_home) / _HF_HUB_DIRNAME
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / _HF_HUB_DIRNAME
    return Path.home() / _HF_CACHE_DIRNAME / _HF_HUB_DIRNAME


def _repo_dir(repo_id: str) -> Path:
    """Path a HuggingFace hub clone of *repo_id* would live at.

    HuggingFace names on-disk directories ``models--<org>--<name>`` with
    ``/`` turned into ``--``. Looks in both the standard
    ``hub/models--...`` layout and the flat ``models--...`` layout that
    some installs produce.
    """
    base = _hf_hub_root()
    legacy = base / _HF_HUB_DIRNAME_LEGACY / _HF_HUB_MODELS / (
        "models--" + repo_id.replace("/", "--")
    )
    flat = base / ("models--" + repo_id.replace("/", "--"))
    if legacy.exists():
        return legacy
    if flat.exists():
        return flat
    return legacy  # caller only checks .exists(), so default is fine


def _basic_model_file(model: str) -> Optional[Path]:
    """Return the path the whisper.cpp binary would look for, if any.

    whisper.cpp ships one ``ggml-<model>.bin`` per size. The file lives
    next to the binary; we check the binary directory, then fall back to
    the current working directory for development convenience.
    """
    bin_path = shutil.which("whisper") or shutil.which("whisper-cpp")
    if not bin_path:
        return None
    candidate = Path(bin_path).resolve().parent / f"ggml-{model}.bin"
    if candidate.exists():
        return candidate
    fallback = Path.cwd() / f"ggml-{model}.bin"
    if fallback.exists():
        return fallback
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _size_hint(tier: str, model: str) -> str:
    """Look up a human-readable size hint, falling back to "?"."""
    return _DOWNLOAD_SIZES.get(model, "?")


_DISCOVER_CACHE: Optional[Dict[str, ModelInfo]] = None
_DISCOVER_CACHE_AT: float = 0.0
_DISCOVER_CACHE_TTL: float = 2.0


def _invalidate_discover_cache() -> None:
    """Clear the discover_models cache. Intended for tests and post-install hooks."""
    global _DISCOVER_CACHE, _DISCOVER_CACHE_AT
    _DISCOVER_CACHE = None
    _DISCOVER_CACHE_AT = 0.0


def discover_models() -> Dict[str, ModelInfo]:
    """Return a dict keyed by ``"<tier>::<model>"`` for every known model.

    The dialog iterates this dict to populate its radio button groups.
    Results are cached for 2 seconds so rapid open/close cycles do not
    hammer the filesystem with 11 stat() calls each time.
    """
    global _DISCOVER_CACHE, _DISCOVER_CACHE_AT
    now = time.monotonic()
    if _DISCOVER_CACHE is not None and (now - _DISCOVER_CACHE_AT) < _DISCOVER_CACHE_TTL:
        return _DISCOVER_CACHE
    out: Dict[str, ModelInfo] = {}
    for tier, model, repo_id in _KNOWN_MODELS:
        key = f"{tier}::{model}"
        if tier == "Basic":
            path = _basic_model_file(model)
            available = path is not None
        else:
            repo = _repo_dir(repo_id)
            path = repo if repo.exists() else None
            available = path is not None
        out[key] = ModelInfo(
            tier=tier,
            model=model,
            path=str(path) if path is not None else None,
            available=available,
            size_hint=_size_hint(tier, model),
        )
    _DISCOVER_CACHE = out
    _DISCOVER_CACHE_AT = now
    return out


def model_info(tier: str, model: str) -> Optional[ModelInfo]:
    """Look up a single (tier, model) pair, or None if not catalogued."""
    return discover_models().get(f"{tier}::{model}")


def is_ready(tier: str, model: str) -> bool:
    """True if *tier* / *model* is already on disk and ready to use."""
    info = model_info(tier, model)
    return bool(info and info.available)


def ready_summary() -> Optional[ModelInfo]:
    """Return the first ready model, scanning fastest first.

    Used by the dialog when the user has no prior ``ai_setup_done`` to
    decide whether the polished settings view (something is already
    downloaded) or the wizard (nothing is) is the right opening view.
    """
    # Prefer the smaller, more common sizes; the user can still pick
    # any tier/model they want from the radio groups.
    preferred = [
        ("Strong", "small"),
        ("Strong", "base"),
        ("Strong", "tiny"),
        ("Strong", "medium"),
        ("Strong", "large-v3"),
        ("Strong", "large-v3-turbo"),
        ("Basic", "small"),
        ("Basic", "base"),
        ("Basic", "tiny"),
        ("Premium", "parakeet-onnx"),
        ("Canary", "canary"),
    ]
    all_info = discover_models()
    for tier, model in preferred:
        info = all_info.get(f"{tier}::{model}")
        if info and info.available:
            return info
    return None


def ready_summary_text() -> str:
    """Human-friendly one-liner for the dialog header card."""
    info = ready_summary()
    if info is None:
        return "No AI model downloaded yet. Let's set one up."
    if info.tier == "Basic":
        return f"Ready: {info.tier} tier, {info.model} model (whisper.cpp)"
    return f"Ready: {info.tier} tier, {info.model} model ({info.size_hint})"
