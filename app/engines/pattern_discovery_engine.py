"""Screenshot/History Pattern-Discovery Engine (Sprint 20 Phase 6).

Answers the trader's own question directly: "learn from my screenshots
-- discover things like 'my winning trades usually have fresh Order
Blocks' automatically." Unlike ``characteristic_gap_engine`` (which
compares ONE current/candidate setup against the trader's winner/loser
profile), this engine looks at the trader's ENTIRE history at once and
surfaces standalone narrative statements about what tends to separate
their wins from their losses -- no candidate setup needed, this is
purely "what has my own screenshot history taught me so far."

Reuses the same dominant-value/tag-presence-share math
``characteristic_gap_engine`` already uses (kept as its own small
copies here per this app's per-engine self-containment convention),
applied to the FULL winner subset vs. the FULL loser subset instead of
one candidate vs. one subset.

Only ever states a pattern when there's real separation between the
two subsets (a dominant value/tag on one side that ISN'T also dominant
on the other, by at least ``MIN_SHARE_GAP``) -- never invents a pattern
from a dimension this app doesn't actually have data for (e.g. "stayed
inside the zone too long" would need time-in-zone data this app
doesn't capture, so it's never surfaced, even though the trader's own
example wording mentioned something like it). Below ``MIN_SAMPLE``
trades on either side, the whole comparison is skipped and
``hasEnoughData`` is false -- same honesty bar (3) used everywhere else
in this app (see ``characteristic_gap_engine.MIN_SAMPLE_FOR_GAP``,
``setup_insight_engine.MIN_SIMILAR_FOR_CONFIDENT_STAT``,
``trade_lesson_engine.MIN_SIMILAR_FOR_LESSON``, ``edge_pattern_engine.
EDGE_MIN_SAMPLE``, ``playbook_engine.PLAYBOOK_MIN_SAMPLE``).

Pure function, no I/O -- same convention as every other
``app/engines/*.py`` module.
"""
from __future__ import annotations

from typing import Any

MIN_SAMPLE = 3
DOMINANT_SHARE = 0.6
# How much lower the OTHER side's share needs to be for a dimension to
# count as a real separator rather than noise -- e.g. winners 70%
# London / losers 55% London isn't a real pattern; winners 70% / losers
# 20% is.
MIN_SHARE_GAP = 0.3

_CATEGORICAL_DIMENSIONS: list[tuple[str, str]] = [
    ("h4PoiType", "point-of-interest type"),
    ("premiumDiscount", "zone"),
    ("session", "session"),
    ("h4Trend", "trend"),
]

_TAG_DIMENSIONS: list[tuple[str, str]] = [
    ("BOS", "a break of structure"),
    ("CHOCH", "a change of character"),
    ("Liquidity Sweep", "a liquidity sweep"),
    ("FVG", "an FVG"),
    ("Fresh Order Block", "a fresh, untested Order Block"),
    ("Mitigated Order Block", "an already-mitigated Order Block"),
    ("Strong Rejection", "a strong rejection candle"),
    ("Large FVG", "a large Fair Value Gap"),
]


def _dominant_value(trades: list[dict[str, Any]], field: str) -> tuple[Any, float]:
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


def _tag_share(trades: list[dict[str, Any]], tag: str) -> float:
    if not trades:
        return 0.0
    present = sum(1 for t in trades if tag in (t.get("m15Confirmations") or []))
    return present / len(trades)


def build_discovered_patterns(history: list[dict[str, Any]] | None) -> dict[str, Any]:
    """build_discovered_patterns(history) -> {patterns: [...],
    winningTradeCount, losingTradeCount, hasEnoughData}.

    Each ``patterns[]`` entry is one plain-language sentence describing
    a real separation this trader's own winning trades and losing
    trades show on some dimension -- purely descriptive, never a
    recommendation or a rule to follow."""
    history = history or []
    winners = [t for t in history if (t.get("pnl") or 0) > 0]
    losers = [t for t in history if (t.get("pnl") or 0) < 0]

    patterns: list[str] = []

    if len(winners) >= MIN_SAMPLE and len(losers) >= MIN_SAMPLE:
        for field, label in _CATEGORICAL_DIMENSIONS:
            w_value, w_share = _dominant_value(winners, field)
            if w_value is None or w_share < DOMINANT_SHARE:
                continue
            same_value_count = sum(1 for t in losers if t.get(field) == w_value)
            same_value_share = same_value_count / len(losers) if losers else 0.0
            if same_value_share <= w_share - MIN_SHARE_GAP:
                patterns.append(
                    f"Your winning trades usually happen in the {w_value} {label} "
                    f"({w_share * 100:.0f}% of {len(winners)} wins) -- only "
                    f"{same_value_share * 100:.0f}% of your losing trades share that."
                )

        for tag, label in _TAG_DIMENSIONS:
            w_share = _tag_share(winners, tag)
            l_share = _tag_share(losers, tag)
            if w_share >= DOMINANT_SHARE and (w_share - l_share) >= MIN_SHARE_GAP:
                patterns.append(
                    f"Your winning trades usually have {label} ({w_share * 100:.0f}% of "
                    f"{len(winners)} wins) -- your losing trades usually don't "
                    f"({l_share * 100:.0f}% of {len(losers)} losses)."
                )
            elif l_share >= DOMINANT_SHARE and (l_share - w_share) >= MIN_SHARE_GAP:
                patterns.append(
                    f"Your losing trades usually have {label} ({l_share * 100:.0f}% of "
                    f"{len(losers)} losses) -- your winning trades usually don't "
                    f"({w_share * 100:.0f}% of {len(winners)} wins)."
                )

    return {
        "patterns": patterns,
        "winningTradeCount": len(winners),
        "losingTradeCount": len(losers),
        "hasEnoughData": len(winners) >= MIN_SAMPLE and len(losers) >= MIN_SAMPLE,
    }
