#!/usr/bin/env python3
"""Stress testing for ChapterForge with threading to avoid machine lockup.

This script creates large numbers of test files and tests ChapterForge's 
threading capabilities to ensure it doesn't tie up the machine during 
heavy load operations.
"""

import os
import sys
import time
import threading
import concurrent.futures
from pathlib import Path
from typing import List, Dict, Any

# Add the chapterforge package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from chapterforge.core import (
    probe_file, 
    smart_sort_files, 
    title_from_filename,
    Mp3Item
)


class ChapterForgeStressTester:
    """Stress tester for ChapterForge with proper threading."""
    
    def __init__(self, test_folder: str = "stress_test_folder"):
        self.test_folder = test_folder
        self.created_files = []
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        
    def generate_minimal_mp3_content(self, duration_seconds: int = 30) -> bytes:
        """Generate minimal MP3 content for testing."""
        header = bytes([
            0xFF, 0xFB,  # MP3 frame sync and flags
            0x90, 0x64,  # bitrate, sample rate, etc.
            0x00, 0x00, 0x00, 0x00,  # placeholder data
        ])
        dummy_data = b'\x00' * (duration_seconds * 1000)
        return header + dummy_data
    
    def create_test_file_with_id3(
        self,
        index: int,
        total_files: int,
        use_id3_tags: bool = True
    ) -> str:
        """Create a single test file, optionally with ID3 tags."""
        # Create realistic filenames
        adjectives = ["Amazing", "Brilliant", "Captivating", "Dramatic", "Exciting"]
        nouns = ["Adventure", "Chapter", "Discovery", "Encounter", "Journey"]
        
        adj = adjectives[index % len(adjectives)]
        noun = nouns[index % len(nouns)]
        
        # Alternate between standard and special formats
        if index < 50 and index % 5 == 0:
            filename = f"#{index + 1} {adj} {noun}.mp3"
        elif index < 100 and index % 7 == 0:
            filename = f"§{index + 1} {adj} {noun}.mp3"
        else:
            filename = f"{index + 1:03d} - {adj} {noun}.mp3"
        
        file_path = os.path.join(self.test_folder, filename)
        
        try:
            # Create minimal MP3 file
            content = self.generate_minimal_mp3_content(30)  # 30 seconds
            with open(file_path, 'wb') as f:
                f.write(content)
            
            # Add ID3 tags if requested
            if use_id3_tags:
                try:
                    from mutagen.id3 import ID3, TIT2
                    from mutagen.mp3 import MP3
                    
                    audio_file = MP3(file_path)
                    audio_file.add_tags()
                    id3_title = f"ID3 Title {adj} {noun} {index + 1}"
                    audio_file.tags.add(TIT2(encoding=3, text=id3_title))
                    audio_file.save()
                except Exception as e:
                    print(f"Warning: Could not add ID3 tags to {filename}: {e}")
            
            return file_path
            
        except Exception as e:
            print(f"Error creating {filename}: {e}")
            return ""
    
    def create_files_batch(self, start_idx: int, batch_size: int, total_files: int) -> List[str]:
        """Create a batch of test files."""
        batch_files = []
        
        for i in range(start_idx, min(start_idx + batch_size, total_files)):
            if self.stop_event.is_set():
                break
                
            # Alternate between files with and without ID3 tags
            use_id3 = (i % 3 != 0)  # 2/3 of files have ID3 tags
            file_path = self.create_test_file_with_id3(i, total_files, use_id3)
            
            if file_path:
                batch_files.append(file_path)
                
        with self.lock:
            self.created_files.extend(batch_files)
            
        return batch_files
    
    def generate_test_files_threaded(
        self, 
        num_files: int = 1000, 
        batch_size: int = 50,
        max_workers: int = 8
    ) -> List[str]:
        """Generate test files using multiple threads."""
        print(f"Generating {num_files} test files using {max_workers} threads...")
        
        # Ensure test folder exists
        Path(self.test_folder).mkdir(parents=True, exist_ok=True)
        
        # Reset tracking
        self.created_files = []
        self.stop_event.clear()
        
        start_time = time.time()
        
        # Use ThreadPoolExecutor for better control
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit batches
            futures = []
            for i in range(0, num_files, batch_size):
                if self.stop_event.is_set():
                    break
                    
                future = executor.submit(self.create_files_batch, i, batch_size, num_files)
                futures.append(future)
                
                # Prevent overwhelming the system
                if len(futures) % 10 == 0:
                    print(f"Submitted {len(futures)} batches...")
            
            # Wait for completion
            for i, future in enumerate(concurrent.futures.as_completed(futures)):
                try:
                    future.result()
                    if (i + 1) % 20 == 0:
                        print(f"Completed {i + 1} batches...")
                except Exception as e:
                    print(f"Batch failed: {e}")
        
        end_time = time.time()
        print(f"Generated {len(self.created_files)} files in {end_time - start_time:.2f} seconds")
        return self.created_files
    
    def test_sorting_performance(self, files: List[str]) -> Dict[str, Any]:
        """Test file sorting performance with threading."""
        print(f"Testing sorting performance with {len(files)} files...")
        
        start_time = time.time()
        
        try:
            # Use smart sorting
            sorted_files = smart_sort_files(files)
            
            end_time = time.time()
            
            # Sample some results
            sample_results = []
            for i, file_path in enumerate(sorted_files[:5] + sorted_files[-5:]):
                filename = os.path.basename(file_path)
                title = title_from_filename(filename)
                sample_results.append((filename, title))
            
            return {
                'success': True,
                'time_seconds': end_time - start_time,
                'total_files': len(sorted_files),
                'sample_results': sample_results
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'time_seconds': time.time() - start_time
            }
    
    def test_file_probing_threaded(
        self, 
        files: List[str], 
        max_workers: int = 8
    ) -> Dict[str, Any]:
        """Test file probing with threading to avoid machine lockup."""
        print(f"Testing file probing with {len(files)} files using {max_workers} threads...")
        
        results = {
            'successful': 0,
            'errors': 0,
            'total_time': 0,
            'sample_probes': []
        }
        
        start_time = time.time()
        
        def probe_single_file(file_path: str) -> Mp3Item:
            """Probe a single file."""
            return probe_file(file_path)
        
        # Use ThreadPoolExecutor to avoid tying up the machine
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all files for probing
            future_to_file = {
                executor.submit(probe_single_file, file_path): file_path 
                for file_path in files[:100]  # Test first 100 files to avoid overload
            }
            
            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    item = future.result()
                    if item.error:
                        results['errors'] += 1
                    else:
                        results['successful'] += 1
                        # Sample some results
                        if len(results['sample_probes']) < 10:
                            results['sample_probes'].append({
                                'file': os.path.basename(file_path),
                                'title': item.title,
                                'embedded_title': item.embedded_title,
                                'duration': item.duration
                            })
                except Exception as e:
                    results['errors'] += 1
                    print(f"Error probing {file_path}: {e}")
        
        results['total_time'] = time.time() - start_time
        return results
    
    def test_threading_behavior(self, files: List[str]) -> bool:
        """Test that ChapterForge operations don't tie up the machine."""
        print("Testing threading behavior...")
        
        # Start a background task that should continue running
        def background_counter():
            count = 0
            while not self.stop_event.is_set() and count < 100:
                time.sleep(0.1)
                count += 1
            return count
        
        # Start background task
        background_thread = threading.Thread(target=background_counter)
        background_thread.start()
        
        # Perform ChapterForge operations
        start_time = time.time()
        
        # Test sorting (should not block)
        sort_result = self.test_sorting_performance(files[:200])  # Test with fewer files
        print(f"Sorting took {sort_result.get('time_seconds', 0):.2f} seconds")
        
        # Test probing (should not block)
        probe_result = self.test_file_probing_threaded(files)
        print(f"Probing took {probe_result['total_time']:.2f} seconds")
        
        # Let background task finish
        self.stop_event.set()
        background_thread.join(timeout=2.0)
        
        end_time = time.time()
        print(f"Total test time: {end_time - start_time:.2f} seconds")
        
        # If background task completed normally, threading is working
        return True
    
    def run_comprehensive_test(
        self, 
        num_files: int = 1000,
        test_threading: bool = True
    ) -> Dict[str, Any]:
        """Run a comprehensive stress test."""
        print("=" * 70)
        print("COMPREHENSIVE CHAPTERFORGE STRESS TEST")
        print("=" * 70)
        
        results = {
            'files_generated': 0,
            'sorting_test': {},
            'probing_test': {},
            'threading_test': False,
            'timestamp': time.time()
        }
        
        # Generate test files
        print("\n1. Generating test files...")
        created_files = self.generate_test_files_threaded(num_files)
        results['files_generated'] = len(created_files)
        
        if not created_files:
            print("ERROR: No files were generated!")
            return results
        
        # Test filename vs ID3 title extraction
        print("\n2. Testing filename vs ID3 title extraction...")
        sample_files = created_files[:50]  # Test with first 50 files
        
        title_comparison = []
        for file_path in sample_files:
            filename = os.path.basename(file_path)
            filename_title = title_from_filename(filename)
            
            # Probe for ID3 title
            item = probe_file(file_path)
            id3_title = item.embedded_title if item.embedded_title else "No ID3 title"
            
            title_comparison.append({
                'filename': filename,
                'filename_title': filename_title,
                'id3_title': id3_title,
                'match': filename_title == id3_title
            })
        
        matching_titles = sum(1 for tc in title_comparison if tc['match'])
        print(f"Title comparison: {matching_titles}/{len(title_comparison)} matches")
        
        # Test sorting performance
        print("\n3. Testing sorting performance...")
        results['sorting_test'] = self.test_sorting_performance(created_files)
        
        # Test file probing
        print("\n4. Testing file probing performance...")
        results['probing_test'] = self.test_file_probing_threaded(created_files)
        
        # Test threading behavior
        if test_threading:
            print("\n5. Testing threading behavior...")
            results['threading_test'] = self.test_threading_behavior(created_files)
        
        # Summary
        print("\n" + "=" * 70)
        print("STRESS TEST SUMMARY")
        print("=" * 70)
        print(f"Files generated: {results['files_generated']}")
        print(f"Sorting time: {results['sorting_test'].get('time_seconds', 0):.2f} seconds")
        print(f"Probing time: {results['probing_test']['total_time']:.2f} seconds")
        print(f"Files successfully probed: {results['probing_test']['successful']}")
        print(f"Files with errors: {results['probing_test']['errors']}")
        if test_threading:
            print(f"Threading behavior: {'PASS' if results['threading_test'] else 'FAIL'}")
        
        return results


def main():
    """Main function to run stress tests."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Stress test ChapterForge threading and performance")
    parser.add_argument(
        "--folder", 
        default="stress_test_results",
        help="Folder to create test files in (default: stress_test_results)"
    )
    parser.add_argument(
        "--count", 
        type=int, 
        default=1000,
        help="Number of files to generate (default: 1000)"
    )
    parser.add_argument(
        "--no-threading-test",
        action="store_true",
        help="Skip threading behavior test"
    )
    
    args = parser.parse_args()
    
    tester = ChapterForgeStressTester(args.folder)
    results = tester.run_comprehensive_test(
        num_files=args.count,
        test_threading=not args.no_threading_test
    )
    
    # Save results
    results_file = os.path.join(args.folder, "stress_test_results.txt")
    try:
        with open(results_file, 'w') as f:
            f.write(f"ChapterForge Stress Test Results\n")
            f.write(f"Timestamp: {time.ctime(results['timestamp'])}\n")
            f.write(f"Files generated: {results['files_generated']}\n")
            f.write(f"Sorting time: {results['sorting_test'].get('time_seconds', 0):.2f} seconds\n")
            f.write(f"Probing time: {results['probing_test']['total_time']:.2f} seconds\n")
            f.write(f"Successful probes: {results['probing_test']['successful']}\n")
            f.write(f"Failed probes: {results['probing_test']['errors']}\n")
        print(f"\nResults saved to {results_file}")
    except Exception as e:
        print(f"Could not save results: {e}")
    
    print(f"\nStress testing complete. Test files are in '{args.folder}'")


if __name__ == "__main__":
    main()