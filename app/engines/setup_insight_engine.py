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


# Human-readable label for each similarity feature, used to explain WHY a
# past trade is considered similar rather than just showing a bare percent.
# Only features whose actual per-match similarity score cleared a
# reasonable bar are shown (see _contribution_reasons) -- a feature can be
# one of the top-3 CONTRIBUTIONS (weight * similarity) purely because it's
# heavily weighted, even with a mediocre similarity score, and that's not
# a fair "why" to show the trader.
_REASON_MIN_SIMILARITY = 0.6


def _contribution_reasons(contributions: list[dict], candidate: dict, entry: dict) -> list[str]:
    reasons: list[str] = []
    for c in contributions:
        feature = c.get("feature")
        sim = c.get("similarity") or 0
        if sim < _REASON_MIN_SIMILARITY:
            continue
        if feature == "pair":
            reasons.append(f"Same pair ({entry.get('pair')})")
        elif feature == "direction":
            reasons.append(f"Same direction ({(entry.get('direction') or '').upper()})")
        elif feature == "asset":
            reasons.append(f"Same asset class ({entry.get('asset')})")
        elif feature == "session":
            reasons.append(f"Same session ({entry.get('session')})")
        elif feature == "h4Trend":
            reasons.append(f"Same trend ({entry.get('h4Trend')})")
        elif feature == "h4PoiType":
            poi = entry.get("h4PoiType") or entry.get("poi")
            reasons.append(f"Same point of interest ({poi})")
        elif feature == "premiumDiscount":
            reasons.append(f"Same zone ({entry.get('premiumDiscount')})")
        elif feature == "bos":
            reasons.append("Both had a BOS")
        elif feature == "choch":
            reasons.append("Both had a CHoCH")
        elif feature == "liquiditySweep":
            reasons.append("Both had a liquidity sweep")
        elif feature == "rr":
            reasons.append("Similar R:R")
        elif feature == "stopDistancePct":
            reasons.append("Similar stop size")
        elif feature == "targetDistancePct":
            reasons.append("Similar take-profit distance")
        elif feature == "entryProximity":
            reasons.append("Very close entry price")
        elif feature == "lots":
            reasons.append("Similar position size")
        elif feature == "confidence":
            reasons.append("Similar read confidence")
        elif feature == "news":
            reasons.append("Similar news risk")
    return reasons


def _r_multiple_display(rr: float | None, outcome: str | None) -> str | None:
    """Signed R-multiple for display, e.g. "+2.5R" / "-1.0R" -- rr is
    stored as a positive ratio, sign comes from the trade's outcome."""
    if rr is None:
        return None
    sign = "-" if (outcome or "").lower() == "loss" else "+"
    return f"{sign}{abs(rr):.2f}R"


def _detected_summary(raw_extraction: dict[str, Any] | None) -> str | None:
    """Restates exactly what the vision model read off THIS screenshot
    -- the trader's own order type, POI label, and structure event, in
    those exact words -- as the very first line of the insight. Sprint
    20 Phase 2 #6: the trader should be able to confirm the read is
    correct ("yes, that's my Buy Limit on a Bullish Order Block") before
    reading anything about how it compares to history, instead of a
    generic "setup detected" line that could describe any trade.

    Takes the raw vision extraction (``candidate_from_vision_extraction``'s
    input, before it's narrowed down to similarity-engine fields), since
    that's the only place ``orderType``/``structure``/``fvgStatus``/the
    verbatim ``latestEvent`` text survive -- ``candidate_from_vision_
    extraction`` drops them down to a plain BOS/CHOCH/sweep tag list for
    the similarity engine's own purposes."""
    if not raw_extraction:
        return None

    structure_bits: list[str] = []
    trend = raw_extraction.get("trend")
    if trend:
        structure_bits.append(f"{trend} trend")
    poi = raw_extraction.get("poiType")
    if poi:
        structure_bits.append(poi)
    latest_event = raw_extraction.get("latestEvent")
    if latest_event:
        structure_bits.append(latest_event)
    fvg = raw_extraction.get("fvgStatus")
    if fvg and fvg.strip().lower() not in ("none", "n/a", "no fvg", ""):
        structure_bits.append(fvg)
    liquidity = raw_extraction.get("liquidity")
    if liquidity and "sweep" in liquidity.lower():
        structure_bits.append(liquidity)
    premium_discount = raw_extraction.get("premiumDiscount")
    if premium_discount:
        structure_bits.append(f"{premium_discount} zone")

    order_bits: list[str] = []
    pair = raw_extraction.get("pair")
    if pair:
        order_bits.append(pair)
    order_type = raw_extraction.get("orderType")
    direction = (raw_extraction.get("orderDirection") or "").upper()
    if order_type:
        order_bits.append(order_type)
    elif direction and direction != "NONE":
        order_bits.append(direction)

    price_bits: list[str] = []
    entry, sl, tp = _num(raw_extraction.get("entry")), _num(raw_extraction.get("stopLoss")), _num(raw_extraction.get("takeProfit"))
    rr = _num(raw_extraction.get("riskReward"))
    if entry is not None:
        price_bits.append(f"Entry {_fmt_price(entry)}")
    if sl is not None:
        price_bits.append(f"SL {_fmt_price(sl)}")
    if tp is not None:
        price_bits.append(f"TP {_fmt_price(tp)}")
    if rr is not None:
        price_bits.append(f"R:R {rr:.2f}")

    if not structure_bits and not order_bits and not price_bits:
        return None

    pieces: list[str] = []
    if structure_bits:
        pieces.append("Detected: " + ", ".join(structure_bits))
    if order_bits:
        pieces.append(" ".join(order_bits))
    if price_bits:
        pieces.append(", ".join(price_bits))
    return " -- ".join(pieces) + "."


def build_setup_insight(
    candidate: dict[str, Any],
    history: list[dict[str, Any]] | None,
    *,
    min_total_history: int = MIN_TOTAL_HISTORY_FOR_INSIGHT,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
    limit: int = DEFAULT_LIMIT,
    raw_extraction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Builds the "have I seen this before, and how did it go?" insight
    for a freshly-read setup. Always returns data -- there is no
    pass/fail gate anywhere in this function's output. Degrades
    honestly (clear "not enough history yet" narrative, not a fake
    result) when the trader hasn't logged enough trades yet.

    ``raw_extraction``: the vision model's raw screenshot read (before
    ``candidate_from_vision_extraction`` narrows it down), used only to
    prepend a "Detected: ..." line restating what was read, in the
    trader's own terms, ahead of any history comparison (Sprint 20
    Phase 2 #6). Optional -- omitted entirely when not supplied (e.g.
    a candidate built some other way than from a screenshot read)."""
    history = history or []
    total_history_count = len(history)
    pair_label = candidate.get("pair") or "this pair"
    detected = _detected_summary(raw_extraction)

    if total_history_count < min_total_history:
        narrative = ([detected] if detected else []) + [
            f"Not enough logged trades yet to compare this setup against your history "
            f"(you have {total_history_count}, need at least {min_total_history}). "
            "Log this trade's outcome when it closes so future setups get real feedback."
        ]
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
            "narrative": narrative,
            "riskNotes": [],
        }

    result = search_similar(candidate, history, min_similarity=min_similarity, limit=limit)
    similar = result["similar"]
    sample_size = len(similar)

    if sample_size == 0:
        narrative = ([detected] if detected else []) + [
            f"This doesn't closely resemble any of your {total_history_count} past trades on {pair_label} "
            "yet -- no similar setup found. That's not good or bad by itself, just new territory."
        ]
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
            "narrative": narrative,
            "riskNotes": [],
        }

    avg_similarity = _average([s["similarity"] for s in similar]) or 0.0
    wins, losses, breakeven = result["wins"], result["losses"], result["breakeven"]
    win_rate = result["winRate"]

    narrative: list[str] = [detected] if detected else []
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
            "rMultiple": _r_multiple_display(_num(s.get("rr")), s.get("outcome")),
            "reasons": _contribution_reasons(s.get("contributions") or [], candidate, s),
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
