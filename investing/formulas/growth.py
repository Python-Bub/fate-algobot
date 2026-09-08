"""
Growth-investing formulas (PEG, GARP, quality compounders).

PEG = P/E ÷ EPS growth%   (growth as percent, e.g. 15 for 15%)
"""

from __future__ import annotations

import numpy as np


def peg_ratio(pe: float, eps_growth_pct: float) -> float:
    """
    PEG = PE / growth%

    growth is expressed as a percent (15 ⇒ 15% EPS growth).
    Returns inf when growth ≤ 0 (undefined / negative denominator).
    """
    pe = float(pe)
    g = float(eps_growth_pct)
    if g <= 0:
        return float("inf")
    return pe / g


def garp_score(pe: float, growth_pct: float, *, peg_max: float = 1.0) -> float:
    """
    GARP boost in [-1, 1] from PEG vs peg_max (default 1.0).

    PEG < peg_max ⇒ positive; PEG > peg_max ⇒ negative.
    """
    peg = peg_ratio(pe, growth_pct)
    if not np.isfinite(peg):
        return -1.0
    peg_max = max(float(peg_max), 1e-9)
    raw = (peg_max - peg) / peg_max
    return float(np.clip(raw, -1.0, 1.0))


def hypergrowth_score(rev_growth: float, earn_growth: float) -> float:
    """
    Hypergrowth composite in [-1, 1] from revenue and earnings growth (decimals).

    Uses tanh scaling for exceptional top-line and bottom-line acceleration.
    """
    rg = float(rev_growth)
    eg = float(earn_growth)
    score = 0.55 * np.tanh(rg * 3.0) + 0.45 * np.tanh(eg * 3.0)
    return float(np.clip(score, -1.0, 1.0))


def quality_growth_score(
    roe: float,
    pm: float,
    debt_to_equity: float,
    rev_growth: float,
) -> float:
    """
    Quality growth composite in [-1, 1].

    Blends ROE, profit margins, modest leverage, and revenue growth.
    """
    roe = float(roe)
    pm = float(pm)
    de = float(debt_to_equity)
    rg = float(rev_growth)
    score = (
        0.30 * np.tanh(roe * 4.0)
        + 0.25 * np.tanh(pm * 6.0)
        + 0.20 * np.tanh((150.0 - de) / 150.0)
        + 0.25 * np.tanh(rg * 3.0)
    )
    return float(np.clip(score, -1.0, 1.0))


def compounder_score(roe: float, earn_growth: float, payout: float) -> float:
    """
    Compounder tilt in [-1, 1]: high ROE + earnings growth + low payout.

    payout is dividend payout ratio (0–1); lower is better for reinvestment.
    """
    roe = float(roe)
    eg = float(earn_growth)
    payout = float(payout)
    low_payout = max(0.0, 1.0 - payout)
    score = (
        0.40 * np.tanh(roe * 4.0)
        + 0.35 * np.tanh(eg * 3.0)
        + 0.25 * np.tanh(low_payout * 2.0)
    )
    return float(np.clip(score, -1.0, 1.0))
