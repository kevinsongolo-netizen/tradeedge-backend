"""Characteristic Gap Engine (Sprint 20 Phase 4).

Answers two of the trader's own questions, directly from their own
history -- never a verdict:

  - "What characteristics do my winning trades have that this one
    does not?"
  - "What characteristics do my losing trades have that this one
    also has?"

Takes the SAME ``similar`` list ``setup_insight_engine.build_setup_
insight`` already computed (via ``similar_engine.search_similar``) --
each entry there is the trader's own logged trade (full
``Trade.to_engine_dict()`` shape) plus its similarity score, so no
extra history fetch or translation is needed here.

Splits that list into its winning and losing subsets and looks for a
DOMINANT value on a handful of categorical/tag dimensions (POI type,
premium/discount zone, session, BOS/CHoCH/liquidity-sweep presence).
"Dominant" means at least ``DOMINANT_SHARE`` of that subset shares the
same value -- a single outlier trade never gets to speak for "your
winners" or "your losers". Below ``MIN_SAMPLE_FOR_GAP`` winners (or
losers), that side is skipped entirely rather than drawing a pattern
from 1-2 trades -- same honesty bar as the rest of Sprint 20 Phase 4
(see ``setup_insight_engine.MIN_SIMILAR_FOR_CONFIDENT_STAT`` and
``trade_lesson_engine.MIN_SIMILAR_FOR_LESSON``, both also 3).

Pure function, no I/O -- same convention as every other engine here.
"""
from __future__ import annotations

from typing import Any

MIN_SAMPLE_FOR_GAP = 3
DOMINANT_SHARE = 0.6

# Categorical fields worth comparing directly (candidate vs. the
# dominant value in the winning/losing subset).
_CATEGORICAL_DIMENSIONS: list[tuple[str, str]] = [
    ("h4PoiType", "point-of-interest type"),
    ("premiumDiscount", "zone"),
    ("session", "session"),
]

# Structural tags (BOS/CHoCH/liquidity sweep) live inside
# m15Confirmations as a list of strings on both a candidate and a
# logged trade -- treated as present/absent rather than a single value.
_TAG_DIMENSIONS: list[tuple[str, str]] = [
    ("BOS", "a break of structure"),
    ("CHOCH", "a change of character"),
    ("Liquidity Sweep", "a liquidity sweep"),
]


def _dominant_value(trades: list[dict[str, Any]], field: str) -> tuple[Any, float]:
    """Most common non-null value of ``field`` across ``trades`` and
    the share of (non-null-valued) trades that share it. ``(None, 0.0)``
    when nothing usable is present."""
    counts: dict[Any, int] = {}
    total = 0
    for t in trades:
        v = t.get(field)
        if v is None or v == "":
            continue
        counts[v] = counts.get(v, 0) + 1
        total += 1
    if not counts:
        return None, 0.0
    value, count = max(counts.items(), key=lambda kv: kv[1])
    return value, count / total


def _tag_presence_share(trades: list[dict[str, Any]], tag: str) -> float:
    if not trades:
        return 0.0
    present = sum(1 for t in trades if tag in (t.get("m15Confirmations") or []))
    return present / len(trades)


def _candidate_has_tag(candidate: dict[str, Any], tag: str) -> bool:
    return tag in (candidate.get("m15Confirmations") or [])


def build_characteristic_gaps(
    candidate: dict[str, Any],
    similar: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Returns ``{hasEnoughData, winningTradeCount, losingTradeCount,
    winnerGaps, loserEchoes}``. ``winnerGaps`` -- characteristics this
    trader's similar WINNING trades typically have that this candidate
    does NOT. ``loserEchoes`` -- characteristics this trader's similar
    LOSING trades typically have (or typically lack) that this
    candidate ALSO has (or also lacks). Purely descriptive, never a
    recommendation -- the trader decides what, if anything, to do
    about a gap."""
    similar = similar or []
    winners = [s for s in similar if s.get("outcome") == "Win"]
    losers = [s for s in similar if s.get("outcome") == "Loss"]

    winner_gaps: list[str] = []
    loser_echoes: list[str] = []

    if len(winners) >= MIN_SAMPLE_FOR_GAP:
        for field, label in _CATEGORICAL_DIMENSIONS:
            value, share = _dominant_value(winners, field)
            if value is not None and share >= DOMINANT_SHARE and candidate.get(field) != value:
                winner_gaps.append(
                    f"Your winning trades on setups like this are usually in the {value} {label} "
                    f"({share * 100:.0f}% of {len(winners)} similar wins) -- this one is "
                    f"{candidate.get(field) or 'not set'}."
                )
        for tag, label in _TAG_DIMENSIONS:
            share = _tag_presence_share(winners, tag)
            if share >= DOMINANT_SHARE and not _candidate_has_tag(candidate, tag):
                winner_gaps.append(
                    f"{share * 100:.0f}% of your similar winning trades had {label} -- this one doesn't."
                )

    if len(losers) >= MIN_SAMPLE_FOR_GAP:
        for field, label in _CATEGORICAL_DIMENSIONS:
            value, share = _dominant_value(losers, field)
            if value is not None and share >= DOMINANT_SHARE and candidate.get(field) == value:
                loser_echoes.append(
                    f"Your losing trades on setups like this are usually in the {value} {label} "
                    f"({share * 100:.0f}% of {len(losers)} similar losses) -- this one is too."
                )
        for tag, label in _TAG_DIMENSIONS:
            absent_share = 1.0 - _tag_presence_share(losers, tag)
            if absent_share >= DOMINANT_SHARE and not _candidate_has_tag(candidate, tag):
                loser_echoes.append(
                    f"{absent_share * 100:.0f}% of your similar losing trades were missing {label} "
                    "-- this one is missing it too."
                )

    return {
        "hasEnoughData": len(winners) >= MIN_SAMPLE_FOR_GAP or len(losers) >= MIN_SAMPLE_FOR_GAP,
        "winningTradeCount": len(winners),
        "losingTradeCount": len(losers),
        "winnerGaps": winner_gaps,
        "loserEchoes": loser_echoes,
    }
