"""Characteristic Gap Engine (Sprint 20 Phase 4, extended Phase 5).

Answers three of the trader's own questions, directly from their own
history -- never a verdict:

  - "What characteristics do my winning trades have that this one
    does not?"
  - "What characteristics do my losing trades have that this one
    also has?"
  - "How many of my winning trades' typical characteristics does this
    setup actually match?" (Sprint 20 Phase 5 -- "This setup only
    matches 2 of those 5 characteristics.")

Takes the SAME ``similar`` list ``setup_insight_engine.build_setup_
insight`` already computed (via ``similar_engine.search_similar``) --
each entry there is the trader's own logged trade (full
``Trade.to_engine_dict()`` shape) plus its similarity score, so no
extra history fetch or translation is needed here.

Splits that list into its winning and losing subsets and looks for a
DOMINANT value on categorical/tag dimensions (POI type, premium/
discount zone, session, trend, BOS/CHoCH/liquidity-sweep/FVG presence)
plus a TYPICAL value on two continuous ones (stop size, R:R -- Sprint
20 Phase 5, per the trader's own "smaller stop loss / higher R:R"
example). "Dominant"/"typical" means at least ``DOMINANT_SHARE`` of
that subset shares the same categorical value (or, for the continuous
pair, the group's average) -- a single outlier trade never gets to
speak for "your winners" or "your losers". Below ``MIN_SAMPLE_FOR_GAP``
winners (or losers), that side is skipped entirely rather than drawing
a pattern from 1-2 trades -- same honesty bar as the rest of Sprint 20
Phase 4 (see ``setup_insight_engine.MIN_SIMILAR_FOR_CONFIDENT_STAT`` and
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
    ("h4Trend", "trend"),
]

# Structural tags (BOS/CHoCH/liquidity sweep/FVG) live inside
# m15Confirmations as a list of strings on both a candidate and a
# logged trade -- treated as present/absent rather than a single value.
_TAG_DIMENSIONS: list[tuple[str, str]] = [
    ("BOS", "a break of structure"),
    ("CHOCH", "a change of character"),
    ("Liquidity Sweep", "a liquidity sweep"),
    ("FVG", "an FVG"),
]

# Sprint 20 Phase 5 -- continuous dimensions (stop size, R:R). A single
# average stands in for "typical" here (there's no dominant value for a
# number the way there is for a category), and a candidate is only
# called "notably different" from it once the ratio clears a real gap
# -- not just any tiny numeric difference. Same ratio convention as
# app/engines/trade_lesson_engine.py's tight/wide-stop checks, kept as
# its own copy here per this app's per-engine self-containment
# convention.
_NOTABLY_LOWER_RATIO = 0.7   # candidate's value is this much (or less) of the group average
_NOTABLY_HIGHER_RATIO = 1.5  # candidate's value is this much (or more) of the group average


def _stop_distance_pct(trade: dict[str, Any]) -> float | None:
    entry, sl = trade.get("entry"), trade.get("sl")
    if not isinstance(entry, (int, float)) or not isinstance(sl, (int, float)) or entry == 0:
        return None
    return abs(entry - sl) / abs(entry) * 100


def _rr_value(trade: dict[str, Any]) -> float | None:
    rr = trade.get("rr")
    return float(rr) if isinstance(rr, (int, float)) else None


# (dimension key, human label, "lower means" phrase, "higher means" phrase, extractor)
_CONTINUOUS_DIMENSIONS: list[tuple[str, str, str, str, Any]] = [
    ("stopDistancePct", "stop loss size", "tighter", "wider", _stop_distance_pct),
    ("rr", "risk:reward", "lower", "higher", _rr_value),
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


def _continuous_average(trades: list[dict[str, Any]], extractor: Any) -> float | None:
    values = [v for v in (extractor(t) for t in trades) if v is not None]
    return sum(values) / len(values) if values else None


def _evaluate_winner_profile(candidate: dict[str, Any], winners: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per dimension that was actually evaluable against the
    winning subset (dominant categorical value found, tag had a real
    majority presence, or a continuous average could be computed) --
    each ``{"matched": bool, "gapText": str | None}``. Used for BOTH
    the winner_gaps text list and the "matches N of M" score, so the
    two never drift out of sync with each other."""
    rows: list[dict[str, Any]] = []

    for field, label in _CATEGORICAL_DIMENSIONS:
        value, share = _dominant_value(winners, field)
        if value is None or share < DOMINANT_SHARE:
            continue
        matched = candidate.get(field) == value
        gap_text = None
        if not matched:
            gap_text = (
                f"Your winning trades on setups like this are usually in the {value} {label} "
                f"({share * 100:.0f}% of {len(winners)} similar wins) -- this one is "
                f"{candidate.get(field) or 'not set'}."
            )
        rows.append({"matched": matched, "gapText": gap_text})

    for tag, label in _TAG_DIMENSIONS:
        share = _tag_presence_share(winners, tag)
        if share < DOMINANT_SHARE:
            continue
        matched = _candidate_has_tag(candidate, tag)
        gap_text = None
        if not matched:
            gap_text = f"{share * 100:.0f}% of your similar winning trades had {label} -- this one doesn't."
        rows.append({"matched": matched, "gapText": gap_text})

    for field, label, lower_word, higher_word, extractor in _CONTINUOUS_DIMENSIONS:
        avg = _continuous_average(winners, extractor)
        candidate_value = extractor(candidate)
        if avg is None or avg == 0 or candidate_value is None:
            continue
        ratio = candidate_value / avg
        matched = _NOTABLY_LOWER_RATIO <= ratio <= _NOTABLY_HIGHER_RATIO
        gap_text = None
        if not matched:
            direction = higher_word if ratio < _NOTABLY_LOWER_RATIO else lower_word
            gap_text = (
                f"Your winning trades usually have a {direction} {label} (avg {avg:.2f}) "
                f"than this one ({candidate_value:.2f})."
            )
        rows.append({"matched": matched, "gapText": gap_text})

    return rows


def build_characteristic_gaps(
    candidate: dict[str, Any],
    similar: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Returns ``{hasEnoughData, winningTradeCount, losingTradeCount,
    winnerGaps, loserEchoes, winnerMatchCount, winnerMatchTotal,
    winnerMatchSummary}``.

    ``winnerGaps`` -- characteristics this trader's similar WINNING
    trades typically have that this candidate does NOT (now covering
    stop size and R:R too, not just categorical/tag dimensions).
    ``loserEchoes`` -- characteristics this trader's similar LOSING
    trades typically have (or typically lack) that this candidate ALSO
    has (or also lacks).
    ``winnerMatchCount``/``winnerMatchTotal`` -- e.g. 2 of 5 -- how many
    of the evaluable winning-profile dimensions this candidate actually
    matches; ``winnerMatchSummary`` is the same thing as one sentence,
    e.g. "This setup matches 2 of 5 characteristics your winning trades
    typically have." None/0 when there weren't enough winners to build
    a profile from at all.

    Purely descriptive, never a recommendation -- the trader decides
    what, if anything, to do about a gap."""
    similar = similar or []
    winners = [s for s in similar if s.get("outcome") == "Win"]
    losers = [s for s in similar if s.get("outcome") == "Loss"]

    winner_gaps: list[str] = []
    loser_echoes: list[str] = []
    winner_match_count = 0
    winner_match_total = 0
    winner_match_summary: str | None = None

    if len(winners) >= MIN_SAMPLE_FOR_GAP:
        profile = _evaluate_winner_profile(candidate, winners)
        winner_gaps = [row["gapText"] for row in profile if row["gapText"]]
        winner_match_total = len(profile)
        winner_match_count = sum(1 for row in profile if row["matched"])
        if winner_match_total > 0:
            winner_match_summary = (
                f"This setup matches {winner_match_count} of {winner_match_total} characteristics "
                "your winning trades typically have."
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
        for field, label, lower_word, higher_word, extractor in _CONTINUOUS_DIMENSIONS:
            avg = _continuous_average(losers, extractor)
            candidate_value = extractor(candidate)
            if avg is None or avg == 0 or candidate_value is None:
                continue
            ratio = candidate_value / avg
            # "Notably similar" is a narrower band than "notably
            # different" above -- being an echo of a losing pattern
            # should mean genuinely close, not just "not wildly off".
            if 0.85 <= ratio <= 1.15:
                loser_echoes.append(
                    f"Your losing trades on setups like this usually have a {label} around {avg:.2f} "
                    f"-- this one is {candidate_value:.2f}, very similar."
                )

    return {
        "hasEnoughData": len(winners) >= MIN_SAMPLE_FOR_GAP or len(losers) >= MIN_SAMPLE_FOR_GAP,
        "winningTradeCount": len(winners),
        "losingTradeCount": len(losers),
        "winnerGaps": winner_gaps,
        "loserEchoes": loser_echoes,
        "winnerMatchCount": winner_match_count,
        "winnerMatchTotal": winner_match_total,
        "winnerMatchSummary": winner_match_summary,
    }
