"""Crowd / retail behavior + after-hours + counterparty flow.

Estimates what most investors are doing (FOMO buy, panic sell, overnight lean)
and adjusts p_up / execution confidence for the full trading stack (paper, fortress).

When we buy, someone sells to us; when we sell, someone buys from us — counterparty
motivation is folded into confidence (capitulation = better entry, distribution = caution).

Modes (CROWD_ADJUST_MODE):
- contrarian_long (default): fade euphoric buying, respect panic / motivated sellers
- momentum: follow crowd + overnight lean
- off: diagnostics only

Env:
- USE_CROWD_BEHAVIOR=true
- USE_AFTER_HOURS=true
- COUNTERPARTY_P_MAX=0.05
- CROWD_P_UP_MAX=0.07
- CROWD_EXEC_MAX=0.06
- CROWD_MIN_EXEC_BUMP=0.04
- CROWD_FEAR_DIP_BOOST=0.04
- CROWD_EUPHORIA_BLOCK=0.72
- RANK_W_CROWD=0.10
- RANK_W_AFTER_HOURS=0.08
"""

from __future__ import annotations

import os
from typing import Any

import numpy as np


def crowd_behavior_enabled() -> bool:
    return os.getenv("USE_CROWD_BEHAVIOR", "true").lower() in ("1", "true", "yes")


def crowd_adjust_mode() -> str:
    m = os.getenv("CROWD_ADJUST_MODE", "contrarian_long").strip().lower()
    if m in ("contrarian_long", "momentum", "off"):
        return m
    return "contrarian_long"


def _clip01(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0))


def _clip11(x: float) -> float:
    return float(np.clip(x, -1.0, 1.0))


def _vix_fear(vix: float | None) -> float:
    if vix is None:
        return 0.0
    v = float(vix)
    if v <= 14:
        return -0.35
    if v >= 32:
        return 0.55
    if v >= 22:
        return 0.15 + 0.4 * (v - 22) / 10.0
    if v <= 18:
        return -0.15 - 0.2 * (18 - v) / 4.0
    return 0.0


def analyze_crowd_behavior(
    symbol: str,
    *,
    news_sentiment: float = 0.0,
    news_factor: float = 0.0,
    social_score: float = 0.0,
    social_bull_share: float = 0.5,
    volume_ratio: float = 1.0,
    vix: float | None = None,
    ah_tilt: float = 0.0,
    ah_return_pct: float = 0.0,
) -> dict[str, Any]:
    sym = (symbol or "").strip().upper()

    news_tilt = _clip11(float(np.tanh(news_sentiment * 1.4)) * 0.55 + float(np.tanh(news_factor * 2.0)) * 0.45)
    social_tilt = _clip11(float(social_score) * 0.7 + (float(social_bull_share) - 0.5) * 2.0 * 0.3)
    vol_rush = _clip11(max(0.0, float(volume_ratio) - 1.25) * 0.8)
    symbol_euphoria = _clip11(0.45 * news_tilt + 0.40 * social_tilt + 0.15 * vol_rush)

    market_fear = _vix_fear(vix)
    ah = _clip11(float(ah_tilt))
    crowd_pressure = _clip11(0.50 * symbol_euphoria - 0.18 * market_fear + 0.32 * ah)

    if crowd_pressure >= 0.35:
        expected_action = "BUY"
        behavior = "euphoric_buying"
    elif crowd_pressure <= -0.35:
        expected_action = "SELL"
        behavior = "fear_selling"
    elif crowd_pressure >= 0.12:
        expected_action = "LEAN_BUY"
        behavior = "optimistic"
    elif crowd_pressure <= -0.12:
        expected_action = "LEAN_SELL"
        behavior = "cautious"
    else:
        expected_action = "HOLD"
        behavior = "neutral"

    return {
        "symbol": sym,
        "crowd_pressure": float(crowd_pressure),
        "symbol_euphoria": float(symbol_euphoria),
        "market_fear": float(market_fear),
        "ah_tilt": float(ah),
        "ah_return_pct": float(ah_return_pct),
        "expected_crowd_action": expected_action,
        "crowd_behavior": behavior,
        "news_tilt": float(news_tilt),
        "social_tilt": float(social_tilt),
        "volume_rush": float(vol_rush),
        "vix": vix,
    }


def counterparty_adjustment(
    *,
    intended_side: str,
    p_up: float,
    exec_conf: float,
    crowd_pressure: float,
    ah_tilt: float,
) -> tuple[float, float, dict[str, Any]]:
    """Other investor takes the opposite side of our trade — adjust confidence."""
    side = (intended_side or "buy").strip().lower()
    max_p = float(os.getenv("COUNTERPARTY_P_MAX", "0.05"))
    max_e = float(os.getenv("COUNTERPARTY_EXEC_MAX", "0.04"))
    mode = crowd_adjust_mode()

    if side in ("buy", "long"):
        # Seller on other side: motivated when crowd fearful or AH weak (capitulation).
        seller_motivation = _clip11(-0.55 * float(crowd_pressure) - 0.45 * float(ah_tilt))
        if mode == "momentum":
            p_delta = -max_p * seller_motivation
        elif mode == "off":
            p_delta = 0.0
        else:
            p_delta = max_p * seller_motivation
        cp_action = "SELL_TO_US" if side in ("buy", "long") else "BUY_FROM_US"
        read = (
            "counterparty likely motivated seller (capitulation / AH weakness)"
            if seller_motivation > 0.15
            else (
                "counterparty may be distributing into strength — crowded buy"
                if seller_motivation < -0.15
                else "counterparty flow neutral"
            )
        )
    else:
        buyer_eagerness = _clip11(float(crowd_pressure) + float(ah_tilt))
        p_delta = -max_p * buyer_eagerness if mode != "momentum" else max_p * buyer_eagerness
        cp_action = "BUY_FROM_US"
        read = (
            "weak buyer interest on other side — harder exit"
            if buyer_eagerness < -0.1
            else "buyers may absorb our sell"
        )

    e_delta = max_e * float(np.tanh(p_delta / max(max_p, 1e-6)))
    diag = {
        "counterparty_side": cp_action,
        "counterparty_read": read,
        "counterparty_p_delta": float(p_delta),
        "counterparty_exec_delta": float(e_delta),
        "intended_side": side,
    }
    return (
        _clip01(float(p_up) + p_delta),
        _clip01(float(exec_conf) + e_delta),
        diag,
    )


def crowd_rank_boost(crowd: dict[str, Any]) -> float:
    if not crowd_behavior_enabled():
        return 0.0
    mode = crowd_adjust_mode()
    p = float(crowd.get("crowd_pressure", 0.0))
    if mode == "momentum":
        return float(np.tanh(p * 1.5))
    if mode == "off":
        return 0.0
    return float(np.tanh(-p * 1.2))


def block_long_on_crowd_euphoria(crowd: dict[str, Any]) -> bool:
    if os.getenv("CROWD_BLOCK_FOMO", "true").lower() not in ("1", "true", "yes"):
        return False
    thr = float(os.getenv("CROWD_EUPHORIA_BLOCK", "0.72"))
    return float(crowd.get("crowd_pressure", 0.0)) >= thr


def apply_investor_context(
    p_up: float,
    exec_conf: float,
    *,
    symbol: str,
    intended_side: str = "buy",
    news_sentiment: float = 0.0,
    news_factor: float = 0.0,
    social_score: float = 0.0,
    social_bull_share: float = 0.5,
    volume_ratio: float = 1.0,
    vix: float | None = None,
    min_exec_base: float | None = None,
    ah_snapshot: dict[str, Any] | None = None,
    fetch_after_hours: bool = True,
) -> dict[str, Any]:
    """Full stack: after-hours + crowd + counterparty → adjusted p_up / exec_conf."""
    ah: dict[str, Any] = ah_snapshot or {}
    if fetch_after_hours and not ah.get("ok") and ah_snapshot is None:
        try:
            from analytics.after_hours_intel import after_hours_enabled, fetch_after_hours_snapshot

            if after_hours_enabled():
                ah = fetch_after_hours_snapshot(symbol)
        except Exception:
            ah = {}

    ah_tilt = float(ah.get("ah_tilt", 0.0))
    ah_ret = float(ah.get("ah_return_pct", 0.0))

    crowd = analyze_crowd_behavior(
        symbol,
        news_sentiment=news_sentiment,
        news_factor=news_factor,
        social_score=social_score,
        social_bull_share=social_bull_share,
        volume_ratio=volume_ratio,
        vix=vix,
        ah_tilt=ah_tilt,
        ah_return_pct=ah_ret,
    )

    p0 = float(np.clip(p_up, 1e-9, 1.0 - 1e-9))
    e0 = float(np.clip(exec_conf, 0.0, 1.0))
    min_exec = float(min_exec_base if min_exec_base is not None else os.getenv("MIN_EXECUTION_CONFIDENCE", "0.65"))

    p_delta = 0.0
    e_delta = 0.0
    min_exec_bump = 0.0

    if crowd_behavior_enabled() and crowd_adjust_mode() != "off":
        cp = float(crowd["crowd_pressure"])
        p_max = float(os.getenv("CROWD_P_UP_MAX", "0.07"))
        e_max = float(os.getenv("CROWD_EXEC_MAX", "0.06"))
        mode = crowd_adjust_mode()

        if mode == "momentum":
            p_delta = p_max * cp
            e_delta = e_max * cp
            if cp > 0.45:
                min_exec_bump = -float(os.getenv("CROWD_MIN_EXEC_BUMP", "0.04")) * 0.5
            elif cp < -0.45:
                min_exec_bump = float(os.getenv("CROWD_MIN_EXEC_BUMP", "0.04")) * 0.5
        else:
            p_delta = -p_max * cp
            e_delta = -e_max * max(0.0, cp)
            if cp > 0.45:
                min_exec_bump = float(os.getenv("CROWD_MIN_EXEC_BUMP", "0.04")) * min(1.0, (cp - 0.35) / 0.35)
            if cp < -0.30 and p0 >= 0.55:
                fear_boost = float(os.getenv("CROWD_FEAR_DIP_BOOST", "0.04"))
                p_delta += fear_boost * min(1.0, abs(cp))
                e_delta += e_max * 0.35 * min(1.0, abs(cp))

        # After-hours is a first-class signal in the real algorithm (not family-forecast).
        if ah.get("ok") and abs(ah_tilt) > 0.08:
            ah_p = float(os.getenv("AH_P_UP_MAX", "0.05"))
            if mode == "momentum":
                p_delta += ah_p * ah_tilt
            else:
                p_delta += ah_p * ah_tilt * 0.85
            e_delta += float(os.getenv("AH_EXEC_MAX", "0.04")) * abs(ah_tilt)

    p1 = _clip01(p0 + p_delta)
    e1 = _clip01(e0 + e_delta)

    p2, e2, cp_diag = counterparty_adjustment(
        intended_side=intended_side,
        p_up=p1,
        exec_conf=e1,
        crowd_pressure=float(crowd["crowd_pressure"]),
        ah_tilt=ah_tilt,
    )

    min_exec_eff = _clip01(min_exec + min_exec_bump)

    try:
        from analytics.after_hours_intel import ah_rank_boost
    except ImportError:
        ah_rank_boost = lambda _x: 0.0  # noqa: E731

    out = dict(crowd)
    out.update(cp_diag)
    out.update(
        {
            "ah_ok": bool(ah.get("ok", False)),
            "ah_session": str(ah.get("session", "")),
            "ah_investor_read": str(ah.get("investor_read", "")),
            "p_up_before": p0,
            "p_up": p2,
            "p_up_delta": float(p2 - p0),
            "execution_confidence_before": e0,
            "execution_confidence": e2,
            "execution_confidence_delta": float(e2 - e0),
            "min_exec_base": float(min_exec),
            "min_exec_effective": float(min_exec_eff),
            "min_exec_bump": float(min_exec_bump),
            "crowd_block_fomo": block_long_on_crowd_euphoria(crowd),
            "rank_boost": crowd_rank_boost(crowd),
            "ah_rank_boost": float(ah_rank_boost(ah)),
            "mode": crowd_adjust_mode(),
        }
    )
    return out


# Back-compat alias used by older call sites
apply_crowd_adjustments = apply_investor_context
