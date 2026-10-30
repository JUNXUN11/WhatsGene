"""SQLite job store (PRD §8: worker + SQLite, no separate queue).

Fields/tables follow docs/ARCHITECTURE.md "Data model". Phone/WhatsApp
keys are stored server-side only and never rendered on results pages.
Results links use unguessable full-UUID job IDs.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config

_lock = threading.Lock()

JOB_STATUSES = ("queued", "running", "done", "failed", "cancelled")
WHATSAPP_STATUSES = ("not_sent", "sent", "failed")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    whatsapp_user_id TEXT,
    question TEXT NOT NULL DEFAULT '',
    intent TEXT NOT NULL DEFAULT '{}',
    outcome TEXT,
    searches_used INTEGER NOT NULL DEFAULT 0,
    deadline_at TEXT,
    input_kind TEXT NOT NULL DEFAULT '',
    raw_input TEXT NOT NULL DEFAULT '',
    sequence TEXT NOT NULL DEFAULT '',
    accession TEXT,
    query_length INTEGER NOT NULL DEFAULT 0,
    detected_type TEXT NOT NULL DEFAULT '',
    program TEXT,
    database TEXT,
    organism_filter TEXT,
    parameters TEXT NOT NULL DEFAULT '{}',
    summary TEXT,
    error TEXT,
    whatsapp_status TEXT NOT NULL DEFAULT 'not_sent',
    notified_at TEXT,
    hits TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL DEFAULT 'whatsapp',
    workflow_mode TEXT NOT NULL DEFAULT 'auto',
    requested_program TEXT,
    notify_to TEXT
);
CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'primary',
    program TEXT,
    database TEXT,
    parameters TEXT NOT NULL DEFAULT '{}',
    rid TEXT,
    status TEXT NOT NULL DEFAULT 'submitted',
    submitted_at TEXT,
    completed_at TEXT,
    hits TEXT NOT NULL DEFAULT '[]',
    error TEXT
);
CREATE TABLE IF NOT EXISTS step_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    step TEXT NOT NULL,
    observation TEXT NOT NULL DEFAULT '',
    decision TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    is_deviation INTEGER NOT NULL DEFAULT 0,
    deviation_reason TEXT
);
"""

# Columns added after the boilerplate schema; applied to existing DBs.
_JOB_COLUMNS: dict[str, str] = {
    "whatsapp_user_id": "TEXT",
    "intent": "TEXT NOT NULL DEFAULT '{}'",
    "outcome": "TEXT",
    "searches_used": "INTEGER NOT NULL DEFAULT 0",
    "deadline_at": "TEXT",
    "source": "TEXT NOT NULL DEFAULT 'whatsapp'",
    "workflow_mode": "TEXT NOT NULL DEFAULT 'auto'",
    "requested_program": "TEXT",
    "notify_to": "TEXT",
}
_SEARCH_COLUMNS: dict[str, str] = {
    "hits": "TEXT NOT NULL DEFAULT '[]'",
    "error": "TEXT",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    path = Path(config.DATABASE_PATH)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock, _connect() as conn:
        conn.executescript(_SCHEMA)
        existing = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        for col, ddl in _JOB_COLUMNS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {ddl}")
        search_cols = {r[1] for r in conn.execute("PRAGMA table_info(searches)").fetchall()}
        for col, ddl in _SEARCH_COLUMNS.items():
            if col not in search_cols:
                conn.execute(f"ALTER TABLE searches ADD COLUMN {col} {ddl}")


def _row_to_job(row: sqlite3.Row) -> dict[str, Any]:
    job = dict(row)
    for key, default in (("parameters", {}), ("hits", []), ("intent", {})):
        try:
            job[key] = json.loads(job.get(key) or json.dumps(default))
        except (json.JSONDecodeError, TypeError):
            job[key] = default
    return job


def create_job(*, question: str, raw_input: str, input_kind: str = "",
               whatsapp_user_id: str | None = None, source: str = "whatsapp",
               workflow_mode: str = "auto", requested_program: str | None = None,
               notify_to: str | None = None) -> dict[str, Any]:
    job_id = f"WG-{uuid.uuid4().hex.upper()}"
    now = _now()
    with _lock, _connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, created_at, updated_at, status, question,
                              input_kind, raw_input, whatsapp_status, whatsapp_user_id,
                              source, workflow_mode, requested_program, notify_to)
            VALUES (?, ?, ?, 'queued', ?, ?, ?, 'not_sent', ?, ?, ?, ?, ?)
            """,
            (job_id, now, now, question, input_kind, raw_input, whatsapp_user_id,
             source, workflow_mode, requested_program, notify_to),
        )
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(row)


def get_job(job_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row else None


def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_job(r) for r in rows]


def update_job(job_id: str, **fields: Any) -> dict[str, Any] | None:
    if not fields:
        return get_job(job_id)
    for key in ("parameters", "hits", "intent"):
        if key in fields and not isinstance(fields[key], str):
            fields[key] = json.dumps(fields[key])
    fields["updated_at"] = _now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    with _lock, _connect() as conn:
        conn.execute(f"UPDATE jobs SET {cols} WHERE id = ?", (*fields.values(), job_id))
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row else None


# --- agent-loop helpers ---

def add_step(job_id: str, *, step: str, observation: str = "", decision: str = "",
             reason: str = "", is_deviation: bool = False,
             deviation_reason: str | None = None) -> None:
    with _lock, _connect() as conn:
        seq = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM step_log WHERE job_id = ?", (job_id,)
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO step_log (job_id, seq, created_at, step, observation, decision, reason, is_deviation, deviation_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, seq, _now(), step, observation, decision, reason,
             1 if is_deviation else 0, deviation_reason),
        )


def get_step_log(job_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM step_log WHERE job_id = ? ORDER BY seq", (job_id,)
        ).fetchall()
    out = []
    for row in rows:
        entry = dict(row)
        entry["is_deviation"] = bool(entry["is_deviation"])
        out.append(entry)
    return out


def create_search(job_id: str, *, kind: str, program: str | None,
                  database: str | None, parameters: dict, rid: str | None) -> int:
    with _lock, _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO searches (job_id, kind, program, database, parameters, rid, status, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, 'submitted', ?)
            """,
            (job_id, kind, program, database, json.dumps(parameters), rid, _now()),
        )
        return int(cur.lastrowid)


def complete_search(search_id: int, *, hits: list | None = None,
                    status: str = "done", error: str | None = None) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            "UPDATE searches SET hits = ?, status = ?, error = ?, completed_at = ? WHERE id = ?",
            (json.dumps(hits or []), status, error, _now(), search_id),
        )


def get_searches(job_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM searches WHERE job_id = ? ORDER BY id", (job_id,)
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        for key, default in (("parameters", {}), ("hits", [])):
            try:
                item[key] = json.loads(item.get(key) or json.dumps(default))
            except (json.JSONDecodeError, TypeError):
                item[key] = default
        out.append(item)
    return out


def list_queued_jobs(limit: int = 50) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_job(r) for r in rows]


def claim_job(job_id: str) -> bool:
    """Atomically move queued -> running. False if already claimed/done."""
    with _lock, _connect() as conn:
        cur = conn.execute(
            "UPDATE jobs SET status = 'running', updated_at = ? WHERE id = ? AND status = 'queued'",
            (_now(), job_id))
    return cur.rowcount == 1


def list_jobs_for_user(whatsapp_user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE whatsapp_user_id = ? OR notify_to = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (whatsapp_user_id, whatsapp_user_id, limit),
        ).fetchall()
    return [_row_to_job(r) for r in rows]


def running_job_for_user(whatsapp_user_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE whatsapp_user_id = ? AND status IN ('queued','running') "
            "ORDER BY created_at DESC LIMIT 1",
            (whatsapp_user_id,),
        ).fetchone()
    return _row_to_job(row) if row else None


def latest_job_for_user(whatsapp_user_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE whatsapp_user_id = ? ORDER BY created_at DESC LIMIT 1",
            (whatsapp_user_id,),
        ).fetchone()
    return _row_to_job(row) if row else None


def delete_user_history(whatsapp_user_id: str) -> int:
    with _lock, _connect() as conn:
        job_ids = [r[0] for r in conn.execute(
            "SELECT id FROM jobs WHERE whatsapp_user_id = ?", (whatsapp_user_id,)
        ).fetchall()]
        for jid in job_ids:
            conn.execute("DELETE FROM step_log WHERE job_id = ?", (jid,))
            conn.execute("DELETE FROM searches WHERE job_id = ?", (jid,))
        conn.execute("DELETE FROM jobs WHERE whatsapp_user_id = ?", (whatsapp_user_id,))
    return len(job_ids)
