# Session Monitor / Code Cipher Widget

Electron control-plane UI for the integrated Orb Weaver Code Cipher + Session Monitor system.

The widget is intentionally split into two views:

- **corner widget** — always-on-top Codex primary/secondary quota status
- **full local dashboard** — session controls, Git/workspace state, token evidence, reload/IPC correlation, Code Cipher release evidence, and source health

## Local services

The Electron app uses the local Session Monitor API at:

```text
http://127.0.0.1:18441
```

On launch, the Electron main process checks `/health`. If the monitor API is not already running, it starts:

```text
session_monitor/server.py
```

The optional Next.js dashboard remains available at:

```text
http://127.0.0.1:3000/session-monitor
```

The Electron full-dashboard action opens `dashboard.html` directly and does **not** require the Next.js server.

## Run

From the repository root:

```bash
cd widget
npm install
npm start
```

The app remains resident in the tray when its windows are hidden.

## Session evidence collection

A monitor session must exist before Codex/VS Code evidence is attributed to it. Use **Start Session** in the full dashboard.

While an active session exists, the Electron process performs an evidence collection pass every 15 seconds:

1. observe the latest Codex quota line
2. ingest new Codex rollout records inside the session time bounds
3. scan VS Code/Codex logs for new reload or IPC/reset evidence

Ingestion is cursor-based and duplicate source records are suppressed. Dashboard `GET` requests are read-only and do not create evidence.

Manual controls remain available for explicit collection/testing:

- Start Session
- End Session
- Scan VS Code
- Ingest Codex
- Scan Code
- tray action: **Collect Evidence Now**

## Evidence separation

The dashboard presents two independent evidence streams side by side:

- **Session Monitor evidence** — runtime/session/Codex/Git/VS Code telemetry
- **Code Cipher evidence** — protected artifact/release manifest evidence

The correlation view compares them. It must display mismatches rather than silently reconciling them.

## Quota semantics

The widget deliberately labels the two provider values separately as Codex primary and secondary quota. It does not calculate quota from elapsed wall-clock time.

Rate-window metadata and usage-limit errors are taken only from observed Codex telemetry when available. Unknown values remain unknown.

## Settings

Electron persists local settings in its user-data directory as:

```text
widget-settings.json
```

Settings include:

- monitor API base URL
- optional web-dashboard URL
- workspace path
- widget position
- click-through state
- polling interval

## WSL / Windows localhost

If Electron is running on Windows and the monitor server is running in WSL, first confirm localhost forwarding:

```powershell
curl http://127.0.0.1:18441/health
```

If forwarding is unavailable, use the WSL VM IP returned by:

```bash
wsl hostname -I
```

and set `apiBase` in `widget-settings.json` accordingly.

## Privacy / evidence rule

The Session Monitor records normalized telemetry and provenance. It should not duplicate raw prompt/response/source payloads into its evidence ledger by default. Source records are identified with path/position and SHA-256 evidence identities where supported.
