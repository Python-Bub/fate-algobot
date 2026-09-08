#!/usr/bin/env python3
"""Refresh Monday playbook with family + quality seeds while weekend sim catches up."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ET = ZoneInfo("America/New_York")
PATH = ROOT / "data" / "monday_playbook.json"


def main() -> int:
    cur = json.loads(PATH.read_text(encoding="utf-8")) if PATH.is_file() else {}
    seen = {str(p.get("ticker", "")).upper() for p in cur.get("preorders") or []}
    pre = list(cur.get("preorders") or [])
    seeds = [
        ("CRM", 0.60),
        ("AAPL", 0.57),
        ("JNJ", 0.55),
        ("RTX", 0.68),
        ("MA", 0.72),
        ("COST", 0.58),
        ("ABBV", 0.56),
        ("CAT", 0.55),
        ("UNH", 0.54),
        ("JPM", 0.53),
        ("AVGO", 0.52),
        ("AMD", 0.51),
        ("V", 0.60),
        ("GOOGL", 0.51),
        ("WMT", 0.95),
        ("APP", 0.82),
        ("BLK", 0.57),
    ]
    for t, s in seeds:
        if t in seen:
            continue
        try:
            from intel.near_term_headwinds import assess_near_term_headwind

            if (assess_near_term_headwind(t) or {}).get("block_playbook"):
                continue
        except Exception:
            pass
        seen.add(t)
        pre.append(
            {
                "ticker": t,
                "p_adj": s,
                "score": s,
                "signal": "BUY",
                "source": "monday_seed_quality",
                "rank": len(pre) + 1,
            }
        )
    try:
        from analytics.trade_rotation import select_diversified_buys

        pre = select_diversified_buys(
            pre, 12, score_key="score", ticker_key="ticker", held=cur.get("holdings_skip") or []
        )
    except Exception:
        pre = pre[:12]
    for i, p in enumerate(pre, 1):
        p["rank"] = i
    cur["preorders"] = pre
    cur["built_at_utc"] = datetime.now(timezone.utc).isoformat()
    cur["built_at_et"] = datetime.now(ET).isoformat()
    notes = list(cur.get("notes") or [])
    notes.append("Merged family_forecast + quality seed picks while weekend paper_sim refreshes.")
    cur["notes"] = notes[-8:]
    PATH.write_text(json.dumps(cur, indent=2, default=str), encoding="utf-8")
    print(f"n={len(pre)}")
    for p in pre:
        print(
            f"  #{p['rank']} {p['ticker']:6} score={float(p['score']):.3f} {p.get('source')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
