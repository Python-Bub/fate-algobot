"""
Income and dividend formulas (Gordon Growth Model, yield screens).
"""

from __future__ import annotations

import numpy as np


def gordon_growth_value(d1: float, r: float, g: float) -> float:
    """
    Gordon Growth Model: P₀ = D₁ / (r − g)

    Raises ValueError if g >= r (undefined / negative denominator).
    """
    d1 = float(d1)
    r = float(r)
    g = float(g)
    if g >= r:
        raise ValueError(f"perpetual growth g={g} must be < discount rate r={r}")
    return d1 / (r - g)


def dividend_yield(div: float, price: float) -> float:
    """Yield = annual dividend / price."""
    div = float(div)
    price = float(price)
    if price <= 0:
        return 0.0
    return div / price


def dividend_coverage(eps: float, dps: float) -> float:
    """
    Coverage = EPS / DPS.

    Values > 1 imply earnings cover the dividend; < 1 is unsustainable.
    """
    eps = float(eps)
    dps = float(dps)
    if dps <= 0:
        return float("inf") if eps > 0 else 0.0
    return eps / dps


def high_yield_score(yield_: float, payout: float, coverage: float) -> float:
    """
    High-yield tilt in [-1, 1] with dividend-trap penalty when payout > 1.

    Rewards attractive yield with sustainable payout and coverage.
    """
    y = float(yield_)
    payout = float(payout)
    cov = float(coverage)
    base = 0.50 * np.tanh(y * 15.0)
    sustain = 0.30 * np.tanh((1.0 - payout) * 2.0) if payout <= 1.0 else -0.40
    cov_score = 0.20 * np.tanh((cov - 1.0) * 2.0) if np.isfinite(cov) else -0.20
    trap_penalty = -0.50 if payout > 1.0 else 0.0
    return float(np.clip(base + sustain + cov_score + trap_penalty, -1.0, 1.0))
