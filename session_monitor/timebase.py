"""Provider-neutral timestamp normalization for Watcher evidence.

UTC ISO-8601 is the canonical stored time. Alternate representations are
purely derived so a report can be independently checked without changing the
underlying evidence record.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

UNIX_EPOCH_JULIAN_DATE = 2440587.5
SECONDS_PER_DAY = 86400.0
MJD_OFFSET = 2400000.5


def _parse(value: Optional[str | datetime]) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def julian_date(value: Optional[str | datetime] = None) -> float:
    dt = _parse(value)
    return UNIX_EPOCH_JULIAN_DATE + dt.timestamp() / SECONDS_PER_DAY


def modified_julian_date(value: Optional[str | datetime] = None) -> float:
    return julian_date(value) - MJD_OFFSET


def representations(value: Optional[str | datetime] = None) -> dict:
    utc_dt = _parse(value)
    local_dt = utc_dt.astimezone()
    epoch_seconds = utc_dt.timestamp()
    return {
        "utc_iso": utc_dt.isoformat().replace("+00:00", "Z"),
        "local_iso": local_dt.isoformat(),
        "local_display": local_dt.strftime("%Y-%m-%d %H:%M:%S.%f %Z %z"),
        "unix_seconds": epoch_seconds,
        "unix_milliseconds": int(round(epoch_seconds * 1000)),
        "julian_date": julian_date(utc_dt),
        "modified_julian_date": modified_julian_date(utc_dt),
    }
