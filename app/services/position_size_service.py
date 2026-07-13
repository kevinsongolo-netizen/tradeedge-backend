"""Position sizing service (Sprint 11). Stateless — no DB access, same
pattern as ``ChartService`` (see its docstring)."""
from __future__ import annotations

from typing import Any

from app.engines.position_size_engine import calculate_position_size
from app.errors import ValidationError


class PositionSizeService:
    def calculate(self, req: dict[str, Any]) -> dict[str, Any]:
        try:
            return calculate_position_size(req)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
