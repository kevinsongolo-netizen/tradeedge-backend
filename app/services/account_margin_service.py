"""AccountMarginService (Sprint 18 — margin/floating-loss buffer).

Turns a raw balance/equity/margin push from the MT5 EA into a plain
"how close am I to a problem" reading. No stop loss exists in the
user's Personal Averaging Strategy, so this is the actual safety net:
it can't close anything, it can only make the real risk visible.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.account_margin_repo import AccountMarginRepository
from app.errors import NotFoundError
from app.schemas.account_margin import (
    DEFAULT_MARGIN_CALL_LEVEL_PCT,
    DEFAULT_STOP_OUT_LEVEL_PCT,
)


class AccountMarginService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AccountMarginRepository(session)

    async def ingest(
        self,
        user_id: int,
        *,
        balance: float,
        equity: float,
        margin: float,
        margin_call_level_pct: float = DEFAULT_MARGIN_CALL_LEVEL_PCT,
        stop_out_level_pct: float = DEFAULT_STOP_OUT_LEVEL_PCT,
    ) -> dict:
        await self.repo.upsert(user_id, balance=balance, equity=equity, margin=margin)
        await self.session.commit()
        # Deliberately NOT reading row.updated_at here -- it's a
        # server-side onupdate=func.now() column, and on the UPDATE
        # path (as opposed to INSERT) touching it after flush/commit
        # triggers an implicit lazy-refresh from the DB that isn't
        # safe outside AsyncSession's own greenlet context. ``latest()``
        # below reads it back on a plain GET (no preceding write in the
        # same call), which is safe -- this mirrors LiveFeedService.
        # ingest()'s same choice not to round-trip the row for its
        # response. A fresh Python timestamp is accurate enough here.
        updated_at = datetime.now(timezone.utc)
        return _to_out(
            balance,
            equity,
            margin,
            updated_at,
            margin_call_level_pct=margin_call_level_pct,
            stop_out_level_pct=stop_out_level_pct,
        )

    async def latest(self, user_id: int) -> dict:
        row = await self.repo.get(user_id)
        if row is None:
            raise NotFoundError(
                "No account margin data yet -- make sure your MT5 EA is attached and running."
            )
        return _to_out(row.balance, row.equity, row.margin, row.updated_at)


def _to_out(
    balance: float,
    equity: float,
    margin: float,
    updated_at,
    margin_call_level_pct: float = DEFAULT_MARGIN_CALL_LEVEL_PCT,
    stop_out_level_pct: float = DEFAULT_STOP_OUT_LEVEL_PCT,
) -> dict:
    floating_pnl = equity - balance

    if margin <= 0:
        return {
            "balance": balance,
            "equity": equity,
            "margin": margin,
            "floatingPnl": floating_pnl,
            "marginLevelPct": None,
            "marginCallLevelPct": margin_call_level_pct,
            "stopOutLevelPct": stop_out_level_pct,
            "bufferToMarginCallPct": None,
            "bufferToStopOutPct": None,
            "status": "NO_POSITIONS",
            "updatedAt": updated_at,
        }

    margin_level_pct = (equity / margin) * 100
    buffer_to_margin_call = margin_level_pct - margin_call_level_pct
    buffer_to_stop_out = margin_level_pct - stop_out_level_pct

    if margin_level_pct <= stop_out_level_pct:
        status = "DANGER"
    elif margin_level_pct <= margin_call_level_pct:
        status = "WARNING"
    else:
        status = "SAFE"

    return {
        "balance": balance,
        "equity": equity,
        "margin": margin,
        "floatingPnl": floating_pnl,
        "marginLevelPct": round(margin_level_pct, 2),
        "marginCallLevelPct": margin_call_level_pct,
        "stopOutLevelPct": stop_out_level_pct,
        "bufferToMarginCallPct": round(buffer_to_margin_call, 2),
        "bufferToStopOutPct": round(buffer_to_stop_out, 2),
        "status": status,
        "updatedAt": updated_at,
    }
