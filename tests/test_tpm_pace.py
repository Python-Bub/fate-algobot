"""Alpaca 200/min soft cap vs HFT target 185 — rolling window, no clock-minute wall."""

from __future__ import annotations

from analytics.alpaca_limits import can_submit_order_pace, trading_orders_per_min_soft
from analytics.trade_math import tpm_capacity


def test_soft_cap_is_200():
    assert trading_orders_per_min_soft() == 200


def test_rolling_pace_allows_185_then_blocks_at_200(monkeypatch):
    monkeypatch.setenv("ALPACA_ORDERS_PER_MIN_SOFT", "200")
    import analytics.alpaca_limits as al

    al._ORDER_TS.clear()
    t0 = 1_700_000_000.0
    for i in range(185):
        hit = can_submit_order_pace(t0 + i * 0.3)
        assert hit.ok, i
    # still under 200
    assert can_submit_order_pace(t0 + 185 * 0.3).ok
    for i in range(14):
        can_submit_order_pace(t0 + (186 + i) * 0.3)
    blocked = can_submit_order_pace(t0 + 200 * 0.3)
    assert blocked.ok is False
    assert blocked.reason == "orders_per_min_soft"


def test_hft_target_sits_under_soft_cap():
    cap = tpm_capacity(n_names=50, cooldown_s=18, cap_per_min=185)
    assert cap["capped_per_min"] <= 200
    assert cap["capped_per_min"] == 185
