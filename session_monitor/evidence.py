"""
evidence.py

Shared evidence schema for everything the monitor persists. Every event
written through here carries the provenance fields the spec requires:
timestamp, session_id, source, source_identifier (path or API name),
evidence_class (observed | inferred | manual), and parser_version.

Nothing else in the monitor package should write events without going
through EvidenceEvent / append_event — that's what keeps "we watched it
happen" separate from "we're guessing."
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

EVIDENCE_CLASSES = ("observed", "inferred", "manual")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EvidenceEvent:
    session_id: str
    category: str          # e.g. "codex", "git", "vscode", "session"
    event_type: str        # e.g. "quota_update", "task_complete", "reload"
    source: str             # e.g. "codex_stats_log", "codex_rollout", "git"
    source_identifier: str  # file path or API name the data came from
    evidence_class: str     # observed | inferred | manual
    parser_version: str
    data: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=now_iso)
    confidence: Optional[str] = None  # optional free-text note on certainty

    def __post_init__(self):
        if self.evidence_class not in EVIDENCE_CLASSES:
            raise ValueError(
                f"evidence_class must be one of {EVIDENCE_CLASSES}, got {self.evidence_class!r}"
            )

    def to_dict(self) -> dict:
        return asdict(self)


class EvidenceLog:
    """Append-only JSONL evidence stream, one file per session, plus a
    combined rolling file for cross-session queries (reload/failure
    timelines, source-health checks) without opening every session file."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.events_dir = data_dir / "events"
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.combined_path = self.data_dir / "all_events.jsonl"

    def append(self, event: EvidenceEvent) -> None:
        line = json.dumps(event.to_dict())
        session_path = self.events_dir / f"{event.session_id}.jsonl"
        with open(session_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        with open(self.combined_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def read_session(self, session_id: str) -> list[dict]:
        path = self.events_dir / f"{session_id}.jsonl"
        if not path.exists():
            return []
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def has_record_hash(self, session_id: str, source_record_hash: str) -> bool:
        return source_record_hash in self.source_record_hashes(session_id)

    def source_record_hashes(self, session_id: str) -> set[str]:
        hashes = set()
        for record in self.read_session(session_id):
            data = record.get("data", {})
            normalized = data.get("normalized", {})
            source_record_hash = normalized.get("source_record_hash")
            if source_record_hash:
                hashes.add(source_record_hash)
        return hashes

    def tail_all(self, limit: int = 200) -> list[dict]:
        if not self.combined_path.exists():
            return []
        lines = self.combined_path.read_text(encoding="utf-8").splitlines()
        out = [json.loads(l) for l in lines[-limit:] if l.strip()]
        out.reverse()
        return out

    def latest_by(self, category: str, event_type: Optional[str] = None) -> Optional[dict]:
        """Most recent event matching category (and optionally event_type)
        across all sessions — used for 'current quota' style lookups."""
        best = None
        for record in self.tail_all(limit=2000):
            if record.get("category") != category:
                continue
            if event_type is not None and record.get("event_type") != event_type:
                continue
            if best is None or record["timestamp"] > best["timestamp"]:
                best = record
        return best
