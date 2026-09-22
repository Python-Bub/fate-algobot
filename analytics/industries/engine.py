"""Live industry scoring engine — factors, news, co-movement for paper sim + features."""

from __future__ import annotations

import os
import time
from typing import Any

import numpy as np
import pandas as pd

_SNAP_CACHE: tuple[float, dict[str, float]] | None = None
_SNAP_TTL_SEC = int(os.getenv("INDUSTRY_FACTOR_SNAPSHOT_TTL_SEC", "900"))

from analytics.industries.base import IndustryContext
from analytics.industries.classifier import classify_ticker
from analytics.industries.registry import get_handler


def get_factor_snapshot(macro_bundle: dict[str, Any] | None = None) -> dict[str, float]:
    global _SNAP_CACHE
    now = time.time()
    if _SNAP_CACHE and now - _SNAP_CACHE[0] < _SNAP_TTL_SEC:
        snap = dict(_SNAP_CACHE[1])
        if macro_bundle:
            for k, v in macro_bundle.items():
                if k in snap and v is not None:
                    try:
                        snap[k] = float(v)
                    except (TypeError, ValueError):
                        pass
        return snap

    snap: dict[str, float] = {
        "spread_10y2y": 0.0,
        "dgs10": 0.0,
        "vix": 0.0,
        "macro_score": 0.0,
        "pmi_score": 0.0,
        "rate_shock_20d": 0.0,
        "nasdaq_ret_5d": 0.0,
    }
    try:
        from signals.fred_macro import get_macro_bundle

        bundle = macro_bundle or get_macro_bundle()
        for k in snap:
            if k in bundle and bundle[k] is not None:
                snap[k] = float(bundle[k])
    except Exception:
        pass
    if snap["nasdaq_ret_5d"] == 0.0:
        try:
            from analytics.industry_comovement import _load_closes_cached

            end = pd.Timestamp.now("UTC").strftime("%Y-%m-%d")
            start = (pd.Timestamp.now("UTC") - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
            q = _load_closes_cached(os.getenv("INDUSTRY_NASDAQ_PROXY", "QQQ"), start, end)
            if len(q) >= 6:
                snap["nasdaq_ret_5d"] = float(q.iloc[-1] / q.iloc[-6] - 1.0)
        except Exception:
            pass
    _SNAP_CACHE = (now, dict(snap))
    return snap


def build_context(
    symbol: str,
    *,
    macro_bundle: dict | None = None,
    news_headlines: list[str] | None = None,
    row_features: dict | None = None,
) -> IndustryContext:
    row = classify_ticker(symbol, use_cache=True, use_yfinance=False)
    macro = get_factor_snapshot(macro_bundle)
    return IndustryContext(
        symbol=symbol.strip().upper(),
        sector=str(row.get("sector") or ""),
        yahoo_industry=str(row.get("yahoo_industry") or ""),
        market_cap=float(row.get("market_cap") or 0.0),
        macro=macro,
        news_headlines=news_headlines or [],
        row_features=row_features or {},
    )


def industry_rank_adjustment(
    symbol: str,
    row: pd.Series | dict,
    *,
    macro_bundle: dict | None = None,
    news_headlines: list[str] | None = None,
) -> dict[str, Any]:
    sym = symbol.strip().upper()
    meta_row = classify_ticker(sym, use_cache=True, use_yfinance=False)
    iid = str(meta_row.get("industry_id") or "unclassified")
    handler = get_handler(iid)

    rf: dict[str, float] = {}
    if isinstance(row, dict):
        rf = {k: float(v) for k, v in row.items() if isinstance(v, (int, float))}
    else:
        rf = {k: float(row[k]) for k in row.index if isinstance(row.get(k), (int, float, np.floating))}

    ctx = build_context(sym, macro_bundle=macro_bundle, news_headlines=news_headlines, row_features=rf)
    factors = handler.compute_factor_tilts(ctx)
    industry_z = rf.get("industry_z_20", 0.0)
    residual = rf.get("industry_residual_1d", 0.0)
    comove = handler.compute_comovement(ctx, industry_z=industry_z, residual=residual)
    news_tilt = handler.news_factor_tilt(ctx)
    playbook_tilt = 0.0
    if news_headlines:
        try:
            from analytics.industries.macro_playbooks import playbook_tilt

            playbook_tilt = playbook_tilt(iid, news_headlines)
        except Exception:
            pass
    score_delta = handler.rank_score_delta(ctx, factors, comove, news_tilt)
    score_delta += float(os.getenv("RANK_W_INDUSTRY_PLAYBOOK", "0.08")) * playbook_tilt

    return {
        "industry_id": iid,
        "industry_name": meta_row.get("industry_name"),
        "etf_proxy": meta_row.get("etf_proxy"),
        "comovement_mode": meta_row.get("comovement_mode"),
        "score_delta": score_delta,
        "factor_tilts": {
            "rate": factors.rate_tilt,
            "expansion": factors.expansion_tilt,
            "nasdaq": factors.nasdaq_tilt,
            "defensive": factors.defensive_tilt,
            "commodity": factors.commodity_tilt,
            "news": factors.news_tilt,
            "combined": factors.combined,
        },
        "sympathy": {
            "sympathy_score": comove.sympathy_score,
            "leader_momentum": comove.leader_momentum,
            "short_sympathy": comove.short_sympathy,
        },
        "news": handler.score_news(news_headlines or []).__dict__ if news_headlines else {},
        "beta": rf.get("industry_beta_60", 1.0),
    }


def score_headlines_for_symbol(symbol: str, headlines: list[str]) -> dict[str, Any]:
    row = classify_ticker(symbol, use_cache=True, use_yfinance=False)
    handler = get_handler(str(row.get("industry_id")))
    ns = handler.score_news(headlines)
    return {
        "symbol": symbol.upper(),
        "industry_id": handler.INDUSTRY_ID,
        **ns.__dict__,
    }
