"""
RL trading agent — spike-encoded market state, motor neuron actions, reward-modulated STDP.

Sensory spikes  →  association cortex  →  motor clusters (buy / hold / sell bias)
Profit          →  reinforcing signal (positive reward → strengthen active synapses)
Loss / lag SPY  →  punishment signal (negative reward → weaken pathways)
"""

from __future__ import annotations

import math
import os
from typing import Any


def encode_spikes(ctx: dict[str, Any]) -> dict[str, float]:
    """Map market features to sensory neuron drive (Poisson-rate proxy in [0,1])."""
    alpha = float(ctx.get("alpha") or 0.0)
    hit = float(ctx.get("hit_rate", 0.5) or 0.5)
    deployed = float(ctx.get("deployed_frac", 0.0) or 0.0)
    pnl = float(ctx.get("paper_pnl", 0.0) or 0.0)
    neural_p = ctx.get("neural_p_up")
    rsi = float(ctx.get("rsi_14", 50.0) or 50.0)
    mom = float(ctx.get("momentum_5d", 0.0) or 0.0)
    dd = float(ctx.get("drawdown", 0.0) or 0.0)

    def rate(x: float) -> float:
        return max(0.0, min(1.0, 0.5 + 0.5 * math.tanh(x)))

    spikes = {
        "s_alpha": rate(alpha * 15.0),
        "s_hit_rate": rate((hit - 0.5) * 3.0),
        "s_deployed": rate(deployed * 2.0 - 0.5),
        "s_paper_pnl": rate(math.tanh(pnl / 4000.0)),
        "s_neural_p": rate((float(neural_p) - 0.5) * 3.0) if neural_p is not None else 0.5,
        "s_rsi": rate((rsi - 50.0) / 40.0),
        "s_momentum": rate(mom * 8.0),
        "s_drawdown": rate(-dd * 5.0),
        "s_hft_pulse": rate(float(ctx.get("hft_pulse", 0.5)) * 2.0 - 0.5),
    }
    return spikes


def decode_action(motor: dict[str, float]) -> str:
    """Motor cluster dominance → discrete trade intent."""
    buy = float(motor.get("buy_bias", 0.0)) + float(motor.get("rank_tilt", 0.0))
    sell = -float(motor.get("paper_boost", 0.0)) if float(motor.get("paper_boost", 0)) < 0 else 0.0
    if buy > 0.04 and buy > abs(sell):
        return "BUY"
    if sell > 0.04:
        return "SELL"
    return "HOLD"


def compute_rl_reward(ctx: dict[str, Any], *, goal_deploy: float = 0.88) -> float:
    """
    Reward signal for STDP / Hebbian plasticity.
    Primary: grow portfolio equity. Secondary: beat SPY, deploy capital safely.
    """
    alpha = ctx.get("alpha")
    hit = float(ctx.get("hit_rate", 0.5) or 0.5)
    deployed = float(ctx.get("deployed_frac", 0.0) or 0.0)
    pnl = float(ctx.get("paper_pnl", 0.0) or 0.0)
    dd = float(ctx.get("drawdown", 0.0) or 0.0)

    # Objective engine reward (equity growth) when available.
    try:
        from self_modify.objective_engine import objective_reward

        obj_r = float(ctx.get("objective_reward") or objective_reward(ctx))
        r = obj_r * 0.70
    except Exception:
        r = 0.0

    if alpha is not None:
        r += float(alpha) * 4.0
    if hit > 0.5:
        r += (hit - 0.5) * 0.4
    r += math.tanh(pnl / 5000.0) * 0.20

    deploy_gap = goal_deploy - deployed
    deploy_penalty = 0.06 if alpha is not None else 0.02
    if deploy_gap > 0.2:
        r -= deploy_gap * deploy_penalty
    elif deployed >= goal_deploy - 0.08:
        r += 0.10

    if dd < -0.06:
        r -= min(0.4, abs(dd) * 2.0)

    eq_delta = float(ctx.get("equity_delta") or 0.0)
    if eq_delta > 0:
        r = max(r, 0.10)

    return max(-1.0, min(1.0, r))


def compute_awareness(firings: dict[str, Any]) -> float:
    """Network activation energy across layers → self-model awareness [0,1]."""
    layers = ("sensory", "association_top", "motor", "meta")
    energies: list[float] = []
    for layer in layers:
        block = firings.get(layer) or {}
        if not block:
            continue
        vals = [abs(float(v)) for v in block.values()]
        energies.append(sum(vals) / len(vals))
    if not energies:
        return 0.0
    raw = sum(energies) / len(energies)
    return max(0.0, min(1.0, raw))
