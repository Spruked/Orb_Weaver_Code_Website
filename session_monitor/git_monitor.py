"""
git_monitor.py

Read-only git state snapshots for the Workspace panel and for before/after
change attribution around a Codex turn. Everything here shells out to git
itself rather than parsing .git internals, so it stays correct across git
versions.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


def _run(args: list[str], cwd: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def snapshot(cwd: Path) -> dict:
    """Full workspace/git panel snapshot for a given path."""
    root = _run(["rev-parse", "--show-toplevel"], cwd)
    if root is None:
        return {
            "is_repo": False, "repo_root": None, "branch": None, "head": None,
            "remote": None, "remote_host": None, "modified_files": None,
            "untracked_files": None, "staged_files": None, "ahead": None, "behind": None,
        }

    root_path = Path(root)
    branch = _run(["rev-parse", "--abbrev-ref", "HEAD"], root_path)
    head = _run(["rev-parse", "--short", "HEAD"], root_path)
    remote = _run(["config", "--get", "remote.origin.url"], root_path)

    remote_host = None
    if remote:
        # crude host extraction, handles both https and ssh remote forms
        cleaned = remote.replace("git@", "").replace("https://", "").replace("http://", "")
        remote_host = cleaned.split("/")[0].split(":")[0] if cleaned else None

    status = _run(["status", "--porcelain"], root_path) or ""
    modified = sum(1 for l in status.splitlines() if l[:2].strip() and l[0] in "MRC")
    untracked = sum(1 for l in status.splitlines() if l.startswith("??"))
    staged = sum(1 for l in status.splitlines() if l[:1] in "MADRC" and l[:1] != " ")

    ahead_behind = _run(["rev-list", "--left-right", "--count", "HEAD...@{upstream}"], root_path)
    ahead, behind = None, None
    if ahead_behind:
        parts = ahead_behind.split()
        if len(parts) == 2:
            ahead, behind = parts[0], parts[1]

    return {
        "is_repo": True,
        "repo_root": root,
        "branch": branch,
        "head": head,
        "remote": remote,
        "remote_host": remote_host,
        "modified_files": modified,
        "untracked_files": untracked,
        "staged_files": staged,
        "ahead": ahead,
        "behind": behind,
    }


def diff_stat(cwd: Path, since_ref: str = "HEAD") -> Optional[dict]:
    """Change attribution since a given ref — files touched, lines added/
    removed. Used to label 'files changed during Codex working interval'
    rather than attributing authorship directly."""
    out = _run(["diff", "--shortstat", since_ref], cwd)
    if not out:
        return {"files_changed": 0, "insertions": 0, "deletions": 0}

    files_changed = insertions = deletions = 0
    for token in out.split(","):
        token = token.strip()
        if "file" in token:
            files_changed = int(token.split()[0])
        elif "insertion" in token:
            insertions = int(token.split()[0])
        elif "deletion" in token:
            deletions = int(token.split()[0])
    return {"files_changed": files_changed, "insertions": insertions, "deletions": deletions}
