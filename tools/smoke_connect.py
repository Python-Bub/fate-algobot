#!/usr/bin/env python3
"""GET-only connectivity / import smoke. Never places Alpaca orders.

Usage:
  python tools/smoke_connect.py --offline   # imports + syntax, no HTTP
  python tools/smoke_connect.py             # also GET /v2/account if keys exist
"""
from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Laptop / this process must stay observe even if a parent exported order.
os.environ.setdefault("FATE_ORDER_ROLE", "observe")

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str, *, warn: bool = False) -> None:
    if ok:
        tag = PASS
    elif warn:
        tag = WARN
    else:
        tag = FAIL
    results.append((tag, name, detail))
    print(f"  [{tag}] {name}: {detail}", flush=True)


def _offline_checks() -> None:
    print("\n-- imports --", flush=True)
    for mod in (
        "analytics.asymmetric_loss",
        "analytics.market_session",
        "data_platform.price_fetch_policy",
        "fortress_universe",
        "symbol_aliases",
        "order_role",
        "generate_csvs",
        "live_realtime_multi",
    ):
        try:
            importlib.import_module(mod)
            check(f"import {mod}", True, "ok")
        except Exception as e:
            check(f"import {mod}", False, str(e)[:240])

    print("\n-- symbols --", flush=True)
    try:
        from symbol_aliases import alpaca_equity_symbol, internal_symbol, price_feed_symbol

        check(
            "BRK-B yahoo",
            price_feed_symbol("BRK.B") == "BRK-B" and internal_symbol("BRK.B") == "BRK-B",
            f"feed={price_feed_symbol('BRK.B')}",
        )
        check(
            "BRK-B alpaca",
            alpaca_equity_symbol("BRK-B") == "BRK.B",
            alpaca_equity_symbol("BRK-B"),
        )
    except Exception as e:
        check("BRK-B map", False, str(e)[:240])

    print("\n-- order role --", flush=True)
    try:
        from order_role import order_role, orders_allowed_here

        role = order_role()
        allowed = orders_allowed_here()
        check("FATE_ORDER_ROLE", role in ("observe", "mac", "train", "none", "off") or not allowed, f"role={role}")
        check("orders_blocked_here", allowed is False, f"allowed={allowed}")
    except Exception as e:
        check("order_role", False, str(e)[:240])


def _online_gets() -> None:
    print("\n-- GET only --", flush=True)
    key = os.getenv("ALPACA_API_KEY", "").strip()
    secret = (os.getenv("ALPACA_SECRET_KEY") or os.getenv("ALPACA_API_SECRET") or "").strip()
    if not key or not secret:
        check("alpaca_account", True, "skipped (no keys)", warn=True)
        return
    try:
        import requests

        from alpaca_broker import _normalize_base, _trade_headers

        base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
        r = requests.get(f"{base}/v2/account", headers=_trade_headers(), timeout=8)
        check("alpaca_account GET", r.status_code == 200, f"HTTP {r.status_code}")
    except Exception as e:
        check("alpaca_account GET", False, str(e)[:240], warn=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="GET-only smoke (never posts orders)")
    ap.add_argument("--offline", action="store_true", help="skip HTTP; imports only")
    args = ap.parse_args()
    print("=== smoke-connect ===", flush=True)
    _offline_checks()
    if not args.offline:
        _online_gets()
    fails = sum(1 for t, _, _ in results if t == FAIL)
    print(f"\n{len(results) - fails}/{len(results)} checks ok  fails={fails}", flush=True)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
