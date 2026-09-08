#!/usr/bin/env python3
"""Historical data smoke test for all 50 industry anchor modules."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Industry historical smoke (50 anchors)")
    ap.add_argument("--limit", type=int, default=0, help="Max industries (0=all)")
    ap.add_argument("--json", action="store_true", help="JSON output")
    ap.add_argument("--industry", type=str, default="", help="Internal industry id (marine_shipping)")
    ap.add_argument("--category", type=str, default="", help="Category slug (marine_transportation)")
    args = ap.parse_args()

    if args.category or args.industry:
        from analytics.industries.categories import get_category

        key = args.category.strip() or args.industry.strip()
        rep = get_category(key).historical_smoke()
        if args.json:
            print(json.dumps(rep, indent=2))
        else:
            status = "PASS" if rep.get("ok") else "FAIL"
            print(f"[{status}] {rep.get('industry_id')} anchor={rep.get('anchor')}")
            for c in rep.get("checks") or []:
                print(f"  [{'OK' if c.get('ok') else 'FAIL'}] {c.get('name')}: {c.get('detail')}")
        return 0 if rep.get("ok") else 1

    from analytics.industries.project_wiring import run_all_historical_smoke

    limit = int(args.limit) if args.limit else None
    summary = run_all_historical_smoke(limit=limit)

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"=== industry historical smoke ===")
        print(f"passed {summary['passed']}/{summary['total']} all_ok={summary['all_ok']}")
        for rep in summary.get("results") or []:
            if rep.get("industry_id") == "unclassified":
                continue
            tag = "PASS" if rep.get("ok") else "FAIL"
            anchor = rep.get("anchor", "?")
            print(f"  [{tag}] {rep.get('industry_id'):28s} {anchor}")
            if not rep.get("ok"):
                for c in rep.get("checks") or []:
                    if not c.get("ok"):
                        print(f"         ! {c.get('name')}: {c.get('detail')}")
                if rep.get("error"):
                    print(f"         ! {rep.get('error')}")

    return 0 if summary.get("all_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
