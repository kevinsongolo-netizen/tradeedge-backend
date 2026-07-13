"""Sprint 11 — general trading tools router.

``POST /api/v1/tools/position-size`` — risk-based position size
calculator (Trade Management Tools). Stateless, no auth/DB dependency,
same pattern as the Chart Analysis Engine router.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.schemas.position_size import PositionSizeRequest, PositionSizeResult
from app.services.position_size_service import PositionSizeService

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
