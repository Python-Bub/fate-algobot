"""Sell tickets must be fillable; stale sleeve maps must not zero real exits."""

from __future__ import annotations

import json
from pathlib import Path

from analytics.limit_pricing import (
    buy_limit_unfillable,
    sell_limit_at_touch,
    sell_limit_unfillable,
    working_sell_needs_reprice,
)


def test_tsla_style_sell_above_ask_is_unfillable():
    assert sell_limit_unfillable(339.46, 335.94, 335.99) is True
    assert sell_limit_at_touch(339.46, 335.94, 335.99) is False
    # Unknown cost: still reprice an unfillable ticket.
    assert working_sell_needs_reprice(339.46, 335.94, 335.99, 90.0) is True
    # A few cents under cost is noise. Do not cross.
    assert working_sell_needs_reprice(336.99, 336.60, 336.64, 47.0, entry_px=336.94) is False
    # A full percent under cost, with the sell sitting above the ask, never fills.
    assert working_sell_needs_reprice(100.30, 98.90, 99.00, 60.0, entry_px=100.0) is True


def test_dump_below_cost_reprices_up_immediately():
    assert working_sell_needs_reprice(336.63, 336.60, 336.64, 5.0, entry_px=336.94) is True


def test_fillable_ask_touch_is_left_alone():
    assert sell_limit_unfillable(365.99, 365.61, 366.00) is False
    assert sell_limit_at_touch(365.99, 365.61, 366.00) is True
    assert working_sell_needs_reprice(365.99, 365.61, 366.00, 4000.0) is False


def test_stale_inside_wide_spread_reprices():
    # AVGO-style: limit near mid of a wide book, sitting for hours.
    assert working_sell_needs_reprice(382.99, 378.94, 385.00, 4.3 * 3600) is True


def test_same_price_does_not_reprice_loop():
    from analytics.limit_pricing import exit_limit_px, sell_already_priced

    bid, ask = 103.43, 112.89
    lp = exit_limit_px("sell", bid, ask, 107.14, forced_loss=False)
    assert lp is not None
    assert sell_already_priced(lp, bid, ask, 107.14) is True


def test_aapl_buy_far_below_bid_is_unfillable():
    assert buy_limit_unfillable(305.64, 310.18, 310.21) is True


def test_cancel_stale_sells_no_longer_skips_full_closes():
    text = Path("alpaca_broker.py").read_text(encoding="utf-8")
    assert "oq >= pos_qty * 0.5" not in text.split("def cancel_stale_sell_orders")[1].split("def ")[0]
    assert "working_sell_needs_reprice" in text
    assert "reprice_working_sells" in text
    assert "cancel_stale_unfillable_buys" in text
    close_fn = text.split("def close_position_alpaca")[1].split("\ndef ")[0]
    assert "or (not _ext_close and underwater)" not in close_fn
    assert "skip market DELETE close" in close_fn


def test_sellable_stale_qty_map_does_not_zero_primary(tmp_path, monkeypatch):
    p = tmp_path / "reg.json"
    p.write_text(
        json.dumps(
            {
                "heads": {"AMZN": "day_trade", "COST": "fortress"},
                "qty_by_sleeve": {"AMZN": {"fortress": 26.0}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PORTFOLIO_HEAD_REGISTRY", str(p))
    import analytics.portfolio_slots as ps

    monkeypatch.setattr(ps, "REGISTRY_FILE", p)
    assert ps.sellable_qty_for_head("AMZN", "day_trade", broker_qty=9.55) == 9.55
    assert (
        ps.sellable_qty_for_head(
            "COST", "micro_scalp", broker_qty=2.5882, confirmed_fill_qty=2.5882
        )
        == 2.5882
    )
    assert ps.sellable_qty_for_head("COST", "micro_scalp", broker_qty=2.5882) == 0.0
