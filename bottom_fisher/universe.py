"""Build the bottom-percentile candidate universe from trained daily models."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from bottom_fisher.config import BottomFisherConfig
from fortress_universe import is_tradeable_equity, symbols_with_daily_models
from model_trainer import training_saved_model
from utils import log


@dataclass
class BottomCandidate:
    ticker: str
    ret_60d: float
    ret_20d: float
    ret_5d: float
    ret_1d: float
    drawdown_52w: float
    last_close: float
    avg_dollar_vol: float
    bottom_rank_pct: float


def _model_symbols(cfg: BottomFisherConfig) -> list[str]:
    min_pool = int(os.getenv("BOTTOM_FISHER_MIN_POOL", "80"))
    pool: list[str] = []
    if cfg.require_model:
        pool = [s for s in symbols_with_daily_models() if training_saved_model(s)]
    else:
        model_dir = Path(os.getenv("MODEL_DIR", "models"))
        pool = sorted(
            {
                p.name[: -len("_model.pkl")].upper()
                for p in model_dir.glob("*_model.pkl")
                if p.stat().st_size > 1000
            }
        )
    pool = [s for s in pool if is_tradeable_equity(s)]
    if len(pool) < min_pool:
        try:
            from fortress_universe import symbols_paper_active_universe

            extra = [s for s in symbols_paper_active_universe() if is_tradeable_equity(s)]
            seen = set(pool)
            for s in extra:
                if s not in seen:
                    pool.append(s)
                    seen.add(s)
        except Exception as e:
            log.debug("[BOTTOM_FISHER] universe fallback: %s", e)
    return pool


def frame_for_symbol(raw: pd.DataFrame, symbol: str) -> pd.DataFrame | None:
    """Pull one ticker out of a single- or MultiIndex Yahoo/Polygon frame."""
    if raw is None or getattr(raw, "empty", True):
        return None
    sym = str(symbol).upper()
    if not isinstance(raw.columns, pd.MultiIndex):
        return raw
    for level in range(raw.columns.nlevels):
        try:
            vals = {str(v).upper() for v in raw.columns.get_level_values(level)}
        except Exception:
            continue
        if sym not in vals:
            continue
        try:
            sub = raw.xs(symbol, axis=1, level=level)
        except Exception:
            try:
                sub = raw.xs(sym, axis=1, level=level)
            except Exception:
                continue
        if sub is None or getattr(sub, "empty", True):
            continue
        if isinstance(sub, pd.Series):
            continue
        return sub
    return None


def load_bottom_universe(cfg: BottomFisherConfig | None = None) -> list[BottomCandidate]:
    """Bottom percentile by distress math (not raw 60d return). Knives are dropped."""
    cfg = cfg or BottomFisherConfig.from_env()
    syms = _model_symbols(cfg)
    if not syms:
        return []

    lookback = int(os.getenv("BOTTOM_FISHER_MOM_LOOKBACK", "90"))
    batch = int(os.getenv("BOTTOM_FISHER_YF_BATCH", "80"))
    rows: list[BottomCandidate] = []

    for i in range(0, len(syms), batch):
        chunk = syms[i : i + batch]
        try:
            from data_platform.market_prices import download

            raw = download(
                chunk,
                period=f"{lookback}d",
                interval="1d",
            )
        except Exception as e:
            log.debug("[BOTTOM_FISHER] yf batch skip: %s", e)
            continue
        if raw is None or raw.empty:
            continue

        if isinstance(raw.columns, pd.MultiIndex):
            for t in chunk:
                sub = frame_for_symbol(raw, t)
                if sub is None:
                    continue
                cand = _row_from_ohlc(t, sub, cfg)
                if cand:
                    rows.append(cand)
        else:
            label = chunk[0] if len(chunk) == 1 else None
            if label:
                cand = _row_from_ohlc(label, raw, cfg)
                if cand:
                    rows.append(cand)

    if not rows:
        return []

    rows.sort(key=lambda r: -r.avg_dollar_vol)
    n = len(rows)
    cut = max(1, int(n * cfg.bottom_percentile))
    # Rank by 60d (more negative first) then keep the worst slice *after* knife filter.
    from analytics.trade_math import distress_score, falling_knife

    scored: list[tuple[float, BottomCandidate]] = []
    for r in rows:
        if falling_knife(r.ret_1d, r.ret_5d, r.ret_20d):
            continue
        ds = distress_score(
            ret_60d=r.ret_60d,
            ret_20d=r.ret_20d,
            ret_5d=r.ret_5d,
            ret_1d=r.ret_1d,
            drawdown_52w=r.drawdown_52w,
            dollar_vol=r.avg_dollar_vol,
            min_dollar_vol=cfg.min_daily_volume_usd,
        )
        if ds <= 0:
            continue
        scored.append((ds, r))
    if not scored:
        # Still return a slice so the scanner is never empty — worst 60d among liquid names.
        liquid = [r for r in rows if r.avg_dollar_vol >= cfg.min_daily_volume_usd]
        liquid.sort(key=lambda r: r.ret_60d)
        scored = [(0.05, r) for r in liquid[:cut]]

    scored.sort(key=lambda x: -x[0])
    bottom = [r for _, r in scored[: max(cut, 1)]]
    for i, r in enumerate(bottom):
        r.bottom_rank_pct = i / max(1, len(bottom) - 1)
    bottom = bottom[: cfg.max_scan_symbols]
    log.info(
        "[BOTTOM_FISHER] universe pool=%d distress_keep=%d scanning=%d worst_60d=%.1f%%",
        n,
        len(scored),
        len(bottom),
        100 * min((x.ret_60d for x in bottom), default=0.0),
    )
    return bottom


def _row_from_ohlc(ticker: str, df: pd.DataFrame, cfg: BottomFisherConfig) -> BottomCandidate | None:
    if df is None or len(df) < 25:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    close_name = "Close" if "Close" in df.columns else ("Adj Close" if "Adj Close" in df.columns else None)
    if close_name is None:
        return None
    close = df[close_name].astype(float)
    vol = df["Volume"].astype(float) if "Volume" in df.columns else pd.Series(0.0, index=df.index)
    last = float(close.iloc[-1])
    if last < cfg.min_price_usd or last > cfg.max_price_usd:
        return None
    dv = float((close * vol).tail(20).mean())
    if dv < cfg.min_daily_volume_usd:
        return None

    c60 = float(close.iloc[-1] / close.iloc[max(0, len(close) - 61)] - 1.0) if len(close) > 61 else 0.0
    c20 = float(close.iloc[-1] / close.iloc[max(0, len(close) - 21)] - 1.0) if len(close) > 21 else 0.0
    c5 = float(close.iloc[-1] / close.iloc[max(0, len(close) - 6)] - 1.0) if len(close) > 6 else 0.0
    c1 = float(close.iloc[-1] / close.iloc[-2] - 1.0) if len(close) > 2 else 0.0
    hi52 = float(close.tail(min(252, len(close))).max())
    dd = float(last / hi52 - 1.0) if hi52 > 0 else 0.0

    return BottomCandidate(
        ticker=str(ticker).upper(),
        ret_60d=c60,
        ret_20d=c20,
        ret_5d=c5,
        ret_1d=c1,
        drawdown_52w=dd,
        last_close=last,
        avg_dollar_vol=dv,
        bottom_rank_pct=0.0,
    )
