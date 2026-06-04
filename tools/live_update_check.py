"""Live end-to-end check of the ChapterForge auto-update path.

Exercises the REAL update code against the REAL GitHub release:
  1. fetch_latest_release()       -> queries api.github.com live
  2. is_newer_version(old, new)   -> simulates an older client (1.1.0)
  3. is_installable_asset(url)    -> validates the real asset URL
  4. download_release_asset(...)  -> streams the real installer from GitHub
  5. integrity                    -> SHA256 must equal the local installer
"""
from __future__ import annotations

import hashlib
import os
import sys

from chapterforge import updates


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    local_installer = os.path.join("installer_output", "ChapterForge-Setup.exe")
    print("1) Querying GitHub Releases API (live)...")
    latest = updates.fetch_latest_release()
    if latest is None:
        print("   FAIL: no release found")
        return 1
    print(f"   latest tag      : {latest.version}")
    print(f"   asset url       : {latest.download_url}")

    print("2) Version comparison (simulating a 1.1.0 client)...")
    newer = updates.is_newer_version("1.1.0", latest.version)
    print(f"   1.1.0 -> {latest.version} is newer: {newer}")
    if not newer:
        print("   FAIL: client would not be offered the update")
        return 1

    print("3) Asset installable on this platform?")
    installable = updates.is_installable_asset(latest.download_url)
    print(f"   is_installable_asset: {installable}")
    if not installable:
        print("   FAIL: asset not recognised as a runnable installer")
        return 1

    print("4) Downloading the real asset from GitHub...")
    last = {"pct": -1}

    def progress(read: int, total: int) -> None:
        pct = int(read * 100 / total) if total else 0
        if pct != last["pct"] and pct % 10 == 0:
            print(f"      {pct:3d}%  ({read:,} / {total:,} bytes)")
            last["pct"] = pct

    path = updates.download_release_asset(latest, progress=progress)
    size = os.path.getsize(path)
    print(f"   downloaded to   : {path}")
    print(f"   downloaded size : {size:,} bytes")

    with open(path, "rb") as fh:
        head = fh.read(2)
    print(f"   PE header 'MZ'  : {head == b'MZ'}")
    if head != b"MZ":
        print("   FAIL: not a Windows executable")
        return 1

    print("5) Integrity vs the installer we built & uploaded...")
    dl_hash = sha256(path)
    print(f"   downloaded SHA256: {dl_hash}")
    if os.path.isfile(local_installer):
        loc_hash = sha256(local_installer)
        print(f"   local     SHA256: {loc_hash}")
        match = dl_hash == loc_hash
        print(f"   bytes identical : {match}")
        if not match:
            print("   FAIL: downloaded installer does not match local build")
            return 1
    else:
        print("   (local installer not present; skipping hash compare)")

    # Leave the path for an optional real install step.
    print(f"\nDOWNLOADED_INSTALLER={path}")
    print("\nALL LIVE UPDATE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
