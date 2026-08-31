"""Read and verify locally sealed Code Weaver release evidence."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_PATH = (
    REPO_ROOT / "code_weaver_vault" / "runtime" / "release_evidence" / "current.json"
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _git_head() -> Optional[str]:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def evidence_path() -> Path:
    return Path(os.environ.get("CODE_WEAVER_RELEASE_EVIDENCE_PATH", DEFAULT_EVIDENCE_PATH))


def read_verified_release_evidence() -> dict:
    path = evidence_path()
    if not path.is_file():
        return {
            "status": "unavailable",
            "verification_result": "NO_SEALED_RELEASE_EVIDENCE",
            "path": str(path),
        }

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "invalid",
            "verification_result": "RELEASE_EVIDENCE_UNREADABLE",
            "path": str(path),
            "error": f"{type(exc).__name__}: {exc}",
        }

    if not isinstance(payload, dict):
        return {
            "status": "invalid",
            "verification_result": "RELEASE_EVIDENCE_INVALID_SHAPE",
            "path": str(path),
        }

    verification: dict = {
        "evidence_file_sha256": None,
        "sidecar_matches": None,
        "canonical_payload_matches": None,
        "current_head_matches": None,
        "artifact_checks": [],
    }

    try:
        file_hash = _sha256_file(path)
        verification["evidence_file_sha256"] = file_hash
        sidecar = path.with_suffix(path.suffix + ".sha256")
        if sidecar.is_file():
            expected = sidecar.read_text(encoding="ascii", errors="replace").strip().split()[0]
            verification["sidecar_matches"] = expected == file_hash
    except OSError:
        pass

    seal = payload.get("seal") if isinstance(payload.get("seal"), dict) else {}
    expected_canonical = seal.get("canonical_payload_sha256")
    unsigned = dict(payload)
    unsigned.pop("seal", None)
    actual_canonical = hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()
    verification["canonical_payload_matches"] = (
        expected_canonical == actual_canonical if expected_canonical else None
    )

    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    sealed_head = source.get("git_commit")
    current_head = _git_head()
    verification["sealed_head"] = sealed_head
    verification["current_head"] = current_head
    verification["current_head_matches"] = (
        sealed_head == current_head if sealed_head and current_head else None
    )

    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        artifact_path = Path(str(artifact.get("path") or ""))
        expected_hash = artifact.get("sha256")
        check = {
            "filename": artifact.get("filename") or artifact_path.name,
            "path": str(artifact_path),
            "exists": artifact_path.is_file(),
            "sha256_matches": None,
        }
        if artifact_path.is_file() and expected_hash:
            try:
                check["sha256_matches"] = _sha256_file(artifact_path) == expected_hash
            except OSError:
                check["sha256_matches"] = False
        verification["artifact_checks"].append(check)

    required_checks = [
        verification.get("canonical_payload_matches"),
        verification.get("sidecar_matches"),
    ]
    artifact_checks = verification["artifact_checks"]
    if artifact_checks:
        required_checks.extend(check.get("sha256_matches") for check in artifact_checks)

    tamper_detected = any(value is False for value in required_checks)
    if tamper_detected:
        runtime_verification = "SEAL_VERIFICATION_FAILED"
    elif verification.get("current_head_matches") is False:
        runtime_verification = "SEALED_SOURCE_DIFFERS_FROM_CURRENT_HEAD"
    elif payload.get("verification_result") == "SEALED_RELEASE_EVIDENCE":
        runtime_verification = "SEALED_RELEASE_EVIDENCE_VERIFIED"
    else:
        runtime_verification = str(payload.get("verification_result") or "SOURCE_EVIDENCE_PRESENT")

    return {
        "status": "observed",
        "path": str(path),
        "verification_result": runtime_verification,
        "sealed_verification_result": payload.get("verification_result"),
        "release_id": payload.get("release_id"),
        "version": payload.get("version"),
        "generated_at": payload.get("generated_at"),
        "source": source,
        "artifacts": artifacts,
        "verification": verification,
    }
