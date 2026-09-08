"""AI reviewer for bottom-fisher candidates (LLM + optional Tavily)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from typing import Any

from bottom_fisher.config import BottomFisherConfig
from utils import log

try:
    from intel.llm_signal_agent import _extract_json, _post_chat
except Exception:  # pragma: no cover
    _extract_json = None  # type: ignore[misc, assignment]
    _post_chat = None  # type: ignore[misc, assignment]


@dataclass
class BottomAIReview:
    ticker: str
    grade: str
    confidence: float
    verdict: str
    recovery_thesis: str
    catalyst_type: str
    risk_flags: list[str]
    hold_days: int
    ai_score: float

    def to_dict(self) -> dict:
        return asdict(self)


_GRADE_VAL = {"A": 1.0, "B": 0.82, "C": 0.65, "D": 0.45, "F": 0.15}


def _grade_to_score(grade: str) -> float:
    return _GRADE_VAL.get((grade or "C").strip().upper()[:1], 0.45)


def _fetch_context(ticker: str) -> str:
    try:
        from intel.ai_final_pick_review import fetch_tavily_snippet

        q = f"{ticker} stock turnaround recovery catalyst news"
        snip = fetch_tavily_snippet(q, max_chars=int(os.getenv("BOTTOM_FISHER_TAVILY_CHARS", "1800")))
        if snip:
            return snip
    except Exception:
        pass
    try:
        from intel.headline_fetch_parallel import fetch_all_headline_texts

        heads = fetch_all_headline_texts(ticker, finnhub_limit=15, news_limit=10, cramer_limit=5)
        return "\n".join(heads[:12])[:2000]
    except Exception:
        return ""


def review_bottom_candidate(row: dict[str, Any], cfg: BottomFisherConfig | None = None) -> BottomAIReview:
    """LLM grades a single bottom-fisher row."""
    cfg = cfg or BottomFisherConfig.from_env()
    sym = str(row.get("ticker", "")).upper()
    default = BottomAIReview(
        sym, "C", 0.0, "hold", "", "unknown", [], 5, 0.5
    )
    if not cfg.use_ai_review or _post_chat is None or _extract_json is None:
        return default

    ctx = _fetch_context(sym)
    payload = {
        "ticker": sym,
        "ret_60d_pct": round(100 * float(row.get("ret_60d", 0)), 2),
        "drawdown_52w_pct": round(100 * float(row.get("drawdown_52w", 0)), 2),
        "recovery_score": round(float(row.get("recovery_score", 0)), 3),
        "news_catalyst": round(float(row.get("catalyst_score", 0)), 3),
        "news_rationale": row.get("news_rationale", ""),
        "technical_rationale": row.get("recovery_rationale", ""),
        "top_headline": (row.get("top_headline") or "")[:300],
    }
    prompt = (
        "You are a contrarian equity analyst. A beaten-down stock may be a recovery candidate "
        "ONLY if catalyst + technical stabilization outweigh bankruptcy/dilution risk.\n"
        "Return JSON: grade (A-F), confidence (0-1), verdict (buy|hold|reject), "
        "recovery_thesis (1 sentence), catalyst_type (turnaround|news|technical|none), "
        "risk_flags (array of short strings), hold_days (int 1-30).\n"
        f"Candidate: {json.dumps(payload)}\n"
        f"Research snippets:\n{ctx[:2200]}"
    )
    try:
        raw = _post_chat(
            [
                {"role": "system", "content": "Reply with valid JSON only."},
                {"role": "user", "content": prompt},
            ]
        )
        js = _extract_json(raw)
        grade = str(js.get("grade", "C")).upper()[:1]
        conf = float(js.get("confidence", 0.0))
        verdict = str(js.get("verdict", "hold")).lower()
        thesis = str(js.get("recovery_thesis", ""))[:400]
        cat = str(js.get("catalyst_type", "unknown"))[:40]
        flags = js.get("risk_flags") if isinstance(js.get("risk_flags"), list) else []
        hold = int(js.get("hold_days", 5))
        ai_score = _grade_to_score(grade) * max(0.2, conf)
        if verdict == "reject":
            ai_score *= 0.35
        return BottomAIReview(
            sym, grade, conf, verdict, thesis, cat, [str(x)[:80] for x in flags[:6]], hold, float(ai_score)
        )
    except Exception as e:
        log.debug("[BOTTOM_FISHER] AI review %s: %s", sym, e)
        return default


def review_batch(rows: list[dict], cfg: BottomFisherConfig | None = None) -> list[BottomAIReview]:
    cfg = cfg or BottomFisherConfig.from_env()
    cap = cfg.max_ai_review
    ordered = sorted(
        rows,
        key=lambda r: -(
            float(r.get("composite_score", 0))
            + 0.3 * float(r.get("catalyst_score", 0))
            + 0.2 * float(r.get("recovery_score", 0))
        ),
    )
    out: list[BottomAIReview] = []
    for r in ordered[:cap]:
        out.append(review_bottom_candidate(r, cfg))
    return out
