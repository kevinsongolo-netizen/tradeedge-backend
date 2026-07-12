"""FastAPI application entry point.

Run with:
    uvicorn app.main:app --reload

App factory wiring: CORS, structured request logging, the global
``AppError`` exception handlers, OpenAPI/Swagger/ReDoc, the system
endpoints (``/healthz``, ``/readyz``, ``/version``), and every
versioned ``/api/v1`` router (trades, ai, similar, stats, coach, ml).
The async DB engine/session are verified at startup
(``check_database_connection``) so the app fails fast with a clear log
line if ``DATABASE_URL`` is unreachable, and the connection pool is
disposed cleanly on shutdown.
"""
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.v1.health import router as health_router
from app.config import get_settings
from app.db.database import dispose_engine
from app.db.session import check_database_connection
from app.errors import register_exception_handlers
from app.logging import RequestLoggingMiddleware, configure_logging, logger

settings = get_settings()
configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("app.startup", env=settings.app_env, version=settings.app_version)
    try:
        await check_database_connection()
    except Exception:
        logger.exception("db.connection_failed", database_url=settings.database_url)
        raise
    logger.info("db.connected", database_url=settings.database_url)
    yield
    await dispose_engine()
    logger.info("app.shutdown")


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "TradeEdge AI backend — REST API for trade journaling, AI "
            "scoring, and ML dataset export. Ported from the frontend's "
            "local JS engines (Sprint 6)."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        # See Settings.cors_allow_credentials (app/config.py) — was
        # hardcoded True here alongside a wildcard origin default,
        # a CORS misconfiguration found during the production
        # readiness audit. Now config-driven and off by default.
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestLoggingMiddleware)
    register_exception_handlers(application)

    # System endpoints live at the root (no /api/v1 prefix) per spec.
    application.include_router(health_router)
    # Versioned domain routers (trades, ai, similar, ...) attach here in
    # later steps — currently empty.
    application.include_router(api_router)

    return application


app = create_app()
