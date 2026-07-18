"""Personal Playbook Engine (Sprint 20 Phase 3 #6).

"My Best Setups" -- for each POI type (Bullish/Bearish Order Block,
Bullish/Bearish FVG, Equilibrium, ...) the trader has actually logged,
show win rate, average R:R, best session, best day, and a couple of
example screenshots from real winning trades of that type. Reuses
``setup_engine.group_stats`` (the same sample-size-weighted win-rate/
expectancy math the Coach Deep Dive and Performance Review already
use) rather than a second, different stats implementation.

Deliberately NOT included here: "average holding time". Trades only
store a single ``date`` field, not separate entry/exit timestamps --
the MT5 auto-journal EA only ever sends a plain YYYY-MM-DD for open
and close events, never a full datetime -- so there's no honest way to
compute a holding duration yet. Adding it later needs a schema change
(entered_at/closed_at columns) and an EA update; faking a number here
instead would violate this app's one hard rule about never presenting
a guess as a real statistic.

Pure function, no I/O -- same convention as every other
``app/engines/*.py`` module.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.engines.setup_engine import SETUP_MIN_SAMPLE, group_stats

PLAYBOOK_MIN_SAMPLE = SETUP_MIN_SAMPLE
_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MAX_EXAMPLE_SCREENSHOTS = 2


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


def _poi_key(entry: dict) -> str | None:
    return entry.get("h4PoiType") or None


def _session_key(entry: dict) -> str | None:
    return entry.get("session") or None


def _entry_screenshot_url(entry: dict) -> str | None:
    for shot in entry.get("screenshots") or []:
        if isinstance(shot, dict) and shot.get("kind") == "entry" and shot.get("url"):
            return shot["url"]
    return None


def _best_row(rows: list[dict]) -> dict | None:
    """First row of an already-ranked group_stats() list that actually
    clears the minimum sample size -- rankScore alone can put a 1-trade
    100%-win-rate group in first place, which isn't a real "best
    session/day" yet, just noise."""
    for row in rows:
        if row["count"] >= PLAYBOOK_MIN_SAMPLE:
            return row
    return rows[0] if rows else None


def build_playbook(history: list[dict[str, Any]] | None) -> dict[str, Any]:
    """build_playbook(history) -> {setups: [...], sampleSize}.

    Each ``setups[]`` entry is one POI type the trader has logged at
    least ``PLAYBOOK_MIN_SAMPLE`` times, ranked the same way
    ``setup_engine.group_stats`` ranks everything else (win rate +
    expectancy, sample-size weighted) -- not a fixed list of "good"
    setups, purely what this trader's own history shows.
    """
    history = history or []
    poi_groups = [g for g in group_stats(history, _poi_key) if g["count"] >= PLAYBOOK_MIN_SAMPLE]

    setups = []
    for g in poi_groups:
        poi_type = g["key"]
        subset = [e for e in history if _poi_key(e) == poi_type]

        session_rows = group_stats(subset, _session_key)
        day_rows = group_stats(subset, lambda e: _day_name(e.get("date")))
        best_session = _best_row(session_rows)
        best_day = _best_row(day_rows)

        winners = [e for e in subset if (_num(e.get("pnl")) or 0) > 0]
        # Most-similar-first isn't meaningful here (no single candidate to
        # compare against) -- just take the most recent winners as examples,
        # newest first, since those are the freshest reminder of "this is
        # what a good one of these looks like."
        winners_sorted = sorted(winners, key=lambda e: e.get("date") or "", reverse=True)
        example_screenshots = []
        for w in winners_sorted:
            url = _entry_screenshot_url(w)
            if url and url not in example_screenshots:
                example_screenshots.append(url)
            if len(example_screenshots) >= MAX_EXAMPLE_SCREENSHOTS:
                break

        setups.append(
            {
                "poiType": poi_type,
                "count": g["count"],
                "wins": g["wins"],
                "losses": g["losses"],
                "breakeven": g["breakeven"],
                "winRate": g["winRate"],
                "averageRR": g["averageRR"],
                "expectancy": g["expectancy"],
                "bestSession": best_session["key"] if best_session else None,
                "bestSessionWinRate": best_session["winRate"] if best_session else None,
                "bestDay": best_day["key"] if best_day else None,
                "bestDayWinRate": best_day["winRate"] if best_day else None,
                "exampleScreenshots": example_screenshots,
            }
        )

    return {"setups": setups, "sampleSize": len(history)}
