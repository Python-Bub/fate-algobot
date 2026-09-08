"""Rolling 60s order pace + fortress keep-working-buy helper."""

from analytics import alpaca_limits as al
from alpaca_broker import fortress_buy_should_cancel


def test_soft_caps_default_200(monkeypatch):
    monkeypatch.delenv("ALPACA_ORDERS_PER_MIN_SOFT", raising=False)
    monkeypatch.delenv("ALPACA_MAX_OPEN_ORDERS", raising=False)
    assert al.trading_orders_per_min_soft() == 200
    assert al.max_open_orders_soft() == 200


def test_rolling_60s_crosses_calendar_minute(monkeypatch):
    monkeypatch.setenv("ALPACA_ORDERS_PER_MIN_SOFT", "2")
    al._ORDER_TS.clear()
    t0 = 1_000_000.0
    assert al.can_submit_order_pace(now=t0).ok
    assert al.can_submit_order_pace(now=t0 + 1.0).ok
    blocked = al.can_submit_order_pace(now=t0 + 2.0)
    assert not blocked.ok
    assert blocked.reason == "orders_per_min_soft"
    # Clock minute would have reset; rolling window still counts the :59 submit.
    assert not al.can_submit_order_pace(now=t0 + 50.0).ok
    assert al.can_submit_order_pace(now=t0 + 60.1).ok


def test_preflight_buy_does_not_consume_pace_slot(monkeypatch):
    monkeypatch.setenv("ALPACA_ORDERS_PER_MIN_SOFT", "2")
    monkeypatch.setenv("ALPACA_MIN_ORDER_NOTIONAL", "1")
    al._ORDER_TS.clear()
    for _ in range(5):
        hit = al.preflight_buy(symbol="AAPL", notional=200.0, buying_power=10_000.0)
        assert hit.ok
    assert al.can_submit_order_pace(now=2_000_000.0).ok
    assert al.can_submit_order_pace(now=2_000_001.0).ok
    blocked = al.can_submit_order_pace(now=2_000_002.0)
    assert not blocked.ok


def test_fortress_keeps_ranked_working_buys(monkeypatch):
    monkeypatch.setenv("FORTRESS_CANCEL_OFFLIST", "true")
    keep = {"AAPL", "NVDA"}
    assert not fortress_buy_should_cancel(
        {"side": "buy", "symbol": "AAPL", "client_order_id": "ft-1"}, keep
    )
    assert fortress_buy_should_cancel(
        {"side": "buy", "symbol": "MSFT", "client_order_id": "ft-1"}, keep
    )
    assert not fortress_buy_should_cancel(
        {"side": "buy", "symbol": "MSFT", "client_order_id": "obi-abc"}, keep
    )
    assert not fortress_buy_should_cancel({"side": "sell", "symbol": "MSFT"}, keep)


def test_pending_buy_fail_closed_when_book_unreadable(monkeypatch):
    import alpaca_broker as ab

    monkeypatch.setattr(ab, "_ORDERS_CACHE", None)
    monkeypatch.setattr(ab, "_ORDERS_UNREADABLE_UNTIL", 9e12)
    hit = ab.pending_buy_order("NVDA")
    assert hit is not None
    assert hit.get("id") == "_unreadable"


def test_nbbo_from_last_is_tight():
    import alpaca_broker as ab

    bid, ask = ab._nbbo_from_last(100.0)
    assert bid == 99.99
    assert ask == 100.01


def test_quote_yahoo_fallback_when_iex_empty(monkeypatch):
    import pandas as pd
    import alpaca_broker as ab

    monkeypatch.setattr(ab, "_keys", lambda: ("k", "s"))
    monkeypatch.setattr(ab, "price_feed_symbol", lambda s: s)
    monkeypatch.setattr(
        "analytics.alpaca_limits.quote_cache_get",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "analytics.alpaca_limits.acquire_data_token",
        lambda **_k: type("G", (), {"ok": True, "reason": "", "retry_after_sec": 0})(),
    )

    class _R:
        status_code = 200
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {"quote": {}, "trade": {}}

    monkeypatch.setattr(ab.requests, "get", lambda *_a, **_k: _R())
    monkeypatch.setattr(
        ab,
        "_yahoo_last_px",
        lambda _s: 55.25,
    )
    q = ab.get_quote_bid_ask("CSCO")
    assert q is not None
    assert abs(q[0] - 55.24) < 0.011
    assert abs(q[1] - 55.26) < 0.011
