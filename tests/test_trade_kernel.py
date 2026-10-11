"""The decision stack, from a close to a filled stop, with no look-ahead."""

from analytics.trade_kernel import (
    feature_row,
    gain_frac,
    order_notional,
    simulate_book,
    stop_triggered,
    verdict,
    walk_forward_p_up,
)


def _uptrend(n: int, step: float = 0.003) -> list[float]:
    px = 100.0
    out = []
    for _ in range(n):
        out.append(px)
        px *= 1.0 + step
    return out


def _momentum_blocks(n: int = 90, block: int = 12) -> list[float]:
    px = 100.0
    direction = 1.0
    out = []
    for i in range(n):
        out.append(px)
        if i > 0 and i % block == 0:
            direction *= -1.0
        px *= 1.0 + 0.01 * direction
    return out


def test_gain_is_price_over_entry_and_shorts_flip_the_sign():
    assert abs(gain_frac(100, 110) - 0.10) < 1e-12
    assert abs(gain_frac(100, 110, side="SHORT") - (-0.10)) < 1e-12
    assert gain_frac(-5, 110) is None
    assert gain_frac(0, 110) is None


def test_features_ignore_the_future():
    closes = _momentum_blocks()
    t = 40
    base = feature_row(closes, t)
    poisoned = feature_row(closes[: t + 1] + [1e9, 1e-6, 50_000], t)
    assert base == poisoned
    assert base is not None and len(base) == 4


def test_walk_forward_does_not_see_tomorrow():
    closes = _momentum_blocks()
    t = 50
    p_now = walk_forward_p_up(closes, t)
    p_blind = walk_forward_p_up(closes[: t + 1] + [1e9, -1.0], t)
    assert p_now is not None
    assert p_blind == p_now


def test_uptrend_is_a_long_and_the_middle_band_is_flat():
    closes = _uptrend(60)
    p = walk_forward_p_up(closes, 50)
    assert p is not None and p > 0.8
    assert verdict(p) == "LONG"
    assert verdict(0.50) == "FLAT"
    assert verdict(0.40) == "SHORT"


def test_momentum_model_beats_a_coin_flip():
    closes = _momentum_blocks(120, block=12)
    hits = 0
    n = 0
    for t in range(40, len(closes) - 1):
        p = walk_forward_p_up(closes[: t + 1], t)
        assert p is not None
        pred = 1 if p >= 0.5 else 0
        actual = 1 if closes[t + 1] > closes[t] else 0
        hits += int(pred == actual)
        n += 1
    assert n > 30
    assert hits / n > 0.7


def test_a_coin_flip_does_not_clear_the_spread():
    from analytics.trade_kernel import min_p_to_pay, one_bar_ev

    # 55% chance of a 1% up bar, 45% chance of a 1% down bar, 20 bps round trip.
    ev = one_bar_ev(0.55, 0.01, 0.01, 0.002)
    assert ev < 0
    # The live book takes +1.5% and cuts at -2.5%. Sixty percent is still a loss.
    assert one_bar_ev(0.60, 0.015, 0.025, 0.001) < 0
    assert one_bar_ev(0.70, 0.015, 0.025, 0.001) > 0
    assert abs(min_p_to_pay(0.015, 0.025, 0.001) - 0.65) < 1e-12


def test_chop_smaller_than_the_spread_is_not_traded():
    px = 100.0
    closes = []
    for i in range(40):
        closes.append(px)
        px *= 1.002 if i % 2 == 0 else 1 / 1.002
    book = simulate_book(closes, cost_frac=0.005, ticket=5_000, hard_stop=0.04)
    assert book["trades"] == []
    assert book["equity"] == 100_000.0


def test_drift_that_clears_the_spread_makes_money():
    closes = _uptrend(50, step=0.01)
    book = simulate_book(closes, cost_frac=0.001, ticket=5_000, hard_stop=0.5)
    assert any(t["side"] == "LONG" for t in book["trades"])
    assert book["equity"] > 100_000.0


def test_size_respects_the_name_cap_and_buying_power():
    assert order_notional(100_000, 40_000, ticket=20_000) == 10_000
    assert order_notional(100_000, 3_000, ticket=20_000) == 3_000
    assert order_notional(100_000, 0, ticket=500) == 0
    assert order_notional(-1, 1_000, ticket=500) == 0


def test_hard_stop_fires_on_a_real_loss_only():
    assert stop_triggered(100, 95, 0.04) is True
    assert stop_triggered(100, 97, 0.04) is False
    assert stop_triggered(-10, 5, 0.04) is False


def test_book_buys_the_trend_then_stops_out_on_the_crash():
    up = _uptrend(45)
    held = simulate_book(up, ticket=5_000, hard_stop=0.04)
    assert held["shares"] > 0
    entry = held["entry"]
    crash_px = entry * 0.94
    book = simulate_book(up + [crash_px], ticket=5_000, hard_stop=0.04)
    longs = [t for t in book["trades"] if t["side"] == "LONG"]
    stops = [t for t in book["trades"] if t["side"] == "STOP"]
    assert len(longs) == 1
    assert stops and stops[-1]["px"] == crash_px
    assert book["shares"] == 0
    qty = longs[0]["qty"]
    expected = 100_000.0 + (crash_px - longs[0]["px"]) * qty
    assert abs(book["equity"] - expected) < 1e-6
    assert book["equity"] < 100_000.0
    assert qty * longs[0]["px"] <= 10_000.0 + 1e-6


def test_hard_stop_closes_the_live_loser(monkeypatch):
    monkeypatch.setenv("FORTRESS_HARD_STOP_PCT", "0.04")
    monkeypatch.delenv("PAPER_HYGIENE_SKIP_TICKERS", raising=False)
    closed: list[str] = []

    def _positions():
        return [
            {
                "symbol": "BCHUSD",
                "qty": "1",
                "side": "long",
                "avg_entry_price": "500",
                "current_price": "460",
                "unrealized_plpc": "-0.08",
                "market_value": "460",
            }
        ]

    monkeypatch.setattr("alpaca_broker.list_positions", _positions)
    monkeypatch.setattr(
        "alpaca_broker.close_position_alpaca",
        lambda sym, force=False, **_k: closed.append(sym) or True,
    )
    monkeypatch.setattr("alpaca_broker.open_sell_orders", lambda _s: [])
    monkeypatch.setattr("alpaca_broker.pending_close_order", lambda _s: False)
    from fortress_portfolio import enforce_hard_stops

    assert enforce_hard_stops() == 1
    assert closed == ["BCHUSD"]


def test_phantom_dust_closes_and_a_real_lot_stays(monkeypatch):
    monkeypatch.setenv("ALPACA_DUST_FULL_CLOSE_USD", "25")
    monkeypatch.delenv("PAPER_HYGIENE_SKIP_TICKERS", raising=False)
    closed: list[str] = []
    monkeypatch.setattr(
        "alpaca_broker.list_positions",
        lambda: [
            {
                "symbol": "AAPL",
                "qty": "0.01",
                "side": "long",
                "avg_entry_price": "-3280",
                "current_price": "337",
                "unrealized_plpc": "1.76",
                "market_value": "3.37",
            },
            {
                "symbol": "NVDA",
                "qty": "2",
                "side": "long",
                "avg_entry_price": "100",
                "current_price": "104",
                "unrealized_plpc": "0.04",
                "market_value": "208",
            },
        ],
    )
    monkeypatch.setattr(
        "alpaca_broker.close_position_alpaca",
        lambda sym, force=False, **_k: closed.append(sym) or True,
    )
    monkeypatch.setattr("alpaca_broker.open_sell_orders", lambda _s: [])
    monkeypatch.setattr("alpaca_broker.pending_close_order", lambda _s: False)
    from fortress_portfolio import flatten_phantom_dust

    assert flatten_phantom_dust() == 1
    assert closed == ["AAPL"]
