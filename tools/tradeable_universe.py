"""Tickers we actually trade — not the full universe."""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _split_csv(raw: str) -> list[str]:
    return [t.strip().upper() for t in (raw or "").split(",") if t.strip()]


def _alpaca_position_symbols() -> list[str]:
    try:
        from alpaca_broker import list_positions

        out: list[str] = []
        for p in list_positions():
            sym = str(p.get("symbol", "")).replace("/", "-").upper()
            qty = float(p.get("qty") or 0)
            if sym and abs(qty) > 0:
                out.append(sym)
        return out
    except Exception:
        return []


def _monday_playbook_symbols() -> list[str]:
    path = Path(os.getenv("MONDAY_PLAYBOOK_PATH", str(ROOT / "data" / "monday_playbook.json")))
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        tickers = data.get("preorder_tickers") or data.get("tickers") or []
        return [str(t).upper() for t in tickers if t]
    except Exception:
        return []


def hft_trade_tickers(*, include_positions: bool = False, include_playbook: bool = False) -> list[str]:
    """
    Subsecond/HFT scope only — WS basket + REST extras (see analytics.model_scopes).
    Does NOT pull fortress playbook names (those are fortress-only).
    """
    from analytics.model_scopes import hft_all_tickers

    out = list(hft_all_tickers())
    if not include_positions and not include_playbook:
        return out

    from fortress_universe import is_tradeable_equity

    seen = frozenset(out)
    ordered = list(out)
    hft_set = seen

    def add(sym: str) -> None:
        s = sym.strip().upper()
        if not s or s in seen or not is_tradeable_equity(s) or s not in hft_set:
            return
        ordered.append(s)

    if include_positions:
        for s in _alpaca_position_symbols():
            add(s)
    if include_playbook:
        for s in _monday_playbook_symbols():
            add(s)
    return ordered


def fortress_trade_tickers(*, max_extra: int = 24) -> list[str]:
    """Fortress intraday scope: playbook + holdings — decoupled from HFT OBI list."""
    from analytics.model_scopes import fortress_priority_tickers

    return fortress_priority_tickers(include_held=True)
