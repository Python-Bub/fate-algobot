"""Data quality checks for OHLCV frames.

Designed to run per-symbol quickly, returning machine-readable issue lists so
ingestion can quarantine or down-rank bad slices before training.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd


@dataclass
class QualityIssue:
    code: str
    severity: str
    detail: str


def _required_cols() -> tuple[str, ...]:
    return ("Open", "High", "Low", "Close", "Volume")


def _check_required(df: pd.DataFrame) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for c in _required_cols():
        if c not in df.columns:
            issues.append(QualityIssue("missing_column", "critical", f"missing:{c}"))
    return issues


def _check_index(df: pd.DataFrame) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    if not isinstance(df.index, pd.DatetimeIndex):
        issues.append(QualityIssue("bad_index", "critical", "index_not_datetime"))
        return issues
    if df.index.duplicated().any():
        issues.append(QualityIssue("duplicate_index", "high", "duplicate timestamps"))
    if not df.index.is_monotonic_increasing:
        issues.append(QualityIssue("unsorted_index", "high", "timestamps not sorted"))
    return issues


def _check_price_geometry(df: pd.DataFrame) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    if df.empty:
        issues.append(QualityIssue("empty", "critical", "no rows"))
        return issues
    bad = (df["High"] < df["Low"]).sum()
    if bad:
        issues.append(QualityIssue("high_below_low", "critical", f"{int(bad)} rows"))
    nonpos = ((df["Close"] <= 0) | (df["Open"] <= 0)).sum()
    if nonpos:
        issues.append(QualityIssue("non_positive_price", "critical", f"{int(nonpos)} rows"))
    return issues


def _check_missing(df: pd.DataFrame) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    miss_ratio = float(df[list(_required_cols())].isna().mean().mean())
    if miss_ratio > 0:
        sev = "high" if miss_ratio > 0.02 else "medium"
        issues.append(QualityIssue("missing_values", sev, f"ratio={miss_ratio:.4f}"))
    return issues


def _check_return_outliers(df: pd.DataFrame) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    close = df["Close"].replace(0, np.nan)
    r = close.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    if r.empty:
        return issues
    giant = int((r.abs() > 0.80).sum())
    if giant:
        issues.append(QualityIssue("extreme_return_jump", "high", f"abs_ret>80% rows={giant}"))
    z = ((r - r.mean()) / (r.std() + 1e-9)).abs()
    spikes = int((z > 8).sum())
    if spikes:
        issues.append(QualityIssue("zscore_outlier", "medium", f"z>8 rows={spikes}"))
    return issues


def _check_stale(df: pd.DataFrame) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    if len(df) < 10:
        return issues
    repeats = int((df["Close"].diff().abs() < 1e-12).rolling(10).sum().max())
    if repeats >= 8:
        issues.append(QualityIssue("stale_close_series", "medium", f"max_10bar_repeats={repeats}"))
    return issues


def audit_ohlcv(df: pd.DataFrame) -> dict:
    issues: list[QualityIssue] = []
    issues.extend(_check_required(df))
    if any(i.severity == "critical" for i in issues):
        return {
            "ok": False,
            "severity": "critical",
            "issues": [asdict(i) for i in issues],
            "rows": int(len(df)),
        }

    issues.extend(_check_index(df))
    issues.extend(_check_price_geometry(df))
    issues.extend(_check_missing(df))
    issues.extend(_check_return_outliers(df))
    issues.extend(_check_stale(df))

    sev_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    worst = "low"
    for i in issues:
        if sev_rank[i.severity] > sev_rank[worst]:
            worst = i.severity
    ok = worst in ("low", "medium")
    return {
        "ok": ok,
        "severity": worst,
        "issues": [asdict(i) for i in issues],
        "rows": int(len(df)),
    }

