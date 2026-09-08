"""Latency / inventory haircuts — Python mirror of hft/src/obi-tape/firm-risk.ts."""

from __future__ import annotations

import math


def lag_haircut(quote_age_ms: float, rtt_ms: float, half_life_ms: float = 250.0) -> float:
    tau = max(1.0, float(half_life_ms))
    lag = max(0.0, float(quote_age_ms)) + max(0.0, float(rtt_ms))
    return math.exp(-math.log(2.0) * (lag / tau))


def inventory_haircut(hft_inventory_usd: float, equity_usd: float, max_inv_frac: float = 0.08) -> float:
    cap = max(1.0, float(equity_usd)) * max(0.01, min(0.5, float(max_inv_frac)))
    used = max(0.0, float(hft_inventory_usd))
    return max(0.0, 1.0 - used / cap)


def combined_haircut(
    quote_age_ms: float,
    hft_inventory_usd: float,
    equity_usd: float,
    rtt_ms: float = 0.0,
    *,
    half_life_ms: float = 250.0,
    min_haircut: float = 0.12,
) -> dict[str, float | bool]:
    lag = lag_haircut(quote_age_ms, rtt_ms, half_life_ms)
    inv = inventory_haircut(hft_inventory_usd, equity_usd)
    h = lag * inv
    return {"haircut": h, "lag": lag, "inv": inv, "sit_out": h < min_haircut}


def clip_notional(
    base_usd: float,
    haircut: float,
    *,
    floor: float = 80.0,
    cap: float = 350.0,
) -> float:
    x = max(0.0, float(base_usd)) * max(0.0, min(1.0, float(haircut)))
    if not math.isfinite(x) or x < floor:
        return 0.0
    return min(cap, x)
