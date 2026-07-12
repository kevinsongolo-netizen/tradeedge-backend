"""AI Coach API tests — ``GET /api/v1/coach/insights`` (Section 4.6)."""


def test_coach_insights_with_few_trades(client):
    client.post("/api/v1/trades", json={"id": "c1", "date": "2026-01-01", "pnl": 10.0})
    resp = client.get("/api/v1/coach/insights")
    assert resp.status_code == 200
    assert len(resp.json()["insights"]) >= 1


def test_coach_insights_respects_limit(client):
    for i in range(15):
        client.post(
            "/api/v1/trades",
            json={
                "id": f"c{i}", "date": f"2026-01-{(i % 28) + 1:02d}", "pair": "EURUSD", "session": "London",
                "h4PoiType": "OB", "m15Confirmations": ["BOS"], "pnl": 50.0 if i % 2 == 0 else -20.0,
                "rulesFollowed": "all", "followedPlan": "Yes", "emotion": "Calm",
            },
        )
    resp = client.get("/api/v1/coach/insights", params={"limit": 2})
    assert resp.status_code == 200
    assert len(resp.json()["insights"]) <= 2


def test_coach_insights_no_trades(client):
    resp = client.get("/api/v1/coach/insights")
    assert resp.status_code == 200
    assert resp.json()["insights"][0]["level"] == "info"


# --- GET /coach/deep-dive (Sprint 8 Phase 6) -----------------------------------

def _seed_deep_dive_trades(client):
    """Seeds enough trades, concentrated so specific dimensions clear
    the confidence threshold (>=3 samples), to exercise every deep-dive
    field deterministically."""
    # XAUUSD: consistently losing (5 losses, 1 win) -> should be flagged pairToStopTrading
    for i in range(6):
        client.post(
            "/api/v1/trades",
            json={
                "id": f"xau{i}",
                "date": f"2026-02-{i + 1:02d}",
                "pair": "XAUUSD",
                "session": "Asian",
                "h4PoiType": "FVG",
                "m15Confirmations": [],
                "pnl": -40.0 if i < 5 else 80.0,
                "rr": 1.0,
                "rulesFollowed": "all",
                "followedPlan": "Yes",
                "emotion": "FOMO",
                "failedTags": ["FOMO"],
            },
        )
    # EURUSD: consistently winning -> should surface as bestSetup / whyWinning
    for i in range(6):
        client.post(
            "/api/v1/trades",
            json={
                "id": f"eur{i}",
                "date": f"2026-03-{i + 1:02d}",
                "pair": "EURUSD",
                "session": "London",
                "h4PoiType": "Order Block",
                "m15Confirmations": ["BOS"],
                "pnl": 90.0,
                "rr": 2.5,
                "rulesFollowed": "all",
                "followedPlan": "Yes",
                "emotion": "Calm",
                "workedTags": ["Patience"],
            },
        )


def test_coach_deep_dive_no_trades_returns_fallback_text(client):
    resp = client.get("/api/v1/coach/deep-dive")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sampleSize"] == 0
    assert "Not enough data" in body["whyLosing"]
    assert "Not enough data" in body["whyWinning"]
    assert body["biggestMistake"] is None
    assert body["bestSetup"] is None
    assert body["pairToStopTrading"] is None


def test_coach_deep_dive_with_data_flags_losing_pair_and_best_setup(client):
    _seed_deep_dive_trades(client)
    resp = client.get("/api/v1/coach/deep-dive")
    assert resp.status_code == 200
    body = resp.json()

    assert body["sampleSize"] == 12
    assert body["pairToStopTrading"] is not None
    assert body["pairToStopTrading"]["key"] == "XAUUSD"
    assert body["bestSetup"] is not None
    assert "FOMO" in body["whyLosing"]
    assert body["biggestMistake"]["name"] == "FOMO"
    assert body["version"] == "8.0"


def test_coach_deep_dive_is_a_valid_shape_for_dimension_stats(client):
    _seed_deep_dive_trades(client)
    resp = client.get("/api/v1/coach/deep-dive")
    body = resp.json()
    for field in ("bestSetup", "worstSetup", "worstDayToTrade", "bestSession", "pairToStopTrading"):
        row = body[field]
        if row is not None:
            for key in ("key", "count", "wins", "losses", "breakeven", "winRate", "expectancy", "totalPnl", "confident"):
                assert key in row, f"{field} missing {key}"
