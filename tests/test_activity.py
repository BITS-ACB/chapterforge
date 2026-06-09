"""Tests for ActivityManager - the background-task registry."""

import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chapterforge.activity import Activity, ActivityManager, ActivityState


def _mgr():
    """Fresh ActivityManager instance (bypasses the singleton for isolation)."""
    return ActivityManager()


def test_start_returns_running_activity():
    mgr = _mgr()
    act = mgr.start("Build audiobook")
    assert act.state == ActivityState.RUNNING
    assert act.label == "Build audiobook"
    assert act.id >= 1
    assert act.progress == 0.0


def test_update_clamps_and_stores():
    mgr = _mgr()
    act = mgr.start("Transcribe")
    act.update(150, "Over limit")
    assert act.progress == 100.0
    act.update(-5)
    assert act.progress == 0.0
    act.update(42, "Forty-two percent")
    assert act.progress == 42.0
    assert act.status_text == "Forty-two percent"


def test_finish_marks_done():
    mgr = _mgr()
    act = mgr.start("Finishing")
    act.finish("Done.")
    assert act.state == ActivityState.DONE
    assert act.progress == 100.0
    assert act.finished_at is not None


def test_fail_marks_failed():
    mgr = _mgr()
    act = mgr.start("Failing")
    act.fail("Something went wrong.")
    assert act.state == ActivityState.FAILED
    assert act.status_text == "Something went wrong."
    assert act.finished_at is not None


def test_cancel_invokes_callback():
    cancelled = threading.Event()
    mgr = _mgr()
    act = mgr.start("Cancellable", can_cancel=True, on_cancel=cancelled.set)
    act.request_cancel()
    assert cancelled.is_set()


def test_cancel_without_callback_is_safe():
    mgr = _mgr()
    act = mgr.start("No callback", can_cancel=True)
    act.request_cancel()  # must not raise


def test_listener_notified_on_start_and_remove():
    mgr = _mgr()
    received = []
    mgr.add_listener(received.append)
    act = mgr.start("Listened")
    mgr.remove(act)
    assert len(received) == 2
    assert received[0].label == "Listened"


def test_active_count_excludes_done():
    mgr = _mgr()
    a1 = mgr.start("Running 1")
    a2 = mgr.start("Running 2")
    a2.finish()
    assert mgr.active_count() == 1
    a1.finish()
    assert mgr.active_count() == 0


def test_remove_listener_stops_notifications():
    mgr = _mgr()
    received = []
    fn = received.append
    mgr.add_listener(fn)
    mgr.remove_listener(fn)
    mgr.start("Silent")
    assert not received
