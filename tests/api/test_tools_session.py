"""API tests for ``POST /api/v1/tools/session-detect`` (Sprint 12)."""


def test_session_detect_with_timestamp(client):
    resp = client.post(
        "/api/v1/tools/session-detect",
        json={"timestamp": "2026-07-13T13:30:00Z"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["isOverlap"] is True
    assert "London" in body["activeSessions"]
    assert "New York" in body["activeSessions"]


def test_session_detect_defaults_to_now(client):
    resp = client.post("/api/v1/tools/session-detect", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "utcTime" in body
    assert "primarySession" in body
