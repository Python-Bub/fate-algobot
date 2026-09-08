"""
Diagnose Alpaca credentials end-to-end. Tells you exactly which endpoint your keys work for.

Run:
    python FATE_AlgoBot.py alpaca-check

Reads:  ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL, ALPACA_DATA_URL
"""

from __future__ import annotations

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()


def _headers() -> dict:
    return {
        "APCA-API-KEY-ID": os.getenv("ALPACA_API_KEY", "").strip(),
        "APCA-API-SECRET-KEY": os.getenv("ALPACA_SECRET_KEY", "").strip(),
    }


def _normalize_base(url: str) -> str:
    base = (url or "").strip().rstrip("/")
    if base.endswith("/v2"):
        base = base[:-3]
    return base


def diagnose() -> int:
    k = os.getenv("ALPACA_API_KEY", "").strip()
    s = os.getenv("ALPACA_SECRET_KEY", "").strip()
    base = _normalize_base(os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
    data = _normalize_base(os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets"))

    print("== Alpaca diagnostics ==")
    print(f"  API key prefix : {k[:6]+'...' if k else '(missing)'}")
    print(f"  Secret present : {'yes' if s else 'NO'}")
    print(f"  Trading base   : {base}")
    print(f"  Market data    : {data}")
    print()

    rc = 0
    try:
        r = requests.get(f"{base}/v2/account", headers=_headers(), timeout=20)
        print(f"  Trading /v2/account  -> HTTP {r.status_code}")
        if r.status_code == 200:
            acc = r.json()
            print(f"    account_status   = {acc.get('status')}")
            print(f"    equity           = ${acc.get('equity')}")
            bp = acc.get("buying_power")
            print(f"    buying_power     = ${bp}  (intraday margin — use this field)")
            # Deprecated July 6, 2026 — shown for migration only
            legacy = acc.get("daytrading_buying_power")
            if legacy is not None and str(legacy) != str(bp):
                print(f"    daytrading_bp    = ${legacy}  (deprecated, mirrors buying_power)")
            if acc.get("pattern_day_trader") is not None:
                print(f"    pattern_day_tr.  = {acc.get('pattern_day_trader')}  (deprecated, always false)")
        else:
            print(f"    body: {r.text[:300]}")
            print("    >> Trading orders will fail with these keys. "
                  "Make sure you generated a *Paper Trading* key on alpaca.markets "
                  "and put it in BOTH ALPACA_API_KEY + ALPACA_SECRET_KEY.")
            rc = 2
    except Exception as e:
        print(f"  Trading /v2/account  -> EXCEPTION {e}")
        rc = 2

    print()
    try:
        r = requests.get(
            f"{data}/v2/stocks/AAPL/bars",
            params={"timeframe": "1Day", "start": "2025-01-01", "limit": 5, "adjustment": "all"},
            headers=_headers(),
            timeout=20,
        )
        print(f"  Market data bars     -> HTTP {r.status_code}")
        if r.status_code == 200:
            n = len(r.json().get("bars") or [])
            print(f"    received {n} bars for AAPL — Alpaca Market Data subscription works.")
        else:
            print(f"    body: {r.text[:300]}")
            print("    >> Most paper/live keys do NOT include Market Data. "
                  "Either subscribe to Alpaca Market Data, or run with "
                  "PRICE_DATA_SOURCE=yfinance (default fallback).")
    except Exception as e:
        print(f"  Market data bars     -> EXCEPTION {e}")

    return rc


if __name__ == "__main__":
    sys.exit(diagnose())
