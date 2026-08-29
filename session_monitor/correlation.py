"""
correlation.py

Read-only derived views over the append-only monitor evidence stream.
This module never appends or rewrites source evidence.
"""

from __future__ import annotations

from typing import Optional

CORRELATION_VERSION = "timeline-correlation-0.3"
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
        "source_file": normalized.get("source_file"),
        "observed_at": normalized.get("observed_at"),
    }


def _summary(event: dict) -> str:
    event_type = event.get("event_type")
    data = event.get("data", {})

    if event_type == "session_start":
        git = data.get("git", {})
        return (
            f"Session started on {git.get('branch') or 'unknown branch'} "
            f"at {git.get('head') or 'unknown HEAD'}"
        )
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
        source_type = normalized.get("source_event_type") or "rollout"
        turn_id = normalized.get("turn_id")
        error = normalized.get("error_code") or normalized.get("error")
        total_tokens = (normalized.get("last_token_usage") or {}).get("total_tokens")
        duration_ms = normalized.get("duration_ms")
        if error:
            return f"Codex {source_type} on turn {turn_id or 'unknown'}: {error}"
        if source_type == "token_count" and total_tokens is not None:
            return f"Codex token usage observed: {total_tokens} last-use tokens"
        if duration_ms is not None:
            return f"Codex {source_type} turn {turn_id or 'unknown'}: {duration_ms}ms"
        return f"Codex {source_type} observed on turn {turn_id or 'unknown'}"
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
    bp = before_quota.get("primary_used_percent")
    ap = after_quota.get("primary_used_percent")
    bs = before_quota.get("secondary_used_percent")
    ass = after_quota.get("secondary_used_percent")
    return {
        "primary_used_percent": ap - bp if bp is not None and ap is not None else None,
        "secondary_used_percent": ass - bs if bs is not None and ass is not None else None,
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
        before = next((timeline[i] for i in reversed(quota_indexes) if i < index), None)
        after = next((timeline[i] for i in quota_indexes if i > index), None)
        windows.append({
            "reload_event": item,
            "quota_before": before,
            "quota_after": after,
            "quota_delta": _quota_delta(before, after),
        })
    return windows


def _token_usage_summary(timeline: list[dict]) -> dict:
    attributed_last = {}
    unattributed_last = 0
    cumulative = []

    for item in timeline:
        if item.get("event_type") != "rollout_record":
            continue
        rollout = item.get("rollout") or {}
        if rollout.get("source_event_type") != "token_count":
            continue
        last_usage = rollout.get("last_token_usage") or {}
        total_usage = rollout.get("total_token_usage") or {}
        if last_usage.get("total_tokens") is not None:
            turn_key = rollout.get("turn_id") or rollout.get("thread_id")
            if turn_key:
                attributed_last[str(turn_key)] = last_usage
            else:
                unattributed_last += 1
        if total_usage.get("total_tokens") is not None:
            cumulative.append(total_usage)

    def sum_key(records: list[dict], key: str) -> int:
        total = 0
        for record in records:
            value = record.get(key)
            if isinstance(value, (int, float)):
                total += int(value)
        return total

    summed = list(attributed_last.values())
    latest_cumulative = cumulative[-1] if cumulative else None
    max_cumulative_total = max(
        (record.get("total_tokens") for record in cumulative if record.get("total_tokens") is not None),
        default=None,
    )
    return {
        "attributed_last_usage_turn_count": len(attributed_last),
        "unattributed_last_usage_record_count": unattributed_last,
        "summed_last_token_usage": {
            "input_tokens": sum_key(summed, "input_tokens"),
            "cached_input_tokens": sum_key(summed, "cached_input_tokens"),
            "cache_write_input_tokens": sum_key(summed, "cache_write_input_tokens"),
            "output_tokens": sum_key(summed, "output_tokens"),
            "reasoning_output_tokens": sum_key(summed, "reasoning_output_tokens"),
            "total_tokens": sum_key(summed, "total_tokens"),
        },
        "cumulative_snapshot_count": len(cumulative),
        "latest_total_token_usage": latest_cumulative,
        "max_total_tokens": max_cumulative_total,
    }


def _latest_rate_limits(timeline: list[dict]) -> Optional[dict]:
    for item in reversed(timeline):
        rollout = item.get("rollout") or {}
        rate_limits = rollout.get("rate_limits") or {}
        if rate_limits.get("limit_id") == "codex" and (
            rate_limits.get("primary") is not None or rate_limits.get("secondary") is not None
        ):
            return {
                "timestamp": item.get("timestamp"),
                **rate_limits,
            }
    return None


def _latest_limit_event(timeline: list[dict]) -> Optional[dict]:
    for item in reversed(timeline):
        rollout = item.get("rollout") or {}
        if rollout.get("error_code") == "usage_limit_exceeded":
            return {
                "timestamp": item.get("timestamp"),
                "turn_id": rollout.get("turn_id"),
                "error_code": rollout.get("error_code"),
                "error_message": rollout.get("error_message"),
            }
    return None


def build_timeline(events: list[dict], limit: int = 200) -> dict:
    ordered_events = sorted(events, key=lambda event: event.get("timestamp") or "")
    timeline = [_timeline_item(event) for event in ordered_events][-limit:]
    counts = {}
    rollout_source_counts = {}

    for item in timeline:
        event_type = item.get("event_type") or "unknown"
        counts[event_type] = counts.get(event_type, 0) + 1
        if event_type == "rollout_record":
            source_type = (item.get("rollout") or {}).get("source_event_type") or "unknown"
            rollout_source_counts[source_type] = rollout_source_counts.get(source_type, 0) + 1

    return {
        "correlation_version": CORRELATION_VERSION,
        "event_count": len(timeline),
        "counts": counts,
        "rollout_source_counts": rollout_source_counts,
        "timeline": timeline,
        "reload_quota_windows": _reload_quota_windows(timeline),
        "token_usage_summary": _token_usage_summary(timeline),
        "latest_rate_limits": _latest_rate_limits(timeline),
        "latest_limit_event": _latest_limit_event(timeline),
    }
