"""Statistics Engine — port of ``js/statistics_engine.js``.

Pure aggregation over journal entries: win/loss/profit-factor/expectancy
core numbers, plus group breakdowns (by pair/asset/session/day/POI/trend)
and rolling chart series. In-process caching (``cachetools``-free — a
simple module-level fingerprint, matching the JS ``STATISTICS_CACHE_KEY``
pattern) avoids recomputation when nothing changed.
"""
from __future__ import annotations

import math
from datetime import date as date_, datetime
from typing import Any

STATISTICS_ENGINE_VERSION = "6.0"

_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_cache_key: str | None = None
_cache_value: dict | None = None


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def _avg(values: list[Any]) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)]
    return sum(nums) / len(nums) if nums else None


def _day_name(date_str: Any) -> str | None:
    if not date_str:
        return None
    try:
        d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return _DAY_NAMES[d.weekday()]


def _score(entry: dict, key: str) -> float | None:
    value = entry.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    ai = entry.get("ai")
    if isinstance(ai, dict) and isinstance(ai.get(key), (int, float)):
        return ai[key]
    return None


def _cache_key_for(entries: list[dict]) -> str:
    return "|".join(
        ":".join(
            str(e.get(k, ""))
            for k in ("id", "date", "pnl", "rr", "ruleScore", "executionScore", "overallScore", "pair", "session", "poi", "h4Trend")
        )
        for e in entries
    )


def _streaks(entries: list[dict]) -> dict:
    chronological = sorted(entries, key=lambda e: str(e.get("date") or ""))
    consecutive_wins = consecutive_losses = current_wins = current_losses = 0
    for e in chronological:
        pnl = e.get("pnl") or 0
        if pnl > 0:
            current_wins += 1
            current_losses = 0
            consecutive_wins = max(consecutive_wins, current_wins)
        elif pnl < 0:
            current_losses += 1
            current_wins = 0
            consecutive_losses = max(consecutive_losses, current_losses)
        else:
            current_wins = current_losses = 0

    current_winning_streak = current_losing_streak = 0
    for e in reversed(chronological):
        pnl = e.get("pnl") or 0
        if pnl > 0 and current_losing_streak == 0:
            current_winning_streak += 1
        elif pnl < 0 and current_winning_streak == 0:
            current_losing_streak += 1
        else:
            break

    return {
        "consecutiveWins": consecutive_wins,
        "consecutiveLosses": consecutive_losses,
        "currentWinningStreak": current_winning_streak,
        "currentLosingStreak": current_losing_streak,
    }


def statistics_core(entries: list[dict] | None) -> dict:
    """statisticsCore(entries) — win rate, profit factor, expectancy,
    averages, and streaks for one slice of trades."""
    entries = entries or []
    wins = [e for e in entries if (e.get("pnl") or 0) > 0]
    losses = [e for e in entries if (e.get("pnl") or 0) < 0]
    breakeven = [e for e in entries if (e.get("pnl") or 0) == 0]
    total_wins = sum(float(e.get("pnl") or 0) for e in wins)
    total_losses_signed = sum(float(e.get("pnl") or 0) for e in losses)
    total_losses = abs(total_losses_signed)
    total_pnl = sum(float(e.get("pnl") or 0) for e in entries)
    rr_values = [v for v in (_num(e.get("rr")) for e in entries) if v is not None]
    rule_scores = [v for v in (_score(e, "ruleScore") for e in entries) if v is not None]
    execution_scores = [v for v in (_score(e, "executionScore") for e in entries) if v is not None]
    overall_scores = [v for v in (_score(e, "overallScore") for e in entries) if v is not None]
    largest_win = max((float(e.get("pnl") or 0) for e in wins), default=0)
    largest_loss = min((float(e.get("pnl") or 0) for e in losses), default=0)

    n = len(entries)
    if total_losses > 0:
        profit_factor = total_wins / total_losses
    elif total_wins > 0:
        profit_factor = math.inf
    else:
        profit_factor = 0.0

    result = {
        "totalTrades": n,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakeven),
        "winRate": (len(wins) / n * 100) if n else 0.0,
        "lossRate": (len(losses) / n * 100) if n else 0.0,
        "breakevenRate": (len(breakeven) / n * 100) if n else 0.0,
        "totalPnl": total_pnl,
        "profitFactor": profit_factor,
        "expectancy": (total_pnl / n) if n else 0.0,
        "averageWin": (total_wins / len(wins)) if wins else 0.0,
        "averageLoss": (total_losses / len(losses)) if losses else 0.0,
        "averageRR": _avg(rr_values),
        "averageRuleScore": _avg(rule_scores),
        "averageExecutionScore": _avg(execution_scores),
        "averageOverallScore": _avg(overall_scores),
        "highestScore": max(overall_scores) if overall_scores else None,
        "lowestScore": min(overall_scores) if overall_scores else None,
        "tradesAbove90": len([v for v in overall_scores if v >= 90]),
        "tradesBelow70": len([v for v in overall_scores if v < 70]),
        "largestWin": largest_win,
        "largestLoss": largest_loss,
    }
    result.update(_streaks(entries))
    return result


def statistics_by(entries: list[dict], key_fn) -> dict[str, dict]:
    groups: dict[str, list[dict]] = {}
    for e in entries or []:
        key = key_fn(e) or "Unspecified"
        groups.setdefault(key, []).append(e)
    return {key: statistics_core(rows) for key, rows in groups.items()}


def compute_statistics(entries: list[dict] | None) -> dict:
    """compute_statistics(entries) — port of ``computeAiStatistics``.
    Full performance + AI score statistics plus group breakdowns."""
    global _cache_key, _cache_value
    entries = entries or []
    key = _cache_key_for(entries)
    if key == _cache_key and _cache_value is not None:
        return _cache_value

    core = statistics_core(entries)
    result = {
        **core,
        "avgScore": round(core["averageRuleScore"]) if core["averageRuleScore"] is not None else None,
        "scoredCount": len([e for e in entries if _score(e, "ruleScore") is not None]),
        "byPair": statistics_by(entries, lambda e: str(e["pair"]).upper() if e.get("pair") else None),
        "byAsset": statistics_by(entries, lambda e: e.get("asset")),
        "bySession": statistics_by(entries, lambda e: e.get("session")),
        "byDay": statistics_by(entries, lambda e: _day_name(e.get("date"))),
        "byPOI": statistics_by(entries, lambda e: e.get("h4PoiType") or e.get("poi")),
        "byTrend": statistics_by(entries, lambda e: e.get("h4Trend")),
        "version": STATISTICS_ENGINE_VERSION,
    }

    winning_scored = [_score(e, "ruleScore") for e in entries if (e.get("pnl") or 0) > 0 and _score(e, "ruleScore") is not None]
    losing_scored = [_score(e, "ruleScore") for e in entries if (e.get("pnl") or 0) < 0 and _score(e, "ruleScore") is not None]
    avg_win_score = _avg(winning_scored)
    avg_lose_score = _avg(losing_scored)
    result["avgWinningScore"] = round(avg_win_score) if avg_win_score is not None else None
    result["avgLosingScore"] = round(avg_lose_score) if avg_lose_score is not None else None

    best_pair = _top_group_key(result["byPair"])
    best_session = _top_group_key(result["bySession"])
    result["bestPair"] = best_pair
    result["bestSession"] = best_session
    result["bestSetup"] = None
    result["worstSetup"] = None

    _cache_key, _cache_value = key, result
    return result


def _top_group_key(groups: dict[str, dict], min_sample: int = 1) -> str | None:
    candidates = [(k, v) for k, v in groups.items() if v["totalTrades"] >= min_sample]
    if not candidates:
        return None
    candidates.sort(key=lambda kv: (kv[1]["winRate"], kv[1]["totalTrades"]), reverse=True)
    return candidates[0][0]


def _rolling(entries: list[dict], selector, window: int) -> list[dict]:
    sorted_entries = sorted(entries or [], key=lambda e: str(e.get("date") or ""))
    points = []
    for index, entry in enumerate(sorted_entries):
        window_slice = sorted_entries[max(0, index - window + 1) : index + 1]
        value = selector(window_slice, entry)
        points.append({"date": entry.get("date"), "value": value, "label": entry.get("pair") or entry.get("date")})
    return [p for p in points if isinstance(p["value"], (int, float)) and math.isfinite(p["value"])]


def build_chart_data(entries: list[dict] | None) -> dict:
    """build_chart_data(entries) — port of ``buildAiChartData``. Data
    series only; rendering stays in the frontend."""
    entries = entries or []

    def score_series(key: str) -> list[dict]:
        return _rolling(entries, lambda _slice, entry: _score(entry, key), 1)

    window = 10
    win_rate_trend = _rolling(
        entries, lambda s, _e: (len([x for x in s if (x.get("pnl") or 0) > 0]) / len(s) * 100) if s else None, window
    )

    def profit_factor(slice_: list[dict], _entry) -> float:
        wins = sum(e.get("pnl", 0) for e in slice_ if (e.get("pnl") or 0) > 0)
        losses = abs(sum(e.get("pnl", 0) for e in slice_ if (e.get("pnl") or 0) < 0))
        return (wins / losses) if losses > 0 else (3.0 if wins > 0 else 0.0)

    profit_factor_trend = _rolling(entries, profit_factor, window)

    def month_key(e: dict) -> str | None:
        d = str(e.get("date") or "")
        return d[:7] or None

    def group_to_series(stats_obj: dict, value_key: str) -> list[dict]:
        return [
            {"label": label, "value": stats.get(value_key) or 0, "count": stats["totalTrades"]}
            for label, stats in stats_obj.items()
        ]

    return {
        "ruleScoreTrend": score_series("ruleScore"),
        "executionScoreTrend": score_series("executionScore"),
        "overallScoreTrend": score_series("overallScore"),
        "winRateTrend": win_rate_trend,
        "profitFactorTrend": profit_factor_trend,
        "monthlyPerformance": group_to_series(statistics_by(entries, month_key), "totalPnl"),
        "sessionPerformance": group_to_series(statistics_by(entries, lambda e: e.get("session")), "totalPnl"),
        "pairPerformance": group_to_series(
            statistics_by(entries, lambda e: str(e["pair"]).upper() if e.get("pair") else None), "totalPnl"
        ),
    }
