"""Buy low / sell high limit pricing."""

import os

from analytics.limit_pricing import entry_limit_px, exit_limit_px, quote_is_sane


def test_buy_below_mid():
    os.environ["ALPACA_AGGRESSIVE_ENTRY"] = "false"
    bid, ask = 100.00, 100.10
    lp = entry_limit_px("buy", bid, ask)
    assert lp is not None
    mid = (bid + ask) / 2
    assert lp <= mid


def test_sell_above_entry():
    os.environ["ALPACA_AGGRESSIVE_EXIT"] = "false"
    bid, ask = 100.05, 100.15
    entry = 100.00
    lp = exit_limit_px("sell", bid, ask, entry, forced_loss=False)
    assert lp is not None
    assert lp >= entry * 1.0003
    assert lp <= ask


def test_underwater_sell_rests_at_or_above_entry():
    os.environ["ALPACA_AGGRESSIVE_EXIT"] = "false"
    os.environ["ALPACA_MIN_EXIT_PROFIT_BPS"] = "3"
    bid, ask = 335.94, 335.99
    entry = 339.46
    lp = exit_limit_px("sell", bid, ask, entry, forced_loss=False)
    assert lp is not None
    assert lp >= entry
    # May sit above the ask until green — that is wait-for-green, not a dump.


def test_wide_quote_rejects_entry():
    os.environ["ALPACA_MAX_ENTRY_SPREAD_PCT"] = "0.015"
    assert entry_limit_px("buy", 101.0, 172.0) is None
    assert not quote_is_sane(101.0, 172.0)


def test_wide_quote_exit_anchors_mid_not_bid():
    os.environ["ALPACA_EXIT_MAX_SPREAD_PCT"] = "0.015"
    os.environ["ALPACA_AGGRESSIVE_EXIT"] = "true"
    # AGL-style fantasy NBBO — must not dump near 101
    lp = exit_limit_px("sell", 101.33, 172.01, 151.87, forced_loss=True)
    assert lp is not None
    mid = (101.33 + 172.01) / 2.0
    assert lp >= mid * 0.95
    assert lp > 120.0
    assert lp <= 172.01


def test_wmt_earnings_dump_forced_exit_is_fillable():
    """2026-08-20 WMT: thesis_death posted 112.63 with ask 109.71 — never filled."""
    os.environ["ALPACA_EXIT_MAX_SPREAD_PCT"] = "0.015"
    os.environ["ALPACA_MAX_FORCE_EXIT_SLIP_PCT"] = "0.02"
    bid, ask, entry = 98.97, 109.71, 114.93
    lp = exit_limit_px("sell", bid, ask, entry, forced_loss=True)
    assert lp is not None
    mid = (bid + ask) / 2.0
    assert lp <= ask
    assert lp >= mid * 0.95
    assert lp < entry * 0.98  # must not rest at the unfillable entry-2% floor
    # Non-forced still waits for green (do not dump winners' wait-for-green path).
    wait = exit_limit_px("sell", bid, ask, entry, forced_loss=False)
    assert wait is not None
    assert wait >= entry


def test_aggressive_buy_capped_near_mid():
    os.environ["ALPACA_AGGRESSIVE_ENTRY"] = "true"
    os.environ["ALPACA_MAX_ENTRY_SPREAD_PCT"] = "0.02"
    os.environ["ALPACA_MAX_ENTRY_CROSS_PCT"] = "0.004"
    bid, ask = 100.00, 100.50  # 0.5% spread — allowed
    lp = entry_limit_px("buy", bid, ask)
    assert lp is not None
    mid = (bid + ask) / 2
    assert lp <= mid * 1.01
