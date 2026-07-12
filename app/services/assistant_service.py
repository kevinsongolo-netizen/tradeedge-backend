"""Sprint 8 — Pre-Trade Analysis service (Vision Phases 5 & 7).

Orchestrates Sprint 7's ML prediction (optional — degrades gracefully
if the user hasn't trained a model yet) and the similar-trade engine,
then hands both to ``app/engines/assistant_engine.py`` for the actual
scoring/explanation logic. This service does no business logic itself,
matching the rest of the app's services/engines split.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.assistant_engine import analyze_pretrade
from app.services.ml_prediction_service import MLPredictionService, NoActiveModelError
from app.services.similar_service import SimilarService


def _candidate_to_similar_shape(candidate: dict[str, Any]) -> dict[str, Any]:
    """Adapts a PredictionRequest-shaped candidate (snake_case; BOS/
    CHOCH/liquidity-sweep as separate booleans) into the camelCase,
    tag-list shape ``search_similar()`` expects (same shape
    ``Trade.to_engine_dict()`` produces — see
    ``TradeBase.to_candidate_dict()`` for why this distinction
    matters)."""
    tags: list[str] = []
    if candidate.get("has_bos"):
        tags.append("BOS")
    if candidate.get("has_choch"):
        tags.append("CHOCH")
    if candidate.get("has_liquidity_sweep"):
        tags.append("Liquidity Sweep")
    return {
        "pair": candidate.get("pair"),
        "direction": candidate.get("direction"),
        "asset": candidate.get("asset"),
        "session": candidate.get("session"),
        "h4Trend": candidate.get("h4_trend"),
        "h4PoiType": candidate.get("h4_poi_type"),
        "m15Confirmations": tags,
        "rr": candidate.get("planned_rr"),
        "confidence": candidate.get("confidence"),
    }


class AssistantService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.prediction_service = MLPredictionService(session)
        self.similar_service = SimilarService(session)

    async def analyze_pretrade(self, user_id: int, candidate: dict[str, Any]) -> dict[str, Any]:
        try:
            ml_result = await self.prediction_service.predict(user_id, candidate)
        except NoActiveModelError:
            # Phase 5 must still be useful before Sprint 7's model has
            # ever been trained — analyze_pretrade() falls back to a
            # rule-score-only estimate in this case.
            ml_result = None

        similar_result = await self.similar_service.find_similar(
            user_id,
            _candidate_to_similar_shape(candidate),
            min_similarity=50.0,
            limit=20,
        )

        return analyze_pretrade(candidate, ml_result=ml_result, similar_result=similar_result)
