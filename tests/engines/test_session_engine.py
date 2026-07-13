"""Tests for the trading session auto-detection engine (Sprint 12)."""
from datetime import datetime, timezone

from app.engines.session_engine import detect_session


def _at(hour, minute=0):
    return datetime(2026, 7, 13, hour, minute, tzinfo=timezone.utc)


def test_asian_session():
    result = detect_session(_at(3))
    assert result["active_sessions"] == ["Asian"]
    assert result["primary_session"] == "Asian"
    assert result["is_overlap"] is False


def test_london_session():
    result = detect_session(_at(9))
    assert "London" in result["active_sessions"]
    assert result["primary_session"] == "London"


def test_new_york_only():
    result = detect_session(_at(18))
    assert result["active_sessions"] == ["New York"]


def test_london_ny_overlap():
    result = detect_session(_at(13))
    assert "London" in result["active_sessions"]
    assert "New York" in result["active_sessions"]
    assert result["is_overlap"] is True
    assert result["primary_session"] == "London/NY Overlap"


def test_between_sessions():
    result = detect_session(_at(23))
    assert result["active_sessions"] == []
    assert result["primary_session"] == "Between sessions"


def test_defaults_to_now_when_none():
    result = detect_session(None)
    assert "utc_time" in result


def test_naive_datetime_treated_as_utc():
    naive = datetime(2026, 7, 13, 3, 0)
    result = detect_session(naive)
    assert result["active_sessions"] == ["Asian"]
