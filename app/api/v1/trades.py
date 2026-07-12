"""Trade CRUD router — ``/api/v1/trades`` (Section 4.2).

Thin per Section 5.1: parse/validate the request, resolve the current
user, delegate to ``TradeService``, serialize the result. No DB or
engine calls happen here.
"""
from __future__ import annotations

from datetime import date as date_

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.deps import get_current_user_id
from app.schemas.trade import (
    BulkTradeIn,
    BulkTradeResult,
    TradeIn,
    TradeListResponse,
    TradeOut,
    TradeUpdate,
)
from app.services.trade_service import TradeService

router = APIRouter(prefix="/trades", tags=["trades"])


@router.post("", response_model=TradeOut, status_code=201, summary="Create or upsert a trade")
async def create_trade(
    body: TradeIn,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> TradeOut:
    """Creates (or upserts, if the client resends the same ``id``) a
    trade and synchronously runs the AI analysis pipeline against it."""
    service = TradeService(session)
    result = await service.create_trade(user_id, body.to_model_kwargs())
    return TradeOut(**result)


@router.get("", response_model=TradeListResponse, summary="List trades")
async def list_trades(
    pair: str | None = None,
    session_name: str | None = Query(default=None, alias="session"),
    date_from: date_ | None = None,
    date_to: date_ | None = None,
    outcome: str | None = Query(default=None, pattern="^(win|loss|breakeven)$"),
    limit: int = Query(default=100, ge=1, le=500),
    cursor: str | None = None,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> TradeListResponse:
    """Filtered, cursor-paginated trade listing."""
    service = TradeService(session)
    result = await service.list_trades(
        user_id,
        pair=pair,
        session_name=session_name,
        date_from=date_from,
        date_to=date_to,
        outcome=outcome,
        limit=limit,
        cursor=cursor,
    )
    return TradeListResponse(**result)


@router.get("/{trade_id}", response_model=TradeOut, summary="Get one trade")
async def get_trade(
    trade_id: str,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> TradeOut:
    service = TradeService(session)
    result = await service.get_trade(user_id, trade_id)
    return TradeOut(**result)


@router.patch("/{trade_id}", response_model=TradeOut, summary="Partially update a trade")
async def update_trade(
    trade_id: str,
    body: TradeUpdate,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> TradeOut:
    """Partial update — only supplied fields change. Re-analysis always
    runs afterward since almost every field affects scoring."""
    service = TradeService(session)
    patch = body.model_dump(by_alias=False, exclude_unset=True)
    if "exit" in patch:
        patch["exit_price"] = patch.pop("exit")
    if "pair" in patch and patch["pair"]:
        patch["pair"] = str(patch["pair"]).upper()
    result = await service.update_trade(user_id, trade_id, patch)
    return TradeOut(**result)


@router.delete("/{trade_id}", status_code=204, summary="Delete a trade")
async def delete_trade(
    trade_id: str,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    service = TradeService(session)
    await service.delete_trade(user_id, trade_id)


@router.post("/bulk", response_model=BulkTradeResult, summary="Bulk upsert (migration script)")
async def bulk_upsert_trades(
    body: BulkTradeIn,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> BulkTradeResult:
    """Used by ``scripts/migrate_from_localstorage.py`` to import a
    user's full JSON export in one call."""
    service = TradeService(session)
    items = [item.to_model_kwargs() for item in body.items]
    result = await service.bulk_upsert(user_id, items)
    return BulkTradeResult(**result)
