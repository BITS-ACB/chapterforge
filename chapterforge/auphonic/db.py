"""SQLite persistence for Auphonic jobs, outputs, and schema cache.

All tables live in %APPDATA%\\ChapterForge\\auphonic.db.
Schema is created on first use; migrations add columns safely.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

from ..settings import config_dir

_DB_FILE = "auphonic.db"

_CREATE_JOBS = """
CREATE TABLE IF NOT EXISTS auphonic_jobs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    auphonic_uuid           TEXT NOT NULL DEFAULT '',
    title                   TEXT NOT NULL DEFAULT '',
    mode                    TEXT NOT NULL DEFAULT 'json',
    is_multitrack           INTEGER NOT NULL DEFAULT 0,
    status                  TEXT NOT NULL DEFAULT 'draft',
    app_status              TEXT NOT NULL DEFAULT 'draft',
    estimated_credits_hours REAL NOT NULL DEFAULT 0,
    used_credits_hours      REAL NOT NULL DEFAULT 0,
    preset_uuid             TEXT NOT NULL DEFAULT '',
    preset_name             TEXT NOT NULL DEFAULT '',
    request_json            TEXT NOT NULL DEFAULT '{}',
    response_json           TEXT NOT NULL DEFAULT '{}',
    error_message           TEXT NOT NULL DEFAULT '',
    warning_message         TEXT NOT NULL DEFAULT '',
    review_before_publishing INTEGER NOT NULL DEFAULT 0,
    source_asset_json       TEXT NOT NULL DEFAULT '{}',
    created_at              TEXT NOT NULL DEFAULT '',
    started_at              TEXT NOT NULL DEFAULT '',
    completed_at            TEXT NOT NULL DEFAULT '',
    updated_at              TEXT NOT NULL DEFAULT ''
)
"""

_CREATE_OUTPUTS = """
CREATE TABLE IF NOT EXISTS auphonic_outputs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id              INTEGER NOT NULL REFERENCES auphonic_jobs(id),
    format              TEXT NOT NULL DEFAULT '',
    ending              TEXT NOT NULL DEFAULT '',
    filename            TEXT NOT NULL DEFAULT '',
    bitrate             TEXT NOT NULL DEFAULT '',
    size_bytes          INTEGER NOT NULL DEFAULT 0,
    download_url        TEXT NOT NULL DEFAULT '',
    local_storage_uri   TEXT NOT NULL DEFAULT '',
    output_type         TEXT NOT NULL DEFAULT 'audio',
    is_allowed          INTEGER NOT NULL DEFAULT 1
)
"""

_CREATE_SCHEMA_CACHE = """
CREATE TABLE IF NOT EXISTS auphonic_schema_cache (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    schema_type TEXT NOT NULL UNIQUE,
    schema_json TEXT NOT NULL DEFAULT '{}',
    fetched_at  REAL NOT NULL DEFAULT 0,
    expires_at  REAL NOT NULL DEFAULT 0
)
"""

_CREATE_CREDIT_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS auphonic_credit_snapshots (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    credits_hours               REAL NOT NULL DEFAULT 0,
    onetime_credits_hours       REAL NOT NULL DEFAULT 0,
    recurring_credits_hours     REAL NOT NULL DEFAULT 0,
    recharge_date               TEXT NOT NULL DEFAULT '',
    recharge_recurring_hours    REAL NOT NULL DEFAULT 0,
    raw_json                    TEXT NOT NULL DEFAULT '{}',
    created_at                  REAL NOT NULL DEFAULT 0
)
"""


def _db_path() -> str:
    return os.path.join(config_dir(), _DB_FILE)


def _connect() -> sqlite3.Connection:
    os.makedirs(config_dir(), exist_ok=True)
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        _CREATE_JOBS + ";" + _CREATE_OUTPUTS + ";" +
        _CREATE_SCHEMA_CACHE + ";" + _CREATE_CREDIT_SNAPSHOTS
    )
    conn.commit()
    return conn


# Use a module-level connection (single-process desktop app)
_conn: Optional[sqlite3.Connection] = None


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _connect()
    return _conn


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def insert_job(title: str, mode: str = "json", is_multitrack: bool = False,
               preset_uuid: str = "", preset_name: str = "",
               request_payload: Optional[Dict] = None,
               estimated_credits_hours: float = 0.0,
               review_before_publishing: bool = False) -> int:
    now = _now()
    c = conn()
    cur = c.execute(
        """INSERT INTO auphonic_jobs
           (title, mode, is_multitrack, preset_uuid, preset_name,
            request_json, estimated_credits_hours, review_before_publishing,
            created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (title, mode, int(is_multitrack), preset_uuid, preset_name,
         json.dumps(request_payload or {}), estimated_credits_hours,
         int(review_before_publishing), now, now),
    )
    c.commit()
    return cur.lastrowid


def update_job(job_id: int, **kwargs) -> None:
    allowed = {
        "auphonic_uuid", "status", "app_status", "used_credits_hours",
        "error_message", "warning_message", "response_json",
        "started_at", "completed_at",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    fields["updated_at"] = _now()
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [job_id]
    c = conn()
    c.execute(f"UPDATE auphonic_jobs SET {sets} WHERE id=?", vals)
    c.commit()


def get_job(job_id: int) -> Optional[sqlite3.Row]:
    return conn().execute(
        "SELECT * FROM auphonic_jobs WHERE id=?", (job_id,)
    ).fetchone()


def get_job_by_uuid(auphonic_uuid: str) -> Optional[sqlite3.Row]:
    return conn().execute(
        "SELECT * FROM auphonic_jobs WHERE auphonic_uuid=?", (auphonic_uuid,)
    ).fetchone()


def list_jobs(limit: int = 100) -> List[sqlite3.Row]:
    return conn().execute(
        "SELECT * FROM auphonic_jobs ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

def insert_output(job_id: int, format: str, ending: str, filename: str,
                  bitrate: str, size_bytes: int, download_url: str,
                  output_type: str, is_allowed: bool = True) -> int:
    c = conn()
    cur = c.execute(
        """INSERT INTO auphonic_outputs
           (job_id, format, ending, filename, bitrate, size_bytes,
            download_url, output_type, is_allowed)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (job_id, format, ending, filename, bitrate, size_bytes,
         download_url, output_type, int(is_allowed)),
    )
    c.commit()
    return cur.lastrowid


def list_outputs(job_id: int) -> List[sqlite3.Row]:
    return conn().execute(
        "SELECT * FROM auphonic_outputs WHERE job_id=? AND is_allowed=1",
        (job_id,),
    ).fetchall()


# ---------------------------------------------------------------------------
# Schema cache
# ---------------------------------------------------------------------------

SCHEMA_TTL_SECONDS = 24 * 3600  # refresh daily


def get_cached_schema(schema_type: str) -> Optional[Any]:
    row = conn().execute(
        "SELECT schema_json, expires_at FROM auphonic_schema_cache WHERE schema_type=?",
        (schema_type,),
    ).fetchone()
    if row and time.time() < row["expires_at"]:
        try:
            return json.loads(row["schema_json"])
        except Exception:
            pass
    return None


def set_cached_schema(schema_type: str, data: Any) -> None:
    now = time.time()
    c = conn()
    c.execute(
        """INSERT INTO auphonic_schema_cache (schema_type, schema_json, fetched_at, expires_at)
           VALUES (?,?,?,?)
           ON CONFLICT(schema_type) DO UPDATE SET
               schema_json=excluded.schema_json,
               fetched_at=excluded.fetched_at,
               expires_at=excluded.expires_at""",
        (schema_type, json.dumps(data), now, now + SCHEMA_TTL_SECONDS),
    )
    c.commit()


# ---------------------------------------------------------------------------
# Credit snapshots
# ---------------------------------------------------------------------------

def record_credit_snapshot(credits: float, onetime: float, recurring: float,
                             recharge_date: str, recharge_recurring: float,
                             raw: Dict) -> None:
    c = conn()
    c.execute(
        """INSERT INTO auphonic_credit_snapshots
           (credits_hours, onetime_credits_hours, recurring_credits_hours,
            recharge_date, recharge_recurring_hours, raw_json, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (credits, onetime, recurring, recharge_date, recharge_recurring,
         json.dumps(raw), time.time()),
    )
    c.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    import datetime
    return datetime.datetime.utcnow().isoformat()
