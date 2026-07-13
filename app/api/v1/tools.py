"""Sprint 11 — general trading tools router.

``POST /api/v1/tools/position-size`` — risk-based position size
calculator (Trade Management Tools). Stateless, no auth/DB dependency,
same pattern as the Chart Analysis Engine router.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.schemas.position_size import PositionSizeRequest, PositionSizeResult
from app.schemas.session import SessionDetectRequest, SessionDetectResult
from app.services.position_size_service import PositionSizeService
from app.services.session_service import SessionService

router = APIRouter(prefix="/tools", tags=["tools"])


@router.post(
    "/position-size",
    response_model=PositionSizeResult,
    summary="Risk-based position size calculator",
)
async def position_size(body: PositionSizeRequest) -> PositionSizeResult:
    service = PositionSizeService()
    result = service.calculate(body.model_dump(by_alias=False))
    return PositionSizeResult(**result)


@router.post(
    "/session-detect",
    response_model=SessionDetectResult,
    summary="Sprint 12 — trading session auto-detection (Asian/London/New York/Overlap)",
)
async def session_detect(body: SessionDetectRequest) -> SessionDetectResult:
    service = SessionService()
    result = service.detect(body.timestamp)
    return SessionDetectResult(**result)
