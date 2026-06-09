"""SFTP transport for publishing built masters to remote destinations.

Thin wrapper around paramiko: connects with password or public-key auth,
uploads with progress callbacks, and supports cooperative cancellation using
the same shape as chapterforge.core.Canceller (BuildCancelled raised mid-
transfer when the user cancels).

Key formats: paramiko.PKey.from_path() loads OpenSSH-format private keys
(RSA, Ed25519, ECDSA, DSA - including the newer OpenSSH container format).
PuTTY .ppk and SecureCRT key files are not natively readable by paramiko;
users with those need to export an OpenSSH-format key first (PuTTYgen's
Conversions > Export OpenSSH key, or SecureCRT's key export to OpenSSH).
"""
from __future__ import annotations

import os
from typing import Callable, Optional

import paramiko

from ..core import BuildCancelled, Canceller

ProgressCallback = Callable[[int, int], None]


class SftpError(Exception):
    pass


def _load_key(key_path: str, passphrase: Optional[str]) -> paramiko.PKey:
    try:
        return paramiko.PKey.from_path(key_path, passphrase=passphrase or None)
    except paramiko.PasswordRequiredException as exc:
        raise SftpError("This private key is encrypted and requires a passphrase.") from exc
    except paramiko.SSHException as exc:
        raise SftpError(
            f"Could not read the private key at {key_path}. PuTTY (.ppk) and "
            "SecureCRT key files must be converted to OpenSSH format first."
        ) from exc
    except OSError as exc:
        raise SftpError(f"Could not open the private key at {key_path}: {exc}") from exc


def connect(host: str, port: int, username: str, *,
            password: Optional[str] = None,
            key_path: str = "",
            passphrase: Optional[str] = None,
            timeout: float = 20.0) -> paramiko.SFTPClient:
    """Open an SFTP session. Raises SftpError on any failure.

    Closing the returned SFTPClient also closes its underlying transport.
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        if key_path:
            pkey = _load_key(key_path, passphrase)
            client.connect(host, port=port, username=username, pkey=pkey,
                           timeout=timeout, allow_agent=False, look_for_keys=False)
        else:
            client.connect(host, port=port, username=username, password=password,
                           timeout=timeout, allow_agent=False, look_for_keys=False)
        return client.open_sftp()
    except SftpError:
        client.close()
        raise
    except paramiko.AuthenticationException as exc:
        client.close()
        raise SftpError("Authentication failed - check the username, password, or key.") from exc
    except (paramiko.SSHException, OSError) as exc:
        client.close()
        raise SftpError(f"Could not connect to {host}:{port} - {exc}") from exc


def _ensure_remote_dir(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    """Create *remote_dir* (and any missing parents) if it doesn't exist."""
    remote_dir = remote_dir.strip()
    if not remote_dir or remote_dir in ("/", "."):
        return
    parts = [p for p in remote_dir.replace("\\", "/").split("/") if p]
    path = "/" if remote_dir.startswith("/") else ""
    for part in parts:
        path = f"{path}{part}" if path in ("", "/") else f"{path}/{part}"
        try:
            sftp.stat(path)
        except FileNotFoundError:
            sftp.mkdir(path)


def upload(host: str, port: int, username: str, local_path: str, *,
           password: Optional[str] = None,
           key_path: str = "",
           passphrase: Optional[str] = None,
           remote_dir: str = "",
           progress: Optional[ProgressCallback] = None,
           canceller: Optional[Canceller] = None,
           timeout: float = 20.0) -> str:
    """Upload *local_path* into *remote_dir* on the SFTP server.

    Returns the full remote path on success. Raises SftpError on transport
    failure, or BuildCancelled if *canceller* is cancelled mid-transfer.
    """
    if canceller and canceller.cancelled:
        raise BuildCancelled("Publish cancelled.")

    sftp = connect(host, port, username, password=password, key_path=key_path,
                   passphrase=passphrase, timeout=timeout)
    try:
        _ensure_remote_dir(sftp, remote_dir)
        filename = os.path.basename(local_path)
        remote_dir = remote_dir.strip().rstrip("/")
        remote_path = f"{remote_dir}/{filename}" if remote_dir else filename

        def _callback(transferred: int, total: int) -> None:
            if canceller and canceller.cancelled:
                raise BuildCancelled("Publish cancelled.")
            if progress:
                progress(transferred, total)

        sftp.put(local_path, remote_path, callback=_callback, confirm=True)
        return remote_path
    except BuildCancelled:
        raise
    except (paramiko.SSHException, OSError) as exc:
        raise SftpError(f"Upload failed: {exc}") from exc
    finally:
        sftp.close()


def test_connection(host: str, port: int, username: str, *,
                     password: Optional[str] = None,
                     key_path: str = "",
                     passphrase: Optional[str] = None,
                     timeout: float = 15.0) -> None:
    """Connect and immediately disconnect. Raises SftpError on failure."""
    sftp = connect(host, port, username, password=password, key_path=key_path,
                   passphrase=passphrase, timeout=timeout)
    sftp.close()
