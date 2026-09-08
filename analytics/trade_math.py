"""Causal trade math used by HFT, fortress rank, and bottom-fisher.

All functions are lookahead-free: they take already-observed scalars/series.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

LOGIT_EPS = 1e-9


def clip_prob(p: float) -> float:
    x = float(p)
    if not math.isfinite(x):
        return 0.5
    return min(1.0 - LOGIT_EPS, max(LOGIT_EPS, x))


def logit(p: float) -> float:
    p = clip_prob(p)
    return math.log(p / (1.0 - p))


def sigmoid(z: float) -> float:
    z = float(np.clip(z, -40.0, 40.0))
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def fuse_logits(pairs: Sequence[tuple[float, float]]) -> float:
    """Weighted logit fusion. pairs = [(prob, weight), ...]. Weights need not sum to 1."""
    num = 0.0
    den = 0.0
    for p, w in pairs:
        ww = float(w)
        if ww <= 0:
            continue
        num += ww * logit(p)
        den += ww
    if den <= 0:
        return 0.5
    return sigmoid(num / den)


def expected_bps(
    p_up: float,
    *,
    tp_bps: float,
    stop_bps: float | None = None,
    cost_bps: float = 0.0,
) -> float:
    """Expected edge in bps.

    Default (stop_bps is None): scalp math — you always pay `cost`, and with
    probability p you collect `tp`. A miss is not a second full stop.
      E = p·tp − cost

    Two-sided (stop set): E = p·tp − (1−p)·stop − cost
    """
    p = clip_prob(p_up)
    tp = max(0.0, float(tp_bps))
    cost = float(cost_bps)
    if stop_bps is None:
        return p * tp - cost
    return p * tp - (1.0 - p) * max(0.0, float(stop_bps)) - cost


def kelly_fraction(p_up: float, payoff_odds: float, *, fraction: float = 0.25) -> float:
    """Fractional Kelly. payoff_odds = net win / net loss (b in Kelly)."""
    p = clip_prob(p_up)
    b = float(payoff_odds)
    if b <= 0:
        return 0.0
    f = (b * p - (1.0 - p)) / b
    return float(np.clip(f * float(fraction), 0.0, 1.0))


def should_enter(
    p_up: float,
    *,
    tp_bps: float,
    cost_bps: float,
    min_ev_bps: float = 0.5,
    min_p: float = 0.52,
    stop_bps: float | None = None,
) -> tuple[bool, dict[str, float]]:
    ev = expected_bps(p_up, tp_bps=tp_bps, stop_bps=stop_bps, cost_bps=cost_bps)
    p = clip_prob(p_up)
    ok = p >= float(min_p) and ev >= float(min_ev_bps)
    return ok, {"p": p, "ev_bps": ev, "min_ev_bps": float(min_ev_bps), "cost_bps": float(cost_bps)}


def zscore(x: Sequence[float], window: int = 20) -> float:
    arr = np.asarray(list(x), dtype=float)
    if arr.size < max(5, window // 2):
        return 0.0
    sl = arr[-int(window) :]
    sl = sl[np.isfinite(sl)]
    if sl.size < 5:
        return 0.0
    mu = float(sl.mean())
    sd = float(sl.std(ddof=1)) if sl.size > 2 else 0.0
    if sd < 1e-12:
        return 0.0
    return float((sl[-1] - mu) / sd)


def ou_half_life(log_prices: Sequence[float]) -> float:
    """Ornstein–Uhlenbeck half-life in bars via AR(1) on demeaned log-price.

    Δx_t = λ x_{t−1} + ε. Half-life = ln(2) / −ln(1+λ) when λ ∈ (−1, 0).
    Returns +inf (a large sentinel) when the series is not mean-reverting.
    """
    x = np.asarray(list(log_prices), dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 30:
        return 1e9
    x = x - float(x.mean())
    y = x[1:]
    z = x[:-1]
    den = float(np.dot(z, z))
    if den < 1e-18:
        return 1e9
    phi = float(np.dot(z, y) / den)
    if not (1e-6 < phi < 0.999):
        return 1e9
    return float(math.log(2.0) / -math.log(phi))


def falling_knife(ret_1d: float, ret_5d: float, ret_20d: float) -> bool:
    """True when short-horizon losses are still accelerating."""
    r1, r5, r20 = float(ret_1d), float(ret_5d), float(ret_20d)
    if r5 <= -0.08 and r1 < 0:
        return True
    if r20 <= -0.18 and r5 < r20 * 0.35:
        return True
    if r5 < -0.04 and r1 < r5 / 5.0 - 0.005:
        return True
    return False


def distress_score(
    *,
    ret_60d: float,
    ret_20d: float,
    ret_5d: float,
    ret_1d: float,
    drawdown_52w: float,
    rsi: float = 50.0,
    ou_hl: float = 1e9,
    dollar_vol: float = 0.0,
    min_dollar_vol: float = 500_000.0,
) -> float:
    """Higher = more beaten-down *and* statistically mean-reverting. Knives score ~0."""
    if dollar_vol < min_dollar_vol:
        return 0.0
    if falling_knife(ret_1d, ret_5d, ret_20d):
        return 0.0
    dd = abs(min(0.0, float(drawdown_52w)))
    mom = max(0.0, -float(ret_60d))
    rsi_os = max(0.0, (40.0 - float(rsi)) / 40.0)
    hl = float(ou_hl)
    hl_term = 1.0 if hl < 8 else (0.65 if hl < 20 else (0.35 if hl < 40 else 0.1))
    turn = 0.0
    if float(ret_5d) > float(ret_20d) + 0.01:
        turn = min(1.0, (float(ret_5d) - float(ret_20d)) * 8.0)
    raw = 0.38 * mom + 0.22 * dd + 0.18 * rsi_os + 0.12 * hl_term + 0.10 * turn
    return float(np.clip(raw, 0.0, 1.0))


def tpm_capacity(
    *,
    n_names: int,
    cooldown_s: float,
    orders_per_roundtrip: int = 2,
    cap_per_min: int = 200,
) -> dict[str, float]:
    """Theoretical OFI throughput. Does not invent tape — plumbing only."""
    cd = max(1e-6, float(cooldown_s))
    cycles = float(n_names) * (60.0 / cd)
    orders = cycles * float(orders_per_roundtrip)
    return {
        "n_names": float(n_names),
        "cooldown_s": cd,
        "cycles_per_min": cycles,
        "orders_per_min": orders,
        "capped_per_min": min(orders, float(cap_per_min)),
        "hits_cap": 1.0 if orders >= float(cap_per_min) * 0.95 else 0.0,
    }


def audit_trade_gates(
    *,
    dual_ok: bool,
    p_up: float,
    ev_bps: float,
    min_ev_bps: float,
    spread_ok: bool,
    already_long: bool,
    slot_ok: bool,
    tape_authentic: bool,
) -> dict[str, Any]:
    """Single place that says *why* a fire is allowed. Order matches live HFT."""
    reasons: list[str] = []
    if already_long:
        reasons.append("already_long")
    if not tape_authentic:
        reasons.append("thin_tape")
    if not dual_ok:
        reasons.append("no_dual_signal")
    if not spread_ok:
        reasons.append("spread")
    if p_up < 0.52:
        reasons.append("p_up")
    if ev_bps < min_ev_bps:
        reasons.append("ev")
    if not slot_ok:
        reasons.append("pace")
    return {"ok": len(reasons) == 0, "reasons": reasons, "ev_bps": float(ev_bps), "p_up": float(p_up)}
