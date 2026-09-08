#!/usr/bin/env python3
"""Run contextual pre-trade risk screen on one or more tickers."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Pre-trade contextual risk filter")
    ap.add_argument("tickers", nargs="+", help="Symbols to screen (e.g. ORCL TMHC PLTR AVGO)")
    ap.add_argument("--json", action="store_true", help="Emit JSON array")
    ap.add_argument("--hold-days", type=int, default=int(os.getenv("HOLD_DAYS_DEFAULT", "5")))
    args = ap.parse_args()

    from intel.algo_risk_filter import AlgoRiskFilter

    filt = AlgoRiskFilter()
    results = [filt.screen_ticker(t.upper(), hold_days=args.hold_days) for t in args.tickers]

    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        print("=== PRE-TRADE CONTEXTUAL RISK FILTER ===")
        for res in results:
            sym = res["ticker"]
            status = "APPROVED" if res["approved"] else "REJECT"
            mark = "OK" if res["approved"] else "BLOCK"
            print(f"[{sym}] {status} ({mark}) — {res['reason']}")
            if res.get("rule"):
                print(f"         rule={res['rule']}")
            dte = res.get("days_to_earnings")
            if dte is not None:
                print(f"         days_to_earnings={dte}")
            if res.get("hold_days") != res.get("requested_hold_days"):
                print(
                    f"         effective_hold_days={res.get('hold_days')} "
                    f"(requested {res.get('requested_hold_days')})"
                )
            for w in res.get("warnings") or []:
                print(f"         ⚠️  {w}")
            tc = res.get("trade_constraints") or {}
            if tc.get("entry_order_type") == "limit":
                print(
                    f"         LIMIT ENTRY ${tc.get('limit_low')}-${tc.get('limit_high')} "
                    f"@ {tc.get('limit_price')}"
                )
            if tc.get("sympathy_trap"):
                print(
                    f"         SYMPATHY TRAP: peer={tc.get('sympathy_peer')} "
                    f"max_hold={tc.get('max_hold_days')}d TP={float(tc.get('take_profit_pct', 0))*100:.1f}% "
                    f"exit_before={tc.get('force_exit_before_date')}"
                )
            for chk in res.get("checks") or []:
                if chk.get("blocked"):
                    print(f"         ! {chk['rule']}: {chk['reason']}")

    rejected = sum(1 for r in results if not r["approved"])
    return 1 if rejected and len(results) == 1 else 0


if __name__ == "__main__":
    raise SystemExit(main())
