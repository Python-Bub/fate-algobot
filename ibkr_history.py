"""
Daily OHLCV from Interactive Brokers (TWS / IB Gateway) for feature engineering.

Set PRICE_DATA_SOURCE=ibkr or hybrid (try IBKR, then Yahoo).
Requires TWS/Gateway running, API enabled, and market data permissions for the symbol.

Uses ADJUSTED_LAST for 1-day bars when available (split-adjusted last price).
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
from ib_insync import IB, Stock, util

from config import IBKR_CLIENT_ID, IBKR_HOST, IBKR_PORT
from utils import log

_ib_prices: IB | None = None


def get_ib_price_client() -> IB:
    global _ib_prices
    if _ib_prices is not None and _ib_prices.isConnected():
        return _ib_prices
    cid = int(os.getenv("IBKR_PRICE_CLIENT_ID", str(IBKR_CLIENT_ID)))
    host = os.getenv("IBKR_HOST", IBKR_HOST)
    port = int(os.getenv("IBKR_PORT", str(IBKR_PORT)))
    ib = IB()
    ib.connect(host, port, clientId=cid)
    _ib_prices = ib
    log.info("[IBKR] Price client connected %s:%s clientId=%s", host, port, cid)
    return ib


def disconnect_ib_prices() -> None:
    global _ib_prices
    if _ib_prices is not None and _ib_prices.isConnected():
        _ib_prices.disconnect()
        log.info("[IBKR] Price client disconnected")
    _ib_prices = None


def _bars_to_df(bars) -> pd.DataFrame:
    if not bars:
        return pd.DataFrame()
    df = util.df(bars)
    if df.empty:
        return df
    df = df.set_index("date")
    df.index = pd.to_datetime(df.index)
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    rename = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    for a, b in rename.items():
        if a in df.columns and b not in df.columns:
            df = df.rename(columns={a: b})
    return df


def fetch_daily_bars_ibkr(
    ib: IB,
    symbol: str,
    start_date: str,
    end_date: str | None = None,
    what_to_show: str | None = None,
) -> pd.DataFrame:
    """
    Pull daily bars from IBKR in chunks (historical pacing limits).
    """
    wts = what_to_show or os.getenv("IBKR_BAR_WHAT_TO_SHOW", "ADJUSTED_LAST")
    use_rth = os.getenv("IBKR_USE_RTH", "true").lower() in ("1", "true", "yes")
    sleep_s = float(os.getenv("IBKR_HIST_SLEEP_SEC", "0.35"))

    end_dt = datetime.now(timezone.utc).replace(tzinfo=None)
    if end_date:
        end_dt = min(end_dt, pd.Timestamp(end_date).to_pydatetime())
    start_ts = pd.Timestamp(start_date)

    contract = Stock(symbol.replace(".", " "), "SMART", "USD")
    ib.qualifyContracts(contract)

    frames: list[pd.DataFrame] = []
    chunk_end = end_dt
    max_iters = int(os.getenv("IBKR_HIST_MAX_CHUNKS", "40"))
    seen_dates: set[pd.Timestamp] = set()
    active_wts = wts

    def _req(what: str):
        return ib.reqHistoricalData(
            contract,
            endDateTime=end_str,
            durationStr="365 D",
            barSizeSetting="1 day",
            whatToShow=what,
            useRTH=use_rth,
            formatDate=1,
        )

    for _ in range(max_iters):
        end_str = chunk_end.strftime("%Y%m%d %H:%M:%S") + " US/Eastern"
        bars = None
        try:
            bars = _req(active_wts)
        except Exception as e:
            if active_wts != "TRADES":
                log.warning("[IBKR] %s whatToShow=%s failed (%s); retrying TRADES", symbol, active_wts, e)
                active_wts = "TRADES"
                try:
                    bars = _req("TRADES")
                except Exception as e2:
                    log.warning("[IBKR] reqHistoricalData failed %s: %s", symbol, e2)
                    break
            else:
                log.warning("[IBKR] reqHistoricalData failed %s: %s", symbol, e)
                break

        if bars is None:
            break

        time.sleep(sleep_s)

        part = _bars_to_df(bars)
        if part.empty:
            break

        part = part[~part.index.duplicated(keep="last")]
        new_rows = part[~part.index.isin(seen_dates)]
        if new_rows.empty:
            break
        for d in new_rows.index:
            seen_dates.add(pd.Timestamp(d))
        frames.append(new_rows)

        earliest = part.index.min()
        if pd.Timestamp(earliest) <= start_ts:
            break
        chunk_end = pd.Timestamp(earliest).to_pydatetime() - timedelta(days=1)
        if chunk_end < start_ts:
            break

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    out = out.loc[out.index >= start_ts]
    out = out.loc[out.index <= pd.Timestamp(end_dt)]

    if "Adj Close" not in out.columns and "Close" in out.columns:
        out["Adj Close"] = out["Close"]

    return out
