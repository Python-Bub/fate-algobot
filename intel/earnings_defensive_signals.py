"""Pre-earnings defensive language — management hedging often precedes misses."""

from __future__ import annotations

import os
import re
from datetime import date
from typing import Any

import numpy as np

DEFENSIVE_PATTERNS = (
    r"didn'?t work",
    r"did not work",
    r"don'?t worry",
    r"do not worry",
    r"might not be (?:that |as )?high",
    r"may not be (?:that |as )?high",
    r"won'?t be (?:that |as )?high",
    r"not (?:as )?strong as (?:we |you )?(?:hoped|expected|anticipated)",
    r"below (?:our |street )?expectations",
    r"challenging quarter",
    r"difficult quarter",
    r"headwinds?",
    r"took longer than expected",
    r"softness in",
    r"weaker than expected",
    r"guidance (?:cut|lower|reduced)",
    r"revising (?:our )?outlook",
    r"macro (?:is|has been) (?:tough|challenging)",
    r"transitional quarter",
    r"one[- ]time (?:charges|headwinds)",
    r"not where we want",
    r"disappointing",
)

_COMPILED = [re.compile(p, re.I) for p in DEFENSIVE_PATTERNS]


def _enabled() -> bool:
    return os.getenv("USE_EARNINGS_DEFENSIVE", "true").lower() in ("1", "true", "yes")


def _pre_earnings_window_days() -> int:
    return int(os.getenv("EARNINGS_DEFENSIVE_WINDOW_DAYS", "14"))


def _scan_text(text: str) -> list[str]:
    if not text or not str(text).strip():
        return []
    t = str(text)
    hits: list[str] = []
    for rx in _COMPILED:
        m = rx.search(t)
        if m:
            hits.append(m.group(0).lower())
    return hits


def scan_documents(documents: list[str]) -> dict[str, Any]:
    """Score defensive phrases across headlines / transcript snippets."""
    all_hits: list[str] = []
    for doc in documents or []:
        all_hits.extend(_scan_text(doc))
    unique = list(dict.fromkeys(all_hits))
    intensity = min(1.0, len(unique) * 0.22 + (0.15 if len(unique) >= 3 else 0.0))
    return {
        "hits": unique[:12],
        "intensity": float(intensity),
        "n_hits": len(unique),
    }


def assess_pre_earnings_defensive(
    symbol: str,
    *,
    documents: list[str] | None = None,
    days_to_earnings: int | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Bearish adjustment when defensive talk appears before earnings."""
    sym = symbol.strip().upper()
    base = {
        "ticker": sym,
        "enabled": _enabled(),
        "active": False,
        "intensity": 0.0,
        "score_delta": 0.0,
        "p_up_delta": 0.0,
        "block_long": False,
        "block_reason": None,
        "hits": [],
        "days_to_earnings": days_to_earnings,
    }
    if not _enabled() or not sym:
        return base

    dte = days_to_earnings
    if dte is None:
        try:
            from intel.earnings_calendar import days_to_next_earnings

            _, dte = days_to_next_earnings(sym, as_of=as_of)
        except Exception:
            dte = None
    if dte is None or dte < 0 or dte > _pre_earnings_window_days():
        return base

    docs = list(documents or [])
    if not docs:
        try:
            from news_reader import fetch_news

            docs = [
                (a.get("headline", "") + " " + a.get("summary", "")).strip()
                for a in fetch_news(sym)
            ]
        except Exception:
            docs = []

    scan = scan_documents(docs)
    intensity = float(scan.get("intensity") or 0.0)
    if intensity <= 0:
        return base

    proximity = 1.0 - (float(dte) / max(_pre_earnings_window_days(), 1))
    adj_intensity = min(1.0, intensity * (0.65 + 0.35 * proximity))
    w_score = float(os.getenv("RANK_W_EARNINGS_DEFENSIVE", "0.18"))
    w_p = float(os.getenv("EARNINGS_DEFENSIVE_P_DELTA", "0.08"))
    score_delta = -w_score * adj_intensity
    p_delta = -w_p * adj_intensity

    block = False
    block_reason = None
    if adj_intensity >= float(os.getenv("EARNINGS_DEFENSIVE_BLOCK_INTENSITY", "0.55")):
        block = os.getenv("EARNINGS_DEFENSIVE_BLOCK", "true").lower() in ("1", "true", "yes")
        block_reason = (
            f"Defensive pre-earnings language ({dte}d to report): "
            + ", ".join(scan.get("hits") or [])[:3]
        )

    return {
        **base,
        "active": True,
        "intensity": adj_intensity,
        "score_delta": score_delta,
        "p_up_delta": p_delta,
        "block_long": block,
        "block_reason": block_reason,
        "hits": scan.get("hits") or [],
        "days_to_earnings": dte,
        "proximity_boost": proximity,
    }


def defensive_factor(symbol: str, documents: list[str] | None = None) -> float:
    """Scalar bearish factor in [0, 1] for fusion-style blending."""
    res = assess_pre_earnings_defensive(symbol, documents=documents)
    if not res.get("active"):
        return 0.0
    return -float(np.tanh(float(res.get("intensity") or 0.0)))
