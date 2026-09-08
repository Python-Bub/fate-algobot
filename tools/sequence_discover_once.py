#!/usr/bin/env python3
"""CLI: general sequence discovery (author's guess_patterns machinery in FATE).

Examples:
  ./venv/bin/python -u tools/sequence_discover_once.py --test
  ./venv/bin/python -u tools/sequence_discover_once.py --seq 2,4,8,16
  ./venv/bin/python -u tools/sequence_discover_once.py --ticker AAPL --returns 12
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


def _run_builtin_tests() -> int:
    from analytics.sequence_discover import _close, fmt, search_pattern

    cases = [
        ("powers of 2", [2, 4, 8, 16], 32),
        ("squares", [1, 4, 9, 16], 25),
        ("n^2+1", [2, 5, 10, 17], 26),
        ("fib", [1, 1, 2, 3, 5], 8),
        ("2^n-1", [1, 3, 7, 15, 31], 63),
        ("arithmetic", [10, 20, 30], 40),
        ("power tower", [4, 9, 3125, 823543], 285311670611),
    ]
    failed = 0
    print("=== sequence_discover tests ===\n")
    for label, seq, expected in cases:
        r = search_pattern(seq)
        if r is None:
            print(f"FAIL {label}: no pattern")
            failed += 1
            continue
        ok = _close(r.next_val, expected)
        print(f"{'OK' if ok else 'FAIL'} {label}: expected {expected}, got {fmt(r.next_val)}")
        if not ok:
            failed += 1
            for line in r.thoughts[-4:]:
                print(f"    {line}")
    return failed


def main() -> int:
    ap = argparse.ArgumentParser(description="Sequence discovery smoke / ticker returns")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--seq", default="", help="comma-separated numbers")
    ap.add_argument("--ticker", default="")
    ap.add_argument("--returns", type=int, default=12, help="last N daily returns for --ticker")
    ap.add_argument("--period", default="6mo")
    args = ap.parse_args()

    if args.test:
        return 0 if _run_builtin_tests() == 0 else 1

    from analytics.sequence_discover import fmt, search_pattern

    nums: list[float] = []
    if args.seq:
        nums = [float(x.strip()) for x in args.seq.split(",") if x.strip()]
    elif args.ticker:
        import numpy as np
        import yfinance as yf

        df = yf.download(args.ticker, period=args.period, interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty:
            raise SystemExit(f"no data for {args.ticker}")
        close = df["Close"]
        if hasattr(close, "columns"):
            close = close.iloc[:, 0]
        c = close.astype(float).values
        rets = np.diff(c) / np.maximum(c[:-1], 1e-12)
        nums = [float(r * 100.0) for r in rets[-args.returns :]]
        print(f"{args.ticker} last {len(nums)} returns (%): {[fmt(x) for x in nums]}")
    else:
        ap.print_help()
        return 2

    r = search_pattern(nums)
    if r is None:
        print("No pattern found.")
        return 1
    for line in r.thoughts:
        print(line)
    print(f"\n→ next = {fmt(r.next_val)}  family={r.best.family}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
