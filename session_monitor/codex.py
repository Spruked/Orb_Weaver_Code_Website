"""
codex.py

Codex telemetry ingestion: quota (Codex Stats.log) and turn/task lifecycle
(rollout JSONL). All paths are discovered dynamically via glob — nothing
here hardcodes a specific VS Code session timestamp or rollout filename,
since those change every launch.

PARSER_VERSION is bumped whenever the extraction logic changes, so every
stored event can be traced back to the parser revision that produced it.

Known-real field names (confirmed from an actual machine read):
    primaryUsedPercent, secondaryUsedPercent, window_minutes, resets_at,
    duration_ms, error (e.g. "usage_limit_exceeded"), thread/turn ids,
    token counts.

Unconfirmed: the exact JSON nesting/record shape those fields live in.
Both parsers below extract by key-presence across whatever structure is
found (top-level dict, nested dict, or free text with `key: value` pairs)
rather than assuming one fixed shape, and every match keeps the raw
source line as evidence. If parsing comes back empty or wrong once run
against real files, send a sample and this gets tightened, not guessed at.
"""

from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from evidence import EvidenceEvent, EvidenceLog, now_iso

PARSER_VERSION = "codex-parser-0.5"

VSCODE_LOGS_ROOT = Path.home() / ".vscode-server" / "data" / "logs"
CODEX_SESSIONS_ROOT = Path.home() / ".codex" / "sessions"

QUOTA_KEYS = {
    "primaryUsedPercent", "secondaryUsedPercent", "primary_used_percent",
    "secondary_used_percent",
}
WINDOW_KEYS = {"window_minutes", "primary.window_minutes", "secondary.window_minutes"}


# ---------------------------------------------------------------------------
# Dynamic path discovery
# ---------------------------------------------------------------------------

def find_latest_vscode_session_dir() -> Optional[Path]:
    """~/.vscode-server/data/logs/<timestamp>/ — most recent by dir name
    (VS Code names these with a sortable timestamp) and falls back to
    mtime if names don't sort cleanly."""
    if not VSCODE_LOGS_ROOT.exists():
        return None
    candidates = [p for p in VSCODE_LOGS_ROOT.iterdir() if p.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: (p.name, p.stat().st_mtime))


def find_codex_stats_logs(session_dir: Optional[Path] = None) -> list[Path]:
    """Locate '*Codex Stats.log' under exthost*/output_logging_*/ for a
    given (or the latest) VS Code session dir. Returns newest-first."""
    root = session_dir or find_latest_vscode_session_dir()
    if root is None:
        return []
    hits = list(root.glob("exthost*/output_logging_*/*Codex Stats.log"))
    hits += list(root.glob("exthost*/*Codex Stats.log"))  # tolerate layout variance
    hits.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return hits


def find_codex_extension_logs(session_dir: Optional[Path] = None) -> list[Path]:
    """Locate exthost*/openai.chatgpt/Codex.log for reload/IPC evidence."""
    root = session_dir or find_latest_vscode_session_dir()
    if root is None:
        return []
    hits = list(root.glob("exthost*/openai.chatgpt/Codex.log"))
    hits.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return hits


def find_rollout_files(days_back: int = 7) -> list[Path]:
    """~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl — newest-first, bounded
    to recent days so this stays cheap on long-lived machines."""
    if not CODEX_SESSIONS_ROOT.exists():
        return []
    hits = list(CODEX_SESSIONS_ROOT.glob("*/*/*/rollout-*.jsonl"))
    hits.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return hits


# ---------------------------------------------------------------------------
# Quota parsing (Codex Stats.log)
# ---------------------------------------------------------------------------

_KV_LINE_RE = re.compile(r'"?([A-Za-z_][A-Za-z0-9_.]*)"?\s*[:=]\s*"?([-\w.:TZ+]+)"?')


def _extract_kv_pairs(text: str) -> dict:
    """Best-effort key:value / key=value extraction from a log line that
    may or may not be strict JSON. Tries JSON first, falls back to regex."""
    text = text.strip()
    if not text:
        return {}

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return _flatten(parsed)
    except json.JSONDecodeError:
        pass

    json_start = text.find("{")
    json_end = text.rfind("}")
    if 0 <= json_start < json_end:
        try:
            parsed = json.loads(text[json_start:json_end + 1])
            if isinstance(parsed, dict):
                return _flatten(parsed)
        except json.JSONDecodeError:
            pass

    return {m.group(1): m.group(2) for m in _KV_LINE_RE.finditer(text)}


def _flatten(d: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, prefix=f"{key}."))
        else:
            out[key] = v
    return out


def _pick_flat(fields: dict, *names: str):
    for name in names:
        for key, value in fields.items():
            if key == name or key.split(".")[-1] == name:
                return value
    return None


def _token_usage(fields: dict, prefix: str) -> dict:
    usage = {}
    for name in (
        "input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "cached_input_tokens",
        "cache_write_input_tokens",
        "total_tokens",
    ):
        usage[name] = fields.get(f"{prefix}.{name}")
    return usage


def _record_hash(path: Path, record: dict) -> str:
    payload = {
        "source_file": str(path),
        "record": record,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _semantic_record_key(flat: dict, line_number: int) -> str:
    thread_id = _pick_flat(flat, "thread_id", "threadId")
    turn_id = _pick_flat(flat, "turn_id", "turnId")
    event_type = _pick_flat(flat, "type")
    item_id = _pick_flat(flat, "item_id", "itemId", "id")
    parts = [thread_id, turn_id, event_type, item_id, line_number]
    return ":".join(str(part) for part in parts if part is not None)


def _iso_from_epoch(value, milliseconds: bool = False) -> Optional[str]:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if milliseconds:
        numeric = numeric / 1000
    return datetime.fromtimestamp(numeric, tz=timezone.utc).isoformat()


def _record_timestamp(flat: dict) -> Optional[str]:
    timestamp = _pick_flat(flat, "timestamp")
    if isinstance(timestamp, str):
        return timestamp
    if timestamp is not None:
        return _iso_from_epoch(timestamp)

    started_at_ms = _pick_flat(flat, "started_at_ms", "startedAtMs")
    if started_at_ms is not None:
        return _iso_from_epoch(started_at_ms, milliseconds=True)

    started_at = _pick_flat(flat, "started_at", "startedAt")
    return _iso_from_epoch(started_at)


def _at_or_after(timestamp: Optional[str], started_after: Optional[str]) -> bool:
    if not started_after:
        return True
    if not timestamp:
        return False
    left = _parse_iso(timestamp)
    right = _parse_iso(started_after)
    if left is None or right is None:
        return timestamp >= started_after
    return left >= right


def _at_or_before(timestamp: Optional[str], ended_before: Optional[str]) -> bool:
    if not ended_before:
        return True
    if not timestamp:
        return False
    left = _parse_iso(timestamp)
    right = _parse_iso(ended_before)
    if left is None or right is None:
        return timestamp <= ended_before
    return left <= right


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_quota_from_stats_log(path: Path) -> Optional[dict]:
    """Reads a Codex Stats.log and returns the most recent quota snapshot
    found in it, or None if no quota-shaped line is present. Keeps the
    raw matched line as `raw_line` for evidence."""
    if not path.exists():
        return None

    best = None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None

    for line in lines:
        kv = _extract_kv_pairs(line)
        if not kv:
            continue
        has_quota = any(k in kv or k.split(".")[-1] in QUOTA_KEYS for k in kv)
        if not has_quota:
            # also check case-insensitive / nested key names
            has_quota = any(
                any(qk.lower() in k.lower() for qk in QUOTA_KEYS) for k in kv
            )
        if has_quota:
            best = {"raw_line": line, "fields": kv}

    return best


def read_current_quota(evidence_log: EvidenceLog, session_id: str) -> Optional[dict]:
    """Finds the newest Codex Stats.log, parses it, writes an evidence
    event if a quota snapshot was found, and returns a normalized dict for
    the API. Returns None (never a guess) if nothing was found."""
    logs = find_codex_stats_logs()
    if not logs:
        return None

    latest_log = logs[0]
    snapshot = parse_quota_from_stats_log(latest_log)
    if snapshot is None:
        return None

    fields = snapshot["fields"]

    normalized = {
        "primary_used_percent": _pick_flat(fields, "primaryUsedPercent", "primary_used_percent"),
        "secondary_used_percent": _pick_flat(fields, "secondaryUsedPercent", "secondary_used_percent"),
        "primary_window_minutes": _pick_flat(fields, "window_minutes"),
        "resets_at": _pick_flat(fields, "resets_at", "resetsAt"),
        "source_file": str(latest_log),
        "observed_at": now_iso(),
    }

    event = EvidenceEvent(
        session_id=session_id,
        category="codex",
        event_type="quota_update",
        source="codex_stats_log",
        source_identifier=str(latest_log),
        evidence_class="observed",
        parser_version=PARSER_VERSION,
        data={"normalized": normalized, "raw": snapshot},
    )
    evidence_log.append(event)
    return normalized


# ---------------------------------------------------------------------------
# Rollout JSONL parsing (turn/task lifecycle)
# ---------------------------------------------------------------------------

TASK_RECORD_HINT_KEYS = {"duration_ms", "task_complete", "error", "thread_id", "turn_id"}
TOKEN_RECORD_HINT_KEYS = {"last_token_usage", "total_token_usage"}


def iter_rollout_records(path: Path) -> Iterator[dict]:
    for _, _, record in iter_rollout_records_with_position(path):
        yield record


def iter_rollout_records_with_position(path: Path, start_offset: int = 0) -> Iterator[tuple[int, int, dict]]:
    if not path.exists():
        return
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            if start_offset:
                f.seek(start_offset)
            while True:
                line = f.readline()
                if not line:
                    break
                offset = f.tell()
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    flat = _flatten(record) if isinstance(record, dict) else {}
                    line_number = _pick_flat(flat, "ordinal")
                    yield int(line_number) if line_number is not None else 0, offset, record
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def _cursor_path(evidence_log: EvidenceLog) -> Path:
    return evidence_log.data_dir / "rollout_cursors.json"


def _read_cursors(evidence_log: EvidenceLog) -> dict:
    path = _cursor_path(evidence_log)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_cursors(evidence_log: EvidenceLog, cursors: dict) -> None:
    path = _cursor_path(evidence_log)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cursors, indent=2, sort_keys=True), encoding="utf-8")


def read_recent_rollout_events(
    evidence_log: EvidenceLog,
    session_id: str,
    max_files: int = 3,
    max_records: int = 200,
    started_after: Optional[str] = None,
    ended_before: Optional[str] = None,
) -> list[dict]:
    """Parses the most recent rollout JSONL file(s), writes an evidence
    event per task-lifecycle-shaped record it finds, and returns the
    normalized list for the API."""
    files = find_rollout_files()[:max_files]
    results = []
    known_hashes = evidence_log.source_record_hashes(session_id)
    cursors = _read_cursors(evidence_log)

    for path in files:
        count = 0
        cursor_key = str(path)
        cursor = cursors.get(cursor_key, {})
        start_offset = int(cursor.get("offset", 0) or 0)
        latest_offset = start_offset
        latest_line_number = int(cursor.get("line_number", 0) or 0)

        for line_number, offset, record in iter_rollout_records_with_position(path, start_offset=start_offset):
            latest_offset = offset
            latest_line_number = line_number or latest_line_number
            if count >= max_records:
                break
            flat = _flatten(record) if isinstance(record, dict) else {}
            has_hint = any(
                any(hint.lower() in k.lower() for hint in TASK_RECORD_HINT_KEYS | TOKEN_RECORD_HINT_KEYS)
                for k in flat
            )
            if not has_hint:
                continue
            event_timestamp = _record_timestamp(flat)
            if not _at_or_after(event_timestamp, started_after):
                continue
            if not _at_or_before(event_timestamp, ended_before):
                continue
            count += 1
            source_record_hash = _record_hash(path, record)
            if source_record_hash in known_hashes:
                continue
            known_hashes.add(source_record_hash)

            normalized = {
                "duration_ms": _pick_flat(flat, "duration_ms", "durationMs"),
                "error": _pick_flat(flat, "error"),
                "thread_id": _pick_flat(flat, "thread_id", "threadId"),
                "turn_id": _pick_flat(flat, "turn_id", "turnId"),
                "source_event_type": _pick_flat(flat, "type"),
                "started_at": _pick_flat(flat, "started_at", "startedAt"),
                "started_at_ms": _pick_flat(flat, "started_at_ms", "startedAtMs"),
                "model_context_window": _pick_flat(flat, "model_context_window", "modelContextWindow"),
                "collaboration_mode_kind": _pick_flat(flat, "collaboration_mode_kind", "collaborationModeKind"),
                "last_token_usage": _token_usage(flat, "payload.info.last_token_usage"),
                "total_token_usage": _token_usage(flat, "payload.info.total_token_usage"),
                "source_file": str(path),
                "source_record_hash": source_record_hash,
                "source_line_number": line_number,
                "semantic_record_key": _semantic_record_key(flat, line_number),
            }
            results.append(normalized)

            event = EvidenceEvent(
                session_id=session_id,
                category="codex",
                event_type="rollout_record",
                source="codex_rollout",
                source_identifier=str(path),
                evidence_class="observed",
                parser_version=PARSER_VERSION,
                data={"normalized": normalized, "raw": record},
                timestamp=event_timestamp or now_iso(),
            )
            evidence_log.append(event)

        cursors[cursor_key] = {
            "offset": latest_offset,
            "line_number": latest_line_number,
            "updated_at": now_iso(),
        }

    _write_cursors(evidence_log, cursors)

    return results
