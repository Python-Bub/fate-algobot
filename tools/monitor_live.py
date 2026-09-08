#!/usr/bin/env python3
"""Live ops monitor: training gaps, health, Alpaca P&L, recent trades."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

LOG = ROOT / "logs" / "monitor_live.log"


def _log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _snapshot() -> dict:
    from fortress_universe import load_top100_symbols
    from model_trainer import training_saved_model
    from tools.retrain_weak_models import find_weak_symbols

    top = load_top100_symbols()
    missing = [s for s in top if not training_saved_model(s)]
    weak = find_weak_symbols(min_top20=0.52, min_meta=0.48, top100_only=True)

    acc = {}
    try:
        from alpaca_broker import get_account

        acc = get_account() or {}
    except Exception as e:
        acc = {"error": str(e)}

    equity = float(acc.get("equity") or 0)
    last_eq = float(acc.get("last_equity") or equity)
    day_pl = equity - last_eq

    trades_n = 0
    rt = ROOT / "data" / "recent_trades.json"
    if rt.is_file():
        try:
            trades_n = len(json.loads(rt.read_text(encoding="utf-8")).get("trades", []))
        except Exception:
            pass

    pids = {}
    for name in ("intraday", "subsecond-obi", "weekly", "paper-awake", "hft-rotator"):
        pf = ROOT / ".pids" / f"{name}.pid"
        if pf.is_file():
            try:
                pid = int(pf.read_text(encoding="utf-8").strip())
                os.kill(pid, 0)
                pids[name] = pid
            except (OSError, ValueError):
                pids[name] = None
        else:
            pids[name] = None

    return {
        "top100_missing": missing,
        "weak": list(weak) if weak else [],
        "equity": equity,
        "day_pl": day_pl,
        "buying_power": float(acc.get("buying_power") or 0),
        "trades_synced": trades_n,
        "daemons": pids,
    }


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=60.0)
    ap.add_argument("--rounds", type=int, default=10, help="0 = run until interrupted")
    args = ap.parse_args()

    rounds = 0
    while args.rounds == 0 or rounds < args.rounds:
        snap = _snapshot()
        _log(
            "[monitor] "
            f"top100_missing={snap['top100_missing'] or 'none'} "
            f"weak={snap['weak'] or 'none'} "
            f"equity=${snap['equity']:,.2f} day_pl=${snap['day_pl']:+,.2f} "
            f"trades={snap['trades_synced']} "
            f"daemons={ {k: v for k, v in snap['daemons'].items() if v} }"
        )
        if not snap["top100_missing"] and not snap["weak"]:
            _log("[monitor] training clear — stack ready for full universe")
        rounds += 1
        if args.rounds and rounds >= args.rounds:
            break
        time.sleep(max(5.0, args.interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
