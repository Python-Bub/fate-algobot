#!/usr/bin/env python3
"""Seed recent_trades from Alpaca fill history (cooldown rotation)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))


def main() -> int:
    hours = float(os.getenv("TRADE_COOLDOWN_HOURS", "24"))
    k = os.getenv("ALPACA_API_KEY", "").strip()
    s = os.getenv("ALPACA_SECRET_KEY", os.getenv("ALPACA_API_SECRET", "")).strip()
    if not k or not s:
        print("[sync-trades] no Alpaca keys — skip")
        return 0

    import requests

    base = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")
    if base.endswith("/v2"):
        base = base[:-3]
    from datetime import datetime, timedelta, timezone

    after = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    try:
        r = requests.get(
            f"{base}/v2/account/activities/FILL",
            params={"after": after, "direction": "desc"},
            headers={"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s},
            timeout=20,
        )
        r.raise_for_status()
        acts = r.json()
    except Exception as e:
        print(f"[sync-trades] alpaca: {e}")
        return 0

    from analytics.trade_rotation import RECENT_FILE, _load_json, _save_json, record_trade

    doc = _load_json(RECENT_FILE)
    # Keep fortress/day-trade entries; refresh HFT scalps from Alpaca fills.
    keep_sources = frozenset(
        s.strip().lower()
        for s in os.getenv(
            "FORTRESS_COOLDOWN_SOURCES",
            "fortress,day_trade,weekly,paper_sim",
        ).split(",")
        if s.strip()
    )
    kept = [
        t
        for t in (doc.get("trades") or [])
        if str(t.get("source", "")).strip().lower() in keep_sources
    ]
    doc["trades"] = kept
    _save_json(RECENT_FILE, doc)

    n = 0
    for a in acts if isinstance(acts, list) else []:
        side = str(a.get("side", "")).upper()
        if side not in ("BUY", "SELL"):
            continue
        sym = str(a.get("symbol", "")).replace("/", "-").upper()
        if not sym:
            continue
        cid = str(a.get("client_order_id") or a.get("order_id") or "").lower()
        if cid.startswith("mr-") or cid.startswith("obi-") or cid.startswith("earn-"):
            source = "hft"
        else:
            source = "alpaca_sync"
        record_trade(sym, side=side, source=source)
        n += 1
    print(f"[sync-trades] synced {n} fills (cooldown window {hours}h)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
