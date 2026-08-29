"""
git_monitor.py

Read-only Git snapshots for the workspace panel and evidence correlation.
Git porcelain's two status columns are preserved exactly so unstaged changes
cannot be misreported as staged changes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


def _run(args: list[str], cwd: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Do not strip leading whitespace: `git status --porcelain` uses it
        # as part of the XY status contract.
        return result.stdout.rstrip("\r\n") if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def snapshot(cwd: Path) -> dict:
    root = _run(["rev-parse", "--show-toplevel"], cwd)
    if root is None:
        return {
            "is_repo": False,
            "repo_root": None,
            "branch": None,
            "head": None,
            "remote": None,
            "remote_host": None,
            "modified_files": None,
            "untracked_files": None,
            "staged_files": None,
            "ahead": None,
            "behind": None,
        }

    root_path = Path(root)
    branch = _run(["rev-parse", "--abbrev-ref", "HEAD"], root_path)
    head = _run(["rev-parse", "--short", "HEAD"], root_path)
    remote = _run(["config", "--get", "remote.origin.url"], root_path)

    remote_host = None
    if remote:
        cleaned = remote.replace("git@", "").replace("https://", "").replace("http://", "")
        remote_host = cleaned.split("/")[0].split(":")[0] if cleaned else None

    status = _run(["status", "--porcelain=v1", "--untracked-files=all"], root_path) or ""
    modified = 0
    untracked = 0
    staged = 0
    for line in status.splitlines():
        if len(line) < 2:
            continue
        x, y = line[0], line[1]
        if x == "?" and y == "?":
            untracked += 1
            continue
        if x not in {" ", "?"}:
            staged += 1
        if y not in {" ", "?"}:
            modified += 1

    ahead_behind = _run(
        ["rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
        root_path,
    )
    ahead, behind = None, None
    if ahead_behind:
        parts = ahead_behind.split()
        if len(parts) == 2:
            try:
                ahead, behind = int(parts[0]), int(parts[1])
            except ValueError:
                ahead, behind = None, None

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
    """Working-tree diff stats relative to a Git ref.

    This is correlation evidence only: it means files changed during a known
    interval, not that a particular tool authored every changed line.
    """
    out = _run(["diff", "--shortstat", since_ref], cwd)
    if not out:
        return {"files_changed": 0, "insertions": 0, "deletions": 0}

    files_changed = insertions = deletions = 0
    for token in out.split(","):
        token = token.strip()
        try:
            value = int(token.split()[0])
        except (ValueError, IndexError):
            continue
        if "file" in token:
            files_changed = value
        elif "insertion" in token:
            insertions = value
        elif "deletion" in token:
            deletions = value
    return {
        "files_changed": files_changed,
        "insertions": insertions,
        "deletions": deletions,
    }
