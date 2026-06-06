#!/usr/bin/env python3
"""Generate large numbers of test files for stress testing ChapterForge.

This script creates realistic test scenarios with 1000+ MP3 files to test
ChapterForge's performance and threading behavior under heavy load.
"""

import os
import sys
import random
import threading
import time
from pathlib import Path
from typing import List, Optional

# Add the chapterforge package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from chapterforge.core import title_from_filename


def generate_test_mp3_content(duration_seconds: int = 30) -> bytes:
    """Generate minimal MP3 content for testing (not playable, but valid format).
    
    This creates a very small MP3 file with minimal valid header information.
    It's not meant to be played, just to test ChapterForge's file processing.
    """
    # Simple MP3 header with minimal valid data
    # This is a basic MP3 frame header that will be recognized by ffprobe
    header = bytes([
        0xFF, 0xFB,  # MP3 frame sync and flags
        0x90, 0x64,  # bitrate, sample rate, etc.
        0x00, 0x00, 0x00, 0x00,  # placeholder data
    ])
    
    # Add some dummy audio data to make it a reasonable size
    dummy_data = b'\x00' * (duration_seconds * 1000)  # ~1KB per second
    
    return header + dummy_data


def create_test_file(
    folder_path: str, 
    index: int, 
    total_files: int,
    use_special_formats: bool = False
) -> Optional[str]:
    """Create a single test MP3 file with realistic naming.
    
    Args:
        folder_path: Directory to create the file in
        index: File index (0-based)
        total_files: Total number of files to create
        use_special_formats: Whether to use special naming formats like #1, §2
        
    Returns:
        Path to created file or None if failed
    """
    # Generate realistic chapter titles
    adjectives = [
        "Amazing", "Brilliant", "Captivating", "Dramatic", "Exciting", 
        "Fascinating", "Gripping", "Heartwarming", "Incredible", "Juicy",
        "Kaleidoscopic", "Luminous", "Mysterious", "Nostalgic", "Optimistic",
        "Pulsating", "Quirky", "Radiant", "Spectacular", "Thrilling"
    ]
    
    nouns = [
        "Adventure", "Beginning", "Chapter", "Discovery", "Encounter",
        "Finale", "Glimpse", "Horizon", "Insight", "Journey",
        "Knowledge", "Legacy", "Memory", "Narrative", "Odyssey",
        "Passage", "Quest", "Revelation", "Saga", "Twist"
    ]
    
    # Create filename based on index and options
    if use_special_formats and index < 100:
        # Use special formats for first 100 files
        formats = ["#", "§"]
        format_char = random.choice(formats)
        title = f"{adjectives[index % len(adjectives)]} {nouns[index % len(nouns)]}"
        filename = f"{format_char}{index + 1} {title}.mp3"
    else:
        # Standard numbered format
        title = f"{adjectives[index % len(adjectives)]} {nouns[index % len(nouns)]}"
        filename = f"{index + 1:03d} - {title}.mp3"
    
    file_path = os.path.join(folder_path, filename)
    
    try:
        # Generate and write test content
        content = generate_test_mp3_content(random.randint(15, 45))  # 15-45 seconds
        with open(file_path, 'wb') as f:
            f.write(content)
        return file_path
    except Exception as e:
        print(f"Error creating {filename}: {e}")
        return None


def generate_test_files_threaded(
    folder_path: str,
    num_files: int = 1000,
    use_special_formats: bool = False,
    batch_size: int = 50
) -> List[str]:
    """Generate test files using threading for better performance.
    
    Args:
        folder_path: Directory to create files in
        num_files: Number of files to generate
        use_special_formats: Whether to include special naming formats
        batch_size: Number of files to process in each batch
        
    Returns:
        List of paths to created files
    """
    # Ensure the folder exists
    Path(folder_path).mkdir(parents=True, exist_ok=True)
    
    created_files = []
    lock = threading.Lock()
    
    def create_batch(start_idx: int, end_idx: int):
        """Create a batch of files."""
        batch_files = []
        for i in range(start_idx, min(end_idx, num_files)):
            file_path = create_test_file(
                folder_path, i, num_files, use_special_formats
            )
            if file_path:
                with lock:
                    batch_files.append(file_path)
                    if len(batch_files) % 10 == 0:
                        print(f"Created {len(batch_files)} files in batch {start_idx//batch_size + 1}")
        
        with lock:
            created_files.extend(batch_files)
    
    # Create threads for batches
    threads = []
    for i in range(0, num_files, batch_size):
        thread = threading.Thread(
            target=create_batch,
            args=(i, i + batch_size)
        )
        threads.append(thread)
        thread.start()
        
        # Limit concurrent threads to avoid system overload
        if len(threads) >= 8:
            for t in threads:
                t.join()
            threads = []
    
    # Wait for remaining threads
    for thread in threads:
        thread.join()
    
    print(f"Successfully created {len(created_files)} test files")
    return created_files


def stress_test_sorting(folder_path: str):
    """Test ChapterForge's file sorting with large numbers of files."""
    print(f"Testing sorting performance with files in {folder_path}")
    
    try:
        from chapterforge.core import smart_sort_files
        
        # Get all MP3 files
        mp3_files = [
            os.path.join(folder_path, f) 
            for f in os.listdir(folder_path) 
            if f.lower().endswith('.mp3')
        ]
        
        print(f"Found {len(mp3_files)} MP3 files")
        
        # Test sorting performance
        start_time = time.time()
        sorted_files = smart_sort_files(mp3_files)
        end_time = time.time()
        
        print(f"Sorting completed in {end_time - start_time:.2f} seconds")
        print(f"Sorted {len(sorted_files)} files")
        
        # Show first 10 and last 10 files
        print("\nFirst 10 files:")
        for i, file_path in enumerate(sorted_files[:10]):
            filename = os.path.basename(file_path)
            title = title_from_filename(filename)
            print(f"  {i+1:3d}. {filename} -> '{title}'")
            
        print("\nLast 10 files:")
        for i, file_path in enumerate(sorted_files[-10:], len(sorted_files)-9):
            filename = os.path.basename(file_path)
            title = title_from_filename(filename)
            print(f"  {i:3d}. {filename} -> '{title}'")
            
    except Exception as e:
        print(f"Error during sorting test: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main function to generate test files and run performance tests."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate test files for ChapterForge stress testing")
    parser.add_argument(
        "--folder", 
        default="test_large_folder",
        help="Folder to create test files in (default: test_large_folder)"
    )
    parser.add_argument(
        "--count", 
        type=int, 
        default=1000,
        help="Number of files to generate (default: 1000)"
    )
    parser.add_argument(
        "--special-formats",
        action="store_true",
        help="Include special naming formats like #1, §2"
    )
    parser.add_argument(
        "--test-sorting",
        action="store_true",
        help="Test sorting performance after generating files"
    )
    
    args = parser.parse_args()
    
    print(f"Generating {args.count} test files in '{args.folder}'")
    if args.special_formats:
        print("Including special naming formats")
    
    start_time = time.time()
    
    # Generate test files
    created_files = generate_test_files_threaded(
        args.folder,
        args.count,
        args.special_formats
    )
    
    end_time = time.time()
    
    print(f"\nGeneration completed in {end_time - start_time:.2f} seconds")
    print(f"Created {len(created_files)} files")
    
    # Test sorting if requested
    if args.test_sorting:
        print("\n" + "="*60)
        stress_test_sorting(args.folder)
    
    print(f"\nTest files are ready in '{args.folder}'")
    print("You can now use ChapterForge to test with these files")


if __name__ == "__main__":
    main()