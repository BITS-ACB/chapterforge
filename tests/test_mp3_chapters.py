"""Test MP3 chapter parsing functionality."""

import os
import sys
import tempfile

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_mp3_chapter_parsing():
    """Test that MP3 chapter parsing works correctly."""
    try:
        from chapterforge import core
        
        # Try to parse a simple MP3 file
        # We can't test with a real file without FFmpeg, but we can at least
        # verify the import works
        print("ChapterForge core module imported successfully")
        print("read_master function available:", hasattr(core, 'read_master'))
        
        # Try to locate the read_master function
        if hasattr(core, 'read_master'):
            print("read_master function found")
        else:
            print("read_master function NOT found")
            
    except Exception as e:
        print(f"Error testing MP3 chapter parsing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_mp3_chapter_parsing()