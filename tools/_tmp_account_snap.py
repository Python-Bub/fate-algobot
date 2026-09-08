#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
from alpaca_broker import get_account, list_open_orders, list_positions

a = get_account() or {}
eq = float(a.get("equity") or 0)
last = float(a.get("last_equity") or 0)
cash = float(a.get("cash") or 0)
bp = float(a.get("buying_power") or 0)
pos = list_positions()
gross = sum(abs(float(p.get("market_value") or 0)) for p in pos)
print(f"equity={eq:.2f} last={last:.2f} day_pnl={eq - last:.2f}")
print(
    f"cash={cash:.2f} bp={bp:.2f} gross={gross:.2f} "
    f"deploy={100 * gross / max(eq, 1):.1f}% names={len(pos)} gap=${eq - gross:.0f}"
)
for p in sorted(pos, key=lambda x: -abs(float(x.get("market_value") or 0))):
    sym = str(p.get("symbol"))
    mv = abs(float(p.get("market_value") or 0))
    qty = float(p.get("qty") or 0)
    upl = float(p.get("unrealized_plpc") or 0) * 100
    print(f"  {sym:6} qty={qty:8.3f} mv=${mv:9.2f} {100 * mv / max(eq, 1):5.1f}%  upl={upl:+6.2f}%")
oo = list_open_orders()
buys = [o for o in oo if str(o.get("side", "")).lower() == "buy"]
sells = [o for o in oo if str(o.get("side", "")).lower() == "sell"]
print(f"open_orders={len(oo)} buys={len(buys)} sells={len(sells)}")
for o in buys[:15]:
    print(
        f"  BUY {o.get('symbol')} qty={o.get('qty')} "
        f"{o.get('type')} {o.get('status')} notional={o.get('notional')}"
    )
