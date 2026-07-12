"""Repository tests — TradeRepository, AnalysisRepository, UserRepository,
WeightsRepository, against a real (temp file) SQLite database via the
async engine (see conftest.py for the per-test DB reset)."""
import pytest

from app.db.database import get_sessionmaker
from app.db.repositories import (
    AnalysisRepository,
    MLExportRepository,
    TradeRepository,
    UserRepository,
    WeightsRepository,
)

pytestmark = pytest.mark.asyncio


async def _session():
    return get_sessionmaker()()


async def test_user_repo_ensure_seed_user_is_idempotent():
    async with await _session() as session:
        repo = UserRepository(session)
        user1 = await repo.ensure_seed_user()
        user2 = await repo.ensure_seed_user()
        await session.commit()
        assert user1.id == user2.id == 1
        assert user1.email == "local@tradeedge.ai"


async def test_user_repo_get_by_email():
    async with await _session() as session:
        repo = UserRepository(session)
        user = await repo.get_by_email("local@tradeedge.ai")
        assert user is not None
        assert user.id == 1
        assert await repo.get_by_email("nobody@example.com") is None


async def test_trade_repo_upsert_creates_then_updates():
    async with await _session() as session:
        repo = TradeRepository(session)
        trade = await repo.upsert(1, "t1", {"pair": "EURUSD", "pnl": 10.0})
        await session.commit()
        assert trade.pair == "EURUSD"

        updated = await repo.upsert(1, "t1", {"pair": "GBPUSD"})
        await session.commit()
        assert updated.id == trade.id
        assert updated.pair == "GBPUSD"
        assert updated.pnl == 10.0  # untouched field preserved


async def test_trade_repo_get_returns_none_for_missing():
    async with await _session() as session:
        repo = TradeRepository(session)
        assert await repo.get(1, "does-not-exist") is None


async def test_trade_repo_list_all_ordered_by_date():
    async with await _session() as session:
        repo = TradeRepository(session)
        await repo.upsert(1, "b", {"date": __import__("datetime").date(2026, 2, 1)})
        await repo.upsert(1, "a", {"date": __import__("datetime").date(2026, 1, 1)})
        await session.commit()
        rows = await repo.list_all(1)
        assert [r.id for r in rows] == ["a", "b"]


async def test_trade_repo_delete():
    async with await _session() as session:
        repo = TradeRepository(session)
        await repo.upsert(1, "to-delete", {"pair": "EURUSD"})
        await session.commit()
        assert await repo.delete(1, "to-delete") is True
        assert await repo.delete(1, "to-delete") is False
        assert await repo.get(1, "to-delete") is None


async def test_trade_repo_pagination_cursor():
    async with await _session() as session:
        repo = TradeRepository(session)
        import datetime

        for i in range(5):
            await repo.upsert(1, f"trade-{i}", {"date": datetime.date(2026, 1, i + 1), "pnl": float(i)})
        await session.commit()

        page1, cursor1 = await repo.list_page(1, limit=2)
        assert len(page1) == 2
        assert cursor1 is not None

        page2, cursor2 = await repo.list_page(1, limit=2, cursor=cursor1)
        assert len(page2) == 2
        assert {t.id for t in page1}.isdisjoint({t.id for t in page2})


async def test_trade_repo_filters_by_outcome():
    async with await _session() as session:
        repo = TradeRepository(session)
        await repo.upsert(1, "win", {"pnl": 100.0})
        await repo.upsert(1, "loss", {"pnl": -50.0})
        await session.commit()
        wins, _ = await repo.list_page(1, outcome="win", limit=10)
        assert {t.id for t in wins} == {"win"}


async def test_analysis_repo_insert_and_list():
    async with await _session() as session:
        trade_repo = TradeRepository(session)
        await trade_repo.upsert(1, "trade-x", {"pair": "EURUSD"})
        await session.commit()

        analysis_repo = AnalysisRepository(session)
        await analysis_repo.insert(1, "trade-x", {"rule_score": 80, "execution_score": 90, "overall_score": 85})
        await session.commit()

        rows = await analysis_repo.list_for_trade(1, "trade-x")
        assert len(rows) == 1
        assert rows[0].rule_score == 80


async def test_weights_repo_upsert_and_get():
    async with await _session() as session:
        repo = WeightsRepository(session)
        assert await repo.get(1) is None
        await repo.upsert(1, {"rule_weights": {"h4Trend": 50}})
        await session.commit()
        row = await repo.get(1)
        assert row.rule_weights == {"h4Trend": 50}


async def test_ml_export_repo_insert():
    async with await _session() as session:
        repo = MLExportRepository(session)
        row = await repo.insert(
            1,
            {
                "format": "json",
                "row_count": 10,
                "rejected_count": 0,
                "quality_score": 100,
                "dataset_version": "6.0",
            },
        )
        await session.commit()
        assert row.id is not None
        assert row.format == "json"
