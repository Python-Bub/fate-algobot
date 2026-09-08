#!/usr/bin/env python3
"""Show Alpaca liquidation state — avoids duplicate 'insufficient qty' UI errors."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def main() -> int:
    from alpaca_broker import (
        list_open_orders,
        list_positions,
        open_sell_orders,
        pending_close_order,
        position_qty_available,
    )
    from analytics.market_session import next_session_open, session_summary

    positions = list_positions()
    sells = open_sell_orders()
    sess = session_summary()
    nxt = next_session_open()

    rows: list[dict] = []
    queued = 0
    actionable = 0
    for p in positions:
        sym = str(p.get("symbol", "")).replace("/", "-").upper()
        qty = abs(float(p.get("qty") or 0))
        if qty <= 0:
            continue
        avail = position_qty_available(sym)
        pend = pending_close_order(sym)
        sym_sells = [o for o in sells if str(o.get("symbol", "")).upper() == sym.replace(".", "")]
        state = "queued" if pend else ("locked" if (avail or 0) <= 1e-8 and sym_sells else "open")
        if state == "queued":
            queued += 1
        else:
            actionable += 1
        rows.append(
            {
                "symbol": sym,
                "qty": qty,
                "qty_available": avail,
                "state": state,
                "pending_order": pend.get("id") if pend else None,
                "sell_orders": len(sym_sells),
            }
        )

    out = {
        "positions": len(rows),
        "queued_for_close": queued,
        "needs_action": actionable,
        "open_sell_orders": len(sells),
        "session": sess.get("session"),
        "next_open_et": nxt.isoformat() if nxt else None,
        "rows": rows,
    }

    if not rows:
        print("[liquidation] Flat — no open positions.")
        return 0

    print(f"[liquidation] {len(rows)} position(s): {queued} queued to sell, {actionable} need action")
    if queued and actionable == 0:
        print(
            "[liquidation] OK — full market sells are already queued. "
            "Do NOT click Liquidate in the Alpaca UI (available qty is 0 until RTH fill)."
        )
        if nxt:
            print(f"[liquidation] Expected fill window: after {nxt.strftime('%Y-%m-%d %H:%M')} ET")
    for row in rows:
        tag = row["state"].upper()
        print(
            f"  {row['symbol']:6s} qty={row['qty']:.4f} avail={row['qty_available']}  [{tag}]"
            + (f" order={str(row['pending_order'])[:8]}" if row["pending_order"] else "")
        )

    if "--json" in sys.argv:
        print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
