"""Persistent bridge from Session Monitor evidence into Code Weaver Vault.

The SQLite index remains the fast session lookup. The vault is a durable
append-oriented mirror for session evidence, memory summaries, glyph traces,
and operational metadata. Primary evidence remains authoritative.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

VAULT_BRIDGE_VERSION = "code-weaver-vault-0.2"

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
    "runtime": "memory_recall",
    "vscode_window": "drift_detected",
    "codex": "decision_escalate",
    "codex_rollout": "decision_escalate",
    "vscode": "drift_detected",
    "git": "memory_recall",
    "storage": "memory_recall",
}

_LOCK = threading.RLock()
_RUNTIME_READY = False
_GLYPH_MAP_CACHE: Optional[dict] = None
_FSYNC = os.environ.get("CODE_WEAVER_VAULT_FSYNC", "0") == "1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> str:
    return str(value)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    rendered = json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n"
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(rendered)
        handle.flush()
        if _FSYNC:
            os.fsync(handle.fileno())
    tmp.replace(path)


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, sort_keys=True, default=_json_default) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(rendered)
        handle.flush()
        if _FSYNC:
            os.fsync(handle.fileno())


def _load_glyph_map() -> dict:
    global _GLYPH_MAP_CACHE
    if _GLYPH_MAP_CACHE is not None:
        return _GLYPH_MAP_CACHE
    path = VAULT_ROOT / "glyphs" / "glyph_map.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        _GLYPH_MAP_CACHE = loaded if isinstance(loaded, dict) else {}
    except Exception:
        _GLYPH_MAP_CACHE = {}
    return _GLYPH_MAP_CACHE


def _glyph_for(event: dict) -> dict:
    glyph_map = _load_glyph_map()
    key = GLYPH_KEYS.get(str(event.get("category") or ""), "memory_recall")
    entry = glyph_map.get(key, {}) if isinstance(glyph_map, dict) else {}
    return {
        "key": key,
        "symbol": entry.get("symbol", "*"),
        "meaning": entry.get("meaning", key),
        "color": entry.get("color"),
    }


def ensure_vault_runtime(force_manifest_refresh: bool = False) -> None:
    """Ensure vault runtime directories exist without rewriting a valid manifest.

    Code Weaver has companion writer processes (for example the provider usage
    observer). Each process has its own module globals, so relying only on the
    in-process ``_RUNTIME_READY`` flag would rewrite the shared manifest every
    time a short-lived writer starts. Existing manifests are therefore treated
    as durable readiness evidence unless an explicit refresh is requested.
    """
    global _RUNTIME_READY
    with _LOCK:
        if _RUNTIME_READY and not force_manifest_refresh:
            return
        for path in (SESSION_ROOT, MEMORY_ROOT, TELEMETRY_ROOT, GLYPH_ROOT, ARCHIVE_ROOT):
            path.mkdir(parents=True, exist_ok=True)

        manifest_path = RUNTIME_ROOT / "vault_runtime_manifest.json"
        if manifest_path.exists() and not force_manifest_refresh:
            _RUNTIME_READY = True
            return

        _write_json(
            manifest_path,
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
        _RUNTIME_READY = True


def record_session_metadata(session: dict) -> None:
    ensure_vault_runtime()
    session_id = session["id"]
    with _LOCK:
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
            "status": session.get("status"),
            "end_reason": session.get("end_reason"),
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
    with _LOCK:
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
    with _LOCK:
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
