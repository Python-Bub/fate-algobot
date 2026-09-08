"""Tests for text→math transforms, math pivot, honest operator protocol."""

from __future__ import annotations

from intel.text_to_math import event_surprise_z, score_texts_to_math, zscore
from analytics.math_pivot import apply_pivot_to_components, pivot_status, weight_multiplier
from intel.operator_persona import format_reply, honest_critique_for_topic, update_mood
from intel.operator_doc import extract_latest_user_message
from intel.operator_code_edit import parse_command_tags


def test_zscore_and_surprise():
    assert abs(zscore(2.0, 0.0, 1.0) - 2.0) < 1e-9
    assert event_surprise_z(1.2, 1.0, 0.1) > 0


def test_score_texts_to_math_numeric():
    out = score_texts_to_math(
        ["Company beats estimates and raises guidance", "Strong demand growth"],
        conviction=0.4,
        reliability=0.8,
    )
    d = out.to_dict()
    assert "sentiment_z" in d
    assert -1.0 <= d["final_math"] <= 1.0
    assert d["sample_count"] == 2


def test_math_pivot_boosts_math_softens_news(monkeypatch):
    monkeypatch.setenv("PURE_MATH_PIVOT", "true")
    monkeypatch.setenv("MATH_PIVOT_MATH_MULT", "1.35")
    monkeypatch.setenv("MATH_PIVOT_NEWS_MULT", "0.55")
    assert weight_multiplier("hedge_fund") == 1.35
    assert weight_multiplier("news") == 0.55
    comps = apply_pivot_to_components({"hedge_fund": 1.0, "news": 1.0})
    assert comps["hedge_fund"] == 1.35
    assert abs(comps["news"] - 0.55) < 1e-9
    assert pivot_status()["pure_math_pivot"] is True


def test_persona_honest_not_theatrical():
    st = update_mood(-0.05, paper_hurting=True)
    assert st.mood in ("concerned", "dissatisfied")
    assert st.concern > 0.4
    critique = honest_critique_for_topic("we are losing money on paper")
    assert critique and "Losses are real" in critique
    text = format_reply("checking stack", st=st, critique=critique)
    assert "Operator AI" in text
    assert "unhinged" not in text.lower()
    assert "roast" not in text.lower()


def test_extract_user_and_commands():
    doc = "USER: hello\nAI: hi\nUSER: [[status]] fix the news weight\n"
    msg = extract_latest_user_message(doc)
    assert msg and "status" in msg
    assert "status" in parse_command_tags(msg)
