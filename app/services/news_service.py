"""News/economic calendar filter service (Sprint 12). Follows the same
pattern as ``ChartService``: orchestrates a pluggable provider +
a pure engine, wraps provider failures as ``AppError``."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.errors import ValidationError
from app.news.calendar_provider import CalendarProviderError, get_calendar_provider
from app.news.news_filter_engine import evaluate_news_risk

LOOKAROUND_DAYS = 2


class NewsService:
    async def check(
        self,
        planned_time: datetime,
        *,
        buffer_minutes: int,
        currencies: list[str] | None,
        min_impact: str,
    ) -> dict[str, Any]:
        provider = get_calendar_provider()
        from_date = (planned_time - timedelta(days=LOOKAROUND_DAYS)).strftime("%Y-%m-%d")
        to_date = (planned_time + timedelta(days=LOOKAROUND_DAYS)).strftime("%Y-%m-%d")
        try:
            events = await provider.get_events(from_date, to_date)
        except CalendarProviderError as exc:
            raise ValidationError(f"Could not check the news calendar: {exc}") from exc

        result = evaluate_news_risk(
            events,
            planned_time,
            buffer_minutes=buffer_minutes,
            currencies=currencies,
            min_impact=min_impact,
        )
        result["provider"] = provider.name
        return result
