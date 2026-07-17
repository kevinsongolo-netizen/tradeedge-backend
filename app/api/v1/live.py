"""Live MT5 Feed router (Sprint 14; simplified Sprint 20).

``POST /api/v1/live/ingest`` -- an MT5 Expert Advisor (or any other
live source) pushes its current price for a symbol/timeframe here.
Sprint 20 dropped the rule engine that used to run on every push (see
app/_legacy/) -- this just records price so ``GET /api/v1/live/latest``
and the repurposed Scanner (``GET /api/v1/live/open-trade-alerts``) can
use it.

``format=plain`` still returns a trivial ``KEY=value`` response (MQL5
has no built-in JSON parser) -- it's now just an echo of what was
ingested, not a rule-engine verdict.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.deps import get_current_user_id
from app.schemas.live import LiveIngestRequest, LiveSnapshotOut, OpenTradeAlertsResponse
from app.services.live_service import LiveFeedService

router = APIRouter(prefix="/live", tags=["live"])


def _format_plain(result: dict) -> str:
    lines = [
        f"SYMBOL={result.get('symbol', '')}",
        f"TIMEFRAME={result.get('timeframe', '')}",
        f"PRICE={result.get('price', '')}",
        f"BID={result.get('bid', '')}",
        f"ASK={result.get('ask', '')}",
    ]
    return "\n".join(lines) + "\n"


@router.post(
    "/ingest",
    summary="Ingest the latest live price for a symbol/timeframe from a live source (e.g. an MT5 EA)",
)
async def ingest(
    body: LiveIngestRequest,
    format: str = Query(default="json", pattern="^(json|plain)$"),
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
):
    service = LiveFeedService(session)
    result = await service.ingest(
        user_id, body.symbol, body.timeframe, price=body.price, bid=body.bid, ask=body.ask
    )
    if format == "plain":
        return PlainTextResponse(_format_plain(result))
    return result


@router.get(
    "/latest",
    response_model=LiveSnapshotOut,
    summary="Fetch the most recently ingested live price for a symbol/timeframe",
)
async def latest(
    symbol: str,
    timeframe: str,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> LiveSnapshotOut:
    service = LiveFeedService(session)
    result = await service.latest(user_id, symbol, timeframe)
    return LiveSnapshotOut(**result)


@router.get(
    "/open-trade-alerts",
    response_model=OpenTradeAlertsResponse,
    summary="Sprint 20 — the repurposed Scanner: live price vs. your own open trades' SL/TP",
)
async def open_trade_alerts(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> OpenTradeAlertsResponse:
    service = LiveFeedService(session)
    alerts = await service.check_open_trade_alerts(user_id)
    return OpenTradeAlertsResponse(alerts=alerts)
