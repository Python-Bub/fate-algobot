import yfinance as yf
import pandas as pd
from feature_engineering import build_features
from config import TICKERS

tickers = ["AAPL", "TSLA", "NVDA", "AMZN", "MSFT", "COIN", "AMD"]


def verify():
    print("🔎 Verifying feature outputs\n")
    for ticker in TICKERS:
        print(f"--- {ticker} ---")
        # you can tweak start/end here if needed
        df = build_features(ticker, start="2023-01-01", end=None)
        print(f"Rows: {df.shape[0]}, Columns: {df.columns.tolist()}")
        print(df.head(3).to_string(), "\n")

    if df.empty:
        print(f"❌ {ticker}: No data downloaded")
        return

    features_df = build_features(df)
    if features_df.empty:
        print(f"⚠️ {ticker}: Feature generation failed")
        return

    expected = [
        "ma_5", "ma_10", "ma_20", "rsi_14", "macd", "macd_signal", "atr_14", "volume",
        "open_close_ratio", "high_low_ratio", "return_1d", "return_5d", "volatility_5d",
        "momentum_10d", "adx_14"
    ]

    missing = [col for col in expected if col not in features_df.columns or features_df[col].isna().all()]
    if missing:
        print(f"❌ {ticker}: Missing or NaN-heavy features: {missing}")
    else:
        print(f"✅ {ticker}: All features present")

if __name__ == "__main__":
    for ticker in tickers:
        verify()
