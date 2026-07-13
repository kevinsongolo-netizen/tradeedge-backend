"""Position sizing calculator (Sprint 11 — Trade Management Tools).

Pure, deterministic risk-based lot-size math. Works across any
instrument (forex, indices, metals, crypto) because it never assumes a
particular contract size — the caller supplies ``value_per_point_per_lot``
(how many account-currency dollars a 1.00-lot position moves per 1.0
unit of price change; visible on any broker's symbol specification
screen, e.g. MT5's "Tick value"). Knows nothing about HTTP; raises
plain ``ValueError`` on invalid input per the engine convention used
throughout ``app/chart/*`` and ``app/engines/*``.
"""
from __future__ import annotations

import math
from typing import Any

DEFAULT_LOT_STEP = 0.01
HIGH_RISK_PERCENT_THRESHOLD = 3.0


def calculate_position_size(req: dict[str, Any]) -> dict[str, Any]:
    account_balance = req.get("account_balance")
    risk_percent = req.get("risk_percent")
    risk_amount_in = req.get("risk_amount")
    entry = req.get("entry")
    stop_loss = req.get("stop_loss")
    take_profit = req.get("take_profit")
    value_per_point_per_lot = req.get("value_per_point_per_lot")
    lot_step = req.get("lot_step")
    lot_step = DEFAULT_LOT_STEP if lot_step is None else lot_step

    if account_balance is None or account_balance <= 0:
        raise ValueError("Account balance must be a positive number.")
    if entry is None or stop_loss is None:
        raise ValueError("Entry and stop loss prices are required.")
    if entry == stop_loss:
        raise ValueError("Entry and stop loss can't be the same price.")
    if value_per_point_per_lot is None or value_per_point_per_lot <= 0:
        raise ValueError(
            "value_per_point_per_lot is required — this is how much a 1.00 lot "
            "position moves in account currency per 1.0 unit of price change "
            "(check your broker's symbol specification, e.g. MT5's 'Tick value')."
        )
    if lot_step <= 0:
        raise ValueError("Lot step must be a positive number.")
    if risk_amount_in is None and risk_percent is None:
        raise ValueError("Provide either risk_percent or risk_amount.")

    risk_amount_used = (
        float(risk_amount_in)
        if risk_amount_in is not None
        else account_balance * (risk_percent / 100.0)
    )
    if risk_amount_used <= 0:
        raise ValueError("Risk amount must be a positive number.")

    price_distance = abs(entry - stop_loss)
    raw_lots = risk_amount_used / (price_distance * value_per_point_per_lot)

    steps = math.floor(raw_lots / lot_step + 1e-9)  # tiny epsilon guards float rounding
    recommended_lots = round(steps * lot_step, 8)

    warnings: list[str] = []
    if recommended_lots <= 0:
        warnings.append(
            "Calculated position size rounds down to 0 lots — your risk amount "
            "is too small for this stop distance and lot step. Consider a "
            "tighter stop, a larger risk amount, or a smaller lot step."
        )
        recommended_lots = 0.0

    actual_risk_amount = recommended_lots * price_distance * value_per_point_per_lot
    potential_profit = None
    risk_reward = None
    if take_profit is not None:
        reward_distance = abs(take_profit - entry)
        potential_profit = recommended_lots * reward_distance * value_per_point_per_lot
        risk_reward = (reward_distance / price_distance) if price_distance else None

    if risk_percent is not None and risk_percent > HIGH_RISK_PERCENT_THRESHOLD:
        warnings.append(
            f"Risking {risk_percent:g}% of your account on a single trade is high "
            "— many traders cap risk at 1-2% per trade."
        )

    return {
        "risk_amount": round(risk_amount_used, 2),
        "price_distance": price_distance,
        "recommended_lots": recommended_lots,
        "actual_risk_amount": round(actual_risk_amount, 2),
        "potential_loss": round(actual_risk_amount, 2),
        "potential_profit": round(potential_profit, 2) if potential_profit is not None else None,
        "risk_reward": round(risk_reward, 2) if risk_reward is not None else None,
        "warnings": warnings,
    }
