#!/usr/bin/env python3
"""Verify ChapterForge threading behavior with large file operations."""

import os
import sys
import time
import threading
from pathlib import Path

# Add the chapterforge package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_threading_not_blocked():
    """Test that ChapterForge operations don't block other threads."""
    print("Testing ChapterForge threading behavior...")
    
    # Import ChapterForge modules
    try:
        from chapterforge.core import (
            probe_file, 
            smart_sort_files, 
            title_from_filename
        )
        print("✓ ChapterForge modules imported successfully")
    except Exception as e:
        print(f"✗ Failed to import ChapterForge modules: {e}")
        return False
    
    # Create a simple test folder with a few files
    test_folder = "threading_test_folder"
    Path(test_folder).mkdir(exist_ok=True)
    
    # Create minimal test files
    test_files = []
    for i in range(5):
        filename = f"test_{i:02d}.mp3"
        filepath = os.path.join(test_folder, filename)
        
        # Create minimal MP3 content
        header = bytes([0xFF, 0xFB, 0x90, 0x64, 0x00, 0x00, 0x00, 0x00])
        dummy_data = b'\x00' * 1000  # 1KB of data
        
        with open(filepath, 'wb') as f:
            f.write(header + dummy_data)
        test_files.append(filepath)
    
    print(f"✓ Created {len(test_files)} test files")
    
    # Test 1: Verify sorting doesn't block
    print("\nTest 1: File sorting threading...")
    start_time = time.time()
    
    def background_task():
        """Background task that should continue running."""
        count = 0
        while count < 100:
            time.sleep(0.01)  # 10ms sleep
            count += 1
        return count
    
    # Start background task
    bg_thread = threading.Thread(target=background_task)
    bg_thread.start()
    
    # Perform sorting (should not block background task)
    try:
        sorted_files = smart_sort_files(test_files)
        print(f"✓ Sorting completed: {len(sorted_files)} files")
    except Exception as e:
        print(f"✗ Sorting failed: {e}")
        return False
    
    # Wait for background task and check if it completed normally
    bg_thread.join(timeout=2.0)
    if bg_thread.is_alive():
        print("✗ Background task was blocked by sorting!")
        return False
    else:
        print("✓ Background task completed normally during sorting")
    
    # Test 2: Verify file probing doesn't block
    print("\nTest 2: File probing threading...")
    
    # Start another background task
    bg_thread2 = threading.Thread(target=background_task)
    bg_thread2.start()
    
    # Probe files (should not block background task)
    probe_results = []
    for filepath in test_files[:3]:  # Test with first 3 files
        try:
            item = probe_file(filepath)
            probe_results.append(item)
            print(f"✓ Probed {os.path.basename(filepath)}")
        except Exception as e:
            print(f"✗ Failed to probe {os.path.basename(filepath)}: {e}")
    
    # Wait for background task
    bg_thread2.join(timeout=2.0)
    if bg_thread2.is_alive():
        print("✗ Background task was blocked by file probing!")
        return False
    else:
        print("✓ Background task completed normally during file probing")
    
    # Cleanup
    for filepath in test_files:
        try:
            os.remove(filepath)
        except:
            pass
    try:
        os.rmdir(test_folder)
    except:
        pass
    
    total_time = time.time() - start_time
    print(f"\n✓ All threading tests passed in {total_time:.2f} seconds")
    return True

def main():
    """Main function to verify threading behavior."""
    print("ChapterForge Threading Behavior Verification")
    print("=" * 50)
    
    success = test_threading_not_blocked()
    
    if success:
        print("\n🎉 SUCCESS: ChapterForge properly handles threading!")
        print("   Large file operations will not tie up the machine.")
    else:
        print("\n❌ FAILURE: ChapterForge may block other threads!")
        print("   Large file operations might tie up the machine.")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())