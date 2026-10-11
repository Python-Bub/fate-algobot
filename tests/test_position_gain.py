"""Phantom Alpaca cost basis must not look like a winner."""

from analytics.position_gain import dust_close_qty, is_phantom_cost_basis, sane_unrealized_gain
from self_modify.policy_agent import clamp_loss_chasing


def test_negative_entry_is_not_a_gain():
    pos = {"avg_entry_price": -3280.82, "unrealized_plpc": 1.1028, "current_price": 337.33}
    assert sane_unrealized_gain(pos) is None
    assert is_phantom_cost_basis(pos) is True


def test_verified_double_is_a_real_gain():
    # Price and the broker percent agree: this name really doubled.
    pos = {"avg_entry_price": 50.0, "current_price": 100.0, "unrealized_plpc": 1.0}
    g = sane_unrealized_gain(pos)
    assert g is not None and abs(g - 1.0) < 1e-9
    assert is_phantom_cost_basis(pos) is False


def test_tiny_entry_with_a_wild_percent_is_phantom():
    # entry $0.01 and a +176% print do not describe the same position.
    pos = {"avg_entry_price": 0.01, "current_price": 337.0, "unrealized_plpc": 1.76}
    assert sane_unrealized_gain(pos) is None
    assert is_phantom_cost_basis(pos) is True


def test_real_crypto_loss_is_kept():
    pos = {"avg_entry_price": 333.21, "unrealized_plpc": -0.0848, "current_price": 304.95}
    g = sane_unrealized_gain(pos)
    assert g is not None and g < -0.08


def test_modest_plpc_without_entry_still_counts():
    g = sane_unrealized_gain({"unrealized_plpc": 0.005, "qty": 10})
    assert g == 0.005


def test_dust_partial_becomes_full_close():
    # 25% nibble of a $2 lot must sell the whole remainder.
    assert dust_close_qty(0.00879156, 0.00219789, 2.96) == 0.00879156
    # A real $8k position keeps the requested partial.
    assert dust_close_qty(11.33, 2.83, 8104.0) == 2.83


def test_loss_chasing_does_not_lower_the_buy_bar():
    out = clamp_loss_chasing(
        {"BUY_THRESHOLD": 0.52, "ORDER_NOTIONAL": 20000},
        equity_delta=-500,
        cur_buy=0.58,
        cur_notional=2500,
    )
    assert out["BUY_THRESHOLD"] >= 0.58
    assert out["ORDER_NOTIONAL"] == 2500


def test_position_snapshot_ignores_phantom_plpc(monkeypatch):
    import fortress_portfolio as fp

    monkeypatch.setattr(
        "alpaca_broker.get_position",
        lambda _t: {
            "symbol": "AAPL",
            "qty": "0.01",
            "market_value": "3.37",
            "avg_entry_price": "-3280",
            "unrealized_plpc": "1.76",
            "current_price": "337",
        },
    )
    mv, gain = fp.position_snapshot("AAPL")
    assert mv == 3.37
    assert gain is None


def test_overnight_trim_does_not_keep_phantom_winners():
    from analytics.overnight_risk import rank_trim_candidates

    ranked = rank_trim_candidates(
        [
            {
                "symbol": "MSFT",
                "qty": 10,
                "market_value": 6820,
                "avg_entry_price": -600,
                "unrealized_plpc": 1.7,
                "unrealized_pl": 12000,
                "current_price": 420,
            },
            {
                "symbol": "NVDA",
                "qty": 10,
                "market_value": 5000,
                "avg_entry_price": 100,
                "current_price": 101.2,
                "unrealized_plpc": 0.012,
                "unrealized_pl": 60,
            },
        ]
    )
    assert [p["symbol"] for p in ranked][0] == "MSFT"


def test_idle_cash_skips_phantom_winners():
    from fortress_portfolio import allocate_idle_cash_to_holds

    extra = allocate_idle_cash_to_holds(
        10_000.0,
        positions=[
            {
                "symbol": "AAPL",
                "qty": "0.01",
                "market_value": "3",
                "avg_entry_price": "-3280",
                "unrealized_plpc": "1.10",
                "current_price": "337",
            },
            {
                "symbol": "BTCUSD",
                "qty": "0.03",
                "market_value": "2600",
                "avg_entry_price": "80000",
                "unrealized_plpc": "0.04",
                "current_price": "83200",
            },
        ],
        max_single_usd=12_000.0,
        min_n=200.0,
    )
    assert "AAPL" not in extra
    assert "BTCUSD" in extra
