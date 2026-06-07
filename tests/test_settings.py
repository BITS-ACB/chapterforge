"""Tests for chapterforge.settings."""

import os
import sys
import json
import tempfile
import shutil
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chapterforge import settings


def test_config_dir():
    """Test that config_dir returns the correct path."""
    # On Windows, should be under %APPDATA%
    if os.name == 'nt':
        expected_base = os.environ.get("APPDATA")
        if expected_base:
            expected = os.path.join(expected_base, settings.APP_FOLDER_NAME)
            assert settings.config_dir() == expected


def test_config_path():
    """Test that config_path returns the correct path."""
    config_dir = settings.config_dir()
    expected = os.path.join(config_dir, "settings.json")
    assert settings.config_path() == expected


def test_load_defaults():
    """Test that load returns defaults when no config file exists."""
    # Temporarily point config to a non-existent directory
    with mock.patch('chapterforge.settings.config_path') as mock_config_path:
        # Point to a temp file that doesn't exist
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent_file = os.path.join(tmpdir, "nonexistent.json")
            mock_config_path.return_value = nonexistent_file
            
            # Should still return defaults without error
            result = settings.load()
            assert isinstance(result, dict)
            assert "artist" in result
            assert "album_artist" in result
            assert "genre" in result


def test_save_and_load():
    """Test saving and loading settings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a temporary config directory
        temp_config_dir = os.path.join(tmpdir, "ChapterForge")
        
        with mock.patch('chapterforge.settings.config_dir', return_value=temp_config_dir):
            # Test saving settings
            test_settings = {
                "artist": "Test Artist",
                "album_artist": "Test Album Artist",
                "genre": "Test Genre",
                "win_max": True
            }
            
            settings.save(test_settings)
            
            # Test loading settings
            loaded_settings = settings.load()
            assert loaded_settings["artist"] == "Test Artist"
            assert loaded_settings["album_artist"] == "Test Album Artist"
            assert loaded_settings["genre"] == "Test Genre"
            assert loaded_settings["win_max"] == True


def test_default_values():
    """Test that default values are correct."""
    defaults = settings.DEFAULTS
    
    # Check some key defaults
    assert defaults["artist"] == ""
    assert defaults["album_artist"] == ""
    assert defaults["genre"] == ""
    assert defaults["win_max"] == True  # This was changed to True
    assert defaults["start_minimized"] == False
    assert defaults["check_updates_startup"] == True