"""Unit tests for the AI model discovery module.

The detector must work without any of the heavy ML dependencies
installed (faster-whisper, onnxruntime) and must not touch the real
HuggingFace cache. We redirect both the HuggingFace hub root and the
``HOME`` environment variable into ``tmp_path`` so the on-disk
"available" check exercises a real directory layout.
"""

from __future__ import annotations

import os
import sys
import shutil
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chapterforge.ai import discovery  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_home(monkeypatch, tmp_path):
    """Point ``Path.home()`` and HF env vars at a temporary directory.

    The discovery module computes ``~/.cache/huggingface/hub`` from
    ``Path.home()`` unless ``HF_HOME`` is set, so flipping both keeps
    every code path inside the test sandbox.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def _make_repo(fake_home: Path, repo_id: str) -> Path:
    """Create the directory layout HuggingFace uses for a downloaded repo.

    Uses the flat ``~/.cache/huggingface/models--<org>--<name>/`` layout,
    which is what faster-whisper actually produces on Windows and which
    the discovery module's fallback path detects.
    """
    repo = fake_home / ".cache" / "huggingface" / (
        "models--" + repo_id.replace("/", "--")
    ) / "snapshots" / "main"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "config.json").write_text("{}", encoding="utf-8")
    return fake_home / ".cache" / "huggingface" / (
        "models--" + repo_id.replace("/", "--")
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_discover_returns_all_canonical_models(fake_home):
    """Every (tier, model) the dialog knows about must show up in the dict."""
    out = discovery.discover_models()
    for key in ("Strong::small", "Strong::medium", "Premium::parakeet-onnx",
                "Basic::tiny", "Canary::canary"):
        assert key in out, f"missing {key!r} from discover_models() output"


def test_models_marked_unavailable_when_nothing_on_disk(fake_home):
    """On a fresh fake home, no model should be marked available."""
    out = discovery.discover_models()
    assert all(not info.available for info in out.values()), (
        "expected every model to be unavailable on a clean cache, "
        f"got: {[(k, v.available) for k, v in out.items()]}"
    )
    assert discovery.is_ready("Strong", "small") is False
    assert discovery.ready_summary() is None
    assert "No AI model" in discovery.ready_summary_text()


def test_faster_whisper_repo_marks_strong_models_available(fake_home):
    """Drop a fake HF hub repo on disk and the matching model is ready."""
    _make_repo(fake_home, "Systran/faster-whisper-small")
    out = discovery.discover_models()
    assert out["Strong::small"].available is True
    assert out["Strong::small"].path is not None
    # Unrelated models in the same tier stay unavailable.
    assert out["Strong::medium"].available is False
    assert out["Strong::base"].available is False


def test_ready_summary_prefers_smaller_strong_model(fake_home):
    """When several models are present, the smallest Strong one is reported."""
    _make_repo(fake_home, "Systran/faster-whisper-large-v3")
    _make_repo(fake_home, "Systran/faster-whisper-small")
    info = discovery.ready_summary()
    assert info is not None
    assert info.tier == "Strong"
    assert info.model == "small"


def test_hf_home_env_overrides_home(monkeypatch, tmp_path):
    """``HF_HOME`` should win over the user home directory."""
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "ignored"))
    repo = tmp_path / "huggingface" / "models--Systran--faster-whisper-base" / "snapshots" / "main"
    repo.mkdir(parents=True)
    (repo / "config.json").write_text("{}")
    out = discovery.discover_models()
    assert out["Strong::base"].available is True


def test_basic_tier_needs_binary_and_model_file(monkeypatch, tmp_path):
    """whisper.cpp readiness needs both the binary on PATH and the model file."""
    # No binary: even if the .bin is on disk, the tier is not ready.
    monkeypatch.setattr(shutil, "which", lambda name: None)
    info = discovery.model_info("Basic", "small")
    assert info is not None
    assert info.available is False

    # With a fake binary in tmp_path and a matching ggml-small.bin next to
    # it, the model should report as available.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "whisper").write_text("")
    (bin_dir / "ggml-small.bin").write_text("")
    monkeypatch.setattr(
        shutil, "which", lambda name: str(bin_dir / "whisper") if name in ("whisper", "whisper-cpp") else None
    )
    # Discovery's _basic_model_file uses Path.cwd() as a fallback; switch
    # into the directory containing the .bin for that branch to also work.
    monkeypatch.chdir(bin_dir)
    info = discovery.model_info("Basic", "small")
    assert info is not None
    assert info.available is True
    assert info.path is not None
