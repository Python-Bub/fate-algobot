"""
Classic value-investing toolkit (book-aligned formulas + screens).

Intrinsic Value (DCF with terminal value):
  IV = Σ_{t=1..n} CF_t / (1+r)^t  +  TV / (1+r)^n
  TV = CF_n × (1+g) / (r − g)     requiring g < r

Also implements Graham Net-Net, deep-value (low P/E + P/B < 1), Buffett-style
moat proxies, and contrarian tilt — used as a *small* rank bias, never replacing
ML heads.

Chapters can keep appending; each screen is independently gated by env.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from utils import log

# ── Formulas (exact from the book) ───────────────────────────────────────────


def terminal_value(cf_n: float, *, r: float, g: float) -> float:
    """
    TV = CF_n × (1+g) / (r − g)

    Raises ValueError if g >= r (undefined / negative denominator).
    """
    r = float(r)
    g = float(g)
    if g >= r:
        raise ValueError(f"perpetual growth g={g} must be < discount rate r={r}")
    return float(cf_n) * (1.0 + g) / (r - g)


def intrinsic_value(
    cash_flows: list[float] | tuple[float, ...] | np.ndarray,
    *,
    r: float,
    tv: float | None = None,
    g: float | None = None,
) -> float:
    """
    IV = Σ CF_t/(1+r)^t + TV/(1+r)^n

    If tv is omitted and g is provided, TV is computed from the last CF via
    terminal_value(CF_n, r=r, g=g).
    """
    cfs = [float(x) for x in cash_flows]
    if not cfs:
        return 0.0
    r = float(r)
    n = len(cfs)
    pv_cfs = sum(cf / ((1.0 + r) ** t) for t, cf in enumerate(cfs, start=1))
    if tv is None:
        if g is None:
            tv = 0.0
        else:
            tv = terminal_value(cfs[-1], r=r, g=float(g))
    pv_tv = float(tv) / ((1.0 + r) ** n)
    return float(pv_cfs + pv_tv)


def margin_of_safety(intrinsic: float, market_price: float) -> float:
    """Buffer (IV − price) / IV. Positive ⇒ buy price below intrinsic."""
    iv = float(intrinsic)
    px = float(market_price)
    if iv <= 0 or px <= 0:
        return 0.0
    return float((iv - px) / iv)


def ncav(current_assets: float, total_liabilities: float) -> float:
    """Net Current Asset Value = current assets − total liabilities (Graham)."""
    return float(current_assets) - float(total_liabilities)


def is_graham_net_net(*, ncav_total: float, market_cap: float, multiple: float = 1.5) -> bool:
    """True when NCAV ≥ multiple × market cap (classic Net-Net screen)."""
    if market_cap <= 0 or ncav_total <= 0:
        return False
    return float(ncav_total) >= float(multiple) * float(market_cap)


# ── Fundamentals → projected CF path ─────────────────────────────────────────


@dataclass
class ValueThesis:
    symbol: str
    intrinsic_per_share: float = 0.0
    market_price: float = 0.0
    margin_of_safety: float = 0.0
    terminal_value_total: float = 0.0
    intrinsic_equity: float = 0.0
    deep_value: bool = False
    graham_net_net: bool = False
    buffett_quality: float = 0.0
    contrarian: float = 0.0
    boost: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


_CACHE: dict[str, tuple[float, ValueThesis]] = {}


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _b(name: str, default: bool = True) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes")


def _safe(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        if v != v:  # NaN
            return default
        return v
    except Exception:
        return default


def project_cash_flows(
    cf0: float,
    *,
    n: int,
    g_near: float,
) -> list[float]:
    """Growing annuity: CF_t = CF_0 × (1+g_near)^t  for t = 1..n."""
    out: list[float] = []
    base = float(cf0)
    g = float(g_near)
    for t in range(1, int(n) + 1):
        out.append(base * ((1.0 + g) ** t))
    return out


def _yahoo_info(symbol: str) -> dict[str, Any]:
    import yfinance as yf

    tk = yf.Ticker(symbol)
    info = tk.info or {}
    return info if isinstance(info, dict) else {}


def analyze_value(symbol: str, *, info: dict[str, Any] | None = None) -> ValueThesis:
    """
    Build a ValueThesis from live fundamentals (Yahoo) using book formulas.

    Cash-flow proxy: freeCashflow (TTM). Shares outstanding → per-share IV.
    Discount r and growth g from env (defaults r=10%, g=3%, n=5).
    """
    sym = symbol.strip().upper()
    thesis = ValueThesis(symbol=sym)
    if not _b("USE_VALUE_INVESTING", True):
        return thesis

    r = _f("VALUE_IV_DISCOUNT_RATE", 0.10)
    g = _f("VALUE_IV_PERP_GROWTH", 0.03)
    g_near = _f("VALUE_IV_NEAR_GROWTH", 0.05)
    n = int(_f("VALUE_IV_YEARS", 5))
    # Hard book rule: g < r
    if g >= r:
        g = max(0.0, r - 0.01)
        thesis.meta["g_clamped"] = True

    try:
        data = info if info is not None else _yahoo_info(sym)
    except Exception as e:
        thesis.meta["error"] = str(e)[:120]
        return thesis

    fcf = _safe(data.get("freeCashflow"))
    shares = _safe(data.get("sharesOutstanding"))
    price = _safe(data.get("currentPrice") or data.get("regularMarketPrice"))
    mcap = _safe(data.get("marketCap"))
    tpe = _safe(data.get("trailingPE"))
    pb = _safe(data.get("priceToBook"))
    ca = _safe(data.get("totalCurrentAssets") or data.get("currentAssets"))
    tl = _safe(data.get("totalLiab") or data.get("totalDebt"))
    # Prefer totalLiabilities-like if present
    for k in ("totalLiab", "totalLiabilitiesNetMinorityInterest", "totalDebt"):
        if data.get(k) is not None:
            tl = _safe(data.get(k))
            break
    de = _safe(data.get("debtToEquity"))
    roe = _safe(data.get("returnOnEquity"))
    pm = _safe(data.get("profitMargins"))
    q_chg = _safe(data.get("fiftyTwoWeekChange") or data.get("52WeekChange"))

    thesis.market_price = price
    thesis.meta.update(
        {
            "fcf": fcf,
            "shares": shares,
            "r": r,
            "g": g,
            "g_near": g_near,
            "n": n,
            "pe": tpe,
            "pb": pb,
            "mcap": mcap,
        }
    )

    # Deep value: historically low P/E + P/B < 1 (book screen)
    pe_max = _f("VALUE_DEEP_PE_MAX", 12.0)
    thesis.deep_value = (0 < tpe <= pe_max) and (0 < pb < 1.0) and fcf > 0 and de < _f("VALUE_DEEP_DE_MAX", 100.0)

    # Graham Net-Net: NCAV ≥ 1.5 × market cap
    if ca > 0 and tl >= 0 and mcap > 0:
        ncv = ncav(ca, tl)
        thesis.graham_net_net = is_graham_net_net(
            ncav_total=ncv,
            market_cap=mcap,
            multiple=_f("VALUE_GRAHAM_NCAV_MULT", 1.5),
        )
        thesis.meta["ncav"] = ncv
    else:
        # Fallback: priceToBook very depressed + low debt as soft Net-Net proxy
        thesis.graham_net_net = 0 < pb < 0.66 and de < 50 and mcap > 0
        thesis.meta["ncav_proxy"] = True

    # Buffett quality / moat proxy: ROE, margins, modest leverage
    thesis.buffett_quality = float(
        np.clip(
            0.40 * np.tanh(roe * 4.0)
            + 0.35 * np.tanh(pm * 6.0)
            + 0.25 * np.tanh((150.0 - de) / 150.0),
            -1.0,
            1.0,
        )
    )

    # Contrarian: temporary mark-down with intact quality (soft)
    if q_chg < -0.15 and thesis.buffett_quality > 0.15:
        thesis.contrarian = float(np.clip(-q_chg * 0.5 * thesis.buffett_quality, 0.0, 0.6))
    else:
        thesis.contrarian = 0.0

    # DCF intrinsic value when FCF + shares known
    if fcf > 0 and shares > 0 and price > 0:
        try:
            cfs = project_cash_flows(fcf, n=n, g_near=g_near)
            tv = terminal_value(cfs[-1], r=r, g=g)
            iv_eq = intrinsic_value(cfs, r=r, tv=tv)
            iv_ps = iv_eq / shares
            thesis.terminal_value_total = tv
            thesis.intrinsic_equity = iv_eq
            thesis.intrinsic_per_share = iv_ps
            thesis.margin_of_safety = margin_of_safety(iv_ps, price)
            thesis.meta["cash_flows"] = cfs
        except ValueError as e:
            thesis.meta["dcf_error"] = str(e)

    # Rank boost: MOS + screens (small, bounded)
    boost = 0.0
    mos = thesis.margin_of_safety
    if mos > 0:
        boost += _f("VALUE_W_MOS", 0.35) * float(np.tanh(mos * 2.0))
    elif mos < -0.25:
        # Expensive vs DCF — mild negative (not a hard block)
        boost += _f("VALUE_W_MOS", 0.35) * float(np.tanh(mos * 1.5))

    if thesis.deep_value:
        boost += _f("VALUE_W_DEEP", 0.12)
    if thesis.graham_net_net:
        boost += _f("VALUE_W_GRAHAM", 0.18)
    boost += _f("VALUE_W_BUFFETT", 0.08) * max(0.0, thesis.buffett_quality)
    boost += _f("VALUE_W_CONTRARIAN", 0.10) * thesis.contrarian

    gain = _f("VALUE_BOOST_GAIN", 0.55)
    cap = _f("VALUE_BOOST_CAP", 0.25)
    thesis.boost = float(np.clip(boost * gain, -cap, cap))
    return thesis


def value_investing_rank_boost(symbol: str) -> tuple[float, dict[str, Any]]:
    """
    Cached rank bias for unified pipeline / fortress.

    Returns (boost, meta). Weight RANK_W_VALUE applied by caller.
    """
    if not _b("USE_VALUE_INVESTING", True):
        return 0.0, {"disabled": True}

    sym = symbol.strip().upper()
    ttl = _f("VALUE_CACHE_TTL_SEC", 3600.0)
    now = time.time()
    hit = _CACHE.get(sym)
    if hit and (now - hit[0]) < ttl:
        t = hit[1]
        return float(t.boost), {"cached": True, **t.meta, "mos": t.margin_of_safety,
                                "deep_value": t.deep_value, "graham_net_net": t.graham_net_net,
                                "iv_ps": t.intrinsic_per_share, "boost_raw": t.boost}

    try:
        thesis = analyze_value(sym)
    except Exception as e:
        log.debug("[VALUE] %s: %s", sym, e)
        return 0.0, {"error": str(e)[:120]}

    _CACHE[sym] = (now, thesis)
    w = _f("RANK_W_VALUE", 0.17)
    applied = float(w * thesis.boost)
    meta = {
        "cached": False,
        "mos": thesis.margin_of_safety,
        "iv_ps": thesis.intrinsic_per_share,
        "price": thesis.market_price,
        "deep_value": thesis.deep_value,
        "graham_net_net": thesis.graham_net_net,
        "buffett_quality": thesis.buffett_quality,
        "contrarian": thesis.contrarian,
        "boost_raw": thesis.boost,
        "applied": applied,
        **thesis.meta,
    }
    return applied, meta
