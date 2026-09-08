"""Point-in-time news + no theme predisposition + honest hist credit."""

from datetime import date, datetime, timezone

from analytics.sleeve_weights import FORTRESS_PCT, LONGTERM_PCT, WEEKLY_PCT, apply_sleeve_env, pct_sum
from analytics.water_theme import enabled, space_rank_boost, water_rank_boost
from intel.point_in_time import filter_items_as_of, item_not_after, news_window


def test_theme_default_off(monkeypatch):
    monkeypatch.delenv("FORTRESS_WATER_THEME", raising=False)
    monkeypatch.delenv("FORTRESS_SPACE_THEME", raising=False)
    assert enabled() is False
    b, meta = water_rank_boost("AWK", p_up=0.70, sleeve="fortress")
    assert b == 0.0
    assert meta["reason"] == "disabled"
    sp, sm = space_rank_boost("RKLB", p_up=0.70, sleeve="longterm")
    assert sp == 0.0
    assert sm["reason"] == "disabled"


def test_sleeve_tables_have_no_theme_mass():
    assert FORTRESS_PCT["water_datacenter"] == 0.0
    assert FORTRESS_PCT["pred_force"] == 0.0
    assert WEEKLY_PCT["water_datacenter"] == 0.0
    assert LONGTERM_PCT["water_datacenter"] == 0.0
    assert LONGTERM_PCT["space_infra"] == 0.0
    assert pct_sum("fortress") == 100.0
    assert pct_sum("weekly") == 100.0
    assert pct_sum("longterm") == 100.0


def test_apply_sleeve_env_zeros_theme_knobs(monkeypatch):
    monkeypatch.setenv("MATH_FIRST_WEIGHTS", "true")
    monkeypatch.setenv("RANK_W_WATER_DATACENTER", "0.12")
    monkeypatch.setenv("PRED_FORCE_SCORE_BOOST", "0.24")
    apply_sleeve_env("fortress", force=True)
    import os

    assert float(os.getenv("RANK_W_WATER_DATACENTER", "1") or 1) == 0.0
    assert float(os.getenv("PRED_FORCE_SCORE_BOOST", "1") or 1) == 0.0


def test_future_headline_dropped():
    as_of = date(2024, 6, 1)
    items = [
        {"headline": "old", "datetime": datetime(2024, 5, 31, 12, tzinfo=timezone.utc).timestamp()},
        {"headline": "future", "datetime": datetime(2024, 6, 3, 12, tzinfo=timezone.utc).timestamp()},
        {"headline": "undated"},
    ]
    kept = filter_items_as_of(items, as_of)
    assert len(kept) == 1
    assert kept[0]["headline"] == "old"
    assert item_not_after(items[0], as_of)
    assert not item_not_after(items[1], as_of)
    start, end = news_window(as_of, lookback_days=7)
    assert end == as_of
    assert start < end


def test_last_wins_no_theme_full_cash():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "data" / "deploy_scale.env").read_text()
    last = text.rsplit("last-wins 2026-09-07 night", 1)[-1]
    assert "FORTRESS_WATER_THEME=false" in last
    assert "FORTRESS_FORCE_BUY_SYMBOLS=" in last
    assert "FORTRESS_MAX_POSITIONS=500" in last
    assert "MAX_GROSS_LEVERAGE=1.0" in last
    assert "FORTRESS_ALLOW_ADD_ON=true" in last
    assert "ALPACA_OPTIONS_ENABLED=false" in last


def test_live_as_of_keeps_all():
    items = [{"headline": "x"}, {"headline": "y", "datetime": 1_700_000_000}]
    assert filter_items_as_of(items, None) == items
