"""Integration test for the feedback-hub GitHub token.

Skipped unless CHAPTERFORGE_GITHUB_TOKEN is set. Creates a real issue on
BITS-ACB/chapterforge and immediately closes it to verify the token has the
correct permissions without polluting the issue tracker.
"""

import json
import os
import urllib.request

import pytest

_TOKEN = os.environ.get("CHAPTERFORGE_GITHUB_TOKEN", "")
_REPO = "BITS-ACB/chapterforge"

pytestmark = pytest.mark.skipif(
    not _TOKEN, reason="CHAPTERFORGE_GITHUB_TOKEN not set"
)


def _gh(method, path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read())


def test_token_can_create_and_close_issue():
    status, issue = _gh(
        "POST",
        f"/repos/{_REPO}/issues",
        {
            "title": "[CI] feedback-hub token smoke test",
            "body": "Automated integration test -- closing immediately.",
            "labels": ["needs-triage"],
        },
    )
    assert status == 201, f"Expected 201 Created, got {status}"

    close_status, _ = _gh(
        "PATCH",
        f"/repos/{_REPO}/issues/{issue['number']}",
        {"state": "closed"},
    )
    assert close_status == 200, f"Expected 200 when closing issue #{issue['number']}, got {close_status}"
