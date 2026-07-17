"""Aggregates all ``/api/v1/*`` routers into one include-able router.

System endpoints (``/healthz``, ``/readyz``, ``/version``) intentionally
live outside the ``/api/v1`` prefix and are mounted directly in
``app.main`` instead (Section 4.8).
"""
from fastapi import APIRouter

from app.api.v1 import account_margin, ai, chart, coach, live, ml, ml_train, news, similar, stats, tools, trades

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(trades.router)
api_router.include_router(ai.router)
api_router.include_router(similar.router)
api_router.include_router(stats.router)
api_router.include_router(coach.router)
api_router.include_router(ml.router)
api_router.include_router(ml_train.router)  # Sprint 7 — /ml/train, /ml/models*, /ml/predict, /ml/dataset/validation-report
# Sprint 20 -- /assistant/* and /backtest/* retired along with the
# rule-based strategy engine they depended on; see app/_legacy/.
api_router.include_router(chart.router)  # Chart Analysis Engine (/chart/*) -- screenshot-first workflow since Sprint 20
api_router.include_router(tools.router)  # Sprint 11 — /tools/position-size
api_router.include_router(news.router)  # Sprint 12 — /news/check-calendar
api_router.include_router(live.router)  # Sprint 14 — /live/ingest, /live/latest (simplified to price-only since Sprint 20)
api_router.include_router(account_margin.router)  # Sprint 18 — /account-margin/ingest, /account-margin/latest
