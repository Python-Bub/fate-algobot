"""Vector evidence algebra — precise, SIMD-friendly probability/signal math.

**LogitEvidence Algebra (LEA)** — project-standard fusion:
  evidence lives in log-odds; weights act on evidence, not on raw probabilities.

  ℓ = logit(p) = log(p / (1 − p))
  ℓ_fuse = Σ_i w_i · ℓ_i          (or log-sum-exp of {ℓ_i + log w_i})
  p_fuse = σ(ℓ_fuse)

Also: sliding-window cosine motifs, cumsum rolling stats, batch polarity.
No fake physics — just stable vectorized numerics.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Iterable, Sequence

import numpy as np

_EPS = 1e-9
_LOGIT_CLIP = 20.0  # |logit| soft-cap ≈ σ⁻¹ near 0/1


def _b(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def clip_prob(p: float | np.ndarray, eps: float = _EPS) -> float | np.ndarray:
    """Keep probabilities in (eps, 1−eps) for stable logits."""
    return np.clip(p, eps, 1.0 - eps)


def logit(p: float | np.ndarray, eps: float = _EPS) -> float | np.ndarray:
    """Log-odds: log(p/(1−p)), clipped for float stability."""
    x = clip_prob(np.asarray(p, dtype=np.float64), eps)
    out = np.log(x) - np.log1p(-x)
    return np.clip(out, -_LOGIT_CLIP, _LOGIT_CLIP)


def sigmoid(z: float | np.ndarray) -> float | np.ndarray:
    """σ(z) = 1/(1+e^{−z}) via tanh for better float behavior."""
    z = np.asarray(z, dtype=np.float64)
    z = np.clip(z, -_LOGIT_CLIP, _LOGIT_CLIP)
    return 0.5 * (1.0 + np.tanh(0.5 * z))


def logit_blend(
    probs: Sequence[float] | np.ndarray,
    weights: Sequence[float] | np.ndarray | None = None,
    *,
    eps: float = _EPS,
) -> float:
    """Weighted mean in log-odds space → sigmoid (LEA soft blend).

    Prefer this over Σ w_i p_i: near 0/1, linear p-mix under/over-states evidence.
    """
    p = np.asarray(probs, dtype=np.float64).ravel()
    if p.size == 0:
        return 0.5
    if weights is None:
        w = np.ones(p.size, dtype=np.float64)
    else:
        w = np.asarray(weights, dtype=np.float64).ravel()
        if w.size != p.size:
            w = np.resize(w, p.size)
    w = np.maximum(w, 0.0)
    s = float(w.sum())
    if s <= 0:
        return float(np.mean(clip_prob(p, eps)))
    w = w / s
    ell = logit(p, eps)
    return float(sigmoid(np.dot(w, ell)))


def logit_pair_blend(p0: float, p1: float, w1: float, *, eps: float = _EPS) -> float:
    """Two-source LEA blend: (1−w)·ℓ₀ + w·ℓ₁ → σ."""
    w = float(max(0.0, min(1.0, w1)))
    return logit_blend([p0, p1], [1.0 - w, w], eps=eps)


def logsumexp_fuse(
    probs: Sequence[float] | np.ndarray,
    weights: Sequence[float] | np.ndarray | None = None,
    *,
    eps: float = _EPS,
) -> float:
    """Log-sum-exp evidence pool: σ( LSE(ℓ_i + log w_i) − LSE(log w_i) ).

    Emphasizes strong agreeing signals more than plain logit mean (still real math).
    """
    p = np.asarray(probs, dtype=np.float64).ravel()
    if p.size == 0:
        return 0.5
    if weights is None:
        w = np.ones(p.size, dtype=np.float64)
    else:
        w = np.maximum(np.asarray(weights, dtype=np.float64).ravel(), _EPS)
        if w.size != p.size:
            w = np.resize(w, p.size)
    ell = logit(p, eps)
    log_w = np.log(w)
    # numerically stable LSE
    a = ell + log_w
    m = float(np.max(a))
    lse_a = m + float(np.log(np.sum(np.exp(a - m))))
    mw = float(np.max(log_w))
    lse_w = mw + float(np.log(np.sum(np.exp(log_w - mw))))
    return float(sigmoid(lse_a - lse_w))


def fuse_probs(
    probs: Sequence[float] | np.ndarray,
    weights: Sequence[float] | np.ndarray | None = None,
    *,
    mode: str | None = None,
) -> float:
    """Dispatch LEA fusion. mode: logit (default) | lse | linear | precision."""
    mode = (mode or os.getenv("VECTOR_MATH_FUSE", "logit")).strip().lower()
    if mode in ("lse", "logsumexp", "pool"):
        return logsumexp_fuse(probs, weights)
    if mode in ("precision", "iv", "bates", "grinold"):
        return precision_fuse(probs, skills=weights)
    if mode in ("linear", "arith", "p"):
        p = np.asarray(probs, dtype=np.float64).ravel()
        if weights is None:
            return float(np.mean(clip_prob(p)))
        w = np.asarray(weights, dtype=np.float64).ravel()
        w = np.maximum(w, 0.0)
        s = float(w.sum()) or 1.0
        return float(np.clip(np.dot(w / s, clip_prob(p)), 0.0, 1.0))
    return logit_blend(probs, weights)


def normalize_weights(
    weights: Sequence[float] | np.ndarray,
    *,
    clip_negative: bool = True,
) -> np.ndarray:
    """L1-normalize to a convex combination. Empty/zero → empty array.

    Bates–Granger / Grinold: combining weights must sum to 1 so a loud knob
    cannot dominate by having a raw scale of 0.85 vs 0.10.
    """
    w = np.asarray(weights, dtype=np.float64).ravel()
    if w.size == 0:
        return w
    if clip_negative:
        w = np.maximum(w, 0.0)
    s = float(np.sum(np.abs(w)))
    if s <= 0:
        return np.zeros_like(w)
    return w / s


def precision_weights(
    *,
    variances: Sequence[float] | np.ndarray | None = None,
    skills: Sequence[float] | np.ndarray | None = None,
    n: int | None = None,
) -> np.ndarray:
    """Inverse-variance (Bates & Granger 1969) × skill (Grinold IC).

    w_i ∝ skill_i / σ_i² . Missing variance → equal precision. Missing skill → 1.
    """
    if variances is not None:
        var = np.maximum(np.asarray(variances, dtype=np.float64).ravel(), _EPS)
        n = int(var.size)
    elif skills is not None:
        n = int(np.asarray(skills, dtype=np.float64).ravel().size)
        var = np.ones(n, dtype=np.float64)
    else:
        n = int(n or 0)
        var = np.ones(max(n, 0), dtype=np.float64)
    if n <= 0:
        return np.zeros(0, dtype=np.float64)
    if skills is None:
        sk = np.ones(n, dtype=np.float64)
    else:
        sk = np.maximum(np.asarray(skills, dtype=np.float64).ravel(), 0.0)
        if sk.size != n:
            sk = np.resize(sk, n)
    raw = sk / var
    return normalize_weights(raw, clip_negative=True)


def precision_fuse(
    probs: Sequence[float] | np.ndarray,
    *,
    variances: Sequence[float] | np.ndarray | None = None,
    skills: Sequence[float] | np.ndarray | None = None,
    eps: float = _EPS,
) -> float:
    """Precision-weighted logit fuse. Disagreeing noisy heads shrink toward 0.5."""
    p = np.asarray(probs, dtype=np.float64).ravel()
    if p.size == 0:
        return 0.5
    w = precision_weights(variances=variances, skills=skills, n=int(p.size))
    if w.size != p.size:
        w = np.resize(w, p.size)
    return logit_blend(p, w, eps=eps)


def l1_weighted_sum(
    scores: Sequence[float] | np.ndarray,
    weights: Sequence[float] | np.ndarray,
) -> float:
    """Convex combination of factor scores (normalized |w|)."""
    x = np.asarray(scores, dtype=np.float64).ravel()
    w = normalize_weights(weights, clip_negative=True)
    if x.size == 0 or w.size == 0:
        return 0.0
    if w.size != x.size:
        w = np.resize(w, x.size)
    finite = np.isfinite(x) & np.isfinite(w)
    if not bool(np.any(finite)):
        return 0.0
    ww = normalize_weights(w[finite], clip_negative=True)
    return float(np.dot(ww, x[finite]))


def signed_agreement(
    p_short: float,
    p_long: float,
    p_ref: float,
) -> float:
    """How much both horizon heads back *p_ref*'s direction, in [0, 1].

    Independent heads required — identical copies of p_ref are *not* agreement.
    """
    ref = float(clip_prob(p_ref))
    ps = float(clip_prob(p_short))
    pl = float(clip_prob(p_long))
    direction = 1.0 if ref >= 0.5 else -1.0
    su = (ps - 0.5) * 2.0 * direction
    lu = (pl - 0.5) * 2.0 * direction
    return float(np.clip(min(su, lu), 0.0, 1.0))


def heads_are_independent(p_short: float, p_long: float, p_ref: float, *, eps: float = 1e-6) -> bool:
    """True when short/long are not just copies of the fused p (fake agreement)."""
    return not (
        abs(float(p_short) - float(p_ref)) < eps and abs(float(p_long) - float(p_ref)) < eps
    )


def logit_std(probs: Sequence[float] | np.ndarray) -> float:
    """Std of log-odds — high when heads disagree on strength/direction."""
    p = np.asarray(probs, dtype=np.float64).ravel()
    if p.size < 2:
        return 0.0
    ell = logit(p)
    return float(np.std(ell))


def factor_to_prob(x: float, *, scale: float = 1.0) -> float:
    """Map unbounded factor → probability via tanh: 0.5 + 0.5·tanh(scale·x)."""
    return float(0.5 + 0.5 * np.tanh(float(scale) * float(x)))


def apply_logit_tilt(p: float, delta_ell: float) -> float:
    """Add evidence in log-odds: p' = σ(logit(p) + Δℓ)."""
    return float(sigmoid(float(logit(p)) + float(delta_ell)))


def delta_p_to_delta_ell(p: float, delta_p: float) -> float:
    """Convert legacy additive Δp at operating point p into Δℓ (exact via logit)."""
    p0 = float(clip_prob(p))
    p1 = float(clip_prob(p0 + float(delta_p)))
    return float(logit(p1) - logit(p0))


def z_to_delta_ell(z: float, *, scale: float = 0.35) -> float:
    """Map a z-score / factor into a bounded log-odds nudge: Δℓ = scale · tanh(z)."""
    return float(scale) * float(np.tanh(float(z)))


# ─── Rolling / sliding vector ops ───────────────────────────────────────────


def rolling_mean(x: np.ndarray, win: int) -> np.ndarray:
    """O(n) rolling mean via cumsum (NaN for first win−1)."""
    x = np.asarray(x, dtype=np.float64).ravel()
    n = x.size
    out = np.full(n, np.nan, dtype=np.float64)
    if win <= 0 or n < win:
        return out
    c = np.cumsum(x)
    out[win - 1 :] = (c[win - 1 :] - np.concatenate(([0.0], c[:-win]))) / float(win)
    return out


def rolling_std(x: np.ndarray, win: int, eps: float = 1e-12) -> np.ndarray:
    """O(n) rolling std via cumsum of x and x²."""
    x = np.asarray(x, dtype=np.float64).ravel()
    n = x.size
    out = np.full(n, np.nan, dtype=np.float64)
    if win <= 0 or n < win:
        return out
    c1 = np.cumsum(x)
    c2 = np.cumsum(x * x)
    s1 = c1[win - 1 :] - np.concatenate(([0.0], c1[:-win]))
    s2 = c2[win - 1 :] - np.concatenate(([0.0], c2[:-win]))
    mean = s1 / float(win)
    var = np.maximum(s2 / float(win) - mean * mean, 0.0)
    out[win - 1 :] = np.sqrt(var + eps)
    return out


def volume_surprise(vol: np.ndarray, win: int = 20) -> np.ndarray:
    """v / rolling_mean(v) − 1, vectorized."""
    v = np.asarray(vol, dtype=np.float64).ravel()
    mu = rolling_mean(v, win)
    return np.where(np.isfinite(mu) & (mu > 0), v / (mu + 1e-12) - 1.0, 0.0)


def isolation_feature_matrix(rets: np.ndarray, vol: np.ndarray | None, win: int = 20) -> np.ndarray:
    """Vectorized feature rows for IsolationForest (same schema as scalar loop)."""
    r = np.asarray(rets, dtype=np.float64).ravel()
    n = r.size
    if n < win + 1:
        return np.zeros((0, 6), dtype=np.float64)
    mu = rolling_mean(r, win)
    sd = rolling_std(r, win)
    # rolling sum = win * mean
    rsum = mu * float(win)
    # rolling range via as_strided max-min
    from numpy.lib.stride_tricks import sliding_window_view

    windows = sliding_window_view(r, win)  # shape (n-win+1, win)
    rrange = windows.max(axis=1) - windows.min(axis=1)
    # Align to index i where window is rets[i-win:i] → row ends at i-1 in 0-index of windows
    # For i in [win, n): window = rets[i-win:i], last ret = rets[i-1]
    # windows[j] = rets[j:j+win], so for window ending at i-1: j = i-win
    start = win  # first usable i
    idxs = np.arange(start, n)
    j = idxs - win
    last_r = r[idxs - 1]
    feat_mu = mu[idxs - 1]
    feat_sd = sd[idxs - 1]
    feat_sum = rsum[idxs - 1]
    feat_rng = rrange[j]
    if vol is not None and len(vol) >= n:
        v = np.asarray(vol, dtype=np.float64).ravel()[:n]
        vmu = rolling_mean(v, win)
        v_ratio = np.where(
            np.isfinite(vmu[idxs - 1]) & (vmu[idxs - 1] > 0),
            v[idxs - 1] / (vmu[idxs - 1] + 1e-12),
            1.0,
        )
    else:
        v_ratio = np.ones(idxs.size, dtype=np.float64)
    return np.column_stack([last_r, feat_mu, feat_sd, feat_sum, feat_rng, v_ratio])


def sliding_cosine_motifs(
    rets: np.ndarray,
    *,
    w: int = 8,
    step: int | None = None,
    min_sim: float = 0.72,
    top_k: int = 5,
) -> tuple[float, float, float]:
    """Vectorized motif scan: return (best_sim, precision_weighted_fwd, best_fwd).

    Cosine on demeaned windows via matmul; top-k softens argmax noise.
    """
    r = np.asarray(rets, dtype=np.float64).ravel()
    if r.size < w * 6:
        return 0.0, 0.0, 0.0
    step = max(1, step if step is not None else w // 2)
    query = r[-w:]
    qn = query - query.mean()
    qnorm = float(np.linalg.norm(qn) + 1e-12)
    end = r.size - 2 * w
    if end <= 0:
        return 0.0, 0.0, 0.0
    starts = np.arange(0, end, step, dtype=np.int64)
    if starts.size == 0:
        return 0.0, 0.0, 0.0
    # Window matrix (m, w) — stepped sample, then one matmul for all cosines
    wins = np.stack([r[i : i + w] for i in starts], axis=0)
    wn = wins - wins.mean(axis=1, keepdims=True)
    norms = np.linalg.norm(wn, axis=1) + 1e-12
    sims = (wn @ qn) / (norms * qnorm)
    # forward path sum for each start
    fwds = np.array([float(np.sum(r[i + w : i + 2 * w])) for i in starts], dtype=np.float64)
    best_i = int(np.argmax(sims))
    best_sim = float(sims[best_i])
    best_fwd = float(fwds[best_i])
    if best_sim < min_sim:
        return best_sim, 0.0, best_fwd
    # precision-weighted forward: softmax over (sim − min_sim)_+
    k = min(top_k, sims.size)
    top = np.argpartition(sims, -k)[-k:]
    s_top = sims[top]
    f_top = fwds[top]
    soft = np.maximum(s_top - min_sim, 0.0)
    if float(soft.sum()) < 1e-12:
        pw = best_fwd
    else:
        # temperature softmax on similarity surplus
        z = soft / (float(np.std(soft)) + 1e-6)
        e = np.exp(z - z.max())
        pw = float(np.dot(e / e.sum(), f_top))
    return best_sim, pw, best_fwd


# ─── Batch text polarity (vector bag over fixed vocab) ───────────────────────


@lru_cache(maxsize=1)
def _lex_arrays() -> tuple[np.ndarray, np.ndarray]:
    try:
        from intel.english_lexicon import _load_expanded

        pos, neg = _load_expanded()
    except Exception:
        pos, neg = frozenset(), frozenset()
    return np.asarray(sorted(pos), dtype=object), np.asarray(sorted(neg), dtype=object)


def polarity_batch(texts: Iterable[str]) -> np.ndarray:
    """Vector of lexicon polarities for many headlines (one pass vocab isin)."""
    try:
        from intel.english_lexicon import tokenize
    except Exception:
        return np.zeros(0, dtype=np.float64)
    pos_arr, neg_arr = _lex_arrays()
    pos_set = set(pos_arr.tolist()) if pos_arr.size else set()
    neg_set = set(neg_arr.tolist()) if neg_arr.size else set()
    out: list[float] = []
    for text in texts:
        toks = tokenize(text)
        if not toks:
            out.append(0.0)
            continue
        # numpy isin on unique tokens
        u, counts = np.unique(np.asarray(toks, dtype=object), return_counts=True)
        pos_c = 0
        neg_c = 0
        for tok, c in zip(u.tolist(), counts.tolist()):
            if tok in pos_set:
                pos_c += int(c)
            elif tok in neg_set:
                neg_c += int(c)
        if pos_c == 0 and neg_c == 0:
            out.append(0.0)
        else:
            out.append(float(np.clip((pos_c - neg_c) / max(3.0, pos_c + neg_c), -1.0, 1.0)))
    return np.asarray(out, dtype=np.float64)


def polarity_mean(texts: Sequence[str]) -> float:
    arr = polarity_batch(texts)
    if arr.size == 0:
        return 0.0
    return float(np.mean(arr))


def lea_enabled() -> bool:
    return _b("USE_LOGIT_EVIDENCE", True)
