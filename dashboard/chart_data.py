"""Build chart-ready OHLCV + overlay payloads for the dashboard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from data_platform.market_prices import fetch_period


def fetch_ohlcv(ticker: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    df = fetch_period(ticker, period=period, interval=interval)
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.dropna(subset=["Open", "High", "Low", "Close"]).copy()
    df.index = pd.to_datetime(df.index)
    return df


def to_lightweight_candles(df: pd.DataFrame) -> list[dict[str, Any]]:
    """TradingView lightweight-charts candlestick series payload."""
    if df is None or df.empty:
        return []
    out = []
    for ts, row in df.iterrows():
        out.append(
            {
                "time": ts.strftime("%Y-%m-%d"),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
            }
        )
    return out


def to_lightweight_volume(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None or df.empty or "Volume" not in df.columns:
        return []
    out = []
    closes = df["Close"].astype(float)
    opens = df["Open"].astype(float)
    for ts, vol, c, o in zip(df.index, df["Volume"].astype(float), closes, opens):
        color = "#26a69a" if c >= o else "#ef5350"
        out.append(
            {
                "time": ts.strftime("%Y-%m-%d"),
                "value": float(vol),
                "color": color,
            }
        )
    return out


def to_lightweight_line(series: pd.Series, color: str = "#2962FF") -> list[dict[str, Any]]:
    if series is None or series.empty:
        return []
    s = series.dropna()
    return [{"time": ts.strftime("%Y-%m-%d"), "value": float(v)} for ts, v in s.items()]


def ur_overlay_markers(df: pd.DataFrame, ur: dict[str, Any]) -> list[dict[str, Any]]:
    """Add a downward marker on the undercut bar and upward arrow on the rally bar."""
    if df is None or df.empty or not ur.get("ur_detected"):
        return []
    last_ts = df.index[-1]
    return [
        {
            "time": last_ts.strftime("%Y-%m-%d"),
            "position": "belowBar",
            "color": "#FF9800",
            "shape": "arrowUp",
            "text": f"U&R {float(ur.get('ur_score', 0.0)):.2f}",
        }
    ]


def latest_paper_sim_report(reports_dir: str = "reports") -> dict | None:
    p = Path(reports_dir)
    if not p.is_dir():
        return None
    files = sorted(p.glob("paper_sim_*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except Exception:
        return None
