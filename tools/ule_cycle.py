#!/usr/bin/env python3
"""Ultimate Learning Engine cycle — history credit → codegen → pattern scan.

Examples:
  ./run_all.sh ule
  ./run_all.sh ule --hist-limit 200 --no-codegen
  ./run_all.sh ule-watch
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

_scale = ROOT / "data" / "deploy_scale.env"
if _scale.is_file():
    try:
        from dotenv import load_dotenv as _ld

        _ld(_scale, override=True)
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Ultimate Learning Engine cycle")
    ap.add_argument("--hist-limit", type=int, default=0, help="Paper-sim rows to credit (0=env)")
    ap.add_argument("--no-codegen", action="store_true", help="Skip subtle-tie codegen")
    ap.add_argument("--no-scan", action="store_true", help="Skip hidden pattern scan")
    ap.add_argument("--json", action="store_true", help="Print JSON only")
    ap.add_argument("--status", action="store_true", help="Print skill/weights only")
    args = ap.parse_args()

    from analytics.ultimate_learning_engine import enabled, run_cycle, skill_weights, _load_state

    if args.status:
        st = _load_state()
        out = {
            "enabled": enabled(),
            "skill": st.get("skill"),
            "weights": skill_weights(st),
            "n_updates": st.get("n_updates"),
            "n_cycles": st.get("n_cycles"),
            "last_cycle": st.get("last_cycle"),
        }
        print(json.dumps(out, indent=2, default=float))
        return 0

    hist = args.hist_limit if args.hist_limit > 0 else None
    summary = run_cycle(
        hist_limit=hist,
        do_codegen=False if args.no_codegen else None,
        do_pattern_scan=False if args.no_scan else None,
    )
    if args.json:
        print(json.dumps(summary, indent=2, default=float))
    else:
        print(
            f"[ULE] ok={summary.get('ok')} learned={(summary.get('history') or {}).get('learned')} "
            f"elapsed={summary.get('elapsed_sec'):.1f}s"
        )
        w = summary.get("weights") or {}
        if w:
            top = sorted(w.items(), key=lambda x: -x[1])[:4]
            print("[ULE] weights:", ", ".join(f"{k}={v:.3f}" for k, v in top))
        cg = summary.get("codegen") or {}
        if cg.get("written") is not None:
            print(f"[ULE] codegen written={cg.get('written')}")
        if cg.get("error"):
            print(f"[ULE] codegen err: {cg['error']}")
        ps = summary.get("pattern_scan") or {}
        if ps.get("error"):
            print(f"[ULE] scan err: {ps['error']}")
        elif ps:
            print(f"[ULE] scan keys={list(ps.keys())[:6]}")
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
