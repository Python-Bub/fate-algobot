"""Math-first downward-pressure gate — block buying into confirmed weakness.

Covers commodity/oil names (BP, XOM, …) and any name with hard trend dump
(e.g. KLAC −12% / 5d, −31% / 20d). Not paper-relaxed.

New buys and add-ons are blocked on hard dumps *and* soft weakness
(unless a 5d bounce counter-signal). Holdings keep the normal stop —
shrinking it to ~1.7% was realizing every dip as a loss.
"""

from __future__ import annotations

import os
import time
from typing import Any

from utils import log

_MEM: dict[str, tuple[float, dict[str, Any]]] = {}

# Industries that inherit commodity / oil proxy pressure from XLE / CL=F / USO
_OIL_INDUSTRIES = frozenset(
    {
        "integrated_oil_gas",
        "oil_gas_ep",
        "oil_gas_equipment",
    }
)

# Semi equipment / semis — use SMH/SOXX when name itself is dumping
_SEMI_INDUSTRIES = frozenset(
    {
        "semiconductors",
        "semi_equipment",
    }
)


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _ttl() -> float:
    return float(os.getenv("DOWNWARD_PRESSURE_TTL_SEC", "900"))


def _rets(symbol: str) -> dict[str, float | None]:
    """r5 / r20 / r60 from Yahoo (network-first)."""
    out: dict[str, float | None] = {"r5": None, "r20": None, "r60": None, "last": None}
    try:
        from datetime import datetime, timedelta, timezone

        from multi_source_data import fetch_yahoo

        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=100)
        df = fetch_yahoo(symbol, start.isoformat(), end.isoformat())
        if df is None or df.empty or "Close" not in df.columns:
            return out
        # Yahoo often appends a same-day row with NaN OHLC + volume — drop it
        # so r5/r20/r60 use the last *valid* close (otherwise gates go blind).
        c = df["Close"].astype(float).dropna()
        if c.empty:
            return out
        out["last"] = float(c.iloc[-1])

        def _r(n: int) -> float | None:
            if len(c) <= n:
                return None
            base = float(c.iloc[-n - 1])
            if base <= 0 or base != base:  # NaN guard
                return None
            last = float(c.iloc[-1])
            if last != last:
                return None
            return float(last / base - 1.0)

        out["r5"] = _r(5)
        out["r20"] = _r(20)
        out["r60"] = _r(60)
    except Exception as e:
        log.debug("[DOWNPRESS] rets %s: %s", symbol, e)
    return out


def _industry_id(symbol: str) -> str:
    try:
        from analytics.industries.classifier import classify_ticker

        row = classify_ticker(symbol)
        iid = str(row.get("industry_id") or "")
        if iid and iid != "unclassified":
            return iid
    except Exception:
        pass
    try:
        from analytics.custom_stock_groups import group_for_symbol

        g = group_for_symbol(symbol)
        return str(g.get("industry_id") or g.get("group_id") or "")
    except Exception:
        return ""


def assess_downward_pressure(symbol: str, *, force: bool = False) -> dict[str, Any]:
    """
    Return pressure assessment.

    block_new_buy=True → fortress/day_trade must not add
    tighten_exit=True  → use tighter stop / allow thesis abort sooner
    """
    sym = symbol.strip().upper()
    now = time.time()
    if not force:
        hit = _MEM.get(sym)
        if hit and (now - hit[0]) < _ttl():
            return dict(hit[1])

    enabled = os.getenv("USE_DOWNWARD_PRESSURE_GATE", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    rets = _rets(sym)
    r5 = rets.get("r5")
    r20 = rets.get("r20")
    r60 = rets.get("r60")
    iid = _industry_id(sym)

    # Thresholds (math, not narrative)
    r5_hard = _f("DOWNPRESS_R5_HARD", -0.08)  # −8% / 5d
    r20_hard = _f("DOWNPRESS_R20_HARD", -0.15)  # −15% / 20d
    r5_soft = _f("DOWNPRESS_R5_SOFT", -0.04)
    r20_soft = _f("DOWNPRESS_R20_SOFT", -0.08)
    r60_oil = _f("DOWNPRESS_OIL_R60", -0.08)

    reasons: list[str] = []
    score = 0.0  # 0 = fine, 1 = max pressure

    if r5 is not None and r5 <= r5_hard:
        score = max(score, 0.85)
        reasons.append(f"hard 5d dump {r5*100:.1f}%")
    elif r5 is not None and r5 <= r5_soft:
        score = max(score, 0.45)
        reasons.append(f"soft 5d weakness {r5*100:.1f}%")

    if r20 is not None and r20 <= r20_hard:
        score = max(score, 0.95)
        reasons.append(f"hard 20d dump {r20*100:.1f}%")
    elif r20 is not None and r20 <= r20_soft:
        score = max(score, max(score, 0.55))
        reasons.append(f"soft 20d weakness {r20*100:.1f}%")

    # Oil / commodity sector proxy
    oilish = iid in _OIL_INDUSTRIES or sym in {
        "BP",
        "XOM",
        "CVX",
        "SHEL",
        "TTE",
        "COP",
        "EOG",
        "OXY",
        "SLB",
        "HAL",
    }
    sector_rets: dict[str, Any] = {}
    if oilish and enabled:
        for proxy in ("XLE", "USO", "CL=F"):
            pr = _rets(proxy)
            sector_rets[proxy] = pr
            pr5, pr60 = pr.get("r5"), pr.get("r60")
            if pr5 is not None and pr5 <= -0.03:
                score = max(score, 0.55)
                reasons.append(f"oil proxy {proxy} 5d {pr5*100:.1f}%")
            if pr60 is not None and pr60 <= r60_oil:
                # Hard oil 60d on an oil name → high enough to clear block floor
                score = max(score, 0.78)
                reasons.append(f"oil proxy {proxy} 60d {pr60*100:.1f}%")
        # Name + sector both soft → escalate
        if r5 is not None and r5 < 0 and score >= 0.55:
            score = max(score, 0.80)
            reasons.append("oil name + sector downward pressure")
        # Oil name itself soft on 60d while sector weak → block new buys
        if r60 is not None and r60 <= r60_oil and score >= 0.55:
            score = max(score, 0.82)
            reasons.append(f"oil name 60d {r60*100:.1f}% + sector pressure")

    # Semi dump (KLAC class)
    if iid in _SEMI_INDUSTRIES or sym in {"KLAC", "LRCX", "AMAT", "ASML"}:
        for proxy in ("SMH", "SOXX"):
            pr = _rets(proxy)
            sector_rets[proxy] = {k: pr.get(k) for k in ("r5", "r20", "r60")}
            pr5, pr20 = pr.get("r5"), pr.get("r20")
            if pr5 is not None and pr5 <= -0.06:
                score = max(score, 0.60)
                reasons.append(f"semi proxy {proxy} 5d {pr5*100:.1f}%")
            if pr20 is not None and pr20 <= -0.12:
                score = max(score, 0.75)
                reasons.append(f"semi proxy {proxy} 20d {pr20*100:.1f}%")

    block_thresh = _f("DOWNPRESS_BLOCK_SCORE", 0.72)
    tighten_thresh = _f("DOWNPRESS_TIGHTEN_SCORE", 0.45)
    block = bool(enabled and score >= block_thresh)
    tighten = bool(enabled and score >= tighten_thresh)

    # Counter-signal: strong short-term bounce + positive 5d can clear soft blocks only
    counter = False
    if r5 is not None and r5 >= _f("DOWNPRESS_COUNTER_R5", 0.04) and score < 0.90:
        counter = True
        if score < block_thresh:
            block = False
            reasons.append("counter-signal: strong 5d bounce")

    res = {
        "symbol": sym,
        "industry_id": iid,
        "enabled": enabled,
        "pressure_score": round(score, 3),
        "block_new_buy": block,
        "tighten_exit": tighten,
        "trim_bias": min(0.8, score * 0.7) if tighten else 0.0,
        "stop_mult": float(os.getenv("DOWNPRESS_STOP_MULT", "0.60")) if tighten else 1.0,
        "reasons": reasons[:8],
        "rets": {k: rets.get(k) for k in ("r5", "r20", "r60", "last")},
        "sector_rets": sector_rets,
        "counter_signal": counter,
        "oilish": oilish,
    }
    _MEM[sym] = (now, res)
    if block:
        log.info(
            "[DOWNPRESS] BLOCK BUY %s score=%.2f — %s",
            sym,
            score,
            "; ".join(reasons[:3]) or "downtrend",
        )
    elif tighten:
        log.info(
            "[DOWNPRESS] TIGHTEN %s score=%.2f — %s",
            sym,
            score,
            "; ".join(reasons[:3]) or "weakness",
        )
    return dict(res)


def blocks_new_buy(symbol: str) -> tuple[bool, str]:
    """Hard gate — not subject to PAPER_RELAX_ALGO_RISK.

    Soft 20d/5d weakness used to only tighten the stop, so fortress still
    bought AAPL/AVGO-class dumps then stopped out at −1.7%. Block those
    entries unless a 5d bounce counter-signal is on.
    """
    a = assess_downward_pressure(symbol)
    if a.get("block_new_buy"):
        return True, "; ".join(a.get("reasons") or ["downward pressure"])
    block_tighten = os.getenv("DOWNPRESS_BLOCK_ON_TIGHTEN", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    if (
        block_tighten
        and a.get("tighten_exit")
        and not a.get("counter_signal")
    ):
        # Filling idle cash / fading the 1d head: only HARD dumps block.
        # Soft 20d/5d weakness was zeroing buy_candidates all midday.
        score = float(a.get("pressure_score") or 0.0)
        reasons = [str(r) for r in (a.get("reasons") or [])]
        hard = score >= 0.85 or any("hard" in r.lower() for r in reasons)
        skip_soft = os.getenv("DOWNPRESS_SOFT_OK_WHEN_UNDERDEPLOY", "false").lower() in (
            "1",
            "true",
            "yes",
        ) or os.getenv("FORTRESS_FADE_SKIP_SOFT_DOWNPRESS", "false").lower() in (
            "1",
            "true",
            "yes",
        )
        if skip_soft and not hard:
            return False, ""
        return True, "; ".join(reasons or ["soft downward pressure"])
    return False, ""


def exit_adjustments(symbol: str) -> dict[str, float]:
    """Stop multiplier + trim bias for open holdings."""
    a = assess_downward_pressure(symbol)
    return {
        "stop_mult": float(a.get("stop_mult") or 1.0),
        "trim_bias": float(a.get("trim_bias") or 0.0),
        "pressure_score": float(a.get("pressure_score") or 0.0),
        "tighten_exit": 1.0 if a.get("tighten_exit") else 0.0,
    }
