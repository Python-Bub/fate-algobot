"""Cross-engine portfolio slot budget — ~3–5 names per head, ~15 total live."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_FILE = Path(os.getenv("PORTFOLIO_HEAD_REGISTRY", "data/portfolio_head_registry.json"))
PROMOTE_FILE = Path(os.getenv("DAY_TRADE_PROMOTE_FILE", "data/intel/day_trade_promote.json"))

HEAD_ORDER = ("day_trade", "fortress", "weekly", "longterm", "hft")


def _enabled() -> bool:
    return os.getenv("PORTFOLIO_SLOT_BUDGET", "true").lower() in ("1", "true", "yes")


def portfolio_max_total() -> int:
    # 0 = unlimited (user wants hundreds of concurrent names across sleeves)
    v = int(os.getenv("PORTFOLIO_MAX_TOTAL", "500"))
    return 10_000 if v <= 0 else max(1, v)


def head_max_slots(head: str) -> int:
    defaults = {
        "day_trade": 50,
        "fortress": 500,
        "weekly": 100,
        "longterm": 100,
        "hft": 200,
    }
    env_keys = {
        "day_trade": "DAY_TRADE_MAX_CONCURRENT",
        "fortress": "FORTRESS_MAX_POSITIONS",
        "weekly": "PAPER_SIM_TOP_K",
        "longterm": "LONGTERM_TOP_K",
        "hft": "HFT_MAX_CONCURRENT_SLOTS",
    }
    h = head.lower()
    if h in env_keys:
        raw = int(os.getenv(env_keys[h], str(defaults.get(h, 50))))
        return 10_000 if raw <= 0 else max(1, raw)
    return defaults.get(h, 50)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def load_registry() -> dict[str, str]:
    return dict(_load_json(REGISTRY_FILE).get("heads") or {})


def load_qty_by_sleeve() -> dict[str, dict[str, float]]:
    """Per-symbol qty owned by each sleeve — prevents cross-sleeve wipe on exit."""
    raw = _load_json(REGISTRY_FILE).get("qty_by_sleeve") or {}
    out: dict[str, dict[str, float]] = {}
    for sym, sleeves in raw.items():
        if not isinstance(sleeves, dict):
            continue
        out[str(sym).upper()] = {
            str(h).lower(): float(q)
            for h, q in sleeves.items()
            if float(q or 0) > 1e-12
        }
    return out


def sleeve_qty(symbol: str, head: str) -> float:
    return float(load_qty_by_sleeve().get(str(symbol).upper(), {}).get(head.lower(), 0.0) or 0.0)


def protected_qty(symbol: str, *, except_heads: tuple[str, ...] = ()) -> float:
    """Qty owned by other sleeves that must NOT be sold by `except_heads` exits."""
    skip = {h.lower() for h in except_heads}
    sleeves = load_qty_by_sleeve().get(str(symbol).upper(), {})
    return float(sum(q for h, q in sleeves.items() if h not in skip and q > 0))


def sellable_qty_for_head(
    symbol: str,
    head: str,
    *,
    broker_qty: float | None = None,
    confirmed_fill_qty: float | None = None,
) -> float:
    """Max qty this head may sell without touching other sleeves' inventory.

    Stale `qty_by_sleeve` that exceeds live (AMZN fortress=26 vs live 9) must not
    zero a day-trade/micro exit. A confirmed fill on THIS ticket is always
    sellable after subtracting recorded overnight qty.
    """
    sym = str(symbol).upper()
    h = head.lower()
    mine = sleeve_qty(sym, h)
    broker = broker_qty
    if broker is None:
        try:
            from alpaca_broker import get_position

            pos = get_position(sym)
            broker = abs(float((pos or {}).get("qty") or 0))
        except Exception:
            broker = 0.0
    broker = float(broker or 0)
    sleeves = load_qty_by_sleeve().get(sym) or {}
    recorded = float(sum(float(q or 0) for q in sleeves.values()))
    primary = str(load_registry().get(sym) or "").lower()
    if recorded > broker + 1e-6:
        # Stale oversized map. Primary head owns the live book.
        if h == primary or (mine <= 1e-12 and primary == h):
            return max(0.0, broker)
        if mine > 1e-12:
            return max(0.0, min(mine, broker))
        return 0.0
    if mine > 1e-12:
        return max(0.0, min(mine, broker))
    prot = protected_qty(sym, except_heads=(h,))
    cf = float(confirmed_fill_qty or 0)
    if cf > 1e-12:
        room = max(0.0, broker - max(0.0, prot))
        return max(0.0, min(cf, room if prot > 1e-12 else broker))
    # Legacy: symbol registered to another overnight head → sell nothing from HFT/day/micro
    # unless we have a confirmed fill (handled above).
    if primary and primary not in (h, "hft") and h in ("hft", "day_trade", "micro_scalp"):
        if primary in ("fortress", "weekly", "longterm"):
            return 0.0
    if prot > 1e-12:
        return max(0.0, broker - prot)
    return max(0.0, broker)


def adjust_sleeve_qty(symbol: str, head: str, delta: float) -> None:
    """Add (positive) or remove (negative) sleeve qty. Drops empty sleeves/symbols."""
    sym = str(symbol).strip().upper()
    h = head.lower()
    if not sym or abs(float(delta)) < 1e-12:
        return
    doc = _load_json(REGISTRY_FILE)
    qty_map = dict(doc.get("qty_by_sleeve") or {})
    sleeves = dict(qty_map.get(sym) or {})
    new_q = float(sleeves.get(h, 0) or 0) + float(delta)
    if new_q <= 1e-12:
        sleeves.pop(h, None)
    else:
        sleeves[h] = round(new_q, 6)
    if sleeves:
        qty_map[sym] = sleeves
    else:
        qty_map.pop(sym, None)
    doc["qty_by_sleeve"] = qty_map
    # Keep primary head = largest sleeve (for legacy readers)
    heads = dict(doc.get("heads") or {})
    if sleeves:
        primary = max(sleeves.items(), key=lambda kv: kv[1])[0]
        heads[sym] = primary
    elif heads.get(sym) == h:
        heads.pop(sym, None)
    doc["heads"] = heads
    doc["updated_utc"] = datetime.now(timezone.utc).isoformat()
    _save_json(REGISTRY_FILE, doc)


def register_symbol(symbol: str, head: str, *, qty: float | None = None) -> None:
    sym = str(symbol).strip().upper()
    if not sym:
        return
    doc = _load_json(REGISTRY_FILE)
    heads = dict(doc.get("heads") or {})
    heads[sym] = head.lower()
    doc["heads"] = heads
    if qty is not None and float(qty) > 0:
        qty_map = dict(doc.get("qty_by_sleeve") or {})
        sleeves = dict(qty_map.get(sym) or {})
        sleeves[head.lower()] = float(sleeves.get(head.lower(), 0) or 0) + float(qty)
        qty_map[sym] = sleeves
        doc["qty_by_sleeve"] = qty_map
    doc["updated_utc"] = datetime.now(timezone.utc).isoformat()
    _save_json(REGISTRY_FILE, doc)


def unregister_symbol(symbol: str, head: str | None = None) -> None:
    sym = str(symbol).strip().upper()
    doc = _load_json(REGISTRY_FILE)
    heads = dict(doc.get("heads") or {})
    qty_map = dict(doc.get("qty_by_sleeve") or {})
    if head:
        sleeves = dict(qty_map.get(sym) or {})
        sleeves.pop(head.lower(), None)
        if sleeves:
            qty_map[sym] = sleeves
            heads[sym] = max(sleeves.items(), key=lambda kv: kv[1])[0]
        else:
            qty_map.pop(sym, None)
            heads.pop(sym, None)
    else:
        heads.pop(sym, None)
        qty_map.pop(sym, None)
    doc["heads"] = heads
    doc["qty_by_sleeve"] = qty_map
    doc["updated_utc"] = datetime.now(timezone.utc).isoformat()
    _save_json(REGISTRY_FILE, doc)


def count_by_head(head: str, *, positions: list[dict] | None = None) -> int:
    h = head.lower()
    registry = load_registry()
    if positions is None:
        try:
            from alpaca_broker import list_positions

            positions = list_positions()
        except Exception:
            positions = []
    syms = {
        str(p.get("symbol", "")).upper()
        for p in positions
        if abs(float(p.get("qty") or 0)) > 0
    }
    return sum(1 for s in syms if registry.get(s) == h)


def live_position_count(*, positions: list[dict] | None = None) -> int:
    if positions is None:
        try:
            from alpaca_broker import list_positions

            positions = list_positions()
        except Exception:
            return 0
    return sum(1 for p in positions if abs(float(p.get("qty") or 0)) > 0)


def can_open_head(head: str, symbol: str, *, positions: list[dict] | None = None) -> tuple[bool, str]:
    if not _enabled():
        return True, "slots_disabled"
    sym = str(symbol).strip().upper()
    registry = load_registry()
    # Allow fortress to add to an existing day-trade leg (promote/hold path).
    if sym in registry and registry[sym] != head.lower():
        if head.lower() == "fortress" and registry[sym] == "day_trade":
            pass
        elif head.lower() == "hft" and registry[sym] in ("fortress", "weekly", "longterm"):
            # HFT may overlay swing inventory — exits MUST use sellable_qty_for_head
            pass
        elif head.lower() in ("day_trade", "micro_scalp") and registry[sym] in (
            "fortress",
            "weekly",
            "longterm",
        ):
            return False, f"overnight_protected_{registry[sym]}"
        else:
            return False, f"owned_by_{registry[sym]}"
    try:
        from alpaca_broker import pending_buy_order

        if pending_buy_order(sym):
            return False, "pending_buy"
    except Exception:
        pass
    total = live_position_count(positions=positions)
    if sym not in registry and total >= portfolio_max_total():
        return False, f"portfolio_full_{total}/{portfolio_max_total()}"
    head_n = count_by_head(head, positions=positions)
    if sym not in registry and head_n >= head_max_slots(head):
        return False, f"{head}_full_{head_n}/{head_max_slots(head)}"
    return True, "ok"


def promote_day_trade_winner(
    symbol: str,
    *,
    pnl_pct: float,
    score: float = 0.0,
    hold_days: int | None = None,
) -> None:
    """After a green day-trade exit, queue for fortress 1d hold unless it falls."""
    if os.getenv("DAY_TRADE_PROMOTE_TO_FORTRESS", "true").lower() not in ("1", "true", "yes"):
        return
    min_pnl = float(os.getenv("DAY_TRADE_PROMOTE_MIN_PNL_PCT", "0.0005"))
    if pnl_pct < min_pnl:
        return
    sym = str(symbol).strip().upper()
    days = hold_days if hold_days is not None else int(os.getenv("FORTRESS_HOLD_DAYS", "1"))
    doc = _load_json(PROMOTE_FILE)
    promos = dict(doc.get("promote") or {})
    promos[sym] = {
        "pnl_pct": pnl_pct,
        "score": score,
        "hold_days": days,
        "promoted_utc": datetime.now(timezone.utc).isoformat(),
        "expires_utc": datetime.now(timezone.utc).timestamp() + days * 86400,
    }
    doc["promote"] = promos
    doc["updated_utc"] = datetime.now(timezone.utc).isoformat()
    _save_json(PROMOTE_FILE, doc)
    register_symbol(sym, "fortress")


def promoted_symbols(*, active_only: bool = True) -> dict[str, dict[str, Any]]:
    promos = dict(_load_json(PROMOTE_FILE).get("promote") or {})
    if not active_only:
        return promos
    now = time.time()
    return {s: m for s, m in promos.items() if float(m.get("expires_utc") or 0) > now}


def clear_promotion(symbol: str) -> None:
    sym = str(symbol).strip().upper()
    doc = _load_json(PROMOTE_FILE)
    promos = dict(doc.get("promote") or {})
    promos.pop(sym, None)
    doc["promote"] = promos
    _save_json(PROMOTE_FILE, doc)


def fortress_promote_boost(symbol: str) -> float:
    """Score boost for fortress when day-trade handed off a winner."""
    if symbol.upper() not in promoted_symbols():
        return 0.0
    return float(os.getenv("FORTRESS_PROMOTE_SCORE_BOOST", "0.12"))
