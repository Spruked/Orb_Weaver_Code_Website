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

STORAGE_VERSION = "storage-0.2"


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

    def to_dict(self) -> dict:
        return asdict(self)


class Storage:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.db_path = data_dir / "sessions.db"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.evidence = EvidenceLog(data_dir)
        self._init_db()

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
            conn.commit()

    def create_session(self, workspace_path: str, source: str) -> SessionRecord:
        git = git_snapshot(Path(workspace_path))
        record = SessionRecord(
            id=str(uuid.uuid4()),
            workspace_path=workspace_path,
            source=source,
            started_at=now_iso(),
            repo_root=git["repo_root"],
            branch=git["branch"],
            head=git["head"],
            remote=git["remote"],
            remote_host=git["remote_host"],
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO sessions
                    (id, workspace_path, source, started_at, ended_at,
                     repo_root, branch, head, remote, remote_host)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        return record

    def end_session(self, session_id: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            existing = conn.execute(
                "SELECT ended_at FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if existing is None or existing["ended_at"] is not None:
                return
            ended = now_iso()
            conn.execute(
                "UPDATE sessions SET ended_at = ? WHERE id = ?", (ended, session_id)
            )
            conn.commit()

        self.evidence.append(
            EvidenceEvent(
                session_id=session_id,
                category="session",
                event_type="session_end",
                source="storage",
                source_identifier=session_id,
                evidence_class="observed",
                parser_version=STORAGE_VERSION,
                data={},
            )
        )

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
