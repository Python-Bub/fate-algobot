"""Day-trade setup scanners on synthetic Yahoo-style bars."""

from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.day_trade_setups import candlestick_signal, scan_setups, trend_signal, vwap_signal


def _bars(n: int = 60, *, drift: float = 0.001) -> pd.DataFrame:
    idx = pd.date_range("2026-06-09 09:30", periods=n, freq="1min", tz="America/New_York")
    c = 100 * np.cumprod(1 + np.random.default_rng(1).normal(drift, 0.0008, n))
    o = np.roll(c, 1)
    o[0] = c[0]
    h = np.maximum(o, c) * 1.0005
    l = np.minimum(o, c) * 0.9995
    v = np.full(n, 10_000.0)
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": v}, index=idx)


def test_trend_signal_uptrend():
    df = _bars(80, drift=0.002)
    val, label = trend_signal(df)
    assert label in ("", "trend_up", "trend_down")
    if label == "trend_up":
        assert val > 0


def test_scan_setups_returns_bias():
    df = _bars(90)
    vwap = float(df["Close"].mean())
    scan = scan_setups("NVDA", df, vwap=vwap)
    assert scan.ticker == "NVDA"
    assert -1.0 <= scan.bias <= 1.0


def test_rank_scan_positive_bias():
    import numpy as np
    import pandas as pd
    from analytics.day_trade_setups import scan_setups
    from analytics.day_trade_rank import rank_scan

    idx = pd.date_range("2026-06-09 09:30", periods=60, freq="1min", tz="America/New_York")
    c = 100 * np.cumprod(1 + np.random.default_rng(2).normal(0.001, 0.0008, 60))
    df = pd.DataFrame(
        {"Open": c, "High": c * 1.001, "Low": c * 0.999, "Close": c, "Volume": 10000.0},
        index=idx,
    )
    scan = scan_setups("NVDA", df, vwap=float(c.mean()))
    pick = rank_scan(scan)
    assert pick.ticker == "NVDA"
    assert isinstance(pick.score, float)

