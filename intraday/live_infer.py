"""Serve trained intraday pickles at trade time (additive to the daily head).

~8k `models/intraday/*_intraday.pkl` files were coverage-only until this module.
Placeholders (p=0.5) are skipped. Failures leave the daily p_up unchanged.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

from utils import log

_CACHE: dict[str, tuple[float, float | None]] = {}


def _enabled() -> bool:
    if os.getenv("USE_INTRADAY_LIVE_BLEND", "true").lower() not in ("1", "true", "yes", "on"):
        return False
    if os.getenv("FORTRESS_LITE_INTEL", "false").lower() in ("1", "true", "yes"):
        return False
    # Paper-sim lite scans hundreds of names; opt in with INTRADAY_LIVE_IN_PAPER_SIM.
    if os.getenv("PAPER_SIM_ACTIVE_RUN", "").lower() in ("1", "true", "yes"):
        if os.getenv("PAPER_SIM_LITE_INTEL", "true").lower() in ("1", "true", "yes"):
            if os.getenv("INTRADAY_LIVE_IN_PAPER_SIM", "false").lower() not in (
                "1",
                "true",
                "yes",
            ):
                return False
    return True


def _ttl() -> float:
    return float(os.getenv("INTRADAY_LIVE_CACHE_SEC", "300"))


def live_intraday_p_up(ticker: str) -> float | None:
    """Return minutely-head p_up or None when missing/placeholder/error."""
    if not _enabled():
        return None
    sym = ticker.strip().upper()
    if not sym:
        return None
    now = time.time()
    hit = _CACHE.get(sym)
    if hit and now - hit[0] < _ttl():
        return hit[1]
    p_up = _compute(sym)
    _CACHE[sym] = (now, p_up)
    return p_up


def _compute(sym: str) -> float | None:
    try:
        from fortress_universe import has_trained_intraday_bundle

        if not has_trained_intraday_bundle(sym):
            return None
    except Exception:
        from pathlib import Path

        p = Path(os.getenv("INTRADAY_MODEL_DIR", "models/intraday")) / f"{sym}_intraday.pkl"
        if not p.is_file() or p.stat().st_size < int(os.getenv("INTRADAY_TRAINED_MIN_BYTES", "12000")):
            return None
    try:
        from intraday.data_loader_intraday import fetch_minute_bars
        from intraday.feature_engineering_intraday import build_intraday_features
        from intraday.intraday_trainer import predict_intraday
    except Exception as e:
        log.debug("[INTRADAY_LIVE] import failed %s: %s", sym, e)
        return None

    lookback = int(os.getenv("INTRADAY_LIVE_LOOKBACK_DAYS", "5"))
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=lookback)).strftime("%Y-%m-%d")
    old_min = os.environ.get("INTRADAY_MIN_BARS")
    try:
        os.environ["INTRADAY_MIN_BARS"] = os.getenv("INTRADAY_LIVE_MIN_BARS", "80")
        bars = fetch_minute_bars(sym, start, end)
    except Exception as e:
        log.debug("[INTRADAY_LIVE] bars %s: %s", sym, e)
        return None
    finally:
        if old_min is None:
            os.environ.pop("INTRADAY_MIN_BARS", None)
        else:
            os.environ["INTRADAY_MIN_BARS"] = old_min
    need = int(os.getenv("INTRADAY_LIVE_MIN_BARS", "80"))
    if bars is None or getattr(bars, "empty", True) or len(bars) < need:
        return None
    try:
        feat = build_intraday_features(bars)
        if feat is None or feat.empty:
            return None
        row = feat.iloc[-1]
        det = predict_intraday(sym, row, horizon="minutely")
        if det.get("missing") or det.get("placeholder"):
            return None
        p = float(det.get("p_up", 0.5))
        if p != p:  # NaN
            return None
        return max(0.01, min(0.99, p))
    except Exception as e:
        log.debug("[INTRADAY_LIVE] predict %s: %s", sym, e)
        return None


def blend_intraday_p(p_daily: float, p_intra: float | None) -> tuple[float, float]:
    """Small additive mix. Returns (p_blended, weight_used)."""
    if p_intra is None:
        return float(p_daily), 0.0
    w = float(os.getenv("INTRADAY_LIVE_BLEND_W", "0.12"))
    w = max(0.0, min(0.35, w))
    base = float(max(0.0, min(1.0, p_daily)))
    intra = float(max(0.0, min(1.0, p_intra)))
    if abs(intra - base) > float(os.getenv("INTRADAY_DISAGREE_DAMPEN", "0.28")):
        w *= float(os.getenv("INTRADAY_DISAGREE_MULT", "0.40"))
    if (intra - 0.5) * (base - 0.5) < 0:
        w *= float(os.getenv("INTRADAY_OPPOSE_MULT", "0.25"))
    out = (1.0 - w) * base + w * intra
    return float(out), float(w)
