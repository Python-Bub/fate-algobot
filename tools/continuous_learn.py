#!/usr/bin/env python3
"""Continuous learning loop — fills + open marks → ULE / neural / meta tweaks.

Runs every CONTINUOUS_LEARN_SEC (default 45). Does NOT retrain the full universe
every second (that would trip Yahoo/Alpaca rate limits). Instead:

  1. Pull recent Alpaca FILL activities
  2. Pair BUY→SELL (or short) legs → realized return → learn_from_realized_trade
  3. Soft mark-to-market credit on open positions (ULE skill only)
  4. Periodic light ULE cycle (skill + history, no heavy codegen by default)

This is the always-on brain pulse beside HFT ticks and fortress sweeps.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
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

STATE = ROOT / "data" / "intel" / "continuous_learn_state.json"
LOG = ROOT / "logs" / "continuous_learn_latest.log"


def _now() -> float:
    return time.time()


def _load_state() -> dict[str, Any]:
    if not STATE.is_file():
        return {"seen_ids": [], "last_ule": 0.0, "n_learned": 0, "n_loops": 0}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"seen_ids": [], "last_ule": 0.0, "n_learned": 0, "n_loops": 0}


def _save_state(st: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    seen = list(st.get("seen_ids") or [])[-4000:]
    st["seen_ids"] = seen
    st["updated"] = _now()
    STATE.write_text(json.dumps(st, indent=2), encoding="utf-8")


def _log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _alpaca_fills(hours: float = 48.0) -> list[dict[str, Any]]:
    k = os.getenv("ALPACA_API_KEY", "").strip()
    s = os.getenv("ALPACA_SECRET_KEY", os.getenv("ALPACA_API_SECRET", "")).strip()
    if not k or not s:
        return []
    import requests

    base = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")
    if base.endswith("/v2"):
        base = base[:-3]
    after = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%d")
    try:
        r = requests.get(
            f"{base}/v2/account/activities/FILL",
            params={"after": after, "direction": "asc", "page_size": 100},
            headers={"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s},
            timeout=20,
        )
        r.raise_for_status()
        acts = r.json()
        return acts if isinstance(acts, list) else []
    except Exception as e:
        _log(f"[continuous-learn] alpaca fills: {e}")
        return []


def _fill_id(a: dict[str, Any]) -> str:
    return str(a.get("id") or a.get("transaction_time") or "") + "|" + str(a.get("order_id") or "")


def _pair_and_learn(fills: list[dict[str, Any]], seen: set[str]) -> tuple[int, list[str]]:
    """Match closes against opens in chronological order; learn on new closes only."""
    from online_learning.trade_feedback import learn_from_realized_trade

    opens: dict[str, list[dict[str, Any]]] = {}
    learned = 0
    new_ids: list[str] = []
    for a in fills:
        fid = _fill_id(a)
        side = str(a.get("side", "")).upper()
        sym = str(a.get("symbol", "")).replace("/", "-").upper()
        if side not in ("BUY", "SELL") or not sym:
            continue
        try:
            qty = float(a.get("qty") or a.get("quantity") or 0)
            px = float(a.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if qty <= 0 or px <= 0:
            continue
        is_new = fid not in seen
        book = opens.setdefault(sym, [])
        if side == "BUY":
            book.append({"qty": qty, "px": px, "id": fid, "new": is_new})
            if is_new:
                new_ids.append(fid)
            continue
        # SELL — close FIFO long inventory
        remain = qty
        cost = 0.0
        closed = 0.0
        used_new = is_new
        while remain > 1e-9 and book:
            leg = book[0]
            take = min(remain, float(leg["qty"]))
            cost += take * float(leg["px"])
            closed += take
            leg["qty"] = float(leg["qty"]) - take
            remain -= take
            if leg.get("new"):
                used_new = True
            if float(leg["qty"]) <= 1e-9:
                book.pop(0)
        if closed <= 1e-9:
            if is_new:
                new_ids.append(fid)
            continue
        avg_in = cost / closed
        ret = (px - avg_in) / avg_in
        if is_new:
            new_ids.append(fid)
        if used_new or is_new:
            try:
                learn_from_realized_trade(
                    sym,
                    "LONG",
                    float(ret),
                    source="continuous_learn",
                    bars_held=1,
                )
                learned += 1
            except Exception as e:
                _log(f"[continuous-learn] learn {sym}: {e}")
    return learned, new_ids


def _soft_mark_open() -> int:
    """ULE soft credit from open unrealized P/L (no neural retrain — cheap)."""
    k = os.getenv("ALPACA_API_KEY", "").strip()
    s = os.getenv("ALPACA_SECRET_KEY", os.getenv("ALPACA_API_SECRET", "")).strip()
    if not k or not s:
        return 0
    if os.getenv("CONTINUOUS_LEARN_MARK", "true").lower() not in ("1", "true", "yes"):
        return 0
    import requests

    base = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")
    if base.endswith("/v2"):
        base = base[:-3]
    try:
        r = requests.get(
            f"{base}/v2/positions",
            headers={"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s},
            timeout=15,
        )
        r.raise_for_status()
        pos = r.json()
    except Exception as e:
        _log(f"[continuous-learn] positions: {e}")
        return 0
    try:
        from analytics.ultimate_learning_engine import active_for_symbol, credit_outcome, enabled
    except Exception:
        return 0
    if not enabled():
        return 0
    from analytics.position_gain import sane_unrealized_gain

    n = 0
    scale = float(os.getenv("CONTINUOUS_LEARN_MARK_SCALE", "0.15"))
    for p in pos if isinstance(pos, list) else []:
        try:
            uplpc = sane_unrealized_gain(p)
        except (TypeError, ValueError):
            continue
        if uplpc is None:
            continue
        if abs(uplpc) < 1e-6:
            continue
        # Soft reward — dampened so marks don't dominate fill learning
        reward = uplpc * scale
        success = reward > 0
        try:
            sym = str(p.get("symbol") or "").strip().upper()
            chans = active_for_symbol(sym) or ["base", "neural", "lstm", "proven", "event"]
            credit_outcome(success=success, active=chans, reward=reward)
            n += 1
        except Exception:
            pass
    return n


def _maybe_ule(st: dict[str, Any]) -> dict[str, Any] | None:
    every = float(os.getenv("CONTINUOUS_LEARN_ULE_EVERY_SEC", "300"))
    last = float(st.get("last_ule") or 0)
    if _now() - last < every:
        return None
    try:
        from analytics.ultimate_learning_engine import run_cycle

        # Light cycle: history credit, skip codegen unless explicitly on
        do_cg = os.getenv("CONTINUOUS_LEARN_CODEGEN", "false").lower() in ("1", "true", "yes")
        summary = run_cycle(hist_limit=int(os.getenv("CONTINUOUS_LEARN_HIST", "40")), do_codegen=do_cg, do_pattern_scan=False)
        st["last_ule"] = _now()
        return summary
    except Exception as e:
        _log(f"[continuous-learn] ule: {e}")
        return None


def run_once() -> dict[str, Any]:
    st = _load_state()
    seen = set(st.get("seen_ids") or [])
    fills = _alpaca_fills(hours=float(os.getenv("CONTINUOUS_LEARN_FILL_HOURS", "168")))
    learned, new_ids = _pair_and_learn(fills, seen)
    for fid in new_ids:
        seen.add(fid)
    marks = _soft_mark_open()
    ule = _maybe_ule(st)
    st["seen_ids"] = list(seen)
    st["n_learned"] = int(st.get("n_learned") or 0) + learned
    st["n_loops"] = int(st.get("n_loops") or 0) + 1
    _save_state(st)
    out = {
        "ok": True,
        "fills": len(fills),
        "learned": learned,
        "marks": marks,
        "n_learned_total": st["n_learned"],
        "ule": (ule or {}).get("ok") if ule else None,
    }
    _log(
        f"[continuous-learn] fills={out['fills']} learned={learned} marks={marks} "
        f"total={st['n_learned']} ule={out['ule']}"
    )
    return out


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Continuous learn pulse")
    ap.add_argument("--loop", action="store_true", help="Run forever (daemon)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    pause = float(os.getenv("CONTINUOUS_LEARN_SEC", "45"))
    if args.loop:
        while True:
            try:
                out = run_once()
                if args.json:
                    print(json.dumps(out), flush=True)
            except Exception as e:
                _log(f"[continuous-learn] loop err: {e}")
            time.sleep(max(15.0, pause))
        return 0
    out = run_once()
    if args.json:
        print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
