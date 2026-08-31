"""Per-window Code Weaver instance model.

The runtime session is the parent control plane. Each VS Code window is a child
instance. Shared plan-limit evidence remains parent/account-level. Evidence is
attached to a child only when a defensible identity link exists.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import codex
import correlation
import vscode_logs
from evidence import EvidenceEvent, now_iso

INSTANCE_VERSION = "window-instance-0.1"


def _ensure_column(conn: sqlite3.Connection, column: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(vscode_windows)").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE vscode_windows ADD COLUMN {column} {definition}")


def ensure_schema(storage) -> None:
    with sqlite3.connect(storage.db_path) as conn:
        _ensure_column(conn, "instance_label", "TEXT")
        _ensure_column(conn, "log_session_dir", "TEXT")
        _ensure_column(conn, "identity_evidence_class", "TEXT DEFAULT 'observed'")
        _ensure_column(conn, "discovered_at", "TEXT")
        conn.commit()


def _workspace_label(workspace_path: Optional[str], fallback: str = "VS Code") -> str:
    if workspace_path:
        name = Path(workspace_path).name
        if name:
            return name
    return fallback


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_from_mtime(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def get_instance(storage, window_id: str) -> Optional[dict]:
    ensure_schema(storage)
    with sqlite3.connect(storage.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM vscode_windows WHERE id = ?", (window_id,)).fetchone()
        return dict(row) if row is not None else None


def list_instances(storage, runtime_session_id: str, active_only: bool = False) -> list[dict]:
    ensure_schema(storage)
    query = "SELECT * FROM vscode_windows WHERE runtime_session_id = ?"
    params: list[object] = [runtime_session_id]
    if active_only:
        query += " AND ended_at IS NULL AND status = 'active'"
    query += " ORDER BY started_at"
    with sqlite3.connect(storage.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def decorate_registered_instance(storage, window: Optional[dict]) -> Optional[dict]:
    if not window:
        return None
    ensure_schema(storage)
    label = _workspace_label(window.get("workspace_path"), "VS Code")
    observed_at = now_iso()
    with sqlite3.connect(storage.db_path) as conn:
        conn.execute(
            """
            UPDATE vscode_windows
            SET instance_label = COALESCE(instance_label, ?),
                identity_evidence_class = COALESCE(identity_evidence_class, 'observed'),
                discovered_at = COALESCE(discovered_at, ?)
            WHERE id = ?
            """,
            (label, observed_at, window["id"]),
        )
        conn.commit()
    return get_instance(storage, window["id"])


def bind_log_session(
    storage,
    window_id: str,
    log_session_dir: str,
    evidence_class: str = "derived",
) -> Optional[dict]:
    ensure_schema(storage)
    if evidence_class not in {"observed", "derived", "inferred"}:
        evidence_class = "inferred"
    window = get_instance(storage, window_id)
    if window is None:
        return None
    log_path = str(Path(log_session_dir).expanduser().resolve())
    observed_at = now_iso()
    with sqlite3.connect(storage.db_path) as conn:
        conflict = conn.execute(
            "SELECT id FROM vscode_windows WHERE log_session_dir = ? AND id <> ?",
            (log_path, window_id),
        ).fetchone()
        if conflict is not None:
            return None
        conn.execute(
            """
            UPDATE vscode_windows
            SET log_session_dir = ?, identity_evidence_class = ?,
                last_observed_at = ?, discovered_at = COALESCE(discovered_at, ?),
                instance_label = COALESCE(instance_label, ?)
            WHERE id = ?
            """,
            (
                log_path,
                evidence_class,
                observed_at,
                observed_at,
                _workspace_label(window.get("workspace_path"), Path(log_path).name),
                window_id,
            ),
        )
        conn.commit()
    storage.evidence.append(
        EvidenceEvent(
            session_id=window["runtime_session_id"],
            category="vscode_window",
            event_type="window_log_session_bound",
            source="window_instances",
            source_identifier=log_path,
            evidence_class=evidence_class,
            parser_version=INSTANCE_VERSION,
            data={
                "child_window_id": window_id,
                "log_session_dir": log_path,
                "association": evidence_class,
            },
            timestamp=observed_at,
        )
    )
    return get_instance(storage, window_id)


def _latest_log_activity(session_dir: Path) -> Optional[float]:
    mtimes: list[float] = []
    for path in codex.find_codex_extension_logs(session_dir) + codex.find_codex_stats_logs(session_dir):
        try:
            mtimes.append(path.stat().st_mtime)
        except OSError:
            pass
    try:
        mtimes.append(session_dir.stat().st_mtime)
    except OSError:
        pass
    return max(mtimes) if mtimes else None


def _unbound_log_dirs(storage, runtime_session_id: str, max_age_seconds: int) -> list[tuple[Path, float]]:
    now = time.time()
    bound = {
        str(Path(row["log_session_dir"]).resolve())
        for row in list_instances(storage, runtime_session_id)
        if row.get("log_session_dir")
    }
    candidates: list[tuple[Path, float]] = []
    for directory in vscode_logs.list_session_dirs():
        activity = _latest_log_activity(directory)
        if activity is None or now - activity > max_age_seconds:
            continue
        if str(directory.resolve()) in bound:
            continue
        candidates.append((directory, activity))
    return sorted(candidates, key=lambda item: item[1], reverse=True)


def _auto_bind_registered(storage, runtime_session_id: str, max_age_seconds: int = 900) -> int:
    """Derive a log binding only when one unique close-time candidate exists."""
    candidates = _unbound_log_dirs(storage, runtime_session_id, max_age_seconds)
    if not candidates:
        return 0
    windows = [
        row for row in list_instances(storage, runtime_session_id, active_only=True)
        if row.get("source") == "vscode_folder_open" and not row.get("log_session_dir")
    ]
    bound = 0
    used: set[str] = set()
    for window in windows:
        started = _parse_iso(window.get("started_at"))
        if started is None:
            continue
        scored: list[tuple[float, Path]] = []
        for directory, activity in candidates:
            key = str(directory.resolve())
            if key in used:
                continue
            delta = abs(activity - started.timestamp())
            if delta <= 120:
                scored.append((delta, directory))
        scored.sort(key=lambda item: item[0])
        if not scored:
            continue
        if len(scored) > 1 and abs(scored[0][0] - scored[1][0]) < 3:
            continue
        selected = scored[0][1]
        result = bind_log_session(storage, window["id"], str(selected), "derived")
        if result is not None:
            used.add(str(selected.resolve()))
            bound += 1
    return bound


def discover_recent_instances(
    storage,
    runtime_session_id: str,
    max_age_seconds: int = 1800,
    max_instances: int = 8,
) -> list[dict]:
    """Discover active-looking VS Code log sessions as transparent INFERRED children.

    This catches windows that were already open before the tracked launcher was
    installed. They remain INFERRED until a stronger identity binding exists.
    """
    ensure_schema(storage)
    _auto_bind_registered(storage, runtime_session_id)
    session = storage.get_session(runtime_session_id)
    if session is None:
        return []
    existing = list_instances(storage, runtime_session_id)
    known_identifiers = {row.get("window_identifier") for row in existing}
    candidates = _unbound_log_dirs(storage, runtime_session_id, max_age_seconds)
    created: list[dict] = []
    for directory, activity in candidates[:max_instances]:
        identifier = f"vscode-log:{directory.name}"
        if identifier in known_identifiers:
            continue
        started_at = _iso_from_mtime(activity)
        window_id = f"log-{directory.name}"
        with sqlite3.connect(storage.db_path) as conn:
            duplicate = conn.execute("SELECT id FROM vscode_windows WHERE id = ?", (window_id,)).fetchone()
            if duplicate is not None:
                continue
            conn.execute(
                """
                INSERT INTO vscode_windows
                    (id, runtime_session_id, workspace_path, source, started_at,
                     ended_at, status, close_reason, repo_root, branch, head,
                     remote, remote_host, process_id, window_identifier,
                     focus_state, codex_thread_id, codex_turn_id, last_observed_at,
                     instance_label, log_session_dir, identity_evidence_class, discovered_at)
                VALUES (?, ?, ?, ?, ?, NULL, 'active', NULL, NULL, NULL, NULL,
                        NULL, NULL, NULL, ?, 'unknown', NULL, NULL, ?, ?, ?, 'inferred', ?)
                """,
                (
                    window_id,
                    runtime_session_id,
                    None,
                    "vscode_log_discovery",
                    started_at,
                    identifier,
                    started_at,
                    f"Detected {directory.name}",
                    str(directory.resolve()),
                    now_iso(),
                ),
            )
            conn.commit()
        storage.evidence.append(
            EvidenceEvent(
                session_id=runtime_session_id,
                category="vscode_window",
                event_type="window_inferred_from_log_session",
                source="window_instances",
                source_identifier=str(directory),
                evidence_class="inferred",
                parser_version=INSTANCE_VERSION,
                data={
                    "child_window_id": window_id,
                    "log_session_dir": str(directory),
                    "workspace_path": None,
                    "identity_note": "Active-looking VS Code log session; workspace/window identity not yet authoritative",
                },
                timestamp=started_at,
            )
        )
        created.append(get_instance(storage, window_id) or {})
    return created


def _event_belongs_to_instance(event: dict, instance: dict) -> bool:
    data = event.get("data") or {}
    if data.get("child_window_id") == instance.get("id"):
        return True
    log_root = instance.get("log_session_dir")
    source_identifier = str(event.get("source_identifier") or "")
    if log_root:
        try:
            if Path(source_identifier).is_relative_to(Path(log_root)):
                return True
        except (ValueError, OSError):
            if source_identifier.startswith(str(log_root)):
                return True
    if event.get("event_type") == "rollout_record":
        normalized = data.get("normalized") or {}
        thread_id = normalized.get("thread_id")
        if thread_id and thread_id == instance.get("codex_thread_id"):
            return True
    return False


def instance_summary(storage, runtime_session_id: str) -> dict:
    ensure_schema(storage)
    instances = list_instances(storage, runtime_session_id)
    events = storage.evidence.read_session(runtime_session_id)
    claimed_event_ids: set[int] = set()
    summaries = []

    for instance in instances:
        child_events = []
        for index, event in enumerate(events):
            if _event_belongs_to_instance(event, instance):
                child_events.append(event)
                claimed_event_ids.add(index)
        timeline = correlation.build_timeline(child_events, limit=120)
        rollout_events = [event for event in child_events if event.get("event_type") == "rollout_record"]
        threads = sorted({
            (event.get("data") or {}).get("normalized", {}).get("thread_id")
            for event in rollout_events
            if (event.get("data") or {}).get("normalized", {}).get("thread_id")
        })
        turns = [
            (event.get("data") or {}).get("normalized", {}).get("turn_id")
            for event in rollout_events
            if (event.get("data") or {}).get("normalized", {}).get("turn_id")
        ]
        summaries.append({
            **instance,
            "instance_label": instance.get("instance_label") or _workspace_label(instance.get("workspace_path"), "VS Code"),
            "event_count": len(child_events),
            "ipc_event_count": sum(1 for event in child_events if event.get("event_type") == "ipc_event"),
            "reload_signal_count": sum(1 for event in child_events if event.get("event_type") == "new_log_session_dir"),
            "rollout_event_count": len(rollout_events),
            "thread_ids": threads,
            "latest_turn_id": turns[-1] if turns else instance.get("codex_turn_id"),
            "token_usage_summary": timeline.get("token_usage_summary", {}),
            "latest_activity_at": max((event.get("timestamp") or "" for event in child_events), default=instance.get("last_observed_at")),
            "timeline": timeline.get("timeline", [])[-24:],
        })

    unassigned = [
        event for index, event in enumerate(events)
        if index not in claimed_event_ids and event.get("event_type") in {"rollout_record", "ipc_event", "new_log_session_dir"}
    ]
    unassigned_rollout = [event for event in unassigned if event.get("event_type") == "rollout_record"]
    return {
        "runtime_session_id": runtime_session_id,
        "instances": summaries,
        "instance_count": len(summaries),
        "unassigned": {
            "event_count": len(unassigned),
            "rollout_event_count": len(unassigned_rollout),
            "token_count": sum(
                1 for event in unassigned_rollout
                if (event.get("data") or {}).get("normalized", {}).get("source_event_type") == "token_count"
            ),
            "note": "Evidence without a defensible child-window identity remains global/unassigned; Code Weaver does not guess.",
        },
    }
