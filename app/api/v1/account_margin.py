"""Sprint 18 — Account margin / floating-loss buffer router.

``POST /api/v1/account-margin/ingest`` — the MT5 EA pushes raw
balance/equity/margin here on the same timer tick as its candle push.
``GET /api/v1/account-margin/latest`` — the website polls this to show
the buffer banner. Pass ``?format=plain`` for MQL5-friendly
``KEY=value`` lines (MQL5 has no JSON parser), same convention as
``/live/ingest``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.deps import get_current_user_id
from app.schemas.account_margin import AccountMarginIngestRequest, AccountMarginOut
from app.services.account_margin_service import AccountMarginService

router = APIRouter(prefix="/account-margin", tags=["account-margin"])


def _format_plain(result: dict) -> str:
    lines = [
        f"STATUS={result.get('status', '')}",
        f"MARGIN_LEVEL_PCT={result.get('marginLevelPct') if result.get('marginLevelPct') is not None else ''}",
        f"BUFFER_TO_MARGIN_CALL_PCT={result.get('bufferToMarginCallPct') if result.get('bufferToMarginCallPct') is not None else ''}",
        f"BUFFER_TO_STOP_OUT_PCT={result.get('bufferToStopOutPct') if result.get('bufferToStopOutPct') is not None else ''}",
    ]
    return "\n".join(lines) + "\n"


@router.post(
    "/ingest",
    response_model=AccountMarginOut,
    summary="Sprint 18 — ingest raw balance/equity/margin from the MT5 EA",
)
async def ingest(
    body: AccountMarginIngestRequest,
    format: str = Query(default="json", pattern="^(json|plain)$"),
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
):
    service = AccountMarginService(session)
    result = await service.ingest(
        user_id,
        balance=body.balance,
        equity=body.equity,
        margin=body.margin,
        margin_call_level_pct=body.margin_call_level_pct,
        stop_out_level_pct=body.stop_out_level_pct,
    )
    if format == "plain":
        return PlainTextResponse(_format_plain(result))
    return AccountMarginOut(**result)


@router.get(
    "/latest",
    response_model=AccountMarginOut,
    summary="Sprint 18 — fetch the most recent margin buffer reading",
)
async def latest(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> AccountMarginOut:
    service = AccountMarginService(session)
    result = await service.latest(user_id)
    return AccountMarginOut(**result)
