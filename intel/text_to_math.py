"""Convert news / NLP / events into pure numeric z-scores and factors.

Optimize-never-remove: keeps Finnhub/NewsAPI/lexicon/LLM pipelines; scores them
mathematically so rank/sizing never leans on narrative intuition alone.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import asdict, dataclass
from typing import Iterable, Sequence


_TOKEN_RE = re.compile(r"[a-z0-9]{2,}", re.I)
_EPS = 1e-9


@dataclass
class TextMathSignals:
    sentiment_raw: float
    sentiment_z: float
    embedding_polarity: float
    embedding_norm: float
    event_surprise_z: float
    conviction_z: float
    final_math: float
    sample_count: int

    def to_dict(self) -> dict:
        return asdict(self)


def zscore(x: float, mu: float = 0.0, sigma: float = 1.0) -> float:
    s = float(sigma)
    if not math.isfinite(s) or abs(s) < _EPS:
        return 0.0
    z = (float(x) - float(mu)) / s
    if not math.isfinite(z):
        return 0.0
    return float(max(-8.0, min(8.0, z)))


def tanh_tilt(z: float, k: float = 1.5) -> float:
    return float(math.tanh(float(z) / max(k, _EPS)))


def event_surprise_z(actual: float, consensus: float, sigma_est: float | None = None) -> float:
    """Standardized surprise: (actual − consensus) / σ_est."""
    a, c = float(actual), float(consensus)
    if not math.isfinite(a) or not math.isfinite(c):
        return 0.0
    base = abs(c) if abs(c) > _EPS else 1.0
    sig = float(sigma_est) if sigma_est is not None and float(sigma_est) > _EPS else max(0.05 * base, 0.01)
    return zscore(a - c, 0.0, sig)


def embedding_proxy(texts: Sequence[str], polarity: float = 0.0) -> tuple[float, float]:
    """Hash bag-of-tokens → unit vector · polarity (offline, no network).

    Returns (embedding_polarity ∈ [-1,1], L2 norm of bag before polarity).
    """
    bag: dict[str, float] = {}
    for t in texts:
        for tok in _TOKEN_RE.findall(t or ""):
            h = int(hashlib.md5(tok.lower().encode()).hexdigest()[:8], 16)
            # 64 pseudo-dims folded into a scalar energy + signed polarity channel
            dim = h % 64
            sign = 1.0 if (h // 64) % 2 == 0 else -1.0
            bag[str(dim)] = bag.get(str(dim), 0.0) + sign
    if not bag:
        return 0.0, 0.0
    energy = math.sqrt(sum(v * v for v in bag.values()))
    if energy < _EPS:
        return 0.0, 0.0
    # Project bag onto polarity axis: mean signed mass
    mass = sum(bag.values()) / energy
    pol = float(max(-1.0, min(1.0, 0.65 * math.tanh(mass) + 0.35 * float(polarity))))
    return pol, float(energy)


def rolling_mu_sigma(values: Iterable[float]) -> tuple[float, float]:
    xs = [float(v) for v in values if math.isfinite(float(v))]
    if not xs:
        return 0.0, 1.0
    mu = sum(xs) / len(xs)
    if len(xs) < 2:
        return mu, 1.0
    var = sum((x - mu) ** 2 for x in xs) / max(1, len(xs) - 1)
    return mu, max(math.sqrt(var), 0.05)


def score_texts_to_math(
    texts: Sequence[str],
    *,
    sentiment_scores: Sequence[float] | None = None,
    hist_sentiments: Sequence[float] | None = None,
    event_actual: float | None = None,
    event_consensus: float | None = None,
    event_sigma: float | None = None,
    conviction: float = 0.0,
    reliability: float = 0.7,
    contradiction: float = 0.0,
) -> TextMathSignals:
    """Full news→math transform used by news_factor_engine and rank path."""
    from intel.news_sentiment_lexicon import classify_headline

    clean = [t for t in texts if (t or "").strip()]
    if sentiment_scores is None:
        sents = [float(classify_headline(t).score) for t in clean] if clean else [0.0]
    else:
        sents = [float(s) for s in sentiment_scores] or [0.0]

    sent_raw = sum(sents) / max(1, len(sents))
    hist = list(hist_sentiments) if hist_sentiments else sents
    mu, sig = rolling_mu_sigma(hist)
    # Cold-start: use unit scale so raw sentiment still becomes a z-like number
    sent_z = zscore(sent_raw, mu if len(hist) >= 5 else 0.0, sig if len(hist) >= 5 else 0.35)

    emb_pol, emb_n = embedding_proxy(clean, polarity=sent_raw)
    emb_z = zscore(emb_pol, 0.0, 0.40)

    if event_actual is not None and event_consensus is not None:
        ev_z = event_surprise_z(event_actual, event_consensus, event_sigma)
    else:
        ev_z = 0.0

    conv_z = zscore(float(conviction), 0.0, 0.30)
    # Math blend — narrative never sizes alone
    blended = (
        0.45 * tanh_tilt(sent_z)
        + 0.20 * tanh_tilt(emb_z)
        + 0.20 * tanh_tilt(ev_z)
        + 0.15 * tanh_tilt(conv_z)
    )
    rel = max(0.35, min(1.0, float(reliability)))
    contrad = max(0.0, min(0.9, float(contradiction)))
    final = blended * rel * (1.0 - 0.7 * contrad)

    return TextMathSignals(
        sentiment_raw=float(sent_raw),
        sentiment_z=float(sent_z),
        embedding_polarity=float(emb_pol),
        embedding_norm=float(emb_n),
        event_surprise_z=float(ev_z),
        conviction_z=float(conv_z),
        final_math=float(max(-1.0, min(1.0, final))),
        sample_count=len(clean),
    )
