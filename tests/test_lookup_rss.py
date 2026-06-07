"""Regression tests for the metadata-lookup query builder and RSS generation.

These cover two bugs fixed during the pre-release audit:
  - MusicBrainz queries were double URL-encoded (quote() inside urlencode()),
    so no search ever matched.
  - The iTunes category was written as element text instead of the required
    text="" attribute, producing a malformed feed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chapterforge import lookup  # noqa: E402
from chapterforge import rss  # noqa: E402
from chapterforge.core import BuildResult, Chapter, Tags  # noqa: E402


def test_mb_escape_handles_special_chars():
    # Backslash and double-quote are the Lucene specials we wrap terms in.
    assert lookup._mb_escape('A "quoted" title') == 'A \\"quoted\\" title'
    assert lookup._mb_escape("back\\slash") == "back\\\\slash"


def test_musicbrainz_query_not_double_encoded(monkeypatch):
    """The raw Lucene query must reach _mb_get unescaped (no %20 inside)."""
    captured = {}

    def fake_mb_get(path, params):
        captured["path"] = path
        captured["params"] = params
        return {"releases": []}

    monkeypatch.setattr(lookup, "_mb_get", fake_mb_get)
    lookup.search_musicbrainz("The Hobbit", "Tolkien")

    query = captured["params"]["query"]
    # The query should contain readable terms, not pre-percent-encoded ones.
    assert "The Hobbit" in query
    assert "Tolkien" in query
    assert "%20" not in query  # would indicate the old double-encoding bug


def test_rss_itunes_category_is_attribute():
    result = BuildResult(
        output_path="book.mp3",
        chapters=[Chapter(index=0, title="One", start_ms=0, end_ms=1000)],
        total_ms=1000,
        reencoded=True,
    )
    tags = Tags(title="My Book", artist="Author", genre="Fiction")
    xml = rss.generate_rss(result, tags, "https://example.com/book.mp3")
    # The genre must be an attribute on itunes:category, not element text.
    assert 'category text="Fiction"' in xml
    assert "<itunes:category>Fiction" not in xml


def test_rss_enclosure_present():
    result = BuildResult(
        output_path="book.mp3",
        chapters=[Chapter(index=0, title="One", start_ms=0, end_ms=1000)],
        total_ms=1000,
        reencoded=True,
    )
    tags = Tags(title="My Book")
    xml = rss.generate_rss(result, tags, "https://example.com/book.mp3")
    assert "enclosure" in xml
    assert "https://example.com/book.mp3" in xml
    assert 'type="audio/mpeg"' in xml
