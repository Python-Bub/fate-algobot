"""Walk-forward event-outcome learner on historical prints — all tickers.

  ./venv/bin/python tools/event_learn_train.py --once
  ./venv/bin/python tools/event_learn_train.py --once --max-symbols 80

Does not forecast unpublished results. Fits public-clock features → next 1d
gap on every earnings date in history, redesigns (drops hurting features)
until out-of-sample IC beats a naive |move| baseline, then writes
data/intel/event_learn_state.json for live rank / ULE / online SGD.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    _scale = ROOT / "data" / "deploy_scale.env"
    if _scale.is_file():
        load_dotenv(_scale, override=True)
except Exception:
    pass


def _universe(max_symbols: int) -> list[str]:
    out: list[str] = []
    try:
        from fortress_universe import load_top100_symbols, load_fortress_scan_list

        out.extend(load_top100_symbols() or [])
        extra = load_fortress_scan_list(max(max_symbols, 100), shuffle_rest=False)
        out.extend(extra or [])
    except Exception:
        pass
    try:
        from alpaca_broker import list_positions

        for p in list_positions() or []:
            if float(p.get("qty") or 0) > 0:
                out.append(str(p.get("symbol", "")).replace("/", "-").upper())
    except Exception:
        pass
    # Always include liquid names so the first train is not empty.
    out.extend(
        [
            "AAPL",
            "MSFT",
            "AMZN",
            "GOOGL",
            "META",
            "NVDA",
            "TSLA",
            "JPM",
            "BAC",
            "WMT",
            "COST",
            "XOM",
            "JNJ",
            "UNH",
            "AMD",
            "AVGO",
            "ORCL",
            "V",
            "MA",
            "SBUX",
            "NFLX",
            "DIS",
            "KO",
            "PEP",
            "MRNA",
            "PFE",
            "LLY",
            "ABBV",
        ]
    )
    seen: set[str] = set()
    uniq: list[str] = []
    for s in out:
        u = str(s or "").strip().upper()
        if not u or u in seen:
            continue
        seen.add(u)
        uniq.append(u)
        if len(uniq) >= max_symbols:
            break
    return uniq


def _closes(symbol: str, start: str, end: str):
    try:
        from data_platform.market_prices import fetch_daily

        df = fetch_daily(symbol, start, end)
        if df is not None and not getattr(df, "empty", True):
            return df
    except Exception:
        pass
    try:
        from feature_engineering import load_price_data

        return load_price_data(symbol, start, end)
    except Exception:
        return None


def _earnings_dates(symbol: str) -> list[date]:
    try:
        from intel.earnings_calendar import load_all_earnings_dates

        return list(load_all_earnings_dates(symbol) or [])
    except Exception:
        return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--max-symbols", type=int, default=int(os.getenv("EVENT_LEARN_MAX_SYMBOLS", "120")))
    ap.add_argument("--years", type=int, default=int(os.getenv("EVENT_LEARN_YEARS", "8")))
    args = ap.parse_args()
    from analytics.event_learn import (
        REPORT_PATH,
        EventSample,
        backfill_peer_feats,
        redesign_until_best,
        save_state,
        samples_from_closes,
    )

    end = date.today()
    start = end - timedelta(days=max(365 * max(2, args.years), 800))
    start_s, end_s = start.isoformat(), end.isoformat()
    syms = _universe(max(20, int(args.max_symbols)))
    samples: list[EventSample] = []
    used: list[str] = []
    failed: list[str] = []
    print(f"[EVENT_LEARN] train universe={len(syms)} window={start_s}..{end_s}", flush=True)
    for i, sym in enumerate(syms, 1):
        try:
            dates = _earnings_dates(sym)
            df = _closes(sym, start_s, end_s)
            if df is None or getattr(df, "empty", True):
                failed.append(sym)
                continue
            chunk = samples_from_closes(sym, df, dates)
            if chunk:
                samples.extend(chunk)
                used.append(sym)
            if i % 15 == 0:
                print(
                    f"[EVENT_LEARN] {i}/{len(syms)} samples={len(samples)} names={len(used)}",
                    flush=True,
                )
        except Exception as e:
            failed.append(sym)
            print(f"[EVENT_LEARN] skip {sym}: {e}", flush=True)
    if len(samples) < 80:
        print(f"[EVENT_LEARN] not enough samples ({len(samples)}) — keep prior weights", flush=True)
        return 0
    try:
        n_peer = backfill_peer_feats(samples)
        print(f"[EVENT_LEARN] peer-backfill attached on {n_peer} samples", flush=True)
    except Exception as e:
        print(f"[EVENT_LEARN] peer-backfill skip: {e}", flush=True)
    st = redesign_until_best(samples)
    save_state(st)
    report = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "n_samples": len(samples),
        "n_event": sum(1 for s in samples if s.is_event),
        "n_symbols": len(used),
        "symbols": used[:80],
        "failed": failed[:40],
        "oos_ic": st.get("oos_ic"),
        "oos_acc": st.get("oos_acc"),
        "mae": st.get("model_mae"),
        "base_mae": st.get("baseline_mae"),
        "beat_baseline": st.get("beat_baseline"),
        "skill": st.get("skill"),
        "dropped": st.get("dropped"),
        "n_redesign": st.get("n_redesign"),
        "active": st.get("active"),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, default=float), encoding="utf-8")
    print(
        f"[EVENT_LEARN] done samples={len(samples)} ic={st.get('oos_ic')} "
        f"acc={st.get('oos_acc')} mae={st.get('model_mae')} base={st.get('baseline_mae')} "
        f"skill={st.get('skill')} dropped={st.get('dropped')}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
