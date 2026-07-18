"""Edge Profile Engine (Sprint 20 Phase 8 -- "AI Learning Engine").

The trader's own framing: "Don't only tell me why this trade could
lose. I want the AI to learn from ALL of my history and compare EVERY
characteristic." Earlier engines in this app each look at a hand-picked
subset of dimensions for a specific question (``characteristic_gap_
engine`` compares one candidate against the SIMILAR-trade subset;
``pattern_discovery_engine`` only surfaces dimensions where winners and
losers clearly diverge). This engine is deliberately different: it
builds one canonical, DATA-DRIVEN registry covering every
characteristic the trader listed (order block freshness, FVG
freshness, trend alignment, liquidity sweep, rejection strength,
premium/discount/equilibrium, session, equal highs/lows, BOS/CHoCH
(including internal/external), stop/target/R:R, and touch number),
ranks EACH ONE independently by how common it is within the trader's
OWN winning trades and within their OWN losing trades (not just the
ones that happen to separate the two groups), and then -- given a
current candidate -- reports exactly how many of each profile's top
characteristics this setup actually matches, and which ones.

Nothing here is a fixed Smart Money rule: every characteristic and its
% comes from ``history`` alone. A characteristic never appears unless
at least ``MIN_CHARACTERISTIC_SUPPORT`` trades on that side actually
have it -- a single trade doesn't get to define "82% of your winners".
Below ``MIN_SAMPLE`` winners or losers, that side is skipped entirely
and ``hasEnoughData`` is false, same honesty bar (3) as every other
engine in this app.

Pure function, no I/O -- same convention as every other
``app/engines/*.py`` module.
"""
from __future__ import annotations

from typing import Any, Callable

MIN_SAMPLE = 3
MIN_CHARACTERISTIC_SUPPORT = 3
MAX_CHARACTERISTICS = 8

Extractor = Callable[[dict[str, Any]], bool]

# Categorical dimensions where EVERY distinct value actually observed in
# the trader's history becomes its own labeled characteristic (e.g.
# "London" and "New York" both compete for a spot in the ranked list,
# rather than only the single most-common value winning a slot the way
# characteristic_gap_engine's winner-profile check does) -- this is
# what lets "London" and "Premium" and "Bullish" all show up together
# in one ranked list, exactly like the trader's own worked example.
_CATEGORICAL_DIMENSIONS: list[str] = ["premiumDiscount", "session", "h4Trend"]

# Tag characteristics -- present/absent on m15Confirmations. Covers
# every SMC-style characteristic the trader listed EXCEPT distance from
# POI and time-inside-the-zone, which stay documented as infeasible
# (see module docstring below the tag list) rather than fabricated.
_TAG_CHARACTERISTICS: list[str] = [
    "Fresh Order Block",
    "Mitigated Order Block",
    "Fresh FVG",
    "Mitigated FVG",
    "Liquidity Sweep",
    "Strong Rejection",
    "Weak Rejection",
    "BOS",
    "CHOCH",
    "Internal BOS",
    "External BOS",
    "Equal Highs Nearby",
    "Equal Lows Nearby",
    "First Touch",
    "Second Touch",
    "Third+ Touch",
]

# "Distance from POI" and "time inside the zone before entry" are both
# on the trader's own list but confirmed infeasible: the vision read
# never captures the POI zone's own high/low prices (only entry/SL/TP),
# and no timestamp-in-zone is ever recorded -- same honesty convention
# as similar_engine.py's documented volatility gap and pattern_
# discovery_engine.py's time-in-zone note. Fabricating either here
# would violate this app's one hard rule about never presenting a
# guess as a real statistic.


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_tag(trade: dict[str, Any], tag: str) -> bool:
    return tag in (trade.get("m15Confirmations") or [])


def _counter_trend(trade: dict[str, Any]) -> bool:
    """Same exact condition app/engines/mistake_engine.py's
    "counterTrend" mistake category already uses, kept as its own copy
    here per this app's per-engine self-containment convention --
    computed on the fly from h4Trend/direction, so it works on any
    historical trade even if it predates this feature."""
    return (trade.get("h4Trend") == "Bullish" and trade.get("direction") == "sell") or (
        trade.get("h4Trend") == "Bearish" and trade.get("direction") == "buy"
    )


def _with_trend(trade: dict[str, Any]) -> bool:
    return (trade.get("h4Trend") == "Bullish" and trade.get("direction") == "buy") or (
        trade.get("h4Trend") == "Bearish" and trade.get("direction") == "sell"
    )


def _build_characteristics(history: list[dict[str, Any]]) -> list[tuple[str, Extractor]]:
    """The full registry for THIS history: every tag characteristic,
    the two trend-alignment characteristics, plus one characteristic
    per distinct value actually observed on each categorical dimension
    (so a trader who has never logged an "Equilibrium" trade never sees
    a fabricated "Equilibrium" row -- only values that really occur)."""
    chars: list[tuple[str, Extractor]] = []
    for tag in _TAG_CHARACTERISTICS:
        chars.append((tag, (lambda t, tag=tag: _has_tag(t, tag))))
    chars.append(("Counter-Trend Setup", _counter_trend))
    chars.append(("With-Trend Setup", _with_trend))
    for field in _CATEGORICAL_DIMENSIONS:
        values = sorted({t.get(field) for t in history if t.get(field)}, key=str)
        for value in values:
            chars.append((str(value), (lambda t, field=field, value=value: t.get(field) == value)))
    return chars


def _rank_characteristics(chars: list[tuple[str, Extractor]], subset: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not subset:
        return []
    rows = []
    for label, fn in chars:
        count = sum(1 for t in subset if fn(t))
        if count < MIN_CHARACTERISTIC_SUPPORT:
            continue
        rows.append({"label": label, "share": round(count / len(subset) * 100, 1), "count": count})
    rows.sort(key=lambda r: (r["share"], r["count"]), reverse=True)
    return rows[:MAX_CHARACTERISTICS]


def build_edge_profile(
    history: list[dict[str, Any]] | None,
    candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """build_edge_profile(history, candidate=None) -> {hasEnoughData,
    winningTradeCount, losingTradeCount, winnerCharacteristics,
    loserCharacteristics, [winnerMatchCount, winnerMatchTotal,
    winnerMatches, loserMatchCount, loserMatchTotal, loserMatches]}.

    ``winnerCharacteristics``/``loserCharacteristics`` -- up to
    ``MAX_CHARACTERISTICS`` characteristics (of ANY kind -- structural
    tag, session, zone, trend, ...) ranked purely by how common they
    are within that side, each as ``{"label": ..., "share": <0-100>}``.
    Not filtered to only characteristics that separate winners from
    losers -- the trader explicitly asked to see everything discovered
    about each side independently, not just the differences.

    When ``candidate`` is supplied and there's enough data, also
    returns how many of each profile's characteristics this candidate
    itself has, and which ones by name -- "this setup matches 4 of
    your winning characteristics and 2 of your losing characteristics."
    """
    history = history or []
    winners = [t for t in history if (_num(t.get("pnl")) or 0) > 0]
    losers = [t for t in history if (_num(t.get("pnl")) or 0) < 0]
    has_enough_data = len(winners) >= MIN_SAMPLE and len(losers) >= MIN_SAMPLE

    result: dict[str, Any] = {
        "hasEnoughData": has_enough_data,
        "winningTradeCount": len(winners),
        "losingTradeCount": len(losers),
        "winnerCharacteristics": [],
        "loserCharacteristics": [],
    }
    if not has_enough_data:
        return result

    chars = _build_characteristics(history)
    winner_rows = _rank_characteristics(chars, winners)
    loser_rows = _rank_characteristics(chars, losers)
    result["winnerCharacteristics"] = [{"label": r["label"], "share": r["share"]} for r in winner_rows]
    result["loserCharacteristics"] = [{"label": r["label"], "share": r["share"]} for r in loser_rows]

    if candidate is not None:
        char_lookup = dict(chars)
        winner_matches = [r["label"] for r in winner_rows if char_lookup[r["label"]](candidate)]
        loser_matches = [r["label"] for r in loser_rows if char_lookup[r["label"]](candidate)]
        result["winnerMatchCount"] = len(winner_matches)
        result["winnerMatchTotal"] = len(winner_rows)
        result["winnerMatches"] = winner_matches
        result["loserMatchCount"] = len(loser_matches)
        result["loserMatchTotal"] = len(loser_rows)
        result["loserMatches"] = loser_matches

    return result
