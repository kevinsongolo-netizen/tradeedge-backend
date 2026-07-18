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


# --- Sprint 20 Phase 6 -- "Analyze Trade" / possible_reasons -------------------

def _seed_losing_history_with_shared_characteristic(client):
    """4 similar past losses sharing pair/direction/POI and an
    'already-mitigated Order Block' tag -- enough for both search_similar
    (same pair/direction/POI) and characteristic_gap_engine's
    MIN_SAMPLE_FOR_GAP (3) to recognize a real loser echo."""
    for i in range(4):
        client.post(
            "/api/v1/trades",
            json={
                "id": f"hist-loss-{i}",
                "date": f"2026-03-0{i + 1}",
                "pair": "EURUSD",
                "direction": "buy",
                "entry": 1.1000,
                "exit": 1.0950,
                "sl": 1.0950,
                "tp": 1.1150,
                "pnl": -30.0,
                "rr": 2.0,
                "h4PoiType": "Order Block",
                "premiumDiscount": "Discount",
                "session": "London",
                "m15Confirmations": ["Mitigated Order Block"],
            },
        )


def test_review_trade_loss_surfaces_possible_reasons_from_history(client):
    _seed_losing_history_with_shared_characteristic(client)
    resp = client.post(
        "/api/v1/coach/review-trade",
        json=_base_body(
            pair="EURUSD", direction="buy", entry=1.1000, exit=1.0950,
            sl=1.0950, tp=1.1150, pnl=-25.0, rr=2.0,
            h4PoiType="Order Block", premiumDiscount="Discount", session="London",
            rulesFollowed="all", exitReason="Stop Loss Hit",
            m15Confirmations=["Mitigated Order Block"],
        ),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["outcome"] == "LOSS"
    assert len(data["possibleReasons"]) >= 1
    assert data["mostLikelyCause"] is not None


def test_review_trade_win_never_populates_possible_reasons(client):
    resp = client.post("/api/v1/coach/review-trade", json=_base_body())
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["outcome"] == "WIN"
    assert data["possibleReasons"] == []
    assert data["mostLikelyCause"] is None
