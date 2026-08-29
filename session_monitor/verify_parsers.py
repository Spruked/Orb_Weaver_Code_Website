#!/usr/bin/env python3
"""
verify_parsers.py — run this on the real WSL machine, inside monitor/, to
sanity-check the codex.py and vscode_logs.py parsers against real files
before trusting server.py's output. Read-only.

Usage:
    cd ~/projects/personal-session-monitor/monitor
    python3 verify_parsers.py
"""

import sys

import codex


def main():
    print("=== Path discovery ===")
    session_dir = codex.find_latest_vscode_session_dir()
    print(f"Latest VS Code session dir: {session_dir}")

    stats_logs = codex.find_codex_stats_logs()
    print(f"Codex Stats.log candidates ({len(stats_logs)}):")
    for p in stats_logs:
        print(f"  {p}")

    ext_logs = codex.find_codex_extension_logs()
    print(f"Codex.log candidates ({len(ext_logs)}):")
    for p in ext_logs:
        print(f"  {p}")

    rollout_files = codex.find_rollout_files()
    print(f"Rollout files found ({len(rollout_files)}), showing up to 5:")
    for p in rollout_files[:5]:
        print(f"  {p}")

    print("\n=== Quota parse attempt ===")
    if stats_logs:
        snapshot = codex.parse_quota_from_stats_log(stats_logs[0])
        if snapshot is None:
            print(f"No quota-shaped line found in {stats_logs[0]}")
            print("-> Send me a few raw lines from this file so the QUOTA_KEYS")
            print("   matching in codex.py can be corrected.")
        else:
            print(f"Matched line: {snapshot['raw_line']}")
            print(f"Extracted fields: {snapshot['fields']}")
    else:
        print("No Codex Stats.log found — check that VS Code has been opened")
        print("recently and Codex has produced output in this session.")

    print("\n=== Rollout parse attempt ===")
    if rollout_files:
        found_any = False
        for record in codex.iter_rollout_records(rollout_files[0]):
            flat = codex._flatten(record) if isinstance(record, dict) else {}
            has_hint = any(
                any(h.lower() in k.lower() for h in codex.TASK_RECORD_HINT_KEYS)
                for k in flat
            )
            if has_hint:
                found_any = True
                print(f"Matched record keys: {list(flat.keys())[:15]}")
                print(f"  duration_ms={flat.get('duration_ms')} error={flat.get('error')}")
                break
        if not found_any:
            print(f"No task-lifecycle-shaped record found in {rollout_files[0]}")
            print("-> Send me a sample record (redact anything sensitive) so")
            print("   TASK_RECORD_HINT_KEYS / normalization in codex.py can be fixed.")
    else:
        print("No rollout files found under ~/.codex/sessions/")

    print("\nDone. If anything above says 'No ... found', that's the exact")
    print("gap to close next — send the output back rather than guessing past it.")


if __name__ == "__main__":
    main()
