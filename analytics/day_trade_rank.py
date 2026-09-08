"""Rank day-trade candidates — setup score × JP-candle RL × optional model boost."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from analytics.day_trade_setups import SetupScan
from analytics.jp_candle_rl import pattern_weight


@dataclass
class RankedPick:
    ticker: str
    score: float
    scan: SetupScan
    rl_weight: float = 1.0
    model_p: float | None = None
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "score": round(self.score, 4),
            "bias": self.scan.bias,
            "confidence": self.scan.confidence,
            "bullish": self.scan.bullish,
            "rl_weight": round(self.rl_weight, 3),
            "model_p": self.model_p,
            "reasons": self.reasons,
        }


def _pattern_from_scan(scan: SetupScan) -> str:
    for label in scan.bullish:
        if label.startswith("candle_"):
            return label.replace("candle_", "").upper()
    return "NONE"


def _model_p_up(ticker: str) -> float | None:
    if os.getenv("DAY_TRADE_USE_MODELS", "true").lower() not in ("1", "true", "yes"):
        return None
    path = os.path.join("models", f"{ticker.upper()}_model.pkl")
    if not os.path.isfile(path):
        return None
    try:
        import pandas as pd

        from feature_engineering import build_features
        from ml_model import predict_row_details

        end = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
        start = (pd.Timestamp.utcnow() - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
        df = build_features(ticker, start, end)
        if df.empty:
            return None
        det = predict_row_details(path, df.iloc[-1])
        p = det.get("p_up")
        return float(p) if p is not None else None
    except Exception:
        return None


def rank_scan(scan: SetupScan) -> RankedPick:
    sym = scan.ticker.upper()
    reasons: list[str] = []
    base = scan.bias * (0.55 + 0.45 * scan.confidence)
    club_info: dict = {}
    cb = 0.0
    try:
        from intel.morning_club_intel import load_latest, morning_club_block_long, morning_club_boost_for

        club_info = (load_latest().get("tickers") or {}).get(sym) or {}
        cb = float(morning_club_boost_for(sym))
        if morning_club_block_long(sym):
            return RankedPick(sym, 0.0, scan, reasons=["club_block"])
    except Exception:
        pass

    if scan.bias <= 0:
        if club_info.get("catalyst") == "earnings" and cb >= 0.65:
            base = float(os.getenv("DAY_TRADE_EARNINGS_BASE", "0.48"))
            reasons.append("earnings_catalyst")
        else:
            return RankedPick(sym, base, scan, reasons=["bearish"])

    try:
        blend = float(os.getenv("DAY_TRADE_CLUB_BLEND", "0.40"))
        add = float(os.getenv("DAY_TRADE_CLUB_ADD", "0.32"))
        if abs(cb) >= 0.08:
            base *= 1.0 + blend * cb
            base += add * max(0.0, cb)
            reasons.append(f"club={cb:+.2f}")
    except Exception:
        pass

    pat = _pattern_from_scan(scan)
    rl_w = pattern_weight(pat)
    score = base * rl_w
    if rl_w > 1.05:
        reasons.append(f"rl+{pat}")
    elif rl_w < 0.95:
        reasons.append(f"rl-{pat}")

    mp = _model_p_up(sym)
    if mp is not None:
        blend = float(os.getenv("DAY_TRADE_MODEL_BLEND", "0.25"))
        if mp >= 0.52:
            score *= 1.0 + blend * (mp - 0.5) * 2
            reasons.append(f"model={mp:.2f}")
        elif mp < 0.45:
            score *= 1.0 - blend * (0.5 - mp) * 2
            reasons.append(f"model_weak={mp:.2f}")

    if scan.last_close > 0 and scan.vwap > 0 and scan.last_close > scan.vwap:
        score *= 1.05
        reasons.append("above_vwap")

    if club_info.get("catalyst") == "earnings" and cb >= 0.65:
        floor = float(os.getenv("DAY_TRADE_EARNINGS_FLOOR_SCORE", "0.58"))
        if score < floor:
            score = floor
            reasons.append("earnings_floor")

    try:
        from intel.unified_intel import day_trade_intel_adjustment

        adj, u_reasons = day_trade_intel_adjustment(sym)
        if adj <= -0.99:
            return RankedPick(sym, 0.0, scan, reasons=u_reasons)
        if adj > 0:
            score *= 1.0 + adj
        elif adj < 0:
            score *= max(0.15, 1.0 + adj)
        reasons.extend(u_reasons)
    except Exception:
        good = float(club_info.get("good_news_score") or 0.0)
        bad = float(club_info.get("bad_news_score") or 0.0)
        if good >= 0.52:
            score *= 1.0 + float(os.getenv("CRAMER_AI_GOOD_NEWS_SCORE_BLEND", "0.07")) * good
            reasons.append(f"ai_good={good:.2f}")
        if bad >= 0.55 and bad > good + 0.15:
            score *= 1.0 - float(os.getenv("CRAMER_AI_BAD_NEWS_SCORE_BLEND", "0.12")) * bad
            reasons.append(f"ai_bad={bad:.2f}")

    if any(str(x).startswith("gainz_buy") for x in scan.bullish):
        score *= 1.12
        reasons.append("gainz_v2")
    layers = float((scan.details or {}).get("gainz_layers") or 0)
    if layers >= 5:
        score *= 1.06
        reasons.append("gainz_layers")

    return RankedPick(sym, score, scan, rl_w, mp, reasons)
