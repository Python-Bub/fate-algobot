"""Pre-trade compliance guardrails (US-focused baseline checks).

This is not legal advice; it is an automated safety layer to reduce obvious
regulatory/operational violations before orders are routed.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crypto_universe import is_crypto_symbol


@dataclass
class ComplianceDecision:
    ok: bool
    reason: str
    details: dict


JOURNAL_CSV = Path(os.getenv("TRADE_JOURNAL_CSV", "data/journal/trades.csv"))


def _rolling_day_trades(days: int = 5) -> int:
    if not JOURNAL_CSV.is_file():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows: list[dict] = []
    try:
        with open(JOURNAL_CSV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append(r)
    except Exception:
        return 0
    # crude day-trade proxy: buy+sell on same symbol same UTC date
    by_key: dict[tuple[str, str], set[str]] = {}
    for r in rows:
        try:
            ts = datetime.fromisoformat(str(r.get("ts", "")))
        except Exception:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < cutoff:
            continue
        sym = str(r.get("symbol", "")).upper()
        side = str(r.get("side", "")).upper()
        key = (sym, ts.date().isoformat())
        by_key.setdefault(key, set()).add(side)
    return sum(1 for _, sides in by_key.items() if "BUY" in sides and "SELL" in sides)


def pretrade_check(
    symbol: str,
    side: str,
    qty: float,
    notional: float,
    *,
    is_short: bool = False,
    equity: float | None = None,
) -> ComplianceDecision:
    s = symbol.strip().upper()
    side_u = side.strip().upper()
    eq = float(equity if equity is not None else os.getenv("PAPER_EQUITY", "100000"))

    # 1) Asset-class hard blocks
    if is_short and is_crypto_symbol(s):
        return ComplianceDecision(
            ok=False,
            reason="crypto_short_blocked",
            details={"symbol": s, "regime": "alpaca_spot_crypto_no_short"},
        )

    # 2) Hard max order notional (fast local backstop — before any network checks)
    hard_max = float(os.getenv("HARD_MAX_ORDER_NOTIONAL", "0") or 0)
    if hard_max <= 0:
        hard_max = float(os.getenv("MAX_ORDER_NOTIONAL", "0") or 0)
    if hard_max > 0 and float(notional) > hard_max + 1e-6:
        return ComplianceDecision(
            ok=False,
            reason="hard_max_order",
            details={"notional": notional, "hard_max": hard_max},
        )

    # 3) Position concentration cap — ALWAYS vs live equity (never 4× buying power).
    cap_base = eq
    try:
        from alpaca_broker import get_account

        acct = get_account() or {}
        live_eq = float(acct.get("equity") or acct.get("last_equity") or 0.0)
        if live_eq > 0:
            cap_base = live_eq
    except Exception:
        pass
    max_frac = min(
        float(os.getenv("MAX_SINGLE_POSITION_FRAC", "0.10")),
        float(os.getenv("FORTRESS_MAX_SINGLE_FRAC", "0.10")),
        float(os.getenv("MAX_SINGLE_ASSET_FRAC", "0.10")),
    )
    try:
        if is_crypto_symbol(s):
            max_frac = float(os.getenv("FORTRESS_CRYPTO_MAX_SINGLE_FRAC", "0.18"))
    except Exception:
        pass
    if cap_base > 0 and float(notional) > cap_base * max_frac * 1.02:
        return ComplianceDecision(
            ok=False,
            reason="position_too_large",
            details={"notional": notional, "cap_base": cap_base, "max_frac": max_frac},
        )

    # 4) Legacy PDT day-trade count guard (Alpaca removed PDT rule in 2026).
    # Default off — Alpaca pre-trade checks reject margin deficits; we size via buying_power.
    legacy_pdt = os.getenv("ALPACA_LEGACY_PDT_GUARD", "false").lower() in ("1", "true", "yes")
    if legacy_pdt and os.getenv("USE_REAL_MONEY", "false").lower() in ("1", "true", "yes"):
        if eq < float(os.getenv("PDT_MIN_EQUITY", "25000")):
            dt = _rolling_day_trades(days=5)
            if dt >= int(os.getenv("PDT_MAX_DAY_TRADES", "3")) and side_u in ("BUY", "SELL"):
                return ComplianceDecision(
                    ok=False,
                    reason="pdt_risk_block",
                    details={"equity": eq, "rolling_5d_day_trades": dt},
                )

    # 5) Context-aware pre-trade risk (M&A, earnings, sympathy, stabilization)
    if side_u == "BUY":
        try:
            from intel.algo_risk_filter import blocks_buy

            blocked, risk_reason = blocks_buy(s)
            if blocked and os.getenv("FORTRESS_IGNORE_SYMPATHY_RISK", "false").lower() in (
                "1",
                "true",
                "yes",
            ):
                rl = str(risk_reason).lower()
                if "sympathy" in rl or "earnings in" in rl or "near-term" in rl:
                    blocked = False
            if blocked and os.getenv("PAPER_RELAX_ALGO_RISK", "true").lower() in ("1", "true", "yes"):
                blocked = False
            if blocked:
                return ComplianceDecision(
                    ok=False,
                    reason="algo_risk_block",
                    details={"symbol": s, "risk_reason": risk_reason},
                )
        except Exception:
            pass

    # 6) Basic sanity
    if qty <= 0 and notional <= 0:
        return ComplianceDecision(ok=False, reason="invalid_size", details={"qty": qty, "notional": notional})

    return ComplianceDecision(ok=True, reason="ok", details={"symbol": s, "side": side_u})


def as_dict(d: ComplianceDecision) -> dict:
    return asdict(d)

