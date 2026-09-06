"""Liveness registry for editors, agents, applications, containers, and remotes."""
from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from evidence import EvidenceEvent, now_iso

STALE_AFTER_SECONDS = 120
IDENTITY_RE = re.compile(r"^[A-Za-z0-9._:/@-]{1,256}$")
TYPES = {"desktop_editor", "cli_agent", "application", "container", "remote_workspace", "unknown"}


def ensure_schema(storage):
    with sqlite3.connect(storage.db_path) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS environments (
          environment_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
          environment_type TEXT NOT NULL, label TEXT, editor_name TEXT,
          editor_process_name TEXT, window_handle TEXT, process_id TEXT,
          window_title TEXT, workspace_path TEXT, workspace_name TEXT,
          project TEXT, started_at_utc TEXT NOT NULL, last_seen_utc TEXT NOT NULL,
          state TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}'
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS environments_session_state ON environments(session_id, state)")
        conn.commit()


def _text(value, field, required=False):
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise ValueError(f"{field} must be a non-empty string of at most 512 characters")
    if field == "environment_id" and not IDENTITY_RE.fullmatch(value):
        raise ValueError("environment_id contains unsupported characters")
    return value.strip()


def _stale_cutoff():
    return datetime.now(timezone.utc) - timedelta(seconds=STALE_AFTER_SECONDS)


def reconcile_stale(storage, session_id):
    cutoff = _stale_cutoff().isoformat()
    timestamp = now_iso()
    with sqlite3.connect(storage.db_path) as conn:
        rows = conn.execute("SELECT environment_id FROM environments WHERE session_id = ? AND state = 'active' AND last_seen_utc < ?", (session_id, cutoff)).fetchall()
        conn.execute("UPDATE environments SET state = 'stale' WHERE session_id = ? AND state = 'active' AND last_seen_utc < ?", (session_id, cutoff))
        conn.commit()
    for (environment_id,) in rows:
        storage.evidence.append(EvidenceEvent(
            session_id=session_id, category="environment", event_type="environment_stale",
            source="environment_registry", source_identifier=environment_id,
            evidence_class="observed", parser_version="environment-registry-1",
            data={"environment_id": environment_id, "state": "stale"}, timestamp=timestamp))
    return len(rows)


def register(storage, session_id, payload):
    ensure_schema(storage)
    environment_id = _text(payload.get("environment_id"), "environment_id", True)
    environment_type = _text(payload.get("environment_type", "unknown"), "environment_type", True)
    if environment_type not in TYPES:
        raise ValueError("unsupported environment_type")
    timestamp = now_iso()
    fields = {
        "label": _text(payload.get("label"), "label"),
        "editor_name": _text(payload.get("editor_name"), "editor_name"),
        "editor_process_name": _text(payload.get("editor_process_name"), "editor_process_name"),
        "window_handle": _text(payload.get("window_handle"), "window_handle"),
        "process_id": _text(str(payload["process_id"]) if isinstance(payload.get("process_id"), int) else payload.get("process_id"), "process_id"),
        "window_title": _text(payload.get("window_title"), "window_title"),
        "workspace_path": _text(payload.get("workspace_path"), "workspace_path"),
        "workspace_name": _text(payload.get("workspace_name"), "workspace_name"),
        "project": _text(payload.get("project"), "project"),
    }
    with sqlite3.connect(storage.db_path) as conn:
        old = conn.execute("SELECT * FROM environments WHERE environment_id = ?", (environment_id,)).fetchone()
        if old:
            conn.execute("""UPDATE environments SET session_id=?, environment_type=?, label=?, editor_name=?, editor_process_name=?, window_handle=?, process_id=?, window_title=?, workspace_path=?, workspace_name=?, project=?, last_seen_utc=?, state='active' WHERE environment_id=?""", (session_id, environment_type, *fields.values(), timestamp, environment_id))
            created = False
        else:
            conn.execute("""INSERT INTO environments (environment_id,session_id,environment_type,label,editor_name,editor_process_name,window_handle,process_id,window_title,workspace_path,workspace_name,project,started_at_utc,last_seen_utc,state) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (environment_id, session_id, environment_type, *fields.values(), timestamp, timestamp, "active"))
            created = True
        conn.commit()
    reconcile_stale(storage, session_id)
    storage.evidence.append(EvidenceEvent(session_id=session_id, category="environment", event_type="environment_registered" if created else "environment_heartbeat", source="environment_registry", source_identifier=environment_id, evidence_class="observed", parser_version="environment-registry-1", data={"environment_id": environment_id, "environment_type": environment_type, "state": "active", "workspace_path": fields["workspace_path"], "window_handle": fields["window_handle"], "process_id": fields["process_id"]}, timestamp=timestamp))
    return get(storage, environment_id)


def get(storage, environment_id):
    with sqlite3.connect(storage.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM environments WHERE environment_id = ?", (environment_id,)).fetchone()
        return dict(row) if row else None


def list_environments(storage, session_id, include_stale=True):
    reconcile_stale(storage, session_id)
    query = "SELECT * FROM environments WHERE session_id = ?"
    params = [session_id]
    if not include_stale:
        query += " AND state = 'active'"
    query += " ORDER BY state = 'active' DESC, last_seen_utc DESC"
    with sqlite3.connect(storage.db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(query, params).fetchall()]
