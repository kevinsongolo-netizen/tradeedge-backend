"""News/economic calendar filter (Sprint 12 — Market Context Filters).

Pure function: given an already-fetched list of economic events (see
``app/news/calendar_provider.py``) and a planned trade time, decides
whether any high-impact news falls too close to the trade and warns
accordingly. Knows nothing about HTTP or any specific provider — same
convention as every other engine in this app.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

IMPACT_RANK = {"low": 1, "medium": 2, "high": 3}
DEFAULT_BUFFER_MINUTES = 60


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def evaluate_news_risk(
    events: list[dict[str, Any]],
    planned_time: datetime,
    *,
    buffer_minutes: int = DEFAULT_BUFFER_MINUTES,
    currencies: list[str] | None = None,
    min_impact: str = "high",
) -> dict[str, Any]:
    if planned_time.tzinfo is None:
        planned_time = planned_time.replace(tzinfo=timezone.utc)
    planned_time = planned_time.astimezone(timezone.utc)

    min_rank = IMPACT_RANK.get(min_impact.lower(), IMPACT_RANK["high"])
    wanted_currencies = {c.upper() for c in currencies} if currencies else None

    matching: list[dict[str, Any]] = []
    for event in events:
        event_time = _parse_time(event.get("time", ""))
        if event_time is None:
            continue
        impact_rank = IMPACT_RANK.get(str(event.get("impact", "low")).lower(), 1)
        if impact_rank < min_rank:
            continue
        if wanted_currencies is not None and str(event.get("currency", "")).upper() not in wanted_currencies:
            continue
        minutes_away = abs((event_time - planned_time).total_seconds()) / 60.0
        if minutes_away <= buffer_minutes:
            matching.append({**event, "minutesAway": round(minutes_away, 1)})

    matching.sort(key=lambda e: e["minutesAway"])
    has_high_impact_nearby = len(matching) > 0

    warnings: list[str] = []
    if has_high_impact_nearby:
        closest = matching[0]
        warnings.append(
            f"{closest.get('event', 'A high-impact event')} ({closest.get('currency', '')}) "
            f"is within {buffer_minutes} minutes of this trade "
            f"({closest['minutesAway']:.0f} min away) — consider waiting."
        )
    is_placeholder = any(e.get("isPlaceholder") for e in events)
    if is_placeholder:
        warnings.append(
            "PLACEHOLDER DATA — no economic calendar API key is configured yet, this is example output only."
        )

    return {
        "has_high_impact_nearby": has_high_impact_nearby,
        "matching_events": matching,
        "warnings": warnings,
        "is_placeholder": is_placeholder,
    }
