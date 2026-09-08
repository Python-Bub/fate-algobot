import csv
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

from feature_engineering import build_features
from ml_model import predict_row

TICKERS = ["AAPL", "TSLA", "NVDA", "AMZN", "MSFT", "COIN", "AMD"]
CONFIDENCE_THRESHOLD = 0.65
TRADE_LOG_FILE = "multi_trade_log.csv"

stop_requested = False


def listen_for_stop():
    global stop_requested
    while True:
        if input().strip().lower() == "stop":
            stop_requested = True
            print("\nStop received — shutting down")
            break


threading.Thread(target=listen_for_stop, daemon=True).start()

try:
    from live_chart import show_live_chart

    _chart = show_live_chart()
except Exception:
    _chart = None


def log_trade(ts, ticker, signal, price, equity, pnl, confidence):
    with open(TRADE_LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([ts, ticker, signal, f"{price:.2f}", f"{equity:.2f}", f"{pnl:.2f}", f"{confidence:.2%}"])


class TradeSimulator:
    def __init__(self, starting_cash=10000.0):
        self.cash = starting_cash
        self.position = {}
        self.entry_price = {}
        self.equity_curve = [starting_cash]

    def on_signal(self, ticker, price, signal, confidence):
        shares = int(self.cash * 0.1 // max(price, 1e-6))
        pnl = 0.0

        if signal == "BUY" and self.position.get(ticker, 0) == 0 and shares > 0:
            self.position[ticker] = shares
            self.entry_price[ticker] = price
            self.cash -= shares * price
            print(f"{ticker}: BUY {shares} @ ${price:.2f} | p_up={confidence:.2%}")

        elif signal == "SELL" and self.position.get(ticker, 0) > 0:
            pnl = (price - self.entry_price[ticker]) * self.position[ticker]
            self.cash += self.position[ticker] * price
            self.position[ticker] = 0
            print(f"{ticker}: SELL @ ${price:.2f} | P&L: ${pnl:.2f}")

        total_equity = self.cash + sum(
            self.position.get(t, 0) * (price if t == ticker else self.entry_price.get(t, 0)) for t in self.position
        )

        self.equity_curve.append(total_equity)
        log_trade(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ticker, signal, price, total_equity, pnl, confidence)
        if _chart:
            _chart(self.equity_curve)


def fetch_intraday(ticker: str) -> pd.DataFrame:
    df = yf.download(ticker, period="7d", interval="1m", progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    return df


def main():
    print(f"Paper loop: {', '.join(TICKERS)} — type 'stop' to exit.\n")
    sim = TradeSimulator()
    last_seen = {}
    end = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=800)).strftime("%Y-%m-%d")

    while not stop_requested:
        for ticker in TICKERS:
            df = fetch_intraday(ticker)
            if df.empty:
                print(f"No intraday data for {ticker}")
                continue

            last_ts = last_seen.get(ticker)
            new_data = df[df.index > last_ts] if last_ts is not None else df
            if new_data.empty:
                continue

            df_feat = build_features(ticker, start, end)
            if df_feat.empty:
                print(f"Feature build failed for {ticker}")
                continue

            path = os.path.join("models", f"{ticker}_model.pkl")
            if not os.path.isfile(path):
                print(f"No model for {ticker}")
                continue

            try:
                _pred, p_up = predict_row(path, df_feat.iloc[-1])
            except Exception as e:
                print(f"Prediction error for {ticker}: {e}")
                continue

            if p_up >= CONFIDENCE_THRESHOLD:
                label = "BUY"
            elif p_up <= 1.0 - CONFIDENCE_THRESHOLD:
                label = "SELL"
            else:
                label = "HOLD"

            close_col = new_data["Close"]
            price = float(close_col.iloc[-1])
            sim.on_signal(ticker, price, label, p_up)
            last_seen[ticker] = new_data.index[-1]

        time.sleep(60)


if __name__ == "__main__":
    main()
