"""Day-mover filters + 50/50 crypto idle-cash split."""

from analytics.crypto_alloc import (
    crypto_gap_usd,
    new_cash_split,
    size_crypto_notional,
)
from analytics.day_movers import skip_post_print_chase, today_liquid_gainers


def test_filters_print_gap_and_keeps_session_pop():
    quotes = [
        {
            "symbol": "MRNA",
            "regularMarketPrice": 145.0,
            "regularMarketChangePercent": 129.0,
            "regularMarketVolume": 90_000_000,
        },
        {
            "symbol": "HOOD",
            "regularMarketPrice": 108.0,
            "regularMarketChangePercent": 13.7,
            "regularMarketVolume": 20_000_000,
        },
        {
            "symbol": "SLS",
            "regularMarketPrice": 2.1,
            "regularMarketChangePercent": 15.0,
            "regularMarketVolume": 5_000_000,
        },
    ]
    assert today_liquid_gainers(fetch=lambda: quotes, limit=10) == ["HOOD"]


def test_skip_chase_needs_live_binary(monkeypatch):
    monkeypatch.setattr(
        "analytics.event_calendar.ticker_row",
        lambda t: {"live_binary": 0.63, "pre": 0.7},
    )
    skip, why = skip_post_print_chase("MRNA", ret_1d=0.50, mom_5d=1.09)
    assert skip is True
    assert "exhaust" in why
    monkeypatch.setattr(
        "analytics.event_calendar.ticker_row",
        lambda t: {"live_binary": 0.0, "pre": 0.0},
    )
    skip2, _ = skip_post_print_chase("AAPL", ret_1d=0.50, mom_5d=0.50)
    assert skip2 is False


def test_new_cash_is_fifty_fifty_until_crypto_target():
    # $71k book, $2.6k crypto, $38k cash → half of cash toward crypto, capped by gap to 50%.
    c, s = new_cash_split(38_000, equity=71_000, crypto_mv=2_600)
    assert abs(c - 19_000) < 1.0
    assert abs(s - 19_000) < 1.0
    # Already at 50%: all idle to stocks.
    c2, s2 = new_cash_split(10_000, equity=71_000, crypto_mv=36_000)
    assert c2 == 0.0
    assert s2 == 10_000
    assert crypto_gap_usd(71_000, 2_600) > 30_000


def test_crypto_clip_uses_idle_half_and_single_cap():
    n = size_crypto_notional(400, equity=71_000, cash=38_000, crypto_mv=2_600)
    # 18% of 71k = 12,780; 50% of cash = 19k; gap ~33k → 12,780
    assert 12_000 < n < 13_000


def test_idle_new_crypto_opens_sol_when_majors_capped(monkeypatch):
    monkeypatch.setenv("FORTRESS_CRYPTO_OVERNIGHT_SCAN", "BTC-USD,ETH-USD,SOL-USD")
    monkeypatch.setenv("FORTRESS_CRYPTO_BOOK_FRAC", "0.50")
    monkeypatch.setenv("FORTRESS_CRYPTO_MAX_SINGLE_FRAC", "0.18")
    from analytics.crypto_alloc import idle_new_crypto_notionals

    extra = idle_new_crypto_notionals(
        12_000.0,
        equity=71_000.0,
        positions=[
            {"symbol": "BTCUSD", "qty": "0.1", "market_value": "12700"},
            {"symbol": "ETHUSD", "qty": "5", "market_value": "12700"},
        ],
        min_n=200.0,
        hard_max=12_800.0,
    )
    # 50% of 71k = 35.5k; majors 25.4k → ~10.1k gap into SOL, not another BTC clip.
    assert extra.get("SOL-USD", 0) > 9_000
    assert "BTC-USD" not in extra
    assert "ETH-USD" not in extra


def test_crypto_single_cap_is_wider_than_equity_10pct(monkeypatch):
    monkeypatch.delenv("FORTRESS_CRYPTO_OVERNIGHT_SCAN", raising=False)
    from analytics.crypto_alloc import crypto_single_cap_usd, overnight_crypto_scan
    from analytics.crypto_math import overlay_equity_p

    cap = crypto_single_cap_usd(71_000)
    assert 12_000 < cap < 13_000
    scan = overnight_crypto_scan()
    assert "BTC-USD" in scan and "SOL-USD" in scan and len(scan) >= 10
    # Equity XGB 0.35 must not keep the coin at a no-buy after overlay.
    assert overlay_equity_p(0.35, 0.62, 0.80) > 0.55
    assert overlay_equity_p(0.70, 0.40, 0.80) < 0.50
