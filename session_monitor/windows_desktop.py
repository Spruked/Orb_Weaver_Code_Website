"""Windows desktop observation for real VS Code top-level windows.

Code Weaver runs inside WSL, while the human-visible VS Code windows are
Windows ``Code.exe`` top-level windows.  Remote WSL ``exthostN`` directories
are useful evidence anchors, but they are not themselves proof of a visible
window.  This module keeps those concepts separate.

The Windows observation is read-only.  ``powershell.exe`` is invoked with an
argument vector (never through shell quoting) and returns JSON for Code.exe
processes that currently own a non-zero main-window handle.
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from evidence import EvidenceEvent, now_iso

PARSER_VERSION = "windows-desktop-0.1"
WINDOW_SOURCES_EXCLUDED = {"vscode_exthost_discovery", "vscode_log_discovery"}


POWERSHELL_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$items = @(
  Get-Process -Name Code -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 -and -not [string]::IsNullOrWhiteSpace($_.MainWindowTitle) } |
    ForEach-Object {
      $started = $null
      try { $started = $_.StartTime.ToUniversalTime().ToString('o') } catch {}
      [pscustomobject]@{
        process_id = [int]$_.Id
        window_handle = [int64]$_.MainWindowHandle
        title = [string]$_.MainWindowTitle
        started_at = $started
      }
    }
)
ConvertTo-Json -InputObject $items -Compress -Depth 3
""".strip()


def _ensure_column(conn: sqlite3.Connection, column: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(vscode_windows)").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE vscode_windows ADD COLUMN {column} {definition}")


def ensure_schema(storage) -> None:
    with sqlite3.connect(storage.db_path) as conn:
        _ensure_column(conn, "window_title", "TEXT")
        _ensure_column(conn, "windows_process_id", "TEXT")
        _ensure_column(conn, "windows_window_handle", "TEXT")
        _ensure_column(conn, "desktop_observed_at", "TEXT")
        conn.commit()


def _powershell_executable() -> Optional[str]:
    candidates = [
        shutil.which("powershell.exe"),
        "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
        shutil.which("pwsh.exe"),
        shutil.which("pwsh"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file() or shutil.which(candidate):
            return str(candidate)
    return None


def observe_visible_windows() -> dict:
    """Observe human-visible VS Code windows through the Windows process API."""
    observed_at = now_iso()
    executable = _powershell_executable()
    if executable is None:
        return {
            "status": "unavailable",
            "observed_at": observed_at,
            "windows": [],
            "error": "powershell.exe/pwsh is unavailable from this WSL runtime",
        }
    try:
        result = subprocess.run(
            [
                executable,
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                POWERSHELL_SCRIPT,
            ],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "status": "unavailable",
            "observed_at": observed_at,
            "windows": [],
            "error": str(exc),
        }

    if result.returncode != 0:
        return {
            "status": "unavailable",
            "observed_at": observed_at,
            "windows": [],
            "error": (result.stderr or f"PowerShell exited {result.returncode}").strip(),
        }

    raw = result.stdout.strip().lstrip("\ufeff")
    if not raw:
        payload = []
    else:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            return {
                "status": "unavailable",
                "observed_at": observed_at,
                "windows": [],
                "error": f"Windows window JSON parse failed: {exc}",
            }
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        payload = []

    windows = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        process_id = item.get("process_id")
        window_handle = item.get("window_handle")
        title = item.get("title")
        if process_id is None or window_handle in (None, 0, "0") or not title:
            continue
        windows.append(
            {
                "process_id": str(process_id),
                "window_handle": str(window_handle),
                "title": str(title),
                "started_at": item.get("started_at"),
            }
        )
    windows.sort(key=lambda row: (row.get("started_at") or "", row["process_id"], row["window_handle"]))
    return {"status": "observed", "observed_at": observed_at, "windows": windows, "error": None}


def _label_from_title(title: str) -> str:
    text = title.strip()
    text = re.sub(r"\s[-–—]\sVisual Studio Code(?:\s-\sInsiders)?$", "", text, flags=re.IGNORECASE)
    parts = [part.strip() for part in re.split(r"\s[-–—]\s", text) if part.strip()]
    return parts[-1] if parts else (text or "VS Code")


def _norm(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _workspace_name(path: Optional[str]) -> str:
    if not path:
        return ""
    return Path(path).name


def visible_window_rows(storage, runtime_session_id: str, active_only: bool = False) -> list[dict]:
    ensure_schema(storage)
    query = "SELECT * FROM vscode_windows WHERE runtime_session_id = ?"
    params: list[object] = [runtime_session_id]
    if WINDOW_SOURCES_EXCLUDED:
        placeholders = ",".join("?" for _ in WINDOW_SOURCES_EXCLUDED)
        query += f" AND source NOT IN ({placeholders})"
        params.extend(sorted(WINDOW_SOURCES_EXCLUDED))
    if active_only:
        query += " AND ended_at IS NULL AND status = 'active'"
    query += " ORDER BY started_at"
    with sqlite3.connect(storage.db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def _find_launcher_match(rows: list[dict], label: str, already_claimed: set[str]) -> Optional[dict]:
    wanted = _norm(label)
    candidates = []
    for row in rows:
        if row["id"] in already_claimed:
            continue
        if row.get("source") not in {"vscode_folder_open", "vscode_launcher"}:
            continue
        if row.get("ended_at") is not None or row.get("windows_window_handle"):
            continue
        workspace = _norm(_workspace_name(row.get("workspace_path")))
        if wanted and workspace and (wanted == workspace or wanted.endswith(workspace) or workspace.endswith(wanted)):
            candidates.append(row)
    return candidates[0] if len(candidates) == 1 else None


def reconcile_visible_windows(storage, runtime_session_id: str) -> dict:
    """Reconcile OS-observed VS Code windows into Code Weaver child-window rows.

    A successful empty probe is meaningful and closes only rows that were
    themselves created by this observer.  A failed/unavailable probe never
    closes anything.
    """
    ensure_schema(storage)
    probe = observe_visible_windows()
    if probe["status"] != "observed":
        return {**probe, "created": 0, "updated": 0, "closed": 0}

    observed_at = probe["observed_at"]
    current_rows = visible_window_rows(storage, runtime_session_id, active_only=True)
    claimed_rows: set[str] = set()
    seen_observer_handles: set[tuple[str, str]] = set()
    created = 0
    updated = 0

    for desktop in probe["windows"]:
        pid = desktop["process_id"]
        handle = desktop["window_handle"]
        title = desktop["title"]
        label = _label_from_title(title)
        exact = next(
            (
                row
                for row in current_rows
                if row.get("windows_process_id") == pid and row.get("windows_window_handle") == handle
            ),
            None,
        )
        row = exact or _find_launcher_match(current_rows, label, claimed_rows)
        if row is not None:
            with sqlite3.connect(storage.db_path) as conn:
                conn.execute(
                    """
                    UPDATE vscode_windows
                    SET windows_process_id = ?, windows_window_handle = ?, window_title = ?,
                        desktop_observed_at = ?, last_observed_at = ?,
                        instance_label = CASE WHEN instance_label IS NULL OR instance_label = '' THEN ? ELSE instance_label END
                    WHERE id = ?
                    """,
                    (pid, handle, title, observed_at, observed_at, label, row["id"]),
                )
                conn.commit()
            claimed_rows.add(row["id"])
            updated += 1
        else:
            window_id = str(uuid.uuid4())
            identifier = f"windows-main-window:{pid}:{handle}"
            with sqlite3.connect(storage.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO vscode_windows
                        (id, runtime_session_id, workspace_path, source, started_at,
                         ended_at, status, close_reason, repo_root, branch, head,
                         remote, remote_host, process_id, window_identifier,
                         focus_state, codex_thread_id, codex_turn_id, last_observed_at,
                         instance_label, log_session_dir, identity_evidence_class, discovered_at,
                         window_title, windows_process_id, windows_window_handle, desktop_observed_at)
                    VALUES (?, ?, NULL, 'windows_main_window_discovery', ?, NULL, 'active', NULL,
                            NULL, NULL, NULL, NULL, NULL, NULL, ?, 'unknown', NULL, NULL, ?,
                            ?, NULL, 'observed', ?, ?, ?, ?, ?)
                    """,
                    (
                        window_id,
                        runtime_session_id,
                        desktop.get("started_at") or observed_at,
                        identifier,
                        observed_at,
                        label,
                        observed_at,
                        title,
                        pid,
                        handle,
                        observed_at,
                    ),
                )
                conn.commit()
            storage.evidence.append(
                EvidenceEvent(
                    session_id=runtime_session_id,
                    category="vscode_window",
                    event_type="window_observed_windows_process_api",
                    source="windows_desktop",
                    source_identifier=identifier,
                    evidence_class="observed",
                    parser_version=PARSER_VERSION,
                    data={
                        "child_window_id": window_id,
                        "windows_process_id": pid,
                        "windows_window_handle": handle,
                        "window_title": title,
                        "identity_note": "Observed Code.exe top-level main window through the Windows process API",
                    },
                    timestamp=observed_at,
                )
            )
            claimed_rows.add(window_id)
            created += 1
        seen_observer_handles.add((pid, handle))

    closed = 0
    with sqlite3.connect(storage.db_path) as conn:
        conn.row_factory = sqlite3.Row
        observer_rows = conn.execute(
            """
            SELECT * FROM vscode_windows
            WHERE runtime_session_id = ? AND source = 'windows_main_window_discovery'
              AND ended_at IS NULL AND status = 'active'
            """,
            (runtime_session_id,),
        ).fetchall()
        for row in observer_rows:
            key = (str(row["windows_process_id"] or ""), str(row["windows_window_handle"] or ""))
            if key in seen_observer_handles:
                continue
            conn.execute(
                """
                UPDATE vscode_windows
                SET ended_at = ?, status = 'closed', close_reason = 'windows_main_window_no_longer_observed',
                    last_observed_at = ?, desktop_observed_at = ?
                WHERE id = ?
                """,
                (observed_at, observed_at, observed_at, row["id"]),
            )
            closed += 1
            storage.evidence.append(
                EvidenceEvent(
                    session_id=runtime_session_id,
                    category="vscode_window",
                    event_type="window_no_longer_observed_windows_process_api",
                    source="windows_desktop",
                    source_identifier=row["window_identifier"] or row["id"],
                    evidence_class="observed",
                    parser_version=PARSER_VERSION,
                    data={"child_window_id": row["id"], "reason": "Top-level Code.exe main window no longer observed"},
                    timestamp=observed_at,
                )
            )
        conn.commit()

    return {**probe, "created": created, "updated": updated, "closed": closed}
