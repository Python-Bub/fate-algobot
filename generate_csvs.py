# generate_csvs.py
#
# Legacy helper for data_loader.py: dump full Yahoo history for a few tickers to
# data/{TICKER}.csv. Kept behind __main__ so importing this module never downloads.

import os

import yfinance as yf

tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META"]
folder = "data"


def main(symbols=None, out_dir=folder) -> int:
    os.makedirs(out_dir, exist_ok=True)
    failed = 0
    for t in symbols or tickers:
        print(f"[FETCH] Downloading {t}...")
        try:
            df = yf.Ticker(t).history(period="max")
            df.to_csv(f"{out_dir}/{t}.csv")
            print(f"[SAVE] {t}.csv written with {df.shape[0]} rows.")
        except Exception as e:
            failed += 1
            print(f"[ERROR] Failed to fetch {t}: {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
