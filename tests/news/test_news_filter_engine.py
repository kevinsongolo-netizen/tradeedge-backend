"""Tests for the news/economic calendar filter engine (Sprint 12)."""
from datetime import datetime, timezone

from app.news.news_filter_engine import evaluate_news_risk


def _event(time, impact="high", currency="USD", event="NFP", is_placeholder=False):
    return {
        "time": time,
        "currency": currency,
        "event": event,
        "impact": impact,
        "actual": None,
        "estimate": None,
        "previous": None,
        "isPlaceholder": is_placeholder,
    }


def test_high_impact_event_within_buffer_flags_risk():
    planned = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    events = [_event("2026-07-13T12:30:00Z")]
    result = evaluate_news_risk(events, planned, buffer_minutes=60)
    assert result["has_high_impact_nearby"] is True
    assert len(result["matching_events"]) == 1
    assert result["matching_events"][0]["minutesAway"] == 30.0
    assert result["warnings"]


def test_event_outside_buffer_is_not_flagged():
    planned = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    events = [_event("2026-07-13T15:00:00Z")]
    result = evaluate_news_risk(events, planned, buffer_minutes=60)
    assert result["has_high_impact_nearby"] is False
    assert result["matching_events"] == []


def test_low_impact_event_filtered_out_by_min_impact():
    planned = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    events = [_event("2026-07-13T12:10:00Z", impact="low")]
    result = evaluate_news_risk(events, planned, buffer_minutes=60, min_impact="high")
    assert result["has_high_impact_nearby"] is False


def test_currency_filter_excludes_non_matching():
    planned = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    events = [_event("2026-07-13T12:10:00Z", currency="EUR")]
    result = evaluate_news_risk(events, planned, buffer_minutes=60, currencies=["USD"])
    assert result["has_high_impact_nearby"] is False


def test_currency_filter_includes_matching():
    planned = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    events = [_event("2026-07-13T12:10:00Z", currency="USD")]
    result = evaluate_news_risk(events, planned, buffer_minutes=60, currencies=["USD", "EUR"])
    assert result["has_high_impact_nearby"] is True


def test_placeholder_event_flagged_in_result():
    planned = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    events = [_event("2026-07-13T12:10:00Z", is_placeholder=True)]
    result = evaluate_news_risk(events, planned, buffer_minutes=60)
    assert result["is_placeholder"] is True
    assert any("PLACEHOLDER" in w for w in result["warnings"])


def test_events_sorted_by_closest_first():
    planned = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    events = [
        _event("2026-07-13T12:50:00Z", event="Far"),
        _event("2026-07-13T12:10:00Z", event="Near"),
    ]
    result = evaluate_news_risk(events, planned, buffer_minutes=60)
    assert result["matching_events"][0]["event"] == "Near"


def test_invalid_time_string_is_skipped_not_raised():
    planned = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    events = [_event("not-a-real-timestamp")]
    result = evaluate_news_risk(events, planned, buffer_minutes=60)
    assert result["matching_events"] == []
