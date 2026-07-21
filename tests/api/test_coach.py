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

    # User-requested improvement: "Consider dropping: XAUUSD" needs
    # evidence, not just a name. Win rate/net P&L already existed on
    # the row (winRate/totalPnl); profitFactor and worstSession are new.
    pts = body["pairToStopTrading"]
    assert pts["profitFactor"] == 80.0 / (40.0 * 5)  # gross profit / gross loss
    assert pts["worstSession"] == "Asian"  # every XAUUSD trade in the fixture is Asian session
    assert "Infinity" not in resp.text
    assert "NaN" not in resp.text


def test_coach_deep_dive_is_a_valid_shape_for_dimension_stats(client):
    _seed_deep_dive_trades(client)
    resp = client.get("/api/v1/coach/deep-dive")
    body = resp.json()
    for field in ("bestSetup", "worstSetup", "worstDayToTrade", "bestSession", "pairToStopTrading"):
        row = body[field]
        if row is not None:
            for key in (
                "key", "count", "wins", "losses", "breakeven", "winRate", "expectancy", "totalPnl",
                "profitFactor", "confident", "worstSession",
            ):
                assert key in row, f"{field} missing {key}"


# --- GET /coach/playbook (Sprint 20 Phase 3 #6) --------------------------------


def test_playbook_empty_with_no_trades(client):
    resp = client.get("/api/v1/coach/playbook")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["setups"] == []
    assert body["sampleSize"] == 0


def test_playbook_excludes_thin_poi_groups(client):
    client.post(
        "/api/v1/trades",
        json={"id": "pb1", "date": "2026-01-01", "pair": "EURUSD", "h4PoiType": "Bullish OB", "pnl": 10.0},
    )
    resp = client.get("/api/v1/coach/playbook")
    assert resp.status_code == 200, resp.text
    assert resp.json()["setups"] == []


def test_playbook_surfaces_a_setup_with_enough_samples_and_example_screenshot(client):
    for i in range(5):
        client.post(
            "/api/v1/trades",
            json={
                "id": f"pb{i}",
                "date": f"2026-01-0{i + 1}",
                "pair": "EURUSD",
                "h4PoiType": "Bullish OB",
                "session": "London",
                "pnl": 50.0,
                "rr": 2.5,
                "screenshots": [{"url": f"https://x/{i}.png", "kind": "entry"}],
            },
        )
    resp = client.get("/api/v1/coach/playbook")
    assert resp.status_code == 200, resp.text
    setups = resp.json()["setups"]
    assert len(setups) == 1
    setup = setups[0]
    assert setup["poiType"] == "Bullish OB"
    assert setup["count"] == 5
    assert setup["winRate"] == 100.0
    assert setup["bestSession"] == "London"
    assert len(setup["exampleScreenshots"]) >= 1
    assert "averageHoldingTime" not in setup


def test_edge_patterns_empty_with_no_trades(client):
    resp = client.get("/api/v1/coach/edge-patterns")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["patterns"] == []
    assert body["hasEnoughData"] is False
    assert body["sampleSize"] == 0


def test_edge_patterns_surfaces_a_full_six_dimension_combination(client):
    for i in range(4):
        client.post(
            "/api/v1/trades",
            json={
                "id": f"edge{i}",
                "date": f"2026-01-0{i + 1}",
                "pair": "BTCUSD",
                "direction": "sell",
                "timeframe": "M15",
                "h4PoiType": "Bearish Order Block",
                "premiumDiscount": "Premium",
                "session": "London",
                "pnl": 50.0 if i < 3 else -20.0,
                "rr": 2.8,
            },
        )
    resp = client.get("/api/v1/coach/edge-patterns")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["hasEnoughData"] is True
    assert len(body["patterns"]) == 1
    p = body["patterns"][0]
    assert p["pair"] == "BTCUSD"
    assert p["direction"] == "sell"
    assert p["timeframe"] == "M15"
    assert p["poiType"] == "Bearish Order Block"
    assert p["premiumDiscount"] == "Premium"
    assert p["session"] == "London"
    assert p["count"] == 4
    assert p["wins"] == 3
    assert p["winRate"] == 75.0


def test_edge_patterns_excludes_trades_missing_any_dimension(client):
    client.post(
        "/api/v1/trades",
        json={"id": "edge-partial", "date": "2026-01-01", "pair": "EURUSD", "direction": "buy", "pnl": 10.0},
    )
    resp = client.get("/api/v1/coach/edge-patterns")
    assert resp.status_code == 200, resp.text
    assert resp.json()["patterns"] == []


# --- GET /coach/discovered-patterns (Sprint 20 Phase 6) ------------------------

def test_discovered_patterns_empty_with_no_trades(client):
    resp = client.get("/api/v1/coach/discovered-patterns")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["patterns"] == []
    assert body["hasEnoughData"] is False


def test_discovered_patterns_surfaces_real_separation(client):
    for i in range(4):
        client.post(
            "/api/v1/trades",
            json={"id": f"disc-w{i}", "date": f"2026-02-0{i + 1}", "session": "London", "pnl": 40.0},
        )
    for i in range(4):
        client.post(
            "/api/v1/trades",
            json={"id": f"disc-l{i}", "date": f"2026-02-1{i + 1}", "session": "Asian", "pnl": -25.0},
        )
    resp = client.get("/api/v1/coach/discovered-patterns")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["hasEnoughData"] is True
    assert any("London" in p for p in body["patterns"])


# --- GET /coach/mentor-report (Sprint 20 Phase 7) ------------------------------

def test_mentor_report_empty_with_no_trades(client):
    resp = client.get("/api/v1/coach/mentor-report")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["hasEnoughData"] is False
    assert body["period"] == "week"


def test_mentor_report_rejects_invalid_period(client):
    resp = client.get("/api/v1/coach/mentor-report", params={"period": "year"})
    assert resp.status_code == 422


def test_mentor_report_month_period_surfaces_stats(client):
    import datetime
    today = datetime.date.today()
    for i in range(5):
        d = today - datetime.timedelta(days=i)
        client.post(
            "/api/v1/trades",
            json={
                "id": f"mentor{i}", "date": d.isoformat(), "pair": "EURUSD",
                "pnl": 40.0 if i % 2 == 0 else -15.0, "failedTags": ["Late entry"] if i % 2 else [],
            },
        )
    resp = client.get("/api/v1/coach/mentor-report", params={"period": "month"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["period"] == "month"
    assert body["hasEnoughData"] is True
    assert body["periodSampleSize"] == 5


# --- GET /coach/edge-profile (Sprint 20 Phase 8) -------------------------------

def test_edge_profile_empty_with_no_trades(client):
    resp = client.get("/api/v1/coach/edge-profile")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["hasEnoughData"] is False
    assert body["winnerCharacteristics"] == []


def test_edge_profile_ranks_characteristics_from_history(client):
    for i in range(4):
        client.post(
            "/api/v1/trades",
            json={
                "id": f"edgeprofile-w{i}", "date": f"2026-04-0{i + 1}", "session": "London",
                "m15Confirmations": ["Fresh Order Block"], "pnl": 40.0,
            },
        )
    for i in range(4):
        client.post(
            "/api/v1/trades",
            json={
                "id": f"edgeprofile-l{i}", "date": f"2026-04-1{i + 1}", "session": "Asian",
                "m15Confirmations": ["Mitigated Order Block"], "pnl": -20.0,
            },
        )
    resp = client.get("/api/v1/coach/edge-profile")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["hasEnoughData"] is True
    winner_labels = {c["label"] for c in body["winnerCharacteristics"]}
    loser_labels = {c["label"] for c in body["loserCharacteristics"]}
    assert "Fresh Order Block" in winner_labels
    assert "London" in winner_labels
    assert "Mitigated Order Block" in loser_labels
    assert "Asian" in loser_labels
