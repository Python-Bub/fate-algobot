"""Execution confidence: a *decision* score in [0, 1], separate from raw calibrated p_up.

NOT the same as:
- sentiment_intensity / news_factor ([-1,1] text weight — see intel/metric_semantics.py)
- options call delta (market-implied P above strike — see analytics/options_implied_prob.py)

Combines (1) extremity of the live probability in log-odds space and, only when
HORIZON_INDEPENDENT is off, (2) short-vs-long head agreement. Default is per-timeframe:
a 1d call does not need the 5d/20d heads to agree. Copies of the fused p still do not
count as agreement when agreement mode is on.
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np

from analytics.vector_math import (
    clip_prob,
    heads_are_independent,
    logit,
    sigmoid,
    signed_agreement,
)


def execution_confidence(
    p_up: float,
    p_short: float | None = None,
    p_long: float | None = None,
) -> tuple[float, dict[str, Any]]:
    p = float(clip_prob(p_up))
    certainty = abs(p - 0.5) * 2.0
    gain = float(os.getenv("EXEC_CERTAINTY_GAIN", "1.8"))
    # Map |ℓ| into [0,1] then mix with the legacy extremity ramp so old knobs still bite.
    ell_cert = float(min(1.0, abs(float(logit(p))) / 2.2))
    base = float(min(1.0, 0.5 + max(certainty, ell_cert) * gain))

    out = base
    try:
        from analytics.horizon_picks import horizon_independent as _horizon_independent

        tf_independent = _horizon_independent()
    except Exception:
        tf_independent = os.getenv("HORIZON_INDEPENDENT", "true").lower() in ("1", "true", "yes")
    default_agree = "0.0" if tf_independent else "0.60"
    w = float(os.getenv("EXEC_AGREE_BLEND", default_agree))
    agree_score = None
    independent = False
    # Per-timeframe mode: certainty of *this* p_up is enough. Cross-horizon
    # disagreement must not fail the dual gate.
    if (not tf_independent) and p_short is not None and p_long is not None and w > 0.0:
        independent = heads_are_independent(float(p_short), float(p_long), p)
        if independent:
            agree_score = signed_agreement(float(p_short), float(p_long), p)
            agree_mapped = 0.5 + 0.5 * agree_score
            # Log-odds mix of certainty vs agreement (Jaynes: evidence adds, p does not).
            out = float(
                sigmoid(
                    (1.0 - w) * float(logit(base)) + w * float(logit(agree_mapped))
                )
            )
            min_agree = float(os.getenv("EXEC_MIN_AGREE", "0.10"))
            if agree_score < min_agree:
                floor_fail = float(os.getenv("MIN_EXECUTION_CONFIDENCE", "0.62")) - 0.02
                out = float(min(out, max(0.0, floor_fail)))

    out = float(np.clip(out, 0.0, 1.0))
    diag = {
        "p_up": p,
        "certainty": float(certainty),
        "base": float(base),
        "p_short": p_short,
        "p_long": p_long,
        "agree_blend": float(w),
        "agree_score": agree_score,
        "independent_heads": independent,
        "horizon_independent": bool(tf_independent),
        "gain": float(gain),
    }
    return out, diag


def min_execution_confidence() -> float:
    return float(os.getenv("MIN_EXECUTION_CONFIDENCE", os.getenv("MIN_MODEL_CONFIDENCE", "0.62")))


def use_execution_confidence_gate() -> bool:
    return os.getenv("USE_EXECUTION_CONFIDENCE_GATE", "true").lower() in ("1", "true", "yes")


def confidence_gate_mode() -> str:
    """exec_only | dual | raw_only"""
    m = os.getenv("CONFIDENCE_GATE_MODE", "dual").strip().lower()
    if m not in ("exec_only", "dual", "raw_only"):
        return "dual"
    return m


def passes_confidence_gates(p_up: float, exec_conf: float, min_p: float, min_exec: float) -> bool:
    """Math floor: even in exec_only, reject clearly weak p_up (blocks dumb buys)."""
    mode = confidence_gate_mode()
    try:
        math_floor = float(os.getenv("MATH_P_UP_FLOOR", "0.48"))
    except (TypeError, ValueError):
        math_floor = 0.48
    if math_floor > 0 and float(p_up) < math_floor:
        return False
    if mode == "raw_only":
        return p_up >= min_p
    if mode == "dual":
        return p_up >= min_p and exec_conf >= min_exec
    return exec_conf >= min_exec


def passes_directional_gates(
    p_up: float,
    exec_conf: float,
    min_p: float,
    min_exec: float,
    *,
    allow_short: bool = False,
) -> bool:
    """Same dual/exec floors, but a high-confidence down can pass when shorts are allowed."""
    p = float(p_up)
    if p >= 0.5:
        return passes_confidence_gates(p, exec_conf, min_p, min_exec)
    if not allow_short:
        return False
    return passes_confidence_gates(1.0 - p, exec_conf, min_p, min_exec)
