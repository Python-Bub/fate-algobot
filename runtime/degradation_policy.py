"""Runtime degradation policy based on latency and error budgets."""

from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class RuntimeHealth:
    avg_score_ms: float
    error_rate: float
    symbol_count: int
    mode: str
    action: str


def decide_degradation(avg_score_ms: float, error_rate: float, symbol_count: int) -> RuntimeHealth:
    mode = "normal"
    action = "none"
    if avg_score_ms > 3500 or error_rate > 0.25:
        mode = "degraded_high"
        action = "disable_sentiment_and_reduce_universe_50pct"
    elif avg_score_ms > 2200 or error_rate > 0.12:
        mode = "degraded_medium"
        action = "disable_llm_signal"
    elif avg_score_ms > 1500:
        mode = "degraded_low"
        action = "reduce_concurrency_contention"
    return RuntimeHealth(
        avg_score_ms=float(avg_score_ms),
        error_rate=float(error_rate),
        symbol_count=int(symbol_count),
        mode=mode,
        action=action,
    )


def as_dict(h: RuntimeHealth) -> dict:
    return asdict(h)

