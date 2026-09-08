"""Bull / bear market score — strong input to the real trading algorithm.

Combines SPY regime (EMA stack), VIX, FRED macro, and optional HMM tilt.
Does not call external LLMs; uses live market data already in the stack.

Env:
- USE_BULL_BEAR_ADJUST=true
- BULL_BEAR_P_MAX=0.06   max |Δp_up| from market regime
- BULL_BEAR_EXEC_MAX=0.05
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np

from regime_detector import Regime, RegimeState


def bull_bear_enabled() -> bool:
    return os.getenv("USE_BULL_BEAR_ADJUST", "true").lower() in ("1", "true", "yes")


def analyze_bull_bear_market(
    regime: RegimeState,
    macro_bundle: dict | None = None,
    hmm_market_score: float = 0.0,
) -> dict[str, Any]:
    """Return score in [-1, 1] and label BULL / BEAR / NEUTRAL."""
    score = 0.0
    if regime.name == Regime.BULL_TREND:
        score += 0.42
    elif regime.name == Regime.BEAR_TREND:
        score -= 0.42
    elif regime.name == Regime.HIGH_VOL_RANGE:
        score -= 0.12
    else:
        score += 0.05

    vix = float(regime.vix)
    if vix >= 30:
        score -= 0.28
    elif vix >= 22:
        score -= 0.12
    elif vix <= 14:
        score += 0.08

    macro = float((macro_bundle or {}).get("macro_score") or 0.0)
    score += 0.18 * float(np.clip(macro, -1.0, 1.0))
    score += 0.12 * float(np.clip(hmm_market_score, -1.0, 1.0))
    score = float(np.clip(score, -1.0, 1.0))

    if score >= 0.18:
        label = "BULL"
        read = "bull market tilt — favor long setups, still capped probability"
    elif score <= -0.18:
        label = "BEAR"
        read = "bear market tilt — tighter long bar, size down"
    else:
        label = "NEUTRAL"
        read = "mixed / range — no strong market direction"

    return {
        "bull_bear_score": score,
        "bull_bear_label": label,
        "bull_bear_read": read,
        "regime": regime.name.value,
        "vix": vix,
        "macro_score": macro,
        "hmm_market_score": float(hmm_market_score),
    }


def apply_bull_bear_to_p_up(p_up: float, bull_bear: dict[str, Any]) -> tuple[float, float]:
    """Adjust p_up and return (new_p_up, delta)."""
    p0 = float(np.clip(p_up, 1e-9, 1.0 - 1e-9))
    if not bull_bear_enabled():
        return p0, 0.0
    s = float(bull_bear.get("bull_bear_score", 0.0))
    p_max = float(os.getenv("BULL_BEAR_P_MAX", "0.06"))
    delta = p_max * s
    return float(np.clip(p0 + delta, 0.0, 1.0)), float(delta)


def apply_bull_bear_to_exec(exec_conf: float, bull_bear: dict[str, Any]) -> tuple[float, float]:
    e0 = float(np.clip(exec_conf, 0.0, 1.0))
    if not bull_bear_enabled():
        return e0, 0.0
    s = float(bull_bear.get("bull_bear_score", 0.0))
    e_max = float(os.getenv("BULL_BEAR_EXEC_MAX", "0.05"))
    delta = e_max * s
    return float(np.clip(e0 + delta, 0.0, 1.0)), float(delta)


def bull_bear_rank_boost(bull_bear: dict[str, Any]) -> float:
    if not bull_bear_enabled():
        return 0.0
    return float(np.tanh(float(bull_bear.get("bull_bear_score", 0.0)) * 1.4))
