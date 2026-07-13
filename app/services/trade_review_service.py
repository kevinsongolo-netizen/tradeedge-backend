"""Trade review (AI review-after-close) service (Sprint 11). Stateless
— no DB access; works on whatever trade fields the caller sends,
synced or not. Same pattern as ``ChartService`` (see its docstring)."""
from __future__ import annotations

from typing import Any

from app.engines.trade_review_engine import build_trade_review
from app.errors import ValidationError


class TradeReviewService:
    def review(self, trade: dict[str, Any]) -> dict[str, Any]:
        try:
            return build_trade_review(trade)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
