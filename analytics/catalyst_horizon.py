#!/usr/bin/env python3
"""Catalyst ↔ horizon alignment + max-equity conviction sizing.

Problem this solves
-------------------
Earnings tomorrow can score high on the 1d model, then get crushed by a
wrong-sleeve weight (~0.05 on weekly/LT event mass) or earnings_size_mult=0.55
so we never buy. Letter diversify ×0.05 can also kill non-FORCE names.

Design (optimize, never remove sleeves)
---------------------------------------
  catalyst_horizon_fit(dte, sleeve) ∈ [0.05, 1.0]
    dte ≤ 1  → fortress/HFT/day_trade = 1.0; weekly = 0.25; longterm = 0.05
    dte 2–7  → weekly = 1.0; fortress = 0.65; longterm = 0.35
    dte ≥ 20 → longterm = 1.0; short sleeves low

  Size: skip earnings dampen when fit ≥ CATALYST_SIZE_FIT_MIN on matching sleeve.
  Rank: multiply earnings stick/event boost by fit (wrong horizon stays tiny).
  Max equity: when conviction + online models agree and risk is calm, size toward
  single-name / BP cap automatically.
"""

from __future__ import annotations

import os
from typing import Any

from analytics.sleeve_weights import Sleeve, resolve_sleeve


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _b(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def catalyst_horizon_fit(
    days_to: int | float | None,
    sleeve: str | None = None,
    *,
    hold_days: int | None = None,
) -> float:
    """How well a catalyst at `days_to` matches this trading sleeve (1=perfect)."""
    if not _b("USE_CATALYST_HORIZON", True):
        return 1.0
    if days_to is None:
        return 1.0
    try:
        dte = int(days_to)
    except (TypeError, ValueError):
        return 1.0
    if dte < 0:
        # post-print: short sleeves may still react; LT less so
        dte_abs = abs(dte)
        sl = resolve_sleeve(hold_days=hold_days) if not sleeve else str(sleeve).strip().lower()
        if sl in ("hft", "day_trade", "fortress"):
            return _f("CATALYST_FIT_POST_SHORT", 0.55) if dte_abs <= 2 else 0.25
        if sl == "weekly":
            return _f("CATALYST_FIT_POST_WEEKLY", 0.40)
        return _f("CATALYST_FIT_POST_LT", 0.20)

    sl = resolve_sleeve(hold_days=hold_days) if not sleeve else str(sleeve).strip().lower()
    floor = _f("CATALYST_FIT_FLOOR", 0.05)

    if dte <= 1:
        table = {
            "hft": _f("CATALYST_FIT_DTE1_HFT", 1.0),
            "day_trade": _f("CATALYST_FIT_DTE1_DAY", 1.0),
            "fortress": _f("CATALYST_FIT_DTE1_FORTRESS", 1.0),
            "weekly": _f("CATALYST_FIT_DTE1_WEEKLY", 0.25),
            "longterm": _f("CATALYST_FIT_DTE1_LT", 0.05),
        }
    elif dte <= 7:
        table = {
            "hft": _f("CATALYST_FIT_DTE7_HFT", 0.45),
            "day_trade": _f("CATALYST_FIT_DTE7_DAY", 0.55),
            "fortress": _f("CATALYST_FIT_DTE7_FORTRESS", 0.65),
            "weekly": _f("CATALYST_FIT_DTE7_WEEKLY", 1.0),
            "longterm": _f("CATALYST_FIT_DTE7_LT", 0.35),
        }
    elif dte <= 20:
        table = {
            "hft": _f("CATALYST_FIT_DTE20_HFT", 0.15),
            "day_trade": _f("CATALYST_FIT_DTE20_DAY", 0.20),
            "fortress": _f("CATALYST_FIT_DTE20_FORTRESS", 0.40),
            "weekly": _f("CATALYST_FIT_DTE20_WEEKLY", 0.70),
            "longterm": _f("CATALYST_FIT_DTE20_LT", 0.85),
        }
    else:
        table = {
            "hft": _f("CATALYST_FIT_FAR_HFT", 0.05),
            "day_trade": _f("CATALYST_FIT_FAR_DAY", 0.08),
            "fortress": _f("CATALYST_FIT_FAR_FORTRESS", 0.20),
            "weekly": _f("CATALYST_FIT_FAR_WEEKLY", 0.45),
            "longterm": _f("CATALYST_FIT_FAR_LT", 1.0),
        }
    return max(floor, min(1.0, float(table.get(sl, 0.5))))


def earnings_rank_boost(
    *,
    days_to: int | float | None,
    p_adj: float,
    sleeve: str | None = None,
    hold_days: int | None = None,
    stick: bool = False,
) -> tuple[float, dict[str, Any]]:
    """Additive rank boost for earnings catalysts, scaled by horizon fit + online models."""
    meta: dict[str, Any] = {"applied": 0.0, "fit": 1.0, "stick": bool(stick)}
    if not stick and days_to is None:
        return 0.0, meta
    fit = catalyst_horizon_fit(days_to, sleeve, hold_days=hold_days)
    meta["fit"] = fit
    min_p = _f("EARNINGS_STICK_MIN_P", 0.52)
    if float(p_adj) < min_p:
        meta["reason"] = "p_below_stick_min"
        return 0.0, meta
    base = _f("EARNINGS_STICK_SCORE_BOOST", 0.28) if stick else _f("EARNINGS_EVENT_RANK_BOOST", 0.08)
    # Online neural / foundation agreement steepens boost (does not replace stick)
    online = online_agreement_mult(p_adj)
    meta["online_mult"] = online
    applied = float(base) * float(fit) * float(online)
    # Cap so one catalyst cannot dominate the whole book score
    cap = _f("EARNINGS_STICK_BOOST_CAP", 0.45)
    applied = max(0.0, min(cap, applied))
    meta["applied"] = applied
    meta["force_ok"] = bool(stick and fit >= _f("CATALYST_FORCE_FIT_MIN", 0.55) and float(p_adj) >= min_p)
    return applied, meta


def earnings_size_mult_aligned(
    *,
    days_to: int | float | None,
    in_earnings_window: bool,
    sleeve: str | None = None,
    hold_days: int | None = None,
    encourage: bool = False,
    playbook_dampen: float = 0.55,
) -> float:
    """Size multiplier: full size on matching horizon; keep dampen on mismatch."""
    if not in_earnings_window and not encourage:
        return 1.0
    fit = catalyst_horizon_fit(days_to, sleeve, hold_days=hold_days)
    # Matching short-horizon catalyst → do NOT cut size (this was the miss)
    if encourage and fit >= _f("CATALYST_SIZE_FIT_MIN", 0.55):
        return max(1.0, _f("CATALYST_MATCH_SIZE_MULT", 1.15))
    # Wrong horizon: keep / deepen dampen so LT doesn't full-size overnight binary
    damp = float(playbook_dampen)
    if fit <= _f("CATALYST_MISMATCH_FIT", 0.20):
        damp = min(damp, _f("CATALYST_MISMATCH_SIZE_MULT", 0.35))
    return max(0.15, min(1.25, damp * max(fit, 0.25) / 0.55))


def online_agreement_mult(p_adj: float, *, extras: dict[str, float] | None = None) -> float:
    """Blend pretrained/online heads into a soft multiplier around 1.0."""
    if not _b("USE_ONLINE_CONVICTION", True):
        return 1.0
    parts: list[float] = [float(p_adj)]
    ex = extras or {}
    for k in ("foundation_p", "neural_p", "lstm_p", "chronos_p", "ule_p"):
        v = ex.get(k)
        if v is None:
            continue
        try:
            parts.append(float(v))
        except (TypeError, ValueError):
            pass
    # Lazy pull live online heads when not supplied
    if len(parts) == 1 and _b("ONLINE_CONVICTION_LAZY", False):
        pass  # keep cheap by default — callers pass extras when available
    avg = sum(parts) / max(1, len(parts))
    # Map avg 0.52..0.72 → mult 0.9..1.25
    edge = max(0.0, min(1.0, (avg - 0.52) / 0.20))
    return 0.90 + 0.35 * edge


def max_equity_size_mult(
    *,
    p_adj: float,
    exec_conf: float | None = None,
    risk_pressure: float | None = None,
    force_priority: bool = False,
    catalyst_fit: float = 1.0,
    online_extras: dict[str, float] | None = None,
) -> float:
    """
    When models agree and risk is calm → push toward max equity deployment.
    When risky → shrink. Always returns a multiplier applied on top of conviction.
    """
    if not _b("USE_MAX_EQUITY_MODE", True):
        return 1.0
    conf = 0.55 if exec_conf is None else float(exec_conf)
    pressure = 0.0 if risk_pressure is None else float(risk_pressure)
    online = online_agreement_mult(p_adj, extras=online_extras)
    # Too risky → refuse max mode
    risk_block = _f("MAX_EQUITY_RISK_BLOCK", 0.62)
    if pressure >= risk_block and not force_priority:
        return _f("MAX_EQUITY_RISKY_MULT", 0.45)
    score = (
        0.40 * max(0.0, min(1.0, (float(p_adj) - 0.52) / 0.20))
        + 0.25 * max(0.0, min(1.0, conf))
        + 0.20 * max(0.0, min(1.0, float(catalyst_fit)))
        + 0.15 * max(0.0, min(1.0, (online - 0.90) / 0.35))
    )
    if force_priority:
        score = max(score, _f("MAX_EQUITY_FORCE_FLOOR", 0.80))
    # score 0..1 → mult 0.7..MAX (default 1.35 toward single-cap / BP)
    lo = _f("MAX_EQUITY_SIZE_MIN", 0.70)
    hi = _f("MAX_EQUITY_SIZE_MAX", 1.35)
    return lo + (hi - lo) * max(0.0, min(1.0, score ** _f("MAX_EQUITY_CURVE", 0.85)))


def enrich_earnings_plan(plan: dict[str, Any], *, sleeve: str | None = None, hold_days: int | None = None) -> dict[str, Any]:
    """Attach fit / size / force hints onto holdings_earnings_plan output."""
    out = dict(plan or {})
    dte = out.get("days_to")
    fit = catalyst_horizon_fit(dte, sleeve, hold_days=hold_days)
    out["catalyst_horizon_fit"] = fit
    out["catalyst_sleeve"] = (sleeve or resolve_sleeve(hold_days=hold_days))
    encourage = bool(out.get("encourage_pre_momentum") or out.get("stick_to_prediction"))
    out["aligned_size_mult"] = earnings_size_mult_aligned(
        days_to=dte,
        in_earnings_window=bool(out.get("near_event")),
        sleeve=sleeve,
        hold_days=hold_days,
        encourage=encourage,
    )
    out["force_horizon_ok"] = bool(encourage and fit >= _f("CATALYST_FORCE_FIT_MIN", 0.55))
    return out
