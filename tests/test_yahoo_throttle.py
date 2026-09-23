"""Yahoo rate-limit throttle + paper-sim price source smoke tests."""

from __future__ import annotations

import time
from unittest.mock import patch

import pandas as pd
import pytest


def test_yahoo_throttle_cooldown_blocks_fetch():
    from data_platform import yahoo_throttle as yt

    yt._cooldown_until = 0.0
    yt._last_call = 0.0
    yt.note_rate_limit()
    assert yt.is_rate_limited()
    assert not yt.wait_turn(block=False)


def test_yahoo_throttle_serializes_calls():
    from data_platform import yahoo_throttle as yt

    yt._cooldown_until = 0.0
    yt._last_call = 0.0
    with patch.dict("os.environ", {"YAHOO_MIN_INTERVAL_SEC": "0.05"}):
        t0 = time.perf_counter()
        assert yt.wait_turn()
        assert yt.wait_turn()
        assert time.perf_counter() - t0 >= 0.04


def test_use_price_cache_reads_even_when_network_first():
    from data_platform.network_data import save_price_cache, use_price_cache

    with patch.dict(
        "os.environ",
        {
            "NETWORK_FIRST": "true",
            "USE_PRICE_CACHE": "true",
            "NETWORK_FIRST_ALLOW_PRICE_WRITES": "false",
            "PAPER_SIM_SAVE_PRICE_CACHE": "true",
        },
    ):
        assert use_price_cache()
        assert save_price_cache()


def test_price_source_prefers_polygon_during_paper_sim(monkeypatch):
    from feature_engineering import _price_source

    monkeypatch.setenv("PAPER_SIM_ACTIVE_RUN", "true")
    monkeypatch.setenv("PAPER_SIM_USE_POLYGON", "true")
    monkeypatch.setenv("PAPER_SIM_FORCE_YAHOO", "false")
    monkeypatch.setenv("FORCE_YAHOO_PRICES", "false")
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    monkeypatch.setenv("ALPACA_API_KEY", "also-set")
    monkeypatch.setenv("PRICE_DATA_SOURCE", "yfinance")

    with patch("alpaca_broker.alpaca_bars_feed_active", return_value=True):
        assert _price_source() == "hybrid_polygon"


def test_price_source_prefers_alpaca_during_paper_sim(monkeypatch):
    from feature_engineering import _price_source

    monkeypatch.setenv("PAPER_SIM_ACTIVE_RUN", "true")
    monkeypatch.setenv("PAPER_SIM_USE_POLYGON", "false")
    monkeypatch.setenv("PAPER_SIM_USE_ALPACA", "true")
    monkeypatch.setenv("PAPER_SIM_FORCE_YAHOO", "false")
    monkeypatch.setenv("FORCE_YAHOO_PRICES", "false")
    monkeypatch.setenv("ALPACA_API_KEY", "test-key")
    monkeypatch.setenv("PRICE_DATA_SOURCE", "yfinance")

    with patch("alpaca_broker.alpaca_bars_feed_active", return_value=True):
        assert _price_source() == "hybrid_alpaca"


def test_load_yfinance_uses_stale_cache_when_yahoo_cooldown(monkeypatch):
    from feature_engineering import _load_yfinance

    idx = pd.date_range("2026-05-01", periods=10, freq="B")
    cached = pd.DataFrame(
        {"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 100.0},
        index=idx,
    )

    monkeypatch.setenv("USE_PRICE_CACHE", "true")
    monkeypatch.setenv("PRICE_CACHE_STALE_OK_DAYS", "5")
    monkeypatch.setenv("YAHOO_SKIP_WHEN_LIMITED", "true")

    with patch("feature_engineering.load_cached_ohlcv", return_value=cached):
        with patch("data_platform.yahoo_throttle.wait_turn", return_value=False):
            out = _load_yfinance("AAPL", "AAPL", "2026-05-01", "2026-06-07", use_cache=True)

    assert not out.empty
    assert out.index.min() >= pd.Timestamp("2026-05-01")


def test_paper_sim_skips_yahoo_fallback(monkeypatch):
    from feature_engineering import _skip_yahoo_fallback

    monkeypatch.setenv("PAPER_SIM_ACTIVE_RUN", "true")
    monkeypatch.setenv("PAPER_SIM_FORCE_YAHOO", "false")
    monkeypatch.setenv("FORCE_YAHOO_PRICES", "false")
    monkeypatch.setenv("PAPER_SIM_SKIP_YAHOO_FALLBACK", "true")
    # Deploy knobs currently run Yahoo-first with fallback on; pin the polygon-first
    # policy this test is about (the code path, not the operator's live setting).
    monkeypatch.setenv("SKIP_YAHOO_FALLBACK", "true")
    monkeypatch.setenv("USE_YAHOO_FIRST", "false")
    monkeypatch.setenv("USE_POLYGON_FIRST", "true")
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    monkeypatch.setenv("PRICE_DATA_SOURCE", "hybrid_polygon")
    assert _skip_yahoo_fallback() is True
