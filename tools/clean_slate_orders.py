#!/usr/bin/env python3
"""Cancel every working order and collapse GOOG/GOOGL-style double listings.

Does not flatten the rest of the book — only dual-class duplicates + open orders.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=True)
    load_dotenv(ROOT / "data" / "deploy_scale.env", override=True)
except ImportError:
    pass


def main() -> int:
    from alpaca_broker import (
        cancel_all_open_orders,
        invalidate_rest_cache,
        list_open_orders,
        list_positions,
    )
    from fortress_portfolio import collapse_share_class_duplicates

    invalidate_rest_cache()
    n = cancel_all_open_orders(skip_hft=False)
    print(f"[clean-slate] cancelled ~{n} order(s)")
    invalidate_rest_cache()
    left = list_open_orders()
    print(f"[clean-slate] open orders remaining={len(left)}")
    for o in left[:12]:
        print(
            "  leftover",
            o.get("symbol"),
            o.get("side"),
            o.get("status"),
            o.get("client_order_id"),
        )

    collapsed = collapse_share_class_duplicates(dry_run=False)
    if collapsed:
        for row in collapsed:
            print(
                "[clean-slate] sold duplicate",
                row.get("symbol"),
                "keep",
                row.get("keep"),
                "ok",
                row.get("closed"),
            )
    else:
        print("[clean-slate] no dual-class duplicates to sell")

    invalidate_rest_cache()
    pos = [
        (
            str(p.get("symbol")),
            float(p.get("qty") or 0),
            float(p.get("market_value") or 0),
        )
        for p in (list_positions() or [])
        if abs(float(p.get("qty") or 0)) > 0
    ]
    print(f"[clean-slate] positions={len(pos)}")
    for sym, qty, mv in sorted(pos, key=lambda r: -abs(r[2]))[:25]:
        print(f"  {sym:8s} qty={qty:.4f} mv=${mv:,.0f}")
    return 0 if not left else 1


if __name__ == "__main__":
    raise SystemExit(main())
