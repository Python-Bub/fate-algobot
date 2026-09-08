#!/usr/bin/env python3
"""1m–1h Gainz-style scan across the trained universe (rotating chunk, never shrink).

Writes data/intel/gainz_v2_signals.json + data/self_improve/hft_runtime.json
(confidence ease when BUY signals fire) so HFT picks them up without a restart.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=False)
_scale = ROOT / "data" / "deploy_scale.env"
if _scale.is_file():
    load_dotenv(_scale, override=True)

from analytics.gainz_v2 import assess
from utils import log

SIGNAL_PATH = ROOT / "data" / "intel" / "gainz_v2_signals.json"
HFT_RUNTIME = ROOT / "data" / "self_improve" / "hft_runtime.json"
ROTATE_PATH = ROOT / "data" / "intel" / "gainz_rotate.json"
DEAD_PATH = ROOT / "data" / "intel" / "gainz_yahoo_skip.json"


def _universe() -> list[str]:
    from analytics.model_scopes import day_trade_tickers
    from fortress_universe import symbols_with_daily_models

    # Full trained book first — rotate, do not drop names.
    try:
        full = list(symbols_with_daily_models() or [])
    except Exception:
        full = []
    dt = day_trade_tickers(include_positions=True)
    seen: set[str] = set()
    out: list[str] = []
    for s in list(dt) + list(full):
        u = str(s or "").strip().upper()
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _chunk(syms: list[str]) -> list[str]:
    n = len(syms)
    if n <= 0:
        return []
    batch = max(8, int(os.getenv("GAINZ_SCAN_CHUNK", "48")))
    rot = {}
    if ROTATE_PATH.is_file():
        try:
            rot = json.loads(ROTATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            rot = {}
    off = int(rot.get("offset") or 0) % n
    chunk = [syms[(off + i) % n] for i in range(min(batch, n))]
    ROTATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ROTATE_PATH.write_text(
        json.dumps({"offset": (off + batch) % n, "total": n, "last": chunk[:12]}, indent=2),
        encoding="utf-8",
    )
    return chunk


def _dead_load() -> dict:
    if not DEAD_PATH.is_file():
        return {}
    try:
        return json.loads(DEAD_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _is_dead(sym: str) -> bool:
    row = (_dead_load().get("syms") or {}).get(sym.upper())
    if not row:
        return False
    return (time.time() - float(row.get("ts") or 0)) < 6 * 3600


def _mark_dead(sym: str, why: str) -> None:
    doc = _dead_load()
    syms = dict(doc.get("syms") or {})
    syms[sym.upper()] = {"ts": time.time(), "why": why[:80]}
    DEAD_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEAD_PATH.write_text(json.dumps({"syms": syms}, indent=2), encoding="utf-8")


def _bars(sym: str):
    from analytics.day_trade_yahoo import fetch_yahoo_bars

    return fetch_yahoo_bars(sym)


def _merge_hft_runtime(buys: list[str], delta: float) -> None:
    doc: dict = {}
    if HFT_RUNTIME.is_file():
        try:
            doc = json.loads(HFT_RUNTIME.read_text(encoding="utf-8"))
        except Exception:
            doc = {}
    prev = float(doc.get("confidence_floor_delta") or 0.0)
    # Ease HFT gates slightly when Gainz prints BUYs (never more than ±0.08).
    doc["confidence_floor_delta"] = max(-0.08, min(0.08, prev * 0.5 + delta))
    doc["gainz_buys"] = buys[:24]
    doc["gainz_ts"] = datetime.now(timezone.utc).isoformat()
    HFT_RUNTIME.parent.mkdir(parents=True, exist_ok=True)
    HFT_RUNTIME.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def scan_once() -> dict:
    if os.getenv("GAINZ_V2_ENABLED", "true").lower() not in ("1", "true", "yes"):
        return {"action": "disabled"}
    uni = _universe()
    chunk = _chunk(uni)
    rows: list[dict] = []
    buys: list[str] = []
    for sym in chunk:
        if _is_dead(sym):
            continue
        try:
            df = _bars(sym)
            if df is None or getattr(df, "empty", True) or len(df) < 30:
                continue
            g = assess(df, symbol=sym)
            if g.side == "none" and not g.ready and not g.bos:
                continue
            d = g.to_dict()
            rows.append(d)
            if g.side == "buy":
                buys.append(sym)
        except Exception as e:
            msg = str(e)
            if "delisted" in msg.lower() or "YFPricesMissing" in msg:
                _mark_dead(sym, msg)
            log.debug("[GAINZ] %s: %s", sym, e)
    payload = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "universe": len(uni),
        "scanned": len(chunk),
        "signals": rows,
        "buys": buys,
    }
    SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    SIGNAL_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    delta = -0.02 if buys else 0.0
    try:
        _merge_hft_runtime(buys, delta)
    except Exception:
        pass
    log.info(
        "[GAINZ] universe=%d scanned=%d signals=%d buys=%s",
        len(uni),
        len(chunk),
        len(rows),
        ",".join(buys[:8]) or "-",
    )
    try:
        from analytics.robot_core import write_status

        write_status()
    except Exception:
        pass
    return payload


def main() -> int:
    interval = float(os.getenv("GAINZ_POLL_SEC", "25"))
    log.info("[GAINZ] 1m-1h teacher loop every %.0fs (chunk=%s)", interval, os.getenv("GAINZ_SCAN_CHUNK", "48"))
    while True:
        try:
            scan_once()
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.warning("[GAINZ] cycle: %s", e)
        time.sleep(interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
