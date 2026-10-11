#!/usr/bin/env python3
"""Experimental crypto HFT daemon — paper, tiny, 24/7, long-only.

Separate from equity OBI (IEX). Uses Alpaca crypto quotes + crypto_math.
Does not cancel resting GTC. Does not touch fortress BTC/ETH inventory.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)
_scale = ROOT / "data" / "deploy_scale.env"
if _scale.is_file():
    load_dotenv(_scale, override=True)

from analytics.crypto_hft import (
    clip_usd,
    decide_entry,
    experimental_enabled,
    hft_symbols,
    max_gross_usd,
    max_open,
    max_orders_per_min,
    poll_sec,
    skip_held,
    stop_px,
    target_px,
)
from analytics.crypto_math import score_crypto
from crypto_universe import yahoo_symbol
from utils import log

STATE_PATH = ROOT / "data" / "intel" / "crypto_hft_state.json"
SNAP_PATH = ROOT / "data" / "intel" / "crypto_hft_latest.json"


def _env_bool(key: str, default: str = "true") -> bool:
    return os.getenv(key, default).lower() in ("1", "true", "yes", "on")


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"open": {}, "mids": {}, "order_ts": []}
    try:
        js = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(js, dict):
            js.setdefault("open", {})
            js.setdefault("mids", {})
            js.setdefault("order_ts", [])
            return js
    except Exception:
        pass
    return {"open": {}, "mids": {}, "order_ts": []}


def _save_state(st: dict[str, Any]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(st, indent=0)[:120_000], encoding="utf-8")
    except Exception:
        pass


def _halted() -> bool:
    try:
        from analytics.day_trade_risk import is_trading_halted

        return bool(is_trading_halted())
    except Exception:
        return os.getenv("TRADING_HALTED", "false").lower() in ("1", "true", "yes")


def _pace_ok(st: dict[str, Any]) -> bool:
    now = time.time()
    ts = [float(x) for x in (st.get("order_ts") or []) if now - float(x) < 60.0]
    st["order_ts"] = ts
    return len(ts) < max_orders_per_min()


def _note_order(st: dict[str, Any]) -> None:
    ts = list(st.get("order_ts") or [])
    ts.append(time.time())
    st["order_ts"] = ts[-40:]


_POS_CACHE: dict[str, Any] = {"t": 0.0, "rows": None}


def _cached_positions() -> list[dict]:
    now = time.time()
    rows = _POS_CACHE.get("rows")
    if isinstance(rows, list) and now - float(_POS_CACHE.get("t") or 0) < 2.0:
        return rows
    try:
        from alpaca_broker import list_positions

        rows = list(list_positions() or [])
    except Exception:
        rows = []
    _POS_CACHE["t"] = now
    _POS_CACHE["rows"] = rows
    return rows


def _live_qty(symbol: str) -> float:
    try:
        from crypto_universe import same_crypto

        for p in _cached_positions():
            sym = str(p.get("symbol") or "")
            if same_crypto(sym, symbol):
                return float(p.get("qty") or p.get("qty_available") or 0)
    except Exception:
        return 0.0
    return 0.0


def _stop_held_long(symbol: str, mid: float, stp_bps: float, st: dict[str, Any]) -> bool:
    """Cut a fortress-held coin past the crypto stop.

    skip_held used to return before any stop, so BCH −8% and LTC −5% were
    never sold: the equity scan thought crypto was someone else's book.
    """
    if mid <= 0 or not _pace_ok(st):
        return False
    if not _env_bool("CRYPTO_HFT_STOP_HELD", "true"):
        return False
    try:
        from crypto_universe import same_crypto
        from analytics.position_gain import sane_unrealized_gain
        from alpaca_broker import close_position_alpaca
    except Exception:
        return False
    pos = None
    for p in _cached_positions():
        if same_crypto(str(p.get("symbol") or ""), symbol):
            pos = p
            break
    if not pos:
        return False
    gain = sane_unrealized_gain(pos, mid)
    stop = -abs(float(stp_bps)) / 10_000.0
    if gain is None or gain > stop:
        return False
    if not close_position_alpaca(symbol, force=True):
        return False
    _note_order(st)
    log.warning("[CRYPTO-HFT] held stop %s gain=%.2f%%", symbol, 100.0 * gain)
    return True


def _quote(symbol: str) -> tuple[float, float] | None:
    try:
        from alpaca_broker import get_quote_bid_ask

        return get_quote_bid_ask(symbol)
    except Exception:
        return None


def _place_limit(symbol: str, qty: float, side: str, px: float) -> dict[str, Any] | None:
    try:
        from alpaca_broker import submit_limit_order

        return submit_limit_order(
            symbol,
            qty,
            side,
            px,
            for_hft=True,
            time_in_force="gtc",
        )
    except Exception as e:
        log.warning("[CRYPTO-HFT] %s %s failed: %s", side, symbol, e)
        if "insufficient" in str(e).lower():
            return {"_insufficient": True, "symbol": symbol}
        return None


def tick(state: dict[str, Any] | None = None) -> dict[str, Any]:
    """One scan. Safe to call from tests with a fake state."""
    st = state if state is not None else _load_state()
    out: dict[str, Any] = {"ok": True, "actions": [], "scores": {}}
    if not experimental_enabled():
        out["ok"] = False
        out["why"] = "disabled"
        return out
    if _halted():
        out["ok"] = False
        out["why"] = "halted"
        return out

    opens: dict[str, Any] = dict(st.get("open") or {})
    mids_map: dict[str, list[float]] = {
        k: list(v) for k, v in (st.get("mids") or {}).items() if isinstance(v, list)
    }
    skip_fort = _env_bool("CRYPTO_HFT_SKIP_IF_HELD", "true")
    tgt_bps = float(os.getenv("CRYPTO_HFT_TARGET_BPS", "22") or 22)
    stp_bps = float(os.getenv("CRYPTO_HFT_STOP_BPS", "400") or 400)

    for sym in hft_symbols():
        q = _quote(sym)
        if not q:
            out["actions"].append({"sym": sym, "why": "no_quote"})
            continue
        bid, ask = float(q[0]), float(q[1])
        mid = 0.5 * (bid + ask)
        hist = mids_map.get(sym) or []
        hist.append(mid)
        mids_map[sym] = hist[-24:]

        yahoo = yahoo_symbol(sym)
        try:
            cs = score_crypto(yahoo)
            out["scores"][sym] = cs.as_dict()
        except Exception as e:
            log.debug("[CRYPTO-HFT] score %s: %s", sym, e)
            continue

        live = _live_qty(sym)
        rec = opens.get(sym) if isinstance(opens.get(sym), dict) else None
        our_qty = float((rec or {}).get("qty") or 0.0)
        fortress = skip_held(sym, live_qty=live, our_qty=our_qty, skip_if_held=skip_fort)

        if rec and our_qty > 1e-12:
            if live <= 1e-12:
                opens.pop(sym, None)
                out["actions"].append({"sym": sym, "why": "phantom_flat"})
                continue
            entry = float(rec.get("entry") or mid)
            tgt = target_px(entry, bps=tgt_bps)
            stp = stop_px(entry, bps=stp_bps)
            if mid >= tgt and _pace_ok(st):
                sell_q = min(our_qty, live)
                if sell_q > 1e-12:
                    od = _place_limit(sym, sell_q, "sell", max(ask * 0.999, tgt))
                    _note_order(st)
                    if od and od.get("_insufficient"):
                        opens.pop(sym, None)
                        out["actions"].append({"sym": sym, "why": "phantom_flat"})
                    else:
                        out["actions"].append({"sym": sym, "why": "take_profit", "order": bool(od)})
                        if od:
                            opens.pop(sym, None)
            elif mid <= stp and _pace_ok(st):
                sell_q = min(our_qty, live)
                if sell_q > 1e-12:
                    od = _place_limit(sym, sell_q, "sell", min(bid, stp))
                    _note_order(st)
                    if od and od.get("_insufficient"):
                        opens.pop(sym, None)
                        out["actions"].append({"sym": sym, "why": "phantom_flat"})
                    else:
                        out["actions"].append({"sym": sym, "why": "wide_stop", "order": bool(od)})
                        if od:
                            opens.pop(sym, None)
            else:
                out["actions"].append({"sym": sym, "why": "hold_open", "pnl_mid": mid / entry - 1.0})
            continue

        if fortress:
            if _stop_held_long(sym, mid, stp_bps, st):
                out["actions"].append({"sym": sym, "why": "held_hard_stop"})
            else:
                out["actions"].append({"sym": sym, "why": "fortress_held"})
            continue

        open_n = sum(1 for v in opens.values() if isinstance(v, dict) and float(v.get("qty") or 0) > 0)
        gross = sum(float(v.get("qty") or 0) * float(v.get("entry") or 0) for v in opens.values() if isinstance(v, dict))
        dec = decide_entry(
            cs,
            bid=bid,
            ask=ask,
            mids=mids_map[sym],
            held_fortress=False,
            open_count=open_n,
            gross_usd=gross,
        )
        if not dec.get("ok"):
            out["actions"].append({"sym": sym, "why": dec.get("why")})
            continue
        if not _pace_ok(st):
            out["actions"].append({"sym": sym, "why": "pace"})
            continue
        qty = float(dec.get("qty") or 0)
        lp = float(dec.get("limit_px") or bid)
        if qty <= 0 or lp <= 0:
            continue
        od = _place_limit(sym, qty, "buy", lp)
        _note_order(st)
        filled = bool(od) and not od.get("_insufficient")
        out["actions"].append({"sym": sym, "why": "enter", "order": filled, "qty": qty, "px": lp})
        if filled:
            fills_px = float(od.get("filled_avg_price") or lp)
            opens[sym] = {
                "qty": qty,
                "entry": fills_px,
                "ts": time.time(),
                "order_id": str(od.get("id") or ""),
                "clip": clip_usd(),
            }

    st["open"] = opens
    st["mids"] = mids_map
    st["ts"] = time.time()
    st["max_gross"] = max_gross_usd()
    st["max_open"] = max_open()
    _save_state(st)
    try:
        SNAP_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAP_PATH.write_text(json.dumps({"ts": st["ts"], "scores": out["scores"], "actions": out["actions"]}, indent=0)[:80_000], encoding="utf-8")
    except Exception:
        pass
    return out


def main() -> int:
    once = "--once" in sys.argv
    log.info(
        "[CRYPTO-HFT] experimental sidecar symbols=%s clip=$%.0f poll=%.1fs",
        ",".join(hft_symbols()),
        clip_usd(),
        poll_sec(),
    )
    while True:
        try:
            tick()
        except Exception as e:
            log.warning("[CRYPTO-HFT] tick: %s", e)
        if once:
            return 0
        time.sleep(poll_sec())


if __name__ == "__main__":
    raise SystemExit(main())
