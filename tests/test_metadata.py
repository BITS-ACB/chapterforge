"""Tests for organization/branding metadata used by the About window."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chapterforge  # noqa: E402


def test_org_and_copyright_metadata():
    assert chapterforge.__org_short__ == "BITS"
    assert "Blind Information Technology Solutions" in chapterforge.__org__
    assert "2026" in chapterforge.__copyright__
    assert "BITS" in chapterforge.__copyright__


def test_version_present():
    assert chapterforge.__version__
    # Three dotted-ish parts is the convention; at least non-empty string.
    assert isinstance(chapterforge.__version__, str)


def test_services_recognized():
    urls = {url for _label, _desc, url in chapterforge.SERVICES}
    assert "https://www.joinbits.org" in urls
    assert "http://www.letitglow.app" in urls
    assert "https://www.community-access.org" in urls
    # Each service has a human-readable label and description.
    for label, desc, url in chapterforge.SERVICES:
        assert label and desc and url.startswith("http")
