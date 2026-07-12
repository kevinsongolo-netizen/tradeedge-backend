"""Coach Engine — port of ``js/coach_engine.js``.

Generates coaching insights purely from calculated statistics/setup/
mistake/health data — no hardcoded advice strings tied to specific
values, only templated text filled in from computed numbers.
"""
from __future__ import annotations

from typing import Any

from app.engines.mistake_engine import analyze_mistakes
from app.engines.setup_engine import analyze_setups
from app.engines.statistics_engine import compute_statistics
from app.engines.strategy_health_engine import compute_strategy_health

COACH_ENGINE_VERSION = "6.0"


def _score(entry: dict, key: str) -> float | None:
    if isinstance(entry.get(key), (int, float)) and not isinstance(entry.get(key), bool):
        return entry[key]
    ai = entry.get("ai")
    if isinstance(ai, dict) and isinstance(ai.get(key), (int, float)):
        return ai[key]
    return None


def _avg(values: list[Any]) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return sum(nums) / len(nums) if nums else None


def _win_rate(entries: list[dict]) -> float | None:
    return (len([e for e in entries if (e.get("pnl") or 0) > 0]) / len(entries) * 100) if entries else None


def generate_coach_insights(entries: list[dict] | None, calculated: dict | None = None) -> list[dict]:
    """generate_coach_insights(entries, calculated=None) — port of
    ``generateCoachInsights``. If ``calculated`` (pre-computed
    statistics/setup/mistakes/strategyHealth) isn't supplied, this runs
    the other engines itself, exactly like the JS version."""
    entries = entries or []
    insights: list[dict] = []
    if len(entries) < 2:
        return [
            {
                "level": "info",
                "text": f"Journal has {len(entries)} trade{'s' if len(entries) != 1 else ''}; coaching insights need more completed trades.",
            }
        ]

    calculated = calculated or {}
    stats = calculated.get("statistics") or compute_statistics(entries)
    setups = calculated.get("setup") or analyze_setups(entries)
    mistakes = calculated.get("mistakes") or analyze_mistakes(entries)
    health = calculated.get("strategyHealth") or compute_strategy_health(entries)

    chronological = sorted(entries, key=lambda e: str(e.get("date") or ""))
    recent = chronological[-20:]
    previous = chronological[-40:-20]
    recent_rule = _avg([_score(e, "ruleScore") for e in recent])
    previous_rule = _avg([_score(e, "ruleScore") for e in previous])
    if recent_rule is not None and previous_rule is not None:
        delta = recent_rule - previous_rule
        insights.append(
            {
                "level": "positive" if delta >= 0 else "warning",
                "text": (
                    f"Your Rule Score {'improved' if delta >= 0 else 'declined'} by {abs(delta):.0f} points over the "
                    f"last {len(recent)} trades compared with the prior {len(previous)}."
                ),
            }
        )

    if setups.get("bestSetup"):
        top_candidates = [setups["top"].get(k) for k in ("pair", "session", "poi") if setups["top"].get(k)]
        if top_candidates:
            sample = min(t["count"] for t in top_candidates)
            insights.append(
                {
                    "level": "positive",
                    "text": (
                        f"Your highest-performing setup is {setups['bestSetup']}, based on journal groups with up to "
                        f"{sample} matching trade{'s' if sample != 1 else ''}."
                    ),
                }
            )

    with_m15 = [e for e in entries if isinstance(e.get("m15Confirmations"), list) and e["m15Confirmations"]]
    without_m15 = [e for e in entries if not isinstance(e.get("m15Confirmations"), list) or not e["m15Confirmations"]]
    with_wr, without_wr = _win_rate(with_m15), _win_rate(without_m15)
    if len(with_m15) >= 2 and len(without_m15) >= 2 and with_wr is not None and without_wr is not None and without_wr + 5 < with_wr:
        insights.append(
            {
                "level": "warning",
                "text": f"Trades without M15 confirmation win {without_wr:.0f}% versus {with_wr:.0f}% with confirmation.",
            }
        )

    lost_profit = mistakes.get("lostProfit") or {}
    if lost_profit.get("earlyExit", 0) > 0:
        insights.append(
            {"level": "warning", "text": f"Closing trades early is estimated to have reduced profit by ${lost_profit['earlyExit']:.2f}."}
        )

    if mistakes.get("mostProfitableHabit"):
        h = mistakes["mostProfitableHabit"]
        insights.append(
            {
                "level": "positive",
                "text": (
                    f"Your strongest habit is {h['name']}: {h['count']} trade{'s' if h['count'] != 1 else ''}, "
                    f"{h['winRate']:.0f}% win rate, and {'+' if h['pnl'] >= 0 else '-'}${abs(h['pnl']):.2f} total P&L."
                ),
            }
        )

    if mistakes.get("mostHarmfulHabit"):
        h = mistakes["mostHarmfulHabit"]
        insights.append({"level": "warning", "text": f"Your most harmful habit is {h['name']}, linked to -${h['totalLoss']:.2f} in losses."})

    if setups["top"].get("session"):
        s = setups["top"]["session"]
        insights.append(
            {
                "level": "positive" if s["winRate"] >= 50 else "warning",
                "text": f"You perform best during the {s['key']} session: {s['winRate']:.0f}% win rate over {s['count']} trade{'s' if s['count'] != 1 else ''}.",
            }
        )

    components = [c for c in (health.get("components") or []) if c.get("percentage") is not None]
    if components:
        weakest = min(components, key=lambda c: c["percentage"])
        insights.append(
            {
                "level": "positive" if weakest["percentage"] >= 80 else "warning",
                "text": f"{weakest['label']} is {weakest['percentage']}% ({weakest['grade']}). {weakest['explanation']}",
            }
        )

    if stats.get("averageOverallScore") is not None:
        insights.append(
            {
                "level": "positive" if stats["averageOverallScore"] >= 80 else "info",
                "text": (
                    f"Average Overall Score is {round(stats['averageOverallScore'])}/100 across "
                    f"{stats['totalTrades']} completed trade{'s' if stats['totalTrades'] != 1 else ''}."
                ),
            }
        )

    seen: set[str] = set()
    unique: list[dict] = []
    for item in insights:
        if item["text"] not in seen:
            seen.add(item["text"])
            unique.append(item)
    return unique[:6]
