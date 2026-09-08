#!/usr/bin/env python3
"""Buy when a ticker is down X% vs prior close (user dip triggers)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

from utils import log

STATE_PATH = ROOT / "data" / "dip_buy_triggers.json"


def _load_state() -> dict:
    if not STATE_PATH.is_file():
        return {"triggers": []}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"triggers": []}


def _save_state(doc: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def daily_change_pct(ticker: str) -> tuple[float | None, float | None, float | None]:
    """Return (pct_change, prev_close, last_px) vs prior session close."""
    sym = ticker.strip().upper()
    last_px = None
    try:
        from alpaca_broker import get_mid_price

        last_px = get_mid_price(sym)
    except Exception:
        pass
    prev_close = None
    try:
        import yfinance as yf

        h = yf.Ticker(sym).history(period="5d")
        if h is not None and len(h) >= 2:
            prev_close = float(h["Close"].iloc[-2])
            if last_px is None:
                last_px = float(h["Close"].iloc[-1])
        elif h is not None and len(h) == 1:
            prev_close = float(h["Open"].iloc[-1])
            if last_px is None:
                last_px = float(h["Close"].iloc[-1])
    except Exception:
        pass
    if prev_close and last_px and prev_close > 0:
        return (last_px - prev_close) / prev_close * 100.0, prev_close, last_px
    return None, prev_close, last_px


def _affordable_notional(requested: float) -> float:
    try:
        from alpaca_broker import get_account

        acct = get_account() or {}
        bp = float(acct.get("daytrading_buying_power") or acct.get("buying_power") or 0)
        reserve = float(os.getenv("DIP_BUY_BP_RESERVE", "2000"))
        cap = max(0.0, bp - reserve)
        if cap <= 0:
            return 0.0
        return min(requested, cap * float(os.getenv("DIP_BUY_BP_USE_FRAC", "0.85")))
    except Exception:
        return requested


def _place_buy(ticker: str, notional: float) -> dict:
    sym = ticker.strip().upper()
    slip = float(os.getenv("DIP_BUY_SLIP_BPS", "10")) / 10000.0
    from alpaca_broker import get_quote_bid_ask, submit_limit_order
    from analytics.limit_pricing import entry_limit_px

    q = get_quote_bid_ask(sym)
    if not q:
        raise RuntimeError(f"no quote for {sym}")
    bid, ask = q
    lp = entry_limit_px("buy", bid, ask)
    if not lp or lp <= 0:
        raise RuntimeError(f"bad limit for {sym}")
    notional = _affordable_notional(notional)
    if notional < float(os.getenv("DIP_BUY_MIN_NOTIONAL", "500")):
        raise RuntimeError("insufficient buying power for dip buy")
    qty = max(1, int(notional / lp))
    # User dip buys bypass midday slow-strategy gate.
    os.environ["DIP_BUY_ACTIVE"] = "1"
    try:
        from analytics import market_session

        orig = market_session.slow_intraday_buy_allowed

        def _bypass(*, for_hft: bool = False, dt=None):
            if os.getenv("DIP_BUY_ACTIVE") == "1":
                return True, "dip_buy_bypass"
            return orig(for_hft=for_hft, dt=dt)

        market_session.slow_intraday_buy_allowed = _bypass
        return submit_limit_order(sym, qty, "buy", lp)
    finally:
        os.environ.pop("DIP_BUY_ACTIVE", None)


def evaluate_trigger(row: dict, *, dry_run: bool = False) -> dict:
    sym = str(row.get("ticker", "")).upper()
    dip = float(row.get("dip_pct", 3.0))
    notional = float(row.get("notional_usd") or os.getenv("ORDER_NOTIONAL", "8000"))
    fired = bool(row.get("fired"))
    out = {"ticker": sym, "dip_pct": dip, "fired": fired, "action": "wait"}

    if fired:
        out["action"] = "already_fired"
        return out

    chg, prev, px = daily_change_pct(sym)
    out["change_pct"] = chg
    out["prev_close"] = prev
    out["last_px"] = px
    if chg is None:
        out["action"] = "no_quote"
        return out

    out["need_pct"] = -abs(dip)
    if chg > -abs(dip):
        out["action"] = "waiting"
        out["gap_pct"] = round(chg - (-abs(dip)), 3)
        return out

    if dry_run:
        out["action"] = "would_buy"
        return out

    try:
        from intel.algo_risk_filter import gate_buy_order

        if not gate_buy_order(sym, source="dip_buy_watch"):
            out["action"] = "risk_blocked"
            return out
        order = _place_buy(sym, notional)
        row["fired"] = True
        row["fired_at_utc"] = datetime.now(timezone.utc).isoformat()
        row["fill_change_pct"] = chg
        row["order_id"] = order.get("id")
        out["action"] = "bought"
        out["order_id"] = order.get("id")
        out["qty"] = order.get("qty")
        log.info("[DIP_BUY] %s down %.2f%% — bought ~$%.0f", sym, chg, notional)
    except Exception as e:
        out["action"] = "buy_failed"
        out["error"] = str(e)
        log.warning("[DIP_BUY] %s buy failed: %s", sym, e)
    return out


def run_once(*, dry_run: bool = False) -> list[dict]:
    doc = _load_state()
    results = []
    for row in doc.get("triggers") or []:
        results.append(evaluate_trigger(row, dry_run=dry_run))
    _save_state(doc)
    return results


def add_trigger(ticker: str, dip_pct: float, notional: float | None = None) -> None:
    doc = _load_state()
    sym = ticker.upper()
    triggers = [t for t in doc.get("triggers") or [] if str(t.get("ticker", "")).upper() != sym]
    triggers.append(
        {
            "ticker": sym,
            "dip_pct": abs(dip_pct),
            "notional_usd": float(notional or os.getenv("ORDER_NOTIONAL", "8000")),
            "fired": False,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    doc["triggers"] = triggers
    _save_state(doc)


def main() -> int:
    ap = argparse.ArgumentParser(description="Buy on dip vs prior close")
    ap.add_argument("--add", metavar="TICKER", help="Register trigger (use with --dip)")
    ap.add_argument("--dip", type=float, default=3.0, help="Buy when down this %% vs prior close")
    ap.add_argument("--notional", type=float, help="USD notional (default ORDER_NOTIONAL)")
    ap.add_argument("--once", action="store_true", help="Single check")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--loop", action="store_true", help="Daemon poll (daemon_loop.sh)")
    ap.add_argument("--interval", type=float, default=float(os.getenv("DIP_BUY_POLL_SEC", "30")))
    args = ap.parse_args()

    if args.add:
        add_trigger(args.add, args.dip, args.notional)
        print(json.dumps({"added": args.add.upper(), "dip_pct": args.dip}, indent=2))

    if args.loop:
        while True:
            for r in run_once(dry_run=args.dry_run):
                if r.get("action") not in ("waiting", "already_fired"):
                    print(json.dumps(r))
            time.sleep(max(5.0, args.interval))
        return 0

    results = run_once(dry_run=args.dry_run)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
