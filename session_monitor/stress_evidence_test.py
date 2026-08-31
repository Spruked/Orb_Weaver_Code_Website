"""Stress proof for Code Weaver append-only evidence storage.

Exercises sustained append volume, concurrent writers, duplicate-hash caching,
streaming tail reads, vault mirroring, and tolerance of a truncated JSONL tail.
No real user prompts, responses, or repository data are used.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

_TEMP_ROOT = Path(tempfile.mkdtemp(prefix="code-weaver-evidence-stress-"))
os.environ["CODE_WEAVER_VAULT_PATH"] = str(_TEMP_ROOT / "code_weaver_vault")
os.environ["CODE_WEAVER_EVIDENCE_FSYNC"] = "0"
os.environ["CODE_WEAVER_VAULT_FSYNC"] = "0"

from evidence import EvidenceEvent, EvidenceLog  # noqa: E402

SESSION_ID = "stress-session"
SEQUENTIAL_EVENTS = 5000
THREADS = 4
EVENTS_PER_THREAD = 500


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_event(index: int, source: str = "stress") -> EvidenceEvent:
    source_hash = f"{source}-{index:08d}"
    return EvidenceEvent(
        session_id=SESSION_ID,
        category="stress",
        event_type="synthetic_evidence",
        source="stress_test",
        source_identifier=source,
        evidence_class="observed",
        parser_version="stress-proof-1",
        data={
            "normalized": {
                "source_record_hash": source_hash,
                "sequence": index,
            }
        },
    )


def append_worker(log: EvidenceLog, worker_id: int) -> None:
    base = SEQUENTIAL_EVENTS + worker_id * EVENTS_PER_THREAD
    for offset in range(EVENTS_PER_THREAD):
        log.append(make_event(base + offset, source=f"worker-{worker_id}"))


def main() -> None:
    data_dir = _TEMP_ROOT / "data"
    log = EvidenceLog(data_dir)
    started = time.monotonic()

    for index in range(SEQUENTIAL_EVENTS):
        log.append(make_event(index))

    first_hash_scan_started = time.monotonic()
    hashes = log.source_record_hashes(SESSION_ID)
    first_hash_scan_seconds = time.monotonic() - first_hash_scan_started
    assert_true(len(hashes) == SEQUENTIAL_EVENTS, "initial source hash index is incomplete")

    cached_hash_scan_started = time.monotonic()
    cached_hashes = log.source_record_hashes(SESSION_ID)
    cached_hash_scan_seconds = time.monotonic() - cached_hash_scan_started
    assert_true(cached_hashes == hashes, "cached source hash index changed unexpectedly")

    threads = [
        threading.Thread(target=append_worker, args=(log, worker_id), daemon=True)
        for worker_id in range(THREADS)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert_true(not thread.is_alive(), "concurrent writer did not finish")

    expected = SEQUENTIAL_EVENTS + THREADS * EVENTS_PER_THREAD
    records = log.read_session(SESSION_ID)
    assert_true(len(records) == expected, f"expected {expected} records, got {len(records)}")

    hashes_after_threads = log.source_record_hashes(SESSION_ID)
    assert_true(len(hashes_after_threads) == expected, "hash cache did not track concurrent appends")

    tail = log.tail_all(limit=200)
    assert_true(len(tail) == 200, "streaming combined tail did not return requested size")

    session_path = data_dir / "events" / f"{SESSION_ID}.jsonl"
    with session_path.open("a", encoding="utf-8") as handle:
        handle.write('{"truncated":')
    recovered_records = log.read_session(SESSION_ID)
    assert_true(
        len(recovered_records) == expected,
        "truncated final JSONL line made historical evidence unreadable",
    )

    vault_events = (
        _TEMP_ROOT
        / "code_weaver_vault"
        / "runtime"
        / "sessions"
        / SESSION_ID
        / "events.jsonl"
    )
    assert_true(vault_events.is_file(), "vault evidence mirror was not created")
    vault_count = sum(1 for line in vault_events.open("r", encoding="utf-8") if line.strip())
    assert_true(vault_count == expected, "vault mirror event count does not match primary evidence")

    elapsed = time.monotonic() - started
    print(json.dumps({
        "status": "PASS",
        "events_written": expected,
        "concurrent_writers": THREADS,
        "tail_records_checked": len(tail),
        "truncated_tail_recovery": True,
        "vault_mirror_records": vault_count,
        "first_hash_scan_seconds": round(first_hash_scan_seconds, 6),
        "cached_hash_scan_seconds": round(cached_hash_scan_seconds, 6),
        "elapsed_seconds": round(elapsed, 3),
        "temp_root": str(_TEMP_ROOT),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(_TEMP_ROOT, ignore_errors=True)
