#!/usr/bin/env python3
"""Autonomous HFT news daemon — AI good/bad intel on tradeable tickers only."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

LOG = ROOT / "logs" / "hft_news_watch.log"
WATCHDOG_LOG = ROOT / "data" / "watchdog_log.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str, *, ok: bool = True) -> None:
    line = f"[{_now()}] {msg}\n"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="", flush=True)
    try:
        with WATCHDOG_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": _now(), "action": "hft_news_watch", "detail": msg, "ok": ok}) + "\n")
    except Exception:
        pass


def _intel_window() -> bool:
    try:
        from analytics.market_session import intel_window_open

        return intel_window_open()[0]
    except Exception:
        return True


def run_once() -> int:
    from tools.hft_news_refresh import refresh

    data = refresh(force=True)
    boosts = data.get("boosts") or {}
    rows = data.get("tickers") or {}
    n_block = sum(1 for v in rows.values() if not v.get("allow_long"))
    n_tilt = sum(1 for v in rows.values() if abs(float(v.get("tilt") or 0)) > 0.001)
    _log(f"refreshed {len(rows)} tickers — blocked={n_block} tilted={n_tilt}")
    return 0


def main() -> int:
    once = "--once" in sys.argv
    poll = int(os.getenv("HFT_NEWS_WATCH_POLL_SEC", "300"))
    off_poll = int(os.getenv("HFT_NEWS_WATCH_OFF_POLL_SEC", "900"))

    _log(f"started poll={poll}s off_poll={off_poll}s (tradeable tickers + LLM good/bad)")
    if once:
        return run_once()

    while True:
        try:
            if _intel_window():
                run_once()
                time.sleep(poll)
            else:
                _log("outside intel window — sleeping")
                time.sleep(off_poll)
        except Exception as e:
            _log(f"error: {e}", ok=False)
            time.sleep(min(poll, 120))


if __name__ == "__main__":
    raise SystemExit(main())
