"""Rule Engine tests — scoring, weight normalization, edge cases."""
from app.engines.rule_engine import (
    DEFAULT_RULE_SCORE_WEIGHTS,
    compute_rule_score,
    normalize_rule_weights,
)

FULL_TRADE = {
    "h4Trend": "Bullish",
    "h4PoiType": "OB",
    "premiumDiscount": "Discount",
    "m15Confirmations": ["BOS", "CHOCH", "Liquidity Sweep"],
    "session": "London",
    "rr": 2.5,
    "news": "Low",
    "confidence": 80,
    "followedPlan": "Yes",
}


def test_full_trade_scores_100_and_recommends_take():
    result = compute_rule_score(FULL_TRADE)
    assert result["score"] == 100
    assert result["recommendation"] == "TAKE"
    assert result["missingConfirmations"] == []


def test_empty_trade_scores_low_and_never_crashes():
    # An absent "news" field defaults to "None" (no news risk), which
    # passes that single check — everything else fails, so the score is
    # low but not necessarily zero. This mirrors the JS engine exactly.
    result = compute_rule_score({})
    assert result["score"] < 20
    assert result["recommendation"] == "SKIP"
    assert len(result["missingConfirmations"]) == len(DEFAULT_RULE_SCORE_WEIGHTS) - 1


def test_none_trade_does_not_crash():
    result = compute_rule_score(None)
    assert isinstance(result["score"], int)
    assert result["recommendation"] == "SKIP"


def test_partial_rr_gives_half_credit():
    trade = {**FULL_TRADE, "rr": 1.2}  # 1 <= rr < 2 -> partial
    result = compute_rule_score(trade)
    rr_check = next(c for c in result["reasons"] if c["key"] == "rr")
    assert rr_check["partial"] is True
    assert rr_check["ok"] is False
    assert rr_check["points"] == round(DEFAULT_RULE_SCORE_WEIGHTS["rr"] / 2)


def test_confidence_on_0_10_scale_is_rescaled_to_100():
    trade = {**FULL_TRADE, "confidence": 8}  # 8 -> 80 after rescale
    result = compute_rule_score(trade)
    confidence_check = next(c for c in result["reasons"] if c["key"] == "confidence")
    assert confidence_check["ok"] is True


def test_recommendation_thresholds():
    assert compute_rule_score({**FULL_TRADE})["recommendation"] == "TAKE"
    # Knock score into the 60-79 range by removing several confirmations.
    weak = {"h4Trend": "Bullish", "session": "London", "rr": 2.5}
    result = compute_rule_score(weak)
    assert result["score"] < 80
    assert result["recommendation"] in ("CAUTION", "SKIP")


def test_weight_override_and_normalization_sums_to_100():
    weights = normalize_rule_weights({"h4Trend": 1000})
    assert abs(sum(weights.values()) - 100) < 1e-9
    # h4Trend should now dominate the distribution.
    assert weights["h4Trend"] > weights["session"]


def test_custom_weights_change_score():
    trade = {"h4Trend": "Bullish"}
    default_score = compute_rule_score(trade)["score"]
    boosted_score = compute_rule_score(trade, {"h4Trend": 1000})["score"]
    assert boosted_score > default_score


def test_news_high_impact_fails_anything_else_passes():
    # Ported verbatim from the JS engine: the only failing case is
    # High-impact news; Medium (and None/Low) both count as a pass, so
    # "partial" never actually fires for this check (JS parity, not a
    # bug introduced in the port).
    high = compute_rule_score({**FULL_TRADE, "news": "High"})
    medium = compute_rule_score({**FULL_TRADE, "news": "Medium"})
    news_high = next(c for c in high["reasons"] if c["key"] == "news")
    news_medium = next(c for c in medium["reasons"] if c["key"] == "news")
    assert news_high["ok"] is False
    assert news_medium["ok"] is True


def test_garbage_input_types_do_not_crash():
    trade = {"rr": "not-a-number", "confidence": [], "m15Confirmations": "not-a-list", "news": None}
    result = compute_rule_score(trade)
    assert isinstance(result["score"], int)
