"""Pick the best listed-style contract for a directional or vol view.

Structures covered (math rank, not folklore):
  equity, long_call, long_put, covered_call, protective_put,
  bull_call_spread, bear_put_spread, long_straddle, iron_condor.

Live Alpaca option POSTs stay gated behind ALPACA_OPTIONS_ENABLED.
"""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Sequence

from investing.formulas.derivatives import (
    black_scholes_call,
    black_scholes_put,
    greeks,
    implied_vol,
    moneyness,
)

STRUCTURES: tuple[str, ...] = (
    "equity",
    "long_call",
    "long_put",
    "covered_call",
    "protective_put",
    "bull_call_spread",
    "bear_put_spread",
    "long_straddle",
    "iron_condor",
)


@dataclass(frozen=True)
class ListedContract:
    symbol: str
    kind: str  # call | put
    strike: float
    dte: float  # calendar days
    bid: float
    ask: float
    oi: float = 0.0
    volume: float = 0.0
    mid: float = 0.0

    def __post_init__(self) -> None:
        if not self.mid:
            object.__setattr__(self, "mid", 0.5 * (float(self.bid) + float(self.ask)) if (self.bid + self.ask) > 0 else 0.0)


def _spread_frac(c: ListedContract) -> float:
    mid = c.mid or 0.5 * (c.bid + c.ask)
    if mid <= 1e-9:
        return 1.0
    return max(0.0, (float(c.ask) - float(c.bid)) / mid)


def _liq_score(c: ListedContract) -> float:
    oi = max(0.0, float(c.oi))
    vol = max(0.0, float(c.volume))
    spr = _spread_frac(c)
    return (math.log1p(oi) + 0.5 * math.log1p(vol)) / (1.0 + 8.0 * spr)


def _iv_rank(iv: float, iv_hist_low: float = 0.12, iv_hist_high: float = 0.80) -> float:
    lo, hi = float(iv_hist_low), float(iv_hist_high)
    if hi <= lo:
        return 0.5
    return float(min(1.0, max(0.0, (float(iv) - lo) / (hi - lo))))


def score_single(
    c: ListedContract,
    *,
    spot: float,
    view: str,
    r: float = 0.04,
    q: float = 0.0,
    sigma_fallback: float = 0.28,
) -> dict[str, Any]:
    T = max(1.0, float(c.dte)) / 365.0
    iv = implied_vol(c.mid, spot, c.strike, T, r, q, c.kind) or float(sigma_fallback)
    g = greeks(spot, c.strike, T, r, iv, q, c.kind)
    mny = moneyness(spot, c.strike)
    atm = math.exp(-abs(mny) / 0.08)
    liq = _liq_score(c)
    ivr = _iv_rank(iv)
    view_n = str(view).lower()
    if view_n in ("long", "bull", "call"):
        delta_fit = max(0.0, g["delta"] if c.kind == "call" else -g["delta"])
        # Prefer 0.30–0.55 delta calls for directional longs (not 0.05 lotto, not 0.90 stock-clone).
        target = math.exp(-((abs(g["delta"]) - 0.40) ** 2) / (2 * 0.12**2))
        struct = "long_call" if c.kind == "call" else "long_put"
        edge = target * (1.0 - ivr * 0.35)  # don't overpay rich IV for longs
    elif view_n in ("short", "bear", "put"):
        target = math.exp(-((abs(g["delta"]) - 0.40) ** 2) / (2 * 0.12**2))
        struct = "long_put" if c.kind == "put" else "long_call"
        edge = target * (1.0 - ivr * 0.35)
        delta_fit = max(0.0, -g["delta"] if c.kind == "put" else g["delta"])
    else:
        # Neutral / vol: want ATM, high IV rank favors selling (iron condor) vs buying straddle.
        target = atm
        struct = "long_straddle" if ivr < 0.45 else "iron_condor"
        edge = target
        delta_fit = 1.0 - abs(g["delta"] if c.kind == "call" else 1.0 + g["delta"])
    score = 0.42 * edge + 0.33 * liq / (1.0 + liq) + 0.15 * atm + 0.10 * delta_fit
    if _spread_frac(c) > 0.18:
        score *= 0.35
    return {
        "structure": struct,
        "symbol": c.symbol,
        "kind": c.kind,
        "strike": c.strike,
        "dte": c.dte,
        "iv": iv,
        "iv_rank": ivr,
        "delta": g["delta"],
        "gamma": g["gamma"],
        "vega": g["vega"],
        "theta": g["theta"],
        "spread_frac": _spread_frac(c),
        "liq": liq,
        "score": float(score),
        "mid": c.mid,
    }


def pick_best(
    contracts: Sequence[ListedContract],
    *,
    spot: float,
    view: str,
    r: float = 0.04,
    q: float = 0.0,
) -> dict[str, Any] | None:
    if not contracts or spot <= 0:
        return None
    scored = [score_single(c, spot=spot, view=view, r=r, q=q) for c in contracts]
    scored.sort(key=lambda d: -float(d["score"]))
    best = scored[0]
    # Overlay structure recommendation from the chain, not a single wing.
    view_n = str(view).lower()
    ivr = float(best.get("iv_rank") or 0.5)
    if view_n in ("long", "bull", "call"):
        best["chosen_structure"] = "bull_call_spread" if ivr >= 0.55 else "long_call"
        if ivr >= 0.70:
            best["chosen_structure"] = "covered_call"  # own stock, sell rich calls
    elif view_n in ("short", "bear", "put"):
        best["chosen_structure"] = "bear_put_spread" if ivr >= 0.55 else "long_put"
        if ivr >= 0.70:
            best["chosen_structure"] = "protective_put"
    else:
        best["chosen_structure"] = "iron_condor" if ivr >= 0.55 else "long_straddle"
    best["alternates"] = scored[1:6]
    return best


def synthetic_chain(
    spot: float,
    *,
    dte: float = 30.0,
    sigma: float = 0.28,
    r: float = 0.04,
    q: float = 0.0,
    strikes: Iterable[float] | None = None,
) -> list[ListedContract]:
    """ATM± ladder for tests / when a live chain is unavailable."""
    spot = float(spot)
    if strikes is None:
        step = max(1.0, round(spot * 0.025, 0) or 1.0)
        strikes = [spot + i * step for i in range(-4, 5)]
    T = max(1.0, float(dte)) / 365.0
    out: list[ListedContract] = []
    for k in strikes:
        k = float(k)
        if k <= 0:
            continue
        for kind in ("call", "put"):
            px = black_scholes_call(spot, k, T, r, sigma, q) if kind == "call" else black_scholes_put(
                spot, k, T, r, sigma, q
            )
            half = max(0.01, px * 0.02)
            out.append(
                ListedContract(
                    symbol=f"SYN-{kind[0].upper()}{int(k)}",
                    kind=kind,
                    strike=k,
                    dte=float(dte),
                    bid=max(0.01, px - half),
                    ask=px + half,
                    oi=800.0,
                    volume=200.0,
                    mid=px,
                )
            )
    return out


def derivatives_rank_boost(ticker: str, *, p_up: float, spot: float | None = None) -> tuple[float, dict[str, Any]]:
    """Sleeve additive in [-1, 1]. Picks a structure from a synthetic ATM chain.

    Live quotes optional; math still runs so the factor is never unweighted.
    """
    _ = ticker
    p = float(p_up)
    if p >= 0.58:
        view = "long"
    elif p <= 0.42:
        view = "short"
    else:
        view = "neutral"
    px = float(spot) if spot and spot > 0 else 100.0
    chain = synthetic_chain(px)
    best = pick_best(chain, spot=px, view=view)
    if not best:
        return 0.0, {"structure": "equity"}
    signed = (p - 0.5) * 2.0
    boost = float(best["score"]) * signed
    if best["chosen_structure"] in ("iron_condor", "long_straddle"):
        boost *= 0.35  # vol structures shouldn't dominate equity rank
    return float(max(-1.0, min(1.0, boost))), {
        "structure": best["chosen_structure"],
        "iv": best.get("iv"),
        "delta": best.get("delta"),
        "score": best.get("score"),
    }


def options_execution_enabled() -> bool:
    return os.getenv("ALPACA_OPTIONS_ENABLED", "false").lower() in ("1", "true", "yes")
