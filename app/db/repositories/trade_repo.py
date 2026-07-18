"""Repository for ``trades``.

All SQL for the ``Trade`` model lives here. Services call these methods
and never construct a SQLAlchemy query themselves (Section 5.1).
"""
from __future__ import annotations

import base64
from datetime import date as date_
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.trade import Trade

#: Columns that are safe to assign directly from a ``TradeIn``-shaped
#: dict via ``setattr`` — i.e. everything except ``id``/``user_id``
#: (identity) and the cached AI columns (owned by ``ai_service``).
_ASSIGNABLE_FIELDS = (
    "date",
    "pair",
    "direction",
    "asset",
    "timeframe",
    "order_type",
    "entry",
    "exit_price",
    "sl",
    "tp",
    "lots",
    "pnl",
    "rr",
    "h4_trend",
    "h4_poi_type",
    "premium_discount",
    "m15_confirmations",
    "session",
    "news",
    "confidence",
    "followed_plan",
    "rules_followed",
    "exit_reason",
    "emotion",
    "notes",
    "worked",
    "failed",
    "worked_tags",
    "failed_tags",
    "screenshots",
    "entered_at",
    "closed_at",
    "vision_fingerprint",
)


def _encode_cursor(trade_id: str) -> str:
    return base64.urlsafe_b64encode(trade_id.encode()).decode()


def _decode_cursor(cursor: str) -> str:
    return base64.urlsafe_b64decode(cursor.encode()).decode()


class TradeRepository:
    """Data access for ``Trade`` rows, scoped to a single user."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int, trade_id: str) -> Trade | None:
        result = await self.session.execute(
            select(Trade).where(Trade.id == trade_id, Trade.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self, user_id: int) -> list[Trade]:
        """All of a user's trades, oldest first — the shape every AI
        engine expects as "journal history". Not paginated; used
        server-side only (never returned directly over the wire)."""
        result = await self.session.execute(
            select(Trade).where(Trade.user_id == user_id).order_by(Trade.date, Trade.created_at)
        )
        return list(result.scalars().all())

    async def list_all_with_analyses(self, user_id: int) -> list[Trade]:
        """Same as ``list_all`` but eagerly loads each trade's analysis
        history, for the ML dataset builder (needs ``executionGrade``
        etc. from the latest analysis row)."""
        result = await self.session.execute(
            select(Trade)
            .where(Trade.user_id == user_id)
            .options(selectinload(Trade.analyses))
            .order_by(Trade.date, Trade.created_at)
        )
        return list(result.scalars().all())

    async def list_page(
        self,
        user_id: int,
        *,
        pair: str | None = None,
        session_name: str | None = None,
        date_from: date_ | None = None,
        date_to: date_ | None = None,
        outcome: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[Trade], str | None]:
        """Filtered, paginated listing for ``GET /trades``.

        Cursor is opaque to the caller (base64 of the last trade id
        seen); pagination itself is a simple id-ordered keyset scan,
        which is stable enough for a single-user SQLite dev database.
        """
        query = select(Trade).where(Trade.user_id == user_id)
        if pair:
            query = query.where(Trade.pair == pair.upper())
        if session_name:
            query = query.where(Trade.session == session_name)
        if date_from:
            query = query.where(Trade.date >= date_from)
        if date_to:
            query = query.where(Trade.date <= date_to)
        if outcome == "win":
            query = query.where(Trade.pnl > 0)
        elif outcome == "loss":
            query = query.where(Trade.pnl < 0)
        elif outcome == "breakeven":
            query = query.where(Trade.pnl == 0)

        query = query.order_by(Trade.date.desc(), Trade.id.desc())
        if cursor:
            last_id = _decode_cursor(cursor)
            query = query.where(Trade.id < last_id)
        query = query.limit(limit + 1)

        result = await self.session.execute(query)
        rows = list(result.scalars().all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = _encode_cursor(rows[-1].id)
        return rows, next_cursor

    async def upsert(self, user_id: int, trade_id: str, data: dict[str, Any]) -> Trade:
        """Creates the trade if it doesn't exist, otherwise updates the
        assignable fields in place. ``data`` uses the model's snake_case
        attribute names (schemas are responsible for the camelCase <->
        snake_case translation)."""
        trade = await self.get(user_id, trade_id)
        if trade is None:
            trade = Trade(id=trade_id, user_id=user_id)
            self.session.add(trade)
        for field in _ASSIGNABLE_FIELDS:
            if field in data:
                setattr(trade, field, data[field])
        await self.session.flush()
        return trade

    async def update_cached_scores(
        self,
        trade: Trade,
        *,
        rule_score: int | None,
        execution_score: int | None,
        overall_score: int | None,
        rule_recommendation: str | None,
    ) -> Trade:
        trade.rule_score = rule_score
        trade.execution_score = execution_score
        trade.overall_score = overall_score
        trade.rule_recommendation = rule_recommendation
        await self.session.flush()
        return trade

    async def delete(self, user_id: int, trade_id: str) -> bool:
        trade = await self.get(user_id, trade_id)
        if trade is None:
            return False
        await self.session.delete(trade)
        await self.session.flush()
        return True

    async def delete_all(self, user_id: int) -> int:
        """Sprint 18 -- bulk-deletes every trade for this user (e.g.
        starting fresh on a new MT5 account). Returns the count
        deleted so the caller can confirm back to the user exactly how
        many rows were removed."""
        result = await self.session.execute(
            select(Trade).where(Trade.user_id == user_id)
        )
        trades = result.scalars().all()
        count = len(trades)
        for trade in trades:
            await self.session.delete(trade)
        await self.session.flush()
        return count

    async def max_updated_at(self, user_id: int) -> str | None:
        """Latest ``updated_at`` across a user's trades, used to build
        the stats/coach cache fingerprint (Section 5.3)."""
        result = await self.session.execute(
            select(Trade.updated_at)
            .where(Trade.user_id == user_id)
            .order_by(Trade.updated_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return row.isoformat() if row else None

    async def count(self, user_id: int) -> int:
        trades = await self.list_all(user_id)
        return len(trades)
