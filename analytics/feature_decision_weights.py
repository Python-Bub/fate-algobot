"""Per-column decision weights from information coefficient (IC).

Features that exist but never move (sentiment zeros) or have ~0 IC vs the
next-bar target get tiny weights so they cannot randomly dominate splits.
Columns are never deleted — weight → 0 is the idle state.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _spearman_ic(x: np.ndarray, y: np.ndarray) -> float:
    if x.size < 20:
        return 0.0
    # Rank via argsort twice; skip pandas for speed on hot train path.
    rx = np.argsort(np.argsort(x))
    ry = np.argsort(np.argsort(y))
    rx = rx.astype(float)
    ry = ry.astype(float)
    rx -= rx.mean()
    ry -= ry.mean()
    den = float(np.sqrt(np.dot(rx, rx) * np.dot(ry, ry)))
    if den < 1e-12:
        return 0.0
    return float(np.dot(rx, ry) / den)


def column_ic_weights(
    X: pd.DataFrame,
    y: pd.Series | np.ndarray,
    *,
    floor: float = 0.05,
) -> dict[str, float]:
    """|IC| mapped to (floor, 1]. Zero-variance columns get `floor` (kept, not dropped)."""
    yv = np.asarray(y, dtype=float).ravel()
    out: dict[str, float] = {}
    ics: list[float] = []
    cols = list(X.columns)
    for c in cols:
        xv = pd.to_numeric(X[c], errors="coerce").to_numpy(dtype=float)
        mask = np.isfinite(xv) & np.isfinite(yv)
        if mask.sum() < 20 or float(np.nanstd(xv[mask])) < 1e-12:
            out[str(c)] = float(floor)
            ics.append(0.0)
            continue
        ic = abs(_spearman_ic(xv[mask], yv[mask]))
        ics.append(ic)
        out[str(c)] = ic
    arr = np.asarray(ics, dtype=float)
    mx = float(arr.max()) if arr.size else 0.0
    if mx < 1e-9:
        return {c: 1.0 for c in out}
    for c in out:
        if out[c] <= float(floor) + 1e-15 and mx > 0:
            continue
        out[c] = float(max(floor, out[c] / mx))
    return out


def apply_column_weights(X: pd.DataFrame, weights: dict[str, float]) -> pd.DataFrame:
    out = X.copy()
    for c in out.columns:
        w = float(weights.get(str(c), 1.0))
        if abs(w - 1.0) > 1e-12:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0) * w
    return out


def row_weighted_score(row: dict[str, Any] | pd.Series, weights: dict[str, float]) -> float:
    """Live overlay: sum w_i * tanh(x_i) for columns present in both."""
    s = 0.0
    den = 0.0
    getter = row.get if isinstance(row, dict) else row.get
    for c, w in weights.items():
        ww = float(w)
        if ww <= 0:
            continue
        try:
            v = float(getter(c, 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(v):
            continue
        s += ww * float(np.tanh(v))
        den += ww
    if den <= 0:
        return 0.0
    return float(s / den)
