"""Development seed script.

Ensures the Sprint-6 seeded user exists (normally done by the initial
Alembic migration already, so this is mostly useful when pointing at a
fresh database created via ``Base.metadata.create_all`` in tests, or
for idempotently re-seeding a dev database) and optionally loads a
sample trade history from ``tests/fixtures/sample_trades.json`` so the
API has something to show immediately after ``make migrate``.

Usage:
    python scripts/seed_dev.py             # seed user only
    python scripts/seed_dev.py --with-sample-trades
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import get_sessionmaker  # noqa: E402
from app.db.repositories import TradeRepository, UserRepository  # noqa: E402
from app.schemas.trade import TradeIn  # noqa: E402
from app.services.trade_service import TradeService  # noqa: E402

SAMPLE_TRADES_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sample_trades.json"


async def seed(with_sample_trades: bool) -> None:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.ensure_seed_user()
        await session.commit()
        print(f"Seeded user: id={user.id} email={user.email}")

        if with_sample_trades:
            if not SAMPLE_TRADES_PATH.exists():
                print(f"No sample trades file at {SAMPLE_TRADES_PATH}, skipping.")
                return
            trades = json.loads(SAMPLE_TRADES_PATH.read_text())
            trade_repo = TradeRepository(session)
            service = TradeService(session, trade_repo)
            inserted = 0
            for trade in trades:
                # Bug fix (Sprint 7): TradeService.create_trade() expects
                # Trade-model kwargs (snake_case, a real ``date`` object,
                # "exit_price" not "exit") — exactly what TradeIn.to_model_kwargs()
                # produces, and exactly what the real POST /trades router
                # does before calling this same service method. Passing the
                # raw camelCase fixture dict straight through (as this loop
                # used to) fails at the DB layer with "SQLite Date type only
                # accepts Python date objects" because ``date`` is still a
                # plain string. Only ever hit when running with
                # --with-sample-trades, which nothing else exercised before.
                await service.create_trade(user.id, TradeIn(**trade).to_model_kwargs())
                inserted += 1
            await session.commit()
            print(f"Seeded {inserted} sample trades for user {user.id}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the TradeEdge AI dev database.")
    parser.add_argument(
        "--with-sample-trades",
        action="store_true",
        help="Also load tests/fixtures/sample_trades.json as journal history.",
    )
    args = parser.parse_args()
    asyncio.run(seed(args.with_sample_trades))


if __name__ == "__main__":
    main()
