"""
correlation.py

Read-only views over the monitor evidence stream. This module does not
append evidence and does not rewrite source records; it builds derived
timeline projections so the dashboard can inspect how VS Code/Codex
events line up with quota observations.
"""

from __future__ import annotations

from typing import Optional

CORRELATION_VERSION = "timeline-correlation-0.2"

RELOAD_EVENT_TYPES = {"new_log_session_dir", "ipc_event"}


def _last_path_part(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return value.rstrip("/").split("/")[-1]


def _as_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _quota_payload(event: dict) -> dict:
    normalized = event.get("data", {}).get("normalized", {})
    return {
        "primary_used_percent": _as_float(normalized.get("primary_used_percent")),
        "secondary_used_percent": _as_float(normalized.get("secondary_used_percent")),
        "resets_at": normalized.get("resets_at"),
        "source_file": normalized.get("source_file"),
    }


def _summary(event: dict) -> str:
    event_type = event.get("event_type")
    data = event.get("data", {})

    if event_type == "session_start":
        git = data.get("git", {})
        head = git.get("head")
        return f"Session started on {git.get('branch') or 'unknown branch'} at {head or 'unknown HEAD'}"

    if event_type == "session_end":
        return "Session ended"

    if event_type == "quota_update":
        quota = _quota_payload(event)
        return (
            "Quota observed "
            f"primary={quota['primary_used_percent']}% "
            f"secondary={quota['secondary_used_percent']}%"
        )

    if event_type == "new_log_session_dir":
        return f"VS Code log session detected: {_last_path_part(data.get('log_dir'))}"

    if event_type == "ipc_event":
        return f"Codex IPC/reset signal matched: {data.get('matched_pattern')}"

    if event_type == "rollout_record":
        normalized = data.get("normalized", {})
        turn_id = normalized.get("turn_id")
        duration_ms = normalized.get("duration_ms")
        error = normalized.get("error")
        token_usage = normalized.get("last_token_usage") or {}
        total_tokens = token_usage.get("total_tokens")
        if error:
            return f"Codex rollout error on turn {turn_id or 'unknown'}: {error}"
        if total_tokens is not None:
            return f"Codex token usage observed: {total_tokens} total tokens"
        if duration_ms:
            return f"Codex rollout turn {turn_id or 'unknown'} completed in {duration_ms}ms"
        return f"Codex rollout turn observed: {turn_id or 'unknown'}"

    return f"{event.get('category')}/{event_type}"


def _timeline_item(event: dict) -> dict:
    item = {
        "timestamp": event.get("timestamp"),
        "session_id": event.get("session_id"),
        "category": event.get("category"),
        "event_type": event.get("event_type"),
        "source": event.get("source"),
        "source_identifier": event.get("source_identifier"),
        "evidence_class": event.get("evidence_class"),
        "parser_version": event.get("parser_version"),
        "summary": _summary(event),
    }

    if event.get("event_type") == "quota_update":
        item["quota"] = _quota_payload(event)
    elif event.get("event_type") == "rollout_record":
        item["rollout"] = event.get("data", {}).get("normalized", {})
    elif event.get("event_type") in RELOAD_EVENT_TYPES:
        item["reload_signal"] = event.get("data", {})

    return item


def _quota_delta(before: Optional[dict], after: Optional[dict]) -> dict:
    if before is None or after is None:
        return {"primary_used_percent": None, "secondary_used_percent": None}

    before_quota = before.get("quota", {})
    after_quota = after.get("quota", {})
    before_primary = before_quota.get("primary_used_percent")
    after_primary = after_quota.get("primary_used_percent")
    before_secondary = before_quota.get("secondary_used_percent")
    after_secondary = after_quota.get("secondary_used_percent")

    return {
        "primary_used_percent": (
            after_primary - before_primary
            if before_primary is not None and after_primary is not None
            else None
        ),
        "secondary_used_percent": (
            after_secondary - before_secondary
            if before_secondary is not None and after_secondary is not None
            else None
        ),
    }


def _reload_quota_windows(timeline: list[dict]) -> list[dict]:
    quota_indexes = [
        index for index, item in enumerate(timeline)
        if item.get("event_type") == "quota_update"
    ]
    windows = []

    for index, item in enumerate(timeline):
        if item.get("event_type") not in RELOAD_EVENT_TYPES:
            continue

        before = next(
            (timeline[i] for i in reversed(quota_indexes) if i < index),
            None,
        )
        after = next(
            (timeline[i] for i in quota_indexes if i > index),
            None,
        )
        windows.append({
            "reload_event": item,
            "quota_before": before,
            "quota_after": after,
            "quota_delta": _quota_delta(before, after),
        })

    return windows


def _token_usage_summary(timeline: list[dict]) -> dict:
    attributed_last_token_records = {}
    unattributed_last_token_records = 0
    cumulative_records = []

    for item in timeline:
        if item.get("event_type") != "rollout_record":
            continue
        rollout = item.get("rollout") or {}
        last_usage = rollout.get("last_token_usage") or {}
        total_usage = rollout.get("total_token_usage") or {}
        if last_usage.get("total_tokens") is not None:
            turn_key = rollout.get("turn_id") or rollout.get("thread_id")
            if turn_key:
                attributed_last_token_records[str(turn_key)] = last_usage
            else:
                unattributed_last_token_records += 1
        if total_usage.get("total_tokens") is not None:
            cumulative_records.append(total_usage)

    def sum_key(records: list[dict], key: str) -> int:
        return sum(value for record in records if isinstance((value := record.get(key)), int))

    summed_records = list(attributed_last_token_records.values())
    latest_cumulative = cumulative_records[-1] if cumulative_records else None
    max_cumulative_total = max(
        (record.get("total_tokens") for record in cumulative_records if record.get("total_tokens") is not None),
        default=None,
    )

    return {
        "attributed_last_usage_turn_count": len(attributed_last_token_records),
        "unattributed_last_usage_record_count": unattributed_last_token_records,
        "summed_last_token_usage": {
            "input_tokens": sum_key(summed_records, "input_tokens"),
            "output_tokens": sum_key(summed_records, "output_tokens"),
            "reasoning_output_tokens": sum_key(summed_records, "reasoning_output_tokens"),
            "cached_input_tokens": sum_key(summed_records, "cached_input_tokens"),
            "cache_write_input_tokens": sum_key(summed_records, "cache_write_input_tokens"),
            "total_tokens": sum_key(summed_records, "total_tokens"),
        },
        "cumulative_snapshot_count": len(cumulative_records),
        "latest_total_token_usage": latest_cumulative,
        "max_total_tokens": max_cumulative_total,
    }


def build_timeline(events: list[dict], limit: int = 200) -> dict:
    ordered_events = sorted(
        events,
        key=lambda event: event.get("timestamp") or "",
    )
    timeline = [_timeline_item(event) for event in ordered_events][-limit:]
    counts = {}

    for item in timeline:
        event_type = item.get("event_type") or "unknown"
        counts[event_type] = counts.get(event_type, 0) + 1

    return {
        "correlation_version": CORRELATION_VERSION,
        "event_count": len(timeline),
        "counts": counts,
        "timeline": timeline,
        "reload_quota_windows": _reload_quota_windows(timeline),
        "token_usage_summary": _token_usage_summary(timeline),
    }
