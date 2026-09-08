#!/usr/bin/env python3
"""Watch fortress + subsecond execution — orders, fills, JP-candle / MR fires."""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=True)
except ImportError:
    pass


def _alpaca_orders_since(minutes: int) -> list[dict]:
    import requests

    key = os.getenv("ALPACA_API_KEY", "")
    sec = os.getenv("ALPACA_SECRET_KEY", "") or os.getenv("ALPACA_API_SECRET", "")
    base = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")
    if not key or not sec:
        return []
    after = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")
    url = f"{base}/orders" if base.endswith("/v2") else f"{base}/v2/orders"
    r = requests.get(
        url,
        params={"status": "all", "limit": 50, "direction": "desc", "after": after},
        headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec},
        timeout=20,
    )
    return r.json() if r.ok and isinstance(r.json(), list) else []


def _tail_matches(path: Path, patterns: tuple[str, ...], n: int = 400) -> list[str]:
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    hits = [ln for ln in lines[-n:] if any(p in ln for p in patterns)]
    return hits[-8:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=8)
    ap.add_argument("--interval", type=int, default=20)
    ap.add_argument("--rounds", type=int, default=12)
    args = ap.parse_args()

    log_dir = ROOT / "logs"
    intraday = log_dir / "intraday_latest.log"
    subsec = log_dir / "subsecond-obi_latest.log"
    seen_orders: set[str] = set()

    forever = args.rounds <= 0
    label = "forever" if forever else f"{args.rounds} rounds"
    print(f"=== execution monitor ({label} × {args.interval}s) ===", flush=True)
    i = 0
    orders: list[dict] = []
    target_eq = float(os.getenv("SESSION_EQUITY_TARGET_USD", "0") or "0")

    while forever or i < args.rounds:
        ts = datetime.now(timezone.utc).isoformat()
        try:
            from alpaca_broker import get_account, list_positions

            acct = get_account() or {}
            eq = float(acct.get("equity") or 0)
            upl = 0.0
            legs: list[str] = []
            for p in list_positions():
                u = float(p.get("unrealized_pl") or 0)
                upl += u
                legs.append(f"{p.get('symbol')}:{p.get('qty')}({u:+.0f})")
            if eq > 0:
                msg = f"[{ts}] equity ${eq:,.2f} carry_upl ${upl:+,.2f}"
                if target_eq > 0:
                    gap = target_eq - eq
                    msg += f" | target ${target_eq:,.0f} ({gap:+,.0f})"
                if legs:
                    msg += " | " + " ".join(legs[:6])
                print(msg, flush=True)
        except Exception:
            pass
        try:
            orders = _alpaca_orders_since(args.minutes)
        except Exception as e:
            print(f"[{ts}] alpaca orders unavailable: {e}", flush=True)
            orders = []
        new = [o for o in orders if str(o.get("id")) not in seen_orders]
        for o in new:
            seen_orders.add(str(o.get("id")))
        if new:
            print(f"\n[{ts}] NEW ORDERS ({len(new)})", flush=True)
            for o in new[:10]:
                print(
                    f"  {o.get('submitted_at','')[:19]} {o.get('symbol')} {o.get('side')} "
                    f"{o.get('status')} qty={o.get('qty')} filled={o.get('filled_qty')}",
                    flush=True,
                )

        fh = _tail_matches(
            intraday,
            ("BUY#", "DCA#", "compliance block", "jp-candle", "place_smart", "order", "skip BUY"),
        )
        sh = _tail_matches(
            subsec,
            (
                "FIRE",
                "FLATTEN",
                "FLATTEN-CLOSE",
                "mr_fire",
                "mr_flatten",
                "entry-expired",
                "exit-unfilled",
                "stale-order-sweep",
                "skip-entry",
                "block-long",
                "NEWS",
                "OBI/MR",
                "place",
                "TAKE-PROFIT",
            ),
        )
        if fh or new:
            print(f"[{ts}] fortress:", flush=True)
            for ln in fh:
                print(f"  {ln[-160:]}", flush=True)
        if sh:
            print(f"[{ts}] subsecond:", flush=True)
            for ln in sh:
                print(f"  {ln[-160:]}", flush=True)
        if not new and not fh and not sh and i == 0:
            print(f"[{ts}] waiting for activity…", flush=True)
        i += 1
        time.sleep(args.interval)

    print("\n=== summary ===", flush=True)
    print(f"  orders seen (last {args.minutes}m): {len(orders)}", flush=True)
    filled = sum(1 for o in orders if str(o.get("status")) in ("filled", "partially_filled"))
    print(f"  filled/partial: {filled}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
