"""Open Trade Alert Engine tests (Sprint 20 — repurposed Scanner).

Confirms the engine only ever compares live price against a trade's
own SL/TP -- never a rule verdict -- and degrades gracefully when a
pair has no live price yet.
"""
from app.engines.open_trade_alert_engine import build_open_trade_alerts


def _trade(**overrides):
    base = {"id": "t1", "pair": "GOLDmicro", "direction": "buy", "entry": 100.0, "sl": 90.0, "tp": 130.0}
    base.update(overrides)
    return base


def test_skips_trades_with_no_live_price_available():
    alerts = build_open_trade_alerts([_trade(pair="EURUSD")], {"GOLDmicro": 95.0})
    assert alerts == []


def test_monitoring_status_when_price_is_mid_range():
    alerts = build_open_trade_alerts([_trade()], {"GOLDmicro": 110.0})
    assert len(alerts) == 1
    assert alerts[0]["status"] == "MONITORING"
    assert alerts[0]["needsAttention"] is False


def test_sl_hit_for_buy_when_price_at_or_below_sl():
    alerts = build_open_trade_alerts([_trade()], {"GOLDmicro": 89.0})
    assert alerts[0]["status"] == "SL_HIT"
    assert alerts[0]["needsAttention"] is True


def test_tp_hit_for_buy_when_price_at_or_above_tp():
    alerts = build_open_trade_alerts([_trade()], {"GOLDmicro": 131.0})
    assert alerts[0]["status"] == "TP_HIT"


def test_sl_hit_direction_flipped_for_sell():
    trade = _trade(direction="sell", entry=100.0, sl=110.0, tp=70.0)
    alerts = build_open_trade_alerts([trade], {"GOLDmicro": 111.0})
    assert alerts[0]["status"] == "SL_HIT"


def test_near_sl_flagged_within_threshold():
    # Risk = 100 - 90 = 10. 15% of that = 1.5. Price 91 is 1 away from SL (90).
    alerts = build_open_trade_alerts([_trade()], {"GOLDmicro": 91.0})
    assert alerts[0]["status"] == "NEAR_SL"
    assert alerts[0]["needsAttention"] is True


def test_near_tp_flagged_within_threshold():
    # Reward = 130 - 100 = 30. 15% of that = 4.5. Price 127 is 3 away from TP (130).
    alerts = build_open_trade_alerts([_trade()], {"GOLDmicro": 127.0})
    assert alerts[0]["status"] == "NEAR_TP"


def test_output_has_no_verdict_field():
    alerts = build_open_trade_alerts([_trade()], {"GOLDmicro": 110.0})
    forbidden = {"tradeStatus", "recommendation", "isValid"}
    assert forbidden.isdisjoint(alerts[0].keys())
