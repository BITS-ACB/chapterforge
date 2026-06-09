"""Saved publishing destinations for ChapterForge.

A *destination* is a remote location ChapterForge can upload a finished
master to - currently SFTP servers. Stored as atomic JSON in the per-user
config dir, tolerant of corruption, mirroring chapterforge.watcher_config's
Process storage (same load/save/atomic-write/tolerant-loading shape). Secrets
(passwords, key passphrases) are never written to this file - only a flag
noting one is stored, looked up by destination id via
chapterforge.publish.credentials.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from .. import settings as settings_mod
from . import credentials

_DESTINATIONS_FILE = "publish_destinations.json"


@dataclass
class Destination:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    name: str = "New destination"
    provider: str = "sftp"
    host: str = ""
    port: int = 22
    username: str = ""
    auth_method: str = "password"   # 'password' | 'key'
    key_path: str = ""
    has_password: bool = False
    has_passphrase: bool = False
    remote_dir: str = ""
    is_default: bool = False
    enabled: bool = True

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "Destination":
        dest = cls(id=str(data.get("id") or uuid.uuid4().hex))
        for f in dest.__dataclass_fields__:  # type: ignore[attr-defined]
            if f != "id" and f in data:
                setattr(dest, f, data[f])
        dest.has_password = bool(dest.has_password)
        dest.has_passphrase = bool(dest.has_passphrase)
        dest.is_default = bool(dest.is_default)
        dest.enabled = bool(dest.enabled)
        try:
            dest.port = int(dest.port)
        except (TypeError, ValueError):
            dest.port = 22
        return dest

    # -- Credential helpers -------------------------------------------------
    # Secrets are stored separately (see credentials.py); these helpers keep
    # the has_password/has_passphrase flags in sync with what's actually saved.

    def password_key(self) -> str:
        return f"{self.id}:password"

    def passphrase_key(self) -> str:
        return f"{self.id}:passphrase"

    def password(self) -> Optional[str]:
        return credentials.load_secret(self.password_key()) if self.has_password else None

    def passphrase(self) -> Optional[str]:
        return credentials.load_secret(self.passphrase_key()) if self.has_passphrase else None

    def set_password(self, secret: str) -> None:
        if secret:
            credentials.save_secret(self.password_key(), secret)
            self.has_password = True
        else:
            credentials.delete_secret(self.password_key())
            self.has_password = False

    def set_passphrase(self, secret: str) -> None:
        if secret:
            credentials.save_secret(self.passphrase_key(), secret)
            self.has_passphrase = True
        else:
            credentials.delete_secret(self.passphrase_key())
            self.has_passphrase = False

    def forget_credentials(self) -> None:
        credentials.delete_secret(self.password_key())
        credentials.delete_secret(self.passphrase_key())
        self.has_password = False
        self.has_passphrase = False

    def describe(self) -> str:
        flag = "" if self.enabled else " (disabled)"
        star = " - default" if self.is_default else ""
        target = f"{self.username}@{self.host}" if self.username else self.host
        return f"{self.name} ({target}){star}{flag}"


def _destinations_path() -> str:
    return os.path.join(settings_mod.config_dir(), _DESTINATIONS_FILE)


def load_destinations() -> List[Destination]:
    try:
        with open(_destinations_path(), "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return []
    items = raw.get("destinations") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []
    return [Destination.from_dict(d) for d in items if isinstance(d, dict)]


def save_destinations(destinations: List[Destination]) -> None:
    try:
        os.makedirs(settings_mod.config_dir(), exist_ok=True)
        tmp = _destinations_path() + ".tmp"
        payload = {"destinations": [d.to_dict() for d in destinations]}
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(tmp, _destinations_path())
    except OSError:
        pass


def get_default(destinations: Optional[List[Destination]] = None) -> Optional[Destination]:
    """The user's chosen default destination, or the first enabled one."""
    items = load_destinations() if destinations is None else destinations
    for d in items:
        if d.is_default and d.enabled:
            return d
    enabled = [d for d in items if d.enabled]
    return enabled[0] if enabled else None


def find_by_id(dest_id: str, destinations: Optional[List[Destination]] = None) -> Optional[Destination]:
    items = load_destinations() if destinations is None else destinations
    for d in items:
        if d.id == dest_id:
            return d
    return None


def resolve(spec: str, destinations: Optional[List[Destination]] = None) -> List[Destination]:
    """Resolve a comma-separated spec of destination ids (or the literal
    "default") to an ordered, de-duplicated list of enabled destinations."""
    items = load_destinations() if destinations is None else destinations
    spec = (spec or "").strip()
    if not spec:
        return []
    seen = set()
    result: List[Destination] = []
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        dest = get_default(items) if token.lower() == "default" else find_by_id(token, items)
        if dest and dest.enabled and dest.id not in seen:
            seen.add(dest.id)
            result.append(dest)
    return result
