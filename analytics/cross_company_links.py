"""Cross-company linkage mathematics — patterns between tied names.

Finds subtle co-movement humans miss across peers, pairs, dual-listings, and
industry leaders. Formulas (all feed a small rank boost; risk gates stay in charge):

  1. Pearson / Spearman / Kendall rolling correlation
  2. OLS rolling beta + idiosyncratic residual vs peer and vs SPY
  3. Partial correlation (control for market)
  4. Log-spread z-score (stat-arb mean-reversion)
  5. Engle–Granger cointegration proxy (ADF on residual if statsmodels; else residual ACF)
  6. Lead–lag via lagged cross-correlation peak
  7. Realized-vol co-movement
  8. Tail co-move (joint extreme-return rate)
  9. Distance-correlation lite (energy distance on ranks)
 10. Rolling correlation regime break (corr drop vs history)
 11. Beta instability / Chow-style break proxy
 12. Hurst exponent lite on spread (mean-reversion vs trend)
 13. Half-life of mean reversion (OU / AR(1) on spread)
 14. Mutual information lite (binned) between returns
 15. Granger causality lite (lagged R² improvement)
 16. Covariance eigenvalue / PCA share of first factor (pair+market)
 17. Information ratio of residual vs peer
 18. Kalman-lite adaptive hedge ratio (recursive beta)
 19. Copula-lite upper/lower tail dependence (empirical)

Cache: data/intel/cross_company_links.json
Boost: cross_company_rank_boost(symbol)
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "intel" / "cross_company_links.json"


@dataclass
class LinkHit:
    symbol: str
    peer: str
    score: float  # 0..1 linkage / dislocation strength
    direction: int  # +1 long tilt on symbol, -1 short/fade, 0 neutral
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _b(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def _z(x: float, mu: float, sigma: float) -> float:
    if sigma <= 1e-12 or not math.isfinite(sigma):
        return 0.0
    return (x - mu) / sigma


# ---------- pure math (testable without network) ----------


def returns_from_closes(closes: np.ndarray) -> np.ndarray:
    c = np.asarray(closes, dtype=float)
    c = c[np.isfinite(c) & (c > 0)]
    if len(c) < 3:
        return np.array([], dtype=float)
    return np.diff(np.log(c))


def align_returns(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = min(len(a), len(b))
    if n < 20:
        return np.array([]), np.array([])
    return np.asarray(a[-n:], dtype=float), np.asarray(b[-n:], dtype=float)


def pearson_corr(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 5:
        return 0.0
    x = x - x.mean()
    y = y - y.mean()
    d = float(np.sqrt(np.dot(x, x) * np.dot(y, y))) + 1e-12
    return float(np.clip(np.dot(x, y) / d, -1.0, 1.0))


def spearman_corr(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 5:
        return 0.0
    rx = x.argsort().argsort().astype(float)
    ry = y.argsort().argsort().astype(float)
    return pearson_corr(rx, ry)


def kendall_tau(x: np.ndarray, y: np.ndarray) -> float:
    """O(n^2) Kendall τ — fine for short rolling windows."""
    n = len(x)
    if n < 5:
        return 0.0
    # subsample for speed if long
    if n > 120:
        idx = np.linspace(0, n - 1, 120).astype(int)
        x, y = x[idx], y[idx]
        n = len(x)
    conc = disc = 0
    for i in range(n - 1):
        dx = x[i + 1 :] - x[i]
        dy = y[i + 1 :] - y[i]
        s = dx * dy
        conc += int(np.sum(s > 0))
        disc += int(np.sum(s < 0))
    tot = conc + disc
    if tot <= 0:
        return 0.0
    return float((conc - disc) / tot)


def ols_beta_resid(y: np.ndarray, x: np.ndarray) -> tuple[float, np.ndarray]:
    """y = α + β x + ε; return β and residual series."""
    if len(y) < 10 or len(x) < 10:
        return 0.0, np.array([])
    n = min(len(y), len(x))
    y, x = y[-n:], x[-n:]
    xm = x - x.mean()
    ym = y - y.mean()
    denom = float(np.dot(xm, xm)) + 1e-12
    beta = float(np.dot(xm, ym) / denom)
    alpha = float(y.mean() - beta * x.mean())
    resid = y - (alpha + beta * x)
    return beta, resid


def partial_corr_xy_given_z(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> float:
    """Corr(resid_x, resid_y) after regressing out z."""
    n = min(len(x), len(y), len(z))
    if n < 20:
        return 0.0
    x, y, z = x[-n:], y[-n:], z[-n:]
    _, rx = ols_beta_resid(x, z)
    _, ry = ols_beta_resid(y, z)
    if len(rx) < 10:
        return 0.0
    return pearson_corr(rx, ry)


def log_spread_z(closes_a: np.ndarray, closes_b: np.ndarray, window: int = 60) -> tuple[float, float]:
    """z of log(a)-log(b) vs rolling history; also return hedge beta ≈ 1."""
    n = min(len(closes_a), len(closes_b))
    if n < window + 5:
        return 0.0, 1.0
    a = np.asarray(closes_a[-n:], dtype=float)
    b = np.asarray(closes_b[-n:], dtype=float)
    mask = (a > 0) & (b > 0) & np.isfinite(a) & np.isfinite(b)
    a, b = a[mask], b[mask]
    if len(a) < window + 5:
        return 0.0, 1.0
    spread = np.log(a) - np.log(b)
    hist = spread[-(window + 1) : -1]
    z = _z(float(spread[-1]), float(hist.mean()), float(hist.std() + 1e-12))
    return z, 1.0


def engle_granger_score(closes_a: np.ndarray, closes_b: np.ndarray) -> tuple[float, float, float]:
    """Cointegration proxy: regress log a on log b; score stationarity of residual.

    Returns (score 0..1, beta, adf_stat_or_acf_proxy).
    """
    n = min(len(closes_a), len(closes_b))
    if n < 40:
        return 0.0, 0.0, 0.0
    a = np.log(np.asarray(closes_a[-n:], dtype=float).clip(min=1e-8))
    b = np.log(np.asarray(closes_b[-n:], dtype=float).clip(min=1e-8))
    beta, resid = ols_beta_resid(a, b)
    if len(resid) < 30:
        return 0.0, beta, 0.0

    adf_stat = 0.0
    try:
        from statsmodels.tsa.stattools import adfuller

        adf_stat = float(adfuller(resid, maxlag=1, regression="c", autolag=None)[0])
        # More negative ADF → stronger cointegration
        score = float(np.clip((-adf_stat - 1.5) / 3.5, 0.0, 1.0))
        return score, beta, adf_stat
    except Exception:
        pass

    # Fallback: low lag-1 ACF of residual differences implies mean-reverting spread
    r = resid - resid.mean()
    if float(np.dot(r[:-1], r[:-1])) < 1e-12:
        return 0.0, beta, 0.0
    acf1 = float(np.dot(r[1:], r[:-1]) / (np.dot(r[:-1], r[:-1]) + 1e-12))
    score = float(np.clip((0.85 - abs(acf1)) / 0.85, 0.0, 1.0))
    return score, beta, acf1


def lead_lag_peak(x: np.ndarray, y: np.ndarray, max_lag: int = 5) -> tuple[int, float]:
    """Lag of y that maximizes corr(x_t, y_{t-lag}). Positive lag ⇒ y leads x."""
    x, y = align_returns(x, y)
    if len(x) < 30:
        return 0, 0.0
    best_lag, best_c = 0, pearson_corr(x, y)
    for lag in range(-max_lag, max_lag + 1):
        if lag == 0:
            continue
        if lag > 0:
            c = pearson_corr(x[lag:], y[:-lag])
        else:
            c = pearson_corr(x[:lag], y[-lag:])
        if abs(c) > abs(best_c):
            best_c, best_lag = c, lag
    return int(best_lag), float(best_c)


def realized_vol(rets: np.ndarray, window: int = 20) -> np.ndarray:
    if len(rets) < window + 2:
        return np.array([])
    out = np.empty(len(rets) - window + 1)
    for i in range(len(out)):
        out[i] = float(np.std(rets[i : i + window]) * math.sqrt(252))
    return out


def vol_comovement(rx: np.ndarray, ry: np.ndarray, window: int = 20) -> float:
    vx, vy = realized_vol(rx, window), realized_vol(ry, window)
    vx, vy = align_returns(vx, vy)
    if len(vx) < 10:
        return 0.0
    return pearson_corr(vx, vy)


def tail_comove(rx: np.ndarray, ry: np.ndarray, q: float = 0.1) -> float:
    """P(both extreme) / (P(x extreme) P(y extreme)) − 1, clipped."""
    rx, ry = align_returns(rx, ry)
    if len(rx) < 40:
        return 0.0
    tx = np.quantile(np.abs(rx), 1.0 - q)
    ty = np.quantile(np.abs(ry), 1.0 - q)
    ex = np.abs(rx) >= tx
    ey = np.abs(ry) >= ty
    p_both = float(np.mean(ex & ey))
    px, py = float(np.mean(ex)), float(np.mean(ey))
    if px * py < 1e-12:
        return 0.0
    lift = p_both / (px * py) - 1.0
    return float(np.clip(lift, -1.0, 3.0))


def distance_corr_lite(x: np.ndarray, y: np.ndarray) -> float:
    """Cheap distance-correlation proxy via double-centered absolute differences."""
    n = min(len(x), len(y))
    if n < 15:
        return 0.0
    if n > 80:
        idx = np.linspace(0, n - 1, 80).astype(int)
        x, y = x[idx], y[idx]
        n = len(x)
    a = np.abs(x[:, None] - x[None, :])
    b = np.abs(y[:, None] - y[None, :])
    A = a - a.mean(axis=1, keepdims=True) - a.mean(axis=0, keepdims=True) + a.mean()
    B = b - b.mean(axis=1, keepdims=True) - b.mean(axis=0, keepdims=True) + b.mean()
    dcov = float(np.mean(A * B))
    dvarx = float(np.mean(A * A))
    dvary = float(np.mean(B * B))
    denom = math.sqrt(max(dvarx, 0) * max(dvary, 0)) + 1e-12
    return float(np.clip(dcov / denom, 0.0, 1.0))


def rolling_corr_series(x: np.ndarray, y: np.ndarray, window: int = 20) -> np.ndarray:
    n = min(len(x), len(y))
    if n < window + 2:
        return np.array([])
    x, y = x[-n:], y[-n:]
    out = np.empty(n - window + 1)
    for i in range(len(out)):
        out[i] = pearson_corr(x[i : i + window], y[i : i + window])
    return out


def corr_regime_break(x: np.ndarray, y: np.ndarray, window: int = 20) -> float:
    """How far the latest rolling corr dropped below its own history (positive ⇒ break)."""
    series = rolling_corr_series(x, y, window=window)
    if len(series) < 10:
        return 0.0
    hist = series[:-1]
    latest = float(series[-1])
    drop = float(hist.mean()) - latest
    # Only count breaks when correlation was previously meaningful
    if float(hist.mean()) < 0.15:
        return 0.0
    return float(np.clip(drop, 0.0, 2.0))


def beta_chow_break(y: np.ndarray, x: np.ndarray, split: float = 0.5) -> float:
    """Chow-style beta instability: |β_late − β_early| / (σ_β proxy).

    Returns a non-negative break score (0 = stable).
    """
    n = min(len(y), len(x))
    if n < 40:
        return 0.0
    y, x = y[-n:], x[-n:]
    k = max(15, int(n * split))
    if k >= n - 15:
        k = n // 2
    b1, _ = ols_beta_resid(y[:k], x[:k])
    b2, _ = ols_beta_resid(y[k:], x[k:])
    # scale by residual vol of full-sample beta
    b_full, resid = ols_beta_resid(y, x)
    if len(resid) < 10:
        return abs(b2 - b1)
    scale = float(np.std(resid) / (np.std(x) + 1e-12)) + 1e-6
    return float(abs(b2 - b1) / scale)


def hurst_lite(series: np.ndarray) -> float:
    """R/S Hurst exponent lite on a 1-D series (spread). H≈0.5 random; <0.5 MR; >0.5 trend."""
    x = np.asarray(series, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 32:
        return 0.5
    # demean
    x = x - x.mean()
    max_k = min(n // 2, 64)
    ks = [k for k in (4, 8, 16, 32, 64) if k <= max_k]
    if len(ks) < 2:
        return 0.5
    log_n: list[float] = []
    log_rs: list[float] = []
    for k in ks:
        rs_vals = []
        for start in range(0, n - k + 1, k):
            seg = x[start : start + k]
            if float(np.std(seg)) < 1e-12:
                continue
            y = np.cumsum(seg - seg.mean())
            r = float(y.max() - y.min())
            s = float(np.std(seg)) + 1e-12
            rs_vals.append(r / s)
        if not rs_vals:
            continue
        log_n.append(math.log(k))
        log_rs.append(math.log(float(np.mean(rs_vals)) + 1e-12))
    if len(log_n) < 2:
        return 0.5
    xn = np.asarray(log_n)
    yn = np.asarray(log_rs)
    xm = xn - xn.mean()
    denom = float(np.dot(xm, xm)) + 1e-12
    h = float(np.dot(xm, yn - yn.mean()) / denom)
    return float(np.clip(h, 0.0, 1.0))


def ou_half_life(spread: np.ndarray) -> float:
    """AR(1) / OU half-life in bars: spread_t = a + φ spread_{t-1} + ε → HL = −ln(2)/ln(φ)."""
    s = np.asarray(spread, dtype=float)
    s = s[np.isfinite(s)]
    if len(s) < 30:
        return 0.0
    y = s[1:]
    x = s[:-1]
    xm = x - x.mean()
    ym = y - y.mean()
    denom = float(np.dot(xm, xm)) + 1e-12
    phi = float(np.dot(xm, ym) / denom)
    if phi <= 0.0 or phi >= 0.999:
        return 0.0
    hl = -math.log(2.0) / math.log(phi)
    return float(np.clip(hl, 0.0, 500.0))


def mutual_info_lite(x: np.ndarray, y: np.ndarray, bins: int = 8) -> float:
    """Binned mutual information (nats) between two return series."""
    n = min(len(x), len(y))
    if n < 30:
        return 0.0
    x, y = x[-n:], y[-n:]
    bins = max(4, min(bins, int(math.sqrt(n / 3))))
    try:
        c_xy, _, _ = np.histogram2d(x, y, bins=bins)
    except Exception:
        return 0.0
    p_xy = c_xy / (c_xy.sum() + 1e-12)
    px = p_xy.sum(axis=1)
    py = p_xy.sum(axis=0)
    mi = 0.0
    for i in range(p_xy.shape[0]):
        for j in range(p_xy.shape[1]):
            p = p_xy[i, j]
            if p <= 0:
                continue
            denom = px[i] * py[j]
            if denom <= 0:
                continue
            mi += float(p * math.log(p / denom))
    return float(max(0.0, mi))


def granger_lite(y: np.ndarray, x: np.ndarray, lag: int = 2) -> float:
    """Lagged R² improvement: does lagged x help predict y beyond lagged y?

    Returns max(0, R²_full − R²_ar) clipped.
    """
    n = min(len(y), len(x))
    if n < 40 or lag < 1:
        return 0.0
    y, x = y[-n:], x[-n:]
    # Build design: [y_{t-1}…y_{t-lag}] vs + [x_{t-1}…x_{t-lag}]
    rows = n - lag
    if rows < 20:
        return 0.0
    Y = y[lag:]
    X_ar = np.column_stack([y[lag - k : n - k] for k in range(1, lag + 1)])
    X_full = np.column_stack(
        [X_ar, *[x[lag - k : n - k] for k in range(1, lag + 1)]]
    )

    def _r2(X: np.ndarray, yy: np.ndarray) -> float:
        # add intercept
        X1 = np.column_stack([np.ones(len(yy)), X])
        try:
            coef, _, _, _ = np.linalg.lstsq(X1, yy, rcond=None)
        except Exception:
            return 0.0
        pred = X1 @ coef
        ss_res = float(np.sum((yy - pred) ** 2))
        ss_tot = float(np.sum((yy - yy.mean()) ** 2)) + 1e-12
        return float(np.clip(1.0 - ss_res / ss_tot, 0.0, 1.0))

    r_ar = _r2(X_ar, Y)
    r_full = _r2(X_full, Y)
    return float(np.clip(r_full - r_ar, 0.0, 1.0))


def pca_factor_share(rx: np.ndarray, ry: np.ndarray, rm: np.ndarray | None = None) -> float:
    """Share of variance explained by the first eigenvalue of the cov matrix (pair [+ mkt])."""
    cols = [rx, ry]
    if rm is not None and len(rm) >= 20:
        cols.append(rm)
    n = min(len(c) for c in cols)
    if n < 25:
        return 0.0
    M = np.column_stack([c[-n:] for c in cols])
    M = M - M.mean(axis=0, keepdims=True)
    cov = (M.T @ M) / max(n - 1, 1)
    try:
        eig = np.linalg.eigvalsh(cov)
    except Exception:
        return 0.0
    eig = np.maximum(eig.real, 0.0)
    tot = float(eig.sum()) + 1e-12
    return float(np.clip(eig.max() / tot, 0.0, 1.0))


def residual_information_ratio(resid: np.ndarray) -> float:
    """Annualized IR of residual series vs peer (mean/std * sqrt(252))."""
    r = np.asarray(resid, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 20:
        return 0.0
    sig = float(np.std(r)) + 1e-12
    return float((np.mean(r) / sig) * math.sqrt(252.0))


def kalman_lite_beta(y: np.ndarray, x: np.ndarray, q: float = 1e-5, r: float = 1e-3) -> tuple[float, np.ndarray]:
    """Recursive OLS / Kalman-lite adaptive hedge ratio (scalar β, known α≈0 demeaned).

    Returns (final_beta, beta_path).
    """
    n = min(len(y), len(x))
    if n < 20:
        return 0.0, np.array([])
    y, x = y[-n:].astype(float), x[-n:].astype(float)
    # demean online-ish
    beta = 1.0
    p = 1.0
    path = np.empty(n)
    for t in range(n):
        # predict
        p = p + q
        # update
        xt = x[t]
        s = p * xt * xt + r
        k = (p * xt) / (s + 1e-12)
        beta = beta + k * (y[t] - beta * xt)
        p = (1.0 - k * xt) * p
        path[t] = beta
    return float(beta), path


def empirical_tail_dependence(
    x: np.ndarray, y: np.ndarray, q: float = 0.1
) -> tuple[float, float]:
    """Empirical upper/lower tail dependence coefficients (copula-lite).

    λ_u ≈ P(U>1-q, V>1-q) / q ; λ_l ≈ P(U<q, V<q) / q  using rank uniforms.
    """
    n = min(len(x), len(y))
    if n < 40:
        return 0.0, 0.0
    x, y = x[-n:], y[-n:]
    # ranks → pseudo-observations in (0,1)
    u = (x.argsort().argsort().astype(float) + 1.0) / (n + 1.0)
    v = (y.argsort().argsort().astype(float) + 1.0) / (n + 1.0)
    q = float(np.clip(q, 0.02, 0.25))
    lam_u = float(np.mean((u > 1.0 - q) & (v > 1.0 - q)) / q)
    lam_l = float(np.mean((u < q) & (v < q)) / q)
    return float(np.clip(lam_u, 0.0, 1.0)), float(np.clip(lam_l, 0.0, 1.0))


def _log_spread_series(closes_a: np.ndarray, closes_b: np.ndarray) -> np.ndarray:
    n = min(len(closes_a), len(closes_b))
    if n < 10:
        return np.array([])
    a = np.asarray(closes_a[-n:], dtype=float)
    b = np.asarray(closes_b[-n:], dtype=float)
    mask = (a > 0) & (b > 0) & np.isfinite(a) & np.isfinite(b)
    a, b = a[mask], b[mask]
    if len(a) < 10:
        return np.array([])
    return np.log(a) - np.log(b)


def link_metrics(
    closes_a: np.ndarray,
    closes_b: np.ndarray,
    closes_mkt: np.ndarray | None = None,
) -> dict[str, float]:
    """Compute full inter-company metric bundle for two close series."""
    ra = returns_from_closes(closes_a)
    rb = returns_from_closes(closes_b)
    ra, rb = align_returns(ra, rb)
    out: dict[str, float] = {}
    if len(ra) < 25:
        return out

    win = ra[-60:] if len(ra) >= 60 else ra
    wb = rb[-len(win) :]
    out["pearson"] = pearson_corr(win, wb)
    out["spearman"] = spearman_corr(win, wb)
    out["kendall"] = kendall_tau(win, wb)

    beta_p, resid_p = ols_beta_resid(win, wb)
    out["beta_peer"] = beta_p
    if len(resid_p) >= 20:
        out["idio_z_peer"] = _z(
            float(resid_p[-1]), float(resid_p[:-1].mean()), float(resid_p[:-1].std() + 1e-12)
        )

    if closes_mkt is not None and len(closes_mkt) >= 30:
        rm = returns_from_closes(closes_mkt)
        n = min(len(ra), len(rb), len(rm))
        if n >= 30:
            rx, ry, rz = ra[-n:], rb[-n:], rm[-n:]
            out["partial_corr"] = partial_corr_xy_given_z(rx, ry, rz)
            beta_m, resid_m = ols_beta_resid(rx, rz)
            out["beta_mkt"] = beta_m
            if len(resid_m) >= 20:
                out["idio_z_mkt"] = _z(
                    float(resid_m[-1]),
                    float(resid_m[:-1].mean()),
                    float(resid_m[:-1].std() + 1e-12),
                )

    sz, _ = log_spread_z(closes_a, closes_b)
    out["spread_z"] = sz
    coint, cbeta, cadf = engle_granger_score(closes_a, closes_b)
    out["coint_score"] = coint
    out["coint_beta"] = cbeta
    out["coint_stat"] = cadf

    lag, lcorr = lead_lag_peak(ra, rb, max_lag=int(_f("CROSS_LINK_MAX_LAG", 5)))
    out["lead_lag"] = float(lag)
    out["lead_lag_corr"] = lcorr

    out["vol_corr"] = vol_comovement(ra, rb)
    out["tail_lift"] = tail_comove(ra, rb)
    out["dcorr"] = distance_corr_lite(win, wb)

    # --- extended math (additive; never removes prior metrics) ---
    out["corr_break"] = corr_regime_break(ra, rb, window=int(_f("CROSS_LINK_CORR_WIN", 20)))
    out["beta_chow"] = beta_chow_break(win, wb)

    spread = _log_spread_series(closes_a, closes_b)
    if len(spread) >= 32:
        out["hurst_spread"] = hurst_lite(spread)
        out["half_life"] = ou_half_life(spread)

    out["mi_lite"] = mutual_info_lite(win, wb, bins=int(_f("CROSS_LINK_MI_BINS", 8)))
    out["granger_peer"] = granger_lite(win, wb, lag=int(_f("CROSS_LINK_GRANGER_LAG", 2)))
    out["granger_from_peer"] = granger_lite(wb, win, lag=int(_f("CROSS_LINK_GRANGER_LAG", 2)))

    rm_aligned: np.ndarray | None = None
    if closes_mkt is not None and len(closes_mkt) >= 30:
        rm = returns_from_closes(closes_mkt)
        n3 = min(len(ra), len(rb), len(rm))
        if n3 >= 30:
            rm_aligned = rm[-n3:]
            out["pca_share"] = pca_factor_share(ra[-n3:], rb[-n3:], rm_aligned)
    if "pca_share" not in out:
        out["pca_share"] = pca_factor_share(win, wb, None)

    if len(resid_p) >= 20:
        out["resid_ir"] = residual_information_ratio(resid_p)

    if _b("CROSS_LINK_KALMAN", True):
        k_beta, k_path = kalman_lite_beta(win, wb)
        out["kalman_beta"] = k_beta
        if len(k_path) >= 10:
            out["kalman_beta_drift"] = float(abs(k_path[-1] - k_path[max(0, len(k_path) // 2)]))

    lam_u, lam_l = empirical_tail_dependence(win, wb, q=_f("CROSS_LINK_TAIL_Q", 0.1))
    out["tail_dep_upper"] = lam_u
    out["tail_dep_lower"] = lam_l
    return out


def score_link(metrics: dict[str, float]) -> tuple[float, int, list[str]]:
    """Blend metrics → (score 0..1, direction, reasons)."""
    if not metrics:
        return 0.0, 0, []
    reasons: list[str] = []
    score = 0.0

    # Strong structural tie
    pc = abs(float(metrics.get("partial_corr") or metrics.get("pearson") or 0))
    if pc >= 0.55:
        score += 0.15 * min(1.0, (pc - 0.4) / 0.5)
        reasons.append(f"corr={pc:.2f}")

    coint = float(metrics.get("coint_score") or 0)
    if coint >= 0.35:
        score += 0.22 * coint
        reasons.append(f"coint={coint:.2f}")

    # Dislocation / mean-reversion opportunity
    sz = float(metrics.get("spread_z") or 0)
    if abs(sz) >= 1.5:
        score += 0.28 * min(1.0, abs(sz) / 3.0)
        reasons.append(f"spread_z={sz:.2f}")

    idio = float(metrics.get("idio_z_peer") or metrics.get("idio_z_mkt") or 0)
    if abs(idio) >= 1.8:
        score += 0.18 * min(1.0, abs(idio) / 3.0)
        reasons.append(f"idio_z={idio:.2f}")

    lag = int(metrics.get("lead_lag") or 0)
    lc = abs(float(metrics.get("lead_lag_corr") or 0))
    if lag != 0 and lc >= 0.35:
        score += 0.12 * min(1.0, lc)
        reasons.append(f"lead_lag={lag} corr={lc:.2f}")

    vc = float(metrics.get("vol_corr") or 0)
    if vc >= 0.5:
        score += 0.06 * min(1.0, vc)
        reasons.append(f"vol_corr={vc:.2f}")

    tl = float(metrics.get("tail_lift") or 0)
    if tl >= 0.4:
        score += 0.08 * min(1.0, tl / 2.0)
        reasons.append(f"tail_lift={tl:.2f}")

    dc = float(metrics.get("dcorr") or 0)
    if dc >= 0.45:
        score += 0.05 * dc
        reasons.append(f"dcorr={dc:.2f}")

    # Extended formulas
    cb = float(metrics.get("corr_break") or 0)
    if cb >= 0.25:
        score += 0.10 * min(1.0, cb / 0.8)
        reasons.append(f"corr_break={cb:.2f}")

    chow = float(metrics.get("beta_chow") or 0)
    if chow >= 0.8:
        score += 0.07 * min(1.0, chow / 2.5)
        reasons.append(f"beta_chow={chow:.2f}")

    hurst = float(metrics.get("hurst_spread") or 0.5)
    hl = float(metrics.get("half_life") or 0)
    if hurst > 0 and hurst < 0.45 and 2.0 <= hl <= 60.0:
        score += 0.10 * (0.45 - hurst) / 0.45
        reasons.append(f"hurst={hurst:.2f} hl={hl:.1f}")

    mi = float(metrics.get("mi_lite") or 0)
    if mi >= 0.08:
        score += 0.05 * min(1.0, mi / 0.35)
        reasons.append(f"mi={mi:.2f}")

    g = max(float(metrics.get("granger_peer") or 0), float(metrics.get("granger_from_peer") or 0))
    if g >= 0.04:
        score += 0.06 * min(1.0, g / 0.2)
        reasons.append(f"granger={g:.2f}")

    pca = float(metrics.get("pca_share") or 0)
    if pca >= 0.65:
        score += 0.04 * min(1.0, (pca - 0.5) / 0.4)
        reasons.append(f"pca={pca:.2f}")

    ir = float(metrics.get("resid_ir") or 0)
    if abs(ir) >= 0.8:
        score += 0.08 * min(1.0, abs(ir) / 2.5)
        reasons.append(f"resid_ir={ir:.2f}")

    k_drift = float(metrics.get("kalman_beta_drift") or 0)
    if k_drift >= 0.25:
        score += 0.04 * min(1.0, k_drift / 1.0)
        reasons.append(f"kalman_drift={k_drift:.2f}")

    tdu = float(metrics.get("tail_dep_upper") or 0)
    tdl = float(metrics.get("tail_dep_lower") or 0)
    td = max(tdu, tdl)
    if td >= 0.35:
        score += 0.06 * min(1.0, td / 0.8)
        reasons.append(f"tail_dep={td:.2f}")

    score = float(np.clip(score, 0.0, 1.0))
    # Direction: mean-revert spread / fade extreme idio
    direction = 0
    if abs(sz) >= 1.2:
        direction = -1 if sz > 0 else 1  # symbol rich vs peer → fade
    elif abs(idio) >= 1.5:
        direction = 1 if idio > 0 else -1
    elif abs(ir) >= 1.0:
        direction = 1 if ir > 0 else -1
    elif lag > 0 and float(metrics.get("lead_lag_corr") or 0) > 0:
        direction = 1  # peer leads up → follow
    elif lag > 0 and float(metrics.get("lead_lag_corr") or 0) < 0:
        direction = -1

    return score, direction, reasons[:8]


# ---------- I/O + peers + scan ----------


def _fetch_closes(symbol: str, period: str = "1y") -> np.ndarray | None:
    try:
        from data_platform.market_prices import fetch_period

        df = fetch_period(symbol.strip().upper(), period=period, interval="1d")
        if df is not None and not df.empty:
            col = "Close" if "Close" in df.columns else "close"
            if col in df.columns:
                c = df[col].astype(float).values
                c = c[np.isfinite(c) & (c > 0)]
                if len(c) >= 40:
                    return np.asarray(c, dtype=float)
    except Exception:
        pass
    try:
        import yfinance as yf

        df = yf.download(symbol, period=period, interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None
        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        col = "Close" if "Close" in df.columns else "close"
        c = df[col].astype(float).values
        c = c[np.isfinite(c) & (c > 0)]
        if len(c) >= 40:
            return np.asarray(c, dtype=float)
    except Exception:
        return None
    return None


def _pair_map() -> dict[str, str]:
    try:
        from analytics.hedge_fund_stack import _pair_map as hf_pairs

        return dict(hf_pairs())
    except Exception:
        raw = os.getenv(
            "PAPER_SIM_PAIR_MAP",
            "KO:PEP,PEP:KO,V:MA,MA:V,XOM:CVX,CVX:XOM,JPM:BAC,BAC:JPM,"
            "MSFT:AAPL,AAPL:MSFT,GOOGL:META,META:GOOGL",
        )
        out: dict[str, str] = {}
        for token in raw.split(","):
            if ":" not in token:
                continue
            a, b = token.strip().upper().split(":", 1)
            if a and b and a != b:
                out[a] = b
        return out


def _dual_listing_peers(symbol: str) -> list[str]:
    peers: list[str] = []
    pairs: list[dict] = []
    try:
        from analytics.market_imbalance import default_pairs, load_pairs

        try:
            pairs = list(load_pairs() or [])
        except Exception:
            pairs = list(default_pairs() or [])
    except Exception:
        pairs = []
    try:
        path = ROOT / "data" / "intel" / "cross_listing_pairs.json"
        if path.is_file() and not pairs:
            doc = json.loads(path.read_text(encoding="utf-8"))
            raw = doc.get("pairs") if isinstance(doc, dict) else doc
            if isinstance(raw, list):
                pairs = [r for r in raw if isinstance(r, dict)]
    except Exception:
        pass
    for row in pairs:
        a = str(row.get("primary") or row.get("a") or row.get("us") or "").upper()
        b = str(row.get("peer") or row.get("b") or row.get("local") or "").upper()
        if symbol == a and b:
            peers.append(b)
        elif symbol == b and a:
            peers.append(a)
    return peers


def _industry_peers(symbol: str, limit: int = 4) -> list[str]:
    try:
        from analytics.industries.peer_ticker_map import PEER_TICKER_MAP

        row = PEER_TICKER_MAP.get(symbol.upper()) or {}
        iid = row.get("industry_id") if isinstance(row, dict) else None
        if not iid:
            return []
        scored = []
        for sym, meta in PEER_TICKER_MAP.items():
            if not isinstance(meta, dict):
                continue
            if meta.get("industry_id") == iid and sym.upper() != symbol.upper():
                scored.append((float(meta.get("market_cap") or 0), sym.upper()))
        scored.sort(reverse=True)
        return [s for _, s in scored[:limit]]
    except Exception:
        return []


def peers_for(symbol: str, limit: int = 6) -> list[str]:
    s = symbol.strip().upper()
    out: list[str] = []
    pm = _pair_map()
    if s in pm:
        out.append(pm[s])
    out.extend(_dual_listing_peers(s))
    out.extend(_industry_peers(s, limit=max(2, limit - len(out))))
    # de-dupe preserve order
    seen: set[str] = set()
    clean: list[str] = []
    for p in out:
        u = p.upper()
        if u and u != s and u not in seen:
            seen.add(u)
            clean.append(u)
        if len(clean) >= limit:
            break
    return clean


def analyze_pair(
    symbol: str,
    peer: str,
    *,
    closes_a: np.ndarray | None = None,
    closes_b: np.ndarray | None = None,
    closes_mkt: np.ndarray | None = None,
) -> LinkHit | None:
    a = closes_a if closes_a is not None else _fetch_closes(symbol)
    b = closes_b if closes_b is not None else _fetch_closes(peer)
    if a is None or b is None:
        return None
    mkt = closes_mkt
    if mkt is None:
        mkt = _fetch_closes(os.getenv("CROSS_LINK_BENCH", "SPY"))
    metrics = link_metrics(a, b, mkt)
    score, direction, reasons = score_link(metrics)
    min_score = _f("CROSS_LINK_MIN_SCORE", 0.28)
    if score < min_score and abs(float(metrics.get("spread_z") or 0)) < 1.2:
        return None
    reasons = [f"vs {peer}: {r}" for r in reasons] or [f"linked:{peer}"]
    return LinkHit(
        symbol=symbol.upper(),
        peer=peer.upper(),
        score=score,
        direction=direction,
        reasons=reasons,
        metrics={k: float(v) for k, v in metrics.items()},
    )


def default_universe(limit: int = 40) -> list[str]:
    syms: list[str] = []
    # Always include known pairs
    pm = _pair_map()
    syms.extend(pm.keys())
    try:
        from fortress_universe import load_top100_symbols

        syms.extend(load_top100_symbols()[: max(20, limit)])
    except Exception:
        syms.extend(["AAPL", "MSFT", "GOOGL", "META", "JPM", "BAC", "XOM", "CVX", "KO", "PEP"])
    return list(dict.fromkeys(s.upper() for s in syms))[:limit]


def scan_universe(symbols: Iterable[str], *, limit: int | None = None) -> list[LinkHit]:
    lim = limit if limit is not None else int(_f("CROSS_LINK_SCAN_LIMIT", 40))
    mkt = _fetch_closes(os.getenv("CROSS_LINK_BENCH", "SPY"))
    hits: list[LinkHit] = []
    cache_closes: dict[str, np.ndarray | None] = {}

    def closes(sym: str) -> np.ndarray | None:
        if sym not in cache_closes:
            cache_closes[sym] = _fetch_closes(sym)
        return cache_closes[sym]

    for sym in list(symbols)[:lim]:
        s = str(sym).upper()
        ca = closes(s)
        if ca is None:
            continue
        for peer in peers_for(s, limit=int(_f("CROSS_LINK_PEERS", 4))):
            cb = closes(peer)
            if cb is None:
                continue
            hit = analyze_pair(s, peer, closes_a=ca, closes_b=cb, closes_mkt=mkt)
            if hit is not None:
                hits.append(hit)
    # keep best per symbol
    best: dict[str, LinkHit] = {}
    for h in hits:
        prev = best.get(h.symbol)
        if prev is None or h.score > prev.score:
            best[h.symbol] = h
    return sorted(best.values(), key=lambda h: h.score, reverse=True)


def save_hits(hits: list[LinkHit]) -> Path:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    by_symbol = {h.symbol: h.to_dict() for h in hits}
    payload = {
        "ts": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "count": len(hits),
        "hits": [h.to_dict() for h in hits],
        "by_symbol": by_symbol,
    }
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, OUT_PATH)
    return OUT_PATH


def load_hits() -> dict[str, Any]:
    if not OUT_PATH.is_file():
        return {"ts": 0, "hits": [], "by_symbol": {}}
    try:
        return json.loads(OUT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"ts": 0, "hits": [], "by_symbol": {}}


def cross_company_rank_boost(symbol: str) -> tuple[float, dict[str, Any]]:
    if not _b("USE_CROSS_COMPANY_LINKS", True):
        return 0.0, {"enabled": False}
    doc = load_hits()
    age = time.time() - float(doc.get("ts") or 0)
    if age > _f("CROSS_LINK_MAX_AGE_SEC", 7200):
        return 0.0, {"stale": True, "age": age}
    row = (doc.get("by_symbol") or {}).get(symbol.strip().upper())
    if not row:
        return 0.0, {"hit": False}
    score = float(row.get("score") or 0)
    direction = int(row.get("direction") or 0)
    w = _f("RANK_W_CROSS_COMPANY", 0.14)
    boost = w * score * (1.0 if direction >= 0 else -0.65)
    meta = {
        "hit": True,
        "peer": row.get("peer"),
        "score": score,
        "direction": direction,
        "reasons": list(row.get("reasons") or [])[:4],
        "metrics": row.get("metrics") or {},
        "boost": boost,
    }
    return float(boost), meta


def run_scan_cycle(*, limit: int | None = None) -> dict[str, Any]:
    if not _b("USE_CROSS_COMPANY_LINKS", True):
        return {"enabled": False, "hits": 0}
    lim = limit if limit is not None else int(_f("CROSS_LINK_SCAN_LIMIT", 40))
    hits = scan_universe(default_universe(lim), limit=lim)
    path = save_hits(hits)
    return {
        "enabled": True,
        "hits": len(hits),
        "path": str(path),
        "top": [
            {"symbol": h.symbol, "peer": h.peer, "score": h.score, "reasons": h.reasons[:2]}
            for h in hits[:8]
        ],
    }


if __name__ == "__main__":
    import pprint

    pprint.pp(run_scan_cycle(limit=int(os.getenv("CROSS_LINK_SCAN_LIMIT", "24"))))
