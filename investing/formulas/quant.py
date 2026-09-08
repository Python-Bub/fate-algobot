"""
Quantitative portfolio formulas (CAPM, Sharpe, Kelly, Fama-French).
"""

from __future__ import annotations

import numpy as np


def capm_expected_return(rf: float, beta: float, rm: float) -> float:
    """CAPM: E[R] = r_f + β × (R_m − r_f)."""
    rf = float(rf)
    beta = float(beta)
    rm = float(rm)
    return rf + beta * (rm - rf)


def sharpe_ratio(excess_return: float, vol: float) -> float:
    """Sharpe = excess return / volatility (annualized inputs)."""
    excess = float(excess_return)
    vol = float(vol)
    if vol <= 0:
        return 0.0
    return excess / vol


def sortino_ratio(excess: float, downside_vol: float) -> float:
    """Sortino = excess return / downside deviation."""
    excess = float(excess)
    dvol = float(downside_vol)
    if dvol <= 0:
        return 0.0
    return excess / dvol


def kelly_fraction(edge: float, odds: float) -> float:
    """
    Kelly criterion: f* = edge / odds, clamped to [0, 1].

    edge = win probability advantage; odds = net odds received per unit risked.
    """
    edge = float(edge)
    odds = float(odds)
    if odds <= 0:
        return 0.0
    return float(np.clip(edge / odds, 0.0, 1.0))


def inverse_vol_weights(vols: list[float]) -> list[float]:
    """
    Naive risk-parity weights: w_i ∝ 1/σ_i, normalized to sum 1.

    Returns equal weights when all vols are zero or missing.
    """
    if not vols:
        return []
    inv = [1.0 / max(float(v), 1e-12) for v in vols]
    total = sum(inv)
    if total <= 0:
        n = len(vols)
        return [1.0 / n] * n
    return [w / total for w in inv]


def fama_french_expected(
    rf: float,
    beta_m: float,
    mkt_prem: float,
    beta_s: float,
    smb: float,
    beta_v: float,
    hml: float,
) -> float:
    """
    Fama-French 3-factor expected return:

    E[R] = r_f + β_m×MKT + β_s×SMB + β_v×HML
    """
    rf = float(rf)
    return rf + float(beta_m) * float(mkt_prem) + float(beta_s) * float(smb) + float(beta_v) * float(hml)


def factor_tilt_score(
    *,
    pb: float,
    pe: float,
    mcap: float,
    mom_12_1: float,
    roe: float,
) -> float:
    """
    Composite factor tilt in [-1, 1]: value / size / momentum / quality.

    Low P/B and P/E ⇒ value; small cap ⇒ size; positive mom ⇒ momentum; high ROE ⇒ quality.
    """
    pb = float(pb)
    pe = float(pe)
    mcap = float(mcap)
    mom = float(mom_12_1)
    roe = float(roe)
    value = 0.0
    if pb > 0:
        value += 0.5 * np.tanh((2.0 - pb) / 2.0)
    if pe > 0:
        value += 0.5 * np.tanh((20.0 - pe) / 20.0)
    size = np.tanh((1e11 - mcap) / 1e11) if mcap > 0 else 0.0
    momentum = np.tanh(mom * 3.0)
    quality = np.tanh(roe * 4.0)
    score = 0.30 * value + 0.20 * size + 0.25 * momentum + 0.25 * quality
    return float(np.clip(score, -1.0, 1.0))
