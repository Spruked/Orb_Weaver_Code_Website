"""Persistent bridge from Session Monitor evidence into Code Weaver Vault.

The SQLite index remains the fast session lookup. The vault is the durable,
repo-local source for append-only session evidence, memory summaries, glyph
traces, and operational metadata.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VAULT_BRIDGE_VERSION = "code-weaver-vault-0.1"

REPO_ROOT = Path(__file__).resolve().parents[1]
VAULT_ROOT = Path(os.environ.get("CODE_WEAVER_VAULT_PATH", REPO_ROOT / "code_weaver_vault"))
RUNTIME_ROOT = VAULT_ROOT / "runtime"
SESSION_ROOT = RUNTIME_ROOT / "sessions"
MEMORY_ROOT = RUNTIME_ROOT / "memory"
TELEMETRY_ROOT = RUNTIME_ROOT / "telemetry"
GLYPH_ROOT = RUNTIME_ROOT / "glyphs"
ARCHIVE_ROOT = RUNTIME_ROOT / "archive"

GLYPH_KEYS = {
    "session": "memory_recall",
    "codex": "decision_escalate",
    "codex_rollout": "decision_escalate",
    "vscode": "drift_detected",
    "git": "memory_recall",
    "storage": "memory_recall",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> str:
    return str(value)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=_json_default) + "\n")


def _load_glyph_map() -> dict:
    path = VAULT_ROOT / "glyphs" / "glyph_map.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _glyph_for(event: dict) -> dict:
    glyph_map = _load_glyph_map()
    key = GLYPH_KEYS.get(str(event.get("category") or ""), "memory_recall")
    entry = glyph_map.get(key, {})
    return {
        "key": key,
        "symbol": entry.get("symbol", "*"),
        "meaning": entry.get("meaning", key),
        "color": entry.get("color"),
    }


def ensure_vault_runtime() -> None:
    for path in (SESSION_ROOT, MEMORY_ROOT, TELEMETRY_ROOT, GLYPH_ROOT, ARCHIVE_ROOT):
        path.mkdir(parents=True, exist_ok=True)

    _write_json(
        RUNTIME_ROOT / "vault_runtime_manifest.json",
        {
            "version": VAULT_BRIDGE_VERSION,
            "vault": "code_weaver_vault",
            "repo_root": str(REPO_ROOT),
            "created_or_verified_at": now_iso(),
            "roles": {
                "sessions": str(SESSION_ROOT),
                "memory": str(MEMORY_ROOT),
                "telemetry": str(TELEMETRY_ROOT),
                "glyphs": str(GLYPH_ROOT),
                "archive": str(ARCHIVE_ROOT),
            },
        },
    )


def record_session_metadata(session: dict) -> None:
    ensure_vault_runtime()
    session_id = session["id"]
    _write_json(SESSION_ROOT / session_id / "session.json", session)
    _append_jsonl(MEMORY_ROOT / "long_term.jsonl", {
        "timestamp": now_iso(),
        "type": "session_metadata",
        "session_id": session_id,
        "workspace_path": session.get("workspace_path"),
        "repo_root": session.get("repo_root"),
        "branch": session.get("branch"),
        "head": session.get("head"),
        "source": session.get("source"),
    })


def record_event(event: dict) -> None:
    ensure_vault_runtime()
    session_id = event.get("session_id") or "unknown"
    glyph = _glyph_for(event)
    vaulted = {
        **event,
        "vault_bridge_version": VAULT_BRIDGE_VERSION,
        "glyph": glyph,
    }
    _append_jsonl(SESSION_ROOT / session_id / "events.jsonl", vaulted)
    _append_jsonl(TELEMETRY_ROOT / "agent_decisions.jsonl", {
        "timestamp": event.get("timestamp") or now_iso(),
        "session_id": session_id,
        "category": event.get("category"),
        "event_type": event.get("event_type"),
        "source": event.get("source"),
        "evidence_class": event.get("evidence_class"),
        "glyph": glyph,
    })
    _append_jsonl(GLYPH_ROOT / "trace.jsonl", {
        "timestamp": event.get("timestamp") or now_iso(),
        "session_id": session_id,
        "path": [
            str(event.get("category") or "unknown"),
            str(event.get("event_type") or "unknown"),
            str(event.get("source") or "unknown"),
        ],
        "glyph": glyph,
    })


def archive_path(path: Path, reason: str) -> Path:
    ensure_vault_runtime()
    if not path.exists():
        return ARCHIVE_ROOT / "missing"
    destination = ARCHIVE_ROOT / path.name
    counter = 1
    while destination.exists():
        destination = ARCHIVE_ROOT / f"{path.name}.{counter}"
        counter += 1
    if path.is_dir():
        shutil.copytree(path, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    _append_jsonl(ARCHIVE_ROOT / "archive_manifest.jsonl", {
        "timestamp": now_iso(),
        "source": str(path),
        "destination": str(destination),
        "reason": reason,
    })
    return destination
