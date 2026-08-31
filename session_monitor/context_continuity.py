"""Read-only context continuity analysis for Watcher evidence.

This module intentionally separates directly observed interruption signals from
inferences about context loss or reconstruction. It never writes evidence and
never claims provider-internal context state that was not exposed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

OBSERVED_INTERRUPTION_TYPES = {
    "ipc_event",
    "new_log_session_dir",
    "connection_reset",
    "disconnect",
    "reconnect",
    "app_server_started",
    "app_server_exited",
    "context_reset",
    "context_compaction",
}

RECONSTRUCTION_ACTION_HINTS = {
    "read_file",
    "file_read",
    "search",
    "repo_scan",
    "workspace_scan",
    "git_status",
    "git_state",
    "list_files",
    "find",
}


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _seconds_between(start: Optional[str], end: Optional[str]) -> Optional[float]:
    left = _parse(start)
    right = _parse(end)
    if left is None or right is None:
        return None
    return max(0.0, (right - left).total_seconds())


def _rollout(event: dict) -> dict:
    return event.get("data", {}).get("normalized", {}) if isinstance(event, dict) else {}


def _thread_id(event: dict) -> Optional[str]:
    rollout = _rollout(event)
    value = rollout.get("thread_id")
    return str(value) if value else None


def _action_key(event: dict) -> Optional[str]:
    data = event.get("data", {}) if isinstance(event, dict) else {}
    normalized = data.get("normalized", {}) if isinstance(data, dict) else {}
    for candidate in (
        normalized.get("action_type"),
        normalized.get("tool_name"),
        normalized.get("source_event_type"),
        data.get("action_type") if isinstance(data, dict) else None,
        event.get("event_type") if isinstance(event, dict) else None,
    ):
        if candidate:
            return str(candidate).lower()
    return None


def analyze(events: list[dict]) -> dict:
    """Build a conservative continuity view from one monitor session."""
    ordered = sorted(events, key=lambda event: event.get("timestamp") or "")
    interruptions = []
    thread_changes = []
    repeated_actions = []
    seen_actions: dict[str, str] = {}
    previous_thread = None

    for event in ordered:
        event_type = str(event.get("event_type") or "").lower()
        timestamp = event.get("timestamp")

        if event_type in OBSERVED_INTERRUPTION_TYPES:
            interruptions.append({
                "timestamp": timestamp,
                "event_type": event_type,
                "source": event.get("source"),
                "evidence_class": event.get("evidence_class"),
                "summary": event.get("data", {}),
            })

        thread = _thread_id(event)
        if thread:
            if previous_thread is not None and thread != previous_thread:
                thread_changes.append({
                    "timestamp": timestamp,
                    "from_thread": previous_thread,
                    "to_thread": thread,
                    "evidence_class": "inferred",
                })
            previous_thread = thread

        action = _action_key(event)
        if action and any(hint in action for hint in RECONSTRUCTION_ACTION_HINTS):
            if action in seen_actions:
                repeated_actions.append({
                    "timestamp": timestamp,
                    "action": action,
                    "previous_timestamp": seen_actions[action],
                    "evidence_class": "inferred",
                })
            seen_actions[action] = timestamp

    state = "CONTINUOUS"
    if interruptions:
        state = "INTERRUPTED_OBSERVED"
    if thread_changes:
        state = "CONTEXT_DISCONTINUITY_INFERRED"
    if repeated_actions and (interruptions or thread_changes):
        state = "RECONSTRUCTION_DETECTED"

    recovery_windows = []
    for interruption in interruptions:
        start = interruption.get("timestamp")
        reconstruction = next(
            (
                action for action in repeated_actions
                if start and action.get("timestamp") and action["timestamp"] >= start
            ),
            None,
        )
        if reconstruction:
            recovery_windows.append({
                "interruption_timestamp": start,
                "first_reconstruction_timestamp": reconstruction.get("timestamp"),
                "seconds_to_first_reconstruction": _seconds_between(
                    start, reconstruction.get("timestamp")
                ),
                "classification": "RECONSTRUCTION_DETECTED",
            })

    return {
        "continuity_version": "watcher-continuity-0.1",
        "state": state,
        "observed_interruption_count": len(interruptions),
        "inferred_thread_change_count": len(thread_changes),
        "inferred_repeated_action_count": len(repeated_actions),
        "interruptions": interruptions,
        "thread_changes": thread_changes,
        "repeated_actions": repeated_actions,
        "recovery_windows": recovery_windows,
        "limitations": [
            "Context loss is not labeled observed unless the provider/runtime explicitly exposes it.",
            "Repeated actions are reconstruction evidence only when correlated with a continuity break.",
            "Correlation does not establish that a continuity event caused provider quota movement.",
        ],
    }
