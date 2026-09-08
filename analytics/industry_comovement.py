"""Industry co-movement engine — basket beta, factor rotation, leader sympathy."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analytics.industry_taxonomy import (
    DEFAULT_INDUSTRY,
    EXPANSION_CYCLICAL,
    NASDAQ_HEAVY,
    RATE_SENSITIVE,
    classify_symbol,
    industry_etf,
    load_catalog,
    load_industry_map,
)
from utils import log

ROOT = Path(__file__).resolve().parents[1]
PANEL_CACHE = ROOT / "data" / "cache" / "industry_panel.json"
LEADER_CACHE = ROOT / "data" / "cache" / "industry_leaders.json"
NASDAQ_PROXY = os.getenv("INDUSTRY_NASDAQ_PROXY", "QQQ")
PMI_PROXY = os.getenv("INDUSTRY_PMI_PROXY", "MANEMP")

INDUSTRY_FEATURE_COLUMNS = (
    "industry_ret_1d",
    "industry_ret_5d",
    "industry_beta_60",
    "industry_residual_1d",
    "industry_z_20",
    "nasdaq_beta_60",
    "factor_rate_tilt",
    "factor_expansion_tilt",
    "industry_sympathy_score",
    "industry_leader_momentum",
)


def _b(name: str, default: bool = True) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes")


_CLOSE_CACHE: dict[str, tuple[float, pd.Series]] = {}


def _load_closes(ticker: str, start: str, end: str | None) -> pd.Series:
    return _load_closes_cached(ticker, start, end)


def _load_closes_cached(ticker: str, start: str, end: str | None) -> pd.Series:
    sym = ticker.strip().upper()
    ttl = int(os.getenv("INDUSTRY_CLOSE_CACHE_SEC", "3600"))
    now = time.time()
    cached = _CLOSE_CACHE.get(sym)
    if cached and now - cached[0] < ttl:
        s = cached[1]
        if start or end:
            lo = pd.Timestamp(start) if start else s.index.min()
            hi = pd.Timestamp(end) if end else s.index.max()
            return s.loc[(s.index >= lo) & (s.index <= hi)].sort_index()
        return s.sort_index()

    from feature_engineering import load_price_data

    df = load_price_data(sym, start, end)
    if df is None or df.empty:
        return pd.Series(dtype=float)
    col = "Adj Close" if "Adj Close" in df.columns else "Close"
    s = df[col].astype(float)
    idx = pd.DatetimeIndex(pd.to_datetime(s.index, errors="coerce"))
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    s.index = idx
    s = s.sort_index()
    _CLOSE_CACHE[sym] = (now, s)
    return s


def _returns(closes: pd.Series) -> pd.Series:
    return closes.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _rolling_beta(asset: pd.Series, bench: pd.Series, window: int = 60) -> pd.Series:
    aligned = pd.concat([asset, bench], axis=1, join="inner").dropna()
    if len(aligned) < max(20, window // 2):
        return pd.Series(0.0, index=asset.index)
    a = aligned.iloc[:, 0]
    b = aligned.iloc[:, 1]
    cov = a.rolling(window, min_periods=max(15, window // 3)).cov(b)
    var = b.rolling(window, min_periods=max(15, window // 3)).var()
    beta = (cov / (var + 1e-12)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return beta.reindex(asset.index).fillna(0.0)


def _rolling_corr(a: pd.Series, b: pd.Series, window: int = 30) -> pd.Series:
    aligned = pd.concat([a, b], axis=1, join="inner").dropna()
    if aligned.empty:
        return pd.Series(0.0, index=a.index)
    out = aligned.iloc[:, 0].rolling(window, min_periods=max(10, window // 3)).corr(aligned.iloc[:, 1])
    return out.reindex(a.index).fillna(0.0)


def get_factor_snapshot(macro_bundle: dict[str, Any] | None = None) -> dict[str, float]:
    """Macro factors for rotation: rates, expansion (PMI proxy), Nasdaq."""
    snap: dict[str, float] = {
        "spread_10y2y": 0.0,
        "dgs10": 0.0,
        "vix": 0.0,
        "macro_score": 0.0,
        "pmi_score": 0.0,
        "nasdaq_ret_5d": 0.0,
        "rate_shock": 0.0,
    }
    try:
        from signals.fred_macro import get_macro_bundle

        bundle = macro_bundle or get_macro_bundle()
        snap["spread_10y2y"] = float(bundle.get("spread_10y2y") or 0.0)
        snap["dgs10"] = float(bundle.get("dgs10") or 0.0)
        snap["vix"] = float(bundle.get("vix") or 0.0)
        snap["macro_score"] = float(bundle.get("macro_score") or 0.0)
        snap["pmi_score"] = float(bundle.get("pmi_score") or 0.0)
        snap["rate_shock"] = float(bundle.get("rate_shock_20d") or 0.0)
    except Exception:
        pass
    if snap["nasdaq_ret_5d"] == 0.0:
        try:
            end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            start = (datetime.now(timezone.utc).date() - pd.Timedelta(days=30)).isoformat()
            q = _load_closes(NASDAQ_PROXY, start, end)
            if len(q) >= 6:
                snap["nasdaq_ret_5d"] = float(q.iloc[-1] / q.iloc[-6] - 1.0)
        except Exception:
            pass
    return snap


def factor_tilts(industry_id: str, factors: dict[str, float] | None = None) -> dict[str, float]:
    """Industry-specific macro tilts from rate / PMI / Nasdaq factors."""
    factors = factors or get_factor_snapshot()
    meta = load_catalog().get(industry_id) or load_catalog()[DEFAULT_INDUSTRY]
    rate_s = float(meta.get("rate_sensitivity") or 0.0)
    exp_b = float(meta.get("expansion_beta") or 0.5)
    ndx_b = float(meta.get("nasdaq_beta") or 1.0)

    spread = float(factors.get("spread_10y2y") or 0.0)
    rate_shock = float(factors.get("rate_shock_20d") or factors.get("rate_shock") or 0.0)
    pmi = float(factors.get("pmi_score") or 0.0)
    ndx5 = float(factors.get("nasdaq_ret_5d") or 0.0)

    # Steeper curve helps rate-sensitive names; rising yields (rate_shock) hurt REITs/utilities
    rate_tilt = rate_s * float(np.tanh(spread * 0.4 + rate_shock * 2.5))
    expansion_tilt = exp_b * pmi if industry_id in EXPANSION_CYCLICAL else exp_b * pmi * 0.35
    nasdaq_tilt = ndx_b * float(np.tanh(ndx5 * 8.0)) if industry_id in NASDAQ_HEAVY else ndx_b * ndx5 * 0.25

    return {
        "factor_rate_tilt": float(rate_tilt),
        "factor_expansion_tilt": float(expansion_tilt),
        "factor_nasdaq_tilt": float(nasdaq_tilt),
        "combined_factor_tilt": float(rate_tilt + expansion_tilt * 0.5 + nasdaq_tilt * 0.35),
    }


def enrich_industry_comovement(
    df: pd.DataFrame,
    ticker: str,
    start_date: str,
    end_date: str | None,
    *,
    macro_bundle: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Add causal industry co-movement columns to a price feature frame."""
    if not _b("USE_INDUSTRY_COMOVEMENT", True):
        out = df.copy()
        for c in INDUSTRY_FEATURE_COLUMNS:
            if c not in out.columns:
                out[c] = 0.0
        return out

    sym = ticker.strip().upper()
    meta = classify_symbol(sym, use_yfinance=False)
    iid = str(meta.get("industry_id") or DEFAULT_INDUSTRY)
    etf = str(meta.get("etf_proxy") or industry_etf(sym))

    out = df.copy()
    idx = pd.DatetimeIndex(pd.to_datetime(out.index, errors="coerce"))
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    out.index = idx

    stock_col = "Adj Close" if "Adj Close" in out.columns else "Close"
    if stock_col not in out.columns:
        for c in INDUSTRY_FEATURE_COLUMNS:
            out[c] = 0.0
        return out

    stock_ret = out[stock_col].astype(float).pct_change().fillna(0.0)
    end_s = end_date or (str(out.index[-1].date()) if len(out) else start_date)

    ind_ret = pd.Series(0.0, index=out.index)
    ndx_ret = pd.Series(0.0, index=out.index)
    try:
        ind_close = _load_closes(etf, start_date, end_s)
        if not ind_close.empty:
            ind_ret = _returns(ind_close).reindex(out.index).fillna(0.0)
        ndx_close = _load_closes(NASDAQ_PROXY, start_date, end_s)
        if not ndx_close.empty:
            ndx_ret = _returns(ndx_close).reindex(out.index).fillna(0.0)
    except Exception as e:
        log.debug("[INDUSTRY] proxy load failed %s: %s", sym, e)

    beta60 = _rolling_beta(stock_ret, ind_ret, window=60)
    ndx_beta60 = _rolling_beta(stock_ret, ndx_ret, window=60)
    residual = stock_ret - beta60 * ind_ret
    ind_cum = ind_ret.rolling(20, min_periods=5).sum()
    ind_mu = ind_cum.rolling(60, min_periods=20).mean()
    ind_sd = ind_cum.rolling(60, min_periods=20).std().replace(0, np.nan)
    ind_z = ((ind_cum - ind_mu) / (ind_sd + 1e-12)).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    factors = get_factor_snapshot(macro_bundle)
    tilts = factor_tilts(iid, factors)
    const_rate = tilts["factor_rate_tilt"]
    const_exp = tilts["factor_expansion_tilt"]

    out["industry_ret_1d"] = ind_ret.astype(np.float64)
    out["industry_ret_5d"] = ind_ret.rolling(5, min_periods=1).sum().astype(np.float64)
    out["industry_beta_60"] = beta60.astype(np.float64)
    out["industry_residual_1d"] = residual.astype(np.float64)
    out["industry_z_20"] = ind_z.astype(np.float64)
    out["nasdaq_beta_60"] = ndx_beta60.astype(np.float64)
    out["factor_rate_tilt"] = const_rate
    out["factor_expansion_tilt"] = const_exp
    out["industry_sympathy_score"] = 0.0
    out["industry_leader_momentum"] = 0.0
    return out


def _leaders_for_industry(industry_id: str, limit: int = 3) -> list[str]:
    cached = {}
    if LEADER_CACHE.is_file():
        try:
            cached = json.loads(LEADER_CACHE.read_text(encoding="utf-8")).get("by_industry") or {}
        except Exception:
            cached = {}
    if industry_id in cached:
        return list(cached[industry_id])[:limit]

    imap = load_industry_map()
    peers = [s for s, row in imap.items() if row.get("industry_id") == industry_id]
    if len(peers) < limit:
        return peers[:limit]
    scored = sorted(peers, key=lambda s: float(imap[s].get("market_cap") or 0.0), reverse=True)
    return scored[:limit]


def compute_leader_sympathy(
    symbol: str,
    *,
    as_of: str | None = None,
    macro_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """If top industry leaders moved sharply, estimate sympathy pull on laggards."""
    sym = symbol.strip().upper()
    meta = classify_symbol(sym, use_yfinance=False)
    iid = str(meta.get("industry_id") or DEFAULT_INDUSTRY)
    leaders = [l for l in _leaders_for_industry(iid) if l != sym][:3]
    if not leaders:
        return {"sympathy_score": 0.0, "leader_momentum": 0.0, "leaders": [], "industry_id": iid}

    end = as_of or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (pd.Timestamp(end) - pd.Timedelta(days=12)).strftime("%Y-%m-%d")
    moves: list[float] = []
    vols: list[float] = []
    for leader in leaders:
        try:
            c = _load_closes(leader, start, end)
            if len(c) < 3:
                continue
            r1 = float(c.iloc[-1] / c.iloc[-2] - 1.0)
            r3 = float(c.iloc[-1] / c.iloc[-4] - 1.0) if len(c) >= 4 else r1
            moves.append(0.6 * r1 + 0.4 * r3)
            vols.append(float(_returns(c).tail(10).std() or 0.01))
        except Exception:
            continue

    if not moves:
        return {"sympathy_score": 0.0, "leader_momentum": 0.0, "leaders": leaders, "industry_id": iid}

    avg_move = float(np.mean(moves))
    avg_vol = float(np.mean(vols) or 0.01)
    z = avg_move / (avg_vol + 1e-6)
    prior = float(meta.get("intra_corr_prior") or 0.75)
    sympathy = float(np.tanh(z * 1.2) * prior)

    factors = get_factor_snapshot(macro_bundle)
    tilts = factor_tilts(iid, factors)

    return {
        "sympathy_score": sympathy,
        "leader_momentum": avg_move,
        "leader_z": z,
        "leaders": leaders,
        "industry_id": iid,
        "factor_tilt": tilts.get("combined_factor_tilt", 0.0),
        "nasdaq_heavy": iid in NASDAQ_HEAVY,
        "rate_sensitive": iid in RATE_SENSITIVE,
    }


def industry_rank_adjustment(
    symbol: str,
    row: pd.Series | dict,
    *,
    macro_bundle: dict[str, Any] | None = None,
    news_headlines: list[str] | None = None,
) -> dict[str, Any]:
    use_blend = os.getenv("USE_INDUSTRY_AI_BLEND", "true").lower() in ("1", "true", "yes")
    if use_blend:
        try:
            from analytics.industries.integration import blended_rank_adjustment

            rf: dict = {}
            if isinstance(row, dict):
                rf = {k: float(v) for k, v in row.items() if isinstance(v, (int, float))}
            else:
                import numpy as np

                rf = {
                    k: float(row[k])
                    for k in row.index
                    if isinstance(row.get(k), (int, float, np.floating))
                }
            return blended_rank_adjustment(
                symbol,
                rf,
                macro_bundle=macro_bundle,
                news_headlines=news_headlines,
            )
        except Exception:
            pass
    try:
        from analytics.industries.engine import industry_rank_adjustment as _new

        return _new(symbol, row, macro_bundle=macro_bundle, news_headlines=news_headlines)
    except Exception:
        pass
    sym = symbol.strip().upper()
    meta = classify_symbol(sym, use_yfinance=False)
    sympathy = compute_leader_sympathy(sym, macro_bundle=macro_bundle)
    factors = get_factor_snapshot(macro_bundle)
    tilts = factor_tilts(str(meta.get("industry_id")), factors)

    def _f(key: str, default: float = 0.0) -> float:
        if isinstance(row, dict):
            return float(row.get(key, default) or default)
        return float(row.get(key, default) if key in row.index else default)

    residual = _f("industry_residual_1d")
    ind_z = _f("industry_z_20")
    beta = _f("industry_beta_60", 1.0)

    # Mean-reversion on stretched industry z; sympathy follows leaders
    reversion = -0.15 * float(np.tanh(ind_z * 0.8))
    sympathy_boost = float(sympathy.get("sympathy_score") or 0.0)
    factor_boost = float(tilts.get("combined_factor_tilt") or 0.0)
    nasdaq_align = 0.0
    if meta.get("nasdaq_heavy"):
        nasdaq_align = float(np.tanh(float(factors.get("nasdaq_ret_5d") or 0.0) * 6.0)) * 0.12

    score_delta = (
        float(os.getenv("RANK_W_INDUSTRY_SYMPATHY", "0.14")) * sympathy_boost
        + float(os.getenv("RANK_W_INDUSTRY_FACTOR", "0.10")) * factor_boost
        + float(os.getenv("RANK_W_INDUSTRY_REVERSION", "0.06")) * reversion
        + float(os.getenv("RANK_W_NASDAQ_ALIGN", "0.08")) * nasdaq_align
        + float(os.getenv("RANK_W_INDUSTRY_RESIDUAL", "0.05")) * float(np.tanh(-residual * 20.0))
    )

    short_signal = False
    leader_z = float(sympathy.get("leader_z") or 0.0)
    if leader_z <= -2.0 and beta > 0.8 and sympathy_boost < -0.2:
        short_signal = True

    return {
        "industry_id": meta.get("industry_id"),
        "industry_name": meta.get("name"),
        "etf_proxy": meta.get("etf_proxy"),
        "score_delta": score_delta,
        "sympathy": sympathy,
        "factor_tilts": tilts,
        "industry_short_sympathy": short_signal,
        "beta": beta,
    }


def rolling_intra_industry_correlation(
    symbols: list[str],
    start: str,
    end: str | None,
    *,
    window: int = 30,
) -> float:
    """Pearson avg pairwise correlation for a symbol list (co-movement check)."""
    rets: list[pd.Series] = []
    for sym in symbols[:12]:
        try:
            c = _load_closes(sym, start, end)
            if len(c) < window + 5:
                continue
            rets.append(_returns(c).tail(window + 10))
        except Exception:
            continue
    if len(rets) < 2:
        return 0.0
    panel = pd.concat(rets, axis=1, join="inner").dropna()
    if panel.shape[0] < window or panel.shape[1] < 2:
        return 0.0
    corr = panel.tail(window).corr()
    vals = []
    n = corr.shape[0]
    for i in range(n):
        for j in range(i + 1, n):
            v = corr.iloc[i, j]
            if pd.notna(v):
                vals.append(float(v))
    return float(np.mean(vals)) if vals else 0.0
