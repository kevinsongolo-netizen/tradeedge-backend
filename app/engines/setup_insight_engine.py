"""Setup Insight Engine (Sprint 20 — screenshot-first workflow).

Replaces the old rule-based Level 2/3 validators
(``app/_legacy/personal_averaging_strategy.py`` and friends) for the
new workflow: instead of checking a setup against a fixed list of
Smart Money rules and returning PASS/FAIL, this engine compares a
freshly-read screenshot's setup against the trader's OWN trade history
(via the existing weighted similarity search in
``app/engines/similar_engine.py``) and returns a plain-language
insight -- never a VALID/INVALID verdict, never a recommendation to
take or skip the trade. That decision stays entirely with the trader;
this only answers "have I seen something like this before, and how did
it go?"

Pure function, no I/O, no database access -- the caller (chart
service) is responsible for fetching trade history and passing it in,
same convention as every other engine in this app.
"""
from __future__ import annotations

from typing import Any

from app.engines.similar_engine import search_similar

MIN_TOTAL_HISTORY_FOR_INSIGHT = 5
DEFAULT_MIN_SIMILARITY = 40.0
DEFAULT_LIMIT = 10
TOP_SIMILAR_DISPLAY_COUNT = 5


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def candidate_from_vision_extraction(extraction: dict[str, Any]) -> dict[str, Any]:
    """Maps the vision provider's raw screenshot-read fields (see
    ``app/chart/vision_provider.py``'s ``VISION_ANALYSIS_SCHEMA_HINT``)
    onto the same field names ``search_similar``/the trade history
    already use (``Trade.to_engine_dict()``'s shape) -- so a freshly
    read screenshot can be compared against real logged trades with no
    extra translation layer at the call site."""
    direction_raw = (extraction.get("orderDirection") or "").upper()
    direction = "buy" if direction_raw == "BUY" else "sell" if direction_raw == "SELL" else None

    tags: list[str] = []
    latest_event = (extraction.get("latestEvent") or "")
    liquidity = (extraction.get("liquidity") or "")
    if "bos" in latest_event.lower():
        tags.append("BOS")
    if "choch" in latest_event.lower() or "choch" in latest_event.lower().replace("ho", "o"):
        tags.append("CHOCH")
    if "sweep" in liquidity.lower():
        tags.append("Liquidity Sweep")

    return {
        "pair": extraction.get("pair"),
        "direction": direction,
        "entry": _num(extraction.get("entry")),
        "sl": _num(extraction.get("stopLoss")),
        "tp": _num(extraction.get("takeProfit")),
        "rr": _num(extraction.get("riskReward")),
        "lots": _num(extraction.get("lots")),
        "h4Trend": extraction.get("trend"),
        "h4PoiType": extraction.get("poiType"),
        "premiumDiscount": extraction.get("premiumDiscount"),
        "m15Confirmations": tags,
    }


def _fmt_price(value: float | None) -> str:
    if value is None:
        return "?"
    return f"{value:g}"


def _average(values: list[float]) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float))]
    return sum(nums) / len(nums) if nums else None


def build_setup_insight(
    candidate: dict[str, Any],
    history: list[dict[str, Any]] | None,
    *,
    min_total_history: int = MIN_TOTAL_HISTORY_FOR_INSIGHT,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Builds the "have I seen this before, and how did it go?" insight
    for a freshly-read setup. Always returns data -- there is no
    pass/fail gate anywhere in this function's output. Degrades
    honestly (clear "not enough history yet" narrative, not a fake
    result) when the trader hasn't logged enough trades yet."""
    history = history or []
    total_history_count = len(history)
    pair_label = candidate.get("pair") or "this pair"

    if total_history_count < min_total_history:
        return {
            "hasEnoughHistory": False,
            "totalHistoryCount": total_history_count,
            "sampleSize": 0,
            "wins": 0,
            "losses": 0,
            "breakeven": 0,
            "winRate": None,
            "averageRR": None,
            "averageProfit": None,
            "topSimilar": [],
            "narrative": [
                f"Not enough logged trades yet to compare this setup against your history "
                f"(you have {total_history_count}, need at least {min_total_history}). "
                "Log this trade's outcome when it closes so future setups get real feedback."
            ],
            "riskNotes": [],
        }

    result = search_similar(candidate, history, min_similarity=min_similarity, limit=limit)
    similar = result["similar"]
    sample_size = len(similar)

    if sample_size == 0:
        return {
            "hasEnoughHistory": True,
            "totalHistoryCount": total_history_count,
            "sampleSize": 0,
            "wins": 0,
            "losses": 0,
            "breakeven": 0,
            "winRate": None,
            "averageRR": None,
            "averageProfit": None,
            "topSimilar": [],
            "narrative": [
                f"This doesn't closely resemble any of your {total_history_count} past trades on {pair_label} "
                "yet -- no similar setup found. That's not good or bad by itself, just new territory."
            ],
            "riskNotes": [],
        }

    avg_similarity = _average([s["similarity"] for s in similar]) or 0.0
    wins, losses, breakeven = result["wins"], result["losses"], result["breakeven"]
    win_rate = result["winRate"]

    narrative: list[str] = []
    win_rate_txt = f"{win_rate:.0f}%" if win_rate is not None else "n/a"
    narrative.append(
        f"This setup is {avg_similarity:.0f}% similar on average to {sample_size} of your past "
        f"{pair_label} trades — {wins} won, {losses} lost"
        + (f", {breakeven} breakeven" if breakeven else "")
        + f" ({win_rate_txt} win rate)."
    )

    top = similar[0]
    top_outcome = (top.get("outcome") or "").lower()
    top_pnl = _num(top.get("pnl"))
    pnl_txt = f"${top_pnl:.2f}" if top_pnl is not None else "no P/L recorded"
    narrative.append(
        f"Closest match ({top['similarity']:.0f}% similar): a {top_outcome} on {top.get('date') or 'an earlier date'} "
        f"({pnl_txt})."
    )

    risk_notes: list[str] = []
    candidate_rr = _num(candidate.get("rr"))
    winning_similar = [s for s in similar if s.get("outcome") == "Win"]
    losing_similar = [s for s in similar if s.get("outcome") == "Loss"]
    avg_rr_wins = _average([_num(s.get("rr")) for s in winning_similar if _num(s.get("rr")) is not None])
    avg_rr_losses = _average([_num(s.get("rr")) for s in losing_similar if _num(s.get("rr")) is not None])

    if candidate_rr is not None and avg_rr_wins is not None and len(winning_similar) >= 2:
        if candidate_rr < avg_rr_wins * 0.7:
            risk_notes.append(
                f"Your planned R:R ({candidate_rr:.2f}) is noticeably tighter than your average R:R on "
                f"similar WINNING trades ({avg_rr_wins:.2f}) -- worth double-checking your take profit isn't too close."
            )

    if (
        candidate_rr is not None
        and avg_rr_losses is not None
        and avg_rr_wins is not None
        and len(losing_similar) >= 2
        and abs(candidate_rr - avg_rr_losses) < abs(candidate_rr - avg_rr_wins)
    ):
        risk_notes.append(
            f"Your planned R:R ({candidate_rr:.2f}) sits closer to your past LOSING trades on similar setups "
            f"(avg {avg_rr_losses:.2f}) than your winning ones (avg {avg_rr_wins:.2f}) -- doesn't mean skip it, "
            "just worth a second look before you commit."
        )

    entry, sl, tp = _num(candidate.get("entry")), _num(candidate.get("sl")), _num(candidate.get("tp"))
    if entry is not None and sl is not None and tp is not None:
        risk_notes.append(
            f"This setup: Entry {_fmt_price(entry)}, SL {_fmt_price(sl)}, TP {_fmt_price(tp)}."
        )

    top_similar_out = [
        {
            "id": s.get("id"),
            "date": s.get("date"),
            "pair": s.get("pair"),
            "direction": s.get("direction"),
            "outcome": s.get("outcome"),
            "similarity": s.get("similarity"),
            "pnl": _num(s.get("pnl")),
            "rr": _num(s.get("rr")),
        }
        for s in similar[:TOP_SIMILAR_DISPLAY_COUNT]
    ]

    return {
        "hasEnoughHistory": True,
        "totalHistoryCount": total_history_count,
        "sampleSize": sample_size,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "winRate": win_rate,
        "averageRR": result.get("averageRR"),
        "averageProfit": result.get("averageProfit"),
        "topSimilar": top_similar_out,
        "narrative": narrative,
        "riskNotes": risk_notes,
    }
