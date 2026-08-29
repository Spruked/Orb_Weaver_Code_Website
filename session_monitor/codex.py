"""
codex.py

Read-only discovery plus explicit evidence ingestion for Codex telemetry.

The parser uses the real structures observed on this machine while remaining
defensive about missing/extra fields. Raw prompt/response/tool payloads are not
copied into the monitor ledger. Persisted evidence keeps normalized telemetry,
source location, parser version, and a SHA-256 source-record identity.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional

from evidence import EvidenceEvent, EvidenceLog, now_iso

PARSER_VERSION = "codex-parser-0.6"

VSCODE_LOGS_ROOT = Path.home() / ".vscode-server" / "data" / "logs"
CODEX_SESSIONS_ROOT = Path.home() / ".codex" / "sessions"

QUOTA_KEYS = {
    "primaryUsedPercent",
    "secondaryUsedPercent",
    "primary_used_percent",
    "secondary_used_percent",
}
TASK_RECORD_HINT_KEYS = {
    "duration_ms",
    "task_complete",
    "error",
    "thread_id",
    "turn_id",
    "item_completed",
}
TOKEN_RECORD_HINT_KEYS = {"last_token_usage", "total_token_usage", "token_count"}

_STATS_TS_RE = re.compile(r"^\[([^\]]+)\]")
_KV_LINE_RE = re.compile(r'"?([A-Za-z_][A-Za-z0-9_.]*)"?\s*[:=]\s*"?([-\w.:TZ+]+)"?')


# ---------------------------------------------------------------------------
# Dynamic path discovery
# ---------------------------------------------------------------------------


def find_latest_vscode_session_dir() -> Optional[Path]:
    if not VSCODE_LOGS_ROOT.exists():
        return None
    candidates = [p for p in VSCODE_LOGS_ROOT.iterdir() if p.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: (p.name, p.stat().st_mtime))


def find_codex_stats_logs(session_dir: Optional[Path] = None) -> list[Path]:
    root = session_dir or find_latest_vscode_session_dir()
    if root is None:
        return []
    hits = list(root.glob("exthost*/output_logging_*/*Codex Stats.log"))
    hits += list(root.glob("exthost*/*Codex Stats.log"))
    # De-duplicate paths while preserving newest-first ordering.
    unique = {str(p): p for p in hits}
    return sorted(unique.values(), key=lambda p: p.stat().st_mtime, reverse=True)


def find_codex_extension_logs(session_dir: Optional[Path] = None) -> list[Path]:
    root = session_dir or find_latest_vscode_session_dir()
    if root is None:
        return []
    hits = list(root.glob("exthost*/openai.chatgpt/Codex.log"))
    return sorted(hits, key=lambda p: p.stat().st_mtime, reverse=True)


def find_rollout_files(days_back: int = 7) -> list[Path]:
    if not CODEX_SESSIONS_ROOT.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(days_back, 1))
    hits = []
    for path in CODEX_SESSIONS_ROOT.glob("*/*/*/rollout-*.jsonl"):
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if modified >= cutoff:
            hits.append(path)
    return sorted(hits, key=lambda p: p.stat().st_mtime, reverse=True)


# ---------------------------------------------------------------------------
# Shared parsing helpers
# ---------------------------------------------------------------------------


def _flatten(d: dict, prefix: str = "") -> dict:
    out = {}
    for key, value in d.items():
        flat_key = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_flatten(value, prefix=f"{flat_key}."))
        else:
            out[flat_key] = value
    return out


def _pick_flat(fields: dict, *names: str):
    for name in names:
        if name in fields:
            return fields[name]
    for name in names:
        for key, value in fields.items():
            if key.split(".")[-1] == name:
                return value
    return None


def _extract_kv_pairs(text: str) -> dict:
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
            parsed = json.loads(text[json_start : json_end + 1])
            if isinstance(parsed, dict):
                return _flatten(parsed)
        except json.JSONDecodeError:
            pass

    return {match.group(1): match.group(2) for match in _KV_LINE_RE.finditer(text)}


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_from_epoch(value, milliseconds: bool = False) -> Optional[str]:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if milliseconds:
        numeric /= 1000
    return datetime.fromtimestamp(numeric, tz=timezone.utc).isoformat()


def _record_timestamp(record: dict, flat: Optional[dict] = None) -> Optional[str]:
    timestamp = record.get("timestamp") if isinstance(record, dict) else None
    if isinstance(timestamp, str):
        return timestamp
    flat = flat or (_flatten(record) if isinstance(record, dict) else {})
    timestamp = _pick_flat(flat, "timestamp")
    if isinstance(timestamp, str):
        return timestamp
    if timestamp is not None:
        return _iso_from_epoch(timestamp)
    started_at_ms = _pick_flat(flat, "started_at_ms", "startedAtMs")
    if started_at_ms is not None:
        return _iso_from_epoch(started_at_ms, milliseconds=True)
    return _iso_from_epoch(_pick_flat(flat, "started_at", "startedAt"))


def _at_or_after(timestamp: Optional[str], boundary: Optional[str]) -> bool:
    if not boundary:
        return True
    if not timestamp:
        return False
    left = _parse_iso(timestamp)
    right = _parse_iso(boundary)
    if left is None or right is None:
        return timestamp >= boundary
    return left >= right


def _at_or_before(timestamp: Optional[str], boundary: Optional[str]) -> bool:
    if not boundary:
        return True
    if not timestamp:
        return False
    left = _parse_iso(timestamp)
    right = _parse_iso(boundary)
    if left is None or right is None:
        return timestamp <= boundary
    return left <= right


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _record_hash(path: Path, line_number: int, record: dict) -> str:
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    return _sha256_text(f"{path}\0{line_number}\0{encoded}")


def _token_usage(info: dict, name: str) -> dict:
    source = info.get(name) if isinstance(info, dict) else None
    source = source if isinstance(source, dict) else {}
    return {
        "input_tokens": source.get("input_tokens"),
        "cached_input_tokens": source.get("cached_input_tokens"),
        "cache_write_input_tokens": source.get("cache_write_input_tokens"),
        "output_tokens": source.get("output_tokens"),
        "reasoning_output_tokens": source.get("reasoning_output_tokens"),
        "total_tokens": source.get("total_tokens"),
    }


def _limit_window(value) -> Optional[dict]:
    if not isinstance(value, dict):
        return None
    return {
        "used_percent": value.get("used_percent"),
        "window_minutes": value.get("window_minutes"),
        "resets_at": value.get("resets_at"),
    }


# ---------------------------------------------------------------------------
# Codex Stats.log quota parsing
# ---------------------------------------------------------------------------


def parse_quota_from_stats_log(path: Path) -> Optional[dict]:
    """Return the newest quota-shaped Stats.log line without persisting it."""
    if not path.exists():
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None

    best = None
    for line_number, line in enumerate(lines, start=1):
        fields = _extract_kv_pairs(line)
        if not fields:
            continue
        has_quota = any(
            any(quota_key.lower() in key.lower() for quota_key in QUOTA_KEYS)
            for key in fields
        )
        if not has_quota:
            continue
        timestamp_match = _STATS_TS_RE.match(line)
        best = {
            "raw_line": line,
            "fields": fields,
            "line_number": line_number,
            "observed_at": timestamp_match.group(1) if timestamp_match else None,
            "source_record_hash": _sha256_text(f"{path}\0{line_number}\0{line}"),
        }
    return best


def read_current_quota(evidence_log: EvidenceLog, session_id: str) -> Optional[dict]:
    """Observe the latest real Stats.log quota line and persist it once.

    Re-reading the same provider line returns the normalized snapshot but does
    not append duplicate evidence.
    """
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
        "primary_window_minutes": None,
        "secondary_window_minutes": None,
        "primary_resets_at": None,
        "secondary_resets_at": None,
        "source_file": str(latest_log),
        "source_line_number": snapshot["line_number"],
        "source_record_hash": snapshot["source_record_hash"],
        "observed_at": snapshot["observed_at"] or now_iso(),
    }

    known_hashes = evidence_log.source_record_hashes(session_id)
    if snapshot["source_record_hash"] not in known_hashes:
        evidence_log.append(
            EvidenceEvent(
                session_id=session_id,
                category="codex",
                event_type="quota_update",
                source="codex_stats_log",
                source_identifier=str(latest_log),
                evidence_class="observed",
                parser_version=PARSER_VERSION,
                data={"normalized": normalized},
                timestamp=normalized["observed_at"],
            )
        )
    return normalized


# ---------------------------------------------------------------------------
# Rollout JSONL parsing
# ---------------------------------------------------------------------------


def iter_rollout_records(path: Path) -> Iterator[dict]:
    for _, _, record in iter_rollout_records_with_position(path):
        yield record


def iter_rollout_records_with_position(
    path: Path, start_offset: int = 0
) -> Iterator[tuple[int, int, dict]]:
    if not path.exists():
        return
    try:
        file_size = path.stat().st_size
        if start_offset < 0 or start_offset > file_size:
            start_offset = 0
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            if start_offset:
                handle.seek(start_offset)
            physical_line = 0
            while True:
                line = handle.readline()
                if not line:
                    break
                physical_line += 1
                offset = handle.tell()
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                ordinal = record.get("ordinal") if isinstance(record, dict) else None
                try:
                    line_number = int(ordinal) if ordinal is not None else physical_line
                except (TypeError, ValueError):
                    line_number = physical_line
                yield line_number, offset, record
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


def _semantic_record_key(record: dict, line_number: int) -> str:
    payload = record.get("payload") if isinstance(record, dict) else None
    payload = payload if isinstance(payload, dict) else {}
    item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
    parts = [
        payload.get("thread_id"),
        payload.get("turn_id"),
        payload.get("type") or record.get("type"),
        item.get("id") or payload.get("id"),
        record.get("ordinal"),
        line_number,
    ]
    return ":".join(str(part) for part in parts if part is not None)


def _normalize_rollout(path: Path, line_number: int, record: dict) -> dict:
    payload = record.get("payload") if isinstance(record, dict) else None
    payload = payload if isinstance(payload, dict) else {}
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
    error = payload.get("error")
    error = error if isinstance(error, dict) else {}
    rate_limits = payload.get("rate_limits")
    rate_limits = rate_limits if isinstance(rate_limits, dict) else {}

    source_event_type = payload.get("type") or record.get("type")
    source_record_hash = _record_hash(path, line_number, record)

    return {
        "source_event_type": source_event_type,
        "root_record_type": record.get("type"),
        "thread_id": payload.get("thread_id"),
        "turn_id": payload.get("turn_id"),
        "item_type": item.get("type"),
        "item_id": item.get("id") or payload.get("id"),
        "duration_ms": payload.get("duration_ms"),
        "time_to_first_token_ms": payload.get("time_to_first_token_ms"),
        "started_at": payload.get("started_at"),
        "completed_at": payload.get("completed_at"),
        "started_at_ms": payload.get("started_at_ms"),
        "completed_at_ms": payload.get("completed_at_ms"),
        "error": error.get("codex_error_info") or error.get("message"),
        "error_code": error.get("codex_error_info"),
        "error_message": error.get("message"),
        "model_context_window": info.get("model_context_window"),
        "last_token_usage": _token_usage(info, "last_token_usage"),
        "total_token_usage": _token_usage(info, "total_token_usage"),
        "rate_limits": {
            "limit_id": rate_limits.get("limit_id"),
            "plan_type": rate_limits.get("plan_type"),
            "rate_limit_reached_type": rate_limits.get("rate_limit_reached_type"),
            "primary": _limit_window(rate_limits.get("primary")),
            "secondary": _limit_window(rate_limits.get("secondary")),
        },
        "source_file": str(path),
        "source_record_hash": source_record_hash,
        "source_line_number": line_number,
        "semantic_record_key": _semantic_record_key(record, line_number),
    }


def _is_relevant_rollout(record: dict, normalized: dict) -> bool:
    event_type = str(normalized.get("source_event_type") or "").lower()
    if event_type in {"token_count", "task_complete", "item_completed"}:
        return True
    flat = _flatten(record) if isinstance(record, dict) else {}
    return any(
        any(hint.lower() in key.lower() for hint in TASK_RECORD_HINT_KEYS | TOKEN_RECORD_HINT_KEYS)
        for key in flat
    )


def read_recent_rollout_events(
    evidence_log: EvidenceLog,
    session_id: str,
    max_files: int = 3,
    max_records: int = 200,
    started_after: Optional[str] = None,
    ended_before: Optional[str] = None,
) -> list[dict]:
    """Ingest new rollout records inside the monitor-session time bounds."""
    files = find_rollout_files()[:max_files]
    results = []
    known_hashes = evidence_log.source_record_hashes(session_id)
    cursors = _read_cursors(evidence_log)

    for path in files:
        cursor_key = str(path)
        cursor = cursors.get(cursor_key, {})
        start_offset = int(cursor.get("offset", 0) or 0)
        latest_offset = start_offset
        latest_line_number = int(cursor.get("line_number", 0) or 0)
        appended = 0

        for line_number, offset, record in iter_rollout_records_with_position(
            path, start_offset=start_offset
        ):
            latest_offset = offset
            latest_line_number = line_number or latest_line_number
            if appended >= max_records:
                break

            normalized = _normalize_rollout(path, line_number, record)
            if not _is_relevant_rollout(record, normalized):
                continue

            event_timestamp = _record_timestamp(record)
            if not _at_or_after(event_timestamp, started_after):
                continue
            if not _at_or_before(event_timestamp, ended_before):
                continue

            source_record_hash = normalized["source_record_hash"]
            if source_record_hash in known_hashes:
                continue
            known_hashes.add(source_record_hash)
            appended += 1
            results.append(normalized)

            evidence_log.append(
                EvidenceEvent(
                    session_id=session_id,
                    category="codex",
                    event_type="rollout_record",
                    source="codex_rollout",
                    source_identifier=str(path),
                    evidence_class="observed",
                    parser_version=PARSER_VERSION,
                    data={"normalized": normalized},
                    timestamp=event_timestamp or now_iso(),
                )
            )

        cursors[cursor_key] = {
            "offset": latest_offset,
            "line_number": latest_line_number,
            "updated_at": now_iso(),
        }

    _write_cursors(evidence_log, cursors)
    return results
