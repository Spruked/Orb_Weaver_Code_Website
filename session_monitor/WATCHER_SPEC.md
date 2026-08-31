# Watcher Evidence Architecture

## Purpose

Watcher is the provider-neutral observability and fairness subsystem inside Orb Weaver Code Cipher.

Its purpose is to preserve enough independently observable evidence for users and providers to determine what happened during an LLM-assisted work session and where reported usage, reliability, context continuity, and delivered work may not line up.

Watcher is not a limit-evasion system, refund engine, or accusation engine.

Core doctrine:

> Watcher reports what was OBSERVED, what was DERIVED from observations, what was INFERRED, what is PLANNED, and what was UNAVAILABLE. It never promotes inference, configuration, documentation, or intent into runtime fact.

## Evidence and implementation-state language

Watcher documentation and UI must distinguish evidence class from implementation state.

Evidence classes:

- `OBSERVED` — directly emitted by a provider, IDE, runtime, OS, browser/DevTools channel, log, API response, filesystem inspection, repository inspection, or process.
- `DERIVED` — deterministic calculation over observed records.
- `INFERRED` — a defensible interpretation of multiple observed signals.
- `MANUAL` — user-entered annotation.
- `UNAVAILABLE` — the monitored source does not expose the field.

Implementation states:

- `PROVEN_RUNNING` — execution has been directly observed and the evidence source is identified.
- `PRESENT_NOT_PROVEN` — code/configuration/files exist, but successful runtime execution has not been observed.
- `PLANNED_REQUIRED` — required architecture that is not yet implemented or not yet proven.
- `ABSENT` — direct repository/runtime inspection shows the required component is not present.
- `UNKNOWN` — evidence is insufficient.

A configuration key, architecture diagram, README statement, lock-file entry, or planned path is not proof that a component runs.

Architecture diagrams must label planned flow as `PLANNED` or `REQUIRED`. Present-tense arrows are reserved for flows with direct runtime evidence.

## Local-tool rule

The system does not require a Watcher adapter hierarchy around first-party system tools.

The required product toolchain lives inside each product repository and ships inside the downloadable/deployed system. The first-party MCP server is the local coordination layer and uses the other local tools in unison.

Required repository topology:

```text
tools/
  mcp_server/                 # first-party system MCP server
  chrome-devtools-mcp/        # vendored official Chrome DevTools MCP source/build/runtime
  visidata/                   # vendored VisiData source/runtime
  TOOLCHAIN_LOCK.json         # pinned upstream provenance, hashes and policy
```

This topology is required in both:

- `Spruked/Orb_Weaver_Code_Website`
- `Spruked/Orb_Weaver`

Chrome DevTools MCP and VisiData are local system tools, not optional cloud integrations and not Watcher observer adapters.

## No-cloud runtime rule

After installation/deployment, core operation must not require network acquisition of tools or dependencies.

Core runtime must not require:

- npm or another package registry
- PyPI or another Python package index
- GitHub or another source host
- a hosted MCP server
- CrUX
- tool usage telemetry endpoints
- automatic upstream update checks
- package downloads at process startup

### Runtime prohibition

Required production/deployed tools must be started from explicit local paths inside the installed system.

Forbidden for required runtime execution:

- `npx`, whether the package is `@latest`, version-pinned, or expected to be cached
- runtime `npm install` or `npm ci`
- runtime `pip install`
- runtime `git clone`, `git pull`, submodule fetch, or equivalent source acquisition
- any fallback that silently reaches a package registry when a local executable is missing

Pinning a version does not satisfy the no-cloud runtime rule by itself. A pinned package still violates the rule if runtime startup can consult a registry or download missing content.

### Deliberate build/release carve-out

Controlled development and release preparation may use networked package/source acquisition to obtain and verify upstream source and resolve dependencies.

Examples permitted during controlled release preparation:

- `git clone` or an equivalent source fetch used to create/update a vendored snapshot
- `npm ci` / `npm install` used to construct the pinned local Chrome DevTools MCP build/runtime payload
- Python package resolution used to construct a pinned local VisiData runtime when required

Those operations are build/release activities, not product runtime behavior.

The produced repository/release/deployment bundle must contain the actual source/tool files, required runtime dependencies, build output, licenses/notices, provenance, and hashes. Production startup must succeed with network access disabled.

Do not use Git submodules for required deployed tools because an archive/download must contain the actual tool files without a second fetch. Prefer a vendored snapshot or Git subtree.

## Local toolchain

### First-party MCP server

The first-party MCP server is the system's local coordination layer.

Required location:

`tools/mcp_server/`

Chrome DevTools MCP, VisiData, and subsequent system tools sit beside it under `tools/` and are invoked locally through the same MCP/tool system.

Watcher records evidence produced by that system. It does not need a second abstraction layer whose only purpose is to rename those tools as adapters.

### Chrome DevTools MCP

Required location:

`tools/chrome-devtools-mcp/`

Use a pinned vendored snapshot of the official `ChromeDevTools/chrome-devtools-mcp` project.

Required production policy:

- execute the local vendored/built binary by explicit path
- no `npx` in production/deployed startup
- no registry lookup or install fallback
- usage statistics disabled
- CrUX disabled
- automatic update checks disabled
- sensitive network-header redaction enabled where supported
- connect only to explicitly authorized local Chrome targets
- preserve upstream Apache-2.0 license/notices

Chrome DevTools evidence may establish network timing/status, console/runtime faults, page/target lifecycle, reloads, navigation, and performance behavior.

Chrome evidence does not establish hidden provider accounting or authoritative LLM context state unless the provider explicitly exposes those facts through the observed channel.

### VisiData

Required location:

`tools/visidata/`

Use a pinned vendored VisiData source/runtime for local evidence and structured-data inspection.

VisiData is GPL-3.0 software. Keep the complete upstream source and license intact in its vendored directory and deployment. Treat it as a separate local program/tool invoked by the first-party system rather than copying GPL implementation code into proprietary first-party modules without a separate licensing review.

## Universal evidence chain

Where identifiers are observable, evidence should be correlatable through:

`provider -> connection -> app/IDE session -> conversation/thread -> invocation -> actions -> response -> usage -> context events -> result`

The chain is a normalized evidence model, not an adapter requirement.

Provider/runtime-specific parsers or collectors may exist where necessary to read a source, but their existence does not create a second system-tool architecture and does not grant authority to invent unavailable fields.

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

The **Tools** section must show actual local tool state, including the first-party MCP server, Chrome DevTools MCP, VisiData, local paths, pinned versions/commits, process state, and last successful evidence/action time.

A documentation file, configuration key, expected executable name, or lock-file entry must never be displayed as proof that the tool is installed or running.

## Delivery stages

Delivery-stage bullets are requirements/plans unless explicitly marked `PROVEN_RUNNING` with evidence.

### Stage 1 — Foundation

- evidence doctrine
- multi-clock timebase
- context-continuity correlation primitives
- dashboard always-on-top
- local toolchain doctrine and lock file

### Stage 2 — Vendor and prove local tools

- place the first-party MCP server under `tools/mcp_server/`
- vendor pinned Chrome DevTools MCP under `tools/chrome-devtools-mcp/`
- vendor pinned VisiData under `tools/visidata/`
- build/package all required runtime dependencies locally
- remove runtime registry/update/telemetry dependencies
- execute each required tool from explicit local paths
- prove offline startup with network access disabled
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

- observe authorized LLM/API connections through the common MCP/local tool system and source-specific collectors where required
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
