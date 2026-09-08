#!/usr/bin/env python3
"""Flatten all Alpaca positions (safe shutdown before closing the Mac).

going-away / close-lid use FLATTEN_FORCE=true so extended-hours limits actually
cross enough to fill (or at least queue marketable sells), cancel HFT rests,
and retry until the book is flat or the wait budget expires.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
_scale = ROOT / "data" / "deploy_scale.env"
if _scale.is_file():
    load_dotenv(_scale, override=True)


def _force_mode() -> bool:
    return os.getenv("FLATTEN_FORCE", "false").lower() in ("1", "true", "yes")


def _clear_close_cooldowns() -> None:
    d = ROOT / "data" / "ops" / "close_cooldown"
    if not d.is_dir():
        return
    for p in d.glob("*.ts"):
        try:
            p.unlink()
        except OSError:
            pass


def main() -> int:
    from fortress_portfolio import flatten_all_positions

    force = _force_mode()
    if force:
        # going-away: cancel HFT rests, allow marketable exits, no per-symbol cooldown thrash.
        os.environ.setdefault("FLATTEN_SKIP_HFT", "false")
        os.environ["ALPACA_AGGRESSIVE_EXIT"] = "true"
        os.environ["ALPACA_CLOSE_ATTEMPT_COOLDOWN_SEC"] = "0"
        _clear_close_cooldowns()
        print("[flatten] FORCE mode — cancel HFT orders, marketable exits, retry until flat")

    retries = int(os.getenv("FLATTEN_RETRIES", "4" if force else "1"))
    wait_sec = float(os.getenv("FLATTEN_RETRY_WAIT_SEC", "8" if force else "0"))
    r: dict = {}
    for attempt in range(max(1, retries)):
        r = flatten_all_positions(cancel_orders=True, force=force)
        print(json.dumps(r, indent=2))
        still = int(r.get("still_open") or 0)
        queued = int(r.get("queued") or 0)
        if still <= 0:
            print("[flatten] book flat")
            return 0
        if attempt + 1 < retries and wait_sec > 0:
            print(
                f"[flatten] still_open={still} queued={queued} — retry {attempt + 2}/{retries} in {wait_sec:.0f}s"
            )
            time.sleep(wait_sec)
            if force:
                _clear_close_cooldowns()

    if r.get("still_open", 0) > 0 and r.get("queued", 0) >= r.get("still_open", 0):
        print(
            "[flatten] All open positions have pending sell orders — "
            "wait for fill. Run: ./run_all.sh liquidation-status"
        )
        # going-away still pauses; exit 0 so pause proceeds, but warn loudly.
        if force:
            print(
                "[flatten] WARNING: lid-close with open qty — sells are working; "
                "check Alpaca before sleep. liquidation-status for progress."
            )
        return 0
    if r.get("failed", 0) > 0:
        return 1
    if r.get("still_open", 0) > 0 and r.get("queued", 0) == 0 and r.get("closed", 0) == 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
