#!/usr/bin/env python3
"""Print good vs bad news breakdown for a ticker (Finnhub + NewsAPI + optional LLM)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    ap = argparse.ArgumentParser(description="News sentiment digest for one ticker")
    ap.add_argument("symbol", help="Ticker symbol (required).")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    from intel.news_digest import build_news_digest

    d = build_news_digest(args.symbol.strip().upper())
    if args.json:
        print(json.dumps(d.to_dict(), indent=2))
        return 0

    print(f"\n=== {d.symbol} news digest ===")
    print(f"Verdict:        {d.verdict.upper()}")
    print(f"Score:          {d.composite_score:+.3f}  (block long if < {os.getenv('SENTIMENT_BLOCK_THRESHOLD', '-0.35')})")
    print(f"Headlines:      {d.bullish_count} bullish | {d.bearish_count} bearish | {d.neutral_count} neutral")
    print(f"Sources:        Finnhub={d.finnhub_count}  NewsAPI={d.newsapi_count}  Cramer={d.cramer_count}")
    if d.finnhub_bull_pct is not None:
        print(f"Finnhub API:    {d.finnhub_bull_pct:.0%} bullish / {d.finnhub_bear_pct:.0%} bearish")
    if d.llm_thesis:
        print(f"LLM thesis:     {d.llm_thesis}")
    print(f"Block long:     {'YES' if d.block_long else 'no'}")

    if d.top_bearish:
        print("\n--- Bearish headlines ---")
        for i, h in enumerate(d.top_bearish, 1):
            print(f"  {i}. {h}")
    if d.top_bullish:
        print("\n--- Bullish headlines ---")
        for i, h in enumerate(d.top_bullish, 1):
            print(f"  {i}. {h}")
    if not d.top_bearish and not d.top_bullish:
        print("\n(no classified headlines — check API keys / quota)")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
