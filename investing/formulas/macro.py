"""
Macro-economic formulas (real rates, Fisher, cycle scoring).
"""

from __future__ import annotations

import numpy as np


def real_rate(nominal: float, inflation: float) -> float:
    """Approximate real rate = nominal − inflation (both as decimals)."""
    return float(nominal) - float(inflation)


def fisher_equation(nominal: float, inflation: float) -> float:
    """
    Fisher equation (exact): (1 + r_nom) = (1 + r_real)(1 + π).

    Returns implied real rate r_real.
    """
    nom = float(nominal)
    infl = float(inflation)
    return (1.0 + nom) / (1.0 + infl) - 1.0


def cycle_score(
    pmi: float | None = None,
    vix: float | None = None,
    yield_curve_slope: float | None = None,
) -> float:
    """
    Soft business-cycle tilt in [-1, 1].

    PMI > 50 bullish; low VIX bullish; positive yield-curve slope bullish.
    Missing inputs are skipped.
    """
    parts: list[float] = []
    if pmi is not None:
        parts.append(float(np.tanh((float(pmi) - 50.0) / 10.0)))
    if vix is not None:
        parts.append(float(np.tanh((20.0 - float(vix)) / 15.0)))
    if yield_curve_slope is not None:
        parts.append(float(np.tanh(float(yield_curve_slope) * 50.0)))
    if not parts:
        return 0.0
    return float(np.clip(np.mean(parts), -1.0, 1.0))


def inflation_hedge_tilt(inflation_yoy: float) -> float:
    """
    Inflation hedge tilt in [-1, 1]: higher YoY inflation ⇒ tilt toward real assets.

    inflation_yoy as decimal (0.05 = 5%).
    """
    return float(np.clip(np.tanh(float(inflation_yoy) * 8.0), -1.0, 1.0))
