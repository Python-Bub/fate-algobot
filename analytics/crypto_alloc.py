"""50/50 crypto vs stocks using idle cash — never flatten the equity book.

Target: crypto market value → FORTRESS_CRYPTO_BOOK_FRAC of equity (default 50%).
New cash split: FORTRESS_NEW_CASH_CRYPTO_FRAC (default 50%) until the target.
Adds only. Existing stock longs stay.
"""

from __future__ import annotations

import os
from typing import Any

from crypto_universe import is_crypto_symbol


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        return default


def crypto_book_target() -> float:
    return min(0.80, max(0.05, _f("FORTRESS_CRYPTO_BOOK_FRAC", 0.50)))


def new_cash_crypto_frac() -> float:
    return min(0.90, max(0.10, _f("FORTRESS_NEW_CASH_CRYPTO_FRAC", 0.50)))


def position_crypto_mv(positions: list[dict[str, Any]] | None) -> float:
    tot = 0.0
    for p in positions or []:
        try:
            if is_crypto_symbol(str(p.get("symbol") or "")):
                tot += abs(float(p.get("market_value") or 0.0))
        except (TypeError, ValueError):
            continue
    return tot


def crypto_frac(equity: float, crypto_mv: float) -> float:
    eq = float(equity or 0.0)
    if eq < 1.0:
        return 0.0
    return max(0.0, float(crypto_mv) / eq)


def crypto_gap_usd(equity: float, crypto_mv: float) -> float:
    return max(0.0, crypto_book_target() * float(equity or 0.0) - float(crypto_mv or 0.0))


def new_cash_split(
    idle_cash: float,
    *,
    equity: float,
    crypto_mv: float,
) -> tuple[float, float]:
    """(crypto_budget, stock_budget) from idle cash. Stocks already held are not sold."""
    idle = max(0.0, float(idle_cash or 0.0))
    gap = crypto_gap_usd(equity, crypto_mv)
    if gap <= 1.0 or idle <= 0:
        return 0.0, idle
    crypto_b = min(idle * new_cash_crypto_frac(), gap)
    return crypto_b, max(0.0, idle - crypto_b)


def crypto_single_cap_usd(equity: float) -> float:
    """Per-coin cap for the 50/50 book — wider than the 10% equity single-name cap."""
    return max(0.0, float(equity or 0.0) * _f("FORTRESS_CRYPTO_MAX_SINGLE_FRAC", 0.18) * 0.995)


def overnight_crypto_scan() -> list[str]:
    """Every liquid Alpaca coin. An env list only prioritizes names, it does not replace the universe."""
    from crypto_universe import CRYPTO_YAHOO

    priority = [
        s.strip().upper()
        for s in os.getenv("FORTRESS_CRYPTO_OVERNIGHT_SCAN", "").split(",")
        if s.strip()
    ]
    return list(dict.fromkeys(priority + list(CRYPTO_YAHOO)))


def idle_new_crypto_notionals(
    leftover: float,
    *,
    equity: float,
    positions: list[dict[str, Any]],
    min_n: float,
    hard_max: float = 0.0,
    already: dict[str, float] | None = None,
) -> dict[str, float]:
    """Open *new* coins with leftover cash until the 50% crypto book is filled.

    Existing coin holds are sized by allocate_idle_cash_to_holds (18% cap).
    This only starts names not yet in the book (SOL after BTC/ETH are capped).
    """
    from crypto_universe import yahoo_symbol

    have = {str(k).replace("/", "-").upper(): float(v) for k, v in (already or {}).items()}
    held_mv: dict[str, float] = {}
    for p in positions or []:
        try:
            qty = float(p.get("qty") or 0)
        except (TypeError, ValueError):
            qty = 0.0
        if qty <= 0:
            continue
        raw = str(p.get("symbol") or "")
        if not is_crypto_symbol(raw):
            continue
        sym = yahoo_symbol(raw)
        try:
            held_mv[sym] = held_mv.get(sym, 0.0) + abs(float(p.get("market_value") or 0))
        except (TypeError, ValueError):
            continue
    crypto_mv = position_crypto_mv(positions)
    left = min(max(0.0, float(leftover)), crypto_gap_usd(equity, crypto_mv))
    cap = crypto_single_cap_usd(equity)
    out: dict[str, float] = {}
    for sym in overnight_crypto_scan():
        if left < float(min_n):
            break
        tu = str(sym).replace("/", "-").upper()
        mv = float(held_mv.get(tu) or 0.0)
        if mv > 1.0:
            continue
        cur = float(have.get(tu) or 0.0) + float(out.get(tu) or 0.0)
        room = max(0.0, cap - mv - cur)
        if hard_max > 0:
            room = min(room, max(0.0, float(hard_max) - cur))
        if room < float(min_n):
            continue
        chunk = min(left, room)
        out[tu] = chunk
        left -= chunk
    return out


def size_crypto_notional(
    proposed: float,
    *,
    equity: float,
    cash: float,
    crypto_mv: float,
) -> float:
    """Boost a crypto clip toward the 50/50 fill. Cap per name and remaining gap."""
    eq = max(1.0, float(equity or 0.0))
    gap = crypto_gap_usd(eq, crypto_mv)
    if gap <= 1.0:
        return min(float(proposed or 0.0), 0.02 * eq)
    crypto_b, _ = new_cash_split(cash, equity=eq, crypto_mv=crypto_mv)
    max_single = min(gap, _f("FORTRESS_CRYPTO_MAX_SINGLE_FRAC", 0.18) * eq, crypto_b)
    if max_single <= 0:
        return 0.0
    n = max(float(proposed or 0.0), min(max_single, crypto_b))
    return max(0.0, min(n, max_single))
