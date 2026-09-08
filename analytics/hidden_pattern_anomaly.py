"""Hidden pattern anomaly detection — subtle price structure humans miss.

Looks for connections and breaks that are invisible on a chart glance:
  1. Idiosyncratic residual spikes vs rolling market beta
  2. Volume–return divergence (z-scored)
  3. Autocorrelation / volatility-regime breaks
  4. Multivariate IsolationForest outliers on return/vol/volume features
  5. Sequence-discovery next-step that diverges from the recent path
  6. Motif echo — nearest historical return-shape + forward path
  7. Entropy / complexity regime breaks
  8. Rolling correlation flip vs market (lead/lag regime)

Outputs feed `data/intel/hidden_pattern_anomalies.json`. Live final calc uses
`hidden_anomaly_rank_boost` + `hidden_pattern_p_blend` (soft p_up). Detector
family weights auto-adjust via `analytics.hidden_pattern_learn` from trade
outcomes. Never sizes trades alone — risk gates stay in charge.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "intel" / "hidden_pattern_anomalies.json"


@dataclass
class AnomalyHit:
    symbol: str
    score: float  # 0..1 anomaly strength
    direction: int  # +1 bullish tilt, -1 bearish, 0 neutral oddity
    reasons: list[str] = field(default_factory=list)
    features: dict[str, float] = field(default_factory=dict)

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


def _safe_closes(df) -> np.ndarray | None:
    if df is None or getattr(df, "empty", True):
        return None
    col = "Close" if "Close" in df.columns else "close"
    if col not in df.columns:
        return None
    c = df[col].astype(float).values
    if len(c) < 40:
        return None
    return np.asarray(c, dtype=float)


def _safe_volume(df) -> np.ndarray | None:
    for col in ("Volume", "volume"):
        if col in df.columns:
            v = df[col].astype(float).values
            if len(v) >= 40:
                return np.asarray(v, dtype=float)
    return None


def _bars_symbol(symbol: str) -> str:
    s = str(symbol or "").strip().upper().lstrip("$")
    try:
        from crypto_universe import is_crypto_symbol, yahoo_symbol

        if is_crypto_symbol(s):
            return yahoo_symbol(s)
    except Exception:
        pass
    return s


def _fetch_bars(symbol: str, period: str = "1y"):
    sym = _bars_symbol(symbol)
    try:
        from data_platform.market_prices import fetch_period

        df = fetch_period(sym, period=period, interval="1d")
        if df is not None and not df.empty:
            return df
    except Exception:
        pass
    try:
        import yfinance as yf

        df = yf.download(
            sym,
            period=period,
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if df is None or df.empty:
            return None
        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        return df
    except Exception:
        return None


def _market_closes(period: str = "1y") -> np.ndarray | None:
    bench = os.getenv("HIDDEN_ANOMALY_BENCH", "SPY")
    df = _fetch_bars(bench, period=period)
    return _safe_closes(df)


def _residual_anomaly(rets: np.ndarray, mkt: np.ndarray | None) -> tuple[float, int, str, float]:
    """Idiosyncratic z vs rolling beta — hidden when raw return looks ordinary."""
    if mkt is None or len(mkt) < len(rets):
        # Fall back to own-return z
        window = rets[-60:] if len(rets) >= 60 else rets
        z = _z(float(rets[-1]), float(np.mean(window[:-1])), float(np.std(window[:-1]) + 1e-12))
        strength = min(1.0, abs(z) / 3.0)
        return strength, (1 if z > 0 else -1 if z < 0 else 0), f"return_z={z:.2f}", z

    n = min(len(rets), len(mkt))
    r = rets[-n:]
    m = mkt[-n:]
    # Align by truncating from the front if needed
    look = min(90, n - 5)
    if look < 30:
        return 0.0, 0, "", 0.0
    rr, mm = r[-look:], m[-look:]
    # Simple OLS beta on prior window, residual on last day
    x = mm[:-1] - np.mean(mm[:-1])
    y = rr[:-1] - np.mean(rr[:-1])
    denom = float(np.dot(x, x)) + 1e-12
    beta = float(np.dot(x, y) / denom)
    resid = float(rr[-1] - beta * mm[-1])
    prior = rr[:-1] - beta * mm[:-1]
    z = _z(resid, float(np.mean(prior)), float(np.std(prior) + 1e-12))
    strength = min(1.0, abs(z) / 3.2)
    return strength, (1 if z > 0 else -1 if z < 0 else 0), f"idio_z={z:.2f} beta={beta:.2f}", z


def _vol_divergence(rets: np.ndarray, vol: np.ndarray | None) -> tuple[float, int, str]:
    if vol is None or len(vol) < 30:
        return 0.0, 0, ""
    n = min(len(rets), len(vol))
    r, v = rets[-n:], vol[-n:]
    rv = v[-20:]
    vz = _z(float(v[-1]), float(np.mean(rv[:-1])), float(np.std(rv[:-1]) + 1e-12))
    rz = _z(float(r[-1]), float(np.mean(r[-60:-1])), float(np.std(r[-60:-1]) + 1e-12))
    # High volume + muted return, or low volume + huge return
    div = abs(vz) - abs(rz)
    if abs(vz) < 1.5:
        return 0.0, 0, ""
    strength = min(1.0, max(0.0, (abs(vz) - abs(rz)) / 3.0))
    if strength < 0.25:
        # Also flag quiet-volume blow-off
        if abs(rz) > 2.0 and abs(vz) < 0.5:
            strength = min(1.0, abs(rz) / 3.5)
            return strength, (1 if rz > 0 else -1), f"quiet_vol_move rz={rz:.2f} vz={vz:.2f}"
        return 0.0, 0, ""
    direction = 1 if rz > 0 else -1 if rz < 0 else 0
    return strength, direction, f"vol_div vz={vz:.2f} rz={rz:.2f} gap={div:.2f}"


def _regime_break(rets: np.ndarray) -> tuple[float, int, str]:
    if len(rets) < 50:
        return 0.0, 0, ""
    short = rets[-10:]
    long = rets[-50:-10]
    # Autocorr lag-1 regime
    def ac1(x: np.ndarray) -> float:
        if len(x) < 5:
            return 0.0
        a, b = x[:-1], x[1:]
        if float(np.std(a)) < 1e-12 or float(np.std(b)) < 1e-12:
            return 0.0
        return float(np.corrcoef(a, b)[0, 1])

    ac_s, ac_l = ac1(short), ac1(long)
    vol_s, vol_l = float(np.std(short)), float(np.std(long) + 1e-12)
    vol_ratio = vol_s / vol_l
    ac_jump = abs(ac_s - ac_l)
    strength = 0.0
    reasons = []
    if ac_jump > 0.45:
        strength = max(strength, min(1.0, ac_jump))
        reasons.append(f"ac1_break {ac_l:.2f}→{ac_s:.2f}")
    if vol_ratio > 2.2 or vol_ratio < 0.35:
        strength = max(strength, min(1.0, abs(math.log(vol_ratio)) / 1.5))
        reasons.append(f"vol_regime×{vol_ratio:.2f}")
    direction = 1 if float(np.mean(short)) > 0 else -1
    return strength, direction, "; ".join(reasons)


def _isolation_score(rets: np.ndarray, vol: np.ndarray | None) -> tuple[float, str]:
    """Multivariate outlier on recent feature row vs history (vector feature build)."""
    n = len(rets)
    if n < 60:
        return 0.0, ""
    try:
        from analytics.vector_math import isolation_feature_matrix

        X = isolation_feature_matrix(rets, vol, win=20)
    except Exception:
        X = np.zeros((0, 6), dtype=float)
    if X.shape[0] < 20:
        # fallback scalar build
        rows = []
        for i in range(40, n):
            window = rets[i - 20 : i]
            feat = [
                float(rets[i - 1]),
                float(np.mean(window)),
                float(np.std(window) + 1e-12),
                float(np.sum(window)),
                float(np.max(window) - np.min(window)),
            ]
            if vol is not None and len(vol) >= i:
                vw = vol[i - 20 : i]
                feat.append(float(vol[i - 1]) / (float(np.mean(vw)) + 1e-12))
            else:
                feat.append(1.0)
            rows.append(feat)
        X = np.asarray(rows, dtype=float)
    if X.shape[0] < 2:
        return 0.0, ""
    last = X[-1:]
    hist = X[:-1]
    try:
        from sklearn.ensemble import IsolationForest

        clf = IsolationForest(
            n_estimators=80,
            contamination=float(os.getenv("HIDDEN_ANOMALY_CONTAM", "0.05")),
            random_state=42,
        )
        clf.fit(hist)
        # decision_function: higher = more normal; negate → anomaly score
        raw = float(-clf.decision_function(last)[0])
        # Map roughly to 0..1
        strength = min(1.0, max(0.0, (raw + 0.05) / 0.35))
        return strength, f"iforest={raw:.3f}"
    except Exception:
        # Mahalanobis-ish fallback
        mu = hist.mean(axis=0)
        std = hist.std(axis=0) + 1e-12
        z = (last[0] - mu) / std
        d = float(np.sqrt(np.mean(z * z)))
        strength = min(1.0, max(0.0, (d - 1.5) / 2.5))
        return strength, f"mahal_z={d:.2f}"


def _sequence_divergence(closes: np.ndarray) -> tuple[float, int, str]:
    if not _b("USE_SEQUENCE_DISCOVER", True) or len(closes) < 15:
        return 0.0, 0, ""
    try:
        from analytics.sequence_discover import search_pattern

        rets = np.diff(closes[-16:]) / np.maximum(closes[-16:-1], 1e-12)
        seq = [float(r * 100.0) for r in rets]
        # Prefer learned sequence family weights when present
        fam_w = None
        try:
            from analytics.hidden_pattern_learn import _load_json, WEIGHTS_PATH

            fam_w = (_load_json(WEIGHTS_PATH).get("seq_family_weights") or None)
        except Exception:
            fam_w = None
        hit = search_pattern(seq, family_weights=fam_w)
        if hit is None or not math.isfinite(hit.next_val):
            return 0.0, 0, ""
        last = float(seq[-1])
        # Divergence: predicted next opposes or dwarfs recent move
        if abs(hit.next_val) < 0.08:
            return 0.0, 0, ""
        agree = (hit.next_val > 0 and last > 0) or (hit.next_val < 0 and last < 0)
        gap = abs(hit.next_val) - abs(last)
        if agree and gap < 0.15:
            return 0.0, 0, ""
        strength = min(1.0, 0.35 + abs(hit.next_val) / 4.0 + (0.2 if not agree else 0.0))
        direction = 1 if hit.next_val > 0 else -1
        return (
            strength,
            direction,
            f"seq:{hit.best.family} next={hit.next_val:+.3f}% last={last:+.3f}%",
        )
    except Exception:
        return 0.0, 0, ""


def _motif_echo(rets: np.ndarray) -> tuple[float, int, str]:
    """Nearest historical return-shape motif via vectorized cosine (top-k soft fwd)."""
    if not _b("USE_HIDDEN_MOTIF_SEARCH", True) or len(rets) < 80:
        return 0.0, 0, ""
    w = int(_f("HIDDEN_MOTIF_LEN", 8))
    if len(rets) < w * 6:
        return 0.0, 0, ""
    min_sim = _f("HIDDEN_MOTIF_MIN_SIM", 0.72)
    try:
        from analytics.vector_math import sliding_cosine_motifs

        best_sim, pw_fwd, best_fwd = sliding_cosine_motifs(
            rets,
            w=w,
            min_sim=min_sim,
            top_k=int(os.getenv("HIDDEN_MOTIF_TOP_K", "5")),
        )
        fwd_use = pw_fwd if abs(pw_fwd) > 1e-12 else best_fwd
    except Exception:
        # scalar fallback
        query = rets[-w:]
        qn = query - np.mean(query)
        qnorm = float(np.linalg.norm(qn) + 1e-12)
        best_sim = -1.0
        best_fwd = 0.0
        end = len(rets) - 2 * w
        step = max(1, w // 2)
        for i in range(0, end, step):
            win = rets[i : i + w]
            wn = win - np.mean(win)
            sim = float(np.dot(qn, wn) / (qnorm * (float(np.linalg.norm(wn)) + 1e-12)))
            if sim > best_sim:
                best_sim = sim
                fwd = rets[i + w : i + w + w]
                best_fwd = float(np.sum(fwd)) if len(fwd) == w else 0.0
        fwd_use = best_fwd
    if best_sim < min_sim:
        return 0.0, 0, ""
    strength = min(1.0, (best_sim - 0.5) / 0.5 * 0.55 + min(0.45, abs(fwd_use) * 8.0))
    if strength < 0.28:
        return 0.0, 0, ""
    direction = 1 if fwd_use > 0 else -1 if fwd_use < 0 else 0
    return strength, direction, f"motif sim={best_sim:.2f} fwd={fwd_use:+.3f}"


def _entropy_break(rets: np.ndarray) -> tuple[float, int, str]:
    """Shannon entropy of signed-return bins — complexity regime shift is often invisible on charts."""
    if not _b("USE_HIDDEN_ENTROPY", True) or len(rets) < 60:
        return 0.0, 0, ""

    def _H(x: np.ndarray) -> float:
        if len(x) < 8:
            return 0.0
        # 5 bins via percentiles of the long window
        qs = np.quantile(x, [0.2, 0.4, 0.6, 0.8])
        bins = np.digitize(x, qs)
        counts = np.bincount(bins, minlength=5).astype(float)
        p = counts / (counts.sum() + 1e-12)
        p = p[p > 0]
        return float(-np.sum(p * np.log(p + 1e-12)))

    long = rets[-60:-15]
    short = rets[-15:]
    h_l, h_s = _H(long), _H(short)
    if h_l < 1e-9:
        return 0.0, 0, ""
    ratio = h_s / (h_l + 1e-12)
    # Collapse (ratio<<1) or explosion (ratio>>1) of return complexity
    if 0.55 < ratio < 1.75:
        return 0.0, 0, ""
    strength = min(1.0, abs(math.log(max(ratio, 1e-6))) / 1.2)
    direction = 1 if float(np.mean(short)) > 0 else -1
    return strength, direction, f"entropy {h_l:.2f}→{h_s:.2f}×{ratio:.2f}"


def _corr_flip(rets: np.ndarray, mkt: np.ndarray | None) -> tuple[float, int, str]:
    """Rolling correlation flip vs market — hidden lead/lag regime change."""
    if mkt is None or len(mkt) < 40 or len(rets) < 40:
        return 0.0, 0, ""
    if not _b("USE_HIDDEN_CORR_FLIP", True):
        return 0.0, 0, ""
    n = min(len(rets), len(mkt))
    r, m = rets[-n:], mkt[-n:]
    if n < 40:
        return 0.0, 0, ""

    def _corr(a: np.ndarray, b: np.ndarray) -> float:
        if len(a) < 8 or float(np.std(a)) < 1e-12 or float(np.std(b)) < 1e-12:
            return 0.0
        return float(np.corrcoef(a, b)[0, 1])

    c_long = _corr(r[-40:-10], m[-40:-10])
    c_short = _corr(r[-10:], m[-10:])
    jump = c_short - c_long
    if abs(jump) < 0.55:
        return 0.0, 0, ""
    strength = min(1.0, abs(jump) / 1.2)
    # If correlation flips negative while stock rises → idiosyncratic bullish; etc.
    direction = 1 if float(np.mean(r[-5:])) > 0 else -1
    return strength, direction, f"corr_flip {c_long:.2f}→{c_short:.2f}"


def analyze_symbol(
    symbol: str,
    *,
    df=None,
    market_rets: np.ndarray | None = None,
) -> AnomalyHit | None:
    """Score one symbol; return None if no meaningful hidden anomaly."""
    sym = symbol.strip().upper()
    if df is None:
        df = _fetch_bars(sym)
    closes = _safe_closes(df)
    if closes is None:
        return None
    vol = _safe_volume(df)
    rets = np.diff(closes) / np.maximum(closes[:-1], 1e-12)
    if len(rets) < 40:
        return None

    # Learned per-family multipliers (auto-adjust from trade outcomes)
    try:
        from analytics.hidden_pattern_learn import load_detector_weights, weighted_detector_strength

        dw = load_detector_weights()
    except Exception:
        dw = {}
        weighted_detector_strength = lambda fam, s, weights=None: float(s)  # noqa: E731

    strengths: list[float] = []
    reasons: list[str] = []
    dirs: list[int] = []
    detectors: list[str] = []
    feats: dict[str, float] = {
        "last_ret": float(rets[-1]),
        "vol20": float(np.std(rets[-20:])),
    }

    s, d, reason, z = _residual_anomaly(rets, market_rets)
    s = weighted_detector_strength("idio", s, dw)
    if s >= 0.28:
        strengths.append(s)
        dirs.append(d)
        reasons.append(reason)
        detectors.append("idio")
        feats["idio_z"] = float(z)

    s, d, reason = _vol_divergence(rets, vol)
    s = weighted_detector_strength("vol_div", s * 0.9, dw)
    if s >= 0.28:
        strengths.append(s)
        dirs.append(d)
        reasons.append(reason)
        detectors.append("vol_div")

    s, d, reason = _regime_break(rets)
    s = weighted_detector_strength("regime", s * 0.85, dw)
    if s >= 0.3:
        strengths.append(s)
        dirs.append(d)
        reasons.append(reason)
        detectors.append("regime")

    s, reason = _isolation_score(rets, vol)
    s = weighted_detector_strength("iforest", s, dw)
    if s >= 0.35:
        strengths.append(s)
        reasons.append(reason)
        detectors.append("iforest")
        dirs.append(1 if rets[-1] > 0 else -1)

    s, d, reason = _sequence_divergence(closes)
    s = weighted_detector_strength("seq", s * 0.8, dw)
    if s >= 0.35:
        strengths.append(s)
        dirs.append(d)
        reasons.append(reason)
        detectors.append("seq")

    s, d, reason = _motif_echo(rets)
    s = weighted_detector_strength("motif", s, dw)
    if s >= 0.28:
        strengths.append(s)
        dirs.append(d)
        reasons.append(reason)
        detectors.append("motif")
        feats["motif_strength"] = float(s)

    s, d, reason = _entropy_break(rets)
    s = weighted_detector_strength("entropy", s, dw)
    if s >= 0.3:
        strengths.append(s)
        dirs.append(d)
        reasons.append(reason)
        detectors.append("entropy")

    s, d, reason = _corr_flip(rets, market_rets)
    s = weighted_detector_strength("corr_flip", s, dw)
    if s >= 0.3:
        strengths.append(s)
        dirs.append(d)
        reasons.append(reason)
        detectors.append("corr_flip")

    # Auto-written subtle-tie detectors (cross-company residual / vol echoes)
    if _b("USE_GENERATED_PATTERNS", True):
        try:
            from analytics.generated_patterns import detectors_for_symbol

            _rets_cache: dict[str, np.ndarray | None] = {sym: rets}
            _vol_cache: dict[str, np.ndarray | None] = {sym: vol}

            def _get_rets(s: str):
                u = s.strip().upper()
                if u in _rets_cache:
                    return _rets_cache[u]
                df_p = _fetch_bars(u)
                c = _safe_closes(df_p)
                if c is None or len(c) < 40:
                    _rets_cache[u] = None
                    return None
                rr = np.diff(c) / np.maximum(c[:-1], 1e-12)
                _rets_cache[u] = rr
                return rr

            def _get_vol(s: str):
                u = s.strip().upper()
                if u in _vol_cache:
                    return _vol_cache[u]
                df_p = _fetch_bars(u)
                vv = _safe_volume(df_p)
                if vv is None:
                    _vol_cache[u] = None
                    return None
                # volume surprise series aligned to returns length
                c = _safe_closes(df_p)
                if c is None:
                    _vol_cache[u] = None
                    return None
                rr_len = len(c) - 1
                v = vv[-rr_len:]
                try:
                    from analytics.vector_math import volume_surprise

                    vs = volume_surprise(v, win=20)
                    # early bars: rolling NaN → use point-relative fallback
                    bad = ~np.isfinite(vs)
                    if bad.any():
                        vs = vs.copy()
                        vs[bad] = 0.0
                except Exception:
                    vs = np.zeros(rr_len, dtype=float)
                    for i in range(rr_len):
                        lo = max(0, i - 20)
                        mu = float(np.mean(v[lo:i])) if i > lo else float(v[i])
                        vs[i] = float(v[i]) / (mu + 1e-12) - 1.0
                _vol_cache[u] = vs
                return vs

            ctx = {
                "symbol": sym,
                "np": np,
                "market_rets": market_rets,
                "get_rets": _get_rets,
                "get_vol": _get_vol,
            }
            for mod in detectors_for_symbol(sym):
                try:
                    out = mod.detect(ctx)
                    if not out or len(out) < 3:
                        continue
                    gs, gd, greason = float(out[0]), int(out[1]), str(out[2] or "")
                    gfeats = out[3] if len(out) > 3 and isinstance(out[3], dict) else {}
                    gs = weighted_detector_strength("gen", gs, dw)
                    if gs >= 0.28 and greason:
                        strengths.append(gs)
                        dirs.append(gd)
                        reasons.append(greason)
                        detectors.append("gen")
                        for fk, fv in list(gfeats.items())[:4]:
                            feats[f"gen_{fk}"] = float(fv)
                except Exception:
                    continue
        except Exception:
            pass

    if not strengths:
        return None

    score = float(min(1.0, max(strengths) * 0.65 + float(np.mean(strengths)) * 0.35))
    min_score = _f("HIDDEN_ANOMALY_MIN_SCORE", 0.42)
    if score < min_score:
        return None

    # Vote direction by strength-weighted signs
    if dirs:
        wdir = sum(dirs)
        direction = 1 if wdir > 0 else -1 if wdir < 0 else 0
    else:
        direction = 0

    hit = AnomalyHit(symbol=sym, score=score, direction=direction, reasons=reasons[:8], features=feats)
    # Stash detector tags for learning (to_dict via features + reasons already covers most)
    hit.features["n_detectors"] = float(len(detectors))
    # Encode detectors list into features keys for persistence without schema change
    for i, fam in enumerate(detectors[:8]):
        hit.features[f"det_{i}_{fam}"] = 1.0
    return hit


def scan_universe(
    symbols: list[str],
    *,
    limit: int | None = None,
    period: str = "1y",
) -> list[AnomalyHit]:
    """Scan tickers; return hits sorted by score desc."""
    if not _b("USE_HIDDEN_PATTERN_ANOMALY", True):
        return []
    lim = limit if limit is not None else int(_f("HIDDEN_ANOMALY_SCAN_LIMIT", 80))
    tickers = [s.strip().upper() for s in symbols if s and str(s).strip()][:lim]
    mkt_closes = _market_closes(period=period)
    mkt_rets = None
    if mkt_closes is not None and len(mkt_closes) > 40:
        mkt_rets = np.diff(mkt_closes) / np.maximum(mkt_closes[:-1], 1e-12)

    hits: list[AnomalyHit] = []
    for sym in tickers:
        try:
            hit = analyze_symbol(sym, market_rets=mkt_rets)
            if hit is not None:
                hits.append(hit)
        except Exception:
            continue
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits


def default_universe(limit: int = 80) -> list[str]:
    """Prefer live book + quality/top lists; fall back to liquid megacaps."""
    out: list[str] = []
    try:
        from alpaca_broker import list_positions

        for p in list_positions():
            s = str(p.get("symbol") or "").upper()
            if s:
                out.append(s)
    except Exception:
        pass
    for path in (
        ROOT / "data" / "hft_quality_tickers.txt",
        ROOT / "data" / "top100_tickers.txt",
        ROOT / "data" / "fortress_priority.txt",
    ):
        if path.is_file():
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    s = line.strip().upper().split()[0] if line.strip() else ""
                    if s and s.replace(".", "").isalnum() and len(s) <= 6:
                        out.append(s)
            except Exception:
                pass
    if not out:
        out = [
            "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD",
            "JPM", "XOM", "UNH", "LLY", "AVGO", "COST", "CRM", "NFLX",
            "SPY", "QQQ", "IWM", "DIA",
        ]
    # de-dupe preserve order
    seen: set[str] = set()
    uniq = []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq[:limit]


def save_hits(hits: list[AnomalyHit], path: Path | None = None) -> Path:
    p = path or OUT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "count": len(hits),
        "hits": [h.to_dict() for h in hits],
        "by_symbol": {h.symbol: h.to_dict() for h in hits},
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


def load_hits(path: Path | None = None) -> dict[str, Any]:
    p = path or OUT_PATH
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def hidden_anomaly_rank_boost(symbol: str) -> tuple[float, dict[str, Any]]:
    """Small fortress/rank boost from latest scan cache (no live fetch)."""
    if not _b("USE_HIDDEN_PATTERN_ANOMALY", True):
        return 0.0, {"enabled": False}
    doc = load_hits()
    age = time.time() - float(doc.get("ts") or 0)
    max_age = _f("HIDDEN_ANOMALY_MAX_AGE_SEC", 7200)
    boost = 0.0
    meta: dict[str, Any] = {"hit": False}
    if age <= max_age:
        row = (doc.get("by_symbol") or {}).get(symbol.strip().upper())
        if row:
            score = float(row.get("score") or 0)
            direction = int(row.get("direction") or 0)
            w = _f("RANK_W_HIDDEN_ANOMALY", 0.10)
            try:
                from analytics.hidden_pattern_learn import blend_scale

                w *= float(blend_scale())
            except Exception:
                pass
            boost = w * score * (1.0 if direction >= 0 else -0.6)
            meta = {
                "hit": True,
                "score": score,
                "direction": direction,
                "reasons": list(row.get("reasons") or [])[:4],
                "boost": boost,
            }
    # Cross-region / dual-listing imbalance (same company, different venue price)
    try:
        from analytics.market_imbalance import imbalance_rank_boost

        ib, im = imbalance_rank_boost(symbol)
        if ib:
            boost = float(boost) + float(ib)
            meta["imbalance"] = im
            meta["boost"] = boost
            meta["hit"] = True
    except Exception:
        pass
    return float(boost), meta


def hidden_pattern_p_blend(symbol: str, p_up: float) -> tuple[float, dict[str, Any]]:
    """Re-export: soft-blend hidden pattern into final p_up."""
    from analytics.hidden_pattern_learn import hidden_pattern_p_blend as _blend

    return _blend(symbol, p_up)


def run_scan_cycle(*, limit: int | None = None) -> dict[str, Any]:
    lim = limit if limit is not None else int(_f("HIDDEN_ANOMALY_SCAN_LIMIT", 80))

    # Keep discovering subtle ties and writing new detector code (never deletes old)
    codegen_summary: dict[str, Any] = {}
    if _b("USE_PATTERN_CODE_EVOLVER", True):
        try:
            from analytics.pattern_code_evolver import discover_and_emit

            codegen_summary = discover_and_emit()
        except Exception as e:
            codegen_summary = {"error": str(e)[:160]}

    universe = default_universe(lim)
    hits = scan_universe(universe, limit=lim)

    imbalance_summary: dict[str, Any] = {}
    try:
        from analytics.market_imbalance import run_imbalance_cycle

        imbalance_summary = run_imbalance_cycle()
        # Merge cross-listing imbalances into anomaly hits (same cache fortress reads)
        from analytics.market_imbalance import load_imbalances

        imb = load_imbalances()
        by = {h.symbol: h for h in hits}
        for row in imb.get("hits") or []:
            sym = str(row.get("symbol") or "").upper()
            if not sym:
                continue
            score = float(row.get("score") or 0)
            direction = int(row.get("direction") or 0)
            reasons = [f"imbalance:{r}" for r in (row.get("reasons") or [])[:3]]
            existing = by.get(sym)
            if existing is None:
                by[sym] = AnomalyHit(
                    symbol=sym,
                    score=score,
                    direction=direction,
                    reasons=reasons,
                    features={
                        "gap_pct": float(row.get("gap_pct") or 0),
                        "z": float(row.get("z") or 0),
                    },
                )
            else:
                # Blend — keep stronger score, append imbalance reasons
                existing.score = max(existing.score, score)
                if abs(direction) >= abs(existing.direction):
                    existing.direction = direction
                existing.reasons = list(dict.fromkeys((existing.reasons or []) + reasons))[:6]
                existing.features["gap_pct"] = float(row.get("gap_pct") or 0)
                existing.features["imb_z"] = float(row.get("z") or 0)
        hits = sorted(by.values(), key=lambda h: h.score, reverse=True)
    except Exception:
        pass

    cross_summary: dict[str, Any] = {}
    try:
        from analytics.cross_company_links import run_scan_cycle as cross_scan

        cross_summary = cross_scan(limit=min(lim, int(_f("CROSS_LINK_SCAN_LIMIT", 40))))
        # Surface strongest cross-link as anomaly reasons (fortress already has dedicated boost)
        from analytics.cross_company_links import load_hits as load_cross

        cx = load_cross()
        by = {h.symbol: h for h in hits}
        for row in cx.get("hits") or []:
            sym = str(row.get("symbol") or "").upper()
            if not sym:
                continue
            score = float(row.get("score") or 0) * 0.85
            direction = int(row.get("direction") or 0)
            reasons = [f"cross:{r}" for r in (row.get("reasons") or [])[:3]]
            existing = by.get(sym)
            if existing is None:
                by[sym] = AnomalyHit(
                    symbol=sym,
                    score=score,
                    direction=direction,
                    reasons=reasons,
                    features=dict(row.get("metrics") or {}),
                )
            else:
                existing.score = max(existing.score, score)
                if abs(direction) >= abs(existing.direction):
                    existing.direction = direction
                existing.reasons = list(dict.fromkeys((existing.reasons or []) + reasons))[:6]
        hits = sorted(by.values(), key=lambda h: h.score, reverse=True)
        cross_summary = {"cross_company_hits": int(cross_summary.get("hits") or 0)}
    except Exception:
        cross_summary = {}

    path = save_hits(hits)
    return {
        "scanned": len(universe),
        "hits": len(hits),
        "path": str(path),
        "top": [h.to_dict() for h in hits[:12]],
        "codegen": codegen_summary,
        **imbalance_summary,
        **cross_summary,
    }
