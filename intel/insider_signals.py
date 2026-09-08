"""Insider / C-suite sell detection — CEO sells tend to precede downside."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "intel" / "insider_signal_state.json"

C_SUITE_RE = re.compile(
    r"\b(ceo|chief executive|cfo|chief financial|coo|chief operating|"
    r"chief people|chief legal|chief technology|chief marketing|chief revenue|"
    r"chief product|chief strategy|chief commercial|chief human|"
    r"chief\s+\w+\s+officer|executive vice|senior vice|evp|svp|"
    r"president|chairman|chairwoman|chairperson|founder|director)\b",
    re.I,
)
SELL_RE = re.compile(r"\b(sale|sell|sold|disposition|gift|transfer)\b", re.I)
BUY_RE = re.compile(r"\b(buy|purchase|acquired|acquisition)\b", re.I)

_MEM: dict[str, Any] | None = None
_TX_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _enabled() -> bool:
    return os.getenv("ENABLE_INSIDER_PROXY", "true").lower() in ("1", "true", "yes")


def _cache_ttl() -> int:
    return int(os.getenv("INSIDER_TX_CACHE_SEC", "3600"))


def _load_state() -> dict[str, Any]:
    global _MEM
    if _MEM is not None:
        return _MEM
    if not STATE_PATH.is_file():
        _MEM = {"version": 1, "symbols": {}, "global": {"sell_hit_rate": 0.55}}
        return _MEM
    try:
        _MEM = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        _MEM = {"version": 1, "symbols": {}, "global": {"sell_hit_rate": 0.55}}
    return _MEM


def _save_state(doc: dict[str, Any]) -> None:
    global _MEM
    doc["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_PATH)
    _MEM = doc


def _parse_tx_row(row: dict[str, Any], cols: dict[str, str]) -> dict[str, Any] | None:
    shares_col = cols.get("shares") or cols.get("shares traded")
    action_col = cols.get("transaction") or cols.get("transaction text")
    owner_col = cols.get("insider") or cols.get("owner") or cols.get("name")
    date_col = cols.get("start date") or cols.get("date") or cols.get("filing date")
    if not shares_col or not action_col:
        return None
    shares = abs(float(row.get(shares_col, 0) or 0))
    if shares <= 0:
        return None
    action = str(row.get(action_col, ""))
    title = str(row.get(owner_col, "") or "")
    dt_raw = row.get(date_col) if date_col else None
    dt = None
    if dt_raw is not None:
        try:
            dt = datetime.fromisoformat(str(dt_raw)[:10]).replace(tzinfo=timezone.utc)
        except Exception:
            dt = None
    is_sell = bool(SELL_RE.search(action)) and not BUY_RE.search(action)
    is_buy = bool(BUY_RE.search(action)) and not SELL_RE.search(action)
    if not is_sell and not is_buy:
        is_sell = "sale" in action.lower() or "sell" in action.lower()
        is_buy = "buy" in action.lower() or "purchase" in action.lower()
    return {
        "shares": shares,
        "is_sell": is_sell and not is_buy,
        "is_buy": is_buy and not is_sell,
        "title": title,
        "action": action,
        "date": dt,
        "is_c_suite": bool(C_SUITE_RE.search(title)),
    }


def fetch_insider_transactions(ticker: str, *, max_rows: int = 50) -> list[dict[str, Any]]:
    """Yahoo insider transactions normalized for scoring."""
    sym = ticker.strip().upper()
    if not sym:
        return []
    now = time.time()
    cached = _TX_CACHE.get(sym)
    if cached and now - cached[0] < _cache_ttl():
        return list(cached[1])

    out: list[dict[str, Any]] = []
    try:
        import yfinance as yf

        tx = None
        tk = yf.Ticker(sym)
        try:
            tx = tk.get_insider_transactions()
        except Exception:
            tx = getattr(tk, "insider_transactions", None)
        if tx is None or len(tx) == 0:
            _TX_CACHE[sym] = (now, [])
            return []
        cols = {str(c).lower(): str(c) for c in tx.columns}
        for _, r in tx.head(max_rows).iterrows():
            parsed = _parse_tx_row(r.to_dict(), cols)
            if parsed:
                out.append(parsed)
    except Exception:
        out = []
    _TX_CACHE[sym] = (now, out)
    return out


def _recent_window_days() -> int:
    return int(os.getenv("INSIDER_LOOKBACK_DAYS", "45"))


def _material_sell_shares() -> float:
    return float(os.getenv("INSIDER_MATERIAL_SELL_SHARES", "5000"))


def assess_insider_flow(ticker: str, *, as_of: datetime | None = None) -> dict[str, Any]:
    """Return bearish/bullish insider pressure with optional hard block on C-suite sells."""
    sym = ticker.strip().upper()
    empty = {
        "ticker": sym,
        "enabled": _enabled(),
        "factor": 0.0,
        "score_delta": 0.0,
        "p_up_delta": 0.0,
        "block_long": False,
        "block_reason": None,
        "c_suite_sell_shares": 0.0,
        "recent_sell_shares": 0.0,
        "recent_buy_shares": 0.0,
        "events": [],
    }
    if not _enabled():
        return empty

    as_of = as_of or datetime.now(timezone.utc)
    cutoff = as_of - timedelta(days=_recent_window_days())
    txs = fetch_insider_transactions(sym)
    c_sell = 0.0
    sell_total = 0.0
    buy_total = 0.0
    events: list[dict[str, Any]] = []
    for tx in txs:
        dt = tx.get("date")
        if dt and dt < cutoff:
            continue
        sh = float(tx.get("shares") or 0)
        if tx.get("is_sell"):
            sell_total += sh
            if tx.get("is_c_suite"):
                c_sell += sh
            events.append({"type": "sell", "shares": sh, "title": tx.get("title"), "c_suite": tx.get("is_c_suite")})
        elif tx.get("is_buy"):
            buy_total += sh
            events.append({"type": "buy", "shares": sh, "title": tx.get("title"), "c_suite": tx.get("is_c_suite")})

    net = buy_total - sell_total
    denom = max(sell_total + buy_total, 1.0)
    raw = float(np.tanh(net / denom))
    if sell_total > buy_total * 1.5:
        raw = min(raw, -0.15 - 0.35 * min(1.0, sell_total / (denom * 2)))

    doc = _load_state()
    hit = float((doc.get("global") or {}).get("sell_hit_rate") or 0.55)
    c_mult = float(os.getenv("INSIDER_C_SUITE_SELL_MULT", "1.8"))
    if c_sell >= _material_sell_shares():
        raw = min(raw, -0.45 * c_mult * hit)

    block = False
    block_reason = None
    block_days = int(os.getenv("INSIDER_BLOCK_C_SUITE_DAYS", "14"))
    mat = _material_sell_shares()
    if c_sell >= mat:
        block = os.getenv("INSIDER_BLOCK_C_SUITE_SELLS", "true").lower() in ("1", "true", "yes")
        block_reason = f"C-suite insider sold {c_sell:,.0f} shares in last {_recent_window_days()}d"

    w_score = float(os.getenv("RANK_W_INSIDER", "0.14"))
    w_p = float(os.getenv("INSIDER_P_UP_DELTA_SCALE", "0.06"))
    return {
        **empty,
        "factor": raw,
        "score_delta": w_score * raw,
        "p_up_delta": w_p * raw,
        "block_long": block,
        "block_reason": block_reason,
        "c_suite_sell_shares": c_sell,
        "recent_sell_shares": sell_total,
        "recent_buy_shares": buy_total,
        "sell_hit_rate": hit,
        "events": events[:8],
        "block_window_days": block_days,
    }


def insider_flow_factor(ticker: str) -> float:
    """Fusion-compatible scalar in roughly [-1, 1]."""
    return float(assess_insider_flow(ticker).get("factor") or 0.0)


def learn_from_trade_outcome(
    ticker: str,
    realized_return: float,
    *,
    had_recent_insider_sell: bool | None = None,
) -> None:
    """Bayesian-ish update: insider sells that preceded losses reinforce bearish prior."""
    if not _enabled():
        return
    sym = ticker.strip().upper()
    doc = _load_state()
    g = doc.setdefault("global", {})
    hit = float(g.get("sell_hit_rate") or 0.55)
    lr = float(os.getenv("INSIDER_RL_LEARN_RATE", "0.04"))
    if had_recent_insider_sell is None:
        flow = assess_insider_flow(sym)
        had_recent_insider_sell = float(flow.get("recent_sell_shares") or 0) > float(
            flow.get("recent_buy_shares") or 0
        )
    if not had_recent_insider_sell:
        return
    ret = float(realized_return)
    if ret < 0:
        hit = min(0.85, hit + lr * (1.0 - hit))
    elif ret > 0.01:
        hit = max(0.35, hit - lr * hit * 0.5)
    g["sell_hit_rate"] = round(hit, 4)
    sym_row = (doc.setdefault("symbols", {})).setdefault(sym, {"n": 0, "sell_losses": 0})
    sym_row["n"] = int(sym_row.get("n") or 0) + 1
    if ret < 0:
        sym_row["sell_losses"] = int(sym_row.get("sell_losses") or 0) + 1
    _save_state(doc)


@lru_cache(maxsize=512)
def cached_insider_assessment(ticker: str) -> dict[str, Any]:
    return assess_insider_flow(ticker)
