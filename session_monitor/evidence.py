"""
evidence.py

Shared evidence schema for everything the monitor persists. Every event
written through here carries the provenance fields the spec requires:
timestamp, session_id, source, source_identifier (path or API name),
evidence_class, and parser_version.

Primary JSONL evidence is append-only. Derived views and vault mirrors may add
structure, but they must never be allowed to make the primary evidence write
fail or rewrite an observed fact.
"""

from __future__ import annotations

import json
import os
import threading
from collections import deque
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

try:
    import vault_bridge
except Exception:  # pragma: no cover - primary evidence must outlive vault issues.
    vault_bridge = None

EVIDENCE_CLASSES = ("observed", "derived", "inferred", "manual", "unavailable")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EvidenceEvent:
    session_id: str
    category: str
    event_type: str
    source: str
    source_identifier: str
    evidence_class: str
    parser_version: str
    data: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=now_iso)
    confidence: Optional[str] = None

    def __post_init__(self):
        if self.evidence_class not in EVIDENCE_CLASSES:
            raise ValueError(
                f"evidence_class must be one of {EVIDENCE_CLASSES}, got {self.evidence_class!r}"
            )

    def to_dict(self) -> dict:
        return asdict(self)


class EvidenceLog:
    """Append-only JSONL evidence stream.

    One JSONL file is maintained per session plus a combined stream for
    cross-session views. Reads are streaming so long-lived installations do
    not have to load the complete evidence history into memory. Source-record
    hashes are cached per session after their first scan so duplicate checks do
    not become O(history) for every newly ingested record.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.events_dir = data_dir / "events"
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.combined_path = self.data_dir / "all_events.jsonl"
        self._lock = threading.RLock()
        self._hash_cache: dict[str, set[str]] = {}
        self._fsync = os.environ.get("CODE_WEAVER_EVIDENCE_FSYNC", "0") == "1"
        self.last_vault_error: Optional[str] = None

    @staticmethod
    def _iter_jsonl(path: Path) -> Iterator[dict]:
        """Yield valid JSONL records and tolerate a truncated final write.

        An interrupted process can leave a partial final line. A damaged line
        must not make the remaining historical evidence unreadable.
        """
        if not path.exists():
            return
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(record, dict):
                        yield record
        except OSError:
            return

    def _write_line(self, path: Path, line: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            if self._fsync:
                os.fsync(handle.fileno())

    def append(self, event: EvidenceEvent) -> None:
        event_dict = event.to_dict()
        line = json.dumps(event_dict, separators=(",", ":"), default=str)
        session_path = self.events_dir / f"{event.session_id}.jsonl"

        with self._lock:
            self._write_line(session_path, line)
            self._write_line(self.combined_path, line)

            normalized = event_dict.get("data", {}).get("normalized", {})
            source_record_hash = normalized.get("source_record_hash")
            if source_record_hash and event.session_id in self._hash_cache:
                self._hash_cache[event.session_id].add(str(source_record_hash))

        if vault_bridge is not None:
            try:
                vault_bridge.record_event(event_dict)
                self.last_vault_error = None
            except Exception as exc:  # pragma: no cover - mirror cannot break evidence.
                self.last_vault_error = f"{type(exc).__name__}: {exc}"

    def read_session(self, session_id: str) -> list[dict]:
        path = self.events_dir / f"{session_id}.jsonl"
        return list(self._iter_jsonl(path))

    def has_record_hash(self, session_id: str, source_record_hash: str) -> bool:
        return source_record_hash in self.source_record_hashes(session_id)

    def source_record_hashes(self, session_id: str) -> set[str]:
        with self._lock:
            cached = self._hash_cache.get(session_id)
            if cached is None:
                cached = set()
                path = self.events_dir / f"{session_id}.jsonl"
                for record in self._iter_jsonl(path):
                    normalized = record.get("data", {}).get("normalized", {})
                    source_record_hash = normalized.get("source_record_hash")
                    if source_record_hash:
                        cached.add(str(source_record_hash))
                self._hash_cache[session_id] = cached
            return set(cached)

    def tail_all(self, limit: int = 200) -> list[dict]:
        if limit <= 0:
            return []
        records: deque[dict] = deque(maxlen=limit)
        for record in self._iter_jsonl(self.combined_path):
            records.append(record)
        out = list(records)
        out.reverse()
        return out

    def latest_by(self, category: str, event_type: Optional[str] = None) -> Optional[dict]:
        """Most recent event matching category and optional event type."""
        best = None
        for record in self.tail_all(limit=2000):
            if record.get("category") != category:
                continue
            if event_type is not None and record.get("event_type") != event_type:
                continue
            if best is None or record.get("timestamp", "") > best.get("timestamp", ""):
                best = record
        return best
