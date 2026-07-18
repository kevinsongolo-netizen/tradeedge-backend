"""Trade review (AI review-after-close) service (Sprint 11; extended
Sprint 20 Phase 2 #4 with the planned-vs-actual lesson engine).

Combines two independent engines:
  * ``trade_review_engine.build_trade_review`` -- did this trade follow
    the trader's own logged checklist (rules/tags/exit reason)? Stateless,
    no DB access, works on whatever fields the caller sends.
  * ``trade_lesson_engine.build_trade_lesson`` -- how does this trade's
    stop/target sizing and outcome compare to the trader's OWN similar
    past trades? Needs the trader's history, so this service now loads
    it the same way ``SimilarService`` does.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.trade_repo import TradeRepository
from app.engines.trade_lesson_engine import build_trade_lesson
from app.engines.trade_review_engine import build_trade_review
from app.errors import ValidationError
from app.services.ai_service import AIService


class TradeReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.trade_repo = TradeRepository(session)
        self.ai_service = AIService(session)

    async def review(self, user_id: int, trade: dict[str, Any]) -> dict[str, Any]:
        try:
            result = build_trade_review(trade)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        try:
            history = [t.to_engine_dict() for t in await self.trade_repo.list_all(user_id)]
            weights = await self.ai_service.get_weights(user_id)
            lesson = build_trade_lesson(trade, history, weights=weights["similarity"])
            result["has_enough_history"] = lesson["hasEnoughHistory"]
            result["similar_sample_size"] = lesson["sampleSize"]
            result["similar_wins"] = lesson["wins"]
            result["similar_losses"] = lesson["losses"]
            result["lessons"] = lesson["lessons"]
            result["patterns"] = lesson["patterns"]
        except ValueError:
            # trade has no exit yet -- build_trade_review already raised
            # for this case above, so we won't get here in practice, but
            # fail soft on the lesson half regardless (the rules-followed
            # review is still useful on its own).
            pass

        return result
