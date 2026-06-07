"""Metadata lookup from free public APIs.

Searches MusicBrainz (musicbrainz.org) and Open Library (openlibrary.org)
by title and artist/author. Both APIs are free with no authentication.

MusicBrainz rate limit: 1 request per second per IP.
Open Library: no stated per-second limit.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import List

_USER_AGENT = "ChapterForge/1.0 (info@chapterforge.org)"
_MB_BASE = "https://musicbrainz.org/ws/2"
_OL_BASE = "https://openlibrary.org"
_TIMEOUT = 12

_last_mb_req: float = 0.0


@dataclass
class LookupResult:
    title: str
    artist: str
    album: str
    album_artist: str
    genre: str
    year: str
    narrator: str = ""
    series_title: str = ""
    series_index: str = ""
    source: str = ""
    score: int = 0


def _http_get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _mb_get(path: str, params: dict) -> dict:
    global _last_mb_req
    elapsed = time.monotonic() - _last_mb_req
    if elapsed < 1.05:
        time.sleep(1.05 - elapsed)
    qs = urllib.parse.urlencode({**params, "fmt": "json"})
    data = _http_get(f"{_MB_BASE}/{path}?{qs}")
    _last_mb_req = time.monotonic()
    return data


def _mb_escape(value: str) -> str:
    """Escape Lucene special characters in a MusicBrainz query term."""
    # Backslash first, then the quote we wrap terms in.
    return value.replace("\\", "\\\\").replace('"', '\\"')


def search_musicbrainz(title: str, artist: str = "") -> List[LookupResult]:
    """Search MusicBrainz for releases matching *title* and optional *artist*."""
    # Build the raw Lucene query; urlencode (in _mb_get) does the URL escaping.
    # Do NOT pre-quote here or the term gets double-encoded and never matches.
    query_parts = [f'release:"{_mb_escape(title)}"']
    if artist:
        query_parts.append(f'artist:"{_mb_escape(artist)}"')
    params = {"query": " AND ".join(query_parts), "limit": 5}
    try:
        data = _mb_get("release", params)
    except Exception:
        return []

    results = []
    for rel in data.get("releases", []):
        score = int(rel.get("score", 0))
        rel_title = rel.get("title", "")
        credits = rel.get("artist-credit", [])
        rel_artist = credits[0].get("name", "") if credits else ""
        date = (rel.get("date") or "")[:4]
        results.append(LookupResult(
            title=rel_title,
            artist=rel_artist,
            album=rel_title,
            album_artist=rel_artist,
            genre="",
            year=date,
            source="MusicBrainz",
            score=score,
        ))
    return results


def search_open_library(title: str, author: str = "") -> List[LookupResult]:
    """Search Open Library for books matching *title* and optional *author*."""
    params: dict = {"title": title, "limit": 5, "fields": "title,author_name,first_publish_year,subject,series"}
    if author:
        params["author"] = author
    try:
        data = _http_get(f"{_OL_BASE}/search.json?{urllib.parse.urlencode(params)}")
    except Exception:
        return []

    results = []
    for doc in data.get("docs", [])[:5]:
        doc_title = doc.get("title", "")
        authors = doc.get("author_name") or []
        doc_author = authors[0] if authors else ""
        year = str(doc.get("first_publish_year") or "")
        subjects = doc.get("subject") or []
        genre = subjects[0] if subjects else ""
        series_list = doc.get("series") or []
        series = series_list[0] if series_list else ""
        title_lower = title.lower().strip()
        score = 95 if doc_title.lower().strip() == title_lower else 75
        results.append(LookupResult(
            title=doc_title,
            artist=doc_author,
            album=doc_title,
            album_artist=doc_author,
            genre=genre,
            year=year,
            series_title=series,
            source="Open Library",
            score=score,
        ))
    return results


def search(title: str, artist: str = "", prefer_books: bool = True) -> List[LookupResult]:
    """Search both MusicBrainz and Open Library; return merged list by score.

    Set *prefer_books* = False for music/podcast content (queries MusicBrainz
    first).
    """
    results: List[LookupResult] = []
    if prefer_books:
        results += search_open_library(title, artist)
    results += search_musicbrainz(title, artist)
    if not prefer_books:
        results += search_open_library(title, artist)
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:8]
