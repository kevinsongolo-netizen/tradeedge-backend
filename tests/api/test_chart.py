"""API tests for the Chart Analysis Engine (``/api/v1/chart/*``).

Sprint 10: Level-1-only reads (analyze-candles/analyze-image), using
the same hand-verified bullish candle series as
``tests/chart/test_candle_smc_engine.py`` so the expected trend/bias is
known ground truth, not a guess.

Sprint 20: the screenshot-first workflow's ``/full-analysis/image`` --
reads a screenshot, compares it against the caller's own trade history,
and must NEVER return a verdict (no tradeStatus/recommendation/VALID
field anywhere), only an honest insight that degrades gracefully with
thin history.
"""
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

# PlaceholderVisionProvider (active whenever no ANTHROPIC_API_KEY is
# set, i.e. in this test environment) always reads a screenshot as
# this exact pair/direction -- see app/chart/vision_provider.py.
_PLACEHOLDER_PAIR = "PLACEHOLDER — GOLDmicro (example data)"
_PLACEHOLDER_TRADE = {
    "date": "2026-01-01", "pair": _PLACEHOLDER_PAIR, "direction": "buy", "asset": "Metals",
    "entry": 2400.0, "exit": 2410.0, "pnl": 50.0, "rr": 2.0, "session": "London",
}


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


def test_full_analysis_image_returns_extraction_and_insight_no_verdict(client):
    """Sprint 20: the screenshot-first workflow's response must contain
    the read setup (extraction) and a plain-language insight -- and
    must NEVER contain a verdict field anywhere (tradeStatus,
    recommendation, VALID/INVALID, TAKE/WAIT), since that decision
    stays with the trader."""
    files = {"file": ("chart.png", io.BytesIO(_TINY_PNG), "image/png")}
    resp = client.post("/api/v1/chart/full-analysis/image", files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert "extraction" in body and "insight" in body and "meta" in body
    assert body["meta"]["isPlaceholder"] is True
    assert body["extraction"]["pair"] == _PLACEHOLDER_PAIR

    # No verdict anywhere in the response, at any nesting level.
    serialized = str(body)
    for forbidden in ("tradeStatus", "recommendation", "VALID", "INVALID", "TAKE", "WAIT"):
        assert forbidden not in serialized


def test_full_analysis_image_reports_thin_history_honestly(client):
    files = {"file": ("chart.png", io.BytesIO(_TINY_PNG), "image/png")}
    resp = client.post("/api/v1/chart/full-analysis/image", files=files)
    assert resp.status_code == 200, resp.text
    insight = resp.json()["insight"]
    assert insight["hasEnoughHistory"] is False
    assert insight["sampleSize"] == 0
    assert "Not enough logged trades" in insight["narrative"][0]


def test_full_analysis_image_finds_similar_trades_once_history_exists(client):
    for i in range(6):
        client.post("/api/v1/trades", json={**_PLACEHOLDER_TRADE, "id": f"hist-{i}"})

    files = {"file": ("chart.png", io.BytesIO(_TINY_PNG), "image/png")}
    resp = client.post("/api/v1/chart/full-analysis/image", files=files)
    assert resp.status_code == 200, resp.text
    insight = resp.json()["insight"]
    assert insight["hasEnoughHistory"] is True
    assert insight["sampleSize"] >= 1
    assert insight["wins"] >= 1
    assert len(insight["narrative"]) >= 1


def test_full_analysis_image_rejects_unsupported_content_type(client):
    files = {"file": ("chart.txt", io.BytesIO(b"not an image"), "text/plain")}
    resp = client.post("/api/v1/chart/full-analysis/image", files=files)
    assert resp.status_code == 422, resp.text
