"""
vscode_logs.py

VS Code writes a new timestamped directory under
~/.vscode-server/data/logs/ each time a server-side session starts
(including reloads). We use the *appearance of a new directory* as
observed evidence of a session start/reload — this is inferred from log
layout, not from a documented stable API, so it's recorded with
evidence_class="inferred" rather than "observed". The VS Code extension
(phase 3) will supply the authoritative observed session-id/reload events
via `vscode.env.sessionId`; this module is the WSL-side fallback/cross-
check that works even before the extension exists.

IPC reset detection scans Codex.log for lines matching known reset/
reconnect phrasing. Since we haven't confirmed Codex.log's exact log
format yet, the patterns below are intentionally broad and each match
keeps the raw line for verification.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from evidence import EvidenceEvent, EvidenceLog

PARSER_VERSION = "vscode-logs-parser-0.1"

VSCODE_LOGS_ROOT = Path.home() / ".vscode-server" / "data" / "logs"
STATE_FILE_NAME = "known_session_dirs.json"
CODEX_LOG_CURSOR_FILE_NAME = "codex_log_cursors.json"

IPC_RESET_PATTERNS = [
    re.compile(r"ipc.*reset", re.IGNORECASE),
    re.compile(r"connection reset", re.IGNORECASE),
    re.compile(r"disconnect", re.IGNORECASE),
    re.compile(r"reconnect", re.IGNORECASE),
    re.compile(r"app-server (spawned|started|exited)", re.IGNORECASE),
]


def list_session_dirs() -> list[Path]:
    if not VSCODE_LOGS_ROOT.exists():
        return []
    return sorted([p for p in VSCODE_LOGS_ROOT.iterdir() if p.is_dir()], key=lambda p: p.name)


def detect_new_session_dirs(state_dir: Path) -> list[Path]:
    """Compares the current set of log dirs against a small state file of
    previously-seen dirs. Returns any that are new since the last check."""
    state_path = state_dir / STATE_FILE_NAME
    known = set()
    if state_path.exists():
        try:
            known = set(json.loads(state_path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            known = set()

    current = list_session_dirs()
    current_names = {p.name for p in current}
    new_names = current_names - known

    state_dir.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(sorted(current_names)), encoding="utf-8")

    return [p for p in current if p.name in new_names]


def baseline_session_dirs(state_dir: Path) -> int:
    """Record the current VS Code log directory set without emitting
    evidence. Used at monitor session start so historical dirs do not
    masquerade as reloads in a fresh session."""
    current_names = {p.name for p in list_session_dirs()}
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / STATE_FILE_NAME
    state_path.write_text(json.dumps(sorted(current_names)), encoding="utf-8")
    return len(current_names)


def _cursor_path(state_dir: Path) -> Path:
    return state_dir / CODEX_LOG_CURSOR_FILE_NAME


def _read_cursors(state_dir: Path) -> dict:
    path = _cursor_path(state_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_cursors(state_dir: Path, cursors: dict) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    _cursor_path(state_dir).write_text(json.dumps(cursors, indent=2, sort_keys=True), encoding="utf-8")


def _parse_log_timestamp(line: str) -> Optional[str]:
    match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})", line)
    if not match:
        return None
    try:
        local_tz = datetime.now().astimezone().tzinfo
        parsed = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S.%f")
        return parsed.replace(tzinfo=local_tz).astimezone().isoformat()
    except ValueError:
        return None


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _in_window(timestamp: Optional[str], started_after: Optional[str], ended_before: Optional[str]) -> bool:
    if timestamp is None:
        return False
    parsed = _parse_iso(timestamp)
    start = _parse_iso(started_after) if started_after else None
    end = _parse_iso(ended_before) if ended_before else None
    if parsed is None:
        return False
    if start is not None and parsed < start:
        return False
    if end is not None and parsed > end:
        return False
    return True


def record_new_sessions(evidence_log: EvidenceLog, session_id: str, state_dir: Path) -> list[dict]:
    new_dirs = detect_new_session_dirs(state_dir)
    records = []
    for d in new_dirs:
        data = {"log_dir": str(d), "log_dir_name": d.name}
        event = EvidenceEvent(
            session_id=session_id,
            category="vscode",
            event_type="new_log_session_dir",
            source="vscode_logs",
            source_identifier=str(d),
            evidence_class="inferred",
            parser_version=PARSER_VERSION,
            data=data,
            confidence="inferred from new timestamped log directory, not a documented API event",
        )
        evidence_log.append(event)
        records.append(data)
    return records


def scan_codex_log_for_resets(
    log_path: Path,
    evidence_log: EvidenceLog,
    session_id: str,
    state_dir: Path,
    started_after: Optional[str] = None,
    ended_before: Optional[str] = None,
) -> list[dict]:
    if not log_path.exists():
        return []
    hits = []
    cursors = _read_cursors(state_dir)
    cursor_key = str(log_path)
    start_offset = int(cursors.get(cursor_key, {}).get("offset", 0) or 0)
    latest_offset = start_offset
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            if start_offset:
                f.seek(start_offset)
            lines = []
            while True:
                line = f.readline()
                if not line:
                    break
                latest_offset = f.tell()
                lines.append(line.rstrip("\n"))
    except OSError:
        return []

    for line in lines:
        for pattern in IPC_RESET_PATTERNS:
            if pattern.search(line):
                event_timestamp = _parse_log_timestamp(line)
                if not _in_window(event_timestamp, started_after, ended_before):
                    break
                data = {"line": line, "matched_pattern": pattern.pattern}
                event = EvidenceEvent(
                    session_id=session_id,
                    category="codex",
                    event_type="ipc_event",
                    source="codex_extension_log",
                    source_identifier=str(log_path),
                    evidence_class="observed",
                    parser_version=PARSER_VERSION,
                    data=data,
                    timestamp=event_timestamp,
                )
                evidence_log.append(event)
                hits.append(data)
                break
    cursors[cursor_key] = {"offset": latest_offset}
    _write_cursors(state_dir, cursors)
    return hits
