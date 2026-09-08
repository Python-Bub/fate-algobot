#!/usr/bin/env python3
"""Place limit buys from data/gtg_buy_queue.json when margin frees (after gtg sells fill)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

import requests

from alpaca_broker import (
    _extended_hours_enabled,
    _limit_price_str,
    _normalize_base,
    _round_limit_price,
    _route_symbol,
    _tif,
    _trade_headers,
    get_mid_price,
)


def main() -> int:
    cfg_path = ROOT / "data" / "gtg_buy_queue.json"
    if not cfg_path.is_file():
        print("no queue file")
        return 0
    cfg = json.loads(cfg_path.read_text())
    symbols = cfg.get("symbols") or []
    notional = float(cfg.get("notional_each_usd", 4000))
    slip = float(cfg.get("slip_bps", 12)) / 10000.0
    base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
    placed = []
    for sym in symbols:
        from alpaca_broker import get_quote_bid_ask, _limit_price_str, _round_limit_price, _route_symbol, _tif, _trade_headers, _extended_hours_enabled
        from analytics.limit_pricing import entry_limit_px

        q = get_quote_bid_ask(sym)
        if not q:
            print(f"skip {sym}: no quote")
            continue
        bid, ask = q
        lp = entry_limit_px("buy", bid, ask)
        if not lp or lp <= 0:
            print(f"skip {sym}: bad limit")
            continue
        lp = _round_limit_price(lp)
        qty = notional / lp
        payload = {
            "symbol": _route_symbol(sym),
            "qty": f"{qty:.8f}".rstrip("0").rstrip(".") or "0",
            "side": "buy",
            "type": "limit",
            "limit_price": _limit_price_str(lp),
            "time_in_force": _tif(sym),
        }
        if _extended_hours_enabled(sym):
            payload["extended_hours"] = True
        r = requests.post(f"{base}/v2/orders", json=payload, headers=_trade_headers(), timeout=30)
        if r.ok:
            placed.append(sym)
            print(f"OK buy {sym} ~${notional:.0f} @ {lp}")
        else:
            print(f"FAIL buy {sym}: {r.text[:180]}")
    if placed and len(placed) == len(symbols):
        cfg_path.unlink(missing_ok=True)
    return 0 if placed else 1


if __name__ == "__main__":
    raise SystemExit(main())
