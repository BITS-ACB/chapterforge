"""Podcast RSS 2.0 + iTunes / Podcasting 2.0 feed generator.

Generates a self-contained .rss file and an optional .chapters.json sidecar
alongside the built audio. Podcasters who self-host their feed can manage
their entire pipeline from ChapterForge.
"""
from __future__ import annotations

import io
import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from .core import BuildResult, Tags

_ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
_PODCAST_NS = "https://podcastindex.org/namespace/1.0"

ET.register_namespace("itunes", _ITUNES_NS)
ET.register_namespace("podcast", _PODCAST_NS)


def _sub(parent: ET.Element, tag: str, text: str = "", **attrs) -> ET.Element:
    el = ET.SubElement(parent, tag, attrs)
    if text:
        el.text = text
    return el


def _itunes(tag: str) -> str:
    return f"{{{_ITUNES_NS}}}{tag}"


def _podcast(tag: str) -> str:
    return f"{{{_PODCAST_NS}}}{tag}"


def generate_rss(
    result: BuildResult,
    tags: Tags,
    media_url: str,
    *,
    feed_url: str = "",
    description: str = "",
    cover_url: str = "",
    narrator: str = "",
    series_title: str = "",
    series_index: str = "",
) -> str:
    """Return an RSS 2.0 + iTunes + Podcasting 2.0 XML string.

    Args:
        result:      BuildResult from build_master().
        tags:        Tags written to the audio file.
        media_url:   Public URL where the audio file is hosted.
        feed_url:    The feed's own canonical URL (atom:self link).
        description: Episode description / show notes.
        cover_url:   Public URL of the cover image.
        narrator:    Narrator name (written as itunes:author if artist differs).
        series_title: Podcast or series name.
        series_index: Episode / series position.
    """
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")

    _sub(channel, "title", tags.title or "Untitled")
    _sub(channel, "description", description or tags.comment or tags.title or "")
    if feed_url:
        _sub(channel, "link", feed_url)
    if tags.genre:
        # iTunes category carries the genre in a "text" attribute, not as
        # element text: <itunes:category text="Fiction"/>.
        ET.SubElement(channel, _itunes("category"), {"text": tags.genre})
    if tags.artist:
        _sub(channel, _itunes("author"), tags.artist)
    if narrator and narrator != tags.artist:
        _sub(channel, _itunes("author"), narrator)
    _sub(channel, _itunes("explicit"), "false")

    if cover_url:
        img_el = ET.SubElement(channel, "image")
        _sub(img_el, "url", cover_url)
        _sub(img_el, "title", tags.title or "")
        _sub(img_el, "link", feed_url or "")
        ET.SubElement(channel, _itunes("image"), href=cover_url)

    pub_date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    total_s = result.total_ms // 1000

    item = ET.SubElement(channel, "item")
    _sub(item, "title", tags.title or "Untitled")
    _sub(item, "description", description or tags.comment or "")
    _sub(item, "pubDate", pub_date)
    _sub(item, _itunes("duration"), str(total_s))
    if series_title:
        _sub(item, _itunes("title"), tags.title or "")
        _sub(item, _itunes("episode"), series_index or "1")
        _sub(item, _itunes("season"), "1")

    file_size = "0"
    if os.path.isfile(result.output_path):
        file_size = str(os.path.getsize(result.output_path))
    ext = os.path.splitext(result.output_path)[1].lower()
    mime = "audio/x-m4b" if ext in {".m4b", ".m4a"} else "audio/mpeg"
    ET.SubElement(item, "enclosure", url=media_url, type=mime, length=file_size)

    # Podcasting 2.0 chapters link (points to the .chapters.json sidecar)
    if result.chapters:
        chapters_url = media_url.rsplit(".", 1)[0] + ".chapters.json"
        ET.SubElement(item, _podcast("chapters"), url=chapters_url,
                      type="application/json+chapters")

    ET.indent(rss, space="  ")
    buf = io.StringIO()
    buf.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    ET.ElementTree(rss).write(buf, encoding="unicode", xml_declaration=False)
    return buf.getvalue()


def write_rss(
    result: BuildResult,
    tags: Tags,
    media_url: str,
    **kwargs,
) -> str:
    """Write the RSS feed as a .rss file alongside the output audio.

    Returns the path of the written file.
    """
    xml = generate_rss(result, tags, media_url, **kwargs)
    rss_path = os.path.splitext(result.output_path)[0] + ".rss"
    with open(rss_path, "w", encoding="utf-8") as fh:
        fh.write(xml)
    return rss_path


def write_chapters_json(result: BuildResult) -> str:
    """Write a Podcasting 2.0 chapters JSON sidecar.

    Returns the path of the written file.
    """
    chapters_data = {
        "version": "1.2.0",
        "chapters": [
            {
                "startTime": ch.start_ms / 1000,
                "title": ch.title,
                **({"url": ch.url} if ch.url else {}),
                **({"img": ch.img} if ch.img else {}),
            }
            for ch in result.chapters
        ],
    }
    json_path = os.path.splitext(result.output_path)[0] + ".chapters.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(chapters_data, fh, indent=2, ensure_ascii=False)
    return json_path
