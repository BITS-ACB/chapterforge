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

if __name__ == "__main__":
    test_app_imports()
    test_main_imports()
    test_settings_imports()
    print("All import tests passed!")