"""
Valuation and analysis formulas (WACC, EV, comps, scenarios, Monte Carlo).
"""

from __future__ import annotations

import math

import numpy as np


def wacc(re: float, rd: float, E: float, D: float, tax: float) -> float:
    """
    WACC = (E/(E+D))·r_e + (D/(E+D))·r_d·(1 − T).

    E = market value of equity; D = market value of debt; tax = corporate tax rate.
    """
    re, rd = float(re), float(rd)
    E, D, tax = float(E), float(D), float(tax)
    total = E + D
    if total <= 0:
        return re
    return (E / total) * re + (D / total) * rd * (1.0 - tax)


def enterprise_value(mcap: float, debt: float, cash: float) -> float:
    """EV = market cap + debt − cash."""
    return float(mcap) + float(debt) - float(cash)


def ev_ebitda(ev: float, ebitda: float) -> float:
    """EV/EBITDA multiple."""
    ebitda = float(ebitda)
    if ebitda <= 0:
        return float("inf")
    return float(ev) / ebitda


def pe_ratio(price: float, eps: float) -> float:
    """P/E = price / EPS."""
    eps = float(eps)
    if eps <= 0:
        return float("inf")
    return float(price) / eps


def comps_implied_price(peer_multiple: float, metric: float) -> float:
    """Implied price = peer multiple × company metric (e.g. EPS, EBITDA/share)."""
    return float(peer_multiple) * float(metric)


def sotp_equity(segment_values: list[float], net_debt: float) -> float:
    """Sum-of-the-parts equity value = Σ segment values − net debt."""
    return sum(float(v) for v in segment_values) - float(net_debt)


def conglomerate_discount(sotp_equity: float, market_cap: float) -> float:
    """
    Conglomerate discount = (SOTP equity − market cap) / SOTP equity.

    Positive ⇒ market trades below sum-of-parts.
    """
    sotp = float(sotp_equity)
    mcap = float(market_cap)
    if sotp <= 0:
        return 0.0
    return (sotp - mcap) / sotp


def margin_of_safety(intrinsic: float, price: float) -> float:
    """Buffer (IV − price) / IV. Positive ⇒ buy price below intrinsic."""
    iv = float(intrinsic)
    px = float(price)
    if iv <= 0 or px <= 0:
        return 0.0
    return float((iv - px) / iv)


def scenario_expected_value(outcomes: list[tuple[float, float]]) -> float:
    """
    Expected value = Σ p_i × v_i.

    outcomes: list of (probability, value) pairs; probabilities need not sum to 1.
    """
    return sum(float(p) * float(v) for p, v in outcomes)


def monte_carlo_mean_paths(
    mu: float,
    sigma: float,
    n_steps: int,
    n_paths: int,
    s0: float = 1.0,
    seed: int = 0,
) -> float:
    """
    GBM terminal mean: S_T = S_0 · exp((μ − σ²/2)·Δt + σ·√Δt·Z).

    Returns mean terminal value across n_paths (Δt = 1 per step).
    """
    rng = np.random.default_rng(seed)
    mu, sigma, s0 = float(mu), float(sigma), float(s0)
    n_steps = int(n_steps)
    n_paths = int(n_paths)
    if n_steps <= 0 or n_paths <= 0:
        return s0
    drift = (mu - 0.5 * sigma * sigma) * n_steps
    diffusion = sigma * math.sqrt(n_steps)
    z = rng.standard_normal(n_paths)
    terminals = s0 * np.exp(drift + diffusion * z)
    return float(np.mean(terminals))
