"""Yahoo Finance intraday OHLCV — primary candle source for day trading."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from utils import log

ROOT = Path(__file__).resolve().parents[1]
INTEL_DIR = ROOT / "data" / "intel" / "yahoo_bars"


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [c[0] if isinstance(c, tuple) else c for c in out.columns]
    rename = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    }
    out = out.rename(columns={k: v for k, v in rename.items() if k in out.columns})
    for col in ("Open", "High", "Low", "Close"):
        if col not in out.columns and "Close" in out.columns:
            out[col] = out["Close"]
    if "Volume" not in out.columns:
        out["Volume"] = 0.0
    out = out.sort_index()
    return out


def fetch_yahoo_bars(
    ticker: str,
    *,
    interval: str | None = None,
    period: str | None = None,
) -> pd.DataFrame:
    """Latest Yahoo intraday bars (1m default — fast refresh for day trading)."""
    from multi_source_data import fetch_yahoo_intraday

    iv = interval or os.getenv("DAY_TRADE_YAHOO_INTERVAL", "1m")
    per = period or os.getenv("DAY_TRADE_YAHOO_PERIOD", "1d")
    if iv == "1m" and per == "5d":
        per = os.getenv("DAY_TRADE_YAHOO_PERIOD", "1d")
    df = fetch_yahoo_intraday(ticker.strip().upper(), period=per, interval=iv)
    return _normalize(df)


def persist_bars(ticker: str, df: pd.DataFrame) -> Path | None:
    """Write last N bars for HFT / fortress consumers."""
    if df is None or df.empty:
        return None
    INTEL_DIR.mkdir(parents=True, exist_ok=True)
    sym = ticker.strip().upper()
    tail = df.tail(int(os.getenv("DAY_TRADE_YAHOO_TAIL", "240")))
    rows: list[dict[str, Any]] = []
    for ts, row in tail.iterrows():
        rows.append(
            {
                "t": pd.Timestamp(ts).isoformat(),
                "Open": float(row["Open"]),
                "High": float(row["High"]),
                "Low": float(row["Low"]),
                "Close": float(row["Close"]),
                "Volume": float(row.get("Volume", 0)),
            }
        )
    payload = {
        "ticker": sym,
        "source": "yahoo",
        "interval": os.getenv("DAY_TRADE_YAHOO_INTERVAL", "1m"),
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "bars": rows,
    }
    path = INTEL_DIR / f"{sym}.json"
    import json

    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def latest_close(ticker: str, df: pd.DataFrame | None = None) -> float:
    if df is None:
        df = fetch_yahoo_bars(ticker)
    if df.empty:
        return 0.0
    return float(df["Close"].iloc[-1])


def session_vwap(df: pd.DataFrame) -> float:
    if df is None or df.empty:
        return 0.0
    vol = df["Volume"].astype(float)
    px = df["Close"].astype(float)
    v = vol.sum()
    if v <= 0:
        return float(px.iloc[-1])
    return float((px * vol).sum() / v)
