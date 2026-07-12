"""Similar Trade Service — Section 5.2's ``find_similar``.

Loads a user's journal history and runs the weighted-v1 (or legacy,
for regression comparisons) similarity engine against a candidate
trade. Read-only — never persists anything.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.trade_repo import TradeRepository
from app.engines.similar_engine import search_similar, search_similar_legacy
from app.services.ai_service import AIService


class SimilarService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.trade_repo = TradeRepository(session)
        self.ai_service = AIService(session)

    async def find_similar(
        self,
        user_id: int,
        candidate: dict[str, Any],
        *,
        min_similarity: float = 50.0,
        limit: int = 10,
        algorithm: str = "weighted-v1",
    ) -> dict:
        """find_similar(user_id, candidate, ...) — Section 9.4's flow:
        load history, run the similarity engine, return ranked matches
        + aggregate outcomes."""
        history = [t.to_engine_dict() for t in await self.trade_repo.list_all(user_id)]
        if algorithm == "legacy":
            return search_similar_legacy(candidate, history)

        weights = await self.ai_service.get_weights(user_id)
        return search_similar(
            candidate,
            history,
            weights=weights["similarity"],
            min_similarity=min_similarity,
            limit=limit,
        )
