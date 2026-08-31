# Code Weaver Dev Log

This file preserves working context for future restarts, crashes, or handoffs.
Keep it current whenever a meaningful implementation or verification boundary changes.

## 2026-08-31 — GitHub hardening pass

### Completed

- Corrected the corner widget quota labels to **5-Hour Limit · Used** and **Weekly Limit · Used** instead of ambiguous Primary/Secondary presentation.
- Hardened `session_monitor/evidence.py` for long-running sessions:
  - streaming JSONL reads instead of loading the full combined evidence file;
  - cached per-session source-record hashes for duplicate suppression;
  - thread-safe append operations;
  - optional fsync mode;
  - tolerance for a truncated final JSONL line after a crash;
  - vault mirror failures no longer break the primary evidence write.
- Hardened `session_monitor/correlation.py`:
  - shared plan-limit terminology;
  - explicit USED semantics and DERIVED remaining percentages;
  - token attribution stays OBSERVED when a token record carries a turn ID;
  - a missing turn ID is only DERIVED when the nearest turn-bearing records before and after it in the same rollout source carry the same turn ID;
  - one-sided/timing guesses remain UNATTRIBUTED;
  - session statistics are calculated over the full session while only the requested tail is displayed.
- Hardened `session_monitor/vault_bridge.py`:
  - stopped rewriting the vault runtime manifest for every evidence event;
  - stopped rereading `glyph_map.json` for every evidence event;
  - cached runtime/glyph state;
  - serialized vault writes;
  - added optional fsync mode.
- Added reproducible release/source evidence sealing:
  - `scripts/seal-code-weaver-release.py` records exact HEAD, branch, dirty state, tracked-file source manifest hash, explicit artifact hashes/sizes, canonical payload hash, and a file-hash sidecar;
  - a dirty source tree cannot be promoted to a clean sealed release;
  - missing artifacts remain unavailable.
- Added `session_monitor/release_evidence.py` and read-only `GET /release/evidence` verification.
  - verifies the seal sidecar and canonical payload;
  - compares sealed HEAD to current HEAD;
  - verifies explicitly supplied artifact hashes;
  - reports verification failures/mismatches instead of reconciling them.
- Updated `session_monitor/server.py`:
  - `/codex/quota` now preserves raw provider fields and also exposes explicit shared `five_hour` and `weekly` objects;
  - remaining percentages are labeled DERIVED;
  - health exposes vault mirror degradation;
  - `/release/evidence` exposes verified sealed evidence.
- Added `scripts/install-code-weaver.sh` as the supported one-command local installer.
  - detects the repository path dynamically;
  - generates persistent user-level monitor and widget services;
  - starts the monitor before the widget and checks health;
  - installs `~/.local/bin/code-weaver-code`;
  - refuses to fetch missing runtime dependencies from the network;
  - resolves the actual local Python/npm executable paths rather than assuming `/usr/bin`.
- Updated `scripts/code-weaver-vscode-session.sh` to be path-portable and to use the requested workspace/current directory.
- Added `session_monitor/stress_evidence_test.py` to exercise sustained writes, concurrent writers, hash caching, streaming tails, truncated-tail recovery, and vault mirror counts.
- Added `CODE_WEAVER_LAUNCH.md` with the install, tracked-window, lifecycle proof, stress proof, quota semantics, and release-sealing procedures.

### Not Yet Proven On The User Machine

- The new GitHub hardening pass must still be pulled locally and run through:
  - Python syntax/import checks;
  - `runtime_lifecycle_test.py`;
  - `stress_evidence_test.py`;
  - the one-command installer;
  - actual monitor/widget restart behavior.
- The Electron full dashboard still contains legacy Primary/Secondary wording in some fields; the corner widget is corrected and the API semantics are corrected. Dashboard presentation cleanup must not change the evidence semantics.
- The release verifier is available through the API; the control-plane display still needs to prefer verified `/release/evidence` over the legacy placeholder manifest when a seal exists.

### Separate / Still Paused

- Do not resume Chrome DevTools MCP repair in this workstream.
- `tools/chrome-devtools-mcp` remains `PRESENT_NOT_PROVEN`.
- `tools/mcp_server` and `tools/visidata` remain required/pending.

## 2026-08-31 06:05:56 -0500

### Completed

- Updated `widget/main.js` so the Electron widget owns a fresh monitor session lifecycle.
- On widget open:
  - starts or verifies the Session Monitor API;
  - checks for an existing active session;
  - collects one final evidence pass for the existing active session;
  - ends the existing active session;
  - creates a new `electron-widget-startup` session;
  - collects an initial evidence pass for the fresh session.
- On widget close/quit:
  - prevents immediate quit once;
  - collects final evidence for the active/widget session;
  - ends the session through `POST /sessions/{id}/end`;
  - then quits normally.
- Added `systemd/code-weaver-widget.service`.
  - User-level Electron widget service.
  - Uses `Restart=always` and `RestartSec=5`.
  - Starts from local repo path `widget` with `npm start`.
- Added `scripts/install-code-weaver-user-services.sh`.
  - Installs/enables the persistent widget service.
  - Installs/enables the fresh VS Code session service.
  - Restarts the widget service after install.
- Updated `README.md` and `DEPLOYMENT.md` to point to the user-service installer.

### Verified

- `node --check widget/main.js` completed successfully.
- `bash -n scripts/install-code-weaver-user-services.sh scripts/code-weaver-vscode-session.sh` completed successfully.
- `systemd-analyze verify --user systemd/code-weaver-widget.service systemd/code-weaver-vscode-session.service` completed successfully.

### Notes

- This assures code-level reset/save behavior and service-level auto-restart configuration.
- The user service still must be installed/enabled on the actual desktop user session before reboot persistence is active.
- No Chrome DevTools MCP repair was resumed.
- No Orb Weaver repository files were touched.

## 2026-08-31 06:04:54 -0500

### Completed

- Updated `widget/main.js` so Electron topmost behavior is actively enforced for both the corner widget and the full dashboard window.
- Added a shared `enforceWindowTopmost()` helper.
- Reasserted always-on-top on `ready-to-show`, `show`, `focus`, `blur`, `restore`, and widget `move`.
- Added a 2-second topmost enforcement interval while the widget app is running.
- Cleared the topmost interval during `before-quit`.

### Verified

- `node --check widget/main.js` completed successfully.

### Notes

- This was a widget-only change.
- No Chrome DevTools MCP repair was resumed.
- No Orb Weaver repository files were touched.

## 2026-08-31 06:01:22 -0500

### Completed

- Confirmed the active repository is `/home/bryan/projects/Orb_Weaver_Code_Website`.
- Stopped work in `/home/bryan/projects/Orb_Weaver`; this task is Code Weaver, not Orb Weaver.
- Renamed the vault template folder from `Vault-Logic-System-Template/` to `code_weaver_vault/`.
- Removed the vault template's nested `.git` metadata before the user clarified not to remove anything else. The vault contents remain as normal files in this repository.
- Kept `tools/chrome-devtools-mcp/` as a required local tool inside this repo.
- Added `tsconfig.json` excludes for `tools/**` and `code_weaver_vault/**` so the Next.js website build does not type-check vendored/tool/template internals.
- Added `session_monitor/vault_bridge.py`.
  - Mirrors Session Monitor evidence into `code_weaver_vault/runtime`.
  - Creates runtime folders for sessions, memory, telemetry, glyphs, and archive.
  - Writes append-only JSONL event, telemetry, memory, and glyph trace records.
  - Uses existing vault glyph definitions from `code_weaver_vault/glyphs/glyph_map.json` when possible.
- Updated `session_monitor/evidence.py` so every appended `EvidenceEvent` is also mirrored into the vault bridge when available.
- Updated `session_monitor/storage.py`.
  - Ensures vault runtime directories exist when the monitor starts.
  - Closes stale open sessions on monitor startup using a `session_autosaved_on_startup` evidence event.
  - Mirrors session metadata to the vault on session start, explicit session end, and autosave-on-startup.
  - Added `active_session()`.
- Updated `session_monitor/server.py`.
  - Added read-only `GET /sessions/active`.
- Added startup/runtime support files:
  - `systemd/code-weaver-session-monitor.service`
  - `systemd/code-weaver-vscode-session.service`
  - `scripts/code-weaver-vscode-session.sh`
- Updated `setup.sh`.
  - Installs/enables/restarts the Code Weaver Session Monitor service alongside the website service.
- Updated `deploy.sh`.
  - Restarts the Session Monitor service during deploy when that service is installed.
- Updated `README.md` and `DEPLOYMENT.md` with monitor service, vault mirror, and fresh VS Code session startup instructions.

### Verified

- `npm run build` from the repo root completed successfully after excluding `tools/**` and `code_weaver_vault/**` from the website TypeScript build.
- `python3 -m py_compile session_monitor/*.py` completed successfully.
- `tools/chrome-devtools-mcp/` has no nested `.git` directory detected by `find tools/chrome-devtools-mcp -maxdepth 2 -type d -name .git`.

### Current Status

- Website build status: passing.
- Session Monitor Python syntax status: passing.
- Vault integration status: implemented in the current patch, not yet runtime-tested through a live monitor session after restart.
- Chrome DevTools MCP status: `PRESENT_NOT_PROVEN`.
- Code Weaver overall production status: not production-complete yet.

### Important Findings

- `tools/chrome-devtools-mcp` source is present, but its local production runtime is incomplete.
- `npm run build` inside `tools/chrome-devtools-mcp` failed because `third_party/devtools-frontend` is incomplete and missing:

```text
front_end/third_party/acorn/package/dist/acorn.mjs
```

- Per `session_monitor/WATCHER_SPEC.md`, Chrome DevTools MCP must not be worked around with `npx`, runtime downloads, package registry fallback, GitHub fetch at runtime, CrUX, telemetry endpoints, or update checks.
- A controlled development/build phase may repair vendored payloads, but that must remain separate from the vault/session-lifecycle patch.
- `tools/TOOLCHAIN_LOCK.json` still marks these required toolchain pieces as pending:
  - `tools/mcp_server`
  - `tools/visidata`
- Therefore Code Weaver must not be described as production-complete yet.

### Interrupted/Stopped Work

- A Chrome DevTools MCP repair attempt was started with `npm run sync` inside `tools/chrome-devtools-mcp`.
- It was stopped after the user clarified that Chrome repair must stay separate from the vault/session patch.
- The command exited with code `130`.
- Do not assume Chrome DevTools MCP repair completed.

### Next Safe Steps

1. Pull the GitHub hardening pass and run the launch runbook tests.
2. Keep Chrome DevTools MCP repair separate.
3. After the runtime tests pass, finish the remaining Electron dashboard presentation wiring for verified release evidence and shared-plan labels.
4. Implement or vendor the still-required `tools/mcp_server` and `tools/visidata` paths as separate evidence/toolchain work.
