"""Session detection service (Sprint 12). Stateless — same pattern as
``ChartService``/``PositionSizeService``."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.engines.session_engine import detect_session


class SessionService:
    def detect(self, timestamp: datetime | None) -> dict[str, Any]:
        return detect_session(timestamp)
