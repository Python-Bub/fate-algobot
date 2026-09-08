"""Bottom-fisher universe math + OHLC slicing (no Yahoo)."""

from __future__ import annotations

import pandas as pd

from analytics.trade_math import distress_score, falling_knife
from bottom_fisher.universe import BottomCandidate, _row_from_ohlc, frame_for_symbol
from bottom_fisher.config import BottomFisherConfig


def _ohlc(n: int = 80, last: float = 20.0, start: float = 28.0) -> pd.DataFrame:
    step = (last - start) / (n - 1)
    close = [start + i * step for i in range(n)]
    return pd.DataFrame(
        {
            "Open": close,
            "High": [c * 1.01 for c in close],
            "Low": [c * 0.99 for c in close],
            "Close": close,
            "Adj Close": close,
            "Volume": [2_000_000] * n,
        }
    )


def test_frame_for_symbol_multiindex_level0_or_1():
    a = _ohlc()
    b = _ohlc(last=15.0, start=22.0)
    parts = []
    for sym, df in (("AAA", a), ("BBB", b)):
        sub = df.copy()
        sub.columns = pd.MultiIndex.from_product([sub.columns, [sym]])
        parts.append(sub)
    raw = pd.concat(parts, axis=1)
    fa = frame_for_symbol(raw, "AAA")
    fb = frame_for_symbol(raw, "BBB")
    assert fa is not None and "Close" in fa.columns
    assert abs(float(fb["Close"].iloc[-1]) - 15.0) < 1e-6


def test_row_from_ohlc_uses_adj_close():
    df = _ohlc()
    df = df.drop(columns=["Close"])
    cfg = BottomFisherConfig(min_price_usd=1.0, max_price_usd=500.0, min_daily_volume_usd=1.0)
    cand = _row_from_ohlc("XYZ", df, cfg)
    assert cand is not None
    assert cand.last_close > 0


def test_knife_not_in_distress_pool():
    assert falling_knife(-0.04, -0.11, -0.09)
    s = distress_score(
        ret_60d=-0.3,
        ret_20d=-0.2,
        ret_5d=-0.11,
        ret_1d=-0.04,
        drawdown_52w=-0.5,
        dollar_vol=3e6,
    )
    assert s == 0.0


def test_candidate_dataclass():
    c = BottomCandidate("TEST", -0.2, -0.05, 0.02, 0.01, -0.3, 12.0, 2e6, 0.1)
    assert c.ticker == "TEST"
