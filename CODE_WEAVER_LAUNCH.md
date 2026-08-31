# Code Weaver Launch Runbook

This is the shortest supported local path for the Code Weaver runtime.
Chrome DevTools MCP repair is a separate workstream and is not required for
this runtime/session proof.

## Install / refresh user services

From the repository root:

```bash
bash scripts/install-code-weaver.sh
```

The installer:

- detects the repository path instead of assuming `/home/bryan/...`;
- creates a persistent user-level Session Monitor service;
- creates a persistent Electron widget service;
- starts the monitor first and verifies `127.0.0.1:18441/health`;
- starts/restarts the widget;
- installs `~/.local/bin/code-weaver-code` for tracked VS Code windows.

The supported Windows + WSL path is to run these services inside WSL/WSLg so
the widget and monitor share WSL localhost. This avoids manual WSL VM-IP
configuration in the normal installation path.

## Open tracked VS Code windows

```bash
code-weaver-code /path/to/workspace
```

If no path is supplied, the current working directory is used.

Each invocation registers a distinct VS Code child-window record beneath the
single active Code Weaver runtime session. Closing that VS Code window closes
only its child record.

## Runtime verification

```bash
curl -fsS http://127.0.0.1:18441/health
python3 session_monitor/runtime_lifecycle_test.py
python3 session_monitor/stress_evidence_test.py
```

The lifecycle proof checks:

- health;
- fresh runtime session creation;
- two distinct VS Code child IDs;
- closing one child while the other remains active;
- persistent primary evidence;
- vault mirror output;
- forced-kill recovery as `unclean`;
- fresh runtime session creation after recovery.

The stress proof checks sustained and concurrent evidence writes, cached source
hashes, streaming tail reads, truncated-tail recovery, and vault mirror counts.

## Shared plan limits

Code Weaver treats the provider fields as shared plan-limit evidence:

- raw `primaryUsedPercent` -> **5-hour used %**;
- raw `secondaryUsedPercent` -> **Weekly used %**.

Remaining percentage is a **DERIVED** value (`100 - used`). Code Weaver does
not derive quota from wall-clock time. An observed `usage_limit_exceeded` event
remains independent evidence and is never suppressed because a percentage
surface disagrees with it.

## Release/source sealing

Create a source seal:

```bash
python3 scripts/seal-code-weaver-release.py
```

Seal one or more actual release artifacts:

```bash
python3 scripts/seal-code-weaver-release.py \
  --release-id CW-YYYYMMDD-001 \
  --version X.Y.Z \
  --artifact /path/to/installer-or-archive
```

The seal records:

- exact Git HEAD and branch;
- clean/dirty working-tree state;
- SHA-256 for every tracked source file folded into a source-manifest hash;
- SHA-256 and size for every explicitly supplied artifact;
- a canonical payload seal and file-hash sidecar.

Read-only verification is exposed at:

```bash
curl -fsS http://127.0.0.1:18441/release/evidence
```

A dirty tree does **not** become a clean release. Missing artifacts do **not**
become available. Tamper/hash failures remain visible.

## Current production boundary

These runtime/session hardening items can be tested independently of the still
separate toolchain work. `tools/chrome-devtools-mcp`, `tools/mcp_server`, and
`tools/visidata` must retain their own implementation/proof status and must not
be silently promoted to `PROVEN_RUNNING` by this runbook.
