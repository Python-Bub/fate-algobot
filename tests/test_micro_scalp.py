"""Unit tests for micro-scalp / noise-harvest target math + spread guards."""

import os

from analytics.micro_scalp import (
    build_scalp_plan,
    can_attempt,
    compute_entry_limit,
    load_caps,
    min_edge_abs,
    quote_allows_entry,
    spread_reject_reason,
    target_exit_px,
    tick_size,
)


def test_tick_size_penny_and_dollar():
    assert tick_size(50.0) == 0.01
    assert tick_size(0.50) == 0.001
    assert tick_size(0.05) == 0.0001


def test_sub_tick_fantasy_floored_to_one_tick():
    """$0.00000000001 is below tick — must use ≥1 tick edge."""
    os.environ["MICRO_SCALP_TARGET_ABS"] = "0.00000000001"
    os.environ["MICRO_SCALP_TARGET_BPS"] = "0"
    os.environ["MICRO_SCALP_MIN_TICKS"] = "1"
    edge = min_edge_abs(100.0)
    assert edge >= 0.01
    tgt = target_exit_px(100.0)
    assert tgt >= 100.01


def test_target_uses_bps_when_larger_than_tick():
    os.environ["MICRO_SCALP_TARGET_ABS"] = "0"
    os.environ["MICRO_SCALP_TARGET_BPS"] = "5"  # 5 bps of $100 = $0.05
    os.environ["MICRO_SCALP_MIN_TICKS"] = "1"
    edge = min_edge_abs(100.0)
    assert abs(edge - 0.05) < 1e-9
    plan = build_scalp_plan(100.0)
    assert plan is not None
    assert plan.target_px == 100.05
    assert plan.edge_bps >= 4.9


def test_reject_wide_spread_agl_style():
    os.environ["MICRO_SCALP_MAX_SPREAD_PCT"] = "0.015"
    os.environ["ALPACA_MAX_ENTRY_SPREAD_PCT"] = "0.015"
    assert not quote_allows_entry(101.0, 172.0)
    assert spread_reject_reason(101.0, 172.0) == "wide_spread"
    assert compute_entry_limit(101.0, 172.0) is None


def test_sane_spread_allows_entry():
    os.environ["MICRO_SCALP_MAX_SPREAD_PCT"] = "0.015"
    os.environ["ALPACA_AGGRESSIVE_ENTRY"] = "true"
    os.environ["MICRO_SCALP_AGGRESSIVE_ENTRY"] = "true"
    os.environ["ALPACA_MAX_ENTRY_SPREAD_PCT"] = "0.02"
    os.environ["ALPACA_MAX_ENTRY_CROSS_PCT"] = "0.004"
    bid, ask = 100.00, 100.04  # ~4 bps
    assert quote_allows_entry(bid, ask)
    lp = compute_entry_limit(bid, ask)
    assert lp is not None
    mid = (bid + ask) / 2
    assert lp <= mid * 1.01


def test_caps_block_max_open_and_pdt():
    caps = load_caps()
    ok, reason = can_attempt(
        open_scalps=caps.max_open,
        open_notional=0,
        trades_today=0,
        equity=10_000,
        daytrade_count=0,
        caps=caps,
    )
    assert not ok and reason == "max_open"

    os.environ["MICRO_SCALP_PDT_AWARE"] = "true"
    os.environ["MICRO_SCALP_PDT_MAX_DAY_TRADES"] = "3"
    os.environ["MICRO_SCALP_PDT_MIN_EQUITY"] = "25000"
    caps2 = load_caps()
    ok2, reason2 = can_attempt(
        open_scalps=0,
        open_notional=0,
        trades_today=0,
        equity=10_000,
        daytrade_count=3,
        caps=caps2,
    )
    assert not ok2 and reason2 == "pdt_day_trade_cap"


def test_order_filled_qty_never_invents_requested_size():
    from tools.micro_scalp_daemon import order_filled_qty, scalp_sell_qty

    assert order_filled_qty({"status": "filled", "qty": "6.56", "filled_qty": "0"}) == 0.0
    assert order_filled_qty({"status": "canceled", "qty": "6.56", "filled_qty": "0"}) == 0.0
    assert order_filled_qty({"status": "filled", "filled_qty": "2.5"}) == 2.5
    assert order_filled_qty(None) == 0.0
    # Fortress 5 shares live must not become the scalp exit.
    assert scalp_sell_qty(filled_qty=0.0, live_qty=5.0, sellable=5.0) == 0.0
    assert scalp_sell_qty(filled_qty=6.56, live_qty=5.0, sellable=0.0) == 0.0
    assert scalp_sell_qty(filled_qty=1.2, live_qty=6.2, sellable=1.2) == 1.2


def test_hit_stop_ignores_fantasy_wide_bid():
    from analytics.micro_scalp import hit_stop

    os.environ["MICRO_SCALP_MAX_SPREAD_PCT"] = "0.004"
    os.environ["MICRO_SCALP_STOP_BPS"] = "35"
    # TSLA dump: 332 bid vs ~336 ask is not a 35bps stop — it is a garbage print.
    assert not hit_stop("buy", 336.72, 332.31, 336.80)


def test_hit_stop_fires_on_sane_quote_at_planned_stop():
    from analytics.micro_scalp import hit_stop, stop_px

    os.environ["MICRO_SCALP_MAX_SPREAD_PCT"] = "0.015"
    os.environ["MICRO_SCALP_STOP_BPS"] = "35"
    entry = 100.00
    stp = stop_px(entry, side="buy")
    assert hit_stop("buy", entry, stp, stp + 0.02)
    assert not hit_stop("buy", entry, 99.90, 99.92)


def test_micro_scalp_confirms_fill_from_entry_order_not_broker_long():
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "tools" / "micro_scalp_daemon.py"
    text = src.read_text(encoding="utf-8")
    assert "Wait for entry fill via position check" not in text
    assert "order_filled_qty" in text
    assert "sellable_qty_for_head" in text
    assert "cancel_open_orders(sym)" not in text
