"""Setup Engine — port of ``js/setup_engine.js``.

Discovers best-performing setup dimensions (pair, asset, session, day,
H4 trend, POI, confirmation combo, RR bucket, confidence bucket) purely
from journal history — no hardcoded "good setup" values.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

SETUP_MIN_SAMPLE = 3

_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _day_name(date_str: Any) -> str | None:
    if not date_str:
        return None
    try:
        d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return _DAY_NAMES[d.weekday()]


def _confirmation_key(entry: dict) -> str | None:
    tags = [t for t in (entry.get("m15Confirmations") or []) if t]
    return " + ".join(sorted(tags)) if tags else None


def _rr_key(entry: dict) -> str | None:
    rr = _num(entry.get("rr"))
    return None if rr is None else f"{round(rr * 10) / 10}R"


def _confidence_key(entry: dict) -> str | None:
    confidence = _num(entry.get("confidence"))
    return None if confidence is None else f"{round(confidence)}%"


def group_stats(entries: list[dict] | None, key_fn: Callable[[dict], str | None]) -> list[dict]:
    """group_stats(entries, key_fn) — ranked group stats using only
    journal-derived values (win rate + expectancy, sample-size weighted)."""
    groups: dict[str, dict] = {}
    for e in entries or []:
        key = key_fn(e)
        if not key:
            continue
        g = groups.setdefault(
            key,
            {
                "key": key,
                "count": 0,
                "wins": 0,
                "losses": 0,
                "breakeven": 0,
                "totalPnl": 0.0,
                "totalRR": 0.0,
                "rrCount": 0,
                "grossProfit": 0.0,
                "grossLoss": 0.0,
            },
        )
        g["count"] += 1
        pnl = e.get("pnl") or 0
        if pnl > 0:
            g["wins"] += 1
            g["grossProfit"] += float(pnl)
        elif pnl < 0:
            g["losses"] += 1
            g["grossLoss"] += abs(float(pnl))
        else:
            g["breakeven"] += 1
        g["totalPnl"] += float(pnl or 0)
        rr = _num(e.get("rr"))
        if rr is not None:
            g["totalRR"] += rr
            g["rrCount"] += 1

    result = []
    for g in groups.values():
        win_rate = (g["wins"] / g["count"] * 100) if g["count"] else 0.0
        expectancy = (g["totalPnl"] / g["count"]) if g["count"] else 0.0
        sample_weight = min(1.0, g["count"] / SETUP_MIN_SAMPLE)
        # profitFactor: None (not 0, not Infinity) whenever there's no
        # losing trade yet in this group -- same JSON-safety fix applied
        # to statistics_engine.py during the Sprint 22 audit (a literal
        # Infinity token isn't valid JSON and breaks response parsing in
        # a browser). None here reads as "no losses recorded yet",
        # distinct from a real (low) ratio.
        profit_factor = (g["grossProfit"] / g["grossLoss"]) if g["grossLoss"] > 0 else None
        result.append(
            {
                **g,
                "winRate": win_rate,
                "expectancy": expectancy,
                "averageRR": (g["totalRR"] / g["rrCount"]) if g["rrCount"] else None,
                "profitFactor": profit_factor,
                "confident": g["count"] >= SETUP_MIN_SAMPLE,
                "rankScore": (win_rate * 0.65 + max(-100.0, min(100.0, expectancy)) * 0.35) * sample_weight,
            }
        )

    result.sort(key=lambda g: (g["rankScore"], g["count"], g["expectancy"]), reverse=True)
    return result


def analyze_setups(entries: list[dict] | None) -> dict:
    """analyze_setups(entries) — port of ``analyzeSetups``. Discovers
    the best pair, asset, session, day, H4 trend, POI, confirmation
    combo, RR bucket, and confidence bucket from journal history."""
    entries = entries or []
    dims: dict[str, Callable[[dict], str | None]] = {
        "pair": lambda e: str(e["pair"]).upper() if e.get("pair") else None,
        "asset": lambda e: e.get("asset"),
        "session": lambda e: e.get("session"),
        "day": lambda e: _day_name(e.get("date")),
        "h4Trend": lambda e: e.get("h4Trend"),
        "poi": lambda e: e.get("h4PoiType") or e.get("poi"),
        "confirmation": _confirmation_key,
        "rr": _rr_key,
        "confidence": _confidence_key,
    }

    by_dimension = {name: group_stats(entries, key_fn)[:10] for name, key_fn in dims.items()}
    top = {name: (rows[0] if rows else None) for name, rows in by_dimension.items()}

    best_setup_parts = [top[k]["key"] for k in ("pair", "session", "poi", "confirmation") if top.get(k)]

    return {
        "byDimension": by_dimension,
        "top": top,
        "bestSetup": " + ".join(best_setup_parts) if best_setup_parts else None,
        "sampleSize": len(entries),
    }
