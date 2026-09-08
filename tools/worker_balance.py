#!/usr/bin/env python3
"""Estimate optimal INTRADAY_GAP_WORKERS vs LSTM_WORKERS to finish around the same time."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _last_progress(log: Path) -> dict | None:
    if not log.is_file():
        return None
    pat = re.compile(r"session (\d+)/(\d+).*left=(\d+).*rate=([\d.]+)/min")
    last = None
    for line in log.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = pat.search(line)
        if m:
            last = {
                "left": int(m.group(3)),
                "rate": float(m.group(4)),
            }
    return last


def _lstm_pending_and_rate() -> tuple[int, float, int]:
    sys.path.insert(0, str(ROOT))
    from tools.train_lstm_heads import _pending_symbols

    pending = len(_pending_symbols())
    wl = int(os.getenv("LSTM_WORKERS", "2"))
    ck = ROOT / "data" / "lstm_train_checkpoint.json"
    done_n = 0
    if ck.is_file():
        try:
            done_n = len(json.loads(ck.read_text(encoding="utf-8")).get("done", []))
        except Exception:
            pass
    log = ROOT / "logs/train-lstm_latest.log"
    elapsed_h = 0.5
    if log.is_file():
        first = None
        for line in log.read_text(encoding="utf-8", errors="ignore").splitlines()[:5]:
            if "[LSTM-BATCH]" in line:
                first = line
                break
        # use log age since batch start (file ctime as proxy)
        elapsed_h = max((time.time() - log.stat().st_ctime) / 3600.0, 0.25)
    # saved/min (total workers) — checkpoint updates every 25 symbols; default ~1.2/min @ 2w
    rate = float(os.getenv("LSTM_RATE_GUESS", "1.2"))
    if done_n >= 10 and elapsed_h > 0.1:
        rate = max(done_n / max(elapsed_h * 60.0, 1.0), 0.2)
    return pending, rate, wl


def main() -> int:
    cores = int(os.getenv("TRAIN_CPU_CORES", str(os.cpu_count() or 8)))
    reserve = int(os.getenv("TRAIN_CPU_RESERVE", "1"))
    budget = max(2, cores - reserve)

    intra = _last_progress(ROOT / "logs/train-intraday_latest.log")
    if not intra:
        print("No intraday [PROGRESS] in logs/train-intraday_latest.log")
        return 1

    lstm_left, rl, wl = _lstm_pending_and_rate()
    if lstm_left <= 0:
        print("LSTM queue empty — only intraday gap-fill remains.")
        print(f"recommended: INTRADAY_GAP_WORKERS={budget}  LSTM_WORKERS=0")
        return 0

    wi = int(os.getenv("INTRADAY_GAP_WORKERS", "6"))
    ri = max(intra["rate"], 0.1)
    ai = ri / max(wi, 1)
    al = rl / max(wl, 1)

    best = (4, 3, 1e9)
    for w_i in range(2, budget):
        w_l = budget - w_i
        if w_l < 1:
            continue
        ti = intra["left"] / max(ai * w_i, 1e-6)
        tl = lstm_left / max(al * w_l, 1e-6)
        finish = max(ti, tl)
        if finish < best[2]:
            best = (w_i, w_l, finish)

    w_i, w_l, finish_h = best
    ti_h = intra["left"] / max(ai * w_i, 1e-6) / 60.0
    tl_h = lstm_left / max(al * w_l, 1e-6) / 60.0

    print(f"cpu_cores={cores}  train_budget={budget}  (reserve={reserve} for OS/HFT/fortress)")
    print(f"intraday: left={intra['left']}  now {ri:.2f}/min @ {wi}w  (~{intra['left']/ri/60:.1f}h)")
    print(f"lstm:     left={lstm_left}  now ~{rl:.2f}/min @ {wl}w  (~{lstm_left/rl/60:.1f}h)")
    print(f"recommended: INTRADAY_GAP_WORKERS={w_i}  LSTM_WORKERS={w_l}")
    print(f"  → intraday ~{ti_h:.1f}h   lstm ~{tl_h:.1f}h   (sync ~{finish_h/60:.1f}h)")
    print("daily train: stop it (430 junk symbols left) — frees 8 workers you do not need")
    print("paper stack (obi/fortress/weekly): keep running; they share the reserved core")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
