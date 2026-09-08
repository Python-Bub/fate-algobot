"""Bitcoin / ether driver math — not equity OFI copy-pasted onto coins.

BTC is a liquidity + dollar + ETF-demand asset. The score is a weighted
blend of those public series (plus range expansion / squeeze). News is an
overlay, not the engine.

Drivers (all causal, last close known):
  • Dollar (UUP / DX-Y): inverse. Strong dollar drains BTC.
  • Real-rate proxy (^TNX): inverse. Higher yields compete with crypto.
  • Spot ETF demand (IBIT 5d minus BTC 5d): flows showing up in the wrapper.
  • Ether confirmation (ETH 5d): risk-on inside crypto.
  • Trend (BTC 5d / 20d) and Donchian 20 breakout.
  • Vol squeeze then expansion (20d vol vs 60d, then 5d vol lift).
  • Volume-ish proxy: close z vs 60d (stretch without a tape).
  • Headline tilt when the caller already classified news.

Experimental HFT uses the same score as a gate; micro timing is spread +
short mid slope, not IEX L2 (Alpaca crypto has no IEX book).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from analytics.alt_series import (
    daily_closes,
    donchian_breakout,
    realized_vol,
    ret_n,
    rolling_z,
)

FetchFn = Callable[[str, int], pd.Series | None]

# Dollar proxies in preference order (UUP is an ETF Alpaca/Yahoo both have).
_DOLLAR = ("UUP", "DX-Y.NYB", "DX=F")
_RATES = ("^TNX", "TNX", "^IRX")
_BTC = ("BTC-USD",)
_ETH = ("ETH-USD",)
_ETF = ("IBIT", "BITO", "GBTC")


def _tanh(x: float, scale: float) -> float:
    if scale <= 0:
        return 0.0
    return float(math.tanh(float(x) / float(scale)))


def _first_closes(cands: tuple[str, ...], fetch: FetchFn | None, days: int) -> pd.Series:
    for s in cands:
        ser = daily_closes(s, days=days, fetch=fetch)
        if ser is not None and len(ser) >= 8:
            return ser
    return pd.Series(dtype=float)


@dataclass
class CryptoScore:
    ticker: str
    score: float
    p_up: float
    explosive: float
    breakout: bool
    drivers: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "score": round(self.score, 4),
            "p_up": round(self.p_up, 4),
            "explosive": round(self.explosive, 4),
            "breakout": self.breakout,
            "drivers": {k: round(float(v), 4) for k, v in self.drivers.items()},
            "notes": list(self.notes),
        }


def score_crypto(
    ticker: str = "BTC-USD",
    *,
    fetch: FetchFn | None = None,
    news_tilt: float = 0.0,
    days: int = 400,
) -> CryptoScore:
    """Signed score in [-1, 1]. `p_up` is 0.5 + 0.5*score for rank mixers."""
    t = ticker.strip().upper().replace("/", "-")
    notes: list[str] = []
    btc = _first_closes(_BTC, fetch, days)
    eth = _first_closes(_ETH, fetch, days)
    if t.startswith("ETH") or t in ("ETHA", "ETHE"):
        spot = eth if len(eth) >= 8 else btc
    elif t.endswith("-USD") and t not in ("BTC-USD",):
        own = daily_closes(t, days=days, fetch=fetch)
        spot = own if own is not None and len(own) >= 8 else btc
    else:
        # BTC spot + IBIT/BITO/GBTC wrappers: score the coin.
        spot = btc
    dollar = _first_closes(_DOLLAR, fetch, days)
    rates = _first_closes(_RATES, fetch, days)
    etf = _first_closes(_ETF, fetch, days)

    dxy_5 = ret_n(dollar, 5)
    tnx_5 = ret_n(rates, 5)
    spot_5 = ret_n(spot, 5)
    spot_20 = ret_n(spot, 20)
    eth_5 = ret_n(eth, 5)
    etf_5 = ret_n(etf, 5)
    btc_5 = ret_n(btc, 5)

    dollar_inv = -_tanh(dxy_5, 0.015)
    rates_inv = -_tanh(tnx_5, 0.12)
    mom = _tanh(spot_5, 0.045)
    trend = _tanh(spot_20, 0.10)
    eth_conf = _tanh(eth_5, 0.06)
    etf_flow = _tanh(etf_5 - btc_5, 0.025)
    stretch = _tanh(rolling_z(spot, 60), 1.8)

    v5 = realized_vol(spot, 5)
    v20 = realized_vol(spot, 20)
    v60 = realized_vol(spot, 60)
    squeeze = 1.0 if (v60 > 1e-8 and v20 < 0.72 * v60) else 0.0
    expand = _tanh((v5 / v20 - 1.0) if v20 > 1e-8 else 0.0, 0.55)
    brk = donchian_breakout(spot, 20)
    news = max(-1.0, min(1.0, float(news_tilt or 0.0)))

    if dollar.empty:
        notes.append("no_dollar_proxy")
    if rates.empty:
        notes.append("no_rates_proxy")
    if etf.empty:
        notes.append("no_etf_proxy")

    # Weights sum to 1. Breakout is a 0/1 feature, not a return.
    brk_f = 1.0 if brk else 0.0
    raw = (
        0.16 * dollar_inv
        + 0.12 * rates_inv
        + 0.16 * mom
        + 0.10 * trend
        + 0.10 * etf_flow
        + 0.08 * eth_conf
        + 0.08 * stretch
        + 0.10 * brk_f
        + 0.06 * squeeze * max(0.0, expand)
        + 0.04 * news
    )
    score = max(-1.0, min(1.0, float(raw)))
    # Explosiveness: breakout + vol expansion + positive 5d, scaled by dollar/rates tailwind.
    tailwind = 0.5 + 0.25 * dollar_inv + 0.25 * rates_inv
    explosive = max(
        0.0,
        min(
            1.0,
            (0.45 * brk_f + 0.30 * max(0.0, expand) + 0.25 * max(0.0, mom))
            * max(0.15, tailwind),
        ),
    )
    p_up = 0.5 + 0.5 * score
    drivers = {
        "dollar_inv": dollar_inv,
        "rates_inv": rates_inv,
        "mom_5d": mom,
        "trend_20d": trend,
        "etf_flow": etf_flow,
        "eth_confirm": eth_conf,
        "stretch_z": stretch,
        "breakout20": brk_f,
        "squeeze": squeeze,
        "vol_expand": expand,
        "news": news,
        "dxy_5d": dxy_5,
        "tnx_5d": tnx_5,
        "spot_5d": spot_5,
        "etf_5d": etf_5,
        "btc_5d": btc_5,
    }
    if brk and explosive >= 0.55:
        notes.append("explosive_up")
    return CryptoScore(
        ticker=t,
        score=score,
        p_up=p_up,
        explosive=explosive,
        breakout=brk,
        drivers=drivers,
        notes=notes,
    )


def should_fire_hft(
    cs: CryptoScore,
    *,
    spread_bps: float,
    mid_slope: float,
    max_spread_bps: float = 12.0,
    min_score: float = 0.18,
    min_explosive: float = 0.28,
) -> tuple[bool, str]:
    """Experimental crypto HFT entry gate. Long-only. No IEX book."""
    if spread_bps > float(max_spread_bps) or spread_bps < 0:
        return False, "spread"
    if cs.score < float(min_score) and cs.explosive < float(min_explosive):
        return False, "score"
    if mid_slope < -1e-5:
        return False, "mid_fade"
    if cs.score >= float(min_score) or (cs.breakout and cs.explosive >= float(min_explosive)):
        return True, "crypto_math"
    return False, "hold"


def overlay_equity_p(equity_p: float, crypto_p: float, mix: float = 0.80) -> float:
    """Own crypto p_up — equity XGB on coin bars is not the thesis."""
    try:
        m = max(0.0, min(1.0, float(mix)))
    except (TypeError, ValueError):
        m = 0.80
    try:
        eq = float(equity_p)
    except (TypeError, ValueError):
        eq = 0.5
    try:
        cp = float(crypto_p)
    except (TypeError, ValueError):
        cp = eq
    return max(0.01, min(0.99, (1.0 - m) * eq + m * cp))
