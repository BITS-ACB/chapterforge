"""Update checking for ChapterForge.

Adapted from the QUILL project's ``quill/core/updates.py``: it queries the
GitHub Releases API for the newest eligible release, compares versions with
intentional pre-release ordering, picks the right installer asset for the
current platform, and refuses any non-HTTPS / untrusted-host download URL.

The check is deliberately dependency-free (``urllib``) and side-effect free -
callers decide what to do with a :class:`ReleaseInfo`. It is safe to run on a
background thread.
"""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Callable, List, Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from . import __version__

# Project repository (Blind Information Technology Specialists / ACB).
GITHUB_OWNER = "bits-acb"
GITHUB_REPO = "chapterforge"
GITHUB_RELEASES_API = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
)
RELEASES_PAGE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
PROJECT_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"

_TRUSTED_HOSTS = {
    "github.com",
    "api.github.com",
    "objects.githubusercontent.com",
    "github-releases.githubusercontent.com",
}

_STABLE_PRERELEASE_RANK = (9, 0)


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    download_url: str
    published_at: str
    notes: str
    prerelease: bool


class UpdateCheckError(Exception):
    """A network or parsing failure while checking for updates."""


def _ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context()


_SKIP_ASSET_SUFFIXES = (".json", ".sig", ".asc", ".pem", ".sha256", ".sha512",
                        ".txt", ".sbom")
_SKIP_ASSET_KEYWORDS = ("provenance", "checksum", "sbom", "signature")


def _platform_asset_suffixes() -> tuple:
    if sys.platform == "darwin":
        return (".dmg", ".pkg", ".zip")
    if sys.platform.startswith("win"):
        return (".exe", ".msi", ".zip")
    return (".appimage", ".tar.gz", ".zip")


def _pick_asset(assets: list) -> str:
    usable: List[tuple] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        url = asset.get("browser_download_url")
        name = str(asset.get("name") or "").lower()
        if not url or name.endswith(_SKIP_ASSET_SUFFIXES):
            continue
        if any(k in name for k in _SKIP_ASSET_KEYWORDS):
            continue
        usable.append((name, str(url)))
    for suffix in _platform_asset_suffixes():
        for name, url in usable:
            if name.endswith(suffix):
                return url
    return usable[0][1] if usable else ""


def _validate_remote_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise UpdateCheckError("Update URLs must use HTTPS.")
    host = (parsed.hostname or "").lower()
    if not host or host not in _TRUSTED_HOSTS:
        raise UpdateCheckError(f"Update URL host is not trusted: {host or '(none)'}")


def _release_from_json(data: dict) -> ReleaseInfo:
    download_url = _pick_asset(data.get("assets") or [])
    if not download_url:
        download_url = str(data.get("html_url") or RELEASES_PAGE)
    return ReleaseInfo(
        version=str(data.get("tag_name") or data.get("name") or "").strip(),
        download_url=download_url,
        published_at=str(data.get("published_at") or "").strip(),
        notes=str(data.get("body") or "").strip(),
        prerelease=bool(data.get("prerelease")),
    )


def fetch_latest_release(include_prereleases: bool = False,
                         api_url: str = GITHUB_RELEASES_API,
                         timeout: int = 10) -> Optional[ReleaseInfo]:
    """Return the newest eligible release, or None when there are none."""
    request = Request(api_url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "ChapterForge-Updater",
    })
    try:
        with urlopen(request, timeout=timeout, context=_ssl_context()) as resp:
            payload = resp.read().decode("utf-8", errors="strict")
    except Exception as exc:  # network, TLS, timeout
        raise UpdateCheckError(str(exc)) from exc

    try:
        releases = json.loads(payload)
    except ValueError as exc:
        raise UpdateCheckError("Malformed releases response.") from exc
    if not isinstance(releases, list):
        raise UpdateCheckError("Unexpected releases response.")

    candidates = [r for r in releases
                  if isinstance(r, dict) and not r.get("draft")]
    if not include_prereleases:
        candidates = [r for r in candidates if not r.get("prerelease")]
    if not candidates:
        return None
    best = max(candidates, key=lambda r: _version_tuple(str(r.get("tag_name") or "")))
    return _release_from_json(best)


def is_newer_version(current: str, available: str) -> bool:
    return _version_tuple(available) > _version_tuple(current)


def check_for_update(include_prereleases: bool = False
                     ) -> Optional[ReleaseInfo]:
    """Return a :class:`ReleaseInfo` if a newer release exists, else None."""
    latest = fetch_latest_release(include_prereleases=include_prereleases)
    if latest and is_newer_version(__version__, latest.version):
        return latest
    return None


def _version_tuple(value: str):
    cleaned = value.strip().lstrip("v")
    core, separator, suffix = cleaned.partition("-")
    parts = core.split(".")
    integers: List[int] = []
    for index in range(3):
        if index < len(parts):
            token = "".join(c for c in parts[index] if c.isdigit())
            integers.append(int(token or "0"))
        else:
            integers.append(0)
    prerelease = _prerelease_rank(suffix) if separator else _STABLE_PRERELEASE_RANK
    return integers[0], integers[1], integers[2], prerelease


def _prerelease_rank(suffix: str) -> tuple:
    lowered = suffix.strip().lower()
    if lowered.startswith("rc"):
        tier = 2
    elif lowered.startswith(("beta", "b")):
        tier = 1
    else:
        tier = 0
    number = "".join(c for c in lowered if c.isdigit())
    return tier, int(number or "0")


# ---------------------------------------------------------------------------
# Downloading and applying an update
# ---------------------------------------------------------------------------


def _platform_installer_suffixes() -> tuple:
    """Asset suffixes we can actually *run* to install (no archives)."""
    if sys.platform == "darwin":
        return (".dmg", ".pkg")
    if sys.platform.startswith("win"):
        return (".exe", ".msi")
    return ()


def is_installable_asset(url: str) -> bool:
    """True when *url* is a trusted, directly-runnable installer for this OS."""
    if not url:
        return False
    try:
        _validate_remote_url(url)
    except UpdateCheckError:
        return False
    suffixes = _platform_installer_suffixes()
    if not suffixes:
        return False
    return urlparse(url).path.lower().endswith(suffixes)


def _safe_asset_name(url: str) -> str:
    name = os.path.basename(urlparse(url).path) or "ChapterForge-Setup"
    name = "".join(c for c in name if c not in '<>:"/\\|?*').strip()
    return name or "ChapterForge-Setup"


def download_release_asset(release: "ReleaseInfo",
                           dest_dir: Optional[str] = None,
                           progress: Optional[Callable[[int, int], None]] = None,
                           timeout: int = 30) -> str:
    """Download *release*'s installer asset and return the local file path.

    The URL is re-validated (HTTPS + trusted host) before any bytes are read.
    *progress* is called as ``progress(bytes_read, total_bytes)`` (``total`` is
    0 when the server does not report a length). Raises
    :class:`UpdateCheckError` on any failure.
    """
    url = release.download_url
    _validate_remote_url(url)
    if dest_dir is None:
        dest_dir = tempfile.mkdtemp(prefix="chapterforge_update_")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, _safe_asset_name(url))
    request = Request(url, headers={"User-Agent": "ChapterForge-Updater"})
    try:
        with urlopen(request, timeout=timeout, context=_ssl_context()) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            read = 0
            with open(dest, "wb") as fh:
                while True:
                    block = resp.read(64 * 1024)
                    if not block:
                        break
                    fh.write(block)
                    read += len(block)
                    if progress:
                        progress(read, total)
    except UpdateCheckError:
        raise
    except Exception as exc:  # network, TLS, timeout, disk
        try:
            if os.path.exists(dest):
                os.remove(dest)
        except OSError:
            pass
        raise UpdateCheckError(str(exc)) from exc
    return dest


def launch_installer(path: str) -> None:
    """Start the downloaded installer in a detached process.

    The caller should close ChapterForge immediately afterwards so the
    installer can replace the application files. Raises
    :class:`UpdateCheckError` if the installer cannot be started.
    """
    if not os.path.isfile(path):
        raise UpdateCheckError("The downloaded installer could not be found.")
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as exc:
        raise UpdateCheckError(f"Could not start the installer: {exc}") from exc

