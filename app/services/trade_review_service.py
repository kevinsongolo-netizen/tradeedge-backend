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
from app.engines.characteristic_gap_engine import build_characteristic_gaps
from app.engines.similar_engine import search_similar
from app.engines.trade_lesson_engine import build_trade_lesson
from app.engines.trade_review_engine import build_trade_review
from app.errors import ValidationError
from app.services.ai_service import AIService

# Sprint 20 Phase 6 -- "Analyze Trade" / "why did this trade fail?" caps
# how many possible-reason bullets to surface, same instinct as
# setup_insight_engine's _MAX_REASONS -- a short, readable list beats a
# wall of every gap/echo found.
MAX_POSSIBLE_REASONS = 5


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

            # Sprint 20 Phase 6 -- "Analyze Trade": for a LOSING trade,
            # explain *why* using the SAME characteristic-gap comparison
            # the pre-trade insight already uses (never a verdict -- just
            # "your losing trades on setups like this usually look like
            # X, and this one does too" / "your winners usually have Y,
            # and this one doesn't"). Reuses search_similar directly
            # (rather than threading it out of build_trade_lesson, which
            # doesn't expose its raw `similar` list) since it's a cheap,
            # pure, in-process computation.
            if result.get("outcome") == "LOSS":
                similar_result = search_similar(trade, history, weights=weights["similarity"], min_similarity=40.0, limit=20)
                gaps = build_characteristic_gaps(trade, similar_result["similar"])
                if gaps["hasEnoughData"]:
                    # Loser echoes first -- "this looks like your other
                    # losses" is more directly diagnostic than "this is
                    # missing something winners have", then winner gaps.
                    reasons = list(gaps["loserEchoes"]) + list(gaps["winnerGaps"])
                    result["possible_reasons"] = reasons[:MAX_POSSIBLE_REASONS]
                    result["most_likely_cause"] = reasons[0] if reasons else None
        except ValueError:
            # trade has no exit yet -- build_trade_review already raised
            # for this case above, so we won't get here in practice, but
            # fail soft on the lesson half regardless (the rules-followed
            # review is still useful on its own).
            pass

        return result
