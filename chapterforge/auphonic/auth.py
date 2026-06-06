"""OAuth 2.0 for Auphonic (desktop / native app flow).

Uses the RFC 8252 loopback redirect pattern:
  1. Open system browser to Auphonic authorization URL.
  2. Start a one-shot HTTP server on a random local port.
  3. Auphonic redirects to http://localhost:{port}/callback?code=...
  4. Exchange the code for access + refresh tokens.
  5. Store tokens encrypted via Windows DPAPI (or base64 fallback).

OAuth app credentials come from:
  - AUPHONIC_CLIENT_ID / AUPHONIC_CLIENT_SECRET env vars (for CI / dev)
  - settings_mod values (for production)
  - Hardcoded placeholders that produce a clear error if unconfigured.

Token storage: %APPDATA%\\ChapterForge\\auphonic_token.bin (DPAPI-protected on
Windows; base64-obfuscated on other platforms as fallback).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import socket
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Optional, Tuple

from ..settings import config_dir

AUPHONIC_BASE = "https://auphonic.com"
TOKEN_ENDPOINT = f"{AUPHONIC_BASE}/oauth2/token/"
AUTHORIZE_ENDPOINT = f"{AUPHONIC_BASE}/oauth2/authorize/"

_DEFAULT_CLIENT_ID = os.environ.get("AUPHONIC_CLIENT_ID", "")
_DEFAULT_CLIENT_SECRET = os.environ.get("AUPHONIC_CLIENT_SECRET", "")

_TOKEN_FILE = "auphonic_token.bin"


# ---------------------------------------------------------------------------
# Token encryption (DPAPI on Windows, obfuscation fallback elsewhere)
# ---------------------------------------------------------------------------

def _machine_key() -> bytes:
    """Derive a stable per-machine key for fallback encryption."""
    seed = os.environ.get("COMPUTERNAME", "") + os.environ.get("USERNAME", "") + "ChapterForge-auphonic"
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
    import ctypes
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
    import ctypes
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


# ---------------------------------------------------------------------------
# Token storage
# ---------------------------------------------------------------------------

def _token_path() -> str:
    return os.path.join(config_dir(), _TOKEN_FILE)


def save_tokens(access_token: str, refresh_token: str, expires_at: float) -> None:
    payload = json.dumps({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
    })
    os.makedirs(config_dir(), exist_ok=True)
    with open(_token_path(), "wb") as fh:
        fh.write(_encrypt(payload))


def load_tokens() -> Optional[Dict[str, object]]:
    path = _token_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
        return json.loads(_decrypt(raw))
    except Exception:
        return None


def delete_tokens() -> None:
    path = _token_path()
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def get_valid_access_token(client_id: str = "", client_secret: str = "") -> Optional[str]:
    """Return a valid access token, refreshing if needed. None if not connected."""
    data = load_tokens()
    if not data:
        return None
    cid = client_id or _DEFAULT_CLIENT_ID
    csec = client_secret or _DEFAULT_CLIENT_SECRET
    if time.time() < float(data.get("expires_at", 0)) - 60:
        return str(data["access_token"])
    refreshed = _refresh_access_token(str(data.get("refresh_token", "")), cid, csec)
    if refreshed:
        return refreshed
    return None


def _refresh_access_token(refresh_token: str, client_id: str, client_secret: str) -> Optional[str]:
    if not refresh_token:
        return None
    try:
        body = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }).encode()
        req = urllib.request.Request(TOKEN_ENDPOINT, data=body, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        access = data["access_token"]
        new_refresh = data.get("refresh_token", refresh_token)
        expires_in = int(data.get("expires_in", 3600))
        save_tokens(access, new_refresh, time.time() + expires_in)
        return access
    except Exception:
        return None


# ---------------------------------------------------------------------------
# OAuth loopback flow
# ---------------------------------------------------------------------------

class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """One-shot handler: captures ?code= and signals the waiting thread."""

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        error = params.get("error", [None])[0]
        self.server.oauth_code = code
        self.server.oauth_error = error
        if code:
            body = b"<html><body><h1>Connected!</h1><p>Return to ChapterForge.</p></body></html>"
        else:
            body = (
                f"<html><body><h1>Error</h1><p>{error or 'Unknown error'}</p></body></html>"
            ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, *args):  # suppress server log output
        pass


def _find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_oauth_flow(client_id: str = "", client_secret: str = "",
                   timeout: int = 120) -> Tuple[bool, str]:
    """Open the system browser and wait for the OAuth callback.

    Returns (success, error_message). On success, tokens are saved.
    """
    cid = client_id or _DEFAULT_CLIENT_ID
    csec = client_secret or _DEFAULT_CLIENT_SECRET
    if not cid or not csec:
        return False, (
            "Auphonic OAuth credentials are not configured. "
            "Set AUPHONIC_CLIENT_ID and AUPHONIC_CLIENT_SECRET."
        )

    port = _find_free_port()
    redirect_uri = f"http://localhost:{port}/callback"
    state = secrets.token_urlsafe(16)

    params = urllib.parse.urlencode({
        "client_id": cid,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": "",
    })
    auth_url = f"{AUTHORIZE_ENDPOINT}?{params}"

    server = HTTPServer(("127.0.0.1", port), _OAuthCallbackHandler)
    server.oauth_code = None
    server.oauth_error = None
    server.timeout = timeout

    webbrowser.open(auth_url)

    def _serve():
        server.handle_request()

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    t.join(timeout=timeout + 5)

    code = server.oauth_code
    error = server.oauth_error

    if error:
        return False, f"Auphonic authorization declined: {error}"
    if not code:
        return False, "Authorization timed out. Please try again."

    return _exchange_code(code, redirect_uri, cid, csec)


def _exchange_code(code: str, redirect_uri: str,
                   client_id: str, client_secret: str) -> Tuple[bool, str]:
    try:
        body = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        }).encode()
        req = urllib.request.Request(TOKEN_ENDPOINT, data=body, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        access = data.get("access_token", "")
        refresh = data.get("refresh_token", "")
        expires_in = int(data.get("expires_in", 3600))
        if not access:
            return False, "Token exchange returned no access token."
        save_tokens(access, refresh, time.time() + expires_in)
        return True, ""
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        return False, f"Token exchange failed ({exc.code}): {raw}"
    except Exception as exc:
        return False, f"Token exchange error: {exc}"
