"""Position sizing calculator schemas (Sprint 11 — Trade Management Tools)."""
from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel


class PositionSizeRequest(CamelModel):
    account_balance: float
    risk_percent: float | None = None
    risk_amount: float | None = None
    entry: float
    stop_loss: float
    take_profit: float | None = None
    value_per_point_per_lot: float = Field(
        ...,
        description=(
            "How many account-currency dollars a 1.00 lot position moves per "
            "1.0 unit of price change (e.g. MT5's 'Tick value' on the symbol "
            "specification screen)."
        ),
    )
    lot_step: float = 0.01


class PositionSizeResult(CamelModel):
    risk_amount: float
    price_distance: float
    recommended_lots: float
    actual_risk_amount: float
    potential_loss: float
    potential_profit: float | None = None
    risk_reward: float | None = None
    warnings: list[str] = Field(default_factory=list)
