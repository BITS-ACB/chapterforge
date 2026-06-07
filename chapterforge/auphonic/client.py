"""Auphonic REST API client.

All network I/O lives here. Never imports wx or any UI module.
Uses stdlib urllib only - no third-party HTTP library required.
"""
from __future__ import annotations

import json
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict, List, Optional

from .models import AuphonicUser

AUPHONIC_BASE = "https://auphonic.com"
_API = f"{AUPHONIC_BASE}/api"


class AuphonicError(Exception):
    """Raised when the Auphonic API returns an error."""
    def __init__(self, message: str, status_code: int = 0, raw: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.raw = raw


class AuphonicClient:
    """Thin wrapper around the Auphonic REST API.

    Callers supply a token via ``set_token()``. All requests are authenticated
    with ``Bearer`` auth. Raises ``AuphonicError`` on API-level errors.
    """

    def __init__(self, token: str = ""):
        self._token = token

    def set_token(self, token: str) -> None:
        self._token = token

    # ------------------------------------------------------------------
    # Internal request helpers
    # ------------------------------------------------------------------

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        h = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }
        if extra:
            h.update(extra)
        return h

    def _get(self, path: str, params: Optional[Dict[str, str]] = None) -> Any:
        url = f"{_API}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=self._headers())
        return self._send(req)

    def _post_json(self, path: str, payload: Dict[str, Any]) -> Any:
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{_API}{path}",
            data=body,
            method="POST",
            headers=self._headers({"Content-Type": "application/json"}),
        )
        return self._send(req)

    def _post_multipart(self, path: str, fields: Dict[str, str],
                        file_field: str, filename: str,
                        data: bytes, content_type: str) -> Any:
        boundary = uuid.uuid4().hex
        body = _encode_multipart(boundary, fields, file_field, filename, data, content_type)
        req = urllib.request.Request(
            f"{_API}{path}",
            data=body,
            method="POST",
            headers=self._headers({
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            }),
        )
        return self._send(req)

    def _delete(self, path: str) -> Any:
        req = urllib.request.Request(
            f"{_API}{path}", method="DELETE", headers=self._headers()
        )
        return self._send(req)

    def _send(self, req: urllib.request.Request) -> Any:
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8", "replace")
                if not raw.strip():
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                data = json.loads(raw)
                msg = data.get("status_string") or data.get("detail") or str(data)
            except Exception:
                msg = raw or str(exc)
            raise AuphonicError(msg, status_code=exc.code, raw=raw) from exc
        except urllib.error.URLError as exc:
            raise AuphonicError(f"Network error: {exc.reason}") from exc

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    def get_user(self) -> AuphonicUser:
        data = self._get("/user.json")
        d = data.get("data", data)
        return AuphonicUser(
            username=d.get("username", ""),
            email=d.get("email", ""),
            user_id=d.get("user_id", d.get("username", "")),
            credits=float(d.get("credits", 0) or 0),
            onetime_credits=float(d.get("onetime_credits", 0) or 0),
            recurring_credits=float(d.get("recurring_credits", 0) or 0),
            recharge_date=str(d.get("recharge_date", "") or ""),
            recharge_recurring_credits=float(d.get("recharge_recurring_credits", 0) or 0),
        )

    # ------------------------------------------------------------------
    # Dynamic schema / info
    # ------------------------------------------------------------------

    def get_info(self) -> Dict[str, Any]:
        return self._get("/info.json").get("data", {})

    def get_algorithms(self) -> Dict[str, Any]:
        return self._get("/info/algorithms.json").get("data", {})

    def get_output_formats(self) -> List[Dict[str, Any]]:
        data = self._get("/info/output_files.json").get("data", [])
        return data if isinstance(data, list) else list(data.values())

    def get_service_types(self) -> Dict[str, Any]:
        return self._get("/info/service_types.json").get("data", {})

    def get_production_statuses(self) -> Dict[str, Any]:
        return self._get("/info/production_status.json").get("data", {})

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------

    def list_presets(self, minimal: bool = True) -> List[Dict[str, Any]]:
        params = {"minimal_data": "1"} if minimal else {}
        data = self._get("/presets.json", params).get("data", [])
        return data if isinstance(data, list) else []

    def get_preset(self, uuid: str) -> Dict[str, Any]:
        return self._get(f"/preset/{uuid}.json").get("data", {})

    def create_preset(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._post_json("/presets.json", payload).get("data", {})

    def update_preset(self, uuid: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._post_json(f"/preset/{uuid}.json", payload).get("data", {})

    # ------------------------------------------------------------------
    # External services
    # ------------------------------------------------------------------

    def list_services(self) -> List[Dict[str, Any]]:
        data = self._get("/services.json").get("data", [])
        return data if isinstance(data, list) else []

    def list_service_files(self, service_uuid: str) -> List[Dict[str, Any]]:
        data = self._get(f"/service/{service_uuid}/ls.json").get("data", [])
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Productions
    # ------------------------------------------------------------------

    def create_production(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._post_json("/productions.json", payload).get("data", {})

    def update_production(self, prod_uuid: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._post_json(f"/production/{prod_uuid}.json", payload).get("data", {})

    def upload_file(self, prod_uuid: str, filename: str,
                    data: bytes, content_type: str = "") -> Dict[str, Any]:
        ct = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return self._post_multipart(
            f"/production/{prod_uuid}/upload.json",
            fields={},
            file_field="input_file",
            filename=filename,
            data=data,
            content_type=ct,
        ).get("data", {})

    def start_production(self, prod_uuid: str) -> Dict[str, Any]:
        return self._post_json(f"/production/{prod_uuid}/start.json", {}).get("data", {})

    def get_production(self, prod_uuid: str) -> Dict[str, Any]:
        return self._get(f"/production/{prod_uuid}.json").get("data", {})

    def get_production_status(self, prod_uuid: str) -> Dict[str, Any]:
        return self._get(f"/production/{prod_uuid}/status.json").get("data", {})

    def publish_production(self, prod_uuid: str) -> Dict[str, Any]:
        return self._post_json(f"/production/{prod_uuid}/publish.json", {}).get("data", {})

    def delete_production(self, prod_uuid: str) -> None:
        self._delete(f"/production/{prod_uuid}.json")

    def list_productions(self) -> List[Dict[str, Any]]:
        data = self._get("/productions.json").get("data", [])
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Downloads
    # ------------------------------------------------------------------

    def download_output(self, url: str) -> bytes:
        """Download a result file from an Auphonic output URL."""
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            raise AuphonicError(f"Download failed: {exc.code}", status_code=exc.code) from exc
        except urllib.error.URLError as exc:
            raise AuphonicError(f"Download error: {exc.reason}") from exc


# ---------------------------------------------------------------------------
# Multipart encoding (stdlib, no external lib)
# ---------------------------------------------------------------------------

def _encode_multipart(boundary: str, fields: Dict[str, str],
                       file_field: str, filename: str,
                       data: bytes, content_type: str) -> bytes:
    parts = []
    crlf = b"\r\n"
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}'.encode()
        )
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
        f'filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'.encode()
        + data
    )
    parts.append(f'--{boundary}--'.encode())
    return crlf.join(parts)
