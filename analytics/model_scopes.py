"""
Per-model trade universes — HFT, fortress, and weekly sim must not share one ticker list.

HFT subsecond: liquid WS basket + optional REST-only names (Alpaca IEX ~12–14 WS symbols).
Fortress intraday: Monday playbook + rotating trained scan (not OBI-gated).
Weekly / longterm: paper-sim active universe (separate from HFT).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _split_csv(raw: str) -> list[str]:
    return [t.strip().upper() for t in (raw or "").split(",") if t.strip()]


def _unique_ordered(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in items:
        u = s.strip().upper()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def hft_ws_tickers() -> list[str]:
    """Alpaca IEX websocket subscribe list (trades + quotes). Keep ≤14 symbols."""
    raw = os.getenv(
        "OBI_TICKER_WHITELIST",
        "SPY,QQQ,IWM,NVDA,AMD,TSLA,MSFT,NFLX,AMZN",
    )
    max_n = int(os.getenv("HFT_WS_MAX_TICKERS", "14"))
    from fortress_universe import is_tradeable_equity

    out = [s for s in _split_csv(raw) if is_tradeable_equity(s)]
    return out[:max_n]


def hft_rest_tickers() -> list[str]:
    """REST mean-reversion scan — extra names not on the WS feed (no shared cap)."""
    extra = _split_csv(os.getenv("HFT_REST_TICKERS", ""))
    if not extra:
        return []
    ws = frozenset(hft_ws_tickers())
    from fortress_universe import is_tradeable_equity

    return [s for s in _unique_ordered(extra) if s not in ws and is_tradeable_equity(s)]


def hft_all_tickers() -> list[str]:
    """Full subsecond monitor set (WS + REST-only)."""
    return _unique_ordered(hft_ws_tickers() + hft_rest_tickers())


def fortress_playbook_tickers() -> list[str]:
    path = Path(os.getenv("MONDAY_PLAYBOOK_PATH", str(ROOT / "data" / "monday_playbook.json")))
    if not path.is_file():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        out: list[str] = []
        for p in doc.get("preorders") or []:
            t = str(p.get("ticker") or "").upper()
            if t:
                out.append(t)
        return _unique_ordered(out)
    except Exception:
        return []


def club_action_tickers() -> list[str]:
    """Autonomous: today's Cramer email + dynamically generated conviction picks."""
    out: list[str] = []
    out.extend(_split_csv(os.getenv("CLUB_ACTION_TICKERS", "")))
    try:
        from intel.club_conviction_engine import proven_pick_tickers

        out.extend(proven_pick_tickers())
    except Exception:
        pass
    try:
        from intel.morning_club_intel import load_latest

        doc = load_latest()
        top_buys = {str(x).upper() for x in (doc.get("top_buys") or [])}
        out.extend(top_buys)
        for sym, row in (doc.get("tickers") or {}).items():
            ab = float(row.get("ai_action_bias", row.get("action_bias", row.get("sentiment", 0))))
            if sym.upper() in top_buys or ab >= 0.38 or row.get("catalyst") == "earnings":
                out.append(sym.upper())
        out.extend(str(x).upper() for x in (doc.get("club_owns") or []))
    except Exception:
        pass
    return _unique_ordered(out)


def fortress_priority_tickers(*, include_held: bool = True) -> list[str]:
    """
    Fortress intraday priority — playbook picks + open legs.
    Never filtered through OBI_TICKER_WHITELIST.
    """
    from fortress_universe import is_tradeable_equity

    out: list[str] = []
    for s in club_action_tickers():
        if is_tradeable_equity(s):
            out.append(s)
    for s in fortress_playbook_tickers():
        if is_tradeable_equity(s):
            out.append(s)
    if include_held:
        try:
            from alpaca_broker import list_positions

            for p in list_positions():
                sym = str(p.get("symbol", "")).replace("/", "-").upper()
                qty = float(p.get("qty") or 0)
                if sym and qty > 0 and is_tradeable_equity(sym):
                    out.append(sym)
        except Exception:
            pass
    return _unique_ordered(out)


def weekly_sim_tickers() -> list[str]:
    """Weekly / longterm paper sim scope (trained active universe)."""
    try:
        from fortress_universe import apply_scan_order, symbols_paper_active_universe

        cap = int(os.getenv("WEEKLY_SIM_MAX_SYMBOLS", "0")) or None
        syms = apply_scan_order(symbols_paper_active_universe())
        if cap and cap > 0:
            syms = syms[:cap]
        return syms
    except Exception:
        return []


def day_trade_tickers(*, include_positions: bool = True) -> list[str]:
    """
    Day-trade universe — top 100 by market cap (trained names) + any open legs.
    Override with DAY_TRADE_TICKERS when DAY_TRADE_FULL_UNIVERSE=false.
    """
    explicit = _split_csv(os.getenv("DAY_TRADE_TICKERS", ""))
    if explicit and os.getenv("DAY_TRADE_FULL_UNIVERSE", "true").lower() not in ("1", "true", "yes"):
        from fortress_universe import is_tradeable_equity

        return [s for s in _unique_ordered(explicit) if is_tradeable_equity(s)]

    from fortress_universe import is_tradeable_equity, load_top100_symbols

    out: list[str] = []
    for s in club_action_tickers():
        if is_tradeable_equity(s):
            out.append(s)
    for s in load_top100_symbols():
        if is_tradeable_equity(s):
            out.append(s)
    if include_positions:
        try:
            from alpaca_broker import list_positions

            for p in list_positions():
                sym = str(p.get("symbol", "")).replace("/", "-").upper()
                if sym and float(p.get("qty") or 0) != 0 and is_tradeable_equity(sym):
                    out.append(sym)
        except Exception:
            pass
    cap = int(os.getenv("DAY_TRADE_MAX_SYMBOLS", "100"))
    return _unique_ordered(out)[:cap] if cap > 0 else _unique_ordered(out)


def models_share_ticker(sym: str) -> dict[str, bool]:
    """Debug: which models include symbol."""
    s = sym.upper()
    return {
        "hft": s in frozenset(hft_all_tickers()),
        "fortress_playbook": s in frozenset(fortress_playbook_tickers()),
        "weekly_sim": s in frozenset(weekly_sim_tickers()),
    }
