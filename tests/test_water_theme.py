"""Datacenter-cooling water is a scored overlay, not a FORCE slogan."""

from analytics.sleeve_weights import FORTRESS_PCT, HFT_PCT, LONGTERM_PCT, pct_sum
from analytics.water_theme import (
    industry_overrides,
    is_water_symbol,
    space_rank_boost,
    water_rank_boost,
    water_scan_symbols,
)


def test_water_scan_has_utilities_and_tech(monkeypatch):
    monkeypatch.setenv("FORTRESS_WATER_INCLUDE_ETFS", "false")
    names = water_scan_symbols()
    assert "AWK" in names and "XYL" in names and "TTEK" in names
    assert "PHO" not in names
    assert is_water_symbol("awk")
    ov = industry_overrides()
    assert ov["AWK"] == "electric_gas_utilities"
    assert ov["XYL"] == "construction_machinery"
    assert ov["ECL"] == "chemicals"


def test_water_etfs_opt_in(monkeypatch):
    monkeypatch.setenv("FORTRESS_WATER_INCLUDE_ETFS", "true")
    names = water_scan_symbols()
    assert "PHO" in names and "FIW" in names


def test_classifier_loads_water_overrides():
    import analytics.industries.classifier as c

    c._MEM_OVERRIDES = None
    ov = c.load_overrides()
    assert ov["AWK"] == "electric_gas_utilities"
    assert ov["XYL"] == "construction_machinery"
    assert ov["ECL"] == "chemicals"
    row = c.classify_ticker("AWK", use_yfinance=False)
    assert row["industry_id"] == "electric_gas_utilities"


def test_chips_are_demand_not_water():
    b, meta = water_rank_boost("NVDA", p_up=0.70, sleeve="fortress")
    assert b == 0.0
    assert meta["reason"] == "demand_side_not_water"


def test_model_down_kills_theme():
    b, meta = water_rank_boost("AWK", p_up=0.40, sleeve="fortress")
    assert b == 0.0
    assert meta["reason"] == "model_down"


def test_tech_beats_utility_when_model_agrees():
    awk, _ = water_rank_boost("AWK", p_up=0.62, sleeve="fortress")
    xyl, _ = water_rank_boost("XYL", p_up=0.62, sleeve="fortress")
    assert awk > 0 and xyl > awk


def test_hft_gets_zero_water():
    b, _ = water_rank_boost("XYL", p_up=0.70, sleeve="hft")
    assert b == 0.0
    assert HFT_PCT.get("water_datacenter", 0.0) == 0.0


def test_space_is_longterm_only():
    f, _ = space_rank_boost("RKLB", p_up=0.62, sleeve="fortress")
    lt, _ = space_rank_boost("RKLB", p_up=0.62, sleeve="longterm")
    tsla, _ = space_rank_boost("TSLA", p_up=0.70, sleeve="longterm")
    assert f == 0.0
    assert lt > 0
    assert tsla == 0.0


def test_water_table_mass():
    assert FORTRESS_PCT["water_datacenter"] == 2.0
    assert FORTRESS_PCT["pred_force"] == 2.0
    assert LONGTERM_PCT["space_infra"] == 1.0
    assert pct_sum("fortress") == 100.0
    assert pct_sum("weekly") == 100.0
    assert pct_sum("longterm") == 100.0
    assert pct_sum("hft") == 100.0
