#!/usr/bin/env python3
"""Refresh data/top100_market_cap.json from yfinance market-cap ranking."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    from universe_lifecycle.rankings import refresh_market_cap_tiers

    out = refresh_market_cap_tiers(top_n=int(os.getenv("TOP100_COUNT", "100")))
    print(f"[top100] wrote {len(out['top100'])} symbols → data/top100_market_cap.json")
    print(f"[top50]  wrote {len(out['top50pct'])} symbols → data/top50pct_market_cap.json")
    print(" ".join(out["top100"][:15]), "…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
