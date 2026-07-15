"""Repository for ``account_margins`` (Sprint 18 — margin buffer)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.account_margin import AccountMargin


class AccountMarginRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int) -> AccountMargin | None:
        result = await self.session.execute(
            select(AccountMargin).where(AccountMargin.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert(self, user_id: int, *, balance: float, equity: float, margin: float) -> AccountMargin:
        existing = await self.get(user_id)
        if existing is not None:
            existing.balance = balance
            existing.equity = equity
            existing.margin = margin
            await self.session.flush()
            return existing
        row = AccountMargin(user_id=user_id, balance=balance, equity=equity, margin=margin)
        self.session.add(row)
        await self.session.flush()
        return row
