"""Pre-Trade Check router (rebuilt per the user's explicit rule that
every feature must run the ONE official H4->M15 POI strategy).

Two ways in, same strategy engine and same supplementary ML/history
layer:

* ``POST /api/v1/assistant/pretrade-analysis`` — pastes H4+M15 candles
  (same as Chart Analysis Engine's "candles" mode).
* ``POST /api/v1/assistant/pretrade-analysis-live`` — reuses whatever
  the Live MT5 Feed already computed for a symbol/timeframe (same as
  Chart Analysis Engine's "Live feed" mode and the Scanner), for
  traders who have no easy way to hand-copy raw candle rows.

Both return the strategy's own VALID/WAIT decision with its rule
checklist first, plus (only when VALID) ML win-probability, historical
similar-trade context, and a plain-language explanation as
supplementary color that never overrides the decision.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.deps import get_current_user_id
from app._legacy.assistant.assistant_schemas import PreTradeAnalysisRequest, PreTradeAnalysisResult, PreTradeFromLiveRequest
from app._legacy.assistant.assistant_service import AssistantService

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post(
    "/pretrade-analysis",
    response_model=PreTradeAnalysisResult,
    summary="Pre-trade check: runs your official H4->M15 POI strategy on pasted candles, plus ML win probability and similar-trade context when it's VALID",
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
        daily_candles=[c.model_dump(by_alias=False) for c in body.daily_candles],
        m15_candles=[c.model_dump(by_alias=False) for c in body.m15_candles],
        open_trade_in_loss=body.open_trade_in_loss,
    )
    return PreTradeAnalysisResult(**result)


@router.post(
    "/pretrade-analysis-live",
    response_model=PreTradeAnalysisResult,
    summary="Pre-trade check using the Live MT5 Feed's latest data for a symbol/timeframe -- no candle paste needed",
)
async def pretrade_analysis_live(
    body: PreTradeFromLiveRequest,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> PreTradeAnalysisResult:
    service = AssistantService(session)
    result = await service.analyze_pretrade_live(
        user_id,
        pair=body.pair,
        asset=body.asset,
        session_name=body.session,
        symbol=body.symbol,
        timeframe=body.timeframe,
    )
    return PreTradeAnalysisResult(**result)
