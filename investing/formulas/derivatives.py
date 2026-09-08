"""
Options and derivatives pricing formulas (Black-Scholes, payoffs).
"""

from __future__ import annotations

import math


def norm_cdf(x: float) -> float:
    """Standard normal CDF via math.erf: Φ(x) = ½(1 + erf(x/√2))."""
    return 0.5 * (1.0 + math.erf(float(x) / math.sqrt(2.0)))


def _d1_d2(S: float, K: float, T: float, r: float, sigma: float, q: float) -> tuple[float, float]:
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0, 0.0
    sqrt_t = math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    return d1, d2


def black_scholes_call(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    q: float = 0.0,
) -> float:
    """
    Black-Scholes European call with continuous dividend yield q:

    C = S·e^(−qT)·Φ(d₁) − K·e^(−rT)·Φ(d₂)
    """
    S, K, T, r, sigma, q = float(S), float(K), float(T), float(r), float(sigma), float(q)
    if T <= 0:
        return max(S - K, 0.0)
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    return S * math.exp(-q * T) * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)


def black_scholes_put(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    q: float = 0.0,
) -> float:
    """
    Black-Scholes European put with continuous dividend yield q:

    P = K·e^(−rT)·Φ(−d₂) − S·e^(−qT)·Φ(−d₁)
    """
    S, K, T, r, sigma, q = float(S), float(K), float(T), float(r), float(sigma), float(q)
    if T <= 0:
        return max(K - S, 0.0)
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    return K * math.exp(-r * T) * norm_cdf(-d2) - S * math.exp(-q * T) * norm_cdf(-d1)


def covered_call_max_return(stock: float, premium: float, strike: float) -> float:
    """
    Max return on covered call if assigned: (strike − stock + premium) / stock.
    """
    stock = float(stock)
    if stock <= 0:
        return 0.0
    return (float(strike) - stock + float(premium)) / stock


def protective_put_floor(stock: float, put_premium: float, strike: float) -> float:
    """
    Effective floor return: (strike − stock − premium) / stock (can be negative).
    """
    stock = float(stock)
    if stock <= 0:
        return 0.0
    return (float(strike) - stock - float(put_premium)) / stock


def put_call_parity_check(
    C: float,
    P: float,
    S: float,
    K: float,
    r: float,
    T: float,
    q: float = 0.0,
) -> float:
    """
    Put-call parity residual: C − P − S·e^(−qT) + K·e^(−rT).

    Should be ≈ 0 for consistent prices.
    """
    C, P, S, K, r, T, q = float(C), float(P), float(S), float(K), float(r), float(T), float(q)
    return C - P - S * math.exp(-q * T) + K * math.exp(-r * T)


def iron_condor_max_profit(
    short_call_prem: float,
    short_put_prem: float,
    wing_widths: tuple[float, float],
) -> float:
    """
    Simple iron condor max profit = net credit collected.

    wing_widths = (call_spread_width, put_spread_width) for reference only;
    max profit equals premium received on short legs.
    """
    _ = wing_widths
    return float(short_call_prem) + float(short_put_prem)


def straddle_payoff(S_T: float, K: float, call_prem: float, put_prem: float) -> float:
    """
    Long straddle P&L at expiry: |S_T − K| − (call_prem + put_prem).
    """
    S_T, K = float(S_T), float(K)
    intrinsic = abs(S_T - K)
    return intrinsic - float(call_prem) - float(put_prem)


def norm_pdf(x: float) -> float:
    """Standard normal PDF φ(x)."""
    z = float(x)
    return math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)


def greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    q: float = 0.0,
    kind: str = "call",
) -> dict[str, float]:
    """Black–Scholes Greeks. Vega is per 1.00 vol (not per vol-point)."""
    S, K, T, r, sigma, q = (float(S), float(K), float(T), float(r), float(sigma), float(q))
    is_call = str(kind).lower() != "put"
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        intrinsic = max(S - K, 0.0) if is_call else max(K - S, 0.0)
        return {
            "delta": 1.0 if is_call and S > K else (-1.0 if (not is_call and S < K) else 0.0),
            "gamma": 0.0,
            "vega": 0.0,
            "theta": 0.0,
            "rho": 0.0,
            "price": intrinsic,
        }
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    disc_q = math.exp(-q * T)
    disc_r = math.exp(-r * T)
    n_d1 = norm_pdf(d1)
    sqrt_t = math.sqrt(T)
    gamma = disc_q * n_d1 / (S * sigma * sqrt_t)
    vega = S * disc_q * n_d1 * sqrt_t
    if is_call:
        delta = disc_q * norm_cdf(d1)
        theta = (
            -S * disc_q * n_d1 * sigma / (2.0 * sqrt_t)
            - r * K * disc_r * norm_cdf(d2)
            + q * S * disc_q * norm_cdf(d1)
        )
        rho = K * T * disc_r * norm_cdf(d2)
        price = black_scholes_call(S, K, T, r, sigma, q)
    else:
        delta = disc_q * (norm_cdf(d1) - 1.0)
        theta = (
            -S * disc_q * n_d1 * sigma / (2.0 * sqrt_t)
            + r * K * disc_r * norm_cdf(-d2)
            - q * S * disc_q * norm_cdf(-d1)
        )
        rho = -K * T * disc_r * norm_cdf(-d2)
        price = black_scholes_put(S, K, T, r, sigma, q)
    return {
        "delta": float(delta),
        "gamma": float(gamma),
        "vega": float(vega),
        "theta": float(theta),
        "rho": float(rho),
        "price": float(price),
    }


def implied_vol(
    market: float,
    S: float,
    K: float,
    T: float,
    r: float,
    q: float = 0.0,
    kind: str = "call",
    *,
    lo: float = 1e-4,
    hi: float = 5.0,
    steps: int = 48,
) -> float:
    """Bisection IV. Returns 0 when the quote is inside intrinsic / degenerate."""
    market = float(market)
    is_call = str(kind).lower() != "put"
    if T <= 0 or S <= 0 or K <= 0 or market <= 0:
        return 0.0
    intrinsic = max(S * math.exp(-q * T) - K * math.exp(-r * T), 0.0) if is_call else max(
        K * math.exp(-r * T) - S * math.exp(-q * T), 0.0
    )
    if market < intrinsic * 0.999:
        return 0.0
    pricer = black_scholes_call if is_call else black_scholes_put
    a, b = float(lo), float(hi)
    fa = pricer(S, K, T, r, a, q) - market
    fb = pricer(S, K, T, r, b, q) - market
    if fa * fb > 0:
        return float(hi) if fb < 0 else float(lo)
    for _ in range(int(steps)):
        mid = 0.5 * (a + b)
        fm = pricer(S, K, T, r, mid, q) - market
        if abs(fm) < 1e-8:
            return mid
        if fa * fm <= 0:
            b, fb = mid, fm
        else:
            a, fa = mid, fm
    return 0.5 * (a + b)


def moneyness(S: float, K: float) -> float:
    """log(S/K). ATM ≈ 0, OTM call negative."""
    S, K = float(S), float(K)
    if S <= 0 or K <= 0:
        return 0.0
    return math.log(S / K)


def calendar_spread_theta_edge(front_theta: float, back_theta: float) -> float:
    """Positive when the short front decays faster than the long back (credit calendars)."""
    return float(front_theta) - float(back_theta)


def futures_basis(futures: float, spot: float) -> float:
    """(F − S) / S. Contango positive."""
    spot = float(spot)
    if spot <= 0:
        return 0.0
    return (float(futures) - spot) / spot
