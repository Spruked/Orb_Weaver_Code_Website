# Session Monitor Evidence Engine

Local evidence service used by the Orb Weaver Code Cipher control plane.

## Purpose

The monitor answers two questions with locally observable evidence:

1. What happened during the development session?
2. Did Codex quota/token movement correlate with actual work, reloads, IPC resets, or other runtime events?

It does not calculate provider quota from elapsed time and does not claim access to hidden cloud-side model state.

## Data model

- `sessions.db` — session index
- `events/<session_id>.jsonl` — append-only per-session evidence
- `all_events.jsonl` — combined append-only evidence stream
- cursor/state files — local parser positions used to prevent historical re-import and duplicate ingestion

Default data directory:

```text
~/.local/share/code-weaver-runtime
```

## Evidence classes

Every event is explicitly classified:

```text
observed     source/runtime data read directly
derived      deterministic calculation or cross-source comparison
inferred     evidence-supported inference
manual       user-entered annotation
unavailable  an expected source could not be observed
```

## Current observed sources

### ChatGPT/Codex provider usage

`wham_usage.py` is an independent provider-side quota observer. It reads the local Codex authentication created by `codex login` from:

```text
~/.codex/auth.json
```

or `$CODEX_HOME/auth.json` when `CODEX_HOME` is configured. It sends an authenticated read request to:

```text
https://chatgpt.com/backend-api/wham/usage
```

and records only normalized quota telemetry such as:

```text
primary_used_percent
secondary_used_percent
primary_window_minutes
secondary_window_minutes
primary_resets_at
secondary_resets_at
```

The collector does **not** persist access tokens, account IDs, email addresses, or raw provider response bodies. Authentication exists only in memory for the request. The provider endpoint is treated as an independently observed source and does not overwrite the VS Code Stats source.

The installer configures a user-level systemd oneshot + timer:

```text
code-weaver-wham-usage.service
code-weaver-wham-usage.timer
```

The timer observes provider usage every 30 seconds. An unavailable authentication/network/provider/schema state is recorded as `UNAVAILABLE` evidence and does not stop future observations.

When a recent `Codex Stats.log` quota observation is also present, Code Weaver creates a `DERIVED` `quota_source_comparison` event. Matching values are recorded as a match; disagreements are preserved as a mismatch. Stats observations older than ten minutes are not forced into a comparison.

The request behavior was independently implemented after reviewing the public MIT-licensed `Maol-1997/codex-stats` project. Code Weaver does not require or vendor that extension at runtime.

### Codex quota from VS Code Stats

VS Code Codex Stats output is discovered dynamically under:

```text
~/.vscode-server/data/logs/<session>/exthost*/output_logging_*/*Codex Stats.log
```

Observed percentage keys include:

```text
primaryUsedPercent
secondaryUsedPercent
```

This remains a separate evidence source from the provider-side observer.

### Codex rollout telemetry

Rollout JSONL is discovered dynamically under:

```text
~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
```

Normalized records can include:

```text
thread_id
turn_id
source_event_type
duration_ms
time_to_first_token_ms
last_token_usage
total_token_usage
rate_limits.primary
rate_limits.secondary
error_code
error_message
```

The parser keeps normalized telemetry plus source identity/hash. It does not copy raw prompt/response/tool payloads into the evidence ledger by default.

### VS Code / Codex lifecycle

Timestamped VS Code log directories and Codex extension logs are used as fallback/cross-check evidence until a dedicated VS Code extension supplies authoritative editor lifecycle events.

Existing log directories are baselined on session start and are not emitted as fresh reload events.

## Run

```bash
python3 server.py
```

Health:

```bash
curl http://127.0.0.1:18441/health
```

## Verify real parsers

```bash
python3 verify_parsers.py
```

`verify_parsers.py` is read-only.

Synthetic provider collector proof:

```bash
python3 wham_usage_test.py
```

The synthetic test sends no real ChatGPT request and writes only to a temporary runtime directory.

## Read vs write API contract

Dashboard reads are side-effect free:

```text
GET /health
GET /sessions
GET /sessions/{id}
GET /today
GET /codex/quota
GET /codex/rollout?session_id=<id>
GET /git/{session_id}
GET /timeline
GET /evidence/sources
```

Evidence enters the ledger only through explicit actions or monitor-owned observers:

```text
POST /sessions
POST /sessions/{id}/end
POST /codex/quota/observe/{session_id}
POST /codex/rollout/ingest/{session_id}
POST /vscode/scan/{session_id}
code-weaver-wham-usage.timer -> wham_usage.py
```

This prevents a dashboard refresh from manufacturing duplicate evidence.

## Session isolation

Rollout ingestion is bounded to the monitor session timestamps and cursor-based. Historical rollout records and historical VS Code directories must not contaminate a fresh session.

Provider usage observations are attached only to the currently active Code Weaver parent runtime session.

## Correlation

`correlation.py` is read-only. It derives:

- ordered session timeline
- event counts
- token-use summaries
- Codex primary/secondary rate-window metadata
- latest observed usage-limit event
- reload/IPC-to-quota windows

`wham_usage.py` additionally performs a narrow deterministic comparison between a new provider-side reading and the latest sufficiently recent `Codex Stats.log` quota reading. The original observations remain independent evidence records.

Correlation is not causation. A quota delta near a reload is surfaced as evidence for investigation, not automatically blamed on the reload.

## Integration with Code Cipher

The dashboard presents Session Monitor evidence and Code Cipher artifact/release evidence side by side. Neither evidence stream is allowed to silently rewrite the other.

Shared values such as repository, Git HEAD, session identity, source-manifest hash, and release identity are comparison keys. A mismatch is a first-class result.
