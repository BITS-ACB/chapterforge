#!/usr/bin/env python3
"""Test script to compare filename vs ID3 tag chapter naming in ChapterForge.

This script creates test files with both filename-based and ID3 tag-based 
chapter titles to test ChapterForge's handling of different title sources.
"""

import os
import sys
import random
import threading
import time
from pathlib import Path
from mutagen.id3 import ID3, TIT2, TP1, TAL, TYE
from mutagen.mp3 import MP3

# Add the chapterforge package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from chapterforge.core import title_from_filename


def generate_test_mp3_with_id3(
    file_path: str,
    filename_title: str,
    id3_title: str,
    artist: str = "Test Artist",
    album: str = "Test Album",
    year: str = "2026"
) -> bool:
    """Generate a test MP3 file with ID3 tags.
    
    Args:
        file_path: Path where to create the file
        filename_title: Title to use in the filename
        id3_title: Title to embed in ID3 tags
        artist: Artist name for ID3 tags
        album: Album name for ID3 tags
        year: Year for ID3 tags
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Generate minimal MP3 content
        header = bytes([
            0xFF, 0xFB,  # MP3 frame sync and flags
            0x90, 0x64,  # bitrate, sample rate, etc.
            0x00, 0x00, 0x00, 0x00,  # placeholder data
        ])
        
        # Add some dummy audio data (30 seconds of silence)
        dummy_data = b'\x00' * 30000  # ~30KB of silence
        
        # Write the file
        with open(file_path, 'wb') as f:
            f.write(header + dummy_data)
        
        # Add ID3 tags
        audio_file = MP3(file_path)
        audio_file.add_tags()
        
        # Set ID3 tags
        audio_file.tags.add(TIT2(encoding=3, text=id3_title))  # Title
        audio_file.tags.add(TP1(encoding=3, text=artist))       # Artist
        audio_file.tags.add(TAL(encoding=3, text=album))        # Album
        audio_file.tags.add(TYE(encoding=3, text=year))         # Year
        
        audio_file.save()
        return True
        
    except Exception as e:
        print(f"Error creating {file_path}: {e}")
        return False


def create_mixed_test_files(folder_path: str, count: int = 50) -> int:
    """Create a mix of files with filename vs ID3 title differences.
    
    Args:
        folder_path: Directory to create files in
        count: Number of files to create
        
    Returns:
        Number of files successfully created
    """
    # Ensure the folder exists
    Path(folder_path).mkdir(parents=True, exist_ok=True)
    
    # Sample titles for testing
    filename_titles = [
        "01 Introduction to the Topic",
        "02 Key Concepts and Principles", 
        "03 Detailed Analysis Part One",
        "04 Deep Dive Into Techniques",
        "05 Advanced Methodologies",
        "06 Case Study Examples",
        "07 Practical Applications",
        "08 Troubleshooting Guide",
        "09 Best Practices Summary",
        "10 Conclusion and Next Steps"
    ]
    
    id3_titles = [
        "Introduction: Getting Started",
        "Core Concepts Explained",
        "Analysis: Part 1 - Fundamentals",
        "Techniques: In-Depth Coverage",
        "Advanced Methods and Approaches",
        "Real-World Examples",
        "Putting Theory into Practice",
        "Common Issues and Solutions",
        "Recommended Best Practices",
        "Wrapping Up and Looking Forward"
    ]
    
    created_count = 0
    
    print(f"Creating {count} test files with mixed title sources...")
    
    for i in range(count):
        # Alternate between filename-first and ID3-first approaches
        if i % 2 == 0:
            # Filename title as primary, different ID3 title
            filename_title = filename_titles[i % len(filename_titles)]
            id3_title = id3_titles[i % len(id3_titles)]
        else:
            # ID3 title as primary, different filename title
            id3_title = id3_titles[i % len(id3_titles)]
            filename_title = filename_titles[i % len(filename_titles)]
        
        # Create filename
        filename = f"{i+1:02d} - {filename_title}.mp3"
        file_path = os.path.join(folder_path, filename)
        
        # Generate the file with ID3 tags
        if generate_test_mp3_with_id3(file_path, filename_title, id3_title):
            created_count += 1
            if created_count % 10 == 0:
                print(f"Created {created_count} files...")
    
    print(f"Successfully created {created_count} test files")
    return created_count


def test_chapter_naming_scenarios(folder_path: str):
    """Test different chapter naming scenarios.
    
    Args:
        folder_path: Directory containing test files
    """
    print(f"\nTesting chapter naming scenarios with files in {folder_path}")
    
    try:
        from chapterforge.core import probe_file
        
        # Get all MP3 files
        mp3_files = [
            os.path.join(folder_path, f) 
            for f in os.listdir(folder_path) 
            if f.lower().endswith('.mp3')
        ]
        
        print(f"Found {len(mp3_files)} MP3 files")
        
        # Test both filename and ID3 title extraction
        results = []
        
        for i, file_path in enumerate(mp3_files[:20]):  # Test first 20 files
            filename = os.path.basename(file_path)
            
            # Get filename-based title
            filename_title = title_from_filename(filename)
            
            # Get ID3-based title by probing the file
            item = probe_file(file_path)
            id3_title = item.embedded_title if item.embedded_title else "No ID3 title"
            
            results.append({
                'file': filename,
                'filename_title': filename_title,
                'id3_title': id3_title,
                'titles_match': filename_title == id3_title
            })
            
            print(f"\nFile {i+1}: {filename}")
            print(f"  Filename title: '{filename_title}'")
            print(f"  ID3 title:      '{id3_title}'")
            print(f"  Match: {filename_title == id3_title}")
        
        # Summary
        matching_count = sum(1 for r in results if r['titles_match'])
        total_count = len(results)
        
        print(f"\nSummary:")
        print(f"  Files tested: {total_count}")
        print(f"  Matching titles: {matching_count}")
        print(f"  Different titles: {total_count - matching_count}")
        
        return results
        
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return []


def main():
    """Main function to create test files and test both naming approaches."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test filename vs ID3 tag chapter naming")
    parser.add_argument(
        "--folder", 
        default="test_id3_filename_comparison",
        help="Folder to create test files in (default: test_id3_filename_comparison)"
    )
    parser.add_argument(
        "--count", 
        type=int, 
        default=50,
        help="Number of files to generate (default: 50)"
    )
    parser.add_argument(
        "--test-only",
        action="store_true",
        help="Only test existing files, don't generate new ones"
    )
    
    args = parser.parse_args()
    
    if not args.test_only:
        print(f"Creating {args.count} test files in '{args.folder}'")
        print("Files will have different filename and ID3 titles for comparison")
        
        start_time = time.time()
        created_count = create_mixed_test_files(args.folder, args.count)
        end_time = time.time()
        
        if created_count == 0:
            print("No files were created successfully!")
            return
            
        print(f"Generation completed in {end_time - start_time:.2f} seconds")
    
    # Test chapter naming scenarios
    print("\n" + "="*70)
    test_chapter_naming_scenarios(args.folder)
    
    print(f"\nTest files are ready in '{args.folder}'")
    print("You can now use ChapterForge to test both filename and ID3 title sources")


if __name__ == "__main__":
    main()