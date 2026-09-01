"""
server.py

Local HTTP API for the Code Weaver Session Monitor control plane.

Read endpoints are side-effect free. Evidence enters the append-only ledger
only through explicit session/observation/ingestion actions or the monitor
service's own startup lifecycle.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from storage import Storage
from git_monitor import snapshot as git_snapshot
import codex
import correlation
import release_evidence
import vscode_logs
import window_instances
import windows_desktop

DATA_DIR = Path(
    os.environ.get(
        "CODE_WEAVER_RUNTIME_DATA_DIR",
        Path.home() / ".local" / "share" / "code-weaver-runtime",
    )
)
DEFAULT_WORKSPACE_PATH = Path(
    os.environ.get(
        "CODE_WEAVER_WORKSPACE_PATH",
        Path(__file__).resolve().parents[1],
    )
).resolve()

storage = Storage(DATA_DIR)
window_instances.ensure_schema(storage)
windows_desktop.ensure_schema(storage)
window_instances.reconcile_legacy_outer_log_bindings(storage)
app = FastAPI(title="Code Weaver Runtime API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:41000",
        "http://localhost:41000",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

ANCHOR_SOURCES = {"vscode_exthost_discovery", "vscode_log_discovery"}


def _number(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _remaining_from_used(value):
    used = _number(value)
    return 100.0 - used if used is not None else None


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _runtime_is_recent(session: Optional[dict], max_age_seconds: int = 120) -> bool:
    if not session:
        return False
    observed = _parse_iso(session.get("last_observed_at") or session.get("started_at"))
    if observed is None:
        return False
    age = (datetime.now(timezone.utc) - observed).total_seconds()
    return age <= max_age_seconds


def _latest_quota() -> dict:
    latest = storage.evidence.latest_by("codex", "quota_update")
    if latest is None:
        return {"status": "unknown"}
    normalized = latest.get("data", {}).get("normalized", {})
    five_hour_used = _number(normalized.get("primary_used_percent"))
    weekly_used = _number(normalized.get("secondary_used_percent"))
    return {
        "status": "observed",
        **normalized,
        "scope": "shared_plan_limits",
        "five_hour": {
            "used_percent": five_hour_used,
            "remaining_percent_derived": _remaining_from_used(five_hour_used),
            "remaining_evidence_class": "derived",
            "raw_source_field": "primaryUsedPercent",
        },
        "weekly": {
            "used_percent": weekly_used,
            "remaining_percent_derived": _remaining_from_used(weekly_used),
            "remaining_evidence_class": "derived",
            "raw_source_field": "secondaryUsedPercent",
        },
        "observed_via": latest.get("source_identifier"),
        "evidence_timestamp": latest.get("timestamp"),
    }


def _session_or_none(session_id: str):
    return storage.get_session(session_id)


def _anchor_token_count(anchor: dict) -> int:
    token = anchor.get("token_usage_summary") or {}
    return int(token.get("attributed_last_usage_turn_count") or 0) + int(
        token.get("unattributed_last_usage_record_count") or 0
    )


def _control_plane_instances(session_id: str) -> dict:
    """Return actual window tabs separately from unbound exthost evidence.

    ``window_instances.instance_summary`` still calculates evidence against all
    persisted rows for backward compatibility.  Here we enforce the user-facing
    ontology: a Remote WSL exthost is an evidence anchor, not proof of a visible
    VS Code window.
    """
    raw = window_instances.instance_summary(storage, session_id)
    rows = raw.get("instances") or []
    anchors = [row for row in rows if row.get("source") in ANCHOR_SOURCES and not row.get("ended_at")]
    windows = [
        row
        for row in rows
        if row.get("source") not in ANCHOR_SOURCES
        and row.get("ended_at") is None
        and row.get("status") == "active"
    ]
    closed_windows = [
        row
        for row in rows
        if row.get("source") not in ANCHOR_SOURCES
        and (row.get("ended_at") is not None or row.get("status") != "active")
    ]

    unassigned = dict(raw.get("unassigned") or {})
    unassigned["event_count"] = int(unassigned.get("event_count") or 0) + sum(
        int(anchor.get("event_count") or 0) for anchor in anchors
    )
    unassigned["rollout_event_count"] = int(unassigned.get("rollout_event_count") or 0) + sum(
        int(anchor.get("rollout_event_count") or 0) for anchor in anchors
    )
    unassigned["token_count"] = int(unassigned.get("token_count") or 0) + sum(
        _anchor_token_count(anchor) for anchor in anchors
    )
    unassigned["extension_host_anchor_count"] = len(anchors)
    unassigned["extension_host_anchors"] = [
        {
            "id": anchor.get("id"),
            "server_log_dir": anchor.get("server_log_dir"),
            "extension_host": anchor.get("extension_host"),
            "extension_host_dir": anchor.get("log_session_dir"),
            "identity_evidence_class": anchor.get("identity_evidence_class") or "inferred",
            "latest_activity_at": anchor.get("latest_activity_at") or anchor.get("last_observed_at"),
            "event_count": anchor.get("event_count") or 0,
            "rollout_event_count": anchor.get("rollout_event_count") or 0,
            "token_count": _anchor_token_count(anchor),
        }
        for anchor in anchors
    ]
    unassigned["note"] = (
        "Unbound exthostN directories are extension-host evidence anchors, not visible-window identities. "
        "They stay here until Code Weaver can defensibly bind them to an observed VS Code window."
    )

    return {
        **raw,
        "instances": windows,
        "instance_count": len(windows),
        "closed_instances": closed_windows,
        "closed_instance_count": len(closed_windows),
        "extension_host_anchors": unassigned["extension_host_anchors"],
        "extension_host_anchor_count": len(anchors),
        "unassigned": unassigned,
    }


def _bootstrap_runtime() -> dict:
    """Guarantee one parent runtime exists whenever the monitor service starts.

    Storage already marks any abandoned runtime from a previous monitor process
    unclean during Storage initialization. The new process then owns a fresh
    runtime immediately, independent of whether Electron wins or loses a
    desktop-startup race.
    """
    record = storage.ensure_runtime_session(str(DEFAULT_WORKSPACE_PATH))
    vscode_logs.baseline_session_dirs(DATA_DIR)
    codex.read_current_quota(storage.evidence, record["id"])
    return record


# The monitor service owns the parent runtime lifecycle. Electron may attach to
# it, but a widget startup failure must never leave Code Weaver without a parent.
_bootstrap_runtime()


@app.get("/health")
def health():
    active = storage.active_runtime_session()
    window_count = 0
    anchor_count = 0
    if active:
        window_count = len(windows_desktop.visible_window_rows(storage, active["id"], active_only=True))
        anchor_count = len(
            [
                row
                for row in window_instances.list_instances(storage, active["id"], active_only=True)
                if row.get("source") in ANCHOR_SOURCES
            ]
        )
    return {
        "ok": True,
        "service": "code-weaver-runtime",
        "data_dir": str(DATA_DIR),
        "vault_mirror": "degraded" if storage.evidence.last_vault_error else "ok",
        "vault_error": storage.evidence.last_vault_error,
        "runtime_session_id": active.get("id") if active else None,
        "runtime_status": active.get("status") if active else "none",
        "active_window_instances": window_count,
        "active_extension_host_anchors": anchor_count,
    }


@app.get("/runtime/session")
def runtime_session():
    session = storage.active_runtime_session()
    return session or {"status": "none"}


@app.post("/runtime/session")
def ensure_runtime_session(workspace_path: str):
    record = storage.ensure_runtime_session(workspace_path)
    vscode_logs.baseline_session_dirs(DATA_DIR)
    codex.read_current_quota(storage.evidence, record["id"])
    return record


@app.post("/runtime/session/{session_id}/heartbeat")
def runtime_heartbeat(session_id: str, source: str = "runtime-api"):
    heartbeat = storage.heartbeat(session_id, source)
    return heartbeat or {"error": "not found"}


@app.post("/runtime/recover-stale")
def recover_stale_runtime_sessions(reason: str = "runtime_startup_recovery"):
    active = storage.active_runtime_session()
    if _runtime_is_recent(active):
        return {
            "closed": 0,
            "preserved_active_runtime": active["id"],
            "reason": "active_runtime_has_recent_heartbeat",
        }
    return {"closed": storage.close_stale_sessions(reason, runtime_only=True)}


@app.post("/runtime/session/{session_id}/vscode-windows")
def start_vscode_window(
    session_id: str,
    workspace_path: str,
    source: str = "vscode_launcher",
    process_id: Optional[str] = None,
    window_identifier: Optional[str] = None,
    focus_state: str = "unknown",
):
    window = storage.create_vscode_window(
        session_id,
        workspace_path,
        source,
        process_id=process_id,
        window_identifier=window_identifier,
        focus_state=focus_state,
    )
    window = window_instances.decorate_registered_instance(storage, window)
    return window or {"error": "not found"}


@app.get("/runtime/session/{session_id}/vscode-windows")
def list_vscode_windows(session_id: str, active_only: bool = False):
    if _session_or_none(session_id) is None:
        return {"error": "not found"}
    windows = windows_desktop.visible_window_rows(storage, session_id, active_only=active_only)
    return {"windows": windows, "count": len(windows)}


@app.get("/runtime/session/{session_id}/instances")
def code_weaver_window_instances(session_id: str):
    if _session_or_none(session_id) is None:
        return {"error": "not found"}
    return _control_plane_instances(session_id)


@app.post("/runtime/session/{session_id}/desktop-windows/observe")
def observe_desktop_windows(session_id: str):
    if _session_or_none(session_id) is None:
        return {"error": "not found"}
    probe = windows_desktop.reconcile_visible_windows(storage, session_id)
    return {"desktop": probe, "instances": _control_plane_instances(session_id)}


@app.post("/runtime/vscode-windows/{window_id}/bind-log")
def bind_vscode_window_log(
    window_id: str,
    log_session_dir: str,
    evidence_class: str = "derived",
):
    window = window_instances.bind_log_session(
        storage,
        window_id,
        log_session_dir,
        evidence_class=evidence_class,
    )
    return window or {"error": "not found or extension-host anchor already bound"}


@app.post("/runtime/vscode-windows/{window_id}/close")
def close_vscode_window(window_id: str, reason: str = "window_closed"):
    window = storage.close_vscode_window(window_id, reason)
    return window or {"error": "not found"}


@app.post("/sessions")
def start_session(workspace_path: str, source: str = "manual"):
    record = storage.create_session(workspace_path, source)
    vscode_logs.baseline_session_dirs(DATA_DIR)
    codex.read_current_quota(storage.evidence, record.id)
    return record.to_dict()


@app.post("/sessions/{session_id}/end")
def end_session(session_id: str):
    if _session_or_none(session_id) is None:
        return {"error": "not found"}
    storage.end_session(session_id)
    return {"id": session_id, "ended": True}


@app.get("/sessions")
def list_sessions(limit: int = 50):
    return storage.list_sessions(limit)


@app.get("/sessions/active")
def active_session():
    return storage.active_session() or {"status": "none"}


@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    record = _session_or_none(session_id)
    return record or {"error": "not found"}


@app.get("/today")
def today():
    sessions = storage.today_sessions()
    return {
        "sessions": sessions,
        "session_count": len(sessions),
        "quota": _latest_quota(),
    }


@app.get("/codex/quota")
def quota():
    return _latest_quota()


@app.post("/codex/quota/observe/{session_id}")
def observe_quota(session_id: str):
    session = _session_or_none(session_id)
    if session is None:
        return {"error": "not found"}
    observed = codex.read_current_quota(storage.evidence, session_id)
    return observed or {"status": "unknown"}


@app.get("/codex/rollout")
def rollout(session_id: str):
    session = _session_or_none(session_id)
    if session is None:
        return {"error": "not found"}
    records = []
    for event in session.get("events", []):
        if event.get("source") != "codex_rollout":
            continue
        normalized = event.get("data", {}).get("normalized")
        if normalized is not None:
            records.append(normalized)
    return {"records": records, "count": len(records)}


@app.post("/codex/rollout/ingest/{session_id}")
def ingest_rollout(session_id: str):
    session = _session_or_none(session_id)
    if session is None:
        return {"error": "not found"}
    records = codex.read_recent_rollout_events(
        storage.evidence,
        session_id,
        started_after=session["started_at"],
        ended_before=session["ended_at"] or codex.now_iso(),
    )
    return {"records": records, "count": len(records)}


@app.get("/git/{session_id}")
def git_state(session_id: str):
    record = _session_or_none(session_id)
    if record is None:
        return {"error": "not found"}
    return git_snapshot(Path(record["workspace_path"]))


@app.get("/release/evidence")
def verified_release_evidence():
    return release_evidence.read_verified_release_evidence()


@app.get("/evidence/sources")
def source_health():
    sources = {}
    for record in storage.evidence.tail_all(limit=2000):
        src = record["source"]
        if src not in sources or record["timestamp"] > sources[src]["last_seen"]:
            sources[src] = {
                "last_seen": record["timestamp"],
                "evidence_class": record["evidence_class"],
                "category": record["category"],
            }
    if storage.evidence.last_vault_error:
        sources["code_weaver_vault"] = {
            "last_seen": None,
            "evidence_class": "unavailable",
            "category": "storage",
            "status": "degraded",
            "error": storage.evidence.last_vault_error,
        }
    return sources


@app.get("/timeline")
def timeline(session_id: Optional[str] = None, limit: int = 200):
    if session_id is not None:
        events = storage.evidence.read_session(session_id)
    else:
        events = list(reversed(storage.evidence.tail_all(limit=max(limit, 2000))))
    return correlation.build_timeline(events, limit=limit)


def _instance_log_paths(session_id: str) -> list[Path]:
    paths: dict[str, Path] = {}
    for instance in window_instances.list_instances(storage, session_id, active_only=True):
        log_dir = instance.get("log_session_dir")
        if not log_dir:
            continue
        for log_path in codex.find_codex_extension_logs(Path(log_dir)):
            paths[str(log_path)] = log_path
    if not paths:
        for log_path in codex.find_codex_extension_logs():
            paths[str(log_path)] = log_path
    return list(paths.values())


@app.post("/vscode/scan/{session_id}")
def vscode_scan(session_id: str):
    session = _session_or_none(session_id)
    if session is None:
        return {"error": "not found"}
    ended_before = session["ended_at"] or codex.now_iso()
    new_dirs = vscode_logs.record_new_sessions(storage.evidence, session_id, DATA_DIR)
    discovered_anchors = window_instances.discover_recent_instances(storage, session_id)
    desktop = windows_desktop.reconcile_visible_windows(storage, session_id)
    reset_hits = []
    for log_path in _instance_log_paths(session_id):
        reset_hits += vscode_logs.scan_codex_log_for_resets(
            log_path,
            storage.evidence,
            session_id,
            DATA_DIR,
            started_after=session["started_at"],
            ended_before=ended_before,
        )
    return {
        "new_log_dirs": new_dirs,
        "ipc_events": reset_hits,
        "desktop_windows": desktop,
        "discovered_extension_host_anchors": discovered_anchors,
        "instances": _control_plane_instances(session_id),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=18441)
