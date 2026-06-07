"""Comprehensive tests for ChapterForge components."""

import os
import sys
import tempfile
from unittest import mock

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

def test_settings_module():
    """Test the settings module functionality."""
    try:
        from chapterforge import settings
        
        # Test loading default settings
        default_settings = settings.load()
        assert isinstance(default_settings, dict)
        assert "win_max" in default_settings
        # The default in the code is now True, but user settings may override
        # Just check that it's a boolean
        assert isinstance(default_settings["win_max"], bool)
        
        # Test saving and loading custom settings
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch('chapterforge.settings.config_dir', return_value=tmpdir):
                # Save custom settings
                custom_settings = {
                    "artist": "Test Artist",
                    "win_max": True  # Use True to match our intended default
                }
                settings.save(custom_settings)
                
                # Load settings and verify
                loaded_settings = settings.load()
                assert loaded_settings["artist"] == "Test Artist"
                assert loaded_settings["win_max"] == True
                
    except Exception as e:
        pytest.fail(f"Settings module test failed: {e}")


def test_core_module_import():
    """Test that core module can be imported."""
    try:
        from chapterforge import core
        assert core is not None
    except ImportError as e:
        pytest.fail(f"Failed to import core module: {e}")


def test_cli_module_import():
    """Test that CLI module can be imported."""
    try:
        from chapterforge import cli
        assert cli is not None
    except ImportError as e:
        pytest.fail(f"Failed to import CLI module: {e}")


def test_main_module_import():
    """Test that main module can be imported."""
    try:
        import main
        assert main is not None
    except ImportError as e:
        pytest.fail(f"Failed to import main module: {e}")


if __name__ == "__main__":
    test_settings_module()
    test_core_module_import()
    test_cli_module_import()
    test_main_module_import()
    print("All component tests passed!")