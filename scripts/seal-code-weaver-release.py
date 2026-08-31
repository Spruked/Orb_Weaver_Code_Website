#!/usr/bin/env python3
"""Create reproducible local release/source evidence for Code Weaver.

This script never invents release facts. It seals the exact tracked Git source
state and any artifact files explicitly supplied by the operator. A dirty
working tree or missing artifact remains visible in the verification result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "code_weaver_vault" / "runtime" / "release_evidence" / "current.json"
SCHEMA = "code-weaver-release-evidence-v1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.rstrip("\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def tracked_source_manifest() -> tuple[list[dict], str]:
    names = [name for name in git("ls-files", "-z").split("\0") if name]
    entries: list[dict] = []
    manifest_digest = hashlib.sha256()

    for relative in sorted(names):
        path = REPO_ROOT / relative
        if not path.is_file():
            # A tracked deletion is already represented by dirty-state evidence.
            continue
        file_hash = sha256_file(path)
        size = path.stat().st_size
        entry = {"path": relative, "sha256": file_hash, "size": size}
        entries.append(entry)
        manifest_digest.update(
            f"{relative}\0{file_hash}\0{size}\n".encode("utf-8", errors="strict")
        )

    return entries, manifest_digest.hexdigest()


def artifact_record(raw_path: str) -> dict:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    if not path.is_file():
        return {
            "path": str(path),
            "filename": path.name,
            "status": "UNAVAILABLE",
            "sha256": None,
            "size": None,
        }
    return {
        "path": str(path),
        "filename": path.name,
        "status": "SEALED",
        "sha256": sha256_file(path),
        "size": path.stat().st_size,
    }


def canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seal Code Weaver source/release evidence")
    parser.add_argument("--release-id", default=None)
    parser.add_argument("--version", default=None)
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    head = git("rev-parse", "HEAD")
    branch = git("branch", "--show-current") or "DETACHED"
    remote = git("config", "--get", "remote.origin.url") if git("remote") else None
    status_lines = [line for line in git("status", "--porcelain=v1").splitlines() if line]
    source_entries, source_manifest_hash = tracked_source_manifest()
    artifacts = [artifact_record(value) for value in args.artifact]
    all_artifacts_sealed = bool(artifacts) and all(item["status"] == "SEALED" for item in artifacts)
    clean = not status_lines

    if clean and all_artifacts_sealed:
        verification_result = "SEALED_RELEASE_EVIDENCE"
    elif clean:
        verification_result = "SOURCE_SEALED_ARTIFACT_PENDING"
    elif all_artifacts_sealed:
        verification_result = "ARTIFACT_SEALED_DIRTY_SOURCE"
    else:
        verification_result = "SOURCE_SEAL_DIRTY_WORKTREE"

    payload = {
        "schema": SCHEMA,
        "generated_at": now_iso(),
        "release_id": args.release_id,
        "version": args.version,
        "verification_result": verification_result,
        "source": {
            "repository": REPO_ROOT.name,
            "repo_root": str(REPO_ROOT),
            "remote": remote,
            "branch": branch,
            "git_commit": head,
            "working_tree_clean": clean,
            "dirty_entries": status_lines,
            "tracked_file_count": len(source_entries),
            "source_manifest_hash": source_manifest_hash,
            "manifest_algorithm": "sha256(path\\0file_sha256\\0size\\n)",
        },
        "artifacts": artifacts,
    }
    seal_hash = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    payload["seal"] = {
        "algorithm": "sha256",
        "canonical_payload_sha256": seal_hash,
    }

    output = Path(args.output).expanduser().resolve()
    rendered = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    atomic_write(output, rendered)
    atomic_write(output.with_suffix(output.suffix + ".sha256"), (sha256_file(output) + "\n").encode("ascii"))

    print(json.dumps({
        "output": str(output),
        "verification_result": verification_result,
        "git_commit": head,
        "source_manifest_hash": source_manifest_hash,
        "artifact_count": len(artifacts),
        "working_tree_clean": clean,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"seal failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
