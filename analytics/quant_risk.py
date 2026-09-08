"""Explicit risk math for the classic quant stack (shared by fortress / paper / talk).

Covers: position sizing (half-Kelly + heat), max drawdown, slippage estimate,
and overfitting warnings. Does not replace ``risk_manager.RiskManager`` —
feeds it and ``portfolio_risk_overlay``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import numpy as np


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass
class PositionSizePlan:
    notional: float
    kelly_frac: float
    heat_frac: float
    warnings: list[str]


@dataclass
class SlippageEstimate:
    expected_bps: float
    adverse_usd: float
    ok: bool
    reason: str


def half_kelly_fraction(
    win_rate: float = 0.52,
    avg_win: float = 0.02,
    avg_loss: float = 0.015,
) -> float:
    b = avg_win / max(avg_loss, 1e-9)
    p = float(np.clip(win_rate, 0.01, 0.99))
    q = 1.0 - p
    f = (b * p - q) / max(b, 1e-9)
    half = max(0.0, min(0.25, f / 2.0))
    return min(half, _f("KELLY_CAP", 0.10))


def size_position(
    equity: float,
    *,
    entry: float,
    stop: float,
    win_rate: float = 0.52,
    avg_win: float = 0.02,
    avg_loss: float = 0.015,
    current_heat: float = 0.0,
    max_heat: float | None = None,
    max_single_frac: float | None = None,
) -> PositionSizePlan:
    """Risk-budgeted notional from stop distance + half-Kelly + portfolio heat."""
    warnings: list[str] = []
    eq = max(float(equity), 1.0)
    kelly = half_kelly_fraction(win_rate, avg_win, avg_loss)
    heat_cap = max_heat if max_heat is not None else _f("MAX_PORTFOLIO_HEAT", 0.06)
    single_cap = max_single_frac if max_single_frac is not None else _f("MAX_SINGLE_ASSET_FRAC", 0.12)
    stop_dist = abs(float(entry) - float(stop)) / max(abs(float(entry)), 1e-9)
    if stop_dist < 1e-6:
        warnings.append("stop_too_tight")
        stop_dist = _f("DEFAULT_STOP_FRAC", 0.02)
    risk_budget = eq * kelly
    notional = risk_budget / stop_dist
    notional = min(notional, eq * single_cap)
    proposed_heat = stop_dist * notional / eq
    headroom = max(0.0, heat_cap - float(current_heat))
    if proposed_heat > headroom and proposed_heat > 0:
        notional *= headroom / proposed_heat
        warnings.append("heat_scaled")
    if notional < _f("MIN_NOTIONAL_USD", 25.0):
        warnings.append("below_min_notional")
        notional = 0.0
    return PositionSizePlan(
        notional=float(max(0.0, notional)),
        kelly_frac=float(kelly),
        heat_frac=float(stop_dist * notional / eq) if eq else 0.0,
        warnings=warnings,
    )


def max_drawdown(equity_series: list[float] | np.ndarray) -> float:
    """Peak-to-trough drawdown fraction (0..1)."""
    if equity_series is None or len(equity_series) < 2:
        return 0.0
    arr = np.asarray(equity_series, dtype=float)
    arr = arr[arr > 0]
    if len(arr) < 2:
        return 0.0
    peak = np.maximum.accumulate(arr)
    dd = (peak - arr) / np.maximum(peak, 1e-9)
    return float(np.max(dd))


def estimate_slippage_bps(
    *,
    mid: float,
    spread_bps: float | None = None,
    notional: float = 0.0,
    adv_usd: float = 0.0,
    vol_frac: float = 0.02,
) -> SlippageEstimate:
    """
    Rough expected adverse slippage in bps:
    half-spread + participation impact (sqrt) + vol cushion.
    """
    mid = max(float(mid or 0), 1e-9)
    half_spread = float(spread_bps if spread_bps is not None else _f("DEFAULT_SPREAD_BPS", 5.0)) / 2.0
    part = 0.0
    if adv_usd > 0 and notional > 0:
        part = float(notional) / float(adv_usd)
    impact = _f("SLIPPAGE_IMPACT_COEF", 8.0) * float(np.sqrt(max(part, 0.0)))
    vol_cushion = _f("SLIPPAGE_VOL_COEF", 15.0) * float(np.clip(vol_frac, 0.0, 0.2))
    total = half_spread + impact + vol_cushion
    cap = _f("SLIPPAGE_MAX_BPS", 80.0)
    ok = total <= cap
    adverse = mid * (total / 10_000.0) * (float(notional) / mid if mid else 0.0)
    return SlippageEstimate(
        expected_bps=float(total),
        adverse_usd=float(adverse),
        ok=ok,
        reason="ok" if ok else f"slippage_{total:.1f}bps_gt_{cap:.0f}",
    )


def overfitting_warning(
    train_metric: float,
    test_metric: float,
    *,
    gap_warn: float | None = None,
    label: str = "model",
) -> dict[str, Any]:
    """
    Flag train≫test gaps (aspirational 'no failures' ≠ ignore overfit).
    Returns ``{warn: bool, gap, message}``.
    """
    gap = float(train_metric) - float(test_metric)
    thresh = gap_warn if gap_warn is not None else _f("OVERFIT_GAP_WARN", 0.12)
    warn = gap >= thresh
    msg = (
        f"{label}: train-test gap {gap:.3f} ≥ {thresh:.3f} — treat live edge as fragile"
        if warn
        else f"{label}: train-test gap {gap:.3f} ok"
    )
    return {"warn": warn, "gap": gap, "threshold": thresh, "message": msg}


def risk_brief(
    equity: float,
    equity_series: list[float] | None = None,
    *,
    current_heat: float = 0.0,
) -> dict[str, Any]:
    """Compact risk snapshot for talk / operator observe paths."""
    dd = max_drawdown(equity_series or [])
    halt = _f("MONTHLY_DRAWDOWN_HALT_PCT", 0.10)
    return {
        "equity": float(equity),
        "max_drawdown": dd,
        "heat": float(current_heat),
        "kelly_cap": half_kelly_fraction(),
        "dd_halt_pct": halt,
        "near_halt": dd >= halt * 0.8,
        "note": "Resilient retries ≠ zero failures — watchdogs + heat/DD gates only.",
    }
