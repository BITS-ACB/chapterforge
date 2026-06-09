"""Tests for chapterforge.a11y accessibility module."""

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chapterforge import a11y


def _reset_engine():
    """Reset the module-level engine so tests start clean."""
    a11y._engine = None
    a11y._handler = None
    a11y._transcript.clear()
    a11y._transcript_enabled = False


def test_announce_strips_control_characters():
    _reset_engine()
    a11y.enable_transcript_capture(True)
    a11y.announce("hello\x00world\x1f!")
    entries = a11y.transcript_entries()
    assert entries == ["hello world!"] or all("\x00" not in e and "\x1f" not in e for e in entries)
    _reset_engine()


def test_announce_empty_string_is_no_op():
    _reset_engine()
    a11y.enable_transcript_capture(True)
    a11y.announce("")
    a11y.announce("   ")
    a11y.announce("\x00\x01")
    assert a11y.transcript_entries() == []
    _reset_engine()


def test_announce_records_transcript():
    _reset_engine()
    a11y.enable_transcript_capture(True)
    a11y.announce("test message")
    assert "test message" in a11y.transcript_entries()
    _reset_engine()


def test_announce_thread_safety():
    """announce() must not raise when called from many threads simultaneously."""
    _reset_engine()
    a11y.enable_transcript_capture(True)
    errors = []

    def worker():
        for _ in range(100):
            try:
                a11y.announce("thread test")
            except Exception as exc:
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"announce() raised in threads: {errors}"
    _reset_engine()


def test_handler_is_called():
    _reset_engine()
    received = []
    a11y.set_announce_handler(received.append)
    a11y.announce("handler test")
    assert "handler test" in received
    _reset_engine()


def test_clear_transcript():
    _reset_engine()
    a11y.enable_transcript_capture(True)
    a11y.announce("before clear")
    a11y.clear_transcript()
    assert a11y.transcript_entries() == []
    _reset_engine()
