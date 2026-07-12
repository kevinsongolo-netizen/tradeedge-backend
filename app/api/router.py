"""Aggregates all ``/api/v1/*`` routers into one include-able router.

System endpoints (``/healthz``, ``/readyz``, ``/version``) intentionally
live outside the ``/api/v1`` prefix and are mounted directly in
``app.main`` instead (Section 4.8).
"""
from fastapi import APIRouter

from app.api.v1 import ai, assistant, chart, coach, ml, ml_train, similar, stats, trades

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(trades.router)
api_router.include_router(ai.router)
api_router.include_router(similar.router)
api_router.include_router(stats.router)
api_router.include_router(coach.router)
api_router.include_router(ml.router)
api_router.include_router(ml_train.router)  # Sprint 7 — /ml/train, /ml/models*, /ml/predict, /ml/dataset/validation-report
api_router.include_router(assistant.router)  # Sprint 8 — /assistant/pretrade-analysis
api_router.include_router(chart.router)  # Sprint 10 — Chart Analysis Engine (/chart/*)
