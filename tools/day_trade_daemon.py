#!/usr/bin/env python3
"""Yahoo-candle day trading loop — foundational + intermediate setups."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)
_scale = ROOT / "data" / "deploy_scale.env"
if _scale.is_file():
    load_dotenv(_scale, override=True)

from analytics.day_trade_engine import run_universe
from utils import log


def main() -> int:
    try:
        from analytics.sleeve_weights import apply_sleeve_env

        apply_sleeve_env("day_trade")
        log.info("[DAY_TRADE] sleeve=day_trade weights applied")
    except Exception as e:
        log.debug("[DAY_TRADE] sleeve_weights: %s", e)
    if os.getenv("DAY_TRADE_MODE", "").lower() not in ("1", "true", "yes"):
        log.info("[DAY_TRADE] DAY_TRADE_MODE off — exit")
        return 0
    interval = float(os.getenv("DAY_TRADE_POLL_SEC", "12"))
    from analytics.model_scopes import day_trade_tickers

    uni = day_trade_tickers()
    log.info(
        "[DAY_TRADE] Yahoo %s — %d symbols, batch=%s every %.0fs",
        os.getenv("DAY_TRADE_YAHOO_INTERVAL", "1m"),
        len(uni),
        os.getenv("DAY_TRADE_BATCH_SIZE", "8"),
        interval,
    )
    while True:
        try:
            results = run_universe()
            if results.get("action") in ("cash_out", "halted"):
                log.info("[DAY_TRADE] %s", results)
            elif results.get("entries") or results.get("exits"):
                log.info("[DAY_TRADE] cycle %s", {k: v for k, v in results.items() if v})
            top3 = results.get("top3")
            if top3:
                log.info("[DAY_TRADE] top3 %s", [(t.get("ticker"), round(float(t.get("score", 0)), 3)) for t in top3])
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.warning("[DAY_TRADE] cycle error: %s", e)
        time.sleep(interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
