"""Runtime lifecycle proof for Code Weaver.

This test starts the real FastAPI runtime on 127.0.0.1:18441 with temporary
data/vault directories, exercises the public API, kills the runtime without
closing a session, and verifies restart recovery marks that session unclean.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib import parse, request

API_BASE = "http://127.0.0.1:18441"
REPO_ROOT = Path(__file__).resolve().parents[1]


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def require_port_free() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", 18441))
        except OSError as exc:
            raise RuntimeError("127.0.0.1:18441 is already in use; stop the runtime before this proof test") from exc


def http_json(method: str, path: str) -> dict:
    req = request.Request(f"{API_BASE}{path}", method=method)
    with request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_health() -> dict:
    last_error: Exception | None = None
    for _ in range(50):
        try:
            return http_json("GET", "/health")
        except Exception as exc:  # pragma: no cover - diagnostic loop.
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"runtime did not become healthy: {last_error}")


def start_runtime(data_dir: Path, vault_dir: Path) -> subprocess.Popen:
    env = {
        **os.environ,
        "CODE_WEAVER_RUNTIME_DATA_DIR": str(data_dir),
        "CODE_WEAVER_VAULT_PATH": str(vault_dir),
    }
    return subprocess.Popen(
        [sys.executable, "server.py"],
        cwd=REPO_ROOT / "session_monitor",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def stop_runtime(process: subprocess.Popen, clean: bool = False) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGTERM if clean else signal.SIGKILL)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> None:
    require_port_free()
    temp_root = Path(tempfile.mkdtemp(prefix="code-weaver-runtime-proof-"))
    data_dir = temp_root / "data"
    vault_dir = temp_root / "code_weaver_vault"
    shutil.copytree(REPO_ROOT / "code_weaver_vault", vault_dir, ignore=shutil.ignore_patterns("runtime"))

    runtime = start_runtime(data_dir, vault_dir)
    try:
        health = wait_for_health()
        assert_true(health["ok"] is True, "health did not report ok")
        assert_true(health["service"] == "code-weaver-runtime", "runtime service name mismatch")

        workspace = parse.quote(str(REPO_ROOT), safe="")
        session = http_json("POST", f"/runtime/session?workspace_path={workspace}")
        session_id = session["id"]
        assert_true(session["source"] == "code_weaver_runtime", "runtime session source mismatch")
        assert_true(session["status"] == "active", "runtime session was not active")

        heartbeat = http_json("POST", f"/runtime/session/{session_id}/heartbeat?source=runtime-proof-test")
        assert_true(heartbeat["id"] == session_id, "heartbeat did not target runtime session")

        window_1 = http_json(
            "POST",
            f"/runtime/session/{session_id}/vscode-windows?workspace_path={workspace}"
            "&source=runtime_proof&process_id=proof-1&window_identifier=simulated-window-1&focus_state=focused",
        )
        window_2 = http_json(
            "POST",
            f"/runtime/session/{session_id}/vscode-windows?workspace_path={workspace}"
            "&source=runtime_proof&process_id=proof-2&window_identifier=simulated-window-2&focus_state=background",
        )
        assert_true(window_1["id"] != window_2["id"], "VS Code child windows did not receive distinct IDs")

        active_windows = http_json("GET", f"/runtime/session/{session_id}/vscode-windows?active_only=true")
        assert_true(active_windows["count"] == 2, "expected two active VS Code child windows")

        closed_1 = http_json("POST", f"/runtime/vscode-windows/{window_1['id']}/close?reason=proof_close_one")
        assert_true(closed_1["status"] == "closed", "first VS Code child window did not close")

        remaining = http_json("GET", f"/runtime/session/{session_id}/vscode-windows?active_only=true")
        assert_true(remaining["count"] == 1, "closing one child window should leave one active")
        assert_true(remaining["windows"][0]["id"] == window_2["id"], "wrong child window remained active")

        session_record = http_json("GET", f"/sessions/{session_id}")
        event_types = {event["event_type"] for event in session_record["events"]}
        assert_true("runtime_heartbeat" in event_types, "runtime heartbeat evidence was not persisted")
        assert_true("window_start" in event_types, "VS Code child window start evidence was not persisted")
        assert_true("window_end" in event_types, "VS Code child window close evidence was not persisted")

        vault_events = vault_dir / "runtime" / "sessions" / session_id / "events.jsonl"
        assert_true(vault_events.exists(), "vault session evidence mirror was not created")
        assert_true(vault_events.read_text(encoding="utf-8").strip() != "", "vault session evidence mirror is empty")

        stop_runtime(runtime, clean=False)
        runtime = start_runtime(data_dir, vault_dir)
        wait_for_health()

        recovered = http_json("GET", f"/sessions/{session_id}")
        assert_true(recovered["status"] == "unclean", "unclean runtime session was not marked unclean")
        assert_true(recovered["end_reason"] == "monitor_startup", "unclean runtime session reason mismatch")
        assert_true(recovered["last_observed_at"], "last observed timestamp was not preserved")
        recovery_events = [event for event in recovered["events"] if event["event_type"] == "session_recovered_unclean"]
        assert_true(recovery_events, "unclean recovery evidence event was not appended")
        assert_true(
            recovery_events[-1]["data"]["recovery_class"] == "crash_recovery",
            "recovery event did not classify crash recovery",
        )

        new_session = http_json("POST", f"/runtime/session?workspace_path={workspace}")
        assert_true(new_session["id"] != session_id, "restart did not create a new runtime session after recovery")

        print(json.dumps({
            "health": health,
            "runtime_session_id": session_id,
            "new_runtime_session_id": new_session["id"],
            "window_ids": [window_1["id"], window_2["id"]],
            "remaining_active_window_id": remaining["windows"][0]["id"],
            "recovered_status": recovered["status"],
            "recovered_reason": recovered["end_reason"],
            "last_observed_at": recovered["last_observed_at"],
            "vault_events": str(vault_events),
        }, indent=2, sort_keys=True))
    finally:
        stop_runtime(runtime, clean=True)
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    main()
