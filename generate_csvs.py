# generate_csvs.py

import os
import yfinance as yf

tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META"]
folder  = "data"

# Create data folder if missing
os.makedirs(folder, exist_ok=True)

for t in tickers:
    print(f"[FETCH] Downloading {t}...")
    try:
        df = yf.Ticker(t).history(period="max")
        df.to_csv(f"{folder}/{t}.csv")
        print(f"[SAVE] {t}.csv written with {df.shape[0]} rows.")
    except Exception as e:
        print(f"[ERROR] Failed to fetch {t}: {e}")
