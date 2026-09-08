"""Japanese candlestick patterns on OHLC bars (daily or intraday).

Port of ``hft/src/obi-tape/jp-candles.ts`` for the Python fortress / paper stack.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

PAT_NONE = 0
PAT_HAMMER = 1
PAT_INV_HAMMER = 2
PAT_SHOOTING_STAR = 3
PAT_HANGING_MAN = 4
PAT_DOJI = 5
PAT_BULLISH_ENGULF = 6
PAT_BEARISH_ENGULF = 7

PATTERN_NAMES = {
    PAT_NONE: "NONE",
    PAT_HAMMER: "HAMMER",
    PAT_INV_HAMMER: "INV_HAMMER",
    PAT_SHOOTING_STAR: "SHOOTING_STAR",
    PAT_HANGING_MAN: "HANGING_MAN",
    PAT_DOJI: "DOJI",
    PAT_BULLISH_ENGULF: "BULLISH_ENGULF",
    PAT_BEARISH_ENGULF: "BEARISH_ENGULF",
}

# Minimum range for ratio math — scales with price to survive float noise on large/small ticks.
_RANGE_EPS_ABS = 1e-9


def pattern_name(pattern_id: int) -> str:
    return PATTERN_NAMES.get(int(pattern_id), "NONE")


def pattern_bias(pattern_id: int) -> int:
    p = int(pattern_id)
    if p in (PAT_HAMMER, PAT_INV_HAMMER, PAT_BULLISH_ENGULF):
        return 1
    if p in (PAT_SHOOTING_STAR, PAT_HANGING_MAN, PAT_BEARISH_ENGULF):
        return -1
    return 0


def _min_range(o: float, h: float, l: float, c: float) -> float:
    scale = max(abs(o), abs(h), abs(l), abs(c), 1.0)
    return max(_RANGE_EPS_ABS, scale * 1e-10)


def _bar_parts(o: float, h: float, l: float, c: float) -> tuple[float, float, float, float] | None:
    """Return (range, body, upper_shadow, lower_shadow) or None when bar is flat/invalid."""
    if not (h >= l):
        return None
    rng = h - l
    eps = _min_range(o, h, l, c)
    if rng <= eps:
        return None
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    return rng, body, upper, lower


def _body_ratio(body: float, rng: float) -> float:
    if rng <= 0:
        return 1.0
    return body / rng


def _recent_trend(closes: list[float], lookback: int = 5) -> int:
    """
    Sign of (close[-1] - close[-1-lb]) where lb = min(lookback, len-1), lb >= 1.
    Uses the widest span available up to ``lookback`` bars — never indexes out of range.
    """
    n = len(closes)
    if n < 2:
        return 0
    lb = min(max(int(lookback), 1), n - 1)
    recent = closes[-1]
    past = closes[-1 - lb]
    if recent > past:
        return 1
    if recent < past:
        return -1
    return 0


def _shadow_reversal(
    *,
    lower: float,
    upper: float,
    body: float,
    rng: float,
    trend: int,
    lower_mult: float = 2.0,
) -> int | None:
    """Hammer / hanging man / inverted hammer / shooting star (incl. dragonfly/gravestone doji)."""
    body_ratio = _body_ratio(body, rng)
    tiny_body = body <= _min_range(0, rng, 0, rng) or body_ratio < 0.40

    # Dragonfly / gravestone doji: zero/near-zero body with dominant shadow.
    if body_ratio < 0.10:
        if lower >= 0.55 * rng and upper <= 0.12 * rng:
            return PAT_HAMMER if trend < 0 else PAT_HANGING_MAN
        if upper >= 0.55 * rng and lower <= 0.12 * rng:
            return PAT_INV_HAMMER if trend < 0 else PAT_SHOOTING_STAR

    if not tiny_body:
        return None

    if lower >= lower_mult * max(body, _min_range(0, rng, 0, rng)) and upper <= 0.3 * rng:
        return PAT_HAMMER if trend < 0 else PAT_HANGING_MAN
    if upper >= lower_mult * max(body, _min_range(0, rng, 0, rng)) and lower <= 0.3 * rng:
        return PAT_INV_HAMMER if trend < 0 else PAT_SHOOTING_STAR
    return None


def classify_bar(
    o1: float,
    h1: float,
    l1: float,
    c1: float,
    *,
    o2: float | None = None,
    c2: float | None = None,
    trend: int = 0,
) -> int:
    """Classify the most recent finished bar (optionally with prior bar for engulfing)."""
    parts = _bar_parts(o1, h1, l1, c1)
    if parts is None:
        return PAT_NONE
    rng1, body1, upper1, lower1 = parts

    rev = _shadow_reversal(lower=lower1, upper=upper1, body=body1, rng=rng1, trend=trend)
    if rev is not None:
        return rev

    if o2 is not None and c2 is not None:
        body2 = abs(c2 - o2)
        bullish1 = c1 > o1
        bearish1 = c1 < o1
        bullish2 = c2 > o2
        bearish2 = c2 < o2
        if bullish1 and bearish2 and c1 > o2 and o1 < c2 and body1 > body2:
            return PAT_BULLISH_ENGULF
        if bearish1 and bullish2 and c1 < o2 and o1 > c2 and body1 > body2:
            return PAT_BEARISH_ENGULF

    # Plain doji — only when shadow-reversal rules did not already classify the bar.
    if _body_ratio(body1, rng1) < 0.10:
        return PAT_DOJI
    return PAT_NONE


def _row_valid(row: pd.Series, cols: tuple[str, ...]) -> bool:
    try:
        vals = [row[c] for c in cols]
    except (KeyError, TypeError):
        return False
    if any(pd.isna(v) for v in vals):
        return False
    try:
        o, h, l, c = (float(v) for v in vals)
    except (TypeError, ValueError):
        return False
    if not (h >= l):
        return False
    return h + 1e-12 >= max(o, c) and l - 1e-12 <= min(o, c)


def _ohlc_tail(df: pd.DataFrame, *, lookback: int, cols: tuple[str, ...]) -> pd.DataFrame | None:
    """
    Last ``lookback + 1`` **valid** OHLC rows, walking backward without .dropna() shrink surprises.
    """
    need = max(lookback + 1, 3)
    sub = df[list(cols)]
    picked: list[pd.Series] = []
    for i in range(len(sub) - 1, -1, -1):
        row = sub.iloc[i]
        if not _row_valid(row, cols):
            continue
        picked.append(row)
        if len(picked) >= need:
            break
    if len(picked) < 2:
        return None
    picked.reverse()
    return pd.DataFrame(picked).reset_index(drop=True)


@dataclass(frozen=True)
class CandleAssessment:
    pattern_id: int
    pattern: str
    bias: int
    trend: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "pattern": self.pattern,
            "bias": self.bias,
            "trend": self.trend,
        }


def assess_candles_from_df(df: pd.DataFrame, *, lookback: int = 6) -> CandleAssessment:
    """Detect pattern on the latest bar using prior bars for trend / engulf context."""
    cols = ("Open", "High", "Low", "Close")
    if df is None or len(df) < 2 or not all(c in df.columns for c in cols):
        return CandleAssessment(PAT_NONE, "NONE", 0, 0)

    tail = _ohlc_tail(df, lookback=lookback, cols=cols)
    if tail is None or len(tail) < 2:
        return CandleAssessment(PAT_NONE, "NONE", 0, 0)

    closes = [float(x) for x in tail["Close"].tolist()]
    trend_lb = min(max(lookback, 5), len(closes) - 1)
    trend = _recent_trend(closes, lookback=trend_lb)

    last = tail.iloc[-1]
    prev = tail.iloc[-2]
    o1, h1, l1, c1 = map(float, (last["Open"], last["High"], last["Low"], last["Close"]))
    o2, c2 = float(prev["Open"]), float(prev["Close"])

    pid = classify_bar(o1, h1, l1, c1, o2=o2, c2=c2, trend=trend)
    return CandleAssessment(pid, pattern_name(pid), pattern_bias(pid), trend)
