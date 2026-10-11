import os
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from analytics.market_session import Session, current_session, orders_allowed

ET = ZoneInfo("America/New_York")


class TestMarketSession(unittest.TestCase):
    def test_friday_post_market(self):
        dt = datetime(2026, 6, 5, 19, 0, tzinfo=ET)
        self.assertEqual(current_session(dt), Session.POST_MARKET)

    def test_rth_only_blocks_post_market_buys(self):
        os.environ["TRADE_SESSION_MODE"] = "rth"
        os.environ["TRADE_EXIT_SESSION_MODE"] = "rth"
        dt = datetime(2026, 6, 5, 19, 0, tzinfo=ET)
        self.assertEqual(current_session(dt), Session.POST_MARKET)
        # orders_allowed uses now(); patch via time travel is heavy — check mode logic inline
        from analytics import market_session as ms

        self.assertFalse(ms._session_in_mode(Session.POST_MARKET, "rth"))
        self.assertTrue(ms._session_in_mode(Session.REGULAR, "rth"))

    def test_rth_buy_window(self):
        os.environ["TRADE_SESSION_MODE"] = "rth"
        os.environ["TRADE_START_ET"] = "12:30"
        os.environ["FORTRESS_TRADE_START_ET"] = "12:30"
        os.environ["TRADE_END_ET"] = "16:00"
        os.environ["TRADE_WEEKDAY_24X5"] = "true"
        dt = datetime(2026, 6, 8, 10, 0, tzinfo=ET)  # Monday 10:00 ET
        from analytics import market_session as ms

        window_ok, _ = ms._within_trade_window(dt)
        self.assertFalse(window_ok)
        self.assertTrue(ms._session_in_mode(ms.Session.REGULAR, "rth"))

    def test_weekend_closed(self):
        dt = datetime(2026, 6, 6, 12, 0, tzinfo=ET)
        self.assertEqual(current_session(dt), Session.CLOSED)


def test_midday_blocks_fortress_buys_hft_exempt(monkeypatch):
    from analytics import market_session as ms

    dt = datetime(2026, 8, 14, 14, 0, tzinfo=ET)  # Friday 2pm ET — midday chop
    monkeypatch.setenv("MIDDAY_HFT_ONLY", "true")
    monkeypatch.setenv("FORTRESS_INVERT_P_UP", "false")
    monkeypatch.setenv("FORTRESS_FADE_DURING_MIDDAY", "false")
    monkeypatch.setenv("TRADE_SESSION_MODE", "extended")
    monkeypatch.setenv("TRADE_WEEKDAY_24X5", "true")
    monkeypatch.setenv("ALPACA_CLOCK_GATE", "false")
    monkeypatch.setenv("MORNING_SWEET_SPOT", "false")
    monkeypatch.setattr(ms, "now_et", lambda: dt)
    monkeypatch.setattr(ms, "exchange_is_open", lambda **_k: (True, "clock_gate_off"))
    ok, why = ms.orders_allowed("buy", for_hft=False)
    assert ok is False
    assert "midday_hft_only" in why
    ok_hft, _ = ms.orders_allowed("buy", for_hft=True)
    assert ok_hft is True


def test_midday_allows_fortress_fade_buys(monkeypatch):
    from analytics import market_session as ms

    dt = datetime(2026, 8, 14, 14, 0, tzinfo=ET)
    monkeypatch.setenv("MIDDAY_HFT_ONLY", "true")
    monkeypatch.setenv("FORTRESS_INVERT_P_UP", "auto")
    monkeypatch.setenv("FORTRESS_FADE_DURING_MIDDAY", "true")
    monkeypatch.setenv("TRADE_SESSION_MODE", "extended")
    monkeypatch.setenv("TRADE_WEEKDAY_24X5", "true")
    monkeypatch.setenv("ALPACA_CLOCK_GATE", "false")
    monkeypatch.setenv("MORNING_SWEET_SPOT", "false")
    monkeypatch.setattr(ms, "now_et", lambda: dt)
    monkeypatch.setattr(ms, "exchange_is_open", lambda **_k: (True, "clock_gate_off"))
    ok, why = ms.orders_allowed("buy", for_hft=False)
    assert ok is True
    assert "fade_midday" in why or "buy_mode" in why


def test_overnight_cash_does_not_bypass_midday_hft_only(monkeypatch):
    from analytics import market_session as ms

    dt = datetime(2026, 8, 14, 14, 0, tzinfo=ET)
    monkeypatch.setenv("MIDDAY_HFT_ONLY", "true")
    monkeypatch.setenv("FORTRESS_INVERT_P_UP", "false")
    monkeypatch.setenv("FORTRESS_FADE_DURING_MIDDAY", "false")
    monkeypatch.setenv("FORTRESS_OVERNIGHT_CASH_DEPLOY", "true")
    monkeypatch.setenv("TRADE_SESSION_MODE", "extended")
    monkeypatch.setenv("TRADE_WEEKDAY_24X5", "true")
    monkeypatch.setenv("ALPACA_CLOCK_GATE", "false")
    monkeypatch.setenv("MORNING_SWEET_SPOT", "false")
    monkeypatch.setattr(ms, "now_et", lambda: dt)
    monkeypatch.setattr(ms, "exchange_is_open", lambda **_k: (True, "clock_gate_off"))
    ok, why = ms.orders_allowed("buy", for_hft=False)
    assert ok is False
    assert "midday_hft_only" in why


def test_overnight_cash_deploy_allows_closed_session_stock_buys(monkeypatch):
    from analytics import market_session as ms

    dt = datetime(2026, 8, 25, 1, 8, tzinfo=ET)  # Tue 1:08 ET — NYSE closed
    monkeypatch.setenv("FORTRESS_OVERNIGHT_CASH_DEPLOY", "true")
    monkeypatch.setenv("TRADE_SESSION_MODE", "extended")
    monkeypatch.setenv("TRADE_WEEKDAY_24X5", "true")
    monkeypatch.setenv("TRADE_START_ET", "06:00")
    monkeypatch.setenv("FORTRESS_TRADE_START_ET", "06:00")
    monkeypatch.setenv("TRADE_END_ET", "20:00")
    monkeypatch.setenv("ALPACA_CLOCK_GATE", "false")
    monkeypatch.setenv("MORNING_SWEET_SPOT", "false")
    monkeypatch.setenv("MIDDAY_HFT_ONLY", "false")
    monkeypatch.setattr(ms, "now_et", lambda: dt)
    monkeypatch.setattr(ms, "current_session", lambda _dt=None: ms.Session.CLOSED)
    monkeypatch.setattr(ms, "exchange_is_open", lambda **_k: (False, "closed"))
    ok, why = ms.orders_allowed("buy", for_hft=False, symbol="AAPL")
    assert ok is True
    assert why == "overnight_cash_deploy"
    ok_hft, why_hft = ms.orders_allowed("buy", for_hft=True, symbol="AAPL")
    assert ok_hft is False
    assert "session=closed" in why_hft or "buy_mode" in why_hft or "closed" in why_hft


if __name__ == "__main__":
    unittest.main()
