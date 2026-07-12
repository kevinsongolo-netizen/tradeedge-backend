"""Sprint 8 — Personal Trading Coach deep dive (Vision Phase 6).

Answers the specific questions the vision doc lists ("why am I losing?
why am I winning? what is my biggest mistake? which setup makes the
most money? which loses the most? which day should I avoid? which
session is best? which pair should I stop trading?") by re-packaging
Sprint 6's existing ``analyze_setups()``/``analyze_mistakes()``/
``compute_strategy_health()`` output into named fields, rather than
recomputing anything — those engines already rank every dimension
(pair/session/day/POI/confirmation-combo) by a sample-size-weighted
win-rate + expectancy score. Pure function, no DB, no HTTP.
"""
from __future__ import annotations

from typing import Any

COACH_DEEP_DIVE_VERSION = "8.0"

#: A dimension needs at least this many trades before its worst row is
#: surfaced as "stop trading this" advice — same threshold
#: ``app/engines/setup_engine.py`` already uses for its own
#: ``confident`` flag, reused here for consistency.
MIN_SAMPLE_FOR_WARNING = 3


def _worst_confident_row(rows: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """The lowest-ranked row that still has enough samples to trust —
    ``setup_engine.group_stats()`` already sorts best-first, so this is
    just "the last row with confident=True", not a fresh re-sort (which
    would treat a single-trade -100% pair the same as a well-sampled
    genuinely-bad one)."""
    candidates = [r for r in (rows or []) if r.get("confident")]
    if not candidates:
        return None
    return min(candidates, key=lambda r: r["rankScore"])


def _why_losing(mistakes: dict[str, Any], weakest_health: dict[str, Any] | None) -> str:
    parts: list[str] = []
    harmful = mistakes.get("mostHarmfulHabit")
    if harmful:
        parts.append(f"Your most harmful habit is {harmful['name']}, linked to ${harmful['totalLoss']:.2f} in losses.")
    expensive = mistakes.get("mostExpensiveMistake")
    if expensive:
        parts.append(
            f"{expensive['name']} has cost ${expensive['totalLoss']:.2f} across "
            f"{expensive['count']} trade{'s' if expensive['count'] != 1 else ''}."
        )
    if weakest_health:
        parts.append(
            f"{weakest_health['label']} is your weakest area at {weakest_health['percentage']}% ({weakest_health['grade']})."
        )
    return " ".join(parts) if parts else "Not enough data yet to identify a clear pattern in your losses."


def _why_winning(mistakes: dict[str, Any], best_setup_row: dict[str, Any] | None) -> str:
    parts: list[str] = []
    profitable = mistakes.get("mostProfitableHabit")
    if profitable:
        parts.append(
            f"Your strongest habit is {profitable['name']}: {profitable['count']} "
            f"trade{'s' if profitable['count'] != 1 else ''} at a {profitable['winRate']:.0f}% win rate."
        )
    if best_setup_row:
        parts.append(
            f"Your best-performing setup is {best_setup_row['key']}: {best_setup_row['winRate']:.0f}% win rate "
            f"over {best_setup_row['count']} trade{'s' if best_setup_row['count'] != 1 else ''}."
        )
    return " ".join(parts) if parts else "Not enough data yet to identify a clear pattern in your wins."


def build_deep_dive(statistics: dict[str, Any], mistakes: dict[str, Any], setups: dict[str, Any], health: dict[str, Any]) -> dict[str, Any]:
    """build_deep_dive(statistics, mistakes, setups, health) — Phase 6's
    structured Q&A. All four arguments are the outputs of Sprint 6's
    ``compute_statistics``/``analyze_mistakes``/``analyze_setups``/
    ``compute_strategy_health`` for the same trade history."""
    by_dimension = setups.get("byDimension", {})
    top = setups.get("top", {})

    best_session = top.get("session")
    worst_day = _worst_confident_row(by_dimension.get("day"))
    worst_pair_row = _worst_confident_row(by_dimension.get("pair"))
    best_setup_row = top.get("poi") or top.get("confirmation")
    worst_setup_row = _worst_confident_row(by_dimension.get("poi")) or _worst_confident_row(by_dimension.get("confirmation"))

    components = [c for c in (health.get("components") or []) if c.get("percentage") is not None]
    weakest_health = min(components, key=lambda c: c["percentage"]) if components else None

    pair_to_stop_trading = (
        worst_pair_row
        if worst_pair_row and worst_pair_row["expectancy"] < 0 and worst_pair_row["count"] >= MIN_SAMPLE_FOR_WARNING
        else None
    )

    return {
        "whyLosing": _why_losing(mistakes, weakest_health),
        "whyWinning": _why_winning(mistakes, best_setup_row),
        "biggestMistake": mistakes.get("mostExpensiveMistake"),
        "bestSetup": best_setup_row,
        "worstSetup": worst_setup_row,
        "worstDayToTrade": worst_day,
        "bestSession": best_session,
        "pairToStopTrading": pair_to_stop_trading,
        "sampleSize": setups.get("sampleSize", 0),
        "version": COACH_DEEP_DIVE_VERSION,
    }
