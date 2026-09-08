#!/usr/bin/env python3
"""Scan / watch for hidden pattern anomalies in historical prices.

Examples:
  ./run_all.sh pattern-anomaly
  ./run_all.sh pattern-anomaly --limit 40
  ./run_all.sh pattern-anomaly-watch   # daemon via daemon_loop
"""

from __future__ import annotations

import argparse
import json
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

# Scale overrides last-win
_scale = ROOT / "data" / "deploy_scale.env"
if _scale.is_file():
    try:
        from dotenv import load_dotenv as _ld

        _ld(_scale, override=True)
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Hidden pattern anomaly scan")
    ap.add_argument("--limit", type=int, default=0, help="Max symbols (0=env default)")
    ap.add_argument("--ticker", action="append", default=[], help="Extra ticker(s)")
    ap.add_argument("--json", action="store_true", help="Print JSON only")
    ap.add_argument("--once", action="store_true", help="Alias for one-shot (default)")
    ap.add_argument(
        "--imbalances-only",
        action="store_true",
        help="Only scan cross-listing / regional price imbalances",
    )
    ap.add_argument(
        "--discover-only",
        action="store_true",
        help="Only discover subtle ties and write detector code (no full anomaly scan)",
    )
    args = ap.parse_args()

    from analytics.hidden_pattern_anomaly import (
        analyze_symbol,
        default_universe,
        run_scan_cycle,
        save_hits,
        scan_universe,
    )
    from utils import log

    if args.discover_only:
        from analytics.pattern_code_evolver import discover_and_emit

        rep = discover_and_emit()
        print(json.dumps(rep, indent=2))
        return 0

    if args.imbalances_only:
        from analytics.market_imbalance import run_imbalance_cycle

        summary = run_imbalance_cycle()
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(f"imbalance_hits={summary.get('imbalance_hits')} → {summary.get('imbalance_path')}")
            for row in summary.get("imbalances") or []:
                print(
                    f"  {row.get('symbol'):6} vs {row.get('peer'):12} "
                    f"gap={100 * float(row.get('gap_pct') or 0):+.2f}% "
                    f"z={float(row.get('z') or 0):+.2f} score={float(row.get('score') or 0):.3f} "
                    f"dir={int(row.get('direction') or 0):+d}"
                )
        return 0

    limit = args.limit or None
    if args.ticker:
        hits = scan_universe([t.upper() for t in args.ticker], limit=limit or 50)
        # Also merge a small default universe so cache stays useful for fortress
        if not args.json:
            extra = scan_universe(default_universe(int(limit or 40)), limit=int(limit or 40))
            by = {h.symbol: h for h in extra}
            for h in hits:
                by[h.symbol] = h
            hits = sorted(by.values(), key=lambda x: x.score, reverse=True)
        path = save_hits(hits)
        summary = {
            "scanned": len(args.ticker),
            "hits": len(hits),
            "path": str(path),
            "top": [h.to_dict() for h in hits[:12]],
        }
    else:
        log.info("[HIDDEN_ANOMALY] scan cycle start (patterns + regional imbalances)")
        summary = run_scan_cycle(limit=limit)
        log.info(
            "[HIDDEN_ANOMALY] scanned=%s hits=%s imbalances=%s → %s",
            summary.get("scanned"),
            summary.get("hits"),
            summary.get("imbalance_hits"),
            summary.get("path"),
        )

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"scanned={summary.get('scanned')} hits={summary.get('hits')}")
        cg = summary.get("codegen") or {}
        if cg:
            print(
                f"codegen written={cg.get('written')} candidates={cg.get('candidates')} "
                f"files={cg.get('files')}"
            )
        if summary.get("imbalance_hits") is not None:
            print(f"regional_imbalances={summary.get('imbalance_hits')} → {summary.get('imbalance_path')}")
        print(f"wrote {summary.get('path')}")
        for row in summary.get("top") or []:
            reasons = "; ".join(row.get("reasons") or [])[:120]
            print(
                f"  {row.get('symbol'):6} score={float(row.get('score') or 0):.3f} "
                f"dir={int(row.get('direction') or 0):+d}  {reasons}"
            )
        for row in (summary.get("imbalances") or [])[:8]:
            print(
                f"  IMB {row.get('symbol'):6} vs {str(row.get('peer')):12} "
                f"gap={100 * float(row.get('gap_pct') or 0):+.2f}% z={float(row.get('z') or 0):+.2f}"
            )
        # Single-ticker deep print
        for t in args.ticker[:3]:
            hit = analyze_symbol(t.upper())
            if hit:
                print(f"\nDetail {hit.symbol}: {hit.to_dict()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
