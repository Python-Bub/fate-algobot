# generate_csvs.py

import os

import yfinance as yf

TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META"]
FOLDER = "data"


def main() -> None:
    os.makedirs(FOLDER, exist_ok=True)
    for t in TICKERS:
        print(f"[FETCH] Downloading {t}...")
        try:
            df = yf.Ticker(t).history(period="max")
            df.to_csv(f"{FOLDER}/{t}.csv")
            print(f"[SAVE] {t}.csv written with {df.shape[0]} rows.")
        except Exception as e:
            print(f"[ERROR] Failed to fetch {t}: {e}")


if __name__ == "__main__":
    main()
