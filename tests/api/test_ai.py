"""AI analysis API tests — ``/api/v1/ai/*`` (Section 4.3)."""


def test_analyze_without_persisting_does_not_create_trade(client):
    resp = client.post("/api/v1/ai/analyze", json={"h4Trend": "Bullish", "rr": 2.5, "confidence": 80})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["ruleScore"], int)
    assert body["executionScore"] is None  # no exit/pnl -> open trade
    assert body["ruleEngineVersion"] == "6.0"
    # Nothing was persisted:
    assert client.get("/api/v1/trades").json()["items"] == []


def test_analyze_closed_trade_has_execution_score(client):
    resp = client.post(
        "/api/v1/ai/analyze",
        json={"h4Trend": "Bullish", "rr": 2.5, "confidence": 80, "exit": 1.09, "pnl": 50, "exitReason": "Take Profit Hit"},
    )
    body = resp.json()
    assert body["executionScore"] is not None
    assert body["overallScore"] is not None


def test_rule_only_endpoint(client):
    resp = client.post("/api/v1/ai/rule", json={"h4Trend": "Bullish", "session": "London", "rr": 2.5})
    assert resp.status_code == 200
    body = resp.json()
    assert "ruleScore" in body
    assert "ruleBreakdown" in body


def test_execution_only_endpoint(client):
    resp = client.post(
        "/api/v1/ai/execution",
        json={"entry": 1.08, "sl": 1.075, "tp": 1.09, "rr": 2.0, "exitReason": "Take Profit Hit"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "executionScore" in body
    assert body["grade"] in ("EXCELLENT", "GOOD", "FAIR", "POOR")


def test_get_weights_returns_defaults(client):
    resp = client.get("/api/v1/ai/weights")
    assert resp.status_code == 200
    body = resp.json()
    assert "rule" in body and "execution" in body and "similarity" in body
    assert abs(sum(body["rule"].values()) - 100) < 1e-6


def test_set_weights_overrides_and_persists(client):
    resp = client.put("/api/v1/ai/weights", json={"rule": {"h4Trend": 50}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rule"]["h4Trend"] > 10  # boosted relative to default

    # Persisted: a second GET should reflect the same override.
    resp2 = client.get("/api/v1/ai/weights")
    assert resp2.json()["rule"]["h4Trend"] == body["rule"]["h4Trend"]


def test_analysis_history_for_trade(client):
    trade = {
        "id": "hist-1", "date": "2026-01-01", "pair": "EURUSD", "direction": "buy", "asset": "Forex",
        "entry": 1.08, "rr": 2.0, "confidence": 80,
    }
    client.post("/api/v1/trades", json=trade)
    resp = client.get("/api/v1/ai/trades/hist-1/analyses")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["tradeId"] == "hist-1"


def test_analysis_history_missing_trade_404(client):
    resp = client.get("/api/v1/ai/trades/nope/analyses")
    assert resp.status_code == 404


def test_rule_preview_matches_persisted_score(client):
    """Regression test for a bug found during Sprint 8: POST /ai/rule
    (and /ai/analyze, /ai/execution) used to pass TradeBase.to_model_kwargs()
    (snake_case: h4_trend, h4_poi_type, m15_confirmations, ...) straight
    into compute_rule_score(), which reads camelCase keys (h4Trend,
    h4PoiType, m15Confirmations, ...) — the same shape
    Trade.to_engine_dict() produces for a persisted trade. Every
    SMC-structure check silently failed in the preview even when set,
    while the actually-persisted score (computed from the saved ORM
    row's to_engine_dict()) was correct — so the live "check before
    saving" preview could disagree wildly with the score the trade
    actually got a moment after saving. This trade's real score should
    be 100 (every checklist item present); the bug scored the preview
    at 34."""
    candidate = {
        "pair": "EURUSD", "direction": "buy", "asset": "Forex", "session": "London",
        "h4Trend": "Bullish", "h4PoiType": "Order Block", "premiumDiscount": "Discount",
        "m15Confirmations": ["BOS", "CHOCH", "Liquidity Sweep"], "rr": 2.5, "confidence": 80,
        "followedPlan": "Yes", "news": "None",
    }

    preview = client.post("/api/v1/ai/rule", json=candidate)
    assert preview.status_code == 200
    preview_score = preview.json()["ruleScore"]

    saved = client.post("/api/v1/trades", json={**candidate, "id": "rule-preview-parity"})
    assert saved.status_code == 201
    persisted_score = saved.json()["ruleScore"]

    assert preview_score == persisted_score == 100
