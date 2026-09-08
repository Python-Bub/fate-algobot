#!/usr/bin/env python3
"""
Always-on paper loop: scores configured symbols on an interval.
Run under tmux/systemd on a VPS for 24/7 operation; keep IBKR/paper APIs separate.
"""
import os
import time
import traceback

from config import TRAIN_TICKERS
from main import run_bot
from utils import log


def _symbols():
    if os.getenv("DAEMON_USE_UNIVERSE", "false").lower() in ("1", "true", "yes"):
        from universe_provider import load_universe_with_cap

        cap = os.getenv("DAEMON_UNIVERSE_CAP")
        return load_universe_with_cap(max_symbols=int(cap) if cap else 500, refresh=False)
    return TRAIN_TICKERS


def main():
    interval = int(os.getenv("DAEMON_INTERVAL_SEC", "300"))
    syms = _symbols()
    log.info("[DAEMON] Starting with interval=%ss symbols=%s", interval, len(syms))
    while True:
        for t in syms:
            try:
                run_bot(t)
            except Exception:
                log.error("[DAEMON] %s failed:\n%s", t, traceback.format_exc())
        time.sleep(interval)


if __name__ == "__main__":
    main()
