"""Secure credential storage for publish destinations.

Two backends are tried in order so credentials persist regardless of how
ChapterForge is installed or run:

  1. Windows Credential Manager, via direct ctypes calls into advapi32.dll
     (CredWriteW / CredReadW / CredDeleteW) - the OS-native, per-user store.
  2. A DPAPI-encrypted local file at %APPDATA%\\ChapterForge\\publish_credentials.bin
     (XOR-obfuscated fallback on non-Windows), mirroring the token-storage
     approach in chapterforge.auphonic.auth. This is what guarantees portable
     installs can still persist credentials even where Credential Manager
     access is unavailable, inconsistent, or simply not the right place to
     keep things.

Writes try Credential Manager first and fall back to the encrypted file on
any failure; reads check Credential Manager first, then the encrypted file,
so a secret saved by either backend is always found again.
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
from typing import Dict, Optional

from ..settings import config_dir

_CRED_FILE = "publish_credentials.bin"
_CRED_TARGET_PREFIX = "ChapterForge:publish:"
_CRED_TYPE_GENERIC = 1          # CRED_TYPE_GENERIC
_CRED_PERSIST_LOCAL_MACHINE = 2  # CRED_PERSIST_LOCAL_MACHINE


# ---------------------------------------------------------------------------
# Backend 1: Windows Credential Manager (advapi32 via ctypes)
# ---------------------------------------------------------------------------

class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]


class _CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", ctypes.c_uint32),
        ("Type", ctypes.c_uint32),
        ("TargetName", ctypes.c_wchar_p),
        ("Comment", ctypes.c_wchar_p),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", ctypes.c_uint32),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
        ("Persist", ctypes.c_uint32),
        ("AttributeCount", ctypes.c_uint32),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", ctypes.c_wchar_p),
        ("UserName", ctypes.c_wchar_p),
    ]


def _cred_target(key: str) -> str:
    return _CRED_TARGET_PREFIX + key


def _cred_write(key: str, secret: str) -> bool:
    if os.name != "nt":
        return False
    try:
        data = secret.encode("utf-8")
        buf = ctypes.create_string_buffer(data, len(data))
        cred = _CREDENTIAL(
            Flags=0,
            Type=_CRED_TYPE_GENERIC,
            TargetName=_cred_target(key),
            Comment=None,
            LastWritten=_FILETIME(),
            CredentialBlobSize=len(data),
            CredentialBlob=ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)),
            Persist=_CRED_PERSIST_LOCAL_MACHINE,
            AttributeCount=0,
            Attributes=None,
            TargetAlias=None,
            UserName="ChapterForge",
        )
        return bool(ctypes.windll.advapi32.CredWriteW(ctypes.byref(cred), 0))
    except Exception:
        return False


def _cred_read(key: str) -> Optional[str]:
    if os.name != "nt":
        return None
    try:
        pcred = ctypes.POINTER(_CREDENTIAL)()
        ok = ctypes.windll.advapi32.CredReadW(
            _cred_target(key), _CRED_TYPE_GENERIC, 0, ctypes.byref(pcred))
        if not ok:
            return None
        try:
            cred = pcred.contents
            blob = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
            return blob.decode("utf-8")
        finally:
            ctypes.windll.advapi32.CredFree(pcred)
    except Exception:
        return None


def _cred_delete(key: str) -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.advapi32.CredDeleteW(_cred_target(key), _CRED_TYPE_GENERIC, 0)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Backend 2: DPAPI-encrypted local file (mirrors chapterforge.auphonic.auth)
# ---------------------------------------------------------------------------

def _machine_key() -> bytes:
    seed = (os.environ.get("COMPUTERNAME", "") + os.environ.get("USERNAME", "")
            + "ChapterForge-publish")
    return hashlib.sha256(seed.encode()).digest()


def _encrypt(plaintext: str) -> bytes:
    if os.name == "nt":
        try:
            return _dpapi_protect(plaintext.encode())
        except Exception:
            pass
    key = _machine_key()
    data = plaintext.encode()
    encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return base64.b64encode(b"v1:" + encrypted)


def _decrypt(ciphertext: bytes) -> str:
    if os.name == "nt":
        try:
            return _dpapi_unprotect(ciphertext).decode()
        except Exception:
            pass
    raw = base64.b64decode(ciphertext)
    if raw.startswith(b"v1:"):
        raw = raw[3:]
    key = _machine_key()
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(raw)).decode()


def _dpapi_protect(data: bytes) -> bytes:
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_char))]
    buf = ctypes.create_string_buffer(data)
    inblob = DATA_BLOB(len(data), buf)
    outblob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(inblob), None, None, None, None, 0, ctypes.byref(outblob)
    ):
        raise RuntimeError("DPAPI protect failed")
    protected = ctypes.string_at(outblob.pbData, outblob.cbData)
    ctypes.windll.kernel32.LocalFree(outblob.pbData)
    return base64.b64encode(b"dpapi:" + protected)


def _dpapi_unprotect(ciphertext: bytes) -> bytes:
    raw = base64.b64decode(ciphertext)
    if raw.startswith(b"dpapi:"):
        raw = raw[6:]
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_char))]
    buf = ctypes.create_string_buffer(raw)
    inblob = DATA_BLOB(len(raw), buf)
    outblob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(inblob), None, None, None, None, 0, ctypes.byref(outblob)
    ):
        raise RuntimeError("DPAPI unprotect failed")
    plaintext = ctypes.string_at(outblob.pbData, outblob.cbData)
    ctypes.windll.kernel32.LocalFree(outblob.pbData)
    return plaintext


def _cred_path() -> str:
    return os.path.join(config_dir(), _CRED_FILE)


def _load_file_store() -> Dict[str, str]:
    path = _cred_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
        data = json.loads(_decrypt(raw))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_file_store(store: Dict[str, str]) -> None:
    os.makedirs(config_dir(), exist_ok=True)
    payload = json.dumps(store)
    with open(_cred_path(), "wb") as fh:
        fh.write(_encrypt(payload))


def _file_write(key: str, secret: str) -> bool:
    try:
        store = _load_file_store()
        store[key] = secret
        _save_file_store(store)
        return True
    except Exception:
        return False


def _file_read(key: str) -> Optional[str]:
    return _load_file_store().get(key)


def _file_delete(key: str) -> None:
    try:
        store = _load_file_store()
        if key in store:
            del store[key]
            _save_file_store(store)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_secret(key: str, secret: str) -> None:
    """Persist *secret* under *key*.

    Tries Windows Credential Manager first; falls back to the encrypted local
    file on any failure (missing API, access denied, non-Windows, etc). Also
    clears any stale copy left in the other backend so later reads are
    unambiguous.
    """
    if _cred_write(key, secret):
        _file_delete(key)
        return
    _file_write(key, secret)


def load_secret(key: str) -> Optional[str]:
    """Return the stored secret for *key*, checking both backends."""
    value = _cred_read(key)
    if value is not None:
        return value
    return _file_read(key)


def delete_secret(key: str) -> None:
    """Remove *key* from both backends."""
    _cred_delete(key)
    _file_delete(key)
