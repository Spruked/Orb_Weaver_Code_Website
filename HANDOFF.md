# Code Weaver handoff — 2026-09-06, 09:52 CDT

User explicitly requested pausing implementation, updating DEVLOG.md, and leaving this handoff. **Resume the authorized work below; it is not complete.** No commits, pushes, or merges were made. Preserve the working tree.

## Workspace and services

- Canonical WSL repo: `/home/bryan/projects/Orb_Weaver_Code_Website`.
- Website: `127.0.0.1:41000`. Public hostname: `codeweaver.certsig.com`.
- Monitor: `127.0.0.1:18441`, **monitor-only**, never the public app port.
- User services: `orb-weaver-code.service`, `code-weaver-session-monitor.service`, `code-weaver-widget.service`; timer: `code-weaver-wham-usage.timer`.
- `cloudflared.service` and `spruked.service` were active; Spruked remains on 3001.
- User-service status was still active for website, widget, and monitor at handoff.
- A final monitor health request stalled; a bounded follow-up was started. Earlier verified health was OK with vault mirror OK and two editor windows. **Do not assume `systemctl is-active` proves current API responsiveness.** Check with `curl --max-time 5` first.
- Existing running Electron process predates the unfinished edits below. **Do not restart it blindly into the incomplete implementation.** The monitor process also predates the latest multi-editor changes. These are ordinary processes without automatic code reload.

## Completed and verified during this session

1. Website recovery:
   - System-wide website unit was missing and `.next/BUILD_ID` absent.
   - `npm run build` passed, including lint/type checking and 36 static pages.
   - Added `systemd/orb-weaver-code.service` (user service, loopback port 41000), installed to `~/.config/systemd/user/`, enabled and started.
   - Local homepage and local `/session-monitor` returned HTTP 200; public homepage changed from 502 to 200.
   - Recovery instructions added to `DEPLOYMENT.md`.
   - `sudo -n true` required interactive authentication. No sudo changes made. `loginctl show-user bryan -p Linger` was `Linger=no`; website starts with the user manager, not guaranteed before login.
   - Existing issue observed: public unauthenticated `/session-monitor` redirects to `https://localhost:41000/checkout` (307). Not fixed.
   - No `.env.local`/production account/payment configuration or SQLite application DB was set up. Don't claim commerce is configured.
2. Widget startup recovery:
   - Widget was crash-looping due to missing `$DISPLAY`, not merely starting.
   - `xdpyinfo` succeeded, then imported `DISPLAY WAYLAND_DISPLAY XDG_RUNTIME_DIR` into the systemd user manager and restarted the widget.
   - Widget became active. The imported display environment is session-local; persistent boot handling remains to be addressed.
3. VS Code window undercount:
   - `Get-Process Code | MainWindowHandle` returned one window for a process owning TWO editor windows.
   - Changed the Windows observer to use `EnumWindows`, `GetWindowThreadProcessId`, visibility, unowned-window filtering, and distinct HWND identity.
   - Restarted monitor/widget at that stage and explicitly observed:
     - PID 13524, HWND 394794: `README.md - Orb_Weaver_Code_Website [WSL: Ubuntu] - Visual Studio Code`
     - PID 13524, HWND 395074: `Dandy - Visual Studio Code`
   - Live `/health` reported `active_window_instances: 2`. Shared PID must never collapse distinct windows.
   - Updated `windows_desktop_test.py` to exercise two HWNDs sharing PID/start time, stable identity, disappearance, and failed-probe safety. Fixed its missing `window_instances.ensure_schema(storage)` setup. Test passed.
   - At that live check runtime session was `0ea4e4e5-5529-449b-a66b-a9f2e291aa84`; discover current ID instead of hardcoding it.

## User's expanded requirements (authoritative)

- Widget AND Electron dashboard must live in the **Windows system tray**, remain always on top when open, and be recoverable from the tray.
- Each detected editor/developer environment gets its OWN labeled widget. Two editor windows mean two widgets, including Windows and WSL windows. Closing/hiding one must not quit the whole application.
- Broader model is **developer activity**, not just VS Code:
  - Desktop IDEs: VS Code, Cursor, JetBrains family, Zed, Windsurf, Visual Studio, Android Studio, Eclipse, Sublime, Emacs; Xcode on macOS eventually.
  - Terminal/agents: Neovim/Vim, Codex CLI, Claude Code, Gemini CLI, Aider, Cline/Roo/Continue/OpenCode, custom agents.
  - Application/API processes: Python, Node, shell, Docker, Windows, WSL, SPRUKED apps including Orb Weaver and Dandy.
  - Remote environments: Codespaces, Gateway/JetBrains Remote, Coder/Gitpod/dev containers through reliable observation or explicit hooks.
- Separate optional/dedicated **API-token usage widget** for users monitoring their own API credentials.
- Provider order: **OpenAI, Anthropic, Google Gemini, xAI Grok**; adapters behind a common extensible ledger.
- Keep API usage separate from Codex/ChatGPT 5-hour/weekly subscription quota.
- Normalize provider, model, application/process, host, project, input/cache/output/reasoning/total tokens, request count, cost, rate-limit/quota metadata, timestamps, evidence source. Preserve provider-specific accounting fields.
- No invented token attribution when an editor hides API calls. No guessing a process consumes tokens merely because it exists.
- User authorized monitoring their own API credentials; no provider credentials have been read, created, sent, or written during this work.

## Unfinished working-tree implementation — NOT deployed

### `widget/main.js`

Replaced single `widgetWindow` with a `widgetWindows` Map and drafted:

- `reconcileWidgetWindows(instances)` creates/removes one window per identity, preserves existing/hidden windows, fallback global widget when none, plus API widget (default setting `apiUsageWidget: true`).
- Separate positions by slot and persisted `widgetBoundsByKey`; widget height increased to 230.
- `syncInstanceWidgets()` polls active runtime + existing `/vscode-windows?active_only=true` every 5s; serializes its own requests and preserves windows on API failure.
- Per-sender IPC lookup (`widgetEntryForSender`) for context/hide/open dashboard.
- Close/minimize hides windows; Quit lives in tray. Dashboard `skipTaskbar: true`; titles pinned for native helper matching.
- `createDashboardWindow(instanceId)` selects tab through query parameter or IPC.
- Shared monitor-summary cache to avoid multiplying expensive fetches per widget.
- Tray actions for all widgets and each widget, dashboard, evidence, quit.
- Starts the new Windows desktop helper under WSL; native Electron Tray elsewhere.

**Known gaps to finish/review:**

- API widget calls `GET /api-usage/summary`, but that endpoint does NOT yet exist.
- Dashboard has no API-usage tab/view yet. Selecting `api-usage` falls back to Global.
- CLI/application/remote activity registry and aggregation with window widgets are NOT implemented. Current polling still only reads existing desktop-window records.
- User-selectable visibility/API-widget option needs complete native and Electron tray UI; boolean exists but no toggle yet.
- Review single-instance lock path, shutdown ordering, late async window creation during quit, hidden/minimized restoration, collision-free positions at higher counts, duplicate labels, and all leftover single-widget references.
- `saveSessionOnClose` is existing behavior that ends shared runtime on app quit; consider runtime ownership before changing it.
- Full lifecycle and Electron UI smoke tests are NOT yet written/run for the new implementation.

### `widget/wsl-desktop.js` (new)

- Spawns Windows PowerShell in STA/hidden mode using argument vector and base64-encoded local script.
- JSON over stdin: widget titles/IDs/labels/visibility and dashboard state; heartbeat every 5s.
- JSON over stdout: tray actions, ready event, native HWND style diagnostics.
- Auto-retry/backoff on helper exit. EOF stops helper, with heartbeat timeout fallback.
- No monitor control HTTP port exposed for tray actions.

### `widget/windows-tray.ps1` (new)

- Embedded C# WinForms `NotifyIcon` and per-widget `ContextMenuStrip`.
- Teal CW icon drawn locally; no image generation dependency.
- Matches only exact Code Weaver titles (allowing WSLg distro suffix) owned by `msrdc`/`mstsc`.
- Sets Windows `HWND_TOPMOST`, `WS_EX_TOOLWINDOW`, clears `WS_EX_APPWINDOW`; does not activate/move/resize windows.
- Only applies to visible targets, checks styles before setting, polls every 500ms.
- Tray removed on EOF or 20s heartbeat expiry; disposes resources.
- **A standalone real Windows smoke probe passed:** temporarily used the currently running old widget/dashboard titles; logged `ready` and both HWNDs with `topmost: true`, `skipTaskbar: true`, then exited 0 after stdin closed. It is not a persistent running helper yet.
- Current old widget/dashboard native styles were changed by that test (authorized topmost/taskbar behavior).
- PowerShell emitted harmless first-use progress CLIXML on stderr; suppress with `$ProgressPreference = 'SilentlyContinue'` if appropriate.
- Needs actual tray click/menu, relaunch/cleanup, and integration verification. Consider robust handling of broken stdout, timer exceptions, stale HWNDs, and duplicate/multi-distro titles.

### Renderer changes

- `widget/preload.js`: context/API usage IPC and dashboard selection listener added.
- `widget/widget.html`: per-instance header; shared quota labeled; X now hides to tray; API mode renders daily UTC input/output/request/cost metadata; polling uses serialized `setTimeout` loop.
- `widget/dashboard.html`: initial tab from query and IPC tab selection. API/activity UI still missing.

### `session_monitor/windows_desktop.py`

- After the proven two-window fix, drafted generalized configurable editor process detection (`DEFAULT_EDITOR_PROCESSES`, `CODE_WEAVER_EDITOR_PROCESSES`). Covers native Windows editor processes including Code/Insiders, Cursor, Windsurf, Zed, Visual Studio, JetBrains variants, Android Studio, Eclipse, Emacs, Sublime, gVim.
- Added editor-name/process-name columns and metadata to records. Retains existing `vscode_windows` storage/routes/source names for compatibility.
- Live read-only direct probe with this latest code returned both correct VS Code windows and editor metadata. Lifecycle test passed.
- This latest generalization is not loaded into the running monitor yet.
- Module/docs still contain some VS-Code-only wording. No automatic macOS, terminal-editor, Linux-native/X11, or remote discovery added. Be honest about support boundaries.

### `session_monitor/api_usage.py` (new, not imported by server)

- Draft adapters: OpenAI Responses/Chat Completions, Anthropic, Gemini camel/snake usage fields, xAI.
- Metadata-only input; completed requests; API billing mode; required request/model/source; optional application/process/host/project/environment/window/account reference.
- Normalized token counts retain null unknowns; provider breakdowns sanitized to numeric accounting fields/enums.
- Provider-specific semantics:
  - OpenAI cached/reasoning are subsets, not additive.
  - Anthropic total input = uncached + cache read + cache creation.
  - Gemini normalized output includes candidates + thoughts; preserve provider total separately.
  - xAI exact cost from `cost_in_usd_ticks / 10**10`; other absent costs remain unknown.
- `UsageLedger`: own `api_usage.db` SQLite append-only records, request-ID deduplication, conflict rejection, immutable triggers, persistent evidence-mirror outbox, UTC-day summaries/groups/recent records and partial/unknown cost coverage.
- **NOT tested behaviorally, NOT instantiated, NO routes, NO live usage ingested, NO provider connection.**
- Review adapter malformed input validation (`dict` shapes), token consistency, cost provenance, dedup scoping/account references, partial/streaming records, quota/header validation, privacy sanitization, mirror retry semantics, scaling/memory, query validation, and null/partial summaries before enabling.
- No scripts/SDK usage reporter or ingestion hook exists yet. No automatic provider/account polling exists.

## Suggested next implementation order

1. Read this handoff and diff; verify current service health with bounded requests. Preserve unrelated website recovery and proven window-count fix.
2. Finish API/activity back end before restarting new UI:
   - expose validated metadata-only ingest + read-only summary routes;
   - explicit environment registration/heartbeat/close for CLI/agent/app/remote contexts, distinguish activity kind from actual visible windows;
   - Python/Node reporting helpers that extract usage metadata from completed responses, never send keys/content, and support explicit environment/window identity;
   - optional `code-weaver-run` wrapper to register real child processes and provide reporter environment variables; no fabricated process/token mapping;
   - provider extensibility and test fixtures for all four providers, unknowns, duplicates, conflicts, cost and privacy.
3. Finish API/activity dashboard tab and per-instance UI selection; wire native and Electron tray visibility/settings consistently.
4. Add deterministic widget lifecycle tests (2 same-PID windows, add/remove, hidden stays hidden, close-to-tray, individual Dashboard routes, monitor outage, API placeholder).
5. Test native helper/menu and Electron UI live; restore services after controlled tests. Verify Windows topmost flags and tray icon, not only Electron `isAlwaysOnTop()` (WSLg ignored prior hints).
6. Fix persistent WSLg display environment startup in canonical installer/unit as needed; do not rerun whole installer gratuitously because it restarts monitor/session state.
7. Restart only completed/tested components, verify live two editor widgets plus API widget and dashboard/tray, then update DEVLOG.md/HANDOFF.md with evidence.

## Verification / commands

```bash
cd /home/bryan/projects/Orb_Weaver_Code_Website
git status --short
curl --max-time 5 -fsS http://127.0.0.1:18441/health
systemctl --user status code-weaver-session-monitor.service code-weaver-widget.service orb-weaver-code.service --no-pager
python3 session_monitor/windows_desktop_test.py
python3 -m py_compile session_monitor/api_usage.py session_monitor/windows_desktop.py
node --check widget/main.js
node --check widget/wsl-desktop.js
node --check widget/preload.js
git diff --check
```

Earlier syntax checks for main.js/wsl-desktop.js passed before the last renderer/cache edits. Final checks were started during handoff; record their actual results, don't infer success from this command list.

## Official accounting/native API references already consulted

- https://developers.openai.com/api/reference/typescript/resources/beta/subresources/responses/methods/create
- https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- https://ai.google.dev/api/generate-content#UsageMetadata
- https://docs.x.ai/developers/cost-tracking
- https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowpos
- https://learn.microsoft.com/en-us/dotnet/api/system.windows.forms.notifyicon
- https://github.com/microsoft/wslg/issues/158 (Windows tray integration gap)

OpenAI credential and docs skills were read. The monitor/reporting path so far makes **no provider API calls** and needs no provider keys. Follow credential rules if adding real authenticated provider polling or proxying; do not create or copy keys implicitly. No subagents were used; current developer instructions prohibit proactive delegation.
