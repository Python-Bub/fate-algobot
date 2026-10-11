"""Short-horizon model probability on the holdout tail only.

The bundles were fit on the earlier rows. Those rows are not traded here.
A date is kept when its probability is at least the fit-period bar. The
holdout that beat the old 1.2% five-day baseline used the 95th percentile.
"""

from __future__ import annotations

import os
from pathlib import Path


def fit_percentile() -> float:
    """Confidence bar. The confirm half kept 95 and dropped 70, 80, 90, and 0.62."""
    return float(os.getenv("FATE_FIT_BAR_PERCENTILE", "95"))


def _fit_cut(n: int, holdout_frac: float = 0.2) -> int | None:
    if n < 80:
        return None
    cut = int(n * (1.0 - holdout_frac))
    return min(max(cut, 40), n - 15)


def fit_probability_bar(
    probs: list[float],
    *,
    holdout_frac: float = 0.2,
    percentile: float | None = None,
) -> float | None:
    """Percentile of fit-period probabilities. Later rows do not move the bar."""
    cut = _fit_cut(len(probs), holdout_frac)
    if cut is None:
        return None
    import numpy as np

    pct = fit_percentile() if percentile is None else float(percentile)
    return float(np.percentile(np.asarray(probs[:cut], dtype=float), pct))


def confident_tail(
    probs: list[float],
    dates: list[str],
    *,
    holdout_frac: float = 0.2,
    percentile: float | None = None,
) -> dict[str, float]:
    """Map holdout dates to P(up). Fit-period dates are left out."""
    n = len(probs)
    cut = _fit_cut(n, holdout_frac)
    if n != len(dates) or cut is None:
        return {}
    thr = fit_probability_bar(probs, holdout_frac=holdout_frac, percentile=percentile)
    if thr is None:
        return {}
    out: dict[str, float] = {}
    for i in range(cut, n):
        p = float(probs[i])
        if p >= thr:
            out[dates[i]] = p
    return out


def _batch_p_up(model, frame, feats: list[str]) -> list[float] | None:
    import pandas as pd

    from ml_model import _align_x_to_model, _sanitize_X

    if model is None or frame is None or frame.empty:
        return None
    x = frame.reindex(columns=list(feats)).astype(float).fillna(0.0)
    x = _sanitize_X(x)
    x = _align_x_to_model(model, x)
    try:
        proba = model.predict_proba(x)
    except Exception:
        return None
    classes = list(getattr(model, "classes_", []))
    if 1 in classes:
        col = proba[:, classes.index(1)]
    elif 0 in classes:
        col = 1.0 - proba[:, classes.index(0)]
    else:
        return None
    return [float(v) for v in col]


def holdout_confident_p(symbol: str, model_path: Path, price_path: Path | None = None) -> dict[str, float]:
    """P(up) from the 5-day head, confident holdout dates only."""
    if not model_path.is_file():
        return {}
    if price_path is not None and price_path.is_file():
        try:
            import pyarrow.parquet as pq

            cols = set(pq.ParquetFile(price_path).schema.names)
        except Exception:
            cols = set()
        if "High" not in cols or "Volume" not in cols:
            return {}
    os.environ["USE_HISTORICAL_EVENTS"] = "false"
    from feature_engineering import build_features
    from ml_model import load_raw_bundle

    try:
        raw = load_raw_bundle(str(model_path))
    except Exception:
        return {}
    model = raw.get("model_short") or raw.get("model")
    feats = list(raw.get("features") or [])
    if model is None or not feats:
        return {}
    try:
        feat = build_features(symbol, "2008-01-01", None)
    except Exception:
        return {}
    if feat is None or feat.empty or "Adj Close" not in feat.columns:
        return {}
    probs = _batch_p_up(model, feat, feats)
    if not probs:
        return {}
    dates = [str(x)[:10] for x in feat.index]
    return confident_tail(probs, dates, percentile=fit_percentile())


def short_head_bar(model_path: Path, frame, *, at=None, percentile: float | None = None) -> tuple[float | None, float | None]:
    """Latest 5-day probability and the fit-period bar, from a frame already in memory.

    The bar is the percentile of predictions on the earlier rows. The row at
    ``at`` (or the last row) is the live probability and is not part of the bar.
    """
    if frame is None or getattr(frame, "empty", True):
        return None, None
    if not Path(model_path).is_file():
        return None, None
    from ml_model import load_raw_bundle

    try:
        raw = load_raw_bundle(str(model_path))
    except Exception:
        return None, None
    model = raw.get("model_short") or raw.get("model")
    feats = list(raw.get("features") or [])
    if model is None or not feats:
        return None, None
    probs = _batch_p_up(model, frame, feats)
    if not probs:
        return None, None
    bar = fit_probability_bar(probs, percentile=percentile)
    idx = len(probs) - 1
    if at is not None:
        try:
            loc = frame.index.get_loc(at)
        except Exception:
            loc = None
        if isinstance(loc, slice):
            idx = max(0, (loc.stop or 1) - 1)
        elif isinstance(loc, int):
            idx = loc
    if idx < 0 or idx >= len(probs):
        return None, bar
    return float(probs[idx]), bar
