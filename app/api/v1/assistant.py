"""Sprint 8 — Intelligent Trading Assistant router (Vision Phase 5).

``POST /api/v1/assistant/pretrade-analysis`` — "help me BEFORE I enter
a trade": trade quality score, win probability, risk level, expected
RR, historical win rate, and a Strong Buy/Buy/Wait/Avoid recommendation
with a plain-language explanation (Phase 7).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.deps import get_current_user_id
from app.schemas.assistant import PreTradeAnalysisResult
from app.schemas.ml_training import PredictionRequest
from app.services.assistant_service import AssistantService

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post(
    "/pretrade-analysis",
    response_model=PreTradeAnalysisResult,
    summary="Pre-trade analysis: quality score, win probability, risk, and a recommendation",
)
async def pretrade_analysis(
    body: PredictionRequest,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> PreTradeAnalysisResult:
    """Works even before the user has ever called ``POST /ml/train`` —
    degrades to a rule-score-only estimate with an explicit note in
    ``historicalReasons`` rather than a hard 404, since the whole point
    of this endpoint is to be useful on day one."""
    service = AssistantService(session)
    result = await service.analyze_pretrade(user_id, body.model_dump(by_alias=False))
    return PreTradeAnalysisResult(**result)
