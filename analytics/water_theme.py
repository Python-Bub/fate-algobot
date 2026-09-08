"""Datacenter-cooling water sleeve — scored overlay, not a slogan.

Why this exists (not because someone typed 'buy water'):
  Training and inference burn electricity *and* water. Hyperscale campuses use
  evaporative cooling, on-site treatment, and municipal supply. Google, Microsoft,
  Meta, and xAI have all published rising water withdrawals as GPU clusters scale.
  The investable claim is: scarce freshwater rights + reuse/metering/cooling chem
  are tollbooths on that capex, with regulated returns the chips themselves do not have.

What we do *not* do:
  - Boost NVDA/MSFT/GOOGL as 'water'. Those are the demand side; they already
    have model_edge / industry_ai mass. Double-counting them would flatten the book.
  - PRED_FORCE the utility list. If the 1d head says down, theme weight is zero.
  - Buy PHO/FIW unless explicitly opted in (index-shaped water beta).

SpaceX is a *long-horizon option only* (no public ticker). RKLB/ASTS are launch
and space-comms proxies scored on the longterm sleeve at 1%, never fortress force.
"""

from __future__ import annotations

import os
from typing import Any

# Liquid US-listed water utilities (regulated rate-base + water rights).
WATER_UTILITIES: tuple[str, ...] = (
    "AWK",
    "WTRG",
    "CWT",
    "AWR",
    "SJW",
    "MSEX",
)

# Pumps, treatment, meters, cooling chemistry — what campuses actually buy.
WATER_TECH: tuple[str, ...] = (
    "XYL",
    "PNR",
    "WMS",
    "TTEK",
    "BMI",
    "ITRI",
    "ECL",
)

WATER_ETFS: tuple[str, ...] = ("PHO", "FIW", "CGW")

# Demand confirmation only — never receive the water rank boost.
AI_WATER_DEMAND: frozenset[str] = frozenset(
    {
        "NVDA",
        "AVGO",
        "MSFT",
        "GOOGL",
        "GOOG",
        "AMZN",
        "META",
        "ORCL",
        "AMD",
        "TSM",
        "VRT",
        "CEG",
        "PWR",
        "DELL",
        "SMCI",
    }
)

# Public launch / space-comms proxies. Not Tesla (different P&L). Not SpaceX.
SPACE_LONG_HORIZON: frozenset[str] = frozenset({"RKLB", "ASTS"})

# Role leverage on the cooling-water spend (tech > regulated utility > ETF).
_ROLE: dict[str, float] = {}
_ROLE.update({s: 0.85 for s in WATER_UTILITIES})
_ROLE.update({s: 1.00 for s in WATER_TECH})
_ROLE.update({s: 0.25 for s in WATER_ETFS})

# Multi-year structural demand. Not a 1-day momentum toy.
_STRUCTURAL_DEMAND = 0.68


def _on(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return float(default)


def _sym(symbol: str) -> str:
    return str(symbol or "").replace("/", "-").replace("$", "").strip().upper()


def enabled() -> bool:
    return _on("FORTRESS_WATER_THEME", "true")


def include_etfs() -> bool:
    return _on("FORTRESS_WATER_INCLUDE_ETFS", "false")


def water_scan_symbols() -> list[str]:
    names = list(WATER_UTILITIES) + list(WATER_TECH)
    if include_etfs():
        names.extend(WATER_ETFS)
    seen: set[str] = set()
    out: list[str] = []
    for s in names:
        u = str(s).strip().upper()
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def is_water_symbol(symbol: str) -> bool:
    return _sym(symbol) in set(water_scan_symbols())


def is_space_proxy(symbol: str) -> bool:
    return _sym(symbol) in SPACE_LONG_HORIZON


def industry_overrides() -> dict[str, str]:
    """Map water names onto existing industry handlers (no new category required)."""
    out = {s: "electric_gas_utilities" for s in WATER_UTILITIES}
    for s in WATER_TECH:
        out[s] = "construction_machinery"
    out["ECL"] = "chemicals"
    return out


def _quality_from_p_up(p_up: float | None) -> float:
    """Theme cannot override a down head. Edge above 0.50 scales the overlay."""
    if p_up is None:
        return 0.45
    p = float(p_up)
    if p < 0.48:
        return 0.0
    edge = max(0.0, (p - 0.50) * 2.0)
    return 0.30 + 0.70 * min(1.0, edge)


def water_rank_boost(
    ticker: str,
    *,
    p_up: float | None = None,
    sleeve: str | None = None,
) -> tuple[float, dict[str, Any]]:
    """Scored datacenter-water overlay. 0 on chips, ETFs (default), and down models."""
    t = _sym(ticker)
    sl = (sleeve or os.getenv("FATE_SLEEVE") or "").strip().lower()
    meta: dict[str, Any] = {
        "ticker": t,
        "thesis": "datacenter_cooling_water",
        "sleeve": sl,
    }
    if sl in ("hft", "day_trade"):
        return 0.0, {**meta, "reason": "sleeve_zero"}
    if not enabled():
        return 0.0, {**meta, "reason": "disabled"}
    if t in AI_WATER_DEMAND:
        return 0.0, {**meta, "reason": "demand_side_not_water"}
    if t not in _ROLE:
        return 0.0, {**meta, "reason": "not_water"}
    if t in WATER_ETFS and not include_etfs():
        return 0.0, {**meta, "reason": "etf_opt_in"}
    quality = _quality_from_p_up(p_up)
    if quality <= 0:
        return 0.0, {**meta, "reason": "model_down", "p_up": p_up}
    role = float(_ROLE.get(t, 0.0))
    w = _f("RANK_W_WATER_DATACENTER", 0.12)
    raw = w * role * _STRUCTURAL_DEMAND * quality
    boost = float(min(w, max(0.0, raw)))
    meta.update(
        {
            "role": "utility" if t in WATER_UTILITIES else ("tech" if t in WATER_TECH else "etf"),
            "role_w": role,
            "structural_demand": _STRUCTURAL_DEMAND,
            "quality": quality,
            "p_up": p_up,
            "boost": boost,
        }
    )
    return boost, meta


def space_rank_boost(
    ticker: str,
    *,
    p_up: float | None = None,
    sleeve: str | None = None,
) -> tuple[float, dict[str, Any]]:
    """Long-horizon launch/space-comms option. Fortress/HFT stay 0."""
    t = _sym(ticker)
    sl = (sleeve or os.getenv("FATE_SLEEVE") or "").strip().lower()
    meta: dict[str, Any] = {
        "ticker": t,
        "thesis": "space_compute_backhaul_option",
        "sleeve": sl,
    }
    if sl != "longterm":
        return 0.0, {**meta, "reason": "longterm_only"}
    if not _on("FORTRESS_SPACE_THEME", "true"):
        return 0.0, {**meta, "reason": "disabled"}
    if t not in SPACE_LONG_HORIZON:
        return 0.0, {**meta, "reason": "not_space_proxy"}
    quality = _quality_from_p_up(p_up)
    if quality <= 0:
        return 0.0, {**meta, "reason": "model_down", "p_up": p_up}
    w = _f("RANK_W_SPACE_INFRA", 0.06)
    boost = float(min(w, max(0.0, w * 0.80 * quality)))
    meta.update({"quality": quality, "p_up": p_up, "boost": boost})
    return boost, meta
