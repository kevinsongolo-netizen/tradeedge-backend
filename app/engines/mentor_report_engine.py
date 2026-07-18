"""Periodic Mentor Report Engine (Sprint 20 Phase 7 -- "AI Trade Mentor").

Answers the trader's own question directly: "I want a weekly/monthly
coaching report" listing their biggest improvement, their biggest
repeated mistake, the habit costing them the most money, their best
and worst setup by money, their best pair and the one to stop trading,
and the single characteristic their winning/losing trades almost
always have.

Deliberately a THIN composition layer over engines this app already
has and already tests -- ``setup_engine.group_stats``/``analyze_
setups`` (sample-size-weighted win-rate/expectancy ranking) and
``mistake_engine.analyze_mistakes`` (habit/mistake cost tracking) --
rather than a second, parallel statistics implementation. The only new
logic here is: (a) picking a "most money" ranking off group_stats'
already-computed ``totalPnl`` (existing code ranks by win-rate+
expectancy, not raw dollars, which is a genuinely different question:
"which setup made me the most money" is not the same as "which setup
has the best win rate"), (b) comparing this period's win rate against
the PRIOR period's (net new: nothing else in this app compares two time
windows against each other), and (c) the single top winner/loser
separating characteristic (same dominant-value/tag-share math
``characteristic_gap_engine.py``/``pattern_discovery_engine.py`` already
use, kept as its own small copy here per this app's per-engine
self-containment convention).

Pure function, no I/O, no date-window slicing (the caller -- the
service layer -- splits history into period/previous-period/full-
history lists; this module only aggregates already-sliced lists).
"""
from __future__ import annotations

from typing import Any

from app.engines.mistake_engine import analyze_mistakes
from app.engines.setup_engine import SETUP_MIN_SAMPLE, group_stats

MENTOR_REPORT_MIN_SAMPLE = 3
DOMINANT_SHARE = 0.6
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


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _win_rate(entries: list[dict[str, Any]]) -> float | None:
    if not entries:
        return None
    wins = len([e for e in entries if (_num(e.get("pnl")) or 0) > 0])
    return wins / len(entries) * 100


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


def _top_separating_characteristic(winners: list[dict[str, Any]], losers: list[dict[str, Any]], *, for_winners: bool) -> str | None:
    """The single highest-margin categorical/tag separator on one side
    -- "the characteristic your winning [or losing] trades almost
    always have." Returns None when nothing clears the same honesty
    bars ``pattern_discovery_engine.py`` uses (DOMINANT_SHARE,
    MIN_SHARE_GAP)."""
    side, other = (winners, losers) if for_winners else (losers, winners)
    best: tuple[float, str] | None = None

    for field, label in _CATEGORICAL_DIMENSIONS:
        value, share = _dominant_value(side, field)
        if value is None or share < DOMINANT_SHARE:
            continue
        other_share = (sum(1 for t in other if t.get(field) == value) / len(other)) if other else 0.0
        gap = share - other_share
        if gap >= MIN_SHARE_GAP and (best is None or gap > best[0]):
            best = (gap, f"{value} {label} ({share * 100:.0f}% of your {'wins' if for_winners else 'losses'})")

    for tag, label in _TAG_DIMENSIONS:
        share = _tag_share(side, tag)
        other_share = _tag_share(other, tag)
        gap = share - other_share
        if share >= DOMINANT_SHARE and gap >= MIN_SHARE_GAP and (best is None or gap > best[0]):
            best = (gap, f"{label} ({share * 100:.0f}% of your {'wins' if for_winners else 'losses'})")

    return best[1] if best else None


def _best_worst_by_money(entries: list[dict[str, Any]], key_fn) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Ranks group_stats' output by raw totalPnl dollars (a genuinely
    different question than the win-rate+expectancy rankScore every
    other feature in this app ranks by) -- "which setup made/lost me
    the most money", gated on the same SETUP_MIN_SAMPLE confidence
    ``group_stats`` already flags."""
    rows = [g for g in group_stats(entries, key_fn) if g["confident"]]
    if not rows:
        return None, None
    best = max(rows, key=lambda g: g["totalPnl"])
    worst = min(rows, key=lambda g: g["totalPnl"])
    if best["key"] == worst["key"]:
        worst = None
    return best, worst


def build_mentor_report(
    period_entries: list[dict[str, Any]] | None,
    previous_period_entries: list[dict[str, Any]] | None,
    full_history: list[dict[str, Any]] | None,
    *,
    period_label: str = "week",
) -> dict[str, Any]:
    """build_mentor_report(period_entries, previous_period_entries,
    full_history, period_label="week"|"month") -> the periodic coaching
    report. ``full_history`` (not just this period) is used for the
    winner/loser characteristic call-outs, since those need a large
    enough sample to mean anything -- a single week rarely has enough
    trades on its own. Everything else is scoped to ``period_entries``.
    Degrades honestly: any individual field is None when there wasn't
    enough data for THAT specific comparison, never a fabricated stat.
    """
    period_entries = period_entries or []
    previous_period_entries = previous_period_entries or []
    full_history = full_history or []

    has_enough_data = len(period_entries) >= MENTOR_REPORT_MIN_SAMPLE

    biggest_improvement: str | None = None
    if has_enough_data and len(previous_period_entries) >= MENTOR_REPORT_MIN_SAMPLE:
        current_wr = _win_rate(period_entries)
        previous_wr = _win_rate(previous_period_entries)
        if current_wr is not None and previous_wr is not None:
            delta = current_wr - previous_wr
            if delta > 0:
                biggest_improvement = (
                    f"Your win rate improved from {previous_wr:.0f}% to {current_wr:.0f}% "
                    f"vs. the previous {period_label}."
                )
            elif delta < 0:
                biggest_improvement = (
                    f"Your win rate slipped from {previous_wr:.0f}% to {current_wr:.0f}% "
                    f"vs. the previous {period_label}."
                )
            else:
                biggest_improvement = f"Your win rate held steady at {current_wr:.0f}% vs. the previous {period_label}."

    biggest_repeated_mistake: str | None = None
    costliest_habit: str | None = None
    if has_enough_data:
        mistakes = analyze_mistakes(period_entries)
        common = mistakes.get("mostCommonMistake")
        if common:
            biggest_repeated_mistake = (
                f"{common['name']} -- repeated {common['count']} time{'s' if common['count'] != 1 else ''} this {period_label}."
            )
        harmful = mistakes.get("mostHarmfulHabit")
        if harmful:
            costliest_habit = (
                f"{harmful['name']} -- ${harmful['totalLoss']:.2f} in losses this {period_label}."
            )

    best_setup: str | None = None
    worst_setup: str | None = None
    if has_enough_data:
        best_row, worst_row = _best_worst_by_money(period_entries, lambda e: e.get("h4PoiType") or e.get("poi"))
        if best_row:
            best_setup = f"{best_row['key']} -- ${best_row['totalPnl']:.2f} across {best_row['count']} trades."
        if worst_row:
            worst_setup = f"{worst_row['key']} -- ${worst_row['totalPnl']:.2f} across {worst_row['count']} trades."

    best_pair: str | None = None
    pair_to_stop_trading: str | None = None
    if has_enough_data:
        pair_rows = [g for g in group_stats(period_entries, lambda e: (e.get("pair") or "").upper() or None) if g["confident"]]
        if pair_rows:
            best_pair_row = max(pair_rows, key=lambda g: g["rankScore"])
            best_pair = f"{best_pair_row['key']} -- {best_pair_row['winRate']:.0f}% win rate over {best_pair_row['count']} trades."
            worst_pair_row = min(pair_rows, key=lambda g: g["rankScore"])
            if worst_pair_row["expectancy"] < 0 and worst_pair_row["key"] != best_pair_row["key"]:
                pair_to_stop_trading = (
                    f"{worst_pair_row['key']} -- {worst_pair_row['winRate']:.0f}% win rate, "
                    f"${worst_pair_row['expectancy']:.2f} average expectancy over {worst_pair_row['count']} trades."
                )

    winner_characteristic: str | None = None
    loser_characteristic: str | None = None
    winners_full = [t for t in full_history if (_num(t.get("pnl")) or 0) > 0]
    losers_full = [t for t in full_history if (_num(t.get("pnl")) or 0) < 0]
    if len(winners_full) >= MENTOR_REPORT_MIN_SAMPLE and len(losers_full) >= MENTOR_REPORT_MIN_SAMPLE:
        winner_characteristic = _top_separating_characteristic(winners_full, losers_full, for_winners=True)
        loser_characteristic = _top_separating_characteristic(winners_full, losers_full, for_winners=False)

    return {
        "period": period_label,
        "hasEnoughData": has_enough_data,
        "periodSampleSize": len(period_entries),
        "biggestImprovement": biggest_improvement,
        "biggestRepeatedMistake": biggest_repeated_mistake,
        "costliestHabit": costliest_habit,
        "bestSetup": best_setup,
        "worstSetup": worst_setup,
        "bestPair": best_pair,
        "pairToStopTrading": pair_to_stop_trading,
        "winnerCharacteristic": winner_characteristic,
        "loserCharacteristic": loser_characteristic,
    }
