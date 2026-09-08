"""5-minute RSI for entry timing vs daily trend flags."""

from __future__ import annotations

import numpy as np
import pandas as pd

from utils import log


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0)
    down = -d.clip(upper=0)
    ma_u = up.rolling(n, min_periods=n).mean()
    ma_d = down.rolling(n, min_periods=n).mean()
    rs = ma_u / ma_d.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)


def intraday_5m_bundle(ticker: str, period: str = "5d") -> pd.DataFrame | None:
    try:
        from multi_source_data import fetch_yahoo_intraday

        df = fetch_yahoo_intraday(ticker, period=period, interval="5m")
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df = df.dropna(how="all")
        df["rsi_5m"] = _rsi(df["Close"])
        return df
    except Exception as e:
        log.warning("[MTF] 5m fetch failed %s: %s", ticker, e)
        return None


def mtf_buy_ok(daily_bull: bool, ticker: str, rsi_oversold: float = 30.0) -> bool:
    """
    Page-2 spec: Daily EMA20 > EMA50 AND 5m RSI < 30 → buy trigger.
    """
    if not daily_bull:
        return False
    m = intraday_5m_bundle(ticker)
    if m is None or m.empty:
        return daily_bull
    last = float(m["rsi_5m"].iloc[-1])
    return last < rsi_oversold
