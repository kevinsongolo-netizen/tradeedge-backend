"""API test for Sprint 12 multi-timeframe confirmation via
``POST /api/v1/chart/full-analysis/candles`` with ``m15Candles``."""
from tests.chart.test_candle_smc_engine import _BULLISH_ROWS

_CANDLES_PAYLOAD = [
    {"time": str(i), "open": o, "high": h, "low": l, "close": c}
    for i, (o, h, l, c) in enumerate(_BULLISH_ROWS)
]


def test_full_analysis_candles_with_m15_confirmation(client):
    resp = client.post(
        "/api/v1/chart/full-analysis/candles",
        json={
            "candles": _CANDLES_PAYLOAD,
            "m15Candles": _CANDLES_PAYLOAD,
            "plannedRr": 3.0,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["multiTimeframe"] is not None
    assert body["multiTimeframe"]["hasM15EntryConfirmation"] is True
    assert body["multiTimeframe"]["aligned"] is True


def test_full_analysis_candles_without_m15_has_no_confirmation_block(client):
    resp = client.post(
        "/api/v1/chart/full-analysis/candles",
        json={"candles": _CANDLES_PAYLOAD, "plannedRr": 3.0},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["multiTimeframe"] is None
