"""Tests for the auto-update download/apply helpers in chapterforge.updates.

These never touch the network: they exercise URL validation, asset selection,
filename sanitising and installer-launch guards.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chapterforge import updates  # noqa: E402
from chapterforge.updates import ReleaseInfo, UpdateCheckError  # noqa: E402

WIN = sys.platform.startswith("win")
MAC = sys.platform == "darwin"


def _release(url):
    return ReleaseInfo(version="9.9.9", download_url=url, published_at="",
                       notes="", prerelease=False)


def test_is_installable_asset_platform():
    exe = "https://github.com/bits-acb/chapterforge/releases/download/v9/Setup.exe"
    dmg = "https://github.com/bits-acb/chapterforge/releases/download/v9/App.dmg"
    if WIN:
        assert updates.is_installable_asset(exe) is True
        assert updates.is_installable_asset(dmg) is False
    elif MAC:
        assert updates.is_installable_asset(dmg) is True
        assert updates.is_installable_asset(exe) is False
    else:
        assert updates.is_installable_asset(exe) is False


def test_is_installable_asset_rejects_archives_and_untrusted():
    zip_url = ("https://github.com/bits-acb/chapterforge/releases/download/"
               "v9/App.zip")
    assert updates.is_installable_asset(zip_url) is False
    assert updates.is_installable_asset("http://github.com/x/y/Setup.exe") is False
    assert updates.is_installable_asset("https://evil.example/Setup.exe") is False
    assert updates.is_installable_asset("") is False


def test_safe_asset_name():
    url = "https://github.com/o/r/releases/download/v9/Chapter Forge-Setup.exe"
    assert updates._safe_asset_name(url) == "Chapter Forge-Setup.exe"
    assert updates._safe_asset_name("https://github.com/o/r/") == "ChapterForge-Setup"


def test_download_rejects_non_https(tmp_path):
    with pytest.raises(UpdateCheckError):
        updates.download_release_asset(
            _release("http://github.com/x/y/Setup.exe"), dest_dir=str(tmp_path))


def test_download_rejects_untrusted_host(tmp_path):
    with pytest.raises(UpdateCheckError):
        updates.download_release_asset(
            _release("https://evil.example/Setup.exe"), dest_dir=str(tmp_path))


def test_launch_installer_missing_file(tmp_path):
    with pytest.raises(UpdateCheckError):
        updates.launch_installer(str(tmp_path / "does-not-exist.exe"))
