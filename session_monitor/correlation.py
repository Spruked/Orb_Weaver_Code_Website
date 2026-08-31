"""
correlation.py

Read-only derived views over the append-only monitor evidence stream.
This module never appends or rewrites source evidence.
"""

from __future__ import annotations

from typing import Optional

CORRELATION_VERSION = "timeline-correlation-0.4"
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
    five_hour_used = _as_float(normalized.get("primary_used_percent"))
    weekly_used = _as_float(normalized.get("secondary_used_percent"))
    return {
        "five_hour_used_percent": five_hour_used,
        "weekly_used_percent": weekly_used,
        "five_hour_remaining_percent_derived": (
            100.0 - five_hour_used if five_hour_used is not None else None
        ),
        "weekly_remaining_percent_derived": (
            100.0 - weekly_used if weekly_used is not None else None
        ),
        "percentage_semantics": "used",
        "remaining_semantics": "derived_from_used",
        "raw_primary_used_percent": five_hour_used,
        "raw_secondary_used_percent": weekly_used,
        "source_file": normalized.get("source_file"),
        "source_line_number": normalized.get("source_line_number"),
        "source_record_hash": normalized.get("source_record_hash"),
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
    if event_type == "session_recovered_unclean":
        return "Previous runtime session recovered as unclean"
    if event_type == "quota_update":
        quota = _quota_payload(event)
        return (
            "Shared plan limits observed: "
            f"5-hour used={quota['five_hour_used_percent']}% "
            f"weekly used={quota['weekly_used_percent']}%"
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
        return {"five_hour_used_percent": None, "weekly_used_percent": None}
    before_quota = before.get("quota", {})
    after_quota = after.get("quota", {})
    b5 = before_quota.get("five_hour_used_percent")
    a5 = after_quota.get("five_hour_used_percent")
    bw = before_quota.get("weekly_used_percent")
    aw = after_quota.get("weekly_used_percent")
    return {
        "five_hour_used_percent": a5 - b5 if b5 is not None and a5 is not None else None,
        "weekly_used_percent": aw - bw if bw is not None and aw is not None else None,
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
    return windows[-100:]


def _neighbor_turn(timeline: list[dict], index: int, direction: int) -> Optional[dict]:
    source_identifier = timeline[index].get("source_identifier")
    cursor = index + direction
    inspected = 0
    while 0 <= cursor < len(timeline) and inspected < 16:
        candidate = timeline[cursor]
        cursor += direction
        inspected += 1
        if candidate.get("event_type") != "rollout_record":
            continue
        if candidate.get("source_identifier") != source_identifier:
            continue
        rollout = candidate.get("rollout") or {}
        turn_id = rollout.get("turn_id")
        if turn_id:
            return {
                "turn_id": str(turn_id),
                "thread_id": rollout.get("thread_id"),
                "timestamp": candidate.get("timestamp"),
            }
    return None


def _token_usage_summary(timeline: list[dict]) -> dict:
    """Summarize token snapshots without pretending missing turn IDs exist.

    Direct source turn IDs remain OBSERVED. A missing token_count turn ID is
    assigned DERIVED only when the nearest turn-bearing rollout event before
    and after it, from the same rollout file, carry the same turn ID. A one-sided
    timing guess stays unattributed.
    """
    per_turn_last: dict[str, dict] = {}
    direct_turn_ids: set[str] = set()
    derived_turn_ids: set[str] = set()
    unattributed_records: list[dict] = []
    cumulative = []

    for index, item in enumerate(timeline):
        if item.get("event_type") != "rollout_record":
            continue
        rollout = item.get("rollout") or {}
        if rollout.get("source_event_type") != "token_count":
            continue

        last_usage = rollout.get("last_token_usage") or {}
        total_usage = rollout.get("total_token_usage") or {}
        if total_usage.get("total_tokens") is not None:
            cumulative.append(total_usage)

        if last_usage.get("total_tokens") is None:
            continue

        direct_turn = rollout.get("turn_id")
        attribution_class = None
        turn_key = None
        attribution_basis = None

        if direct_turn:
            turn_key = str(direct_turn)
            attribution_class = "observed"
            attribution_basis = "turn_id_present_on_token_record"
            direct_turn_ids.add(turn_key)
        else:
            before = _neighbor_turn(timeline, index, -1)
            after = _neighbor_turn(timeline, index, 1)
            if before and after and before["turn_id"] == after["turn_id"]:
                turn_key = before["turn_id"]
                attribution_class = "derived"
                attribution_basis = "same_turn_observed_before_and_after_token_record"
                derived_turn_ids.add(turn_key)

        if turn_key:
            per_turn_last[turn_key] = {
                "turn_id": turn_key,
                "thread_id": rollout.get("thread_id"),
                "timestamp": item.get("timestamp"),
                "usage": last_usage,
                "attribution_class": attribution_class,
                "attribution_basis": attribution_basis,
                "source_identifier": item.get("source_identifier"),
                "source_record_hash": rollout.get("source_record_hash"),
            }
        else:
            unattributed_records.append({
                "timestamp": item.get("timestamp"),
                "source_identifier": item.get("source_identifier"),
                "source_record_hash": rollout.get("source_record_hash"),
                "last_token_usage": last_usage,
                "attribution_class": "unattributed",
                "reason": "no_direct_turn_id_and_no_two_sided_deterministic_join",
            })

    def sum_key(records: list[dict], key: str) -> int:
        total = 0
        for record in records:
            value = (record.get("usage") or {}).get(key)
            if isinstance(value, (int, float)):
                total += int(value)
        return total

    attributed = list(per_turn_last.values())
    latest_cumulative = cumulative[-1] if cumulative else None
    max_cumulative_total = max(
        (record.get("total_tokens") for record in cumulative if record.get("total_tokens") is not None),
        default=None,
    )
    return {
        "attributed_last_usage_turn_count": len(per_turn_last),
        "observed_attributed_turn_count": len(direct_turn_ids),
        "derived_attributed_turn_count": len(derived_turn_ids - direct_turn_ids),
        "unattributed_last_usage_record_count": len(unattributed_records),
        "attribution_policy": "direct turn id observed; otherwise two-sided same-turn join only",
        "per_turn_last_usage": attributed[-100:],
        "recent_unattributed_records": unattributed_records[-50:],
        "summed_last_token_usage": {
            "input_tokens": sum_key(attributed, "input_tokens"),
            "cached_input_tokens": sum_key(attributed, "cached_input_tokens"),
            "cache_write_input_tokens": sum_key(attributed, "cache_write_input_tokens"),
            "output_tokens": sum_key(attributed, "output_tokens"),
            "reasoning_output_tokens": sum_key(attributed, "reasoning_output_tokens"),
            "total_tokens": sum_key(attributed, "total_tokens"),
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
                "scope": "shared_plan_limits",
                "five_hour": rate_limits.get("primary"),
                "weekly": rate_limits.get("secondary"),
                "raw_primary": rate_limits.get("primary"),
                "raw_secondary": rate_limits.get("secondary"),
                "limit_id": rate_limits.get("limit_id"),
                "plan_type": rate_limits.get("plan_type"),
                "rate_limit_reached_type": rate_limits.get("rate_limit_reached_type"),
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
                "evidence_class": item.get("evidence_class"),
                "source_identifier": item.get("source_identifier"),
                "source_record_hash": rollout.get("source_record_hash"),
            }
    return None


def build_timeline(events: list[dict], limit: int = 200) -> dict:
    ordered_events = sorted(events, key=lambda event: event.get("timestamp") or "")
    full_timeline = [_timeline_item(event) for event in ordered_events]
    display_timeline = full_timeline[-limit:]
    counts = {}
    rollout_source_counts = {}

    for item in full_timeline:
        event_type = item.get("event_type") or "unknown"
        counts[event_type] = counts.get(event_type, 0) + 1
        if event_type == "rollout_record":
            source_type = (item.get("rollout") or {}).get("source_event_type") or "unknown"
            rollout_source_counts[source_type] = rollout_source_counts.get(source_type, 0) + 1

    return {
        "correlation_version": CORRELATION_VERSION,
        "event_count": len(full_timeline),
        "display_event_count": len(display_timeline),
        "counts": counts,
        "rollout_source_counts": rollout_source_counts,
        "timeline": display_timeline,
        "reload_quota_windows": _reload_quota_windows(full_timeline),
        "token_usage_summary": _token_usage_summary(full_timeline),
        "latest_rate_limits": _latest_rate_limits(full_timeline),
        "latest_limit_event": _latest_limit_event(full_timeline),
    }
