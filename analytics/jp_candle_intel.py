"""Multi-timeframe JP candlestick intel — intraday + Yahoo daily confirmation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import pandas as pd

from analytics.jp_candles import assess_candles_from_df

STRONG_BEAR_PATTERNS = frozenset({"BEARISH_ENGULF", "DARK_CLOUD"})
WEAK_BEAR_PATTERNS = frozenset({"DOJI", "HANGING_MAN", "SHOOTING_STAR"})
STRONG_BULL_PATTERNS = frozenset(
    {"THREE_WHITE", "MORNING_STAR", "BULLISH_ENGULF", "PIERCING", "HAMMER", "INV_HAMMER", "BULL_MARUBOZU"}
)


@dataclass(frozen=True)
class AdvancedCandleIntel:
    intraday: dict[str, Any]
    daily: dict[str, Any]
    composite_bias: int
    composite_score: float
    pattern: str
    trend: int
    daily_confirms: bool
    rl_weight: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "intraday": self.intraday,
            "daily": self.daily,
            "composite_bias": self.composite_bias,
            "composite_score": self.composite_score,
            "pattern": self.pattern,
            "trend": self.trend,
            "daily_confirms": self.daily_confirms,
            "rl_weight": self.rl_weight,
        }


def _three_white_soldiers(df: pd.DataFrame) -> bool:
    if len(df) < 3:
        return False
    tail = df.tail(3)
    greens = all(float(r["Close"]) > float(r["Open"]) for _, r in tail.iterrows())
    if not greens:
        return False
    c0, c1, c2 = (float(tail.iloc[i]["Close"]) for i in range(3))
    return c2 > c1 > c0


def _morning_star(df: pd.DataFrame) -> bool:
    if len(df) < 3:
        return False
    a, b, c = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    body_b = abs(float(b["Close"]) - float(b["Open"]))
    rng_b = float(b["High"]) - float(b["Low"])
    if rng_b <= 0:
        return False
    star = body_b / rng_b < 0.35
    bear_a = float(a["Close"]) < float(a["Open"])
    bull_c = float(c["Close"]) > float(c["Open"])
    gap_down = float(b["High"]) < float(a["Close"])
    reclaim = float(c["Close"]) > (float(a["Open"]) + float(a["Close"])) / 2
    return bear_a and star and bull_c and gap_down and reclaim


def _piercing_line(prev, last) -> bool:
    o1, c1 = float(last["Open"]), float(last["Close"])
    o2, c2 = float(prev["Open"]), float(prev["Close"])
    if not (c2 < o2 and c1 > o1):
        return False
    mid = (o2 + c2) / 2
    return c1 > mid and o1 < c2


def _dark_cloud(prev, last) -> bool:
    o1, c1 = float(last["Open"]), float(last["Close"])
    o2, c2 = float(prev["Open"]), float(prev["Close"])
    if not (c2 > o2 and c1 < o1):
        return False
    mid = (o2 + c2) / 2
    return c1 < mid and o1 > c2


def _bull_marubozu(row) -> bool:
    o, h, l, c = map(float, (row["Open"], row["High"], row["Low"], row["Close"]))
    if c <= o:
        return False
    rng = h - l
    if rng <= 0:
        return False
    body = c - o
    return body / rng > 0.85 and (h - c) / rng < 0.08 and (o - l) / rng < 0.08


def _detect_extras(df: pd.DataFrame) -> tuple[str, int]:
    if df is None or len(df) < 2:
        return "NONE", 0
    tail = df.tail(max(6, int(os.getenv("FORTRESS_JP_CANDLE_LOOKBACK", "6")) + 1))
    if _three_white_soldiers(tail):
        return "THREE_WHITE", 1
    if _morning_star(tail):
        return "MORNING_STAR", 1
    if len(tail) >= 2:
        prev, last = tail.iloc[-2], tail.iloc[-1]
        if _piercing_line(prev, last):
            return "PIERCING", 1
        if _dark_cloud(prev, last):
            return "DARK_CLOUD", -1
        if _bull_marubozu(last):
            return "BULL_MARUBOZU", 1
    return "NONE", 0


def _load_daily_yahoo(ticker: str, *, days: int = 120) -> pd.DataFrame:
    from datetime import datetime, timedelta, timezone

    from feature_engineering import load_price_data

    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    df = load_price_data(ticker, start, None)
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if "Open" not in out.columns and "Close" in out.columns:
        out["Open"] = out["Close"]
    if "High" not in out.columns:
        out["High"] = out["Close"]
    if "Low" not in out.columns:
        out["Low"] = out["Close"]
    return out


def assess_advanced(
    ticker: str,
    intraday_df: pd.DataFrame,
    *,
    lookback: int | None = None,
    use_daily: bool | None = None,
) -> AdvancedCandleIntel:
    lb = lookback if lookback is not None else int(os.getenv("FORTRESS_JP_CANDLE_LOOKBACK", "6"))
    use_d = use_daily if use_daily is not None else os.getenv("FORTRESS_JP_MULTI_TF", "true").lower() in (
        "1",
        "true",
        "yes",
    )

    intra_ca = assess_candles_from_df(intraday_df, lookback=lb)
    extra_name, extra_bias = _detect_extras(intraday_df)
    intra_bias = intra_ca.bias if intra_ca.bias != 0 else extra_bias
    intra_pat = intra_ca.pattern if intra_ca.pattern != "NONE" else extra_name

    daily_meta: dict[str, Any] = {"pattern": "NONE", "bias": 0, "trend": 0, "rows": 0}
    daily_bias = 0
    if use_d:
        daily_df = _load_daily_yahoo(ticker)
        daily_meta["rows"] = int(len(daily_df))
        if len(daily_df) >= 5:
            d_ca = assess_candles_from_df(daily_df, lookback=min(lb, 10))
            d_extra, d_ex_bias = _detect_extras(daily_df)
            daily_pat = d_ca.pattern if d_ca.pattern != "NONE" else d_extra
            daily_bias = d_ca.bias if d_ca.bias != 0 else d_ex_bias
            daily_meta.update(
                {
                    "pattern": daily_pat,
                    "bias": daily_bias,
                    "trend": d_ca.trend,
                }
            )

    # Composite: strong reversal can veto; doji / hanging / shooting are tilts only.
    # Daily last-bar hanging + intraday doji used to sum to -0.45 → hard skip on
    # names the model already liked (p_adj 0.73–0.85). That gate barely worked.
    score = 0.0
    intra_strong_bear = intra_pat in STRONG_BEAR_PATTERNS
    daily_pat = str(daily_meta.get("pattern") or "NONE")
    daily_strong_bear = daily_pat in STRONG_BEAR_PATTERNS
    if intra_bias > 0:
        score += 1.0
    elif intra_strong_bear:
        score -= 1.0
    elif intra_bias < 0:
        score -= 0.20
    if daily_bias > 0:
        score += 0.55
    elif daily_strong_bear:
        score -= 0.55
    elif daily_bias < 0:
        score -= 0.12

    if intra_pat in STRONG_BULL_PATTERNS:
        score += 0.25
    if daily_pat in ("THREE_WHITE", "MORNING_STAR", "BULLISH_ENGULF"):
        score += 0.20

    composite_bias = 1 if score >= 0.55 else (-1 if score <= -0.70 else 0)
    daily_confirms = daily_bias >= 0 or composite_bias <= 0

    from analytics.jp_candle_rl import adjust_boost, pattern_weight

    rl_w = pattern_weight(intra_pat if intra_pat != "NONE" else daily_meta.get("pattern", "NONE"))

    return AdvancedCandleIntel(
        intraday={**intra_ca.to_dict(), "extra_pattern": extra_name, "effective_pattern": intra_pat},
        daily=daily_meta,
        composite_bias=composite_bias,
        composite_score=score,
        pattern=intra_pat if intra_pat != "NONE" else str(daily_meta.get("pattern", "NONE")),
        trend=intra_ca.trend,
        daily_confirms=daily_confirms,
        rl_weight=rl_w,
    )


def apply_to_p_adj(
    p_adj: float,
    intel: AdvancedCandleIntel,
    *,
    want_buy: bool,
) -> tuple[float, bool, str]:
    """Return (p_adj, want_buy, log_line)."""
    base_boost = float(os.getenv("FORTRESS_JP_CANDLE_BOOST", "0.045"))
    strong_boost = float(os.getenv("FORTRESS_JP_STRONG_BOOST", "0.07"))
    from analytics.jp_candle_rl import adjust_boost

    relax = os.getenv("FORTRESS_RELAX_GATES", "false").lower() in ("1", "true", "yes")
    require_bull = os.getenv("FORTRESS_JP_CANDLE_REQUIRE_BULL", "false").lower() in ("1", "true", "yes")

    pat = str(intel.pattern or "NONE").upper()
    daily_pat = str((intel.daily or {}).get("pattern") or "NONE").upper()
    hard_bear = (not relax) and (
        pat in STRONG_BEAR_PATTERNS or daily_pat in STRONG_BEAR_PATTERNS
    ) and intel.composite_bias < 0
    if hard_bear:
        return p_adj, False, f"bearish composite ({intel.pattern})"

    if pat in WEAK_BEAR_PATTERNS and pat != "DOJI":
        haircut = float(os.getenv("FORTRESS_JP_WEAK_BEAR_HAIRCUT", "0.015"))
        p_adj = max(0.01, float(p_adj) - haircut)
        if intel.composite_bias <= 0:
            return p_adj, want_buy, f"weak bear tilt ({intel.pattern})"

    if intel.composite_bias > 0:
        boost = strong_boost if intel.composite_score >= 1.2 else base_boost
        if intel.daily_confirms and intel.daily.get("bias", 0) > 0:
            boost += float(os.getenv("FORTRESS_JP_DAILY_CONFIRM_BOOST", "0.025"))
        boost, w = adjust_boost(boost, intel.pattern)
        p_adj = min(0.99, float(p_adj) + boost)
        return (
            p_adj,
            want_buy,
            f"boost {intel.pattern} score={intel.composite_score:.2f} daily={intel.daily.get('pattern')} rl×{w:.2f}",
        )

    # Doji / none is indecision, not a short. Never hard-skip a model buy for it.
    if pat in ("DOJI", "NONE", "") or pat in WEAK_BEAR_PATTERNS:
        return p_adj, want_buy, ""

    if require_bull and not relax and intel.intraday.get("bias", 0) <= 0 and intel.composite_bias == 0:
        return p_adj, False, "no bullish JP pattern"

    return p_adj, want_buy, ""
