#!/usr/bin/env python3
"""Download and extract libmpv-2.dll if it doesn't exist.

This script ensures bin/mpv/libmpv-2.dll is available before building. If
missing, it fetches the latest x86_64 "dev" build from the mpv-player-windows
project on SourceForge, verifies it against the publisher's MD5 checksum, and
extracts just the DLL.

Nightly build filenames are date-stamped and get pruned over time, so rather
than hardcoding one, this queries the project's libmpv RSS feed and picks the
newest entry for the plain x86_64 architecture (not the "-v3" variant, which
requires a newer CPU).
"""

import hashlib
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

BIN_DIR = Path(__file__).parent.parent / "bin" / "mpv"
LIBMPV_DLL = BIN_DIR / "libmpv-2.dll"

FEED_URL = "https://sourceforge.net/projects/mpv-player-windows/rss?path=/libmpv"
DOWNLOAD_URL = "https://master.dl.sourceforge.net/project/mpv-player-windows/libmpv/{filename}?viasf=1"

# Matches plain x86_64 builds, e.g. mpv-dev-x86_64-20260607-git-71ebd08.7z
# (and not the "-v3" variant, which targets newer CPUs only).
_NAME_RE = re.compile(r"^mpv-dev-x86_64-\d{8}-git-[0-9a-f]+\.7z$")

_NS = {"media": "http://search.yahoo.com/mrss/"}


def libmpv_exists():
    """Check if libmpv-2.dll exists."""
    return LIBMPV_DLL.exists()


def _find_latest_build():
    """Return (filename, md5) for the newest plain-x86_64 dev build, or None."""
    with urllib.request.urlopen(FEED_URL, timeout=30) as resp:
        feed = ET.fromstring(resp.read())

    for item in feed.iter("item"):
        title = (item.findtext("title") or "").strip().lstrip("/")
        filename = title.split("/")[-1]
        if not _NAME_RE.match(filename):
            continue
        hash_el = item.find("media:content/media:hash", _NS)
        if hash_el is None or hash_el.get("algo") != "md5":
            continue
        return filename, hash_el.text.strip()
    return None


def download_libmpv():
    """Download, verify and extract libmpv-2.dll into bin/mpv/."""
    print("Looking up the latest libmpv build...")
    try:
        found = _find_latest_build()
    except Exception as e:
        print(f"Error querying the libmpv feed: {e}", file=sys.stderr)
        return False
    if not found:
        print("Error: no matching x86_64 libmpv build found in the feed", file=sys.stderr)
        return False
    filename, expected_md5 = found

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = BIN_DIR / filename
    url = DOWNLOAD_URL.format(filename=filename)
    print(f"Downloading {filename}...")
    try:
        urllib.request.urlretrieve(url, archive_path)
    except Exception as e:
        print(f"Error downloading libmpv: {e}", file=sys.stderr)
        return False

    print("Verifying checksum...")
    digest = hashlib.md5()
    with open(archive_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    if digest.hexdigest().lower() != expected_md5.lower():
        print("Error: MD5 checksum mismatch - download may be corrupt", file=sys.stderr)
        archive_path.unlink(missing_ok=True)
        return False

    print("Extracting libmpv-2.dll...")
    try:
        import py7zr
        with py7zr.SevenZipFile(archive_path, mode="r") as archive:
            targets = [n for n in archive.getnames() if n.endswith("libmpv-2.dll")]
            if not targets:
                print("Error: libmpv-2.dll not found in archive", file=sys.stderr)
                return False
            archive.extract(path=BIN_DIR, targets=targets)
        extracted = next(BIN_DIR.rglob("libmpv-2.dll"))
        if extracted != LIBMPV_DLL:
            extracted.replace(LIBMPV_DLL)
            # Clean up any now-empty directory the archive's path created.
            for parent in extracted.parents:
                if parent == BIN_DIR:
                    break
                try:
                    parent.rmdir()
                except OSError:
                    break
    except Exception as e:
        print(f"Error extracting libmpv: {e}", file=sys.stderr)
        print(
            f"You can extract it manually with 7-Zip from {archive_path} - "
            f"copy mpv-dev-*/libmpv-2.dll to {LIBMPV_DLL}", file=sys.stderr)
        return False
    finally:
        archive_path.unlink(missing_ok=True)

    return True


if __name__ == "__main__":
    if libmpv_exists():
        print(f"libmpv-2.dll found in {BIN_DIR}")
        sys.exit(0)

    if not download_libmpv():
        print("Failed to download libmpv-2.dll", file=sys.stderr)
        sys.exit(1)

    if not libmpv_exists():
        print("libmpv-2.dll missing after download", file=sys.stderr)
        sys.exit(1)

    print("libmpv ready")
    sys.exit(0)
