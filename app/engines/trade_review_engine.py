"""AI review-after-close (Sprint 11 — Trade Management Tools).

Pure, deterministic engine: takes one closed trade (the same camelCase
shape ``Trade.to_engine_dict()`` / ``TradeBase.to_candidate_dict()``
produce) and builds a plain-language review of what happened — never
just a win/loss label. Reuses fields the journal already collects
(rules followed, worked/failed tags, exit reason, R:R, H4 trend/POI)
rather than requiring anything new from the user. Knows nothing about
HTTP; raises plain ``ValueError`` on invalid input.
"""
from __future__ import annotations

from typing import Any

RR_HEALTHY_MINIMUM = 2.0

_FOLLOWED_PLAN_NOTES = {
    "all": "You followed your full trading plan.",
    "most": "You mostly followed your plan, with minor deviations.",
    "some": "You only partially followed your plan.",
    "none": "You did not follow your trading plan on this trade.",
}


def _infer_outcome(pnl: float | None, entry: float | None, exit_price: float | None, direction: str) -> str:
    if pnl is None and entry is not None and exit_price is not None:
        pnl = (entry - exit_price) if direction == "sell" else (exit_price - entry)
    if pnl is None:
        return "UNKNOWN"
    if pnl > 0:
        return "WIN"
    if pnl < 0:
        return "LOSS"
    return "BREAKEVEN"


def build_trade_review(trade: dict[str, Any]) -> dict[str, Any]:
    exit_price = trade.get("exit")
    if exit_price is None:
        raise ValueError(
            "This trade doesn't have an exit price yet — add one before requesting an AI review."
        )

    entry = trade.get("entry")
    direction = (trade.get("direction") or "").lower()
    outcome = _infer_outcome(trade.get("pnl"), entry, exit_price, direction)

    rules_followed = (trade.get("rulesFollowed") or "").lower()
    worked_tags = trade.get("workedTags") or []
    failed_tags = trade.get("failedTags") or []
    exit_reason = trade.get("exitReason") or ""
    rr = trade.get("rr")

    what_worked: list[str] = []
    what_went_wrong: list[str] = []

    if rules_followed == "all":
        what_worked.append("You followed all of your trading rules on this trade.")
    elif rules_followed == "most":
        what_worked.append("You followed most of your rules.")
    elif rules_followed == "some":
        what_went_wrong.append(
            "You only followed some of your rules — worth reviewing which ones you skipped and why."
        )
    elif rules_followed == "none":
        what_went_wrong.append("You deviated from your trading plan on this trade.")

    what_worked.extend(worked_tags)
    what_went_wrong.extend(failed_tags)

    if rr is not None:
        if rr >= RR_HEALTHY_MINIMUM:
            what_worked.append(f"Risk:Reward was {rr:g}, meeting or beating a healthy 1:{RR_HEALTHY_MINIMUM:g} minimum.")
        else:
            what_went_wrong.append(
                f"Risk:Reward was only {rr:g} — below the 1:{RR_HEALTHY_MINIMUM:g} minimum most SMC strategies recommend."
            )

    if exit_reason == "Take Profit Hit":
        what_worked.append("Trade hit take profit as planned.")
    elif exit_reason == "Stop Loss Hit":
        what_went_wrong.append("Trade hit stop loss.")
    elif exit_reason.startswith("Manual Close"):
        detail = exit_reason.replace("Manual Close - ", "").replace("Manual Close — ", "")
        what_went_wrong.append(f"Trade was manually closed early ({detail}).")

    if not trade.get("h4Trend"):
        what_went_wrong.append(
            "No H4 trend was recorded for this trade — logging it helps confirm you're trading with higher-timeframe bias."
        )
    if not trade.get("h4PoiType"):
        what_went_wrong.append(
            "No point-of-interest (POI) type was recorded — was this trade taken from a real SMC zone?"
        )

    if outcome == "WIN" and not what_went_wrong:
        headline = "WIN — Clean Execution"
    elif outcome == "WIN":
        headline = "WIN — But Room to Tighten Your Process"
    elif outcome == "LOSS" and what_went_wrong:
        headline = "LOSS — Rules Were Broken"
    elif outcome == "LOSS":
        headline = "LOSS — Valid Setup, Just Didn't Work Out"
    elif outcome == "BREAKEVEN":
        headline = "BREAKEVEN TRADE"
    else:
        headline = "REVIEW"

    if what_went_wrong:
        lesson = what_went_wrong[0]
    elif outcome == "WIN":
        lesson = "This is the process to repeat — you followed your rules and the trade worked out."
    else:
        lesson = "No major process errors found — sometimes a valid, well-planned trade still loses. That's normal risk, not a mistake."

    followed_plan_note = _FOLLOWED_PLAN_NOTES.get(
        rules_followed, "Rules-followed wasn't recorded for this trade."
    )

    return {
        "outcome": outcome,
        "headline": headline,
        "what_worked": what_worked,
        "what_went_wrong": what_went_wrong,
        "lesson": lesson,
        "followed_plan_note": followed_plan_note,
    }
