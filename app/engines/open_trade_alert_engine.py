"""Open Trade Alert Engine (Sprint 20 — repurposed Live Opportunity
Scanner).

The old Scanner ran the retired rule engine against every watched
symbol/timeframe and flagged a fresh VALID setup. There's no rule
engine anymore, so the Scanner's job changed to something the
screenshot-first workflow actually needs: watching the trader's own
OPEN trades (logged from a screenshot, no exit price yet -- see
``Trade.to_engine_dict()``) against live price, and flagging when
price is closing in on or has crossed the SL/TP the trader already
decided on. Pure function, no I/O, no verdict on whether the trade
itself is good -- just where price sits relative to the trader's own
plan.
"""
from __future__ import annotations

from typing import Any

NEAR_THRESHOLD_PCT = 0.15  # "near" = within 15% of the original risk/reward distance


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _hit_sl(direction: str | None, price: float, sl: float) -> bool:
    if direction == "buy":
        return price <= sl
    if direction == "sell":
        return price >= sl
    return False


def _hit_tp(direction: str | None, price: float, tp: float) -> bool:
    if direction == "buy":
        return price >= tp
    if direction == "sell":
        return price <= tp
    return False


def build_open_trade_alerts(
    open_trades: list[dict[str, Any]], latest_price_by_pair: dict[str, float]
) -> list[dict[str, Any]]:
    """For each open trade whose pair has a live price available,
    returns its current status relative to SL/TP -- ``SL_HIT``,
    ``TP_HIT``, ``NEAR_SL``, ``NEAR_TP``, or ``MONITORING``. Trades
    whose pair has no live price yet (EA not attached/pushing for that
    symbol) are skipped, not reported as an error -- this is a
    best-effort watch, not a required check."""
    alerts: list[dict[str, Any]] = []
    for trade in open_trades:
        pair = trade.get("pair")
        if not pair or pair not in latest_price_by_pair:
            continue
        price = latest_price_by_pair[pair]
        direction = trade.get("direction")
        entry, sl, tp = _num(trade.get("entry")), _num(trade.get("sl")), _num(trade.get("tp"))

        status = "MONITORING"
        message = f"Price ({price:g}) is being watched against your plan."

        if sl is not None and _hit_sl(direction, price, sl):
            status = "SL_HIT"
            message = f"Price ({price:g}) has reached or crossed your stop loss ({sl:g})."
        elif tp is not None and _hit_tp(direction, price, tp):
            status = "TP_HIT"
            message = f"Price ({price:g}) has reached or crossed your take profit ({tp:g})."
        else:
            near_sl = False
            near_tp = False
            if sl is not None and entry is not None:
                total_risk = abs(entry - sl)
                if total_risk > 0 and abs(price - sl) <= total_risk * NEAR_THRESHOLD_PCT:
                    near_sl = True
            if tp is not None and entry is not None:
                total_reward = abs(tp - entry)
                if total_reward > 0 and abs(price - tp) <= total_reward * NEAR_THRESHOLD_PCT:
                    near_tp = True

            if near_sl:
                status = "NEAR_SL"
                message = f"Price ({price:g}) is approaching your stop loss ({sl:g})."
            elif near_tp:
                status = "NEAR_TP"
                message = f"Price ({price:g}) is approaching your take profit ({tp:g})."

        alerts.append(
            {
                "tradeId": trade.get("id"),
                "pair": pair,
                "direction": direction,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "currentPrice": price,
                "status": status,
                "needsAttention": status != "MONITORING",
                "message": message,
            }
        )
    return alerts
