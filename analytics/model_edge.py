"""Short-horizon model probability on the holdout tail only.

The bundles were fit on the earlier rows. Those rows are not traded here.
A date is kept when its probability is at least the 80th percentile of the
fit period. That is the model's own confident band, not a target return.
"""

from __future__ import annotations

import os
from pathlib import Path


def confident_tail(
    probs: list[float],
    dates: list[str],
    *,
    holdout_frac: float = 0.2,
    percentile: float = 80.0,
) -> dict[str, float]:
    """Map holdout dates to P(up). Fit-period dates are left out."""
    n = len(probs)
    if n != len(dates) or n < 80:
        return {}
    cut = int(n * (1.0 - holdout_frac))
    cut = min(max(cut, 40), n - 15)
    import numpy as np

    thr = float(np.percentile(np.asarray(probs[:cut], dtype=float), percentile))
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
    return confident_tail(probs, dates)
