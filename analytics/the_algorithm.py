"""The Algorithm — one live decision surface over every trained head.

Heads stay on disk (daily RF/XGB, LSTM, intraday, ULE, cortex). This module
does not delete pickles or skip training. It fuses serve-time evidence:

  daily p_up  +  chart structure  +  value/small-cap  +  cross-company
  +  buy-fear-of-quality  +  cancel-fingerprint  +  cortex myelin tilt

Cost rule (active vs index): do not cancel→reissue the same ticket.
"""

from __future__ import annotations

import os
from typing import Any

from analytics.vector_math import apply_logit_tilt, delta_p_to_delta_ell


def _b(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _clip01(p: float) -> float:
    return float(max(0.01, min(0.99, p)))


def refine_live(
    symbol: str,
    p_up: float,
    *,
    row: Any | None = None,
    sent: float = 0.0,
    nf: float = 0.0,
) -> tuple[float, dict[str, Any]]:
    """Serve fuse after ULE. Returns (p_up, meta). skip_buy names go to 0.5."""
    meta: dict[str, Any] = {"algorithm": True, "symbol": str(symbol).upper()}
    p = _clip01(float(p_up))
    if not _b("USE_THE_ALGORITHM", True):
        return p, {**meta, "enabled": False}

    try:
        from analytics.order_fingerprint import recently_cancelled

        if recently_cancelled(symbol, side="buy"):
            meta["skip_buy"] = True
            meta["why"] = "recent_cancel_fingerprint"
            return 0.5, meta
    except Exception as e:
        meta["fingerprint_err"] = str(e)[:80]

    # Detailed OHLC graph — ATR channel, wicks, compression, volume trend.
    if row is not None:
        try:
            from analytics.chart_structure import chart_structure_score

            cs = float(chart_structure_score(row))
            meta["chart"] = cs
            w = _f("ALGO_CHART_W", 1.0)
            if abs(cs * w) > 1e-9:
                p = apply_logit_tilt(p, delta_p_to_delta_ell(p, cs * w))
        except Exception as e:
            meta["chart_err"] = str(e)[:80]

    try:
        from analytics.value_investing import value_investing_rank_boost

        v_boost, v_meta = value_investing_rank_boost(symbol)
        meta["value"] = float(v_boost)
        if v_meta:
            meta["value_deep"] = bool(v_meta.get("deep_value"))
            meta["value_small"] = bool(v_meta.get("small_cap") or v_meta.get("smallcap"))
        w = _f("ALGO_VALUE_W", 0.55)
        if abs(v_boost * w) > 1e-9:
            p = apply_logit_tilt(p, delta_p_to_delta_ell(p, float(v_boost) * w))
        # Buy fear in quality: sentiment dump + value/mosat still green.
        if float(sent) < _f("ALGO_FEAR_SENT", -0.25) and float(v_boost) > 0.0:
            fear = _f("ALGO_FEAR_TILT", 0.03)
            p = apply_logit_tilt(p, delta_p_to_delta_ell(p, fear))
            meta["fear_buy"] = True
    except Exception as e:
        meta["value_err"] = str(e)[:80]

    try:
        from analytics.cross_company_links import cross_company_rank_boost

        c_boost, _ = cross_company_rank_boost(symbol)
        meta["cross"] = float(c_boost)
        w = _f("ALGO_CROSS_W", 0.35)
        if abs(c_boost * w) > 1e-9:
            p = apply_logit_tilt(p, delta_p_to_delta_ell(p, float(c_boost) * w))
    except Exception as e:
        meta["cross_err"] = str(e)[:80]

    if abs(float(nf)) > 1e-6:
        meta["news_factor"] = float(nf)

    try:
        from cortex.integrate import cortex_rank_tilt

        rsi = 50.0
        if row is not None:
            try:
                rsi = float(row.get("rsi_14", 50) or 50)
            except Exception:
                rsi = 50.0
        tilt = float(cortex_rank_tilt(symbol, p, {"rsi_14": rsi}) or 0.0)
        meta["cortex_tilt"] = tilt
        if abs(tilt) > 1e-9:
            p = apply_logit_tilt(p, delta_p_to_delta_ell(p, tilt * _f("ALGO_CORTEX_W", 0.5)))
    except Exception:
        pass

    p = _clip01(p)
    meta["p_up"] = p
    return p, meta
