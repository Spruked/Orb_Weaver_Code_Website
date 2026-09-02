"""Synthetic proof for the provider-side WHAM usage collector.

No real ChatGPT request is sent. The HTTP opener is replaced with deterministic
responses and all evidence is written under a temporary directory.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from urllib.error import URLError

_TEMP_ROOT = Path(tempfile.mkdtemp(prefix="code-weaver-wham-test-"))
os.environ["CODE_WEAVER_VAULT_PATH"] = str(_TEMP_ROOT / "vault")
os.environ["CODEX_HOME"] = str(_TEMP_ROOT / "codex-home")

from evidence import EvidenceEvent, EvidenceLog  # noqa: E402
import wham_usage  # noqa: E402

# Keep the synthetic proof isolated from any real VS Code logs on the machine.
wham_usage.codex.VSCODE_LOGS_ROOT = _TEMP_ROOT / "no-real-vscode-logs"


class FakeResponse:
    status = 200

    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._body


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def prepare_runtime(data_dir: Path) -> str:
    data_dir.mkdir(parents=True, exist_ok=True)
    session_id = "synthetic-runtime-session"
    with sqlite3.connect(data_dir / "sessions.db") as conn:
        conn.execute(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                source TEXT,
                started_at TEXT,
                ended_at TEXT,
                status TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO sessions (id, source, started_at, ended_at, status)
            VALUES (?, ?, ?, NULL, 'active')
            """,
            (session_id, "code_weaver_runtime", wham_usage.now_iso()),
        )
        conn.commit()
    return session_id


def prepare_auth() -> tuple[Path, str]:
    token = "synthetic-secret-access-token-never-persist"
    auth_dir = _TEMP_ROOT / "codex-home"
    auth_dir.mkdir(parents=True, exist_ok=True)
    path = auth_dir / "auth.json"
    path.write_text(
        json.dumps(
            {
                "tokens": {
                    "access_token": token,
                    "account_id": "synthetic-account-id-never-persist",
                }
            }
        ),
        encoding="utf-8",
    )
    return path, token


def seed_stats_observation(data_dir: Path, session_id: str, timestamp: str) -> None:
    EvidenceLog(data_dir).append(
        EvidenceEvent(
            session_id=session_id,
            category="codex",
            event_type="quota_update",
            source="codex_stats_log",
            source_identifier="synthetic/Codex Stats.log",
            evidence_class="observed",
            parser_version="synthetic",
            data={
                "normalized": {
                    "primary_used_percent": 42,
                    "secondary_used_percent": 17,
                    "source_record_hash": "synthetic-stats-hash",
                    "observed_at": timestamp,
                }
            },
            timestamp=timestamp,
        )
    )


def main() -> None:
    data_dir = _TEMP_ROOT / "runtime"
    session_id = prepare_runtime(data_dir)
    auth_path, secret_token = prepare_auth()
    seed_stats_observation(data_dir, session_id, wham_usage.now_iso())

    payload = {
        "rate_limit": {
            "primary_window": {
                "used_percent": 42,
                "limit_window_seconds": 18000,
                "reset_at": 2000000000,
            },
            "secondary_window": {
                "used_percent": 17,
                "limit_window_seconds": 604800,
                "reset_at": 2000600000,
            },
        }
    }

    def fake_open(request, timeout=0):
        assert_true(
            request.get_header("Authorization") == f"Bearer {secret_token}",
            "bearer token missing",
        )
        assert_true(
            request.get_header("Chatgpt-account-id") == "synthetic-account-id-never-persist",
            "account header missing",
        )
        assert_true(timeout > 0, "request timeout was not set")
        return FakeResponse(payload)

    first = wham_usage.record_once(data_dir=data_dir, auth_path=auth_path, opener=fake_open)
    assert_true(first["status"] == "observed", "provider observation was not recorded")
    assert_true(first["persisted"] is True, "first provider observation should persist")

    second = wham_usage.record_once(data_dir=data_dir, auth_path=auth_path, opener=fake_open)
    assert_true(second["status"] == "observed", "second provider observation failed")
    assert_true(second["persisted"] is False, "identical provider state duplicated evidence")

    evidence = EvidenceLog(data_dir)
    events = evidence.read_session(session_id)
    wham_events = [event for event in events if event.get("source") == "codex_wham_usage"]
    comparisons = [event for event in events if event.get("event_type") == "quota_source_comparison"]
    assert_true(len(wham_events) == 1, "expected one deduplicated WHAM observation")
    assert_true(len(comparisons) == 1, "expected one source comparison")
    assert_true(
        comparisons[0]["data"]["normalized"]["state"] == "match",
        "matching sources were not correlated as match",
    )

    combined_text = (data_dir / "all_events.jsonl").read_text(encoding="utf-8")
    assert_true(secret_token not in combined_text, "access token leaked into evidence")
    assert_true(
        "synthetic-account-id-never-persist" not in combined_text,
        "account ID leaked into evidence",
    )

    changed_payload = {
        "rate_limit": {
            "primary_window": {"used_percent": 43, "limit_window_seconds": 18000},
            "secondary_window": {"used_percent": 17, "limit_window_seconds": 604800},
        }
    }

    def changed_open(request, timeout=0):
        return FakeResponse(changed_payload)

    changed = wham_usage.record_once(data_dir=data_dir, auth_path=auth_path, opener=changed_open)
    assert_true(changed["persisted"] is True, "changed provider reading did not persist")

    def offline_open(request, timeout=0):
        raise URLError("synthetic offline")

    failure = wham_usage.record_once(data_dir=data_dir, auth_path=auth_path, opener=offline_open)
    assert_true(failure["status"] == "unavailable", "network failure was not represented as unavailable")
    failure_again = wham_usage.record_once(data_dir=data_dir, auth_path=auth_path, opener=offline_open)
    assert_true(failure_again["persisted"] is False, "identical consecutive failure duplicated evidence")

    events = EvidenceLog(data_dir).read_session(session_id)
    status_events = [event for event in events if event.get("event_type") == "quota_source_status"]
    assert_true(len(status_events) == 1, "unavailable state should be deduplicated")
    assert_true(status_events[0]["evidence_class"] == "unavailable", "failure evidence class is wrong")

    print(
        {
            "status": "PASS",
            "provider_observation": True,
            "state_transition_deduplication": True,
            "source_correlation": True,
            "secret_redaction": True,
            "unavailable_state": True,
        }
    )


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(_TEMP_ROOT, ignore_errors=True)
