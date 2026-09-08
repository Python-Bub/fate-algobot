"""
Composite book-investing rank boost — blends live formula families.

Layers (small, bounded — never replace ML heads):
  value (DCF/Graham/Buffett), growth (PEG/GARP), income (GGM),
  quant factor tilts, technical composite when history available.
"""

from __future__ import annotations

import os
import time
from typing import Any

import numpy as np

from utils import log

_CACHE: dict[str, tuple[float, float, dict[str, Any]]] = {}


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
        if v != v:
            return default
        return v
    except Exception:
        return default


def book_rank_boost(symbol: str) -> tuple[float, dict[str, Any]]:
    """
    Multi-family investing-book boost for a ticker.

    Returns (applied_boost, meta). Caller may also apply RANK_W_BOOK.
    """
    if not _b("USE_INVESTING_BOOK", True):
        return 0.0, {"disabled": True}

    sym = symbol.strip().upper()
    ttl = _f("BOOK_CACHE_TTL_SEC", 3600.0)
    now = time.time()
    hit = _CACHE.get(sym)
    if hit and (now - hit[0]) < ttl:
        return float(hit[1]), {**(hit[2] or {}), "cached": True}

    meta: dict[str, Any] = {"symbol": sym, "families": {}}
    terms: list[tuple[float, float]] = []

    # Value DCF/Graham is already live via analytics.value_investing in the
    # rank pipeline — only include it here when that module is disabled.
    if not _b("USE_VALUE_INVESTING", True):
        try:
            from analytics.value_investing import analyze_value

            thesis = analyze_value(sym)
            v_raw = float(thesis.boost)
            terms.append((_f("BOOK_W_VALUE", 0.35), v_raw))
            meta["families"]["value"] = {
                "boost": v_raw,
                "mos": thesis.margin_of_safety,
                "deep_value": thesis.deep_value,
                "graham_net_net": thesis.graham_net_net,
            }
        except Exception as e:
            log.debug("[BOOK] value %s: %s", sym, e)
            meta["families"]["value"] = {"error": str(e)[:80]}
    else:
        meta["families"]["value"] = {"skipped": "USE_VALUE_INVESTING already live"}

    # Shared Yahoo info for growth/income/quant (+ optional history)
    info: dict[str, Any] = {}
    closes: list[float] = []
    try:
        import yfinance as yf

        tk = yf.Ticker(sym)
        info = tk.info or {}
        if _b("BOOK_USE_TECHNICAL", True) or _b("BOOK_USE_MOMENTUM", True):
            h = tk.history(period="1y")
            if h is not None and len(h) >= 30:
                closes = h["Close"].astype(float).tolist()
    except Exception as e:
        meta["yahoo_error"] = str(e)[:80]

    pe = _safe(info.get("trailingPE") or info.get("forwardPE"))
    earn_g = _safe(info.get("earningsGrowth") or info.get("earningsQuarterlyGrowth"))
    # Yahoo earningsGrowth often as fraction (0.15); convert to %
    earn_g_pct = earn_g * 100.0 if abs(earn_g) < 3 else earn_g
    rev_g = _safe(info.get("revenueGrowth"))
    rev_g_pct = rev_g * 100.0 if abs(rev_g) < 3 else rev_g
    roe = _safe(info.get("returnOnEquity"))
    pm = _safe(info.get("profitMargins"))
    de = _safe(info.get("debtToEquity"))
    pb = _safe(info.get("priceToBook"))
    mcap = _safe(info.get("marketCap"))
    price = _safe(info.get("currentPrice") or info.get("regularMarketPrice"))
    div_rate = _safe(info.get("dividendRate"))
    # Prefer DPS/price; Yahoo dividendYield units are inconsistent across tickers
    yld_from_rate = (div_rate / price) if (div_rate > 0 and price > 0) else 0.0
    yld_raw = _safe(info.get("dividendYield"))
    if 0 < yld_raw <= 0.20:
        div_yield_frac = yld_raw
    elif yld_raw > 0.20:
        # Sometimes quoted as percent (e.g. 2.5) rather than 0.025
        div_yield_frac = yld_raw / 100.0 if yld_raw < 50 else 0.0
    else:
        div_yield_frac = 0.0
    if yld_from_rate > 0:
        div_yield_frac = yld_from_rate
    payout = _safe(info.get("payoutRatio"))
    eps = _safe(info.get("trailingEps"))

    # ── Growth / GARP ────────────────────────────────────────────────────
    try:
        from investing.formulas.growth import (
            compounder_score,
            garp_score,
            hypergrowth_score,
            peg_ratio,
            quality_growth_score,
        )

        peg = peg_ratio(pe, earn_g_pct) if pe > 0 and earn_g_pct > 0 else float("nan")
        g_score = garp_score(pe, earn_g_pct) if pe > 0 and earn_g_pct > 0 else 0.0
        h_score = hypergrowth_score(rev_g_pct / 100.0 if rev_g_pct else 0.0, earn_g_pct / 100.0 if earn_g_pct else 0.0)
        q_score = quality_growth_score(roe, pm, de, rev_g if abs(rev_g) < 3 else rev_g / 100.0)
        c_score = compounder_score(roe, earn_g if abs(earn_g) < 3 else earn_g / 100.0, payout)
        g_blend = 0.40 * g_score + 0.20 * h_score + 0.20 * q_score + 0.20 * c_score
        terms.append((_f("BOOK_W_GROWTH", 0.25), float(g_blend)))
        meta["families"]["growth"] = {
            "peg": None if peg != peg else round(peg, 3),
            "garp": round(g_score, 3),
            "hyper": round(h_score, 3),
            "quality": round(q_score, 3),
            "compounder": round(c_score, 3),
            "blend": round(g_blend, 3),
        }
    except Exception as e:
        meta["families"]["growth"] = {"error": str(e)[:80]}

    # ── Income / Gordon ──────────────────────────────────────────────────
    try:
        from investing.formulas.income import (
            dividend_coverage,
            gordon_growth_value,
            high_yield_score,
        )

        r = _f("BOOK_DDM_R", 0.09)
        g = _f("BOOK_DDM_G", 0.03)
        if g >= r:
            g = r - 0.01
        inc = 0.0
        ggm_iv = 0.0
        if div_rate > 0 and price > 0:
            d1 = div_rate * (1.0 + g)
            try:
                ggm_iv = gordon_growth_value(d1, r, g)
                mos = (ggm_iv - price) / ggm_iv if ggm_iv > 0 else 0.0
                inc += float(np.tanh(mos * 2.0)) * 0.6
            except ValueError:
                pass
            cov = dividend_coverage(eps, div_rate) if eps else 0.0
            inc += 0.4 * high_yield_score(div_yield_frac, payout, cov)
        terms.append((_f("BOOK_W_INCOME", 0.15), float(np.clip(inc, -1, 1))))
        meta["families"]["income"] = {
            "ggm_iv": round(ggm_iv, 3),
            "div_yield": round(div_yield_frac, 4),
            "score": round(inc, 3),
        }
    except Exception as e:
        meta["families"]["income"] = {"error": str(e)[:80]}

    # ── Quant factors ────────────────────────────────────────────────────
    try:
        from investing.formulas.quant import factor_tilt_score

        mom = 0.0
        if len(closes) > 42:
            # 12-1 momentum proxy: skip last ~21 trading days
            mom = float(closes[-22] / closes[0] - 1.0)
        ft = factor_tilt_score(pb=pb, pe=pe, mcap=mcap, mom_12_1=mom, roe=roe)
        terms.append((_f("BOOK_W_QUANT", 0.15), float(ft)))
        meta["families"]["quant"] = {"factor_tilt": round(float(ft), 3), "mom_12_1": round(mom, 3)}
    except Exception as e:
        meta["families"]["quant"] = {"error": str(e)[:80]}

    # ── Technical ────────────────────────────────────────────────────────
    if _b("BOOK_USE_TECHNICAL", True):
        try:
            from investing.formulas.technical import technical_composite

            tech = float(technical_composite(closes[-126:])) if len(closes) >= 30 else 0.0
            terms.append((_f("BOOK_W_TECHNICAL", 0.10), tech))
            meta["families"]["technical"] = {"score": round(tech, 3)}
        except Exception as e:
            meta["families"]["technical"] = {"error": str(e)[:80]}

    # ── Cramer / investor signal (math tilt only — never letter favoritism) ──
    cramer_part = 0.0
    if _b("BOOK_USE_CRAMER", True):
        try:
            from intel.cramer_picks import cramer_boost_for

            cr = float(cramer_boost_for(sym))
            cramer_part = _f("BOOK_W_CRAMER", 0.08) * cr
            terms.append((_f("BOOK_W_CRAMER", 0.08), cr))
            meta["families"]["cramer"] = {"boost": round(cr, 4), "weighted": round(cramer_part, 4)}
        except Exception as e:
            meta["families"]["cramer"] = {"error": str(e)[:80]}

    # ── Ingested guide parts (book_strategies.json) — coverage tilt only ──
    if _b("BOOK_USE_INGESTED", True):
        try:
            import json
            from pathlib import Path

            sp = Path(__file__).resolve().parents[1] / "data" / "intel" / "book_strategies.json"
            if sp.is_file():
                doc = json.loads(sp.read_text(encoding="utf-8"))
                fams = set(doc.get("families") or [])
                n_parts = int(doc.get("parts_indexed") or len(doc.get("strategies") or []) or 0)
                # Modest coverage signal: more ingested families → tiny confidence tilt
                # (does not invent alpha; amplifies that the book sleeve is wired)
                cov = min(1.0, len(fams) / 7.0) * min(1.0, 0.35 + 0.15 * n_parts)
                w_ing = _f("BOOK_W_INGESTED", 0.08)
                if cov > 0 and terms:
                    from analytics.vector_math import l1_weighted_sum

                    pre = l1_weighted_sum([s for _, s in terms], [w for w, _ in terms])
                    sign = 1.0 if pre >= 0 else -1.0
                    terms.append((w_ing * cov, sign * abs(float(np.tanh(abs(pre))))))
                meta["families"]["ingested_guide"] = {
                    "families": sorted(fams),
                    "parts_indexed": n_parts,
                    "coverage": round(cov, 3),
                    "source": doc.get("source_path"),
                }
        except Exception as e:
            meta["families"]["ingested_guide"] = {"error": str(e)[:80]}

    # Lee-Chin: few high-quality businesses, understood, held (small tilt).
    if _b("USE_LEE_CHIN", True):
        try:
            from investing.knowledge.lee_chin import lee_chin_tilt

            lc = float(lee_chin_tilt(info) or 0.0)
            if abs(lc) > 1e-6:
                terms.append((_f("BOOK_W_LEE_CHIN", 0.12), lc))
                meta["families"]["lee_chin"] = {"tilt": round(lc, 4)}
        except Exception as e:
            meta["families"]["lee_chin"] = {"error": str(e)[:80]}

    # Free undervaluation news investigation (Google RSS / Yahoo / DDG — no paid keys)
    if _b("USE_FREE_VALUE_NEWS", True):
        try:
            from intel.free_news_investigator import tilt_for

            vt = float(tilt_for(sym) or 0.0)
            if abs(vt) > 1e-6:
                w_vn = _f("BOOK_W_VALUE_NEWS", 0.12)
                terms.append((w_vn, vt))
                meta["families"]["free_value_news"] = {"tilt": round(vt, 4)}
        except Exception as e:
            meta["families"]["free_value_news"] = {"error": str(e)[:80]}

    if terms:
        if _b("BOOK_NORMALIZE_WEIGHTS", True):
            from analytics.vector_math import l1_weighted_sum

            raw = float(l1_weighted_sum([s for _, s in terms], [w for w, _ in terms]))
        else:
            raw = float(sum(w * s for w, s in terms))
    else:
        raw = 0.0
    if raw != raw:  # NaN guard
        raw = 0.0
    gain = _f("BOOK_BOOST_GAIN", 0.50)
    cap = _f("BOOK_BOOST_CAP", 0.28)
    w = _f("RANK_W_BOOK", 0.25)
    applied = float(np.clip(raw * gain, -cap, cap) * w)
    if applied != applied:
        applied = 0.0
    meta["raw"] = round(raw, 4)
    meta["applied"] = round(applied, 4)
    meta["parts"] = [round(w * s, 4) if (w == w and s == s) else 0.0 for w, s in terms]
    meta["normalized"] = _b("BOOK_NORMALIZE_WEIGHTS", True)
    meta["no_name_favoritism"] = True

    # Unique playbook tilt (math-first; env USE_UNIQUE_PLAYBOOK / RANK_W_UNIQUE)
    if _b("USE_UNIQUE_PLAYBOOK", True):
        try:
            from intel.unique_style_playbook import unique_rank_boost

            u_boost, u_meta = unique_rank_boost(sym)
            applied = float(applied) + float(u_boost or 0.0)
            meta["unique_playbook"] = u_meta
            meta["applied"] = round(applied, 4)
        except Exception as e:
            meta["unique_playbook"] = {"error": str(e)[:80]}

    _CACHE[sym] = (now, applied, meta)
    return applied, meta
