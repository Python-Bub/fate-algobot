"""Per-commodity driver math — silver is not gold, oil is not copper.

Each metal / energy has a different dependence structure. We score the
liquid ETF the book actually trades (SLV, GLD, USO, CPER, UNG, …) from
the public futures / rate / dollar series, not from equity OFI.

Silver (SLV / SIVR)
  Gold/silver ratio mean-reversion (high GSR → silver cheap vs gold),
  industrial confirmation (copper), dollar inverse, real-rate inverse,
  gold beta. Silver is the hybrid: half precious, half industrial.

Gold (GLD / IAU / GLDM)
  Real rates (primary), dollar, mild VIX haven, own trend. Copper is
  *not* a gold driver — that would contaminate the haven sleeve.

Oil (USO / BNO)
  Dollar inverse, own 20d trend (oil is persistent), energy-equity
  confirmation (XLE). No gold/silver ratio.

Copper (CPER)
  Dollar inverse, risk-on (SPY), own trend. Rates matter less than for gold.

Nat gas (UNG)
  Own momentum + vol (weather/storage we do not invent). Dollar mild.

Miners (NEM, AG, FCX, …)
  45% of the underlying metal score — they are levered claims on the
  metal, not the metal itself.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from analytics.alt_series import (
    aligned_ratio,
    daily_closes,
    realized_vol,
    ret_n,
    rolling_z,
)

FetchFn = Callable[[str, int], pd.Series | None]

_DOLLAR = ("UUP", "DX-Y.NYB", "DX=F")
_RATES = ("^TNX", "TNX")
_VIX = ("^VIX", "VIX")
_SPY = ("SPY",)
_GOLD = ("GC=F", "GLD")
_SILVER = ("SI=F", "SLV")
_COPPER = ("HG=F", "CPER")
_OIL = ("CL=F", "USO")
_GAS = ("NG=F", "UNG")
_XLE = ("XLE",)

SILVER_ETFS = frozenset({"SLV", "SIVR"})
GOLD_ETFS = frozenset({"GLD", "IAU", "GLDM"})
OIL_ETFS = frozenset({"USO", "BNO"})
GAS_ETFS = frozenset({"UNG"})
COPPER_ETFS = frozenset({"CPER"})
PLAT_ETFS = frozenset({"PPLT"})
PALL_ETFS = frozenset({"PALL"})
AG_ETFS = frozenset({"DBA", "WEAT", "CORN", "SOYB"})
BASKET_ETFS = frozenset({"DBC", "PDBC", "GSG"})

SILVER_MINERS = frozenset({"AG", "HL", "PAAS", "MAG", "SVM", "EXK", "CDE", "SILV"})
GOLD_MINERS = frozenset({"NEM", "GOLD", "AEM", "KGC", "AU", "FNV", "WPM", "RGLD", "EGO", "IAG", "BTG"})
COPPER_MINERS = frozenset({"FCX", "SCCO", "HBM", "TECK", "AA", "NUE"})


def _tanh(x: float, scale: float) -> float:
    if scale <= 0:
        return 0.0
    return float(math.tanh(float(x) / float(scale)))


def _first(cands: tuple[str, ...], fetch: FetchFn | None, days: int) -> pd.Series:
    for s in cands:
        ser = daily_closes(s, days=days, fetch=fetch)
        if ser is not None and len(ser) >= 8:
            return ser
    return pd.Series(dtype=float)


@dataclass
class CommodityScore:
    ticker: str
    family: str
    score: float
    p_up: float
    drivers: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "family": self.family,
            "score": round(self.score, 4),
            "p_up": round(self.p_up, 4),
            "drivers": {k: round(float(v), 4) for k, v in self.drivers.items()},
            "notes": list(self.notes),
        }


def classify_commodity(ticker: str) -> str:
    t = ticker.strip().upper()
    if t in SILVER_ETFS or t in SILVER_MINERS:
        return "silver" if t in SILVER_ETFS else "silver_miner"
    if t in GOLD_ETFS or t in GOLD_MINERS:
        return "gold" if t in GOLD_ETFS else "gold_miner"
    if t in OIL_ETFS:
        return "oil"
    if t in GAS_ETFS:
        return "natgas"
    if t in COPPER_ETFS or t in COPPER_MINERS:
        return "copper" if t in COPPER_ETFS else "copper_miner"
    if t in PLAT_ETFS:
        return "platinum"
    if t in PALL_ETFS:
        return "palladium"
    if t in AG_ETFS:
        return "ag"
    if t in BASKET_ETFS:
        return "basket"
    return ""


def _common_macro(fetch: FetchFn | None, days: int) -> dict[str, float]:
    dollar = _first(_DOLLAR, fetch, days)
    rates = _first(_RATES, fetch, days)
    vix = _first(_VIX, fetch, days)
    spy = _first(_SPY, fetch, days)
    dxy_5 = ret_n(dollar, 5)
    tnx_5 = ret_n(rates, 5)
    vix_5 = ret_n(vix, 5)
    spy_5 = ret_n(spy, 5)
    return {
        "dollar_inv": -_tanh(dxy_5, 0.015),
        "rates_inv": -_tanh(tnx_5, 0.12),
        "vix_up": _tanh(vix_5, 0.12),
        "risk_on": _tanh(spy_5, 0.025),
        "dxy_5d": dxy_5,
        "tnx_5d": tnx_5,
        "vix_5d": vix_5,
        "spy_5d": spy_5,
    }


def score_silver(fetch: FetchFn | None = None, days: int = 400) -> tuple[float, dict[str, float], list[str]]:
    gold = _first(_GOLD, fetch, days)
    silver = _first(_SILVER, fetch, days)
    copper = _first(_COPPER, fetch, days)
    macro = _common_macro(fetch, days)
    notes: list[str] = []
    gsr = aligned_ratio(gold, silver)
    gsr_z = rolling_z(gsr, min(120, max(20, len(gsr)))) if len(gsr) >= 20 else 0.0
    # High gold/silver ratio → silver cheap vs gold → long silver.
    cheap = _tanh(gsr_z, 1.15)
    industrial = _tanh(ret_n(copper, 5), 0.04)
    gold_beta = _tanh(ret_n(gold, 5), 0.03)
    own = _tanh(ret_n(silver, 5), 0.04)
    stretch = _tanh(rolling_z(silver, 60), 1.8)
    if gsr.empty:
        notes.append("no_gsr")
    raw = (
        0.28 * cheap
        + 0.20 * industrial
        + 0.18 * float(macro["dollar_inv"])
        + 0.16 * float(macro["rates_inv"])
        + 0.10 * gold_beta
        + 0.08 * own
        - 0.04 * abs(stretch) * (1.0 if stretch > 1.4 else 0.0)
    )
    drivers = {
        **macro,
        "gsr_z": gsr_z,
        "silver_cheap_vs_gold": cheap,
        "copper_5d": industrial,
        "gold_5d": gold_beta,
        "silver_5d": own,
        "stretch": stretch,
        "gsr_last": float(gsr.iloc[-1]) if len(gsr) else 0.0,
    }
    return max(-1.0, min(1.0, float(raw))), drivers, notes


def score_gold(fetch: FetchFn | None = None, days: int = 400) -> tuple[float, dict[str, float], list[str]]:
    gold = _first(_GOLD, fetch, days)
    macro = _common_macro(fetch, days)
    own = _tanh(ret_n(gold, 5), 0.03)
    trend = _tanh(ret_n(gold, 20), 0.08)
    # Gold: rates + dollar dominate. VIX haven is mild. Copper is excluded on purpose.
    raw = (
        0.34 * float(macro["rates_inv"])
        + 0.28 * float(macro["dollar_inv"])
        + 0.12 * float(macro["vix_up"])
        + 0.16 * own
        + 0.10 * trend
    )
    return max(-1.0, min(1.0, float(raw))), {**macro, "gold_5d": own, "gold_20d": trend}, []


def score_oil(fetch: FetchFn | None = None, days: int = 400) -> tuple[float, dict[str, float], list[str]]:
    oil = _first(_OIL, fetch, days)
    xle = _first(_XLE, fetch, days)
    macro = _common_macro(fetch, days)
    own5 = _tanh(ret_n(oil, 5), 0.05)
    own20 = _tanh(ret_n(oil, 20), 0.12)  # oil trends
    energy_eq = _tanh(ret_n(xle, 5), 0.04)
    vol = realized_vol(oil, 20)
    raw = (
        0.22 * float(macro["dollar_inv"])
        + 0.28 * own20
        + 0.22 * own5
        + 0.18 * energy_eq
        + 0.10 * float(macro["risk_on"])
        - 0.08 * _tanh(vol - 0.03, 0.02)  # chaotic tape: fade size, not invert
    )
    return (
        max(-1.0, min(1.0, float(raw))),
        {**macro, "oil_5d": own5, "oil_20d": own20, "xle_5d": energy_eq, "oil_vol20": vol},
        [],
    )


def score_copper(fetch: FetchFn | None = None, days: int = 400) -> tuple[float, dict[str, float], list[str]]:
    cu = _first(_COPPER, fetch, days)
    macro = _common_macro(fetch, days)
    own = _tanh(ret_n(cu, 5), 0.04)
    trend = _tanh(ret_n(cu, 20), 0.10)
    raw = (
        0.28 * float(macro["dollar_inv"])
        + 0.28 * float(macro["risk_on"])
        + 0.24 * own
        + 0.20 * trend
    )
    return max(-1.0, min(1.0, float(raw))), {**macro, "copper_5d": own, "copper_20d": trend}, []


def score_natgas(fetch: FetchFn | None = None, days: int = 400) -> tuple[float, dict[str, float], list[str]]:
    gas = _first(_GAS, fetch, days)
    macro = _common_macro(fetch, days)
    own = _tanh(ret_n(gas, 5), 0.08)
    trend = _tanh(ret_n(gas, 20), 0.18)
    vol = realized_vol(gas, 10)
    # Gas is mean-reverting at short horizons; fade stretch, follow 20d.
    stretch = _tanh(rolling_z(gas, 40), 1.4)
    raw = 0.40 * trend + 0.20 * own + 0.15 * float(macro["dollar_inv"]) - 0.25 * stretch
    return (
        max(-1.0, min(1.0, float(raw))),
        {**macro, "gas_5d": own, "gas_20d": trend, "stretch": stretch, "gas_vol10": vol},
        ["mean_revert_short"],
    )


def score_commodity(
    ticker: str,
    *,
    fetch: FetchFn | None = None,
    days: int = 400,
) -> CommodityScore:
    t = ticker.strip().upper()
    fam = classify_commodity(t)
    if not fam:
        return CommodityScore(ticker=t, family="", score=0.0, p_up=0.5)
    miner_w = 0.45 if fam.endswith("_miner") else 1.0
    base = fam.replace("_miner", "")
    if base == "silver":
        raw, drivers, notes = score_silver(fetch=fetch, days=days)
    elif base == "gold" or base in ("platinum", "palladium"):
        raw, drivers, notes = score_gold(fetch=fetch, days=days)
        if base != "gold":
            notes = list(notes) + [f"{base}_uses_gold_haven_math"]
    elif base == "oil":
        raw, drivers, notes = score_oil(fetch=fetch, days=days)
    elif base == "copper":
        raw, drivers, notes = score_copper(fetch=fetch, days=days)
    elif base == "natgas":
        raw, drivers, notes = score_natgas(fetch=fetch, days=days)
    elif base in ("ag", "basket"):
        g, gd, _ = score_gold(fetch=fetch, days=days)
        o, od, _ = score_oil(fetch=fetch, days=days)
        c, cd, _ = score_copper(fetch=fetch, days=days)
        raw = 0.34 * g + 0.33 * o + 0.33 * c
        drivers = {**gd, **{f"oil_{k}": v for k, v in od.items()}, **{f"cu_{k}": v for k, v in cd.items()}}
        notes = ["blend_gold_oil_copper"]
    else:
        raw, drivers, notes = 0.0, {}, []
    score = max(-1.0, min(1.0, float(raw) * miner_w))
    if miner_w < 1.0:
        notes = list(notes) + ["miner_0.45x_metal"]
    return CommodityScore(
        ticker=t,
        family=fam,
        score=score,
        p_up=0.5 + 0.5 * score,
        drivers=drivers,
        notes=notes,
    )
