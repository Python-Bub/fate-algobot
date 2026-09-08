#!/usr/bin/env python3
"""CLI: scan bottom-percentile universe for recovery + news + AI picks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def main() -> int:
    p = argparse.ArgumentParser(description="Bottom-fisher scan (worst performers → recovery signals)")
    p.add_argument("--max", type=int, default=0, help="Max symbols in bottom slice (0=env default)")
    p.add_argument("--skip-ai", action="store_true", help="Skip LLM review (faster)")
    p.add_argument("--json", action="store_true", help="Print full JSON")
    p.add_argument("--top", type=int, default=15, help="Lines to print in table mode")
    args = p.parse_args()

    from bottom_fisher.scanner import run_bottom_fisher_scan

    out = run_bottom_fisher_scan(
        max_symbols=args.max or None,
        skip_ai=args.skip_ai,
    )
    picks = out.get("picks") or []
    if args.json:
        print(json.dumps(out, indent=2))
        return 0

    print(f"Bottom-fisher: {len(picks)} picks (scanned {out.get('universe_scanned', 0)} in {out.get('elapsed_sec', 0)}s)")
    for r in picks[: args.top]:
        trade = "TRADE" if r.get("trade_eligible") else "watch"
        print(
            f"  {r['ticker']:6s}  {trade:5s}  comp={r.get('composite_score', 0):.3f}  "
            f"rec={r.get('recovery_score', 0):.2f}  news={r.get('catalyst_score', 0):.2f}  "
            f"AI={r.get('ai_grade', '?')} {r.get('ai_verdict', '')}  "
            f"60d={100 * float(r.get('ret_60d', 0)):+.1f}%"
        )
        if r.get("recovery_thesis"):
            print(f"         {str(r['recovery_thesis'])[:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
