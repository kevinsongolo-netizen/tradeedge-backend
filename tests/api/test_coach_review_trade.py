"""API tests for ``POST /api/v1/coach/review-trade`` (Sprint 11 — AI
review-after-close)."""


def _base_body(**overrides):
    body = {
        "pair": "EURUSD",
        "direction": "buy",
        "entry": 1.1000,
        "exit": 1.1100,
        "pnl": 50.0,
        "rr": 2.5,
        "rulesFollowed": "all",
        "workedTags": ["Followed my plan"],
        "exitReason": "Take Profit Hit",
        "h4Trend": "Bullish",
        "h4PoiType": "Order Block",
    }
    body.update(overrides)
    return body


def test_review_trade_win(client):
    resp = client.post("/api/v1/coach/review-trade", json=_base_body())
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["outcome"] == "WIN"
    assert data["headline"] == "WIN — Clean Execution"


def test_review_trade_missing_exit_is_validation_error(client):
    body = _base_body()
    del body["exit"]
    resp = client.post("/api/v1/coach/review-trade", json=body)
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_review_trade_loss(client):
    resp = client.post(
        "/api/v1/coach/review-trade",
        json=_base_body(pnl=-20.0, rulesFollowed="none", failedTags=["Revenge trade"], exitReason="Stop Loss Hit"),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["outcome"] == "LOSS"
    assert "Revenge trade" in data["whatWentWrong"]
