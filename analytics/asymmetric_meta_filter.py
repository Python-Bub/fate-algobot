"""Asymmetric dual-threshold meta filter (Phase 10 of online-RL plan).

Decision space:
- LONG  if p_long  >= LONG_DECISION_THRESHOLD   (default: PAPER_SIM_MIN_CONF or 0.58 on calibrated scale)
- SHORT if p_short >= SHORT_DECISION_THRESHOLD  (default 0.80, equivalent to p_up <= 0.20)
- otherwise NO_TRADE  (the explicit "no-trade zone")

This sits *after* base ensemble + execution_confidence and *before* sizing/routing.
It is intentionally separate from execution_confidence so each layer is independently
tunable: confidence asks "is the model sure?", asymmetric filter asks "is this side
worth the asymmetric risk we accept?".

Env knobs:
- USE_ASYM_META_FILTER          (default true)
- LONG_DECISION_THRESHOLD       (default: PAPER_SIM_MIN_CONF, else 0.58 — must match calibrated 8–92% scale)
- SHORT_DECISION_THRESHOLD      (default 0.80) -- on p_short, equivalent to 1-0.20
- ASYM_REQUIRE_EXEC_CONF        (default true) -- also require exec_conf >= min_exec
- ASYM_NO_TRADE_LOG             (default false) -- log every NO_TRADE skip
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AsymDecision:
    action: str
    p_long: float
    p_short: float
    long_threshold: float
    short_threshold: float
    exec_conf: float
    min_exec: float
    rationale: str


def _bool_env(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes")


def long_threshold() -> float:
    """Long bar on *calibrated* p_up (same scale as paper_sim after probability_calibrate)."""
    explicit = os.getenv("LONG_DECISION_THRESHOLD", "").strip()
    if explicit:
        return float(explicit)
    paper_min = os.getenv("PAPER_SIM_MIN_CONF", "").strip()
    if paper_min:
        return float(paper_min)
    return float(os.getenv("MIN_MODEL_CONFIDENCE", "0.58"))


def short_threshold() -> float:
    return float(os.getenv("SHORT_DECISION_THRESHOLD", "0.80"))


def asymmetric_decision(
    p_up: float,
    exec_conf: float,
    min_exec: float,
    p_short_model: float | None = None,
    p_long_model: float | None = None,
) -> AsymDecision:
    """Map a calibrated p_up + exec_confidence to LONG / SHORT / NO_TRADE.

    `p_short_model` / `p_long_model` are the raw heads if available; we use them only
    for diagnostics — the actual action is driven by `p_up` (final blended probability).
    """
    p_up = max(0.0, min(1.0, float(p_up)))
    p_short = 1.0 - p_up
    long_thr = long_threshold()
    short_thr = short_threshold()
    require_exec = _bool_env("ASYM_REQUIRE_EXEC_CONF", True)
    use_filter = _bool_env("USE_ASYM_META_FILTER", True)

    if not use_filter:
        if p_up >= 0.5:
            return AsymDecision(
                action="LONG",
                p_long=p_up,
                p_short=p_short,
                long_threshold=long_thr,
                short_threshold=short_thr,
                exec_conf=float(exec_conf),
                min_exec=float(min_exec),
                rationale="filter_disabled",
            )
        return AsymDecision(
            action="NO_TRADE",
            p_long=p_up,
            p_short=p_short,
            long_threshold=long_thr,
            short_threshold=short_thr,
            exec_conf=float(exec_conf),
            min_exec=float(min_exec),
            rationale="filter_disabled",
        )

    if require_exec and exec_conf < min_exec:
        return AsymDecision(
            action="NO_TRADE",
            p_long=p_up,
            p_short=p_short,
            long_threshold=long_thr,
            short_threshold=short_thr,
            exec_conf=float(exec_conf),
            min_exec=float(min_exec),
            rationale="exec_conf_below_floor",
        )

    if p_up >= long_thr:
        return AsymDecision(
            action="LONG",
            p_long=p_up,
            p_short=p_short,
            long_threshold=long_thr,
            short_threshold=short_thr,
            exec_conf=float(exec_conf),
            min_exec=float(min_exec),
            rationale="p_long_ge_long_threshold",
        )

    if p_short >= short_thr:
        return AsymDecision(
            action="SHORT",
            p_long=p_up,
            p_short=p_short,
            long_threshold=long_thr,
            short_threshold=short_thr,
            exec_conf=float(exec_conf),
            min_exec=float(min_exec),
            rationale="p_short_ge_short_threshold",
        )

    return AsymDecision(
        action="NO_TRADE",
        p_long=p_up,
        p_short=p_short,
        long_threshold=long_thr,
        short_threshold=short_thr,
        exec_conf=float(exec_conf),
        min_exec=float(min_exec),
        rationale="in_no_trade_zone",
    )
