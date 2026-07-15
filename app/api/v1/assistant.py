"""Pre-Trade Check router (rebuilt per the user's explicit rule that
every feature must run the ONE official H4->M15 POI strategy).

``POST /api/v1/assistant/pretrade-analysis`` — "help me BEFORE I enter
a trade": pastes H4+M15 candles (same as Chart Analysis Engine),
returns the strategy's own VALID/WAIT decision with its rule checklist
first, plus (only when VALID) ML win-probability, historical
similar-trade context, and a plain-language explanation as
supplementary color that never overrides the decision.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.deps import get_current_user_id
from app.schemas.assistant import PreTradeAnalysisRequest, PreTradeAnalysisResult
from app.services.assistant_service import AssistantService

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post(
    "/pretrade-analysis",
    response_model=PreTradeAnalysisResult,
    summary="Pre-trade check: runs your official H4->M15 POI strategy, plus ML win probability and similar-trade context when it's VALID",
)
async def pretrade_analysis(
    body: PreTradeAnalysisRequest,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> PreTradeAnalysisResult:
    service = AssistantService(session)
    result = await service.analyze_pretrade_candles(
        user_id,
        pair=body.pair,
        asset=body.asset,
        session_name=body.session,
        h4_candles=[c.model_dump(by_alias=False) for c in body.h4_candles],
        m15_candles=[c.model_dump(by_alias=False) for c in body.m15_candles],
    )
    return PreTradeAnalysisResult(**result)
