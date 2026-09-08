"""
Metric semantics — sentiment intensity is NOT trade probability.

- sentiment_intensity / news_factor: [-1, +1] text relevance weight (arbitrary scale)
- p_up: calibrated model probability P(up)
- execution_confidence: decision score from p_up extremity + model agreement [0, 1]
- options_call_delta: market-implied P(finish above strike) from listed options
"""

from __future__ import annotations

from intel.news_sentiment_lexicon import classify_headline

METRIC_SENTIMENT = "sentiment_intensity"
METRIC_P_UP = "p_up"
METRIC_EXEC_CONF = "execution_confidence"
METRIC_OPTIONS_DELTA = "options_call_delta"


def clamp_sentiment_intensity(x: float) -> float:
    return float(max(-1.0, min(1.0, x)))


def sentiment_rank_impulse(intensity: float, *, scale: float = 0.02, cap: float = 0.03) -> float:
    """Tiny rank/p_up nudge — NOT a probability percentage."""
    i = clamp_sentiment_intensity(intensity)
    return float(max(-cap, min(cap, i * scale)))


def headline_contradicts_intensity(headline: str, intensity: float, *, margin: float = 0.12) -> bool:
    """True when displayed headline polarity fights the numeric factor."""
    if not (headline or "").strip():
        return False
    hl = classify_headline(headline)
    if hl.label == "bearish" and intensity > margin:
        return True
    if hl.label == "bullish" and intensity < -margin:
        return True
    if hl.label == "neutral" and abs(intensity) > 0.45:
        return True
    return False


def reconcile_sentiment_with_headline(headline: str, intensity: float) -> tuple[float, str | None]:
    """
    Cap misleading positive factors on neutral/bearish headlines (e.g. IWM 'mixed/lower').
    Returns (adjusted_intensity, warning).
    """
    i = clamp_sentiment_intensity(intensity)
    if not headline:
        return i, None
    hl = classify_headline(headline)
    warn: str | None = None
    if hl.label == "bearish":
        i = min(i, max(-0.5, hl.score))
        warn = "headline_bearish_cap"
    elif hl.label == "neutral":
        i = max(-0.15, min(0.15, i * 0.45))
        if abs(intensity) > 0.2:
            warn = "headline_neutral_dampen"
    elif hl.label == "bullish" and i < -0.1:
        i = max(i, hl.score * 0.5)
        warn = "headline_bullish_floor"
    if headline_contradicts_intensity(headline, i):
        warn = warn or "headline_factor_mismatch"
    return clamp_sentiment_intensity(i), warn
