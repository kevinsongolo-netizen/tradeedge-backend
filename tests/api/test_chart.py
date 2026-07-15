"""API tests for the Chart Analysis Engine (``/api/v1/chart/*``,
Sprint 10). Uses the same hand-verified bullish candle series as
``tests/chart/test_candle_smc_engine.py`` so the expected trend/bias
is known ground truth, not a guess."""
import io

from tests.chart.test_candle_smc_engine import _BULLISH_ROWS

_CANDLES_PAYLOAD = [
    {"time": str(i), "open": o, "high": h, "low": l, "close": c}
    for i, (o, h, l, c) in enumerate(_BULLISH_ROWS)
]

# A minimal valid 1x1 PNG (transparent pixel) — enough to pass the
# content-type/size checks without needing a real chart screenshot.
_TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000c4944415478da6360000002000155a2415d0000000049454e44"
    "ae426082"
)


def test_analyze_candles_returns_bullish_trend(client):
    resp = client.post("/api/v1/chart/analyze-candles", json={"candles": _CANDLES_PAYLOAD})
    assert resp.status_code == 200, resp.text
    data = resp.json()["analysis"]
    assert data["trend"] == "Bullish"
    assert data["source"] == "candles"


def test_analyze_candles_rejects_too_few_candles(client):
    resp = client.post("/api/v1/chart/analyze-candles", json={"candles": _CANDLES_PAYLOAD[:3]})
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_analyze_image_returns_placeholder_without_api_key(client):
    files = {"file": ("chart.png", io.BytesIO(_TINY_PNG), "image/png")}
    resp = client.post("/api/v1/chart/analyze-image", files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["meta"]["isPlaceholder"] is True
    assert body["analysis"]["isPlaceholder"] is True


def test_analyze_image_rejects_unsupported_content_type(client):
    files = {"file": ("chart.txt", io.BytesIO(b"not an image"), "text/plain")}
    resp = client.post("/api/v1/chart/analyze-image", files=files)
    assert resp.status_code == 422, resp.text


def test_full_analysis_image_returns_explicit_wait_not_classic_bias(client):
    """The screenshot path only ever sees ONE chart, so it can't run
    the dual-timeframe H4->M15 strategy -- it must return an honest,
    clearly-explained WAIT rather than silently falling back to the
    retired Classic Bias validator (which would make this the one
    place in the app running a second, different strategy)."""
    files = {"file": ("chart.png", io.BytesIO(_TINY_PNG), "image/png")}
    resp = client.post("/api/v1/chart/full-analysis/image", files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["validation"]["tradeStatus"] == "INVALID"
    assert body["validation"]["recommendation"] == "WAIT"
    assert body["validation"]["confidence"] == 0
    rule_statuses = {c["rule"]: c["status"] for c in body["validation"]["ruleChecks"]}
    assert rule_statuses == {
        "H4 Order Block/FVG": "NOT_CHECKED",
        "M15 Order Block/FVG": "NOT_CHECKED",
        "POI Alignment": "NOT_CHECKED",
        "Entry / SL / TP": "NOT_CHECKED",
    }
    assert "one chart" in body["validation"]["reasonsFailed"][0]
    assert body["coach"]["headline"] == "WAIT"


def test_full_analysis_candles_end_to_end(client):
    resp = client.post(
        "/api/v1/chart/full-analysis/candles",
        json={"candles": _CANDLES_PAYLOAD, "plannedRr": 3.0},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["analysis"]["trend"] == "Bullish"
    assert body["validation"]["tradeStatus"] in ("VALID", "INVALID")
    assert body["coach"]["headline"] in ("BUY ANALYSIS", "SELL ANALYSIS", "WAIT")
    assert 0 <= body["coach"]["confidence"]["overall"] <= 100


def test_validate_endpoint_standalone(client):
    analyze_resp = client.post("/api/v1/chart/analyze-candles", json={"candles": _CANDLES_PAYLOAD})
    analysis = analyze_resp.json()["analysis"]
    resp = client.post(
        "/api/v1/chart/validate",
        json={"analysis": analysis, "plannedRr": 3.0},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["tradeStatus"] in ("VALID", "INVALID")


def test_coach_endpoint_standalone(client):
    analyze_resp = client.post("/api/v1/chart/analyze-candles", json={"candles": _CANDLES_PAYLOAD})
    analysis = analyze_resp.json()["analysis"]
    validate_resp = client.post("/api/v1/chart/validate", json={"analysis": analysis, "plannedRr": 3.0})
    validation = validate_resp.json()
    resp = client.post("/api/v1/chart/coach", json={"analysis": analysis, "validation": validation})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["headline"] in ("BUY ANALYSIS", "SELL ANALYSIS", "WAIT")
    assert len(body["explanation"]) >= 1
