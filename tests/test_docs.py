"""Tests for the HTML documentation generator and runtime resolver."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import build_docs  # noqa: E402
from chapterforge import docs  # noqa: E402


def test_render_inline_escapes_and_formats():
    out = build_docs.render_inline("Use **bold**, `code` & a <tag>.")
    assert "<strong>bold</strong>" in out
    assert "<code>code</code>" in out
    assert "&amp;" in out and "&lt;tag&gt;" in out


def test_render_inline_rewrites_md_links():
    out = build_docs.render_inline("See [the guide](docs/USER_GUIDE.md).")
    assert 'href="USER_GUIDE.html"' in out
    assert ".md" not in out


def test_render_inline_keeps_external_links():
    out = build_docs.render_inline("[site](https://example.com/page)")
    assert 'href="https://example.com/page"' in out


def test_convert_table_and_headings():
    md = (
        "# Title\n\n"
        "## Section\n\n"
        "| Key | Action |\n"
        "| --- | --- |\n"
        "| Ctrl+O | Open |\n"
    )
    body, toc = build_docs.convert(md)
    assert "<h1>Title</h1>" in body
    assert '<h2 id="section">Section</h2>' in body
    assert "<table>" in body and "<th>Action</th>" in body
    assert "<td>Open</td>" in body
    assert ("section" in slug for _l, slug, _t in toc)


def test_convert_task_list():
    body, _ = build_docs.convert("- [x] done\n- [ ] todo\n")
    assert 'type="checkbox" disabled checked' in body
    assert body.count("<li") == 2


def test_convert_code_block_escapes():
    body, _ = build_docs.convert("```\n<a> & 'x'\n```\n")
    assert "<pre><code>" in body
    assert "&lt;a&gt;" in body


def test_runtime_docs_resolves_generated_pages():
    # tools/build_docs.py output should be discoverable by chapterforge.docs.
    assert docs.docs_dir() is not None
    assert docs.doc_path(docs.USER_GUIDE) is not None
    assert docs.doc_path(docs.HOME) is not None
