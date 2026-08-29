#!/usr/bin/env python3
"""Read-only sanity check against the real local Codex/VS Code files."""

from __future__ import annotations

import sys

import codex


def main() -> int:
    failures = []

    print("=== Path discovery ===")
    session_dir = codex.find_latest_vscode_session_dir()
    print(f"Latest VS Code session dir: {session_dir}")

    stats_logs = codex.find_codex_stats_logs()
    print(f"Codex Stats.log candidates ({len(stats_logs)}):")
    for path in stats_logs[:5]:
        print(f"  {path}")

    ext_logs = codex.find_codex_extension_logs()
    print(f"Codex.log candidates ({len(ext_logs)}):")
    for path in ext_logs[:5]:
        print(f"  {path}")

    rollout_files = codex.find_rollout_files()
    print(f"Rollout files found ({len(rollout_files)}), showing up to 5:")
    for path in rollout_files[:5]:
        print(f"  {path}")

    print("\n=== Quota parse ===")
    if not stats_logs:
        failures.append("No Codex Stats.log found")
    else:
        snapshot = codex.parse_quota_from_stats_log(stats_logs[0])
        if snapshot is None:
            failures.append(f"No quota-shaped line found in {stats_logs[0]}")
        else:
            fields = snapshot["fields"]
            primary = codex._pick_flat(fields, "primaryUsedPercent", "primary_used_percent")
            secondary = codex._pick_flat(fields, "secondaryUsedPercent", "secondary_used_percent")
            print(f"source: {stats_logs[0]}")
            print(f"line: {snapshot['line_number']}")
            print(f"observed_at: {snapshot['observed_at']}")
            print(f"primary_used_percent: {primary}")
            print(f"secondary_used_percent: {secondary}")
            print(f"source_record_hash: {snapshot['source_record_hash']}")
            if primary is None or secondary is None:
                failures.append("Quota line found but primary/secondary percentages were not normalized")

    print("\n=== Rollout normalization ===")
    token_record = None
    task_record = None
    for path in rollout_files[:5]:
        for line_number, _, record in codex.iter_rollout_records_with_position(path):
            normalized = codex._normalize_rollout(path, line_number, record)
            source_type = normalized.get("source_event_type")
            if source_type == "token_count" and token_record is None:
                token_record = normalized
            if source_type == "task_complete" and task_record is None:
                task_record = normalized
            if token_record is not None and task_record is not None:
                break
        if token_record is not None and task_record is not None:
            break

    if token_record is None:
        failures.append("No token_count rollout record normalized")
    else:
        limits = token_record.get("rate_limits") or {}
        primary = limits.get("primary") or {}
        secondary = limits.get("secondary") or {}
        print("token_count:")
        print(f"  turn_id: {token_record.get('turn_id')}")
        print(f"  last_total_tokens: {(token_record.get('last_token_usage') or {}).get('total_tokens')}")
        print(f"  cumulative_total_tokens: {(token_record.get('total_token_usage') or {}).get('total_tokens')}")
        print(f"  limit_id: {limits.get('limit_id')}")
        print(f"  primary_used_percent: {primary.get('used_percent')}")
        print(f"  primary_window_minutes: {primary.get('window_minutes')}")
        print(f"  primary_resets_at: {primary.get('resets_at')}")
        print(f"  secondary_used_percent: {secondary.get('used_percent')}")
        print(f"  secondary_window_minutes: {secondary.get('window_minutes')}")
        print(f"  secondary_resets_at: {secondary.get('resets_at')}")
        if limits.get("limit_id") == "codex":
            if primary.get("window_minutes") not in (None, 300):
                failures.append(f"Unexpected Codex primary window: {primary.get('window_minutes')}")
            if secondary.get("window_minutes") not in (None, 10080):
                failures.append(f"Unexpected Codex secondary window: {secondary.get('window_minutes')}")

    if task_record is None:
        failures.append("No task_complete rollout record normalized")
    else:
        print("task_complete:")
        print(f"  turn_id: {task_record.get('turn_id')}")
        print(f"  duration_ms: {task_record.get('duration_ms')}")
        print(f"  time_to_first_token_ms: {task_record.get('time_to_first_token_ms')}")
        print(f"  error_code: {task_record.get('error_code')}")
        print(f"  error_message: {task_record.get('error_message')}")
        if task_record.get("duration_ms") is None:
            failures.append("task_complete found but duration_ms is missing")

    print("\n=== Result ===")
    if failures:
        print("FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("PASS — real Codex paths and normalized telemetry structures are readable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
