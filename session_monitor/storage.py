"""
storage.py

SQLite session index plus the append-only EvidenceLog.

A session is an explicit monitor-session boundary. The future VS Code extension
can supply the authoritative editor session identity; until then the Electron
control plane starts/ends monitor sessions explicitly.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional

from evidence import EvidenceEvent, EvidenceLog, now_iso
from git_monitor import snapshot as git_snapshot
import vault_bridge

STORAGE_VERSION = "storage-0.2"
RUNTIME_SOURCES = {
    "code_weaver_runtime",
    "electron-widget-startup",
    "vscode_fresh_window",
}


@dataclass
class SessionRecord:
    id: str
    workspace_path: str
    source: str
    started_at: str
    ended_at: Optional[str] = None
    repo_root: Optional[str] = None
    branch: Optional[str] = None
    head: Optional[str] = None
    remote: Optional[str] = None
    remote_host: Optional[str] = None
    status: str = "active"
    end_reason: Optional[str] = None
    last_observed_at: Optional[str] = None
    recovered_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class Storage:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.db_path = data_dir / "sessions.db"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.evidence = EvidenceLog(data_dir)
        self._init_db()
        vault_bridge.ensure_vault_runtime()
        self.close_stale_sessions("monitor_startup")

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    workspace_path TEXT,
                    source TEXT,
                    started_at TEXT,
                    ended_at TEXT,
                    repo_root TEXT,
                    branch TEXT,
                    head TEXT,
                    remote TEXT,
                    remote_host TEXT
                )
                """
            )
            self._ensure_column(conn, "sessions", "status", "TEXT DEFAULT 'active'")
            self._ensure_column(conn, "sessions", "end_reason", "TEXT")
            self._ensure_column(conn, "sessions", "last_observed_at", "TEXT")
            self._ensure_column(conn, "sessions", "recovered_at", "TEXT")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vscode_windows (
                    id TEXT PRIMARY KEY,
                    runtime_session_id TEXT,
                    workspace_path TEXT,
                    source TEXT,
                    started_at TEXT,
                    ended_at TEXT,
                    status TEXT,
                    close_reason TEXT,
                    repo_root TEXT,
                    branch TEXT,
                    head TEXT,
                    remote TEXT,
                    remote_host TEXT,
                    process_id TEXT,
                    window_identifier TEXT,
                    focus_state TEXT,
                    codex_thread_id TEXT,
                    codex_turn_id TEXT,
                    last_observed_at TEXT
                )
                """
            )
            conn.commit()

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {
            row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def create_session(self, workspace_path: str, source: str) -> SessionRecord:
        git = git_snapshot(Path(workspace_path))
        started = now_iso()
        record = SessionRecord(
            id=str(uuid.uuid4()),
            workspace_path=workspace_path,
            source=source,
            started_at=started,
            repo_root=git["repo_root"],
            branch=git["branch"],
            head=git["head"],
            remote=git["remote"],
            remote_host=git["remote_host"],
            last_observed_at=started,
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO sessions
                    (id, workspace_path, source, started_at, ended_at,
                     repo_root, branch, head, remote, remote_host,
                     status, end_reason, last_observed_at, recovered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.workspace_path,
                    record.source,
                    record.started_at,
                    record.ended_at,
                    record.repo_root,
                    record.branch,
                    record.head,
                    record.remote,
                    record.remote_host,
                    record.status,
                    record.end_reason,
                    record.last_observed_at,
                    record.recovered_at,
                ),
            )
            conn.commit()

        self.evidence.append(
            EvidenceEvent(
                session_id=record.id,
                category="session",
                event_type="session_start",
                source="storage",
                source_identifier=workspace_path,
                evidence_class="observed",
                parser_version=STORAGE_VERSION,
                data={"source": source, "git": git},
            )
        )
        vault_bridge.record_session_metadata(record.to_dict())
        return record

    def latest_session_event_timestamp(self, session_id: str) -> Optional[str]:
        events = self.evidence.read_session(session_id)
        timestamps = [event.get("timestamp") for event in events if event.get("timestamp")]
        return max(timestamps) if timestamps else None

    def close_stale_sessions(self, reason: str, runtime_only: bool = False) -> int:
        recovered = now_iso()
        closed = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if runtime_only:
                placeholders = ",".join("?" for _ in RUNTIME_SOURCES)
                rows = conn.execute(
                    f"""
                    SELECT * FROM sessions
                    WHERE ended_at IS NULL AND source IN ({placeholders})
                    ORDER BY started_at
                    """,
                    tuple(RUNTIME_SOURCES),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sessions WHERE ended_at IS NULL ORDER BY started_at"
                ).fetchall()
            for row in rows:
                last_observed = self.latest_session_event_timestamp(row["id"]) or row["last_observed_at"]
                conn.execute(
                    """
                    UPDATE sessions
                    SET ended_at = ?, status = ?, end_reason = ?, recovered_at = ?,
                        last_observed_at = ?
                    WHERE id = ?
                    """,
                    (recovered, "unclean", reason, recovered, last_observed, row["id"]),
                )
                conn.execute(
                    """
                    UPDATE vscode_windows
                    SET ended_at = ?, status = ?, close_reason = ?, last_observed_at = ?
                    WHERE runtime_session_id = ? AND ended_at IS NULL
                    """,
                    (recovered, "unclean", reason, last_observed, row["id"]),
                )
                closed.append(dict(row))
            conn.commit()

        for session in closed:
            last_observed = self.latest_session_event_timestamp(session["id"]) or session.get("last_observed_at")
            session["ended_at"] = recovered
            session["status"] = "unclean"
            session["end_reason"] = reason
            session["recovered_at"] = recovered
            session["last_observed_at"] = last_observed
            self.evidence.append(
                EvidenceEvent(
                    session_id=session["id"],
                    category="session",
                    event_type="session_recovered_unclean",
                    source="storage",
                    source_identifier=session["id"],
                    evidence_class="observed",
                    parser_version=STORAGE_VERSION,
                    data={
                        "reason": reason,
                        "recovery_class": "crash_recovery",
                        "last_observed_at": last_observed,
                        "ended_at_is_recovery_detection_time": True,
                    },
                )
            )
            vault_bridge.record_session_metadata(session)
        return len(closed)

    def end_session(self, session_id: str, reason: str = "normal_shutdown") -> None:
        ended = now_iso()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            existing = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if existing is None or existing["ended_at"] is not None:
                return
            conn.execute(
                """
                UPDATE sessions
                SET ended_at = ?, status = ?, end_reason = ?, last_observed_at = ?
                WHERE id = ?
                """,
                (ended, "closed", reason, ended, session_id),
            )
            conn.execute(
                """
                UPDATE vscode_windows
                SET ended_at = ?, status = ?, close_reason = ?, last_observed_at = ?
                WHERE runtime_session_id = ? AND ended_at IS NULL
                """,
                (ended, "closed", "parent_session_closed", ended, session_id),
            )
            conn.commit()
            session = dict(existing)
            session["ended_at"] = ended
            session["status"] = "closed"
            session["end_reason"] = reason
            session["last_observed_at"] = ended

        self.evidence.append(
            EvidenceEvent(
                session_id=session_id,
                category="session",
                event_type="session_end",
                source="storage",
                source_identifier=session_id,
                evidence_class="observed",
                parser_version=STORAGE_VERSION,
                data={"reason": reason},
            )
        )
        vault_bridge.record_session_metadata(session)

    def list_sessions(self, limit: int = 50) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    def get_session(self, session_id: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if row is None:
                return None
            record = dict(row)
            record["events"] = self.evidence.read_session(session_id)
            return record

    def active_session(self) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM sessions
                WHERE ended_at IS NULL AND status = 'active'
                ORDER BY started_at DESC LIMIT 1
                """
            ).fetchone()
            return dict(row) if row is not None else None

    def active_runtime_session(self) -> Optional[dict]:
        placeholders = ",".join("?" for _ in RUNTIME_SOURCES)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"""
                SELECT * FROM sessions
                WHERE ended_at IS NULL AND status = 'active'
                  AND source IN ({placeholders})
                ORDER BY started_at DESC LIMIT 1
                """,
                tuple(RUNTIME_SOURCES),
            ).fetchone()
            return dict(row) if row is not None else None

    def ensure_runtime_session(self, workspace_path: str) -> dict:
        existing = self.active_runtime_session()
        if existing is not None:
            return existing
        return self.create_session(workspace_path, "code_weaver_runtime").to_dict()

    def heartbeat(self, session_id: str, source: str) -> Optional[dict]:
        session = self.get_session(session_id)
        if session is None or session.get("ended_at") is not None:
            return None
        observed_at = now_iso()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE sessions SET last_observed_at = ? WHERE id = ?",
                (observed_at, session_id),
            )
            conn.commit()
        self.evidence.append(
            EvidenceEvent(
                session_id=session_id,
                category="runtime",
                event_type="runtime_heartbeat",
                source=source,
                source_identifier=session_id,
                evidence_class="observed",
                parser_version=STORAGE_VERSION,
                data={"runtime_session_id": session_id},
                timestamp=observed_at,
            )
        )
        return {"id": session_id, "heartbeat_at": observed_at}

    def create_vscode_window(
        self,
        runtime_session_id: str,
        workspace_path: str,
        source: str,
        process_id: Optional[str] = None,
        window_identifier: Optional[str] = None,
        focus_state: str = "unknown",
    ) -> Optional[dict]:
        session = self.get_session(runtime_session_id)
        if session is None or session.get("ended_at") is not None:
            return None
        git = git_snapshot(Path(workspace_path))
        started = now_iso()
        window = {
            "id": str(uuid.uuid4()),
            "runtime_session_id": runtime_session_id,
            "workspace_path": workspace_path,
            "source": source,
            "started_at": started,
            "ended_at": None,
            "status": "active",
            "close_reason": None,
            "repo_root": git["repo_root"],
            "branch": git["branch"],
            "head": git["head"],
            "remote": git["remote"],
            "remote_host": git["remote_host"],
            "process_id": process_id,
            "window_identifier": window_identifier,
            "focus_state": focus_state,
            "codex_thread_id": None,
            "codex_turn_id": None,
            "last_observed_at": started,
        }
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO vscode_windows
                    (id, runtime_session_id, workspace_path, source, started_at,
                     ended_at, status, close_reason, repo_root, branch, head,
                     remote, remote_host, process_id, window_identifier,
                     focus_state, codex_thread_id, codex_turn_id, last_observed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    window["id"], window["runtime_session_id"], window["workspace_path"],
                    window["source"], window["started_at"], window["ended_at"],
                    window["status"], window["close_reason"], window["repo_root"],
                    window["branch"], window["head"], window["remote"],
                    window["remote_host"], window["process_id"], window["window_identifier"],
                    window["focus_state"], window["codex_thread_id"], window["codex_turn_id"],
                    window["last_observed_at"],
                ),
            )
            conn.execute(
                "UPDATE sessions SET last_observed_at = ? WHERE id = ?",
                (started, runtime_session_id),
            )
            conn.commit()
        self.evidence.append(
            EvidenceEvent(
                session_id=runtime_session_id,
                category="vscode_window",
                event_type="window_start",
                source=source,
                source_identifier=window["id"],
                evidence_class="observed",
                parser_version=STORAGE_VERSION,
                data={
                    "child_window_id": window["id"],
                    "workspace_path": workspace_path,
                    "git": git,
                    "process_id": process_id,
                    "window_identifier": window_identifier,
                    "focus_state": focus_state,
                    "codex_association": {
                        "thread_id": None,
                        "turn_id": None,
                        "status": "prepared_not_observed",
                    },
                },
                timestamp=started,
            )
        )
        return window

    def close_vscode_window(self, window_id: str, reason: str = "window_closed") -> Optional[dict]:
        ended = now_iso()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            existing = conn.execute(
                "SELECT * FROM vscode_windows WHERE id = ?", (window_id,)
            ).fetchone()
            if existing is None:
                return None
            window = dict(existing)
            if window["ended_at"] is not None:
                return window
            conn.execute(
                """
                UPDATE vscode_windows
                SET ended_at = ?, status = ?, close_reason = ?, last_observed_at = ?
                WHERE id = ?
                """,
                (ended, "closed", reason, ended, window_id),
            )
            conn.execute(
                "UPDATE sessions SET last_observed_at = ? WHERE id = ?",
                (ended, window["runtime_session_id"]),
            )
            conn.commit()
        window["ended_at"] = ended
        window["status"] = "closed"
        window["close_reason"] = reason
        window["last_observed_at"] = ended
        self.evidence.append(
            EvidenceEvent(
                session_id=window["runtime_session_id"],
                category="vscode_window",
                event_type="window_end",
                source=window["source"],
                source_identifier=window_id,
                evidence_class="observed",
                parser_version=STORAGE_VERSION,
                data={"child_window_id": window_id, "reason": reason},
                timestamp=ended,
            )
        )
        return window

    def list_vscode_windows(self, runtime_session_id: str, active_only: bool = False) -> list[dict]:
        query = "SELECT * FROM vscode_windows WHERE runtime_session_id = ?"
        params: list[str] = [runtime_session_id]
        if active_only:
            query += " AND ended_at IS NULL AND status = 'active'"
        query += " ORDER BY started_at"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def today_sessions(self) -> list[dict]:
        """Sessions that started during the machine's current local calendar day.

        Session timestamps stay UTC in storage; only the reporting boundary is
        converted from local time to UTC.
        """
        local_now = datetime.now().astimezone()
        local_start = datetime.combine(local_now.date(), time.min, tzinfo=local_now.tzinfo)
        local_end = local_start + timedelta(days=1)
        utc_start = local_start.astimezone(timezone.utc).isoformat()
        utc_end = local_end.astimezone(timezone.utc).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM sessions
                WHERE started_at >= ? AND started_at < ?
                ORDER BY started_at DESC
                """,
                (utc_start, utc_end),
            ).fetchall()
            return [dict(row) for row in rows]
