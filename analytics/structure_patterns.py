"""Research-backed structure / pattern signals — no lookahead.

Literature (2024–2026 quant audits of candlesticks across SPY / large universes):
  - Raw candlestick hit rates cluster ~50–55% — near random once trend is controlled.
  - Context (trend + support/resistance) is where any residual edge lives.
  - Chart *structure* (swings, HH/HL, S/R distance) is more reliable than candle folklore.

This module therefore:
  1. Scores trend / support / resistance with objective swing math.
  2. Treats candlesticks as *weak confirmation only*, shrunk toward 0.5.
  3. Optionally validates patterns vs forward returns and weights by *excess*
     hit rate over the unconditional baseline (never raw confidence).

Inspired by the selftrader pattern catalog, but re-implemented for FATE's
pandas OHLC frames and rank pipeline — not a copy-paste of that package.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _b(name: str, default: bool = True) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes")


@dataclass
class StructureMatch:
    name: str
    bias: int  # +1 bullish, -1 bearish, 0 neutral
    weight: float  # contribution magnitude after literature shrink
    detail: str = ""


@dataclass
class StructureContext:
    trend: str = "unknown"
    support: float | None = None
    resistance: float | None = None
    matches: list[StructureMatch] = field(default_factory=list)
    composite: float = 0.0  # in [-1, 1]
    excess_edge: float = 0.0  # validated excess hit-rate contribution

    def summary_lines(self) -> list[str]:
        lines = [f"trend={self.trend}  composite={self.composite:+.4f}"]
        if self.support is not None:
            lines.append(f"  support={self.support:.4f}")
        if self.resistance is not None:
            lines.append(f"  resistance={self.resistance:.4f}")
        for m in sorted(self.matches, key=lambda x: -abs(x.weight)):
            arrow = "▲" if m.bias > 0 else ("▼" if m.bias < 0 else "─")
            lines.append(f"  {arrow} {m.name:22s}  w={m.weight:+.3f}  {m.detail}")
        return lines


def _closes_highs_lows(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    c = df["Close"].astype(float).to_numpy() if "Close" in df.columns else df["Adj Close"].astype(float).to_numpy()
    if "High" in df.columns and "Low" in df.columns and "Open" in df.columns:
        h = df["High"].astype(float).to_numpy()
        l = df["Low"].astype(float).to_numpy()
        o = df["Open"].astype(float).to_numpy()
    else:
        # Approximate OHLC from closes (same idea as selftrader, but local).
        o = np.roll(c, 1)
        o[0] = c[0]
        h = np.maximum(o, c) * 1.002
        l = np.minimum(o, c) * 0.998
    return o, h, l, c


def find_swings(closes: np.ndarray, window: int = 5) -> tuple[list[int], list[int]]:
    """Swing highs / lows using only bars up to each index (causal)."""
    highs: list[int] = []
    lows: list[int] = []
    n = len(closes)
    for i in range(window, n):
        chunk = closes[i - window : i + 1]
        if closes[i] >= chunk.max() - 1e-12:
            highs.append(i)
        if closes[i] <= chunk.min() + 1e-12:
            lows.append(i)
    return highs, lows


def identify_trend(closes: np.ndarray, i: int, lookback: int = 60) -> str:
    start = max(0, i - lookback + 1)
    seg = closes[start : i + 1]
    if len(seg) < 10:
        return "unknown"
    highs, lows = find_swings(seg, window=3)
    if len(highs) < 2 or len(lows) < 2:
        ret = (seg[-1] - seg[0]) / seg[0] if seg[0] else 0.0
        if ret > 0.05:
            return "uptrend"
        if ret < -0.05:
            return "downtrend"
        return "sideways"
    hh = sum(1 for k in range(1, len(highs)) if seg[highs[k]] > seg[highs[k - 1]])
    hl = sum(1 for k in range(1, len(lows)) if seg[lows[k]] > seg[lows[k - 1]])
    lh = sum(1 for k in range(1, len(highs)) if seg[highs[k]] < seg[highs[k - 1]])
    ll = sum(1 for k in range(1, len(lows)) if seg[lows[k]] < seg[lows[k - 1]])
    if hh >= 1 and hl >= 1:
        return "uptrend"
    if lh >= 1 and ll >= 1:
        return "downtrend"
    return "sideways"


def find_support_resistance(
    closes: np.ndarray, i: int, lookback: int = 60
) -> tuple[float | None, float | None]:
    start = max(0, i - lookback + 1)
    seg = closes[start : i + 1]
    price = float(closes[i])
    highs, lows = find_swings(seg, window=3)
    support_levels = [float(seg[j]) for j in lows if seg[j] < price]
    resist_levels = [float(seg[j]) for j in highs if seg[j] > price]
    support = max(support_levels) if support_levels else None
    resistance = min(resist_levels) if resist_levels else None
    return support, resistance


def _near(a: float, b: float, tol: float = 0.02) -> bool:
    if b == 0:
        return False
    return abs(a - b) / abs(b) <= tol


def _double_top_bottom(closes: np.ndarray, i: int, lookback: int) -> StructureMatch | None:
    start = max(0, i - lookback + 1)
    seg = closes[start : i + 1]
    highs, lows = find_swings(seg, window=4)
    # Double top
    if len(highs) >= 2 and len(lows) >= 1:
        p1, p2 = float(seg[highs[-2]]), float(seg[highs[-1]])
        trough = float(seg[lows[-1]])
        if _near(p1, p2, 0.02) and trough < min(p1, p2) * 0.97 and highs[-2] < lows[-1] < highs[-1]:
            height = ((p1 + p2) / 2) - trough
            # Structure confidence capped — literature distrusts high folklore confidences.
            w = min(0.35, 0.18 + height / max(p1, 1e-9) * 2.0)
            return StructureMatch("Double Top", -1, w, f"peaks~{p1:.2f}/{p2:.2f}")
    # Double bottom
    if len(lows) >= 2 and len(highs) >= 1:
        t1, t2 = float(seg[lows[-2]]), float(seg[lows[-1]])
        peak = float(seg[highs[-1]])
        if _near(t1, t2, 0.02) and peak > max(t1, t2) * 1.03 and lows[-2] < highs[-1] < lows[-1]:
            height = peak - (t1 + t2) / 2
            w = min(0.35, 0.18 + height / max(t1, 1e-9) * 2.0)
            return StructureMatch("Double Bottom", 1, w, f"troughs~{t1:.2f}/{t2:.2f}")
    return None


def _head_shoulders(closes: np.ndarray, i: int, lookback: int) -> StructureMatch | None:
    """Classic H&S / inverse — weight capped (chart folklore, not a free lunch)."""
    start = max(0, i - lookback + 1)
    seg = closes[start : i + 1]
    highs, lows = find_swings(seg, window=3)
    if len(highs) >= 3:
        l, h, r = float(seg[highs[-3]]), float(seg[highs[-2]]), float(seg[highs[-1]])
        if h > l and h > r and _near(l, r, 0.03):
            return StructureMatch("Head & Shoulders", -1, 0.22, f"head={h:.2f} shoulders~{l:.2f}/{r:.2f}")
    if len(lows) >= 3:
        l, h, r = float(seg[lows[-3]]), float(seg[lows[-2]]), float(seg[lows[-1]])
        if h < l and h < r and _near(l, r, 0.03):
            return StructureMatch("Inverse H&S", 1, 0.22, f"head={h:.2f} shoulders~{l:.2f}/{r:.2f}")
    return None


def _triangle(closes: np.ndarray, i: int, lookback: int) -> StructureMatch | None:
    """Ascending / descending / symmetrical triangle from swing slopes."""
    start = max(0, i - lookback + 1)
    seg = closes[start : i + 1]
    highs, lows = find_swings(seg, window=3)
    if len(highs) < 3 or len(lows) < 3:
        return None
    hx = np.array(highs[-3:], dtype=float)
    hy = np.array([seg[j] for j in highs[-3:]], dtype=float)
    lx = np.array(lows[-3:], dtype=float)
    ly = np.array([seg[j] for j in lows[-3:]], dtype=float)
    # Simple OLS slope
    def _slope(x: np.ndarray, y: np.ndarray) -> float:
        xm, ym = x.mean(), y.mean()
        den = ((x - xm) ** 2).sum()
        if den < 1e-12:
            return 0.0
        return float(((x - xm) * (y - ym)).sum() / den)

    h_slope = _slope(hx, hy)
    l_slope = _slope(lx, ly)
    # Normalize by price scale
    px = max(float(seg[-1]), 1e-9)
    h_slope /= px
    l_slope /= px
    if h_slope < -0.0005 and l_slope > 0.0005:
        return StructureMatch("Symmetrical Triangle", 0, 0.12, "converging swings — wait for break")
    if abs(h_slope) < 0.0005 and l_slope > 0.0005:
        return StructureMatch("Ascending Triangle", 1, 0.20, "flat resistance, rising support")
    if h_slope < -0.0005 and abs(l_slope) < 0.0005:
        return StructureMatch("Descending Triangle", -1, 0.20, "falling resistance, flat support")
    return None


def _breakout(closes: np.ndarray, i: int, lookback: int) -> StructureMatch | None:
    support, resistance = find_support_resistance(closes, i, lookback)
    if i < 2:
        return None
    price, prev = float(closes[i]), float(closes[i - 1])
    if prev <= 0:
        return None
    ret = (price - prev) / prev
    if resistance and prev <= resistance and price > resistance * 1.002 and ret > 0.005:
        w = min(0.28, 0.14 + abs(ret) * 8.0)
        return StructureMatch("Resistance Breakout", 1, w, f"above {resistance:.2f} (+{ret*100:.2f}%)")
    if support and prev >= support and price < support * 0.998 and ret < -0.005:
        w = min(0.28, 0.14 + abs(ret) * 8.0)
        return StructureMatch("Support Breakdown", -1, w, f"below {support:.2f} ({ret*100:.2f}%)")
    return None


def _sequence_math_signal(closes: np.ndarray, i: int, lookback: int = 12) -> StructureMatch | None:
    """Use general sequence discovery on recent *returns* (not folklore chart names).

    Maps predicted next return sign → small structure bias. Disabled unless
    USE_SEQUENCE_DISCOVER=true. Complexity/runtime gated for rank path.
    """
    if not _b("USE_SEQUENCE_DISCOVER", True):
        return None
    n = min(lookback, i)
    if n < 6:
        return None
    window = closes[i - n : i + 1]
    rets = np.diff(window) / np.maximum(window[:-1], 1e-12)
    # Scale to nicer magnitudes for the discoverer (percent points)
    seq = [float(r * 100.0) for r in rets[-min(10, len(rets)) :]]
    try:
        from analytics.sequence_discover import search_pattern

        hit = search_pattern(seq)
        if hit is None or not math.isfinite(hit.next_val):
            return None
        # Direction of next predicted return
        if abs(hit.next_val) < 0.05:  # <5bp in pct-space ≈ noise
            return None
        bias = 1 if hit.next_val > 0 else -1
        # Tiny weight — math discovery is exploratory, not a primary alpha source
        w = min(0.15, 0.06 + min(abs(hit.next_val), 2.0) * 0.02)
        return StructureMatch(
            f"Seq:{hit.best.family}",
            bias,
            w,
            f"{hit.best.name} → next≈{hit.next_val:+.3f}%",
        )
    except Exception:
        return None


def _candle_confirm(o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray, i: int) -> StructureMatch | None:
    """Weak candle confirmation. Raw folklore confidence is shrunk toward 0.5."""
    if i < 1:
        return None
    try:
        from analytics.jp_candles import assess_candles_from_df, pattern_bias, pattern_name

        df = pd.DataFrame(
            {
                "Open": o[max(0, i - 8) : i + 1],
                "High": h[max(0, i - 8) : i + 1],
                "Low": l[max(0, i - 8) : i + 1],
                "Close": c[max(0, i - 8) : i + 1],
            }
        )
        res = assess_candles_from_df(df)
        pid = int(getattr(res, "pattern", 0) or 0)
        bias = int(getattr(res, "bias", 0) or pattern_bias(pid))
        if bias == 0 or pid == 0:
            return None
        # Literature: raw candle hit ~50–55%. Keep only a slice of (prior − 0.5).
        raw_conf = 0.55
        shrink = _f("STRUCTURE_CANDLE_SHRINK", 0.25)
        excess = (raw_conf - 0.5) * shrink
        return StructureMatch(
            pattern_name(pid),
            bias,
            excess * abs(bias),
            "candle confirm (shrunk toward 0.5)",
        )
    except Exception:
        return None


def analyze_structure(
    df: pd.DataFrame,
    *,
    lookback: int | None = None,
    bar_index: int | None = None,
) -> StructureContext:
    """Causal structure analysis on OHLC dataframe ending at `bar_index`."""
    if df is None or len(df) < 15:
        return StructureContext()
    lookback = int(lookback or _f("STRUCTURE_LOOKBACK", 60))
    o, h, l, c = _closes_highs_lows(df)
    i = int(bar_index if bar_index is not None else len(c) - 1)
    i = max(0, min(i, len(c) - 1))

    trend = identify_trend(c, i, lookback)
    support, resistance = find_support_resistance(c, i, lookback)
    matches: list[StructureMatch] = []

    # Trend structure (primary signal — math HH/HL)
    if trend == "uptrend":
        matches.append(StructureMatch("Uptrend", 1, 0.22, "higher highs / higher lows"))
    elif trend == "downtrend":
        matches.append(StructureMatch("Downtrend", -1, 0.22, "lower highs / lower lows"))

    # Proximity to S/R (context amplifier)
    price = float(c[i])
    if support is not None and price > 0:
        dist = (price - support) / price
        if 0 <= dist <= 0.02:
            matches.append(StructureMatch("At Support", 1, 0.18, f"dist={dist*100:.2f}%"))
    if resistance is not None and price > 0:
        dist = (resistance - price) / price
        if 0 <= dist <= 0.02:
            matches.append(StructureMatch("At Resistance", -1, 0.18, f"dist={dist*100:.2f}%"))

    dtb = _double_top_bottom(c, i, lookback)
    if dtb:
        matches.append(dtb)

    for det in (_head_shoulders, _triangle, _breakout):
        m = det(c, i, lookback)
        if m is not None and m.bias != 0:
            matches.append(m)
        elif m is not None and m.bias == 0 and _b("STRUCTURE_KEEP_NEUTRAL", False):
            matches.append(m)

    seq = _sequence_math_signal(c, i, lookback=min(14, lookback // 3 or 8))
    if seq is not None:
        # Soft-agree with trend when present; otherwise allow small exploratory bias
        if trend == "uptrend" and seq.bias < 0 and not _b("SEQUENCE_ALLOW_CONTRA", False):
            pass
        elif trend == "downtrend" and seq.bias > 0 and not _b("SEQUENCE_ALLOW_CONTRA", False):
            pass
        else:
            matches.append(seq)

    # Candle only if it *agrees* with trend or S/R context
    candle = _candle_confirm(o, h, l, c, i)
    if candle is not None:
        trend_ok = (trend == "uptrend" and candle.bias > 0) or (trend == "downtrend" and candle.bias < 0)
        sr_ok = any(m.name in ("At Support", "At Resistance") and m.bias == candle.bias for m in matches)
        if trend_ok or sr_ok or _b("STRUCTURE_ALLOW_ORPHAN_CANDLES", False):
            matches.append(candle)
        # else: drop orphan candles (literature: no edge without context)

    composite = 0.0
    if matches:
        composite = sum(m.bias * m.weight for m in matches) / max(1, len(matches))
        composite = max(-1.0, min(1.0, composite))

    return StructureContext(
        trend=trend,
        support=support,
        resistance=resistance,
        matches=matches,
        composite=float(composite),
    )


def validate_structure(
    df: pd.DataFrame,
    *,
    horizon: int = 5,
    lookback: int = 60,
) -> list[dict[str, Any]]:
    """Hit-rate table vs unconditional baseline. Excess = hit − baseline."""
    if df is None or len(df) < lookback + horizon + 20:
        return []
    o, h, l, c = _closes_highs_lows(df)
    n = len(c)
    fwd = (c[horizon:] - c[:-horizon]) / np.maximum(c[:-horizon], 1e-12)
    baseline_up = float(np.mean(fwd > 0))
    baseline_dn = 1.0 - baseline_up
    buckets: dict[str, list[bool]] = {}

    for i in range(lookback + 5, n - horizon):
        sub = df.iloc[: i + 1]
        ctx = analyze_structure(sub, lookback=lookback, bar_index=len(sub) - 1)
        actual_up = bool(fwd[i] > 0)
        for m in ctx.matches:
            if m.bias == 0:
                continue
            hit = actual_up if m.bias > 0 else (not actual_up)
            buckets.setdefault(m.name, []).append((hit, m.bias))

    rows = []
    for name, pairs in sorted(buckets.items()):
        if len(pairs) < 8:
            continue
        hits = [p[0] for p in pairs]
        bias = pairs[0][1]
        hr = sum(hits) / len(hits)
        base = baseline_up if bias > 0 else baseline_dn
        rows.append(
            {
                "pattern": name,
                "n": len(hits),
                "hit_rate": round(hr, 4),
                "baseline": round(base, 4),
                "excess": round(hr - base, 4),
            }
        )
    rows.sort(key=lambda r: -r["excess"])
    return rows


def structure_rank_boost(df: pd.DataFrame | None) -> tuple[float, dict[str, Any]]:
    """Small rank delta from validated structure. Capped — patterns must not dominate ML heads."""
    if not _b("USE_STRUCTURE_PATTERNS", True):
        return 0.0, {"enabled": False}
    if df is None or len(df) < 20:
        return 0.0, {"enabled": True, "reason": "short_history"}
    ctx = analyze_structure(df)
    w = _f("RANK_W_STRUCTURE", 0.10)
    # Soft-gate: near-zero composites ignored (noise)
    if abs(ctx.composite) < _f("STRUCTURE_MIN_ABS", 0.04):
        return 0.0, {"enabled": True, "composite": ctx.composite, "gated": True, "trend": ctx.trend}
    boost = w * float(np.tanh(ctx.composite * 2.0))
    return float(boost), {
        "enabled": True,
        "composite": ctx.composite,
        "trend": ctx.trend,
        "support": ctx.support,
        "resistance": ctx.resistance,
        "n_matches": len(ctx.matches),
        "boost": boost,
    }
