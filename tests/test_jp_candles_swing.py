"""Tests for Japanese candlestick detection and swing buy windows."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from analytics.jp_candles import (
    PAT_BULLISH_ENGULF,
    PAT_DOJI,
    PAT_HAMMER,
    PAT_NONE,
    _recent_trend,
    assess_candles_from_df,
    classify_bar,
)
from analytics.market_session import swing_buy_window_open

ET = ZoneInfo("America/New_York")


def test_classify_hammer_after_downtrend():
    pid = classify_bar(100, 101, 90, 100.5, trend=-1)
    assert pid == PAT_HAMMER


def test_classify_bullish_engulf():
    pid = classify_bar(98, 105, 97, 104, o2=103, c2=100, trend=-1)
    assert pid == PAT_BULLISH_ENGULF


def test_assess_from_dataframe():
    df = pd.DataFrame(
        {
            "Open": [100, 99, 98, 97, 96, 95.5],
            "High": [101, 100, 99, 98, 97, 96],
            "Low": [99, 98, 97, 96, 95, 90],
            "Close": [99.5, 98.5, 97.5, 96.5, 95.5, 95.8],
        }
    )
    ca = assess_candles_from_df(df)
    assert ca.pattern in (
        "HAMMER",
        "INV_HAMMER",
        "BULLISH_ENGULF",
        "NONE",
        "DOJI",
        "SHOOTING_STAR",
        "HANGING_MAN",
        "BEARISH_ENGULF",
    )


def test_swing_midday_blocked(monkeypatch):
    monkeypatch.setenv("SWING_BUY_WINDOW_ENABLED", "true")
    midday = datetime(2026, 6, 9, 12, 0, tzinfo=ET)
    ok, reason = swing_buy_window_open(midday)
    assert ok is False
    assert "midday" in reason.lower()


def test_swing_open_window_allowed(monkeypatch):
    monkeypatch.setenv("SWING_BUY_WINDOW_ENABLED", "true")
    open_time = datetime(2026, 6, 9, 9, 45, tzinfo=ET)
    ok, _ = swing_buy_window_open(open_time)
    assert ok is True


def test_swing_close_window_allowed(monkeypatch):
    monkeypatch.setenv("SWING_BUY_WINDOW_ENABLED", "true")
    close_time = datetime(2026, 6, 9, 15, 45, tzinfo=ET)
    ok, _ = swing_buy_window_open(close_time)
    assert ok is True


def test_flat_bar_returns_none_not_crash():
    assert classify_bar(100.0, 100.0, 100.0, 100.0, trend=-1) == PAT_NONE


def test_recent_trend_uses_widest_available_span():
    closes = [90.0, 91.0, 92.0, 93.0, 94.0, 95.0, 96.0]
    assert _recent_trend(closes, lookback=6) == 1
    assert _recent_trend(closes, lookback=99) == 1  # clamped to len-1


def test_recent_trend_short_series():
    assert _recent_trend([95.0, 96.0], lookback=5) == 1
    assert _recent_trend([96.0, 95.0], lookback=5) == -1


def test_nan_row_skipped_without_shrinking_window():
    df = pd.DataFrame(
        {
            "Open": [100, 99, float("nan"), 97, 96, 95.5, 95.0],
            "High": [101, 100, float("nan"), 98, 97, 96, 96],
            "Low": [99, 98, float("nan"), 96, 95, 90, 89],
            "Close": [99.5, 98.5, float("nan"), 96.5, 95.5, 95.8, 95.5],
        }
    )
    ca = assess_candles_from_df(df, lookback=6)
    assert ca.trend != 0 or ca.pattern != "NONE"


def test_dragonfly_doji_classed_as_hammer_in_downtrend():
    # Open≈Close at top, long lower shadow — dragonfly / hammer family, not plain DOJI.
    pid = classify_bar(100.0, 100.05, 90.0, 100.0, trend=-1)
    assert pid == PAT_HAMMER


def test_tiny_range_bar_no_division_crash():
    pid = classify_bar(1e-8, 1e-8 + 1e-15, 1e-8, 1e-8, trend=0)
    assert pid == PAT_NONE
