"""Global Polygon-first price routing tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def test_configure_process_prices_polygon_first(monkeypatch):
    from data_platform.market_prices import configure_process_prices

    monkeypatch.delenv("PRICE_DATA_SOURCE", raising=False)
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    monkeypatch.setenv("USE_POLYGON_FIRST", "true")
    monkeypatch.setenv("FORCE_YAHOO_PRICES", "false")
    monkeypatch.setenv("TRAIN_FORCE_YAHOO", "false")
    monkeypatch.setenv("PAPER_SIM_FORCE_YAHOO", "false")
    monkeypatch.setenv("PAPER_SIM_ACTIVE_RUN", "false")
    configure_process_prices(training=True)
    assert __import__("os").getenv("PRICE_DATA_SOURCE") == "hybrid_polygon"
    assert __import__("os").getenv("SKIP_YAHOO_FALLBACK") == "true"


def test_price_source_global_polygon(monkeypatch):
    from feature_engineering import _price_source

    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    monkeypatch.setenv("USE_POLYGON_FIRST", "true")
    monkeypatch.setenv("FORCE_YAHOO_PRICES", "false")
    monkeypatch.setenv("TRAIN_FORCE_YAHOO", "false")
    monkeypatch.setenv("PAPER_SIM_FORCE_YAHOO", "false")
    monkeypatch.setenv("PAPER_SIM_ACTIVE_RUN", "false")
    monkeypatch.setenv("PRICE_DATA_SOURCE", "yfinance")
    assert _price_source() == "hybrid_polygon"


def test_skip_yahoo_fallback_global(monkeypatch):
    from data_platform.price_fetch_policy import skip_yahoo_fallback

    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    monkeypatch.setenv("USE_POLYGON_FIRST", "true")
    monkeypatch.setenv("SKIP_YAHOO_FALLBACK", "true")
    monkeypatch.setenv("FORCE_YAHOO_PRICES", "false")
    assert skip_yahoo_fallback() is True
