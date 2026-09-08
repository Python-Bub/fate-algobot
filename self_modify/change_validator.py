"""Validation guardrails for adaptive changes."""

from __future__ import annotations

from dataclasses import dataclass, asdict


BOUNDS = {
    "BUY_THRESHOLD": (0.52, 0.99),
    "SELL_THRESHOLD": (0.15, 0.48),
    "MIN_MODEL_CONFIDENCE": (0.52, 0.99),
    "MIN_EXECUTION_CONFIDENCE": (0.50, 0.99),
    "EXEC_CERTAINTY_GAIN": (1.0, 12.0),
    "ORDER_NOTIONAL": (50.0, 12000.0),
    "MAX_SINGLE_POSITION_FRAC": (0.005, 0.20),
    "PAPER_SIM_MIN_CONF": (0.50, 0.99),
    "RANK_W_MACRO": (-0.05, 0.50),
    "MAX_SINGLE_ASSET_FRAC": (0.02, 0.30),
    "HF_W_MOMENTUM": (-0.08, 0.20),
    "HF_W_TREND": (-0.08, 0.20),
    "HF_W_STAT_ARB": (-0.08, 0.20),
    "HF_W_MEAN_REV": (-0.08, 0.20),
    "MAX_TOTAL_EXPOSURE_FRAC": (0.40, 0.95),
    "MONTHLY_DRAWDOWN_HALT_PCT": (0.05, 0.30),
    "SECTOR_MAX_EXPOSURE_FRAC": (0.15, 0.60),
    "PAPER_SIM_MIN_SCORE": (-0.50, 1.00),
}


@dataclass
class ValidationResult:
    ok: bool
    reason: str
    accepted: dict
    rejected: dict


def validate_param_changes(changes: dict[str, float]) -> ValidationResult:
    accepted: dict = {}
    rejected: dict = {}
    for k, v in changes.items():
        if k not in BOUNDS:
            rejected[k] = "unknown_param"
            continue
        lo, hi = BOUNDS[k]
        try:
            x = float(v)
        except Exception:
            rejected[k] = "nan"
            continue
        if x < lo or x > hi:
            rejected[k] = f"out_of_bounds[{lo},{hi}]"
            continue
        accepted[k] = x
    ok = len(accepted) > 0 and len(rejected) == 0
    reason = "ok" if ok else ("partial" if accepted else "rejected")
    return ValidationResult(ok=ok, reason=reason, accepted=accepted, rejected=rejected)


def validate_live_metrics(metrics: dict) -> ValidationResult:
    """Block adaptation if strategy health is unstable."""
    dd = float(metrics.get("drawdown", 0.0))
    hit = float(metrics.get("hit_rate", 0.5))
    sharpe = float(metrics.get("sharpe_proxy", 0.0))
    if dd < -0.12:
        return ValidationResult(False, "drawdown_too_large", {}, {"drawdown": dd})
    if hit < 0.35 and sharpe < 0:
        return ValidationResult(False, "edge_negative", {}, {"hit_rate": hit, "sharpe_proxy": sharpe})
    return ValidationResult(True, "ok", {}, {})


def as_dict(v: ValidationResult) -> dict:
    return asdict(v)

