"""
server.py

Local HTTP API for the Session Monitor control plane.

Read endpoints are side-effect free. Evidence enters the append-only ledger
only through explicit session/observation/ingestion actions.

Endpoints:
    GET  /health
    POST /sessions
    POST /sessions/{id}/end
    GET  /sessions
    GET  /sessions/{id}
    GET  /today
    GET  /codex/quota
    POST /codex/quota/observe/{session_id}
    GET  /codex/rollout?session_id=<id>
    POST /codex/rollout/ingest/{session_id}
    GET  /git/{session_id}
    GET  /evidence/sources
    GET  /timeline
    POST /vscode/scan/{session_id}
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from storage import Storage
from git_monitor import snapshot as git_snapshot
import codex
import correlation
import vscode_logs

DATA_DIR = Path.home() / ".local" / "share" / "personal-session-monitor"

storage = Storage(DATA_DIR)
app = FastAPI(title="Personal Session Monitor API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _latest_quota() -> dict:
    latest = storage.evidence.latest_by("codex", "quota_update")
    if latest is None:
        return {"status": "unknown"}
    normalized = latest.get("data", {}).get("normalized", {})
    return {
        "status": "observed",
        **normalized,
        "observed_via": latest.get("source_identifier"),
        "evidence_timestamp": latest.get("timestamp"),
    }


def _session_or_none(session_id: str):
    return storage.get_session(session_id)


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "personal-session-monitor",
        "data_dir": str(DATA_DIR),
    }


@app.post("/sessions")
def start_session(workspace_path: str, source: str = "manual"):
    record = storage.create_session(workspace_path, source)
    # Existing VS Code log directories are baseline state, not reload events.
    vscode_logs.baseline_session_dirs(DATA_DIR)
    # Capture one real provider observation at the session boundary.
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


@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    record = _session_or_none(session_id)
    return record or {"error": "not found"}


@app.get("/today")
def today():
    # Read-only: dashboard refreshes must never create evidence.
    sessions = storage.today_sessions()
    return {
        "sessions": sessions,
        "session_count": len(sessions),
        "quota": _latest_quota(),
    }


@app.get("/codex/quota")
def quota():
    # Read-only view of the latest persisted provider observation.
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
    # Read-only view. Ingestion is a POST operation below.
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
    return sources


@app.get("/timeline")
def timeline(session_id: Optional[str] = None, limit: int = 200):
    if session_id is not None:
        events = storage.evidence.read_session(session_id)
    else:
        events = list(reversed(storage.evidence.tail_all(limit=limit)))
    return correlation.build_timeline(events, limit=limit)


@app.post("/vscode/scan/{session_id}")
def vscode_scan(session_id: str):
    session = _session_or_none(session_id)
    if session is None:
        return {"error": "not found"}
    ended_before = session["ended_at"] or codex.now_iso()
    new_dirs = vscode_logs.record_new_sessions(storage.evidence, session_id, DATA_DIR)
    reset_hits = []
    for log_path in codex.find_codex_extension_logs():
        reset_hits += vscode_logs.scan_codex_log_for_resets(
            log_path,
            storage.evidence,
            session_id,
            DATA_DIR,
            started_after=session["started_at"],
            ended_before=ended_before,
        )
    return {"new_log_dirs": new_dirs, "ipc_events": reset_hits}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=18441)
