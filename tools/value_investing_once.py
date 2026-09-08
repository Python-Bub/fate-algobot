#!/usr/bin/env python3
"""One-shot value / DCF intrinsic-value screen (book formulas).

  ./venv/bin/python -u tools/value_investing_once.py AAPL MSFT
  ./run_all.sh value-screen AAPL IBM
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="DCF intrinsic value + Graham/Buffett screens")
    ap.add_argument("symbols", nargs="*", default=["AAPL", "IBM", "BRK-B"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    from analytics.value_investing import analyze_value, intrinsic_value, terminal_value

    # Smoke the pure formulas first (book check)
    cfs = [100.0, 105.0, 110.25, 115.76, 121.55]
    tv = terminal_value(cfs[-1], r=0.10, g=0.03)
    iv = intrinsic_value(cfs, r=0.10, tv=tv)
    if args.json:
        reports = []
        for sym in args.symbols:
            t = analyze_value(sym)
            reports.append(
                {
                    "symbol": t.symbol,
                    "iv_ps": round(t.intrinsic_per_share, 4),
                    "price": round(t.market_price, 4),
                    "mos": round(t.margin_of_safety, 4),
                    "deep_value": t.deep_value,
                    "graham_net_net": t.graham_net_net,
                    "buffett_quality": round(t.buffett_quality, 4),
                    "boost": round(t.boost, 4),
                }
            )
        print(json.dumps({"formula_check": {"tv": tv, "iv": iv}, "tickers": reports}, indent=2))
        return 0

    print(f"formula check  TV={tv:,.2f}  IV={iv:,.2f}  (r=10% g=3% n=5 growing CF)")
    print("-" * 72)
    for sym in args.symbols:
        t = analyze_value(sym)
        print(
            f"{t.symbol:8}  price={t.market_price:>10.2f}  IV/sh={t.intrinsic_per_share:>10.2f}  "
            f"MOS={t.margin_of_safety:>+6.1%}  deep={t.deep_value}  "
            f"netnet={t.graham_net_net}  buffett={t.buffett_quality:+.2f}  boost={t.boost:+.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
