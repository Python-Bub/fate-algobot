# data_loader.py

import pandas as pd
import numpy as np
import os
from utils import log

def _load_local_csv(ticker: str) -> pd.DataFrame:
    path = f"data/{ticker.upper()}.csv"
    if not os.path.exists(path):
        log.warning(f"[DATA] Missing {ticker} CSV. Skipping.")
        return None

    df = pd.read_csv(path, parse_dates=["Date"])
    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Adj Close": "close", "Volume": "volume"
    })

    df["Date"] = pd.to_datetime(df["Date"], utc=True)
    df = df.set_index("Date").sort_index()

    return df[["open", "high", "low", "close", "volume"]]

def fetch_price_data(ticker: str, start: str = None, end: str = None) -> pd.DataFrame:
    df = _load_local_csv(ticker)

    if df is None or df.empty or df.shape[0] < 5:
        log.warning(f"[DATA] No usable CSV for {ticker}. Skipping training.")
        return pd.DataFrame()

    if start:
        df = df[df.index >= pd.to_datetime(start).tz_localize("UTC")]
    if end:
        df = df[df.index <= pd.to_datetime(end).tz_localize("UTC")]

    return df

def fetch_sentiment_data(ticker: str, start: str = None, end: str = None, freq: str = "30Min") -> pd.DataFrame:
    start_ts = pd.to_datetime(start).tz_localize("UTC") if start else pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=1)
    end_ts   = pd.to_datetime(end).tz_localize("UTC")   if end else pd.Timestamp.now(tz="UTC")

    times    = pd.date_range(start=start_ts, end=end_ts, freq=freq, tz="UTC")
    data     = np.random.uniform(-1, 1, len(times))
    df       = pd.DataFrame({"sentiment": data}, index=times)
    df.index.name = "timestamp"

    return df

def get_price_data(ticker: str, start: str = None, end: str = None) -> pd.DataFrame:
    return fetch_price_data(ticker, start, end)

def get_sentiment_data(ticker: str, start: str = None, end: str = None) -> pd.DataFrame:
    return fetch_sentiment_data(ticker, start, end)

def fetch_data(ticker: str, start: str = None, end: str = None) -> pd.DataFrame:
    price     = get_price_data(ticker, start, end)
    sentiment = get_sentiment_data(ticker, start, end)

    return price.merge(sentiment, left_index=True, right_index=True)
