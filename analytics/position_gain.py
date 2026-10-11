"""Real unrealized gain. Ignore Alpaca cost-basis garbage.

Paper positions have shown avg_entry_price < 0 and unrealized_plpc of +100%
to +240% after a short flip (AAPL, GOOGL, META, MSFT on 2026-09-28). Those
figures are not profits. Using them unlocked HFT scalps and idle-cash adds
while the account equity was falling.
"""

from __future__ import annotations


def _f(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def sane_unrealized_gain(pos: dict, price: float | None = None) -> float | None:
    """Fractional gain from a trustworthy cost basis, else None.

    A negative avg entry is always garbage (short-flip residue). When price
    and a positive entry exist, the gain is (price - entry) / entry, including
    a real double. A broker percent above 50% with no agreeing price is
    dropped. A modest percent with no entry is kept so older payloads still
    size and exit.
    """
    entry = _f(pos.get("avg_entry_price"))
    px = _f(price) if price is not None else _f(pos.get("current_price"))
    from_px = ((px - entry) / entry) if entry > 0 and px > 0 else None
    raw = pos.get("unrealized_plpc")
    if entry < 0:
        return None
    g = None
    if raw is not None:
        parsed = _f(raw, default=float("nan"))
        if parsed == parsed:
            g = parsed
    if from_px is None:
        # No live mark. A modest broker percent is still usable; a +100%
        # print with nothing to check it against is not.
        if g is None or abs(g) > 0.50:
            return None
        return g
    # (price - entry) / entry is the gain. Trust it inside a normal move.
    if abs(from_px) <= 0.50:
        return from_px
    # A real double (or a real crash) is above 50%. Keep it when the broker
    # percent agrees, or when the broker percent is the wilder number.
    # Drop it when the price math is even wilder than the broker print —
    # that is a tiny garbage entry, not a 100x winner.
    if g is None:
        return from_px
    if abs(from_px - g) <= max(0.05, 0.25 * abs(g)):
        return from_px
    if abs(from_px) + 1e-9 < abs(g):
        return from_px
    return None


def is_phantom_cost_basis(pos: dict) -> bool:
    """True when reported P&L cannot be a real winner or loser."""
    if _f(pos.get("avg_entry_price")) < 0:
        return True
    raw = pos.get("unrealized_plpc")
    if raw is None:
        return False
    g = _f(raw, default=float("nan"))
    if g != g or abs(g) <= 0.50:
        return False
    return sane_unrealized_gain(pos) is None


def dust_close_qty(
    broker_qty: float,
    requested: float | None,
    market_value: float,
    *,
    dust_usd: float = 25.0,
) -> float:
    """Sell the whole leftover when a partial would nibble a dust lot.

    AAPL/GOOGL were sold at exactly 25% of the remaining shares every few
    minutes (sub-dollar clips) because a broken cost basis looked like a
    +100% winner. A position worth <= dust_usd closes in one ticket.
    """
    broker = abs(float(broker_qty or 0))
    if broker <= 0:
        return 0.0
    req = broker if requested is None else min(broker, abs(float(requested or 0)))
    mv = abs(float(market_value or 0))
    if mv > 0 and mv <= float(dust_usd) and req + 1e-8 < broker:
        return broker
    return req
