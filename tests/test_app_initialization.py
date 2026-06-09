"""Tests for ChapterForge app initialization."""

import os
import sys

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

# Skip these tests in environments without a display
pytestmark = pytest.mark.skipif(
    os.environ.get("CI") == "true" or os.name != "nt",
    reason="GUI tests require Windows with display"
)

def test_app_imports():
    """Test that main app modules can be imported without error."""
    try:
        from chapterforge.app import ChapterForgeApp
        assert ChapterForgeApp is not None
    except ImportError as e:
        pytest.fail(f"Failed to import ChapterForgeApp: {e}")

def test_main_imports():
    """Test that main module can be imported."""
    try:
        import main
        assert main is not None
    except ImportError as e:
        pytest.fail(f"Failed to import main: {e}")

def test_settings_imports():
    """Test that settings module can be imported."""
    try:
        from chapterforge import settings
        assert settings is not None
    except ImportError as e:
        pytest.fail(f"Failed to import settings: {e}")


@pytest.fixture(scope="module")
def _wx_app():
    import wx
    app = wx.App()
    yield app
    app.Destroy()


@pytest.fixture()
def _frame(_wx_app):
    import wx
    f = wx.Frame(None)
    yield f
    f.Destroy()


def test_ffmpeg_setup_dialog_close_mid_download(_frame):
    """Closing FFmpegSetupDialog while a CallAfter is queued must not raise.

    Regression test for the wx.PyDeadObjectError risk when the worker
    posts a status update after the user has already dismissed the dialog.
    """
    import wx
    from chapterforge.app import FFmpegSetupDialog

    dlg = FFmpegSetupDialog(_frame)
    # Queue a deferred update - this simulates a worker thread calling
    # update_status just as the user closes the dialog.
    dlg.update_status("Downloading...")
    dlg.Destroy()
    # Process any pending events; the wx.IsDestroyed guard must prevent
    # touching the dead status widget.
    for _ in range(10):
        wx.GetApp().ProcessPendingEvents()


if __name__ == "__main__":
    test_app_imports()
    test_main_imports()
    test_settings_imports()
    print("All import tests passed!")