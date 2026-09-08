#!/usr/bin/env python3
"""CLI: structure/pattern scan + historical validation (FATE research-backed module).

Examples:
  ./venv/bin/python -u tools/structure_patterns_once.py --ticker AAPL
  ./venv/bin/python -u tools/structure_patterns_once.py --ticker AAPL --validate
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except Exception:
    pass


def _load_ohlc(ticker: str, period: str = "2y"):
    import pandas as pd
    import yfinance as yf

    df = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=True)
    if df is None or df.empty:
        raise SystemExit(f"no data for {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    return df


def main() -> int:
    ap = argparse.ArgumentParser(description="Structure / S/R / pattern scan")
    ap.add_argument("--ticker", default="AAPL")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--lookback", type=int, default=60)
    ap.add_argument("--period", default="2y")
    args = ap.parse_args()

    from analytics.structure_patterns import analyze_structure, structure_rank_boost, validate_structure

    df = _load_ohlc(args.ticker, args.period)
    ctx = analyze_structure(df, lookback=args.lookback)
    print(f"=== {args.ticker} latest bar ===")
    for line in ctx.summary_lines():
        print(line)
    boost, meta = structure_rank_boost(df)
    print(f"rank_boost={boost:+.4f}  meta={meta}")

    if args.validate:
        print(f"\n=== validation (horizon={args.horizon}d, excess vs directional baseline) ===")
        rows = validate_structure(df, horizon=args.horizon, lookback=args.lookback)
        if not rows:
            print("  (insufficient history)")
        for r in rows:
            print(
                f"  {r['pattern']:22s}  n={r['n']:4d}  hit={r['hit_rate']*100:5.1f}%  "
                f"base={r['baseline']*100:5.1f}%  excess={r['excess']*100:+5.1f}%"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
