"""Feature/prediction drift diagnostics."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class DriftEntry:
    feature: str
    psi: float
    ks_like: float
    severity: str


def _bin_edges(ref: pd.Series, bins: int = 10) -> np.ndarray:
    q = np.linspace(0, 1, bins + 1)
    e = np.quantile(ref.dropna().values, q)
    # ensure strictly increasing
    e = np.unique(e)
    if len(e) < 3:
        mn, mx = float(ref.min()), float(ref.max())
        if mn == mx:
            mx = mn + 1e-6
        e = np.linspace(mn, mx, bins + 1)
    return e


def _psi(ref: pd.Series, cur: pd.Series, bins: int = 10) -> float:
    edges = _bin_edges(ref, bins=bins)
    r_hist, _ = np.histogram(ref.fillna(0.0), bins=edges)
    c_hist, _ = np.histogram(cur.fillna(0.0), bins=edges)
    r = r_hist / max(r_hist.sum(), 1)
    c = c_hist / max(c_hist.sum(), 1)
    eps = 1e-8
    return float(np.sum((c - r) * np.log((c + eps) / (r + eps))))


def _ks_like(ref: pd.Series, cur: pd.Series) -> float:
    rr = np.sort(ref.fillna(0.0).to_numpy())
    cc = np.sort(cur.fillna(0.0).to_numpy())
    grid = np.unique(np.concatenate([rr, cc]))
    if len(grid) == 0:
        return 0.0
    fr = np.searchsorted(rr, grid, side="right") / max(len(rr), 1)
    fc = np.searchsorted(cc, grid, side="right") / max(len(cc), 1)
    return float(np.max(np.abs(fr - fc)))


def monitor_feature_drift(reference_df: pd.DataFrame, current_df: pd.DataFrame, cols: list[str]) -> dict:
    entries: list[DriftEntry] = []
    for c in cols:
        if c not in reference_df.columns or c not in current_df.columns:
            continue
        psi = _psi(reference_df[c], current_df[c], bins=10)
        ks = _ks_like(reference_df[c], current_df[c])
        if psi >= 0.25 or ks >= 0.30:
            sev = "high"
        elif psi >= 0.10 or ks >= 0.15:
            sev = "medium"
        else:
            sev = "low"
        entries.append(DriftEntry(feature=c, psi=float(psi), ks_like=float(ks), severity=sev))
    high = [e for e in entries if e.severity == "high"]
    med = [e for e in entries if e.severity == "medium"]
    return {
        "ok": len(high) == 0,
        "high_count": len(high),
        "medium_count": len(med),
        "entries": [asdict(e) for e in entries],
    }


def write_drift_report(report: dict, path: str = "reports/drift_report.json") -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return p

