"""High-level AuphonicService: orchestrates client, auth, db, and polling.

This is the main entry point for the UI and CLI layers.
Never imports wx directly - all UI callbacks go through the caller.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .auth import get_valid_access_token, run_oauth_flow, delete_tokens, load_tokens
from .client import AuphonicClient, AuphonicError
from .db import (
    insert_job, update_job, get_job, get_job_by_uuid, list_jobs,
    insert_output, list_outputs,
    get_cached_schema, set_cached_schema,
    record_credit_snapshot,
)
from .estimate import estimate_credits, credits_sufficient
from .models import AuphonicUser, AuphonicJob, JobStatus, ProductionRequest
from .output_filter import filter_outputs, classify_output, is_allowed_output
from .polling import ProductionPoller
from .validate import validate_local_file, validate_remote_url, AudioValidationError


class AuphonicService:
    """Facade over all Auphonic subsystems.

    Instantiate once and share across the app. Thread-safe for read operations;
    mutations should originate from the main thread or be dispatched via callbacks.
    """

    def __init__(self, client_id: str = "", client_secret: str = ""):
        self._client_id = client_id
        self._client_secret = client_secret
        self._client = AuphonicClient()
        self._pollers: Dict[str, ProductionPoller] = {}

    # ------------------------------------------------------------------
    # Connection / auth
    # ------------------------------------------------------------------

    def is_connected(self) -> bool:
        token = get_valid_access_token(self._client_id, self._client_secret)
        return bool(token)

    def connect(self, timeout: int = 120) -> Tuple[bool, str]:
        """Launch OAuth flow. Returns (success, error_message)."""
        ok, err = run_oauth_flow(self._client_id, self._client_secret, timeout=timeout)
        if ok:
            self._refresh_client_token()
        return ok, err

    def disconnect(self) -> None:
        delete_tokens()
        self._client.set_token("")

    def _refresh_client_token(self) -> bool:
        token = get_valid_access_token(self._client_id, self._client_secret)
        if token:
            self._client.set_token(token)
            return True
        return False

    # ------------------------------------------------------------------
    # Account / credits
    # ------------------------------------------------------------------

    def get_user(self) -> Optional[AuphonicUser]:
        if not self._refresh_client_token():
            return None
        try:
            user = self._client.get_user()
            record_credit_snapshot(
                credits=user.credits,
                onetime=user.onetime_credits,
                recurring=user.recurring_credits,
                recharge_date=user.recharge_date,
                recharge_recurring=user.recharge_recurring_credits,
                raw={},
            )
            return user
        except AuphonicError:
            return None

    # ------------------------------------------------------------------
    # Schema cache
    # ------------------------------------------------------------------

    def get_algorithms(self) -> Dict[str, Any]:
        cached = get_cached_schema("algorithms")
        if cached is not None:
            return cached
        if not self._refresh_client_token():
            return {}
        try:
            data = self._client.get_algorithms()
            set_cached_schema("algorithms", data)
            return data
        except AuphonicError:
            return {}

    def get_output_formats(self) -> List[Dict[str, Any]]:
        cached = get_cached_schema("output_files")
        if cached is not None:
            return cached
        if not self._refresh_client_token():
            return []
        try:
            data = self._client.get_output_formats()
            set_cached_schema("output_files", data)
            return data
        except AuphonicError:
            return []

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------

    def list_account_presets(self) -> List[Dict[str, Any]]:
        if not self._refresh_client_token():
            return []
        try:
            return self._client.list_presets(minimal=True)
        except AuphonicError:
            return []

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_file(self, path: str):
        """Raises AudioValidationError on rejection."""
        return validate_local_file(path)

    def validate_url(self, url: str):
        """Raises AudioValidationError on rejection."""
        return validate_remote_url(url)

    # ------------------------------------------------------------------
    # Production submission
    # ------------------------------------------------------------------

    def submit_production(
        self,
        request: ProductionRequest,
        local_file_path: str = "",
        on_update: Optional[Callable] = None,
        on_done: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
    ) -> Tuple[Optional[int], str]:
        """Create, upload (if needed), and start an Auphonic production.

        Returns (job_id, error_message). On success job_id is set and
        polling is started.
        """
        if not self._refresh_client_token():
            return None, "Not connected to Auphonic. Please connect first."

        # Credit preflight
        user = self.get_user()
        if user and request.input_file:
            try:
                probe = validate_local_file(local_file_path or request.input_file)
                est = estimate_credits(probe.duration_seconds)
                if not credits_sufficient(user.credits, est):
                    return None, (
                        f"Insufficient Auphonic credits. "
                        f"Estimated {est * 60:.1f} minutes needed; "
                        f"{user.credits * 60:.1f} minutes available."
                    )
            except AudioValidationError:
                pass  # validation already checked separately

        payload = _build_payload(request)
        job_id = insert_job(
            title=request.title,
            mode="json",
            is_multitrack=bool(request.multi_input_files),
            preset_uuid=request.preset_uuid,
            request_payload=payload,
            review_before_publishing=request.review_before_publishing,
        )

        try:
            prod = self._client.create_production(payload)
            prod_uuid = prod.get("uuid", "")
            update_job(job_id, auphonic_uuid=prod_uuid, status="ready", app_status=JobStatus.READY)

            if local_file_path and os.path.isfile(local_file_path):
                update_job(job_id, app_status=JobStatus.UPLOADING)
                with open(local_file_path, "rb") as fh:
                    data = fh.read()
                self._client.upload_file(prod_uuid, os.path.basename(local_file_path), data)

            self._client.start_production(prod_uuid)
            update_job(job_id, status="Queued", app_status=JobStatus.QUEUED,
                       started_at=_now())

        except AuphonicError as exc:
            update_job(job_id, status="Error", app_status=JobStatus.ERROR,
                       error_message=str(exc))
            return job_id, str(exc)

        # Start polling
        if prod_uuid and (on_update or on_done or on_error):
            self._start_polling(
                job_id, prod_uuid,
                on_update=on_update or _noop,
                on_done=on_done or _noop,
                on_error=on_error or _noop,
            )

        return job_id, ""

    def _start_polling(self, job_id: int, prod_uuid: str,
                       on_update: Callable, on_done: Callable, on_error: Callable):
        def _on_update(status, data):
            update_job(job_id, status=status)
            on_update(status, data)

        def _on_done(status, data):
            update_job(job_id, status=status, app_status=_map_status(status),
                       completed_at=_now(),
                       used_credits_hours=float(data.get("used_credits", 0) or 0),
                       response_json=json.dumps(data))
            self._ingest_outputs(job_id, data)
            on_done(status, data)

        def _on_error(msg):
            update_job(job_id, app_status=JobStatus.ERROR, error_message=msg)
            on_error(msg)

        poller = ProductionPoller(
            self._client, prod_uuid,
            on_update=_on_update,
            on_done=_on_done,
            on_error=_on_error,
        )
        self._pollers[prod_uuid] = poller
        poller.start()

    def stop_polling(self, prod_uuid: str) -> None:
        poller = self._pollers.pop(prod_uuid, None)
        if poller:
            poller.stop()

    def _ingest_outputs(self, job_id: int, prod_data: Dict[str, Any]) -> None:
        raw_outputs = prod_data.get("output_files", [])
        allowed = filter_outputs(raw_outputs)
        for out in allowed:
            insert_output(
                job_id=job_id,
                format=out.get("format", ""),
                ending=out.get("ending", ""),
                filename=out.get("filename", ""),
                bitrate=str(out.get("bitrate", "")),
                size_bytes=int(out.get("size", 0) or 0),
                download_url=out.get("download_url", ""),
                output_type=classify_output(out),
                is_allowed=is_allowed_output(out),
            )

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish_production(self, auphonic_uuid: str) -> Tuple[bool, str]:
        if not self._refresh_client_token():
            return False, "Not connected to Auphonic."
        try:
            self._client.publish_production(auphonic_uuid)
            row = get_job_by_uuid(auphonic_uuid)
            if row:
                update_job(row["id"], app_status=JobStatus.PUBLISHED)
            return True, ""
        except AuphonicError as exc:
            return False, str(exc)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def list_jobs(self, limit: int = 100):
        return list_jobs(limit)

    def get_job(self, job_id: int):
        return get_job(job_id)

    def get_outputs(self, job_id: int):
        return list_outputs(job_id)

    def download_output(self, download_url: str) -> Tuple[Optional[bytes], str]:
        if not self._refresh_client_token():
            return None, "Not connected to Auphonic."
        try:
            return self._client.download_output(download_url), ""
        except AuphonicError as exc:
            return None, str(exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_payload(req: ProductionRequest) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"title": req.title}
    if req.input_url:
        payload["input_file"] = req.input_url
    elif req.external_service_uuid and req.external_service_path:
        payload["service"] = req.external_service_uuid
        payload["input_file"] = req.external_service_path
    if req.preset_uuid and not req.preset_uuid.startswith("builtin-"):
        payload["preset"] = req.preset_uuid
    if req.metadata:
        payload["metadata"] = req.metadata
    if req.output_files:
        payload["output_files"] = req.output_files
    if req.algorithms:
        payload["algorithms"] = req.algorithms
    if req.speech_recognition:
        payload["speech_recognition"] = req.speech_recognition
    if req.chapters:
        payload["chapters"] = req.chapters
    if req.multi_input_files:
        payload["multi_input_files"] = req.multi_input_files
    if req.output_basename:
        payload["output_basename"] = req.output_basename
    if req.review_before_publishing:
        payload["review_before_publishing"] = True
    if req.webhook:
        payload["webhook"] = req.webhook
    payload["action"] = req.action
    return payload


def _map_status(status_string: str) -> str:
    s = status_string.lower()
    if "done" in s:
        return JobStatus.DONE
    if "error" in s or "fail" in s:
        return JobStatus.ERROR
    if "review" in s:
        return JobStatus.NEEDS_REVIEW
    return JobStatus.PROCESSING


def _noop(*args, **kwargs):
    pass


def _now() -> str:
    import datetime
    return datetime.datetime.utcnow().isoformat()
