#!/usr/bin/env python3
"""Watch free news for undervaluation / value claims and investigate (no paid news APIs).

  ./venv/bin/python tools/valuation_news_watch.py
  ./venv/bin/python tools/valuation_news_watch.py --once GOOG AAPL
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="single scan then exit")
    ap.add_argument("symbols", nargs="*", help="optional tickers")
    args = ap.parse_args()

    from intel.free_news_investigator import scan_watchlist

    pause = float(os.getenv("VALUATION_NEWS_LOOP_SEC", "900"))
    while True:
        syms = [s.upper() for s in args.symbols] or None
        payload = scan_watchlist(syms)
        rows = payload.get("rows") or {}
        hits = [
            (k, v)
            for k, v in rows.items()
            if v.get("investigate") or v.get("allow_long_boost")
        ]
        print(
            json.dumps(
                {
                    "n": payload.get("n"),
                    "hits": len(hits),
                    "top": [
                        {
                            "symbol": k,
                            "tilt": v.get("tilt"),
                            "mos": v.get("margin_of_safety"),
                            "claim": (v.get("top_claim") or "")[:100],
                        }
                        for k, v in sorted(hits, key=lambda kv: -float(kv[1].get("tilt") or 0))[:8]
                    ],
                },
                indent=2,
            ),
            flush=True,
        )
        if args.once:
            return 0
        time.sleep(max(60.0, pause))


if __name__ == "__main__":
    raise SystemExit(main())
