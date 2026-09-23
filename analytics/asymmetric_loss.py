"""Asymmetric loss for online weight updates (Phase 8 of online-RL plan).

We treat every closed trade as a single labeled example: we know the action taken
(LONG / SHORT) and the realized return. Penalty multipliers are intentionally larger
than reward multipliers so the agent learns "precision over volume".

Env knobs:
- ASYM_REWARD_SCALE     default 1.0   -- payout for correct directional trades
- ASYM_PENALTY_LONG     default 5.0   -- multiplier on losses from failed longs
- ASYM_PENALTY_SHORT    default 10.0  -- multiplier on losses from failed shorts
- ASYM_FRICTION         default 0.0001 -- fixed friction subtracted each trade
- ASYM_TIME_DECAY       default 0.0   -- penalty per held bar when |return|<eps
- ASYM_REWARD_CLIP      default 5.0   -- clip reward to [-clip, +clip]
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass


@dataclass
class AsymRewardBreakdown:
    reward: float
    raw_return: float
    side: str
    correct: bool
    friction: float
    time_decay: float
    components: dict


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def asymmetric_reward(
    side: str,
    realized_return: float,
    bars_held: int = 1,
    *,
    position_pnl: bool | None = None,
) -> AsymRewardBreakdown:
    """Compute reward signal for a single closed trade.

    side: "LONG" or "SHORT"
    realized_return: either the position P&L fraction (positive = the leg made money,
        regardless of side — e.g. Alpaca ``unrealized_plpc``) or the underlying signed
        price return (e.g. ``fwd_1d_return``); which one is controlled by ``position_pnl``.
    bars_held: number of bars the position was held (used for time-decay penalty)
    position_pnl: True  -> ``realized_return`` is already position P&L (no sign flip).
                  False -> ``realized_return`` is a price return; SHORT is sign-flipped.
                  None  -> fall back to env ``ASYM_POSITION_PNL`` (default true).
    """
    side_u = side.upper().strip()
    if side_u not in ("LONG", "SHORT"):
        return AsymRewardBreakdown(
            reward=0.0,
            raw_return=float(realized_return),
            side=side_u,
            correct=False,
            friction=0.0,
            time_decay=0.0,
            components={"error": "unknown_side"},
        )

    reward_scale = _f("ASYM_REWARD_SCALE", 1.0)
    pen_long = _f("ASYM_PENALTY_LONG", 5.0)
    pen_short = _f("ASYM_PENALTY_SHORT", 10.0)
    friction = _f("ASYM_FRICTION", 0.0001)
    time_decay_per_bar = _f("ASYM_TIME_DECAY", 0.0)
    clip = _f("ASYM_REWARD_CLIP", 5.0)

    # ASYM_POSITION_PNL=true (default): realized_return is broker position P&L
    # (Alpaca unrealized_plpc / closed P&L already positive when the leg made money).
    # false: realized_return is underlying price return — SHORT needs a sign flip.
    if position_pnl is None:
        pos_pnl = os.getenv("ASYM_POSITION_PNL", "true").lower() not in ("0", "false", "no")
    else:
        pos_pnl = bool(position_pnl)
    if pos_pnl:
        signed = float(realized_return)
    else:
        direction = 1.0 if side_u == "LONG" else -1.0
        signed = float(realized_return) * direction
    correct = signed > 0.0

    if correct:
        base = reward_scale * signed
    else:
        mult = pen_long if side_u == "LONG" else pen_short
        base = mult * signed

    time_pen = 0.0
    if abs(realized_return) < 1e-6 and bars_held > 1:
        time_pen = time_decay_per_bar * float(bars_held - 1)

    out = base - friction - time_pen
    if math.isnan(out) or math.isinf(out):
        out = -friction

    out = max(-clip, min(clip, out))

    return AsymRewardBreakdown(
        reward=float(out),
        raw_return=float(realized_return),
        side=side_u,
        correct=bool(correct),
        friction=float(friction),
        time_decay=float(time_pen),
        components={
            "base": float(base),
            "reward_scale": reward_scale,
            "pen_long": pen_long,
            "pen_short": pen_short,
            "clip": clip,
        },
    )
