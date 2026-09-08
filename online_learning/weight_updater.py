"""Phase 11: single-step online weight editor for the meta logistic head.

Why the meta head, not the deep ensemble?

- The meta `LogisticRegression` is small, linear, and per-ticker — perfect for safe
  per-trade SGD micro-updates without destabilizing 800-tree XGBoost/LightGBM bases.
- Bases stay frozen until you choose to retrain offline. The meta head re-shapes
  *how* the existing base probabilities + advanced features map to a final p_up.

What this does on every closed trade:
1. Reload meta `LogisticRegression` for that ticker.
2. Build the meta feature row at the moment of entry.
3. Compute asymmetric reward; map to a target probability + per-sample weight.
4. Take ONE SGD step on (coef_, intercept_) with weight clipping.
5. Persist updated meta back to disk so the next prediction sees it.

Env knobs:
- ONLINE_LR             default 1e-5  (per Phase 11 spec)
- ONLINE_WEIGHT_CLIP    default 1.5
- ONLINE_REWARD_TO_TARGET_GAIN default 4.0
- USE_ONLINE_UPDATER    default false (opt-in; only enable in paper at first)
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any

import numpy as np

from utils import log


_META_FEATURE_COLS = [
    "p_short",
    "p_long",
    "p_gap",
    "vol_regime_ratio",
    "sentiment_impulse",
    "regime_transition_flag",
    "alpha_proxy_20",
]


@dataclass
class OnlineUpdateReport:
    applied: bool
    ticker: str
    reward: float
    target: float
    weight: float
    pre_p: float
    post_p: float
    delta_l2: float
    reason: str


def use_online_updater() -> bool:
    return os.getenv("USE_ONLINE_UPDATER", "false").strip().lower() in ("1", "true", "yes")


def _meta_feature_vec(state: dict[str, float]) -> np.ndarray:
    row = []
    for c in _META_FEATURE_COLS:
        if c == "p_gap":
            row.append(float(state.get("p_gap", state.get("p_short", 0.5) - state.get("p_long", 0.5))))
        else:
            row.append(float(state.get(c, 0.0)))
    return np.asarray(row, dtype=np.float64).reshape(1, -1)


def _sigmoid(z: float) -> float:
    if z > 50:
        return 1.0
    if z < -50:
        return 0.0
    return 1.0 / (1.0 + math.exp(-z))


def _reward_to_target(reward: float, side: str) -> float:
    """Map asymmetric reward to a [0,1] target for the meta head.

    Big positive reward on a LONG -> target 1.0 (model should have been more bullish).
    Big negative reward on a LONG -> target 0.0 (model should have been less bullish).
    SHORT mirrors LONG.
    """
    gain = float(os.getenv("ONLINE_REWARD_TO_TARGET_GAIN", "4.0"))
    s = _sigmoid(reward * gain)
    if side.upper() == "LONG":
        return float(s)
    return float(1.0 - s)


def _sample_weight(reward: float) -> float:
    """Bigger losses get bigger learning weight (within clip)."""
    clip = float(os.getenv("ONLINE_WEIGHT_CLIP", "1.5"))
    w = 1.0 + min(clip, abs(reward))
    return float(w)


def online_update_meta_for_trade(
    ticker: str,
    state_at_entry: dict[str, float],
    side: str,
    reward: float,
) -> OnlineUpdateReport:
    """Apply a single SGD micro-step to the meta `LogisticRegression` for this ticker."""
    if not use_online_updater():
        return OnlineUpdateReport(
            applied=False,
            ticker=ticker,
            reward=float(reward),
            target=0.0,
            weight=0.0,
            pre_p=0.0,
            post_p=0.0,
            delta_l2=0.0,
            reason="updater_disabled",
        )

    try:
        from analytics.meta_stack import load_meta_stack, save_meta_stack, MetaStackResult
    except Exception as e:
        return OnlineUpdateReport(
            applied=False,
            ticker=ticker,
            reward=float(reward),
            target=0.0,
            weight=0.0,
            pre_p=0.0,
            post_p=0.0,
            delta_l2=0.0,
            reason=f"meta_import_failed:{e}",
        )

    model = load_meta_stack(ticker)
    if model is None or not hasattr(model, "coef_") or not hasattr(model, "intercept_"):
        return OnlineUpdateReport(
            applied=False,
            ticker=ticker,
            reward=float(reward),
            target=0.0,
            weight=0.0,
            pre_p=0.0,
            post_p=0.0,
            delta_l2=0.0,
            reason="no_meta_model_or_unsupported",
        )

    x = _meta_feature_vec(state_at_entry)
    target = _reward_to_target(reward, side)
    weight = _sample_weight(reward)
    lr = float(os.getenv("ONLINE_LR", "1e-5"))

    coef = np.asarray(model.coef_, dtype=np.float64).reshape(-1)
    intercept = float(np.asarray(model.intercept_, dtype=np.float64).reshape(-1)[0])
    if coef.shape[0] != x.shape[1]:
        return OnlineUpdateReport(
            applied=False,
            ticker=ticker,
            reward=float(reward),
            target=float(target),
            weight=float(weight),
            pre_p=0.0,
            post_p=0.0,
            delta_l2=0.0,
            reason="feature_dim_mismatch",
        )

    z_pre = float(coef @ x.reshape(-1) + intercept)
    p_pre = _sigmoid(z_pre)

    err = (p_pre - target) * weight
    grad_w = err * x.reshape(-1)
    grad_b = err

    new_coef = coef - lr * grad_w
    new_intercept = intercept - lr * grad_b

    clip = float(os.getenv("ONLINE_PARAM_CLIP", "10.0"))
    new_coef = np.clip(new_coef, -clip, clip)
    new_intercept = float(np.clip(new_intercept, -clip, clip))

    z_post = float(new_coef @ x.reshape(-1) + new_intercept)
    p_post = _sigmoid(z_post)
    delta_l2 = float(np.linalg.norm(new_coef - coef))

    try:
        model.coef_ = new_coef.reshape(model.coef_.shape)
        model.intercept_ = np.array([new_intercept], dtype=np.float64).reshape(model.intercept_.shape)
        res = MetaStackResult(
            auc=0.0,
            rows=0,
            features=list(_META_FEATURE_COLS),
            bars_total=0,
            meta_eval_rows=0,
        )
        save_meta_stack(ticker, model, res)
    except Exception as e:
        return OnlineUpdateReport(
            applied=False,
            ticker=ticker,
            reward=float(reward),
            target=float(target),
            weight=float(weight),
            pre_p=float(p_pre),
            post_p=float(p_post),
            delta_l2=float(delta_l2),
            reason=f"persist_failed:{e}",
        )

    log.info(
        "[ONLINE] %s %s reward=%.4f target=%.3f w=%.2f pre_p=%.4f post_p=%.4f dL2=%.5f",
        ticker,
        side,
        reward,
        target,
        weight,
        p_pre,
        p_post,
        delta_l2,
    )
    return OnlineUpdateReport(
        applied=True,
        ticker=ticker,
        reward=float(reward),
        target=float(target),
        weight=float(weight),
        pre_p=float(p_pre),
        post_p=float(p_post),
        delta_l2=float(delta_l2),
        reason="updated",
    )
