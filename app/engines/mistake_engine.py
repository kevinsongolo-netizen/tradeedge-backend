"""Mistake Engine — port of ``js/mistake_engine.js``.

Detects repeated, expensive, emotional, and habit-driven mistakes, and
estimates lost profit per error category versus a clean-trade baseline.
Pure aggregation over journal entries.
"""
from __future__ import annotations

from typing import Any

MISTAKE_ENGINE_VERSION = "6.0"


def _text(entry: dict) -> str:
    parts = [entry.get("failed"), entry.get("notes"), *(entry.get("failedTags") or [])]
    return " ".join(str(p) for p in parts if p is not None).lower()


def _has(entry: dict, terms: list[str]) -> bool:
    haystack = _text(entry)
    return any(t.lower() in haystack for t in terms)


def _avg_pnl(entries: list[dict]) -> float:
    return (sum(float(e.get("pnl") or 0) for e in entries) / len(entries)) if entries else 0.0


def _win_rate(entries: list[dict]) -> float | None:
    return (len([e for e in entries if (e.get("pnl") or 0) > 0]) / len(entries) * 100) if entries else None


def _top_count(groups: dict[str, dict]) -> dict | None:
    if not groups:
        return None
    name, data = max(groups.items(), key=lambda kv: (kv[1]["count"], abs(kv[1]["pnl"])))
    return {"name": name, **data}


def _top_loss(groups: dict[str, dict]) -> dict | None:
    """The single worst-losing group by net P&L -- but only among
    groups that have ACTUALLY lost money (net pnl < 0).

    Bug found via user report (Sprint 22 follow-up): with the old
    ``min(groups.items(), ...)``, a group with only one breakeven or
    winning trade still "won" the min() comparison whenever it was the
    only group present (or tied at 0), producing the nonsensical
    "X has cost $0.00 across 1 trade" / "linked to $0.00 in losses" --
    a habit/mistake tag that hasn't actually cost anything shouldn't be
    reported as the most harmful/expensive one. Returning None here
    lets both call sites (mostExpensiveMistake, mostHarmfulHabit) fall
    back to their existing "not enough data yet" honesty pattern
    instead of fabricating a hollow headline."""
    losing = {name: data for name, data in groups.items() if data["pnl"] < 0}
    if not losing:
        return None
    name, data = min(losing.items(), key=lambda kv: kv[1]["pnl"])
    return {"name": name, **data, "totalLoss": abs(data["pnl"])}


def _habit_groups(entries: list[dict], tag_key: str) -> dict[str, dict]:
    groups: dict[str, dict] = {}
    for e in entries:
        for tag in e.get(tag_key) or []:
            g = groups.setdefault(tag, {"count": 0, "pnl": 0.0, "wins": 0})
            g["count"] += 1
            g["pnl"] += float(e.get("pnl") or 0)
            if (e.get("pnl") or 0) > 0:
                g["wins"] += 1
    return groups


def analyze_mistakes(entries: list[dict] | None) -> dict:
    """analyze_mistakes(entries) — port of ``analyzeMistakes``."""
    entries = entries or []
    mistake_groups: dict[str, dict] = {}
    rule_groups: dict[str, dict] = {}
    emotion_groups: dict[str, dict] = {}

    def add_group(group: dict[str, dict], key: str | None, pnl: Any) -> None:
        if not key:
            return
        g = group.setdefault(key, {"count": 0, "pnl": 0.0})
        g["count"] += 1
        g["pnl"] += float(pnl or 0)

    for e in entries:
        for tag in e.get("failedTags") or []:
            add_group(mistake_groups, tag, e.get("pnl"))
        if e.get("rulesFollowed") and e["rulesFollowed"] != "all":
            add_group(rule_groups, e["rulesFollowed"], e.get("pnl"))
        for r in e.get("ruleReasons") or []:
            if not r.get("ok"):
                add_group(rule_groups, r.get("text"), e.get("pnl"))
        if e.get("emotion") in ("FOMO", "Revenge", "Anxious", "Bored"):
            add_group(emotion_groups, e["emotion"], e.get("pnl"))
        if e.get("exitReason") == "Manual Close - Fear/Uncertainty":
            add_group(emotion_groups, "Fear/Uncertainty Exit", e.get("pnl"))

    worked_habits = _habit_groups(entries, "workedTags")
    profitable_habit = _top_count(dict(sorted(worked_habits.items(), key=lambda kv: kv[1]["pnl"], reverse=True)))
    harmful_habit = _top_loss(_habit_groups(entries, "failedTags"))

    categories = {
        "earlyExit": [
            e for e in entries if e.get("exitReason") == "Manual Close - Fear/Uncertainty" or _has(e, ["early exit", "closed early"])
        ],
        "fomo": [e for e in entries if e.get("emotion") == "FOMO" or _has(e, ["fomo", "chased", "late entry"])],
        "revengeTrading": [e for e in entries if e.get("emotion") == "Revenge" or _has(e, ["revenge"])],
        "counterTrend": [
            e
            for e in entries
            if _has(e, ["counter trend", "counter-trend"])
            or (e.get("h4Trend") == "Bullish" and e.get("direction") == "sell")
            or (e.get("h4Trend") == "Bearish" and e.get("direction") == "buy")
        ],
        "poorRR": [e for e in entries if isinstance(e.get("rr"), (int, float)) and e["rr"] < 1.5 and not isinstance(e.get("rr"), bool)],
    }
    # rr may arrive as string; normalize via parseFloat-equivalent check
    def _rr_below(e: dict) -> bool:
        try:
            return float(e.get("rr")) < 1.5
        except (TypeError, ValueError):
            return False

    categories["poorRR"] = [e for e in entries if _rr_below(e)]

    excluded_ids = set()
    for rows in categories.values():
        excluded_ids.update(id(e) for e in rows)
    clean_trades = [e for e in entries if id(e) not in excluded_ids]
    baseline = _avg_pnl(clean_trades) if clean_trades else _avg_pnl([e for e in entries if (e.get("pnl") or 0) > 0])

    lost_profit = {}
    for key, rows in categories.items():
        actual = sum(float(e.get("pnl") or 0) for e in rows)
        expected = len(rows) * baseline
        lost_profit[key] = max(0.0, expected - actual)

    most_common_mistake = _top_count(mistake_groups)
    most_expensive_mistake = _top_loss(mistake_groups)
    most_common_rule_violation = _top_count(rule_groups)
    most_common_emotional_mistake = _top_count(emotion_groups)

    top_mistakes: list[str] = []
    if most_expensive_mistake:
        top_mistakes.append(
            f"{most_expensive_mistake['name']} has cost ${most_expensive_mistake['totalLoss']:.2f} across "
            f"{most_expensive_mistake['count']} trade{'s' if most_expensive_mistake['count'] != 1 else ''}."
        )
    if most_common_rule_violation:
        top_mistakes.append(
            f"{most_common_rule_violation['name']} is your most common rule violation "
            f"({most_common_rule_violation['count']} time{'s' if most_common_rule_violation['count'] != 1 else ''})."
        )
    if most_common_emotional_mistake:
        top_mistakes.append(
            f"{most_common_emotional_mistake['name']} is your most common emotional mistake "
            f"({most_common_emotional_mistake['count']} time{'s' if most_common_emotional_mistake['count'] != 1 else ''})."
        )
    for key, value in sorted(lost_profit.items(), key=lambda kv: kv[1], reverse=True)[:2]:
        if value > 0:
            label = "".join(f" {c.lower()}" if c.isupper() else c for c in key).strip()
            top_mistakes.append(f"{label} is estimated to have reduced profit by ${value:.2f}.")

    return {
        "mostCommonMistake": most_common_mistake,
        "mostCommonTag": {"tag": most_common_mistake["name"], "count": most_common_mistake["count"]} if most_common_mistake else None,
        "mostExpensiveMistake": most_expensive_mistake,
        "mostExpensiveTag": (
            {"tag": most_expensive_mistake["name"], "totalLoss": most_expensive_mistake["totalLoss"]}
            if most_expensive_mistake
            else None
        ),
        "mostCommonRuleViolation": most_common_rule_violation,
        "mostCommonEmotionalMistake": most_common_emotional_mistake,
        "mostProfitableHabit": (
            {
                "name": profitable_habit["name"],
                "count": profitable_habit["count"],
                "pnl": profitable_habit["pnl"],
                "winRate": (profitable_habit["wins"] / profitable_habit["count"] * 100) if profitable_habit["count"] else 0,
            }
            if profitable_habit
            else None
        ),
        "mostHarmfulHabit": (
            {
                "name": harmful_habit["name"],
                "count": harmful_habit["count"],
                "pnl": harmful_habit["pnl"],
                "totalLoss": harmful_habit["totalLoss"],
            }
            if harmful_habit
            else None
        ),
        "lostProfit": lost_profit,
        "categoryStats": {
            key: {"count": len(rows), "winRate": _win_rate(rows), "averagePnl": _avg_pnl(rows)} for key, rows in categories.items()
        },
        "topMistakes": top_mistakes,
        "version": MISTAKE_ENGINE_VERSION,
    }
