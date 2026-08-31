# Watcher Evidence Architecture

## Purpose

Watcher is the provider-neutral observability and fairness subsystem inside Orb Weaver Code Cipher.

Its job is not to accuse a provider, calculate hidden provider-side accounting, evade limits, or obtain free service. Its job is to preserve enough independently observable evidence for users and providers to determine what happened during an LLM-assisted work session and where reported usage, reliability, context continuity, and delivered work may not line up.

Core doctrine:

> Watcher reports what was observed, what was derived from observations, what was inferred, and what was unavailable. It never promotes inference into fact.

Codex is Provider Adapter #1. The core evidence model must remain provider-neutral so the same system can monitor API clients, IDE assistants, local inference servers, and future LLM providers.

## Evidence classes

- `observed` — directly emitted by a provider, IDE, runtime, OS, log, API response, or process.
- `derived` — deterministic calculation over observed records.
- `inferred` — a defensible interpretation of multiple observed signals.
- `manual` — user-entered annotation.
- `unavailable` — a field that the monitored provider/runtime does not expose.

Existing append-only evidence remains authoritative. New Watcher views are read-only correlations over that evidence unless an adapter is explicitly performing an observation action.

## Universal hierarchy

Every observation should be normalizable into this hierarchy where the source exposes the identifiers:

`provider -> connection -> app/IDE session -> conversation/thread -> invocation -> actions -> response -> usage -> context events -> result`

No adapter is required to populate fields the provider does not expose.

## Required session measurements

### App / IDE presence

Watcher should distinguish these concepts rather than combining them:

- app session opened
- app session ended
- elapsed app-open time
- app reload/restart intervals
- foreground/focused time when an authoritative source is available
- idle time when an authoritative source is available
- workspace/repository/branch/HEAD at observation boundaries

A timestamped VS Code log directory remains a fallback/inferred editor lifecycle signal. A future VS Code extension should provide authoritative editor lifecycle and focus events.

### LLM invocation accounting

For every invocation or turn where observable:

- provider and model
- connection/request ID
- conversation/thread ID
- turn/invocation ID
- request start
- first response/token time
- completion time
- wall-clock duration
- completion result: completed / failed / cancelled / timed-out / disconnected / limited / unknown
- completed-return count
- failure count
- retry count
- tool/action count
- provider error code/message

### Actions and results

Record metadata about measurable actions without copying private prompts, responses, or source code into the ledger by default:

- action/tool type
- action start/end
- duration
- result status
- exit/error code where available
- affected file/repository identifiers where appropriate
- whether an action repeats substantially equivalent discovery already observed in the same continuity segment

### Usage and accounting

Capture provider-reported values exactly as observed:

- input tokens
- cached input tokens
- cache-write tokens when exposed
- output tokens
- reasoning tokens
- total tokens
- context-window size
- provider quota/usage percentages
- rate-limit window size
- reset timestamp
- request start
- response status
- request ID
- request duration
- source filename/API identifier
- source line/record number
- source-record SHA-256

Watcher must preserve quota snapshots even when window/reset metadata is unavailable, but the UI must clearly state that the window metadata was not observed.

### Context continuity

Watcher should detect and report context continuity episodes using layered evidence:

Observed signals can include:

- provider/IDE connection reset
- disconnect/reconnect
- app-server spawn/start/exit
- editor reload/restart
- explicit provider context reset/compaction events
- changed thread/conversation identifiers
- incomplete invocation followed by a new continuity segment

Inferred reconstruction signals can include:

- repeated reads of files already read before an interruption
- repeated repository scans/searches
- repeated Git/state discovery
- repeated tool sequences
- repeated retrieval of substantially equivalent working context

Watcher should report:

- continuity state
- interruption timestamp
- first reconstruction action
- context re-established timestamp when inferable
- recovery duration
- recovery invocations
- recovery actions
- recovery token usage when attributable
- recovery overhead as a fraction of observed LLM-active time

Allowed classifications:

- `CONTINUOUS`
- `INTERRUPTED_OBSERVED`
- `CONTEXT_DISCONTINUITY_INFERRED`
- `RECONSTRUCTION_DETECTED`
- `CONTEXT_REESTABLISHED`
- `UNKNOWN`

Correlation is not causation. A quota change near a continuity break is reported as a temporal relationship, not automatically attributed to the break.

## Multi-clock timestamp contract

Every significant Watcher event should be displayable in:

- local standard time with UTC offset/time-zone abbreviation where available
- UTC ISO-8601
- Unix epoch seconds
- Unix epoch milliseconds
- Julian Date (JD)
- Modified Julian Date (MJD)

UTC ISO-8601 remains the canonical stored event timestamp. Alternate representations are deterministic derived views.

## Provider adapters

Adapters should expose a common interface and capabilities declaration. Examples:

- Codex / VS Code
- OpenAI API
- Anthropic API
- Gemini API
- Grok API
- Ollama
- llama.cpp
- Qwen/local inference runtimes
- other IDE extensions

An adapter must explicitly declare unavailable measurements rather than fabricating substitutes.

## Source validation

Every provider-specific usage display should have a validator that can show the evidence chain behind the displayed value.

For Codex Stats this includes, when present:

1. usage request started
2. provider response received
3. HTTP status
4. request ID
5. response duration
6. parsed quota values
7. source log path
8. source line
9. source-record hash
10. freshness relative to the current monitor session

Suggested UI states:

- `VERIFIED`
- `STALE`
- `MISMATCH`
- `NO_SOURCE`
- `FAILED`

## Service-quality / fairness report

A report should present three separate columns of fact:

1. **Provider accounting** — what the provider reported as usage, quota, limits, tokens, and cost.
2. **Observed activity** — invocations, actions, timing, errors, resets, context reconstruction, and IDE/runtime state.
3. **Delivered utility** — completed returns and successfully completed measurable work.

A report may state that the observed relationship warrants investigation. It must not claim access to hidden provider-side accounting logic.

## Delivery stages

### Stage 1 — Foundation

- provider-neutral Watcher contract
- multi-clock timebase utilities
- provider adapter base class
- context-continuity correlation primitives
- dashboard always-on-top

### Stage 2 — Codex evidence hardening

- Codex usage source validator in the control plane
- session-boundary freshness validation
- correct distinction between quota saturation and observed `usage_limit_exceeded` events
- invocation/return/failure/retry counters
- context-continuity panel
- VS Code elapsed-session view

### Stage 3 — Control-plane navigation

Preserve the existing visual language while reorganizing the dashboard into navigable sections:

- Overview
- Session
- Usage
- Context
- Evidence
- Code Cipher
- Settings

The navigation should be persistent/sticky and should not hide evidence detail.

### Stage 4 — Generic API monitoring

- local proxy/SDK instrumentation interface
- OpenAI-compatible adapter first
- provider request/response metadata capture
- cost/token/rate-limit adapters where exposed

### Stage 5 — IDE and local-model adapters

- authoritative VS Code extension lifecycle/focus events
- Anthropic/Gemini/Grok integrations as observable APIs permit
- Ollama/llama.cpp/local-runtime metrics
- CPU/GPU/RAM/VRAM telemetry where locally available

### Stage 6 — Exportable evidence report

- reproducible session summary
- raw evidence references and hashes
- continuity/recovery timeline
- provider usage versus delivered work correlation
- multi-clock timestamps
- machine-readable JSON plus human-readable report
