"""Near-term headline + technical headwinds — block chasing broken mega-caps."""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "data" / "near_term_headwinds.json"

NEWS_HEADWIND_RE = re.compile(
    r"(underweight|downgrade|cut target|gap down|whisper.*miss|"
    r"dilution|equity dilution|stock sale|below.{0,12}200.?day|"
    r"broke.{0,12}200.?day|soft.{0,20}guidance|cap\s*ex|capital expenditure|"
    r"meltdown|single.?session drop|failed.{0,12}200.?day)",
    re.I,
)

HORIZON_DAYS = {
    "one_day": 1,
    "one_week": 5,
    "one_month": 21,
    "six_months": 126,
    "one_year": 252,
    "five_years": 1260,
    "ten_years": 2520,
    # legacy
    "next_trading_day": 1,
    "this_week": 5,
    "this_month": 21,
    "two_months": 126,
}


@lru_cache(maxsize=1)
def _load_overrides() -> dict[str, dict]:
    path = Path(os.getenv("NEAR_TERM_HEADWINDS_PATH", str(DEFAULT_PATH)))
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return {k.upper(): v for k, v in (doc.get("symbols") or {}).items() if isinstance(v, dict)}
    except Exception:
        return {}


def _technical_flags(*, closes, mom_5d: float | None, mom_1d: float | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "below_sma200": False,
        "weekly_drop_pct": None,
        "daily_drop_pct": None,
    }
    if closes is not None and len(closes) >= 50:
        try:
            import pandas as pd

            c = closes.astype(float)
            close = float(c.iloc[-2] if len(c) >= 2 else c.iloc[-1])
            sma200 = float(c.rolling(200, min_periods=50).mean().iloc[-2])
            if sma200 > 0:
                out["below_sma200"] = close < sma200 * 0.998
                out["sma200"] = sma200
                out["close"] = close
        except Exception:
            pass
    if mom_5d is not None:
        out["weekly_drop_pct"] = float(mom_5d) * 100.0
    if mom_1d is not None:
        out["daily_drop_pct"] = float(mom_1d) * 100.0
    elif closes is not None and len(closes) >= 3:
        try:
            c = closes.astype(float)
            out["daily_drop_pct"] = float(c.iloc[-2] / c.iloc[-3] - 1.0) * 100.0
        except Exception:
            pass
    return out


def assess_near_term_headwind(
    symbol: str,
    *,
    closes=None,
    mom_5d: float | None = None,
    mom_1d: float | None = None,
    news_texts: list[str] | None = None,
    horizon_label: str | None = None,
) -> dict[str, Any]:
    """Return penalties + block flags for a symbol (file overrides + live techn/news)."""
    sym = symbol.strip().upper()
    cfg = dict(_load_overrides().get(sym, {}))
    tech = _technical_flags(closes=closes, mom_5d=mom_5d, mom_1d=mom_1d)

    reasons = list(cfg.get("reasons") or [])
    p_pen = float(cfg.get("p_penalty", 0.0))
    score_pen = float(cfg.get("score_penalty", 0.0))
    block_playbook = bool(cfg.get("block_playbook", False))
    block_horizons = {str(h) for h in (cfg.get("block_horizons") or [])}
    stance = str(cfg.get("stance", "neutral"))

    if tech.get("below_sma200"):
        p_pen = max(p_pen, 0.08)
        score_pen = max(score_pen, 0.25)
        reasons.append("Price below 200-day moving average")
    wk = tech.get("weekly_drop_pct")
    if wk is not None and wk <= -5.0:
        p_pen = max(p_pen, 0.12)
        score_pen = max(score_pen, 0.35)
        reasons.append(f"Sharp weekly drop ({wk:.1f}%)")
    day = tech.get("daily_drop_pct")
    if day is not None and day <= -3.0:
        p_pen = max(p_pen, 0.06)
        score_pen = max(score_pen, 0.15)
        reasons.append(f"Large single-session drop ({day:.1f}%)")

    if news_texts:
        hits = [t for t in news_texts if t and NEWS_HEADWIND_RE.search(t)]
        if hits:
            p_pen = max(p_pen, 0.05)
            score_pen = max(score_pen, 0.12)
            reasons.append("Recent headline headwinds (downgrade/guidance/dilution/CapEx)")

    block_horizon = False
    if horizon_label:
        from analytics.family_horizons import normalize_label

        hkey = normalize_label(horizon_label)
        if hkey in block_horizons or horizon_label in block_horizons:
            block_horizon = True

    block_near_term_buy = block_playbook or stance in ("block_near_term", "volatile_caution")
    if horizon_label:
        from analytics.family_horizons import normalize_label

        hkey = normalize_label(horizon_label)
        days = HORIZON_DAYS.get(hkey, HORIZON_DAYS.get(horizon_label, 5))
        if stance == "block_near_term" and days <= 20:
            block_horizon = True
        if stance == "volatile_caution" and days <= 5:
            block_horizon = True
        if stance == "dip_watch_only" and days <= 1:
            block_horizon = True

    return {
        "symbol": sym,
        "stance": stance,
        "p_penalty": float(min(p_pen, 0.35)),
        "score_penalty": float(min(score_pen, 1.0)),
        "block_playbook": block_playbook,
        "block_horizon": block_horizon,
        "block_near_term_buy": block_near_term_buy and block_playbook,
        "reasons": reasons[:6],
        "technical": tech,
    }


def apply_headwind_to_score_row(row: dict, *, closes=None) -> dict:
    """Mutate scoring row: penalize p_up/score; add gate when blocked."""
    sym = str(row.get("ticker", "")).upper()
    if not sym:
        return row
    hw = assess_near_term_headwind(
        sym,
        closes=closes,
        mom_5d=row.get("momentum_5d"),
    )
    if hw["p_penalty"] <= 0 and hw["score_penalty"] <= 0:
        return row
    p = float(row.get("p_up", 0.5))
    row["p_up"] = max(0.05, p - float(hw["p_penalty"]))
    row["score"] = float(row.get("score", 0.0)) - float(hw["score_penalty"])
    row["near_term_headwind"] = hw
    if hw["block_playbook"] or hw["block_near_term_buy"]:
        gd = str(row.get("gate_detail", "all_ok"))
        row["gate_detail"] = gd if gd != "all_ok" else "headwind_block"
        if "headwind" not in row["gate_detail"]:
            row["gate_detail"] = f"{row['gate_detail']}+headwind"
        row["asym_action"] = "NO_TRADE"
    return row


def _fill_skip_soft_headwind() -> bool:
    """Idle-cash / fade: CapEx and stale 200d blocks must not park 40%+ cash."""
    for name in (
        "DOWNPRESS_SOFT_OK_WHEN_UNDERDEPLOY",
        "FORTRESS_FILL_SKIP_SOFT_HEADWIND",
        "FORTRESS_FADE_SKIP_SOFT_DOWNPRESS",
    ):
        if os.getenv(name, "false").lower() in ("1", "true", "yes", "on"):
            return True
    return False


_HARD_HEADWIND_MARKERS = (
    "earnings today",
    "earnings in 0",
    "halt",
    "bankruptcy",
    "going concern",
    "delist",
)


def _soft_headwind_reasons(reasons: list[str]) -> bool:
    blob = " ".join(str(r).lower() for r in reasons)
    return not any(m in blob for m in _HARD_HEADWIND_MARKERS)


def blocks_playbook_buy(symbol: str) -> tuple[bool, list[str]]:
    try:
        from intel.algo_risk_filter import blocks_buy

        blocked, reason = blocks_buy(symbol)
        if blocked:
            reasons = [reason]
            if _fill_skip_soft_headwind() and _soft_headwind_reasons(reasons):
                if "earnings" not in str(reason).lower():
                    return False, reasons
            return True, reasons
    except Exception:
        pass
    hw = assess_near_term_headwind(symbol)
    reasons = list(hw.get("reasons") or [])
    if hw.get("block_playbook") and _fill_skip_soft_headwind() and _soft_headwind_reasons(reasons):
        return False, reasons
    return bool(hw.get("block_playbook")), reasons


def blocks_horizon_pick(
    symbol: str,
    horizon_label: str,
    *,
    live_risk: bool = True,
) -> tuple[bool, list[str]]:
    if live_risk:
        try:
            from intel.algo_risk_filter import blocks_buy

            blocked, reason = blocks_buy(symbol)
            if blocked:
                return True, [reason]
        except Exception:
            pass
    hw = assess_near_term_headwind(symbol, horizon_label=horizon_label)
    return bool(hw.get("block_horizon")), list(hw.get("reasons") or [])
