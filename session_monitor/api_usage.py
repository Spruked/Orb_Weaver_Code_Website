"""Provider usage adapters and an append-only API ledger, independent of plan quota.

Only completed, caller-reported usage metadata is accepted. No provider keys,
prompts, generated content, network interception, or inferred process links.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Callable

from evidence import EvidenceEvent, now_iso

VERSION = "api-usage-1"
METRICS = ("input_tokens", "cached_tokens", "cache_creation_tokens", "output_tokens", "reasoning_tokens", "total_tokens")


def count(value):
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueError("Token counts must be nonnegative integers or null")
    return value


def total(*values):
    return sum(values) if all(value is not None for value in values) else None


def metadata_text(value, field, required=False):
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise ValueError(f"{field} must be a nonempty string of at most 512 characters")
    if re.search(r"(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{20,}|Bearer\s+\S+)", value):
        raise ValueError(f"Do not send credentials in {field}")
    return value


def accounting_fields(value, depth=0):
    """Keep numeric usage breakdowns and accounting enums, never content strings."""
    if depth > 8:
        raise ValueError("Usage metadata is too deeply nested")
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,79}", key):
                continue
            if key in {"modality", "type", "service_tier", "serviceTier"} and isinstance(item, str):
                if re.fullmatch(r"[a-zA-Z_ -]{1,40}", item):
                    result[key] = item
            elif re.search(r"token|count|cache|reason|think|cost|iteration|server_tool|request|search|tier|details", key, re.I):
                cleaned = accounting_fields(item, depth + 1)
                if cleaned is not None:
                    result[key] = cleaned
        return result
    if isinstance(value, list):
        if len(value) > 100:
            raise ValueError("Usage breakdown has too many items")
        return [accounting_fields(item, depth + 1) for item in value]
    if type(value) is int:
        return count(value)
    if value is None:
        return None
    return None


def openai_adapter(usage):
    input_details = usage.get("input_tokens_details") or usage.get("prompt_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or usage.get("completion_tokens_details") or {}
    inp = count(usage.get("input_tokens", usage.get("prompt_tokens")))
    out = count(usage.get("output_tokens", usage.get("completion_tokens")))
    return dict(input_tokens=inp, output_tokens=out,
                cached_tokens=count(input_details.get("cached_tokens")),
                cache_creation_tokens=count(input_details.get("cache_write_tokens")),
                reasoning_tokens=count(output_details.get("reasoning_tokens")),
                total_tokens=count(usage.get("total_tokens")) if usage.get("total_tokens") is not None else total(inp, out),
                accounting_note="Cached input and reasoning output are subsets; do not add them again.")


def anthropic_adapter(usage):
    base = count(usage.get("input_tokens"))
    cached = count(usage.get("cache_read_input_tokens"))
    creation = count(usage.get("cache_creation_input_tokens"))
    # Older non-caching responses omit both cache fields. Missing optional
    # cache categories add nothing, while their own normalized values stay null.
    inp = None if base is None else base + (cached or 0) + (creation or 0)
    out = count(usage.get("output_tokens"))
    details = usage.get("output_tokens_details") or {}
    return dict(input_tokens=inp, cached_tokens=cached, cache_creation_tokens=creation,
                output_tokens=out, reasoning_tokens=count(details.get("thinking_tokens")),
                total_tokens=total(inp, out),
                accounting_note="Input includes uncached input, cache reads, and cache creation. Thinking is not added twice.")


def gemini_adapter(usage):
    def field(camel, snake):
        return count(usage.get(camel, usage.get(snake)))
    inp = field("promptTokenCount", "prompt_token_count")
    candidates = field("candidatesTokenCount", "candidates_token_count")
    thoughts = field("thoughtsTokenCount", "thoughts_token_count")
    out = None if candidates is None else candidates + (thoughts or 0)
    provider_total = field("totalTokenCount", "total_token_count")
    return dict(input_tokens=inp, cached_tokens=field("cachedContentTokenCount", "cached_content_token_count"),
                cache_creation_tokens=None, output_tokens=out, reasoning_tokens=thoughts,
                total_tokens=provider_total if provider_total is not None else total(inp, out),
                accounting_note="Output includes candidates plus thoughts. Provider total and tool-use breakdowns are preserved separately.")


def xai_adapter(usage):
    result = openai_adapter(usage)
    ticks = count(usage.get("cost_in_usd_ticks"))
    if ticks is not None:
        result.update(cost_amount=str(Decimal(ticks) / Decimal(10**10)), cost_currency="USD", cost_source="provider_response")
    return result


ADAPTERS: dict[str, Callable] = {"openai": openai_adapter, "anthropic": anthropic_adapter, "google": gemini_adapter, "xai": xai_adapter}
ALIASES = {"gemini": "google", "google-gemini": "google", "grok": "xai"}


def register_adapter(provider: str, adapter: Callable):
    ADAPTERS[provider] = adapter


def normalize(payload):
    provider = metadata_text(payload.get("provider"), "provider", True).lower()
    provider = ALIASES.get(provider, provider)
    if provider not in ADAPTERS:
        raise ValueError("No usage adapter registered for this provider")
    if payload.get("usage_complete", True) is not True:
        raise ValueError("Report completed request usage once, not partial stream snapshots")
    if payload.get("billing_mode", "api") != "api":
        raise ValueError("Subscription usage belongs to the subscription evidence source")
    usage = payload.get("usage")
    if not isinstance(usage, dict) or len(json.dumps(usage)) > 32768:
        raise ValueError("usage must be a metadata object of at most 32 KiB")
    normalized = ADAPTERS[provider](usage)
    for field in METRICS:
        normalized[field] = count(normalized.get(field))
    if all(normalized.get(field) is None for field in METRICS):
        raise ValueError("No token usage evidence found")
    for field in ("model", "request_id", "evidence_source"):
        normalized[field] = metadata_text(payload.get(field), field, True)
    for field in ("application", "process_id", "host", "project", "environment_id", "window_id", "account_ref"):
        value = payload.get(field)
        if field == "process_id" and type(value) is int:
            value = str(value)
        normalized[field] = metadata_text(value, field)
    timestamp = payload.get("timestamp") or now_iso()
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ValueError("timestamp must include a UTC offset") from None
    normalized.update(provider=provider, timestamp=parsed.astimezone(timezone.utc).isoformat(),
                      received_at=now_iso(), billing_mode="api", request_count=1,
                      attribution="source_reported" if normalized.get("environment_id") or normalized.get("window_id") else "unassigned",
                      provider_fields=accounting_fields(usage))
    cost = payload.get("cost")
    if cost is not None:
        try:
            amount = Decimal(str(cost["amount"]))
            if not amount.is_finite() or amount < 0:
                raise ValueError()
            currency = cost["currency"]
            if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
                raise ValueError()
            source = cost["source"]
            if source not in {"provider_response", "invoice", "manual", "estimate"}:
                raise ValueError()
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise ValueError("cost requires a nonnegative amount, ISO currency, and evidence source") from None
        if normalized.get("cost_amount") is not None and (Decimal(normalized["cost_amount"]) != amount or currency != normalized["cost_currency"]):
            raise ValueError("Reported cost conflicts with provider usage cost")
        normalized.update(cost_amount=str(amount), cost_currency=currency, cost_source=source)
    for field in ("cost_amount", "cost_currency", "cost_source"):
        normalized.setdefault(field, None)
    limits = payload.get("rate_limits") or {}
    if not isinstance(limits, dict):
        raise ValueError("rate_limits must contain response rate-limit headers only")
    normalized["rate_limits"] = {
        key.lower(): str(value)[:128] for key, value in limits.items()
        if re.fullmatch(r"(?:x-ratelimit-[a-z-]+|anthropic-ratelimit-[a-z-]+|retry-after)", key.lower())
        and isinstance(value, (str, int, float)) and len(str(value)) <= 128
        and re.fullmatch(r"[0-9a-zA-Z .,:+/_-]+", str(value))
    }
    identity = json.dumps([provider, normalized.get("account_ref"), normalized["request_id"]])
    normalized["record_id"] = hashlib.sha256(identity.encode()).hexdigest()
    return normalized


class UsageLedger:
    def __init__(self, storage):
        self.storage = storage
        self.db_path = storage.data_dir / "api_usage.db"
        self.lock = threading.RLock()
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS api_usage (
                    record_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL, record TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS api_usage_time ON api_usage(timestamp);
                CREATE TABLE IF NOT EXISTS api_usage_mirrors (record_id TEXT PRIMARY KEY);
                CREATE TRIGGER IF NOT EXISTS api_usage_no_update BEFORE UPDATE ON api_usage
                    BEGIN SELECT RAISE(ABORT, 'Usage records are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS api_usage_no_delete BEFORE DELETE ON api_usage
                    BEGIN SELECT RAISE(ABORT, 'Usage records are append-only'); END;
            """)
        self.flush_mirrors()

    def flush_mirrors(self):
        with self.lock, sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT record_id, session_id, record FROM api_usage WHERE record_id NOT IN (SELECT record_id FROM api_usage_mirrors)").fetchall()
            for record_id, session_id, serialized in rows:
                record = json.loads(serialized)
                try:
                    if not self.storage.evidence.has_record_hash(session_id, record_id):
                        self.storage.evidence.append(EvidenceEvent(
                            session_id=session_id, category="api_usage", event_type="api_request_usage_reported",
                            source="api_usage", source_identifier=record["evidence_source"], evidence_class="observed",
                            parser_version=VERSION, timestamp=record["timestamp"],
                            data={"normalized": {**record, "source_record_hash": record_id}}))
                    conn.execute("INSERT OR IGNORE INTO api_usage_mirrors VALUES (?)", (record_id,))
                except OSError:
                    # SQLite is the authoritative ledger; the persistent outbox
                    # retries the evidence mirror on the next report/restart.
                    break

    def record(self, payload, session_id):
        record = normalize(payload)
        with self.lock, sqlite3.connect(self.db_path) as conn:
            old = conn.execute("SELECT record FROM api_usage WHERE record_id = ?", (record["record_id"],)).fetchone()
            if old:
                existing = json.loads(old[0])
                ignored = {"timestamp", "received_at", "evidence_source"}
                if {k:v for k,v in record.items() if k not in ignored} != {k:v for k,v in existing.items() if k not in ignored}:
                    raise ValueError("Conflicting usage for an already recorded request_id")
                result = {"ok": True, "duplicate": True, "record": existing}
            else:
                conn.execute("INSERT INTO api_usage VALUES (?, ?, ?, ?)", (record["record_id"], record["timestamp"], session_id, json.dumps(record)))
                result = {"ok": True, "duplicate": False, "record": record}
        self.flush_mirrors()
        return result

    def summary(self, since=None, environment_id=None, window_id=None):
        since = since or datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            records = [json.loads(row[0]) for row in conn.execute("SELECT record FROM api_usage WHERE timestamp >= ? ORDER BY timestamp DESC", (since,))]
            pending = conn.execute("SELECT count(*) FROM api_usage WHERE record_id NOT IN (SELECT record_id FROM api_usage_mirrors)").fetchone()[0]
        if environment_id:
            records = [r for r in records if r.get("environment_id") == environment_id]
        if window_id:
            records = [r for r in records if r.get("window_id") == window_id]
        result = {field: (sum(r[field] for r in records if r.get(field) is not None) if any(r.get(field) is not None for r in records) else None) for field in METRICS}
        costs = {}
        cost_known = 0
        for record in records:
            if record["cost_amount"] is not None:
                key = record["cost_currency"] + " · " + record["cost_source"]
                costs[key] = costs.get(key, Decimal(0)) + Decimal(record["cost_amount"])
                cost_known += 1
        cost_display = "; ".join(f"{amount:f} {currency}" for currency, amount in costs.items()) if costs else "cost unknown"
        if 0 < cost_known < len(records):
            cost_display = "partial cost: " + cost_display
        groups = {}
        for record in records:
            key = (record["provider"], record["model"], record.get("application"), record.get("project"), record.get("environment_id"), record.get("window_id"))
            group = groups.setdefault(key, dict(provider=key[0], model=key[1], application=key[2], project=key[3], environment_id=key[4], window_id=key[5], request_count=0, **{field: None for field in METRICS}))
            group["request_count"] += 1
            for field in METRICS:
                if record[field] is not None:
                    group[field] = (group[field] or 0) + record[field]
        return {**result, "since": since, "request_count": len(records), "status": "observed" if records else "no_evidence",
                "missing_counts": {field: sum(r.get(field) is None for r in records) for field in METRICS},
                "costs": {key: str(value) for key, value in costs.items()}, "cost_display": cost_display,
                "unknown_cost_requests": len(records) - cost_known, "pending_evidence_mirrors": pending,
                "groups": list(groups.values()), "recent": records[:50], "providers": list(ADAPTERS),
                "coverage": "Only reported completed API requests; not subscription quota or a provider billing total."}
