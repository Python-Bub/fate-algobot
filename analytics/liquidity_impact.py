"""Market impact / counterparty depth — large orders may not fill at mid."""

from __future__ import annotations

import os
import time
from typing import Any

import numpy as np
import pandas as pd

_ADV_CACHE: dict[str, tuple[float, float]] = {}


def _cache_ttl() -> int:
    return int(os.getenv("LIQUIDITY_ADV_CACHE_SEC", "1800"))


def _max_participation() -> float:
    return float(os.getenv("LIQUIDITY_MAX_PARTICIPATION", "0.05"))


def _min_adv_usd() -> float:
    return float(os.getenv("LIQUIDITY_MIN_ADV_USD", "500000"))


def estimate_adv_usd(
    ticker: str,
    price: float,
    *,
    volume_series: pd.Series | None = None,
    window: int = 20,
) -> float:
    """Average daily dollar volume over `window` sessions."""
    sym = ticker.strip().upper()
    px = max(float(price or 0), 0.01)
    now = time.time()
    cached = _ADV_CACHE.get(sym)
    if cached and now - cached[0] < _cache_ttl():
        return float(cached[1])

    adv = 0.0
    try:
        if volume_series is not None and len(volume_series) >= 5:
            vol = volume_series.astype(float).tail(window)
            adv = float((vol * px).mean())
        else:
            from feature_engineering import load_price_data

            end = pd.Timestamp.now("UTC").strftime("%Y-%m-%d")
            start = (pd.Timestamp.now("UTC") - pd.Timedelta(days=window + 15)).strftime("%Y-%m-%d")
            df = load_price_data(sym, start, end)
            if df is not None and not df.empty and "Volume" in df.columns:
                close_col = "Adj Close" if "Adj Close" in df.columns else "Close"
                closes = df[close_col].astype(float).tail(window)
                vols = df["Volume"].astype(float).tail(window)
                adv = float((closes * vols).mean())
    except Exception:
        adv = 0.0

    if adv <= 0:
        adv = _min_adv_usd()
    _ADV_CACHE[sym] = (now, adv)
    return adv


def assess_order_liquidity(
    ticker: str,
    notional_usd: float,
    price: float,
    *,
    side: str = "buy",
    volume_series: pd.Series | None = None,
) -> dict[str, Any]:
    """
    Cap notional when order would exceed safe participation of ADV.
    Estimates slippage when counterparty depth is thin.
    """
    sym = ticker.strip().upper()
    px = max(float(price or 0), 0.01)
    req = max(float(notional_usd or 0), 0.0)
    adv = estimate_adv_usd(sym, px, volume_series=volume_series)
    max_part = _max_participation()
    max_fill = adv * max_part
    participation = req / max(adv, 1.0)

    fillable = min(req, max_fill)
    unfilled = max(0.0, req - fillable)
    fill_ratio = fillable / req if req > 0 else 1.0

    # Square-root market impact (simplified Almgren-Chriss style)
    impact_bps = 0.0
    if participation > 0:
        impact_bps = float(
            np.sqrt(participation / max(max_part, 1e-6))
            * float(os.getenv("LIQUIDITY_IMPACT_BPS_SCALE", "35"))
        )
    if participation > max_part * 2:
        impact_bps *= 1.35

    block = False
    block_reason = None
    min_fill = float(os.getenv("LIQUIDITY_MIN_FILL_RATIO", "0.35"))
    if fill_ratio < min_fill and req >= float(os.getenv("ORDER_NOTIONAL", "500")):
        block = os.getenv("LIQUIDITY_BLOCK_THIN", "true").lower() in ("1", "true", "yes")
        block_reason = (
            f"Thin book: ${req:,.0f} order is {participation*100:.1f}% of ADV "
            f"(${adv:,.0f}) — only ~{fill_ratio*100:.0f}% likely fillable"
        )

    eff_notional = fillable
    if side.lower() in ("sell", "short"):
        eff_notional = fillable

    return {
        "ticker": sym,
        "requested_notional_usd": req,
        "effective_notional_usd": eff_notional,
        "adv_usd": adv,
        "participation_rate": participation,
        "max_participation": max_part,
        "fill_ratio": fill_ratio,
        "unfilled_notional_usd": unfilled,
        "estimated_slippage_bps": round(impact_bps, 2),
        "block_order": block,
        "block_reason": block_reason,
        "side": side,
    }


def cap_notional_for_liquidity(
    ticker: str,
    notional_usd: float,
    price: float,
    *,
    volume_series: pd.Series | None = None,
) -> tuple[float, dict[str, Any]]:
    """Return (capped_notional, liquidity_meta)."""
    if os.getenv("USE_LIQUIDITY_IMPACT", "true").lower() not in ("1", "true", "yes"):
        return float(notional_usd), {"enabled": False}
    liq = assess_order_liquidity(ticker, notional_usd, price, volume_series=volume_series)
    return float(liq.get("effective_notional_usd") or notional_usd), liq
