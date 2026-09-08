"""Residual (idiosyncratic) momentum — Blitz, Huij, Martens 2011.

12-1 month stock return minus the market's 12-1 return (beta=1).
Skip the most recent month so the last-month reversal does not contaminate.
Works well as a *second* momentum expert next to total-return TSMOM.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def residual_mom_12_1(
    closes: pd.Series | None,
    bench: pd.Series | None = None,
    *,
    skip: int = 21,
    look: int = 252,
) -> float:
    """Latest residual 12-1 return. 0.0 if the tape is too short."""
    if closes is None:
        return 0.0
    try:
        c = pd.Series(closes).astype(float).dropna()
    except Exception:
        return 0.0
    if len(c) < look + skip + 2:
        return 0.0
    px_now = float(c.iloc[-(skip + 1)])
    px_then = float(c.iloc[-(look + skip + 1)])
    if px_then <= 0 or px_now <= 0:
        return 0.0
    r_s = px_now / px_then - 1.0
    r_m = 0.0
    if bench is not None:
        try:
            b = pd.Series(bench).astype(float).reindex(c.index).ffill().dropna()
            if len(b) >= look + skip + 2:
                bm_now = float(b.iloc[-(skip + 1)])
                bm_then = float(b.iloc[-(look + skip + 1)])
                if bm_then > 0 and bm_now > 0:
                    r_m = bm_now / bm_then - 1.0
        except Exception:
            r_m = 0.0
    out = float(r_s - r_m)
    if not np.isfinite(out):
        return 0.0
    return float(max(-2.0, min(2.0, out)))


def attach_resid_mom(row: Any, closes: pd.Series | None, bench: pd.Series | None) -> Any:
    """Copy row and stamp resid_mom_12_1 so proven_online can vote."""
    rm = residual_mom_12_1(closes, bench)
    if row is None:
        return {"resid_mom_12_1": rm}
    if isinstance(row, dict):
        out = dict(row)
        out["resid_mom_12_1"] = rm
        return out
    try:
        out = row.copy()
        out["resid_mom_12_1"] = rm
        return out
    except Exception:
        return row
