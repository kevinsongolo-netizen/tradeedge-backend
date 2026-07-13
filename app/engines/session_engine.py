"""Trading session auto-detection (Sprint 12 — Market Context Filters).

Pure function, no I/O: given a UTC timestamp, returns which trading
session(s) are active. Session hours are the conventional forex-market
windows (UTC), matching the options already offered in the journal's
"Session" dropdown (Asian, London, New York, London/NY Overlap).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# (start_hour, end_hour) in UTC, half-open [start, end). Overlap is
# derived, not listed separately, so it can't drift out of sync.
ASIAN_HOURS = (0, 9)
LONDON_HOURS = (7, 16)
NEW_YORK_HOURS = (12, 21)


def _in_window(hour: int, window: tuple[int, int]) -> bool:
    start, end = window
    return start <= hour < end


def detect_session(dt: datetime | None = None) -> dict[str, Any]:
    if dt is None:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_utc = dt.astimezone(timezone.utc)
    hour = dt_utc.hour

    active: list[str] = []
    if _in_window(hour, ASIAN_HOURS):
        active.append("Asian")
    if _in_window(hour, LONDON_HOURS):
        active.append("London")
    if _in_window(hour, NEW_YORK_HOURS):
        active.append("New York")

    is_overlap = "London" in active and "New York" in active
    if is_overlap:
        primary = "London/NY Overlap"
    elif active:
        primary = active[0]
    else:
        primary = "Between sessions"

    return {
        "utc_time": dt_utc.isoformat(),
        "active_sessions": active,
        "primary_session": primary,
        "is_overlap": is_overlap,
    }
