#!/usr/bin/env python3
"""Lock the stack for unattended paper go-live. Does NOT switch Alpaca to funded live."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)
_scale = ROOT / "data" / "deploy_scale.env"
if _scale.is_file():
    load_dotenv(_scale, override=True)

OUT = ROOT / "data" / "ops" / "go_live_now.json"


def main() -> int:
    from analytics.robot_core import write_status
    from tools.go_autonomous import apply_go_live_policy

    base = (os.getenv("ALPACA_BASE_URL") or "https://paper-api.alpaca.markets").rstrip("/")
    paper = "paper-api.alpaca.markets" in base or os.getenv("ALPACA_PAPER", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    policy = apply_go_live_policy()
    core = write_status()
    acct: dict = {}
    try:
        from alpaca_broker import get_account

        raw = get_account() or {}
        acct = {
            "equity": raw.get("equity") or raw.get("last_equity"),
            "buying_power": raw.get("buying_power"),
            "status": raw.get("status"),
            "pattern_day_trader": raw.get("pattern_day_trader"),
            "trading_blocked": raw.get("trading_blocked"),
        }
    except Exception as e:
        acct = {"error": str(e)[:160]}

    doc = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "alpaca_paper_fully_live",
        "funded_live": False,
        "alpaca_base": base,
        "paper": paper,
        "policy": policy,
        "johnston_missing": core.get("missing_buckets"),
        "core_families_missing": core.get("core_families_missing"),
        "account": acct,
        "note": "Orders route to Alpaca paper. Funded live requires ALPACA_BASE_URL=https://api.alpaca.markets and explicit operator confirm.",
        "do_not": ["flatten overnight holds", "shrink universe", "disable HFT/day-trade/fortress"],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(json.dumps({k: doc[k] for k in ("mode", "paper", "alpaca_base", "account", "johnston_missing")}, indent=2))
    if not paper:
        print("[go-live-now] REFUSE: base URL is not paper — will not flip to funded live from this script", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
