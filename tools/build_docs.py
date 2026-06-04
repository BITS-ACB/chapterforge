#!/usr/bin/env python3
"""Generate accessible, self-contained HTML documentation from the project's
Markdown files.

This is a small, dependency-free Markdown -> HTML converter that supports the
subset of Markdown used by ChapterForge's docs: ATX headings, fenced code
blocks, GitHub-style pipe tables, ordered/unordered lists (including task
lists), horizontal rules, paragraphs, and inline code/bold/links.

Output is written to ``docs/html/`` as standalone HTML pages (CSS embedded, no
network needed) plus an ``index.html``. The pages are designed to be readable
with a screen reader: a single ``<h1>`` per page, a "skip to content" link, a
landmark ``<main>``, an in-page table of contents, visible focus styles and a
``prefers-color-scheme`` aware theme.

Run it from the repo root:

    python tools/build_docs.py
"""

from __future__ import annotations

import html
import re
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "docs", "html")

FOOTER = ("\u00a9 2026 Blind Information Technology Specialists (BITS). "
          "ChapterForge documentation, generated from Markdown.")

# (source markdown path, output html filename, nav label, page title)
PAGES = [
    ("README.md", "index.html", "Home", "ChapterForge"),
    (os.path.join("docs", "USER_GUIDE.md"), "USER_GUIDE.html",
     "User Guide", "ChapterForge \u2014 User Guide"),
    (os.path.join("docs", "DEPLOYMENT.md"), "DEPLOYMENT.html",
     "Deployment", "ChapterForge \u2014 Deployment Guide"),
    ("CHANGELOG.md", "CHANGELOG.html", "Changelog", "ChapterForge \u2014 Changelog"),
    ("THIRD_PARTY.md", "THIRD_PARTY.html", "Third-Party Notices",
     "ChapterForge \u2014 Third-Party Notices"),
]

# Map known local markdown targets to their generated HTML page.
MD_TO_HTML = {
    "readme.md": "index.html",
    "docs/user_guide.md": "USER_GUIDE.html",
    "user_guide.md": "USER_GUIDE.html",
    "docs/deployment.md": "DEPLOYMENT.html",
    "deployment.md": "DEPLOYMENT.html",
    "changelog.md": "CHANGELOG.html",
    "third_party.md": "THIRD_PARTY.html",
    "license": "LICENSE.txt",
}


def slugify(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-") or "section"


def _map_link(url: str) -> str:
    """Rewrite local .md links to their generated .html equivalents."""
    if re.match(r"^[a-z]+://", url) or url.startswith("#") or url.startswith("mailto:"):
        return url
    base, _, frag = url.partition("#")
    key = base.lower()
    if key in MD_TO_HTML:
        target = MD_TO_HTML[key]
    else:
        # Leave unknown links (e.g. samples/README.md) untouched rather than
        # inventing a page that was never generated.
        return url
    return target + (("#" + frag) if frag else "")


def render_inline(text: str) -> str:
    """Render inline Markdown (code, links, bold, italic) to safe HTML."""
    code_spans = []

    def stash(match):
        code_spans.append(match.group(1))
        return f"\x00{len(code_spans) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = html.escape(text)

    def link(match):
        label, url = match.group(1), _map_link(match.group(2))
        return f'<a href="{html.escape(url, quote=True)}">{label}</a>'

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\s)([^*]+?)\*(?!\*)", r"<em>\1</em>", text)

    def restore(match):
        return f"<code>{html.escape(code_spans[int(match.group(1))])}</code>"

    return re.sub(r"\x00(\d+)\x00", restore, text)


def _is_table_sep(line: str) -> bool:
    return bool(re.match(r"^\s*\|?\s*:?-{3,}.*$", line)) and "-" in line and "|" in line


def _split_row(line: str):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def convert(md: str):
    """Convert Markdown text to (body_html, toc_entries)."""
    lines = md.split("\n")
    out = []
    toc = []
    i = 0
    n = len(lines)
    list_stack = []

    def close_list(stack):
        while stack:
            out.append(f"</{stack.pop()}>")

    while i < n:
        line = lines[i]

        # Fenced code block
        if re.match(r"^```(.*)$", line):
            close_list(list_stack)
            i += 1
            buf = []
            while i < n and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1  # skip closing fence
            code = html.escape("\n".join(buf))
            out.append(f"<pre><code>{code}</code></pre>")
            continue

        # Table
        if "|" in line and i + 1 < n and _is_table_sep(lines[i + 1]):
            close_list(list_stack)
            header = _split_row(line)
            i += 2
            rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(_split_row(lines[i]))
                i += 1
            out.append("<table>")
            out.append("<thead><tr>" +
                       "".join(f"<th>{render_inline(c)}</th>" for c in header) +
                       "</tr></thead>")
            out.append("<tbody>")
            for r in rows:
                cells = "".join(f"<td>{render_inline(c)}</td>" for c in r)
                out.append(f"<tr>{cells}</tr>")
            out.append("</tbody></table>")
            continue

        # Headings
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            close_list(list_stack)
            level = len(m.group(1))
            text = m.group(2).strip()
            inner = render_inline(text)
            if level == 1:
                out.append(f"<h1>{inner}</h1>")
            else:
                slug = slugify(text)
                out.append(f'<h{level} id="{slug}">{inner}</h{level}>')
                if level in (2, 3):
                    toc.append((level, slug, text))
            i += 1
            continue

        # Horizontal rule
        if re.match(r"^\s*---+\s*$", line):
            close_list(list_stack)
            out.append("<hr>")
            i += 1
            continue

        # Task list / unordered list
        m = re.match(r"^(\s*)[-*]\s+(.*)$", line)
        if m:
            text = m.group(2)
            if "ul" not in list_stack[-1:]:
                close_list(list_stack)
                out.append("<ul>")
                list_stack.append("ul")
            task = re.match(r"^\[([ xX])\]\s+(.*)$", text)
            if task:
                checked = " checked" if task.group(1).lower() == "x" else ""
                out.append(
                    f'<li class="task"><input type="checkbox" disabled{checked}> '
                    f"{render_inline(task.group(2))}</li>")
            else:
                out.append(f"<li>{render_inline(text)}</li>")
            i += 1
            continue

        # Ordered list
        m = re.match(r"^(\s*)\d+\.\s+(.*)$", line)
        if m:
            if "ol" not in list_stack[-1:]:
                close_list(list_stack)
                out.append("<ol>")
                list_stack.append("ol")
            out.append(f"<li>{render_inline(m.group(2))}</li>")
            i += 1
            continue

        # Blank line ends a list / paragraph
        if not line.strip():
            close_list(list_stack)
            i += 1
            continue

        # Paragraph (gather consecutive plain lines)
        close_list(list_stack)
        para = [line]
        i += 1
        while i < n and lines[i].strip() and not re.match(
                r"^(#{1,6}\s|```|\s*[-*]\s|\s*\d+\.\s|\s*---+\s*$)", lines[i]) \
                and not ("|" in lines[i] and i + 1 < n and _is_table_sep(lines[i + 1])):
            para.append(lines[i])
            i += 1
        out.append("<p>" + render_inline(" ".join(s.strip() for s in para)) + "</p>")

    close_list(list_stack)
    return "\n".join(out), toc


CSS = """
:root {
  --bg: #ffffff; --fg: #1b1b1b; --muted: #555; --accent: #0b5fa5;
  --border: #d0d7de; --code-bg: #f3f4f6; --nav-bg: #f6f8fa;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d1117; --fg: #e6edf3; --muted: #9da7b1; --accent: #58a6ff;
    --border: #30363d; --code-bg: #161b22; --nav-bg: #161b22;
  }
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: 1rem/1.6 -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
}
.skip {
  position: absolute; left: -999px; top: 0; background: var(--accent);
  color: #fff; padding: .6rem 1rem; z-index: 100;
}
.skip:focus { left: 0; }
header.site {
  border-bottom: 1px solid var(--border); background: var(--nav-bg);
  padding: .5rem 1rem;
}
header.site nav ul {
  list-style: none; display: flex; flex-wrap: wrap; gap: .25rem 1rem;
  margin: 0; padding: 0;
}
header.site nav a { text-decoration: none; color: var(--accent); padding: .25rem 0; }
header.site nav a[aria-current="page"] { font-weight: 700; text-decoration: underline; }
.wrap { max-width: 52rem; margin: 0 auto; padding: 1rem 1.25rem 4rem; }
main { outline: none; }
h1 { font-size: 2rem; line-height: 1.2; margin: 1rem 0 .5rem; }
h2 { font-size: 1.5rem; margin-top: 2.2rem; border-bottom: 1px solid var(--border); padding-bottom: .2rem; }
h3 { font-size: 1.2rem; margin-top: 1.6rem; }
a { color: var(--accent); }
a:focus-visible, button:focus-visible, input:focus-visible {
  outline: 3px solid var(--accent); outline-offset: 2px;
}
code { background: var(--code-bg); padding: .1rem .35rem; border-radius: 4px;
  font-family: Consolas, "SFMono-Regular", Menlo, monospace; font-size: .9em; }
pre { background: var(--code-bg); padding: 1rem; border-radius: 8px;
  overflow: auto; border: 1px solid var(--border); }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid var(--border); padding: .5rem .7rem; text-align: left; vertical-align: top; }
thead th { background: var(--nav-bg); }
li.task { list-style: none; margin-left: -1.2rem; }
li.task input { margin-right: .4rem; }
nav.toc { background: var(--nav-bg); border: 1px solid var(--border);
  border-radius: 8px; padding: .75rem 1rem; margin: 1.5rem 0; }
nav.toc p { margin: 0 0 .4rem; font-weight: 700; }
nav.toc ul { margin: 0; padding-left: 1.2rem; }
nav.toc li.lvl3 { margin-left: 1rem; list-style: circle; }
footer.site { color: var(--muted); border-top: 1px solid var(--border);
  margin-top: 3rem; padding: 1rem 1.25rem; font-size: .9rem; }
""".strip()


def build_nav(current: str) -> str:
    items = []
    for _src, out_name, label, _title in PAGES:
        cur = ' aria-current="page"' if out_name == current else ""
        items.append(f'<li><a href="{out_name}"{cur}>{html.escape(label)}</a></li>')
    return ('<header class="site"><nav aria-label="Documentation"><ul>'
            + "".join(items) + "</ul></nav></header>")


def build_toc(toc) -> str:
    if len(toc) < 2:
        return ""
    items = []
    for level, slug, text in toc:
        cls = ' class="lvl3"' if level == 3 else ""
        items.append(f'<li{cls}><a href="#{slug}">{html.escape(text)}</a></li>')
    return ('<nav class="toc" aria-label="On this page"><p>On this page</p><ul>'
            + "".join(items) + "</ul></nav>")


def page_html(title: str, nav: str, toc_html: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
{nav}
<div class="wrap">
<main id="main" tabindex="-1">
{toc_html}
{body}
</main>
</div>
<footer class="site">{html.escape(FOOTER)}</footer>
</body>
</html>
"""


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    built = []
    for src, out_name, _label, title in PAGES:
        src_path = os.path.join(REPO_ROOT, src)
        if not os.path.isfile(src_path):
            print(f"  skip (missing): {src}")
            continue
        with open(src_path, encoding="utf-8") as fh:
            md = fh.read()
        body, toc = convert(md)
        nav = build_nav(out_name)
        html_doc = page_html(title, nav, build_toc(toc), body)
        out_path = os.path.join(OUT_DIR, out_name)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(html_doc)
        built.append(out_name)
        print(f"  wrote docs/html/{out_name}")

    lic = os.path.join(REPO_ROOT, "LICENSE")
    if os.path.isfile(lic):
        import shutil
        shutil.copyfile(lic, os.path.join(OUT_DIR, "LICENSE.txt"))
        print("  wrote docs/html/LICENSE.txt")

    print(f"Done. {len(built)} page(s) in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
