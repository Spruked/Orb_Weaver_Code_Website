"""
server.py

Local HTTP API for the Personal Session Monitor. Run as a long-lived
process started by start.sh on WSL. The dashboard (phase 5) reads from
this instead of localStorage.

Endpoints:
    POST /sessions                 start a new session (always new — no resume)
    POST /sessions/{id}/end        end a session
    GET  /sessions                 list sessions, most recent first
    GET  /sessions/{id}            full session record + its evidence events
    GET  /today                    today's sessions + latest codex quota
    GET  /codex/quota              latest observed quota, or {"status": "unknown"}
    GET  /codex/rollout            recent parsed rollout records for a session
    GET  /git/{session_id}         current git snapshot for that session's workspace
    GET  /evidence/sources         source-health panel: last time each source produced data
    GET  /timeline                 derived event timeline + reload/quota windows
    POST /vscode/scan/{session_id} trigger a manual scan for new log dirs / IPC events

Requires: fastapi, uvicorn
    pip install fastapi uvicorn
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from storage import Storage
from evidence import EvidenceLog
from git_monitor import snapshot as git_snapshot
import codex
import correlation
import vscode_logs

DATA_DIR = Path.home() / ".local" / "share" / "personal-session-monitor"

storage = Storage(DATA_DIR)
app = FastAPI(title="Personal Session Monitor API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


@app.post("/sessions")
def start_session(workspace_path: str, source: str = "manual"):
    record = storage.create_session(workspace_path, source)
    # Best-effort first-touch scans so a new session immediately has
    # whatever quota/log evidence is already sitting on disk.
    codex.read_current_quota(storage.evidence, record.id)
    vscode_logs.baseline_session_dirs(DATA_DIR)
    return record.to_dict()


@app.post("/sessions/{session_id}/end")
def end_session(session_id: str):
    storage.end_session(session_id)
    return {"id": session_id, "ended": True}


@app.get("/sessions")
def list_sessions(limit: int = 50):
    return storage.list_sessions(limit)


@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    record = storage.get_session(session_id)
    return record or {"error": "not found"}


@app.get("/today")
def today():
    sessions = storage.today_sessions()
    quota = codex.read_current_quota(storage.evidence, sessions[0]["id"]) if sessions else None
    return {
        "sessions": sessions,
        "session_count": len(sessions),
        "quota": quota or {"status": "unknown"},
    }


@app.get("/codex/quota")
def quota():
    latest = storage.evidence.latest_by("codex", "quota_update")
    if latest is None:
        return {"status": "unknown"}
    return {"status": "observed", **latest["data"]["normalized"], "observed_via": latest["source_identifier"]}


@app.get("/codex/rollout")
def rollout(session_id: str):
    session = storage.get_session(session_id)
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
    record = storage.get_session(session_id)
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
    session = storage.get_session(session_id)
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
