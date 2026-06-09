"""PublishService: orchestrates publishing a built master to one or more
saved destinations.

Mirrors the shape of chapterforge.auphonic.service.AuphonicService - a thin
facade instantiated once and shared across the app, never importing wx, and
returning plain data so callers (GUI, watcher, CLI) decide how to present
results. Safe to drive entirely from a background worker thread.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from ..core import BuildCancelled, Canceller
from . import sftp
from .destinations import Destination, get_default, load_destinations, resolve

ProgressCallback = Callable[[Destination, int, int], None]


@dataclass
class PublishResult:
    destination: Destination
    success: bool
    message: str
    remote_path: str = ""


class PublishService:
    """Facade over destination resolution and provider transports."""

    # ------------------------------------------------------------------
    # Destination lookup
    # ------------------------------------------------------------------

    def destinations(self) -> List[Destination]:
        return load_destinations()

    def default_destination(self) -> Optional[Destination]:
        return get_default()

    def resolve_destinations(self, spec: str) -> List[Destination]:
        """Resolve a stored spec ("default", a comma-separated id list, or
        empty) to concrete, enabled Destination objects."""
        return resolve(spec)

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish_one(self, destination: Destination, local_path: str, *,
                    progress: Optional[Callable[[int, int], None]] = None,
                    canceller: Optional[Canceller] = None) -> PublishResult:
        """Upload *local_path* to a single destination.

        Never raises for ordinary failures - they're reported in the
        returned PublishResult. BuildCancelled propagates so callers driving
        multiple destinations can stop early.
        """
        if destination.provider != "sftp":
            return PublishResult(destination, False,
                                 f"Unsupported provider '{destination.provider}'.")
        try:
            remote_path = sftp.upload(
                destination.host, destination.port, destination.username, local_path,
                password=destination.password(),
                key_path=destination.key_path,
                passphrase=destination.passphrase(),
                remote_dir=destination.remote_dir,
                progress=progress,
                canceller=canceller,
            )
            return PublishResult(destination, True,
                                 f"Uploaded to {destination.name} ({remote_path}).",
                                 remote_path=remote_path)
        except BuildCancelled:
            raise
        except sftp.SftpError as exc:
            return PublishResult(destination, False, f"{destination.name}: {exc}")

    def publish(self, local_path: str, destinations: List[Destination], *,
                progress: Optional[ProgressCallback] = None,
                canceller: Optional[Canceller] = None) -> List[PublishResult]:
        """Upload *local_path* to each destination in turn.

        Stops early (returning whatever results were collected so far) if
        *canceller* is cancelled mid-run.
        """
        results: List[PublishResult] = []
        for destination in destinations:
            if canceller and canceller.cancelled:
                break

            def _on_progress(transferred: int, total: int, _dest=destination) -> None:
                if progress:
                    progress(_dest, transferred, total)

            try:
                results.append(self.publish_one(destination, local_path,
                                                 progress=_on_progress, canceller=canceller))
            except BuildCancelled:
                break
        return results

    def test_connection(self, destination: Destination) -> Tuple[bool, str]:
        """Quick connect/disconnect to verify a destination's settings.

        Returns (success, message); never raises.
        """
        if destination.provider != "sftp":
            return False, f"Unsupported provider '{destination.provider}'."
        try:
            sftp.test_connection(
                destination.host, destination.port, destination.username,
                password=destination.password(),
                key_path=destination.key_path,
                passphrase=destination.passphrase(),
            )
            return True, f"Connected to {destination.host} successfully."
        except sftp.SftpError as exc:
            return False, str(exc)
