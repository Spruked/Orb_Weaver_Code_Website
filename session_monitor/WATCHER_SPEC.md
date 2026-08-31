# Watcher Evidence Architecture

## Purpose

Watcher is the provider-neutral observability and fairness subsystem inside Orb Weaver Code Cipher.

Its purpose is to preserve enough independently observable evidence for users and providers to determine what happened during an LLM-assisted work session and where reported usage, reliability, context continuity, and delivered work may not line up.

Watcher is not a limit-evasion system, refund engine, or accusation engine.

Core doctrine:

> Watcher reports what was OBSERVED, what was DERIVED from observations, what was INFERRED, and what was UNAVAILABLE. It never promotes inference into fact.

## Local-tool rule

Watcher does not use provider-adapter or observer-adapter layers for first-party system tooling.

The product toolchain lives inside the repository and ships with the product. The first-party MCP server coordinates the local tools directly.

Canonical repository layout:

```text
tools/
  mcp_server/                 # first-party system MCP server
  chrome-devtools-mcp/        # vendored official Chrome DevTools MCP source/build
  visidata/                   # vendored VisiData source/runtime
  TOOLCHAIN_LOCK.json         # pinned upstream provenance
```

The same local tool layout is required in both:

- `Spruked/Orb_Weaver_Code_Website`
- `Spruked/Orb_Weaver`

Chrome DevTools MCP and VisiData are system tools, not optional cloud integrations. They are used in unison with the first-party MCP server.

### No-cloud runtime rule

After installation/deployment, core operation must not require:

- npm or another package registry
- PyPI or another Python package index
- GitHub or another source host
- a hosted MCP server
- CrUX
- tool usage telemetry endpoints
- automatic upstream update checks
- a package download performed at process startup

Forbidden runtime patterns include `npx ...@latest`, runtime `git clone`, runtime `pip install`, and equivalent network acquisition.

Source acquisition and dependency resolution happen during controlled development/release preparation. The resulting release/deployment bundle contains the local tool code, required runtime dependencies/build output, licenses, provenance, and hashes.

Do not use Git submodules for required deployed tools: an archive/download must contain the actual tool files without a second fetch. A vendored snapshot or Git subtree is preferred.

## Local toolchain

### First-party MCP server

The first-party MCP server is the local coordination layer. Chrome DevTools MCP, VisiData, and subsequent system tools sit beside it under `tools/` and are invoked locally through that system MCP/tool layer.

Watcher records the resulting evidence. It does not need a second abstraction layer that merely renames those tools as adapters.

### Chrome DevTools MCP

Use the official `ChromeDevTools/chrome-devtools-mcp` source as a pinned in-repository tool.

Required runtime policy:

- local executable/build only
- no `@latest`
- usage statistics disabled
- CrUX disabled
- update checks disabled
- sensitive network-header redaction enabled where supported
- connect only to explicitly authorized local Chrome targets
- preserve upstream Apache-2.0 license/notices

Watcher may use Chrome DevTools evidence for network timing/status, console/runtime faults, page/target lifecycle, reloads, navigation, and performance behavior.

Chrome evidence does not establish hidden provider accounting or authoritative LLM context state unless the provider explicitly exposes those facts through the observed channel.

### VisiData

VisiData is a pinned in-repository local analysis tool used to inspect Watcher/Orb Weaver evidence and structured exports.

VisiData is GPL-3.0 software. Keep the upstream source and license intact in its vendored directory and deployment. Treat it as a separate local program/tool invoked by the system rather than copying GPL implementation code into proprietary first-party modules without a separate licensing review.

## Evidence classes

- `OBSERVED` — directly emitted by a provider, IDE, runtime, OS, browser/DevTools channel, log, API response, or process.
- `DERIVED` — deterministic calculation over observed records.
- `INFERRED` — a defensible interpretation of multiple observed signals.
- `MANUAL` — user-entered annotation.
- `UNAVAILABLE` — the monitored source does not expose the field.

The append-only evidence ledger remains authoritative. Unknown data stays unknown.

## Universal evidence chain

Where identifiers are observable, evidence should be correlatable through:

`provider -> connection -> app/IDE session -> conversation/thread -> invocation -> actions -> response -> usage -> context events -> result`

The chain is a normalized evidence model, not an adapter requirement.

## Required session measurements

### App / IDE presence

Track separately where observable:

- application/editor session start and end
- elapsed app-open time
- foreground/focused time
- idle time
- reload/restart intervals
- workspace/repository/branch/HEAD

A timestamped VS Code log directory can remain an inferred fallback lifecycle signal. An in-system VS Code/MCP tool should provide authoritative lifecycle/focus evidence when available.

### LLM invocation accounting

For every invocation/turn where observable:

- provider and model
- connection/request ID
- conversation/thread ID
- invocation/turn ID
- request start
- first response/token time
- completion time
- wall-clock duration
- result: completed / failed / cancelled / timed-out / disconnected / limited / unknown
- completed-return count
- failure count
- retry count
- tool/action count
- provider error code/message

### Actions and results

Record measurable action metadata without copying private prompts, responses, credentials, or source payloads into the ledger by default:

- action/tool type
- action start/end
- duration
- result status
- exit/error code where available
- affected file/repository identifiers where appropriate
- repeated/redundant discovery or context-reconstruction actions

### Usage/accounting

Capture provider-reported values exactly as observed:

- input tokens
- cached input tokens
- cache-write tokens when exposed
- output tokens
- reasoning tokens
- total tokens
- context-window size
- provider usage/quota percentages
- rate-limit window size
- reset timestamp
- usage-request start
- response status
- provider request ID
- request duration
- source filename/API identifier
- source line/record number
- source-record SHA-256

Quota snapshots remain valid observations even when window/reset metadata is unavailable; the UI must say `UNAVAILABLE` rather than infer the missing window.

## Context continuity

Observed continuity-break signals may include:

- provider/IDE connection reset
- disconnect/reconnect
- app-server spawn/start/exit
- editor reload/restart
- explicit context reset/compaction event
- changed thread/conversation ID
- incomplete invocation followed by a new continuity segment

Inferred reconstruction signals may include:

- rereading previously read files
- repeating repository scans/searches
- repeating Git/state discovery
- repeating tool sequences
- rebuilding substantially equivalent working context

Report:

- continuity state
- interruption timestamp
- first reconstruction action
- context re-established timestamp when inferable
- recovery duration
- recovery invocations/actions
- recovery token usage when attributable
- recovery overhead as a fraction of observed LLM-active time

Allowed classifications:

- `CONTINUOUS`
- `INTERRUPTED_OBSERVED`
- `CONTEXT_DISCONTINUITY_INFERRED`
- `RECONSTRUCTION_DETECTED`
- `CONTEXT_REESTABLISHED`
- `UNKNOWN`

Correlation is not causation.

## Multi-clock timestamp contract

Every significant event must be displayable in:

- local standard time with UTC offset/time-zone abbreviation where available
- UTC ISO-8601
- Unix epoch seconds
- Unix epoch milliseconds
- Julian Date (JD)
- Modified Julian Date (MJD)

UTC ISO-8601 is the canonical stored timestamp; the other clocks are deterministic derived views.

## Source validation

Every provider-specific usage display must expose its evidence chain.

For Codex Stats this includes, when present:

1. usage request started
2. provider response received
3. HTTP status
4. request ID
5. response duration
6. parsed usage values
7. source log path
8. source line/record
9. source-record hash
10. freshness relative to the monitored session

Suggested UI states:

- `VERIFIED`
- `STALE`
- `MISMATCH`
- `NO_SOURCE`
- `FAILED`

## Service-quality / fairness report

Reports keep three fact domains separate:

1. **Provider accounting** — provider-reported usage, quota, limits, tokens, and cost.
2. **Observed activity** — invocations, actions, timing, errors, resets, context reconstruction, IDE/browser/runtime state.
3. **Delivered utility** — completed returns and successfully completed measurable work.

A report may state that an observed relationship warrants investigation. It must never claim access to hidden provider accounting logic.

## Control-plane organization

Preserve the current visual language while organizing the always-on-top dashboard into persistent navigation sections:

- Overview
- Session
- Usage
- Context
- Evidence
- Tools
- Code Cipher
- Settings

The **Tools** section must show the actual local tool state, including the first-party MCP server, Chrome DevTools MCP, VisiData, local paths, pinned versions/commits, process state, and last successful evidence/action time. A documentation file existing in the repo is not evidence that a tool is running.

## Delivery stages

### Stage 1 — Foundation

- evidence doctrine
- multi-clock timebase
- context-continuity correlation primitives
- dashboard always-on-top
- local toolchain doctrine and lock file

### Stage 2 — Vendor and prove local tools

- place first-party MCP server under `tools/mcp_server/`
- vendor pinned Chrome DevTools MCP under `tools/chrome-devtools-mcp/`
- vendor pinned VisiData under `tools/visidata/`
- build/package all required runtime dependencies locally
- remove runtime registry/update/telemetry dependencies
- expose tool health/provenance in the control panel

### Stage 3 — Codex evidence hardening

- Codex usage source validator
- session-boundary freshness validation
- quota saturation vs explicit usage-limit event distinction
- invocation/return/failure/retry counters
- context-continuity panel
- VS Code elapsed/focus session view

### Stage 4 — Control-plane navigation

- persistent section navigation
- source drill-down
- tool status
- evidence validation controls

### Stage 5 — General LLM/API observation

- observe any authorized LLM/API connection through the common MCP/local tool system
- preserve provider-specific fields without fabricating absent values
- local model/runtime metrics for Ollama, llama.cpp, Qwen, and other local runtimes
- CPU/GPU/RAM/VRAM telemetry where locally available

### Stage 6 — Exportable evidence report

- reproducible session summary
- raw evidence references and hashes
- continuity/recovery timeline
- provider usage versus delivered-work correlation
- multi-clock timestamps
- machine-readable JSON plus human-readable report
