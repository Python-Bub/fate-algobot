#!/usr/bin/env python3
"""Re-apply asymmetric filter to the latest paper_sim report (no rescan)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def main() -> int:
    rep_dir = ROOT / "reports"
    files = sorted(rep_dir.glob("paper_sim_*.json"), reverse=True)
    if not files:
        print("[repatch-asym] no report found")
        return 1
    path = files[0]
    report = json.loads(path.read_text(encoding="utf-8"))
    rows = list(report.get("rows") or [])
    if not rows:
        print(f"[repatch-asym] {path.name} has no rows")
        return 1

    from analytics.asymmetric_meta_filter import asymmetric_decision, long_threshold
    from analytics.execution_confidence import min_execution_confidence

    min_exec = min_execution_confidence()
    long_thr = long_threshold()
    print(f"[repatch-asym] {path.name}  LONG_DECISION_THRESHOLD={long_thr:.2f}")

    for row in rows:
        if row.get("skipped"):
            continue
        p_up = float(row.get("p_up") or 0.5)
        exec_conf = float(row.get("execution_confidence") or p_up)
        asym = asymmetric_decision(
            p_up,
            exec_conf,
            min_exec,
            p_short_model=row.get("p_short_model"),
            p_long_model=row.get("p_long_model"),
        )
        row["asym_action"] = str(asym.action)
        row["asym_rationale"] = str(asym.rationale)

    tradeable = [r for r in rows if not r.get("skipped")]
    long_zone = [r for r in tradeable if r.get("asym_action") == "LONG"]
    short_zone = [r for r in tradeable if r.get("asym_action") == "SHORT"]
    no_trade = [r for r in tradeable if r.get("asym_action") == "NO_TRADE"]
    n = max(len(tradeable), 1)
    report["asym_filter_metrics"] = {
        "n_scored": len(tradeable),
        "n_asym_long_zone": len(long_zone),
        "n_asym_short_zone": len(short_zone),
        "n_asym_no_trade": len(no_trade),
        "yield_long_zone_frac": round(len(long_zone) / n, 4),
        "yield_short_zone_frac": round(len(short_zone) / n, 4),
        "yield_no_trade_frac": round(len(no_trade) / n, 4),
        "long_threshold": long_thr,
    }
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"[repatch-asym] long_zone={len(long_zone)} short={len(short_zone)} "
        f"no_trade={len(no_trade)}  →  {path.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
