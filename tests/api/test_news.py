"""API tests for ``POST /api/v1/news/check-calendar`` (Sprint 12)."""


def test_check_calendar_returns_placeholder_without_api_key(client):
    resp = client.post(
        "/api/v1/news/check-calendar",
        json={"plannedTime": "2026-07-13T12:00:00Z", "bufferMinutes": 1440},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider"] == "placeholder"
    assert body["isPlaceholder"] is True


def test_check_calendar_respects_buffer(client):
    resp = client.post(
        "/api/v1/news/check-calendar",
        json={"plannedTime": "2026-07-13T00:00:01Z", "bufferMinutes": 1},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["hasHighImpactNearby"] is False
