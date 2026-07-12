"""System endpoints: liveness, readiness, and version info."""
from fastapi import APIRouter

from app.config import get_settings
from app.db.session import check_migrations_at_head

router = APIRouter(tags=["system"])


@router.get("/healthz", summary="Liveness probe")
async def healthz() -> dict:
    """Always returns 200 if the process is up and able to handle a
    request. Does not check any dependency (DB, disk, etc.)."""
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness probe")
async def readyz() -> dict:
    """Reports whether the service is ready to accept real traffic:
    the database must be reachable AND Alembic migrations must be at
    head (i.e. the schema on disk matches what the app code expects)."""
    at_head, current_revision = await check_migrations_at_head()
    return {"ready": at_head, "migration": current_revision}


@router.get("/version", summary="Build/version info")
async def version() -> dict:
    """Reports the running application name, version, and the version
    string each AI engine reports — a caller can confirm exactly which
    build (and which engine revisions) they're talking to."""
    settings = get_settings()
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "python": "3.10+",
        "engines": {
            "rule": "6.0",
            "execution": "6.0",
            "reason": "6.0",
            "similar": "6.0",
            "statistics": "6.0",
            "strategyHealth": "6.0",
            "setup": "6.0",
            "mistake": "6.0",
            "coach": "6.0",
            "ml": "6.0",
            "mlTraining": "7.0",
        },
    }
