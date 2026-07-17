"""Live MT5 feed service (Sprint 14; simplified Sprint 20).

Sprint 20 -- screenshot-first workflow. This service no longer runs
any chart/rule engine on ingest (that engine is retired, see
app/_legacy/) -- it just records the latest live price per (user,
symbol, timeframe). ``check_open_trade_alerts`` is the new Scanner
basis: compares that live price against the trader's own logged open
trades (Trade rows with no exit price yet) for the same symbol, and
flags when price is close to or has crossed SL/TP. No rule engine, no
verdict -- just "here's where price is relative to your own plan."
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.live_snapshot_repo import LiveSnapshotRepository
from app.db.repositories.trade_repo import TradeRepository
from app.errors import NotFoundError
from app.engines.open_trade_alert_engine import build_open_trade_alerts


class LiveFeedService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = LiveSnapshotRepository(session)
        self.trade_repo = TradeRepository(session)

    async def ingest(
        self,
        user_id: int,
        symbol: str,
        timeframe: str,
        *,
        price: float | None = None,
        bid: float | None = None,
        ask: float | None = None,
    ) -> dict[str, Any]:
        await self.repo.upsert(user_id, symbol, timeframe, {"price": price, "bid": bid, "ask": ask})
        await self.session.commit()
        return {"symbol": symbol, "timeframe": timeframe, "price": price, "bid": bid, "ask": ask}

    async def latest(self, user_id: int, symbol: str, timeframe: str) -> dict[str, Any]:
        row = await self.repo.get(user_id, symbol, timeframe)
        if row is None:
            raise NotFoundError(
                f"No live data yet for {symbol} {timeframe}. Make sure your MT5 EA is "
                "attached and running, and that it's pushed at least one update."
            )
        return {
            "symbol": row.symbol,
            "timeframe": row.timeframe,
            "price": row.price,
            "bid": row.bid,
            "ask": row.ask,
            "updated_at": row.updated_at,
        }

    async def check_open_trade_alerts(self, user_id: int) -> list[dict[str, Any]]:
        """The repurposed Scanner: for every open trade (logged from a
        screenshot, exit price not yet filled in), look up the latest
        live price for that trade's pair across every timeframe an EA
        has pushed for it, and flag proximity to / crossing of SL/TP.
        Pure price comparison -- no rule engine, no verdict on whether
        the trade itself was good."""
        trades = await self.trade_repo.list_all(user_id)
        open_trades = [t.to_engine_dict() for t in trades if t.exit_price is None and t.pair]
        if not open_trades:
            return []

        # get_latest_for_symbol matches case-insensitively (trades store
        # ``pair`` uppercased; an EA may push ``symbol`` in whatever case
        # the broker uses, e.g. "GOLDmicro") -- keep each trade's own pair
        # casing as the dict key for display.
        pairs = {t["pair"] for t in open_trades}
        latest_by_pair: dict[str, float] = {}
        for pair in pairs:
            row = await self.repo.get_latest_for_symbol(user_id, pair)
            if row is not None and row.price is not None:
                latest_by_pair[pair] = row.price

        return build_open_trade_alerts(open_trades, latest_by_pair)
