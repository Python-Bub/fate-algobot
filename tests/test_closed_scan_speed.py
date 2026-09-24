"""Closed-session scans must keep equities and score from a bar cache, not a 90s tick."""

from __future__ import annotations

import os

import pandas as pd


def test_closed_session_keeps_long_pass_and_short_ticks():
    import fortress_live as fl

    keys = [
        "FORTRESS_PASS_MAX_SEC",
        "FORTRESS_CRYPTO_PASS_MAX_SEC",
        "FORTRESS_FEATURE_LOOKBACK_DAYS",
        "FORTRESS_CLOSED_LOOKBACK_DAYS",
        "FORTRESS_TICK_TIMEOUT_SEC",
        "FORTRESS_CLOSED_TICK_TIMEOUT_SEC",
        "FORTRESS_CRYPTO_TICK_TIMEOUT_SEC",
        "FORTRESS_INTEL_TIMEOUT_SEC",
        "FORTRESS_LITE_INTEL",
        "FORTRESS_CRYPTO_SESSION_ONLY",
        "FORTRESS_LITE_SKIP_NEWS",
        "USE_TICKER_HISTORY_STITCH",
        "USE_TRAIN_SIGNAL_FEATURES",
        "USE_HIDDEN_PATTERN_FEATURES",
        "USE_VALUE_INVESTING",
        "USE_BOTTOM_FISHER",
        "USE_INVESTING_BOOK",
        "USE_HIDDEN_PATTERN_ANOMALY",
        "USE_CROSS_COMPANY_LINKS",
    ]
    saved = {k: os.environ.get(k) for k in keys}
    try:
        os.environ["FORTRESS_PASS_MAX_SEC"] = "1800"
        os.environ.pop("FORTRESS_CRYPTO_PASS_MAX_SEC", None)
        os.environ["FORTRESS_FEATURE_LOOKBACK_DAYS"] = "400"
        os.environ.pop("FORTRESS_CLOSED_LOOKBACK_DAYS", None)
        os.environ["FORTRESS_TICK_TIMEOUT_SEC"] = "90"
        os.environ.pop("FORTRESS_CLOSED_TICK_TIMEOUT_SEC", None)
        fl._apply_closed_session_scan_env()
        assert os.environ["FORTRESS_PASS_MAX_SEC"] == "1800"
        assert os.environ["FORTRESS_FEATURE_LOOKBACK_DAYS"] == "120"
        assert os.environ["FORTRESS_TICK_TIMEOUT_SEC"] == "18"
        assert os.environ["FORTRESS_CRYPTO_TICK_TIMEOUT_SEC"] == "18"
        assert os.environ["FORTRESS_LITE_INTEL"] == "true"
        assert os.environ["USE_TICKER_HISTORY_STITCH"] == "false"
        assert os.environ["USE_VALUE_INVESTING"] == "false"
        assert os.environ["USE_BOTTOM_FISHER"] == "false"
        assert fl._lite_skip_news()
        assert fl._queue_buy_this_session(True)
        assert not fl._queue_buy_this_session(False)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_lite_flat_news_does_not_block_buy():
    import fortress_live as fl

    saved = {k: os.environ.get(k) for k in ("FORTRESS_LITE_INTEL", "FORTRESS_ACCURACY_MODE")}
    try:
        os.environ["FORTRESS_LITE_INTEL"] = "true"
        assert fl._news_supports_buy(0.0, 0.0)
        assert not fl._news_supports_buy(-0.2, 0.0)
        os.environ["FORTRESS_LITE_INTEL"] = "false"
        os.environ["FORTRESS_ACCURACY_MODE"] = "true"
        assert not fl._news_supports_buy(0.0, 0.0)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_pass_bar_cache_skips_network(monkeypatch):
    import feature_engineering as fe

    fe.clear_pass_bars()
    idx = pd.bdate_range("2025-01-01", periods=80)
    df = pd.DataFrame(
        {
            "Open": 1.0,
            "High": 1.1,
            "Low": 0.9,
            "Close": 1.0,
            "Adj Close": 1.0,
            "Volume": 100.0,
        },
        index=idx,
    )
    fe.remember_pass_bars("ZZCACHE", df)

    def boom(*_a, **_k):
        raise AssertionError("network")

    monkeypatch.setattr(fe, "_load_alpaca", boom)
    monkeypatch.setattr(fe, "_load_yfinance", boom)
    monkeypatch.setattr(fe, "_load_polygon", boom)
    monkeypatch.setattr(fe, "_load_ibkr", boom)
    monkeypatch.setenv("USE_TICKER_HISTORY_STITCH", "false")
    out = fe.load_price_data("ZZCACHE", "2025-01-01", "2026-01-01")
    assert len(out) >= 60
    fe.clear_pass_bars()


def test_multi_bar_payload_maps_logical_tickers():
    import feature_engineering as fe

    payload = {
        "bars": {
            "AAPL": [
                {"t": "2026-09-01T00:00:00Z", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 10}
            ],
            "BTC/USD": [
                {"t": "2026-09-01T00:00:00Z", "o": 10, "h": 12, "l": 9, "c": 11, "v": 3}
            ],
        }
    }
    frames = fe.frames_from_alpaca_multi(
        payload,
        {"AAPL": ["AAPL"], "BTC/USD": ["BTC-USD"]},
    )
    assert float(frames["AAPL"]["Close"].iloc[-1]) == 1.5
    assert float(frames["BTC-USD"]["Adj Close"].iloc[-1]) == 11.0
    assert frames["AAPL"].index.tz is None


def test_prefetch_stores_equity_and_crypto(monkeypatch):
    import feature_engineering as fe

    fe.clear_pass_bars()
    idx = pd.bdate_range("2025-06-01", periods=30)
    frame = pd.DataFrame(
        {
            "Open": 1.0,
            "High": 1.0,
            "Low": 1.0,
            "Close": 2.0,
            "Adj Close": 2.0,
            "Volume": 1.0,
        },
        index=idx,
    )

    def fake(url, api_symbols, key_map, start_iso, end_iso, *, timeout):
        out = {}
        for api in api_symbols:
            for logical in key_map[api]:
                out[logical] = frame.copy()
        return out

    monkeypatch.setattr(fe, "_fetch_alpaca_multi_bars", fake)
    n = fe.prefetch_scan_bars(["AAPL", "BTC-USD"], lookback_days=120)
    assert n >= 2
    assert "AAPL" in fe._PASS_BAR_CACHE
    assert "BTC-USD" in fe._PASS_BAR_CACHE
    assert "SPY" in fe._PASS_BAR_CACHE
    fe.clear_pass_bars()
