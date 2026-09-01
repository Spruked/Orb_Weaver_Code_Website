"""Synthetic proof for the Windows desktop child-window lifecycle.

No real Windows processes or user workspaces are touched.  The PowerShell probe
is replaced with deterministic observations so this test proves row creation,
identity stability, closure, and unavailable-probe safety.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

_TEMP_ROOT = Path(tempfile.mkdtemp(prefix="code-weaver-desktop-test-"))
os.environ["CODE_WEAVER_VAULT_PATH"] = str(_TEMP_ROOT / "vault")

from storage import Storage  # noqa: E402
import windows_desktop  # noqa: E402


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    storage = Storage(_TEMP_ROOT / "runtime")
    session = storage.ensure_runtime_session(str(_TEMP_ROOT / "workspace"))
    session_id = session["id"]

    first = {
        "status": "observed",
        "observed_at": "2026-09-01T10:00:00+00:00",
        "error": None,
        "windows": [
            {
                "process_id": "101",
                "window_handle": "1001",
                "title": "Repo A - Visual Studio Code",
                "started_at": "2026-09-01T09:55:00+00:00",
            },
            {
                "process_id": "202",
                "window_handle": "2002",
                "title": "Repo B - Visual Studio Code",
                "started_at": "2026-09-01T09:56:00+00:00",
            },
        ],
    }
    windows_desktop.observe_visible_windows = lambda: first
    result = windows_desktop.reconcile_visible_windows(storage, session_id)
    assert_true(result["created"] == 2, "two observed main windows were not created")
    rows = windows_desktop.visible_window_rows(storage, session_id, active_only=True)
    assert_true(len(rows) == 2, "active visible-window count should be two")
    ids = {row["id"] for row in rows}

    # Re-observing the same handles must update, not duplicate.
    second = dict(first)
    second["observed_at"] = "2026-09-01T10:00:15+00:00"
    windows_desktop.observe_visible_windows = lambda: second
    result = windows_desktop.reconcile_visible_windows(storage, session_id)
    rows = windows_desktop.visible_window_rows(storage, session_id, active_only=True)
    assert_true(result["created"] == 0, "stable window handles should not duplicate rows")
    assert_true({row["id"] for row in rows} == ids, "window identity changed across observations")

    # A successful observation with one window gone closes only the observer row.
    third = {
        "status": "observed",
        "observed_at": "2026-09-01T10:00:30+00:00",
        "error": None,
        "windows": [second["windows"][0]],
    }
    windows_desktop.observe_visible_windows = lambda: third
    result = windows_desktop.reconcile_visible_windows(storage, session_id)
    assert_true(result["closed"] == 1, "missing observed window was not closed")
    rows = windows_desktop.visible_window_rows(storage, session_id, active_only=True)
    assert_true(len(rows) == 1, "one visible window should remain active")

    # An unavailable probe must never close the remaining window.
    windows_desktop.observe_visible_windows = lambda: {
        "status": "unavailable",
        "observed_at": "2026-09-01T10:00:45+00:00",
        "windows": [],
        "error": "synthetic probe failure",
    }
    result = windows_desktop.reconcile_visible_windows(storage, session_id)
    rows = windows_desktop.visible_window_rows(storage, session_id, active_only=True)
    assert_true(result["closed"] == 0, "unavailable probe must not close windows")
    assert_true(len(rows) == 1, "unavailable probe changed visible-window state")

    print(
        {
            "status": "PASS",
            "created_two_windows": True,
            "stable_identity": True,
            "closed_disappeared_window": True,
            "unavailable_probe_preserved_state": True,
        }
    )


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(_TEMP_ROOT, ignore_errors=True)
