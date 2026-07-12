"""Strategy Health Engine — port of ``js/strategy_health_engine.js``.

Calculates Discipline, Execution, Risk Management, Psychology, and
Consistency components, then an overall health score/grade. Pure
aggregation over journal entries.
"""
from __future__ import annotations

from typing import Any

STRATEGY_HEALTH_VERSION = "6.0"


def _avg(values: list[Any]) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return sum(nums) / len(nums) if nums else None


def _score(entry: dict, key: str) -> float | None:
    if isinstance(entry.get(key), (int, float)) and not isinstance(entry.get(key), bool):
        return entry[key]
    ai = entry.get("ai")
    if isinstance(ai, dict) and isinstance(ai.get(key), (int, float)):
        return ai[key]
    return None


def _grade(score: float | None) -> str:
    if score is None:
        return "N/A"
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _component(key: str, percentage: float | None, explanation: str) -> dict:
    pct = None if percentage is None else max(0, min(100, round(percentage)))
    return {"key": key, "label": key, "percentage": pct, "score": pct, "grade": _grade(pct), "explanation": explanation}


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_strategy_health(entries: list[dict] | None) -> dict:
    """compute_strategy_health(entries) — port of ``computeStrategyHealth``."""
    entries = entries or []
    if not entries:
        return {
            "healthScore": None,
            "percentage": None,
            "grade": None,
            "verdict": "No trades recorded yet.",
            "components": [],
            "version": STRATEGY_HEALTH_VERSION,
        }

    rules_all = len([e for e in entries if (e.get("rulesFollowed") or "all") == "all"])
    plan_yes = len([e for e in entries if (e.get("followedPlan") or "Yes") == "Yes"])
    discipline = ((rules_all + plan_yes) / (len(entries) * 2)) * 100

    execution_scores = [v for v in (_score(e, "executionScore") for e in entries) if v is not None]
    execution = _avg(execution_scores)

    rr_vals = [v for v in (_to_float(e.get("rr")) for e in entries) if v is not None]
    rr_good = len([v for v in rr_vals if v >= 2])
    sl_recorded = len([e for e in entries if e.get("sl") not in (None, "")])
    risk = (
        (((rr_good / len(rr_vals)) if rr_vals else 0.5) + (sl_recorded / len(entries))) / 2 * 100
        if entries
        else None
    )

    calm = len([e for e in entries if e.get("emotion") in ("Calm", "Confident", "", None)])
    emotional_bad = len(
        [
            e
            for e in entries
            if e.get("emotion") in ("FOMO", "Revenge", "Anxious") or e.get("exitReason") == "Manual Close - Fear/Uncertainty"
        ]
    )
    psychology = (
        max(0.0, (calm / len(entries) * 100) - (emotional_bad / len(entries) * 30)) if entries else None
    )

    chronological = sorted(entries, key=lambda e: str(e.get("date") or ""))
    last = chronological[-10:]
    prev = chronological[-20:-10]

    def wr(rows: list[dict]) -> float | None:
        return (len([e for e in rows if (e.get("pnl") or 0) > 0]) / len(rows) * 100) if rows else None

    last_wr, prev_wr = wr(last), wr(prev)
    consistency = discipline if prev_wr is None else max(0.0, min(100.0, 70 + (last_wr - prev_wr)))

    components = [
        _component(
            "Discipline",
            discipline,
            f"{rules_all} of {len(entries)} trades followed all rules; {plan_yes} followed the written plan.",
        ),
        _component(
            "Execution",
            execution,
            "No execution scores recorded yet." if execution is None else f"Average execution score is {round(execution)}/100.",
        ),
        _component(
            "Risk Management",
            risk,
            f"{sl_recorded} trades recorded a stop loss; {rr_good} trades had at least 2R.",
        ),
        _component("Psychology", psychology, f"{emotional_bad} emotional risk event{'s' if emotional_bad != 1 else ''} detected."),
        _component(
            "Consistency",
            consistency,
            "Not enough history for trend comparison; using discipline consistency."
            if prev_wr is None
            else f"Recent win rate {last_wr:.0f}% vs prior {prev_wr:.0f}%.",
        ),
    ]

    available = [c for c in components if c["percentage"] is not None]
    health_score = round(sum(c["percentage"] for c in available) / len(available)) if available else None
    grade = _grade(health_score)
    weakest = min(available, key=lambda c: c["percentage"]) if available else None
    verdict = (
        f"{weakest['label']} is the current lowest health category at {weakest['percentage']}%."
        if weakest
        else "Not enough data to assess health."
    )

    return {
        "healthScore": health_score,
        "percentage": health_score,
        "grade": grade,
        "verdict": verdict,
        "components": components,
        "version": STRATEGY_HEALTH_VERSION,
    }
