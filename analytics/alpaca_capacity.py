"""Alpaca buying-power / equity mapping — paper and live share the same fields.

Never treat leftover buying_power as total portfolio capacity. Equity ≈
portfolio_value. Cash is the bleed/settlement guard. Crypto uses
non_marginable / crypto buying power when present.
"""

from __future__ import annotations

from typing import Any


def capacity_from_account(acct: dict | None) -> dict[str, Any]:
    a = acct or {}

    def _f(key: str, *alts: str) -> float:
        for k in (key, *alts):
            try:
                v = a.get(k)
                if v is None or v == "":
                    continue
                return float(v)
            except (TypeError, ValueError):
                continue
        return 0.0

    equity = _f("equity", "portfolio_value", "last_equity")
    portfolio_value = _f("portfolio_value", "equity")
    cash = _f("cash")
    bp = _f("buying_power")
    regt = _f("regt_buying_power", "buying_power")
    dtbp = _f("daytrading_buying_power")
    crypto_bp = _f("crypto_buying_power", "non_marginable_buying_power")
    if crypto_bp <= 0:
        crypto_bp = cash if cash > 0 else bp
    # Sizing budget for a new long: min of BP and a fraction of equity — never BP alone
    # if equity is the risk base.
    return {
        "equity": equity,
        "portfolio_value": portfolio_value if portfolio_value > 0 else equity,
        "cash": cash,
        "buying_power": bp,
        "regt_buying_power": regt,
        "daytrading_buying_power": dtbp,
        "crypto_buying_power": crypto_bp,
        "pattern_day_trader": bool(a.get("pattern_day_trader")),
        "multiplier": _f("multiplier") or 1.0,
        "currency": str(a.get("currency") or "USD"),
        "account_number": str(a.get("account_number") or ""),
        "status": str(a.get("status") or ""),
        "trading_blocked": bool(a.get("trading_blocked")),
        "pattern_day_trader_blocked": bool(a.get("trading_blocked") or a.get("account_blocked")),
    }


def size_budget_usd(cap: dict[str, Any], *, crypto: bool = False, max_frac: float = 0.10) -> float:
    """USD available for one new buy after Alpaca semantics."""
    eq = float(cap.get("equity") or 0.0)
    if crypto:
        raw = float(cap.get("crypto_buying_power") or cap.get("cash") or 0.0)
    else:
        raw = float(cap.get("buying_power") or cap.get("cash") or 0.0)
    cap_eq = max(0.0, eq * float(max_frac))
    if cap_eq <= 0:
        return max(0.0, raw)
    return max(0.0, min(raw, cap_eq if raw > cap_eq else raw))
