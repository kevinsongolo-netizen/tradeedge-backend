"""Edge Pattern Engine (Sprint 20 Phase 5 -- "Best Pattern" analytics).

Once enough trades exist, automatically discover the trader's own
multi-dimensional edge: which COMBINATION of pair + direction +
timeframe + POI type + premium/discount zone + session performs best --
not just one dimension at a time. That's what the existing "My Best
Setups" playbook (``app/engines/playbook_engine.py``) already does,
grouped by POI type alone; this answers a more specific question the
trader asked for directly: "Best-performing pattern: BTCUSD SELL M15
Bearish Order Block Premium London Session -- 74% win rate, avg R:R
2.8, 126 trades."

Reuses ``app/engines/setup_engine.py``'s ``group_stats`` (the same
sample-size-weighted win-rate/expectancy math every other coaching
feature in this app already uses) with a COMPOSITE key built from all
six dimensions -- a trade only joins a pattern group if it has a value
for every one of them, so a "pattern" here always means "this exact
combination", never a partial match blurred across trades that don't
actually share the full setup.

Entirely derived from the trader's own trading history -- no
hardcoded "good" combination anywhere. Degrades honestly: an empty
``patterns`` list (not a fabricated one) whenever nothing has reached
``EDGE_MIN_SAMPLE`` occurrences yet, same honesty bar (3) used
everywhere else in this app (setup_insight_engine's
MIN_SIMILAR_FOR_CONFIDENT_STAT, trade_lesson_engine's
MIN_SIMILAR_FOR_LESSON, characteristic_gap_engine's MIN_SAMPLE_FOR_GAP,
playbook_engine's PLAYBOOK_MIN_SAMPLE -- all also 3).

Pure function, no I/O -- same convention as every other
``app/engines/*.py`` module.
"""
from __future__ import annotations

from typing import Any

from app.engines.setup_engine import group_stats

EDGE_MIN_SAMPLE = 3
# A short ranked list, not just the single "best" one -- with real
# data, ties and near-ties between a couple of patterns are common,
# and seeing more than one is more honest than presenting a single
# "the" edge that might just barely have edged out another by expectancy.
MAX_PATTERNS = 3


def _pattern_key(entry: dict[str, Any]) -> str | None:
    """A trade only contributes to a pattern group if it has a value
    for ALL SIX dimensions -- a partial match (e.g. same pair/direction
    but no POI type logged) never blurs into a pattern that's supposed
    to mean "this exact combination", the same way every other
    dimension in this app only compares fields that are actually
    present rather than treating "missing" as "matches anything"."""
    pair = entry.get("pair")
    direction = entry.get("direction")
    timeframe = entry.get("timeframe")
    poi = entry.get("h4PoiType")
    zone = entry.get("premiumDiscount")
    session = entry.get("session")
    if not all([pair, direction, timeframe, poi, zone, session]):
        return None
    # Delimiter-joined only for group_stats' internal bookkeeping (it
    # needs a single hashable key) -- the actual field values displayed
    # to the trader are read back off a representative trade below, not
    # split out of this string, so a stray "|" inside a field value
    # (unlikely for any of these six) can't corrupt the output.
    return "|".join([str(pair).upper(), str(direction).upper(), str(timeframe), str(poi), str(zone), str(session)])


def build_edge_patterns(history: list[dict[str, Any]] | None) -> dict[str, Any]:
    """build_edge_patterns(history) -> {patterns: [...], sampleSize,
    hasEnoughData}.

    Each ``patterns[]`` entry is one pair+direction+timeframe+POI+zone+
    session combination the trader has logged at least
    ``EDGE_MIN_SAMPLE`` times, ranked by the same win-rate+expectancy
    score ``group_stats`` already uses everywhere else -- purely
    discovered from history, never a hardcoded "good" combination."""
    history = history or []
    groups = [g for g in group_stats(history, _pattern_key) if g["count"] >= EDGE_MIN_SAMPLE]
    groups.sort(key=lambda g: g["rankScore"], reverse=True)

    # One representative trade per pattern key, so the individual field
    # values (pair/direction/timeframe/poi/zone/session) shown to the
    # trader come straight from a real logged trade, not a string split.
    key_to_entry: dict[str, dict[str, Any]] = {}
    for e in history:
        key = _pattern_key(e)
        if key and key not in key_to_entry:
            key_to_entry[key] = e

    patterns: list[dict[str, Any]] = []
    for g in groups[:MAX_PATTERNS]:
        rep = key_to_entry.get(g["key"])
        if rep is None:
            continue
        patterns.append(
            {
                "pair": (rep.get("pair") or None),
                "direction": rep.get("direction"),
                "timeframe": rep.get("timeframe"),
                "poiType": rep.get("h4PoiType"),
                "premiumDiscount": rep.get("premiumDiscount"),
                "session": rep.get("session"),
                "count": g["count"],
                "wins": g["wins"],
                "losses": g["losses"],
                "breakeven": g["breakeven"],
                "winRate": g["winRate"],
                "averageRR": g["averageRR"],
                "expectancy": g["expectancy"],
            }
        )

    return {
        "patterns": patterns,
        "sampleSize": len(history),
        "hasEnoughData": len(patterns) > 0,
    }
