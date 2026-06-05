#!/usr/bin/env python3
"""Download and extract FFmpeg binaries if they don't exist.

This script ensures ffmpeg.exe and ffprobe.exe are available in bin/
before building. If missing, it downloads them from gyan.dev.
"""

import os
import sys
import urllib.request
import zipfile
import shutil
from pathlib import Path

BIN_DIR = Path(__file__).parent.parent / "bin"
FFMPEG_EXE = BIN_DIR / "ffmpeg.exe"
FFPROBE_EXE = BIN_DIR / "ffprobe.exe"

# gyan.dev FFmpeg builds (static, Windows)
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-full.zip"

def ffmpeg_exists():
    """Check if both ffmpeg and ffprobe exist and are executable."""
    return FFMPEG_EXE.exists() and FFPROBE_EXE.exists()

def download_ffmpeg():
    """Download and extract FFmpeg binaries to bin/."""
    print("Downloading FFmpeg...")
    BIN_DIR.mkdir(parents=True, exist_ok=True)

    # Download to a temp zip
    zip_path = BIN_DIR / "ffmpeg.zip"
    try:
        urllib.request.urlretrieve(FFMPEG_URL, zip_path)
    except Exception as e:
        print(f"Error downloading FFmpeg: {e}", file=sys.stderr)
        return False

    print("Extracting FFmpeg...")
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            # Find the bin/ folder inside the zip (structure: ffmpeg-release-full/bin/)
            members = z.namelist()
            bin_members = [m for m in members if '/bin/ffmpeg.exe' in m or '/bin/ffprobe.exe' in m]

            if not bin_members:
                print("Error: FFmpeg binaries not found in ZIP", file=sys.stderr)
                return False

            # Extract just the .exe files
            for member in bin_members:
                if member.endswith(('ffmpeg.exe', 'ffprobe.exe')):
                    data = z.read(member)
                    exe_name = Path(member).name
                    exe_path = BIN_DIR / exe_name
                    with open(exe_path, 'wb') as f:
                        f.write(data)
                    print(f"Extracted {exe_name}")

        zip_path.unlink()  # Delete the temp zip
        return True
    except Exception as e:
        print(f"Error extracting FFmpeg: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    if ffmpeg_exists():
        print(f"FFmpeg binaries found in {BIN_DIR}")
        sys.exit(0)

    if not download_ffmpeg():
        print("Failed to download FFmpeg binaries", file=sys.stderr)
        sys.exit(1)

    if not ffmpeg_exists():
        print("FFmpeg binaries missing after download", file=sys.stderr)
        sys.exit(1)

    print("FFmpeg ready")
    sys.exit(0)
