"""Canonical, token-driven descriptions of ChapterForge's controls.

``control_help.json`` is the single source of truth for what each control
does - it feeds two very different readers from the same data:

* The in-app F1 "Help on This Control" dialog (:mod:`chapterforge.context_help`),
  which wants the *live* answer: "what does this do, and what will happen if I
  activate it right now, given my current settings and the app's state?"
* The generated Control Reference documentation page (``tools/build_docs.py``),
  which wants a stable answer that reads naturally with no running app behind
  it: "what does this do, in general, and what's it set to out of the box?"

A description is a template string containing ``{token}`` placeholders.
Each token is declared once, in the schema's ``tokens`` table, as one of:

* ``setting`` - resolves against the user's current settings in the live
  dialog, and against :data:`chapterforge.settings.DEFAULTS` in
  documentation, so the reference always shows accurate out-of-the-box values.
* ``live`` - resolves by calling a named resolver (see ``_LIVE_RESOLVERS``
  below) against the running frame/player in the live dialog, and by
  substituting the schema's illustrative ``doc_example`` text in
  documentation - the reference reads as a believable snapshot rather than
  "Currently at 0:00 of 0:00" for an app that was never opened.

Controls whose meaning depends on build vs. edit mode - the chapter list's
Move Up/Down and Remove/Merge Up buttons are the prime example, since both
their label and behaviour change - carry ``variants`` keyed by mode instead
of a single template. The live dialog renders only the variant matching the
current mode (each variant's own text names the contrast, so the user always
hears how the *other* mode differs too); the reference renders both, since a
reader may meet the control in either mode.

This module owns resolution and rendering; it knows nothing about wx. The
wx-facing pieces - locating the focused control, the help dialog itself, and
the generic fallback for controls not in the schema - live in
:mod:`chapterforge.context_help`.
"""

from __future__ import annotations

import json
import os
import re
from typing import Callable, Dict, List, Tuple

from . import core
from . import settings as settings_mod

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "control_help.json")
_TOKEN_RE = re.compile(r"\{(\w+)\}")

_schema_cache: dict | None = None


def _schema() -> dict:
    global _schema_cache
    if _schema_cache is None:
        with open(_SCHEMA_PATH, encoding="utf-8") as fh:
            _schema_cache = json.load(fh)
    return _schema_cache


def _control(control_id: str) -> dict:
    for entry in _schema()["controls"]:
        if entry["id"] == control_id:
            return entry
    raise KeyError(f"No control_help entry for {control_id!r}")


def iter_controls() -> List[Tuple[str, str, str]]:
    """Return ``(id, title, category)`` for every control in the schema, in
    schema (display) order - what the documentation generator iterates."""
    return [(c["id"], c["title"], c["category"]) for c in _schema()["controls"]]


# ----------------------------------------------------------------------
# Live token resolvers - each takes the MainFrame and returns the live text
# to substitute. Registered by the name used in control_help.json's
# ``tokens[*].resolver``. Rebuilt fresh on every call (cheap), so they always
# reflect the app's current state rather than whatever was true when the
# F1 dialog was last opened.
# ----------------------------------------------------------------------

def _play_state(frame) -> str:
    p = frame.player
    if p.is_playing():
        return "playing"
    return "paused" if p.has_media() else "stopped"


def _chapter_position(frame) -> str:
    p = frame.player
    if not p.has_media() or not p.chapters:
        return "No audio is currently loaded."
    idx = p._chapter_index(p.playhead_ms())
    if 0 <= idx < len(p.chapters):
        return (f"Currently on chapter {idx + 1} of {len(p.chapters)}: "
                f"{p.chapters[idx].title}.")
    return f"{len(p.chapters)} chapter(s) loaded."


def _playback_position(frame) -> str:
    p = frame.player
    if not p.has_media():
        return "No audio is currently loaded."
    pos = core.format_timestamp(p.playhead_ms())
    length = core.format_timestamp(p._length())
    return f"Currently at {pos} of {length}.\n\n{_chapter_position(frame)}"


def _current_volume(frame) -> str:
    return f"{frame.player.vol_slider.GetValue()} percent"


def _current_speed(frame) -> str:
    p = frame.player
    idx = p.speed_choice.GetSelection()
    val = p.SPEED_VALUES[idx] if 0 <= idx < len(p.SPEED_VALUES) else 1.0
    return f"{val:g}x"


def _chapter_count(frame) -> str:
    return f"{frame._row_count()} chapter(s)"


def _mode_description(frame) -> str:
    if frame.mode == "edit":
        return "edit mode (you're adjusting an already-built master)"
    return "build mode (you're assembling a new master from source files)"


def _playhead_clause(frame) -> str:
    p = frame.player
    if p.has_media() and p.playhead_ms() > 0:
        return f" The player is currently at {core.format_timestamp(p.playhead_ms())}."
    return " Move the player to the desired split point first."


_LIVE_RESOLVERS: Dict[str, Callable[[object], str]] = {
    "play_state": _play_state,
    "chapter_position": _chapter_position,
    "playback_position": _playback_position,
    "current_volume": _current_volume,
    "current_speed": _current_speed,
    "chapter_count": _chapter_count,
    "mode_description": _mode_description,
    "playhead_clause": _playhead_clause,
}


# ----------------------------------------------------------------------
# Token resolution - one path reads live state, the other reads defaults
# and illustrative examples. Both funnel through the same templates, which
# is what keeps the dialog and the documentation from drifting apart.
# ----------------------------------------------------------------------

def _token_names(template: str) -> List[str]:
    # dict.fromkeys de-duplicates while preserving order (Python 3.7+).
    return list(dict.fromkeys(_TOKEN_RE.findall(template)))


def _resolve_live(name: str, frame) -> str:
    spec = _schema()["tokens"][name]
    if spec["kind"] == "setting":
        value = frame.settings.get(spec["key"], settings_mod.DEFAULTS[spec["key"]])
        return spec["format"].format(value=value)
    return _LIVE_RESOLVERS[spec["resolver"]](frame)


def _resolve_doc(name: str) -> str:
    spec = _schema()["tokens"][name]
    if spec["kind"] == "setting":
        return spec["format"].format(value=settings_mod.DEFAULTS[spec["key"]])
    return spec["doc_example"]


def _fill(template: str, resolve: Callable[[str], str]) -> str:
    values = {name: resolve(name) for name in _token_names(template)}
    return template.format(**values) if values else template


def render_live(control_id: str, frame) -> Tuple[str, str]:
    """The answer for someone using the app right now: (title, body) with
    every token resolved against current settings and live app state."""
    entry = _control(control_id)
    if "variants" in entry:
        mode = "edit" if frame.mode == "edit" else "build"
        return entry["title"], entry["variants"][mode]
    return entry["title"], _fill(entry["template"], lambda n: _resolve_live(n, frame))


def render_doc(control_id: str) -> Tuple[str, str]:
    """The answer for the documentation: (title, body) with setting-tokens
    resolved against documented defaults and live-tokens against illustrative
    examples, so the page reads naturally with no app running behind it.
    Mode-dependent controls render both variants, since a reader may meet
    the control in either mode."""
    entry = _control(control_id)
    if "variants" in entry:
        return entry["title"], entry["variants"]["build"] + "\n\n" + entry["variants"]["edit"]
    return entry["title"], _fill(entry["template"], _resolve_doc)


def generate_markdown() -> str:
    """Render the full Control Reference as a Markdown document, grouped by
    category in schema order. This is what ``tools/build_docs.py`` writes to
    ``docs/CONTROL_REFERENCE.md`` before converting it to HTML alongside the
    other pages - generated fresh from the schema on every doc build, so it
    can never say something the in-app F1 help doesn't (or vice versa)."""
    lines = [
        "# Control Reference",
        "",
        "This page is generated from the same descriptions ChapterForge's "
        "in-app **Help on This Control** (press F1 on any focused control) "
        "shows you - it can't drift out of sync with what the app actually "
        "says. The live dialog tailors its wording to your current settings "
        "and the app's state at the moment you press F1; the examples below "
        "use the application's documented defaults instead, so this page "
        "reads sensibly on its own.",
        "",
    ]
    current_category = None
    for control_id, _title, category in iter_controls():
        if category != current_category:
            lines.append(f"## {category}")
            lines.append("")
            current_category = category
        title, body = render_doc(control_id)
        lines.append(f"### {title}")
        lines.append("")
        lines.extend(body.split("\n"))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
