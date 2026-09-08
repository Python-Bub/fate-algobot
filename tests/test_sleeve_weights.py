"""Sleeve weight tables — 100% sums, no HFT↔LT bleed, index ban."""

from __future__ import annotations

import os

import pytest

from analytics.sleeve_weights import (
    SLEEVES,
    HFT_PCT,
    LONGTERM_PCT,
    assert_tables_valid,
    no_cross_bleed,
    pct_sum,
    resolve_sleeve,
    apply_sleeve_env,
)
from analytics.rank_pipeline import curriculum_soft_boosts


def test_all_sleeves_sum_100():
    assert_tables_valid()
    for s in SLEEVES:
        assert pct_sum(s) == pytest.approx(100.0, abs=0.01)


def test_no_hft_longterm_bleed():
    bleed = no_cross_bleed()
    assert bleed["ok"] is True
    assert bleed["forbidden_overlap"] == []
    assert bleed["hft_cramer"] == 0.0
    assert bleed["lt_obi"] == 0.0
    assert bleed["index_etf_allowed"]["longterm"] > 0


def test_resolve_sleeve_hold_days(monkeypatch):
    monkeypatch.delenv("FATE_SLEEVE", raising=False)
    monkeypatch.delenv("PAPER_SIM_SLEEVE", raising=False)
    monkeypatch.setenv("HOLD_DAYS_DEFAULT", "20")
    assert resolve_sleeve() == "longterm"
    monkeypatch.setenv("HOLD_DAYS_DEFAULT", "5")
    assert resolve_sleeve() == "weekly"


def test_curriculum_soft_gated_to_weekly_lt(monkeypatch):
    monkeypatch.setenv("RANK_W_INFLATION", "0.12")
    monkeypatch.setenv("RANK_W_RATE_CYCLE", "0.12")
    monkeypatch.setenv("RANK_W_BUY_HOLD", "0.14")
    monkeypatch.setenv("RANK_W_ALT_CONTEXT", "0.04")
    mb = {"macro_score": 0.4, "spread_10y2y": 0.01, "vix": 18.0}
    assert curriculum_soft_boosts(sleeve="hft", macro_bundle=mb, fund_score=0.5) == {}
    assert curriculum_soft_boosts(sleeve="day_trade", macro_bundle=mb, fund_score=0.5) == {}
    assert curriculum_soft_boosts(sleeve="fortress", macro_bundle=mb, fund_score=0.5) == {}
    lt = curriculum_soft_boosts(sleeve="longterm", macro_bundle=mb, fund_score=0.5)
    assert "dca_buy_hold" in lt or "interest_rate_cycle" in lt or "inflation_deflation" in lt


def test_hft_has_no_fundamental_weights():
    for k in ("cramer_daily", "power_people", "value", "book", "macro_cycle", "dca_buy_hold", "buffett_graham"):
        assert HFT_PCT.get(k, 0.0) == 0.0
    assert HFT_PCT["obi"] > 0 and HFT_PCT["tape"] > 0


def test_longterm_has_no_microstructure():
    for k in ("obi", "tape", "spread_liquidity", "micro_price"):
        assert LONGTERM_PCT.get(k, 0.0) == 0.0
    assert LONGTERM_PCT["value_dcf"] > 0
    assert LONGTERM_PCT["macro_top_down_bottom_up"] > 0
    assert LONGTERM_PCT["dca_buy_hold"] > 0
    assert LONGTERM_PCT["index_etf"] > 0


def test_index_etf_allowed_under_control():
    bleed = no_cross_bleed()
    assert bleed["ok"] is True
    assert bleed["index_etf_allowed"]["longterm"] >= 4.0
    assert bleed["index_etf_allowed"]["fortress"] >= 1.0
    assert bleed["hft_cramer"] == 0.0


def test_cramer_daily_on_active_non_hft():
    from analytics.sleeve_weights import FORTRESS_PCT, DAY_TRADE_PCT, WEEKLY_PCT, LONGTERM_PCT

    assert FORTRESS_PCT["cramer_daily"] > 0
    assert DAY_TRADE_PCT["cramer_daily"] > 0
    assert WEEKLY_PCT["cramer_daily"] > 0
    assert LONGTERM_PCT["cramer_daily"] > 0
    assert HFT_PCT.get("cramer_daily", 0.0) == 0.0


def test_hft_news_env_is_zero(monkeypatch):
    monkeypatch.delenv("HFT_W_NEWS_PROB", raising=False)
    apply_sleeve_env("hft", force=True)
    assert float(os.getenv("HFT_W_NEWS_PROB", "1") or 1) == 0.0
    assert HFT_PCT["obi"] >= 30.0
    assert HFT_PCT["news_micro"] == 0.0


def test_fortress_cramer_capped_and_momentum_up(monkeypatch):
    monkeypatch.setenv("FORTRESS_CRAMER_BLEND", "0.9")
    monkeypatch.setenv("MATH_FIRST_WEIGHTS", "true")
    apply_sleeve_env("fortress", force=True)
    assert float(os.getenv("FORTRESS_CRAMER_BLEND", "1") or 1) <= 0.06
    assert float(os.getenv("HF_W_MOMENTUM", "0") or 0) >= 0.15
    assert float(os.getenv("HF_W_TREND", "0") or 0) >= 0.14
    assert float(os.getenv("FORTRESS_SOCIAL_BLEND", "1") or 1) == pytest.approx(0.08, abs=1e-9)


def test_apply_sleeve_env_locks_liquidity_on_fortress(monkeypatch):
    monkeypatch.delenv("HF_W_LIQUIDITY_MM", raising=False)
    monkeypatch.delenv("HF_W_ETF_DISLOC", raising=False)
    monkeypatch.delenv("FORTRESS_BAN_INDEX_BUYS", raising=False)
    apply_sleeve_env("fortress", force=True)
    assert os.getenv("FATE_SLEEVE") == "fortress"
    assert os.getenv("HF_W_LIQUIDITY_MM") == "0.0"
    assert os.getenv("FORTRESS_BAN_INDEX_BUYS") == "false"
    assert float(os.getenv("HF_W_ETF_DISLOC", "0") or 0) > 0
