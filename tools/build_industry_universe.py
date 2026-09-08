#!/usr/bin/env python3
"""Build industry map for entire model universe + lifecycle sync."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Classify all universe symbols into 50 industries")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-yfinance", action="store_true")
    ap.add_argument("--workers", type=int, default=int(os.getenv("INDUSTRY_CLASSIFY_WORKERS", "8")))
    ap.add_argument("--lifecycle", action="store_true", help="Apply corporate action classifications")
    ap.add_argument(
        "--only-unclassified",
        action="store_true",
        help="Re-classify only symbols marked unclassified or low confidence",
    )
    args = ap.parse_args()

    from analytics.industries.classifier import apply_corporate_events_to_industry_map, classify_universe, iter_universe_symbols, load_industry_map
    from analytics.industry_taxonomy import persist_taxonomy

    persist_taxonomy()
    syms = list(iter_universe_symbols())
    if args.only_unclassified:
        mp = load_industry_map()
        syms = [
            s
            for s in syms
            if str((mp.get(s) or {}).get("industry_id") or "unclassified") == "unclassified"
            or float((mp.get(s) or {}).get("confidence") or 0.0) < 0.55
        ]
        print(f"[build-industry] only-unclassified filter → {len(syms)} symbols", flush=True)
    if args.limit > 0:
        syms = syms[: args.limit]
    print(f"[build-industry] classifying {len(syms)} symbols (workers={args.workers})", flush=True)
    classify_universe(
        syms,
        workers=args.workers,
        use_yfinance=not args.no_yfinance,
        persist=True,
    )
    if args.lifecycle:
        applied = apply_corporate_events_to_industry_map()
        print(f"[build-industry] lifecycle rows: {len(applied)}", flush=True)

    from analytics.industries.classifier import load_industry_map

    mp = load_industry_map()
    counts: dict[str, int] = {}
    for row in mp.values():
        iid = str(row.get("industry_id") or "?")
        counts[iid] = counts.get(iid, 0) + 1
    print(f"[build-industry] done — {len(mp)} symbols in map", flush=True)
    for iid, n in sorted(counts.items(), key=lambda x: -x[1])[:15]:
        print(f"  {iid}: {n}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
