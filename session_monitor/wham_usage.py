"""Provider-side Codex shared-plan usage observer for Code Weaver.

This collector is intentionally independent from the existing VS Code
``Codex Stats.log`` parser.  It reads the local Codex login token from
``~/.codex/auth.json`` (or ``$CODEX_HOME/auth.json``), queries ChatGPT's
``/backend-api/wham/usage`` endpoint, and records only normalized rate-limit
telemetry.  Access tokens, account IDs, email addresses, and raw response bodies
are never written to Code Weaver evidence.

The request shape was independently implemented after reviewing the public,
MIT-licensed ``Maol-1997/codex-stats`` project.  No extension UI or vendored
source from that project is required at runtime.

The script is designed to run as a short-lived systemd oneshot.  It does not
instantiate ``Storage`` because doing so would invoke monitor-startup recovery
logic in a second process.  Instead it reads the active runtime session ID from
SQLite and appends through the shared append-only ``EvidenceLog``.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from evidence import EvidenceEvent, EvidenceLog, now_iso

PARSER_VERSION = "wham-usage-0.1"
ENDPOINT = "https://chatgpt.com/backend-api/wham/usage"
UPSTREAM_REFERENCE = "https://github.com/Maol-1997/codex-stats"
DEFAULT_TIMEOUT_SECONDS = 12.0
RUNTIME_SOURCES = (
    "code_weaver_runtime",
    "electron-widget-startup",
    "vscode_fresh_window",
)


def _finite_number(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _canonical_hash(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def _runtime_data_dir() -> Path:
    configured = os.environ.get("CODE_WEAVER_RUNTIME_DATA_DIR")
    return (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".local" / "share" / "code-weaver-runtime"
    )


def load_auth(auth_path: Optional[Path] = None) -> dict:
    """Load only the credentials required for the request.

    The returned token values exist in memory only.  Callers must never place
    this object in evidence, logs, exceptions, or command output.
    """
    path = auth_path or (_codex_home() / "auth.json")
    if not path.exists():
        return {"status": "unavailable", "reason": "auth_file_missing"}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "unavailable", "reason": "auth_file_unreadable"}

    tokens = payload.get("tokens") if isinstance(payload, dict) else None
    tokens = tokens if isinstance(tokens, dict) else {}
    access_token = tokens.get("access_token")
    account_id = tokens.get("account_id") or payload.get("account_id")
    if not isinstance(access_token, str) or not access_token.strip():
        return {"status": "unavailable", "reason": "access_token_missing"}

    return {
        "status": "ready",
        "access_token": access_token.strip(),
        "account_id": account_id if isinstance(account_id, str) and account_id else None,
    }


def _parse_window(value, observed_epoch: float) -> Optional[dict]:
    if not isinstance(value, dict):
        return None

    used_percent = _finite_number(value.get("used_percent"))
    if used_percent is None:
        return None

    window_seconds = _finite_number(value.get("limit_window_seconds"))
    reset_after_seconds = _finite_number(value.get("reset_after_seconds"))
    reset_at = _finite_number(value.get("reset_at"))

    if reset_at is None and reset_after_seconds is not None:
        reset_at = observed_epoch + max(0.0, reset_after_seconds)
    if reset_after_seconds is None and reset_at is not None:
        reset_after_seconds = max(0.0, reset_at - observed_epoch)

    return {
        "used_percent": used_percent,
        "window_minutes": window_seconds / 60.0 if window_seconds is not None else None,
        "resets_in_seconds": reset_after_seconds,
        "resets_at": reset_at,
    }


def parse_usage(payload: dict, observed_at: Optional[str] = None) -> dict:
    """Normalize the provider response without retaining the raw body."""
    if not isinstance(payload, dict):
        raise ValueError("provider_payload_not_object")

    rate_limit = payload.get("rate_limit")
    rate_limit = rate_limit if isinstance(rate_limit, dict) else {}
    observed_at = observed_at or now_iso()
    try:
        observed_epoch = datetime.fromisoformat(
            observed_at.replace("Z", "+00:00")
        ).timestamp()
    except ValueError:
        observed_epoch = time.time()

    primary = _parse_window(rate_limit.get("primary_window"), observed_epoch)
    secondary = _parse_window(rate_limit.get("secondary_window"), observed_epoch)
    if primary is None and secondary is None:
        raise ValueError("provider_rate_limit_windows_missing")

    fingerprint_payload = {
        "primary": primary,
        "secondary": secondary,
    }
    source_record_hash = _canonical_hash(fingerprint_payload)

    return {
        "primary_used_percent": primary.get("used_percent") if primary else None,
        "secondary_used_percent": secondary.get("used_percent") if secondary else None,
        "primary_window_minutes": primary.get("window_minutes") if primary else None,
        "secondary_window_minutes": secondary.get("window_minutes") if secondary else None,
        "primary_resets_in_seconds": primary.get("resets_in_seconds") if primary else None,
        "secondary_resets_in_seconds": secondary.get("resets_in_seconds") if secondary else None,
        "primary_resets_at": primary.get("resets_at") if primary else None,
        "secondary_resets_at": secondary.get("resets_at") if secondary else None,
        "observed_at": observed_at,
        "source_record_hash": source_record_hash,
        "source_endpoint": ENDPOINT,
        "provider_response_keys": sorted(str(key) for key in payload.keys())[:20],
        "rate_limit_keys": sorted(str(key) for key in rate_limit.keys())[:20],
    }


def fetch_usage(
    auth: dict,
    opener: Callable = urlopen,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """Fetch one provider observation.

    Returned failures are deliberately coarse so secrets cannot leak through a
    proxy error string, response body, or exception message.
    """
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {auth['access_token']}",
        "User-Agent": "code-weaver-wham-observer/0.1",
    }
    if auth.get("account_id"):
        headers["chatgpt-account-id"] = auth["account_id"]

    request = Request(ENDPOINT, headers=headers, method="GET")
    observed_at = now_iso()
    try:
        with opener(request, timeout=timeout_seconds) as response:
            status = int(getattr(response, "status", 200) or 200)
            if status < 200 or status >= 300:
                return {
                    "status": "unavailable",
                    "reason": "provider_http_status",
                    "http_status": status,
                }
            body = response.read()
    except HTTPError as exc:
        return {
            "status": "unavailable",
            "reason": "provider_http_status",
            "http_status": int(exc.code),
        }
    except (URLError, TimeoutError, OSError):
        return {"status": "unavailable", "reason": "provider_network_error"}
    except Exception:
        return {"status": "unavailable", "reason": "provider_request_error"}

    try:
        payload = json.loads(body.decode("utf-8"))
        normalized = parse_usage(payload, observed_at=observed_at)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"status": "unavailable", "reason": "provider_json_invalid"}
    except ValueError as exc:
        return {"status": "unavailable", "reason": str(exc)}

    return {"status": "observed", "normalized": normalized}


def active_runtime_session_id(data_dir: Path) -> Optional[str]:
    db_path = data_dir / "sessions.db"
    if not db_path.exists():
        return None

    placeholders = ",".join("?" for _ in RUNTIME_SOURCES)
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            row = conn.execute(
                f"""
                SELECT id FROM sessions
                WHERE ended_at IS NULL AND status = 'active'
                  AND source IN ({placeholders})
                ORDER BY started_at DESC LIMIT 1
                """,
                RUNTIME_SOURCES,
            ).fetchone()
    except sqlite3.Error:
        return None
    return str(row[0]) if row else None


def _append_if_new(evidence: EvidenceLog, event: EvidenceEvent, record_hash: str) -> bool:
    if evidence.has_record_hash(event.session_id, record_hash):
        return False
    evidence.append(event)
    return True


def _latest_stats_quota(evidence: EvidenceLog, session_id: str) -> Optional[dict]:
    for event in reversed(evidence.read_session(session_id)):
        if event.get("event_type") != "quota_update":
            continue
        if event.get("source") != "codex_stats_log":
            continue
        normalized = event.get("data", {}).get("normalized")
        if isinstance(normalized, dict):
            return {
                "timestamp": event.get("timestamp"),
                "normalized": normalized,
            }
    return None


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _comparison_payload(stats: Optional[dict], wham: dict) -> dict:
    wham_time = _parse_timestamp(wham.get("observed_at"))
    stats_time = _parse_timestamp(stats.get("timestamp")) if stats else None
    age_seconds = None
    if wham_time is not None and stats_time is not None:
        age_seconds = abs((wham_time - stats_time).total_seconds())

    stats_normalized = stats.get("normalized", {}) if stats else {}
    s5 = _finite_number(stats_normalized.get("primary_used_percent"))
    sw = _finite_number(stats_normalized.get("secondary_used_percent"))
    w5 = _finite_number(wham.get("primary_used_percent"))
    ww = _finite_number(wham.get("secondary_used_percent"))

    comparable = stats is not None and age_seconds is not None and age_seconds <= 600
    five_hour_delta = w5 - s5 if comparable and w5 is not None and s5 is not None else None
    weekly_delta = ww - sw if comparable and ww is not None and sw is not None else None

    if not stats:
        state = "not_compared_no_stats_observation"
    elif not comparable:
        state = "not_compared_stats_stale"
    else:
        deltas = [delta for delta in (five_hour_delta, weekly_delta) if delta is not None]
        state = "match" if deltas and all(abs(delta) <= 0.01 for delta in deltas) else "mismatch"
        if not deltas:
            state = "not_compared_missing_values"

    return {
        "state": state,
        "scope": "shared_plan_limits",
        "comparison_evidence_class": "derived",
        "maximum_source_age_seconds": 600,
        "source_age_seconds": age_seconds,
        "stats": {
            "timestamp": stats.get("timestamp") if stats else None,
            "primary_used_percent": s5,
            "secondary_used_percent": sw,
            "source_record_hash": stats_normalized.get("source_record_hash"),
        },
        "wham": {
            "timestamp": wham.get("observed_at"),
            "primary_used_percent": w5,
            "secondary_used_percent": ww,
            "source_record_hash": wham.get("source_record_hash"),
        },
        "delta": {
            "primary_used_percent": five_hour_delta,
            "secondary_used_percent": weekly_delta,
        },
    }


def _record_comparison(
    evidence: EvidenceLog,
    session_id: str,
    normalized: dict,
) -> bool:
    comparison = _comparison_payload(_latest_stats_quota(evidence, session_id), normalized)
    fingerprint = _canonical_hash(comparison)
    event = EvidenceEvent(
        session_id=session_id,
        category="codex",
        event_type="quota_source_comparison",
        source="code_weaver_quota_correlator",
        source_identifier="codex_stats_log<->codex_wham_usage",
        evidence_class="derived",
        parser_version=PARSER_VERSION,
        data={
            "normalized": {
                **comparison,
                "source_record_hash": fingerprint,
            }
        },
        timestamp=normalized.get("observed_at") or now_iso(),
    )
    return _append_if_new(evidence, event, fingerprint)


def _record_unavailable(
    evidence: EvidenceLog,
    session_id: str,
    reason: str,
    http_status: Optional[int] = None,
) -> bool:
    normalized = {
        "status": "unavailable",
        "reason": reason,
        "http_status": http_status,
        "source_endpoint": ENDPOINT,
    }
    fingerprint = _canonical_hash(normalized)
    normalized["source_record_hash"] = fingerprint
    event = EvidenceEvent(
        session_id=session_id,
        category="codex",
        event_type="quota_source_status",
        source="codex_wham_usage",
        source_identifier=ENDPOINT,
        evidence_class="unavailable",
        parser_version=PARSER_VERSION,
        data={"normalized": normalized},
    )
    return _append_if_new(evidence, event, fingerprint)


def record_once(
    data_dir: Optional[Path] = None,
    auth_path: Optional[Path] = None,
    opener: Callable = urlopen,
) -> dict:
    """Collect one provider observation and append new evidence only."""
    data_dir = data_dir or _runtime_data_dir()
    session_id = active_runtime_session_id(data_dir)
    if not session_id:
        return {"status": "no_active_runtime"}

    evidence = EvidenceLog(data_dir)
    auth = load_auth(auth_path)
    if auth.get("status") != "ready":
        persisted = _record_unavailable(
            evidence,
            session_id,
            str(auth.get("reason") or "auth_unavailable"),
        )
        return {"status": "unavailable", "reason": auth.get("reason"), "persisted": persisted}

    result = fetch_usage(auth, opener=opener)
    # Drop the in-memory credential reference as soon as the request is done.
    auth.clear()

    if result.get("status") != "observed":
        persisted = _record_unavailable(
            evidence,
            session_id,
            str(result.get("reason") or "provider_unavailable"),
            result.get("http_status"),
        )
        return {
            "status": "unavailable",
            "reason": result.get("reason"),
            "http_status": result.get("http_status"),
            "persisted": persisted,
        }

    normalized = result["normalized"]
    record_hash = normalized["source_record_hash"]
    event = EvidenceEvent(
        session_id=session_id,
        category="codex",
        event_type="quota_provider_observation",
        source="codex_wham_usage",
        source_identifier=ENDPOINT,
        evidence_class="observed",
        parser_version=PARSER_VERSION,
        data={"normalized": normalized},
        timestamp=normalized["observed_at"],
    )
    persisted = _append_if_new(evidence, event, record_hash)
    comparison_persisted = _record_comparison(evidence, session_id, normalized) if persisted else False

    return {
        "status": "observed",
        "persisted": persisted,
        "comparison_persisted": comparison_persisted,
        "primary_used_percent": normalized.get("primary_used_percent"),
        "secondary_used_percent": normalized.get("secondary_used_percent"),
        "observed_at": normalized.get("observed_at"),
    }


def main() -> int:
    result = record_once()
    if os.environ.get("CODE_WEAVER_WHAM_VERBOSE") == "1":
        print(json.dumps(result, sort_keys=True))
    # Collection failure is evidence, not a service crash.  The timer should
    # keep running so a later successful request can recover automatically.
    return 0


if __name__ == "__main__":
    sys.exit(main())
