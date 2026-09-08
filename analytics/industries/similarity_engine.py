"""Soft industry matching — companies rarely fit one bucket exactly.

Uses TF-IDF cosine similarity between company context and all 50 category
definition profiles, producing multi-industry blend weights (not hard labels).
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Any

import numpy as np

ROOT_PROFILES: dict[str, str] | None = None
_VECTORIZER = None
_PROFILE_MATRIX = None
_PROFILE_IDS: list[str] | None = None


def _enabled() -> bool:
    return os.getenv("USE_INDUSTRY_SIMILARITY", "true").lower() in ("1", "true", "yes")


def _tokenize(text: str) -> str:
    t = re.sub(r"[^a-z0-9\s\-]", " ", str(text or "").lower())
    return re.sub(r"\s+", " ", t).strip()


@lru_cache(maxsize=1)
def category_text_profiles() -> dict[str, str]:
    """One text profile per internal industry_id from specs + handlers."""
    from analytics.industries.categories.specs import CATEGORY_SPECS
    from analytics.industries.registry import get_handler

    profiles: dict[str, str] = {}
    for spec in CATEGORY_SPECS.values():
        iid = spec.industry_id
        try:
            h = get_handler(iid)
            yahoo = " ".join(list(h.YAHOO_PATTERNS)[:6]) if h.YAHOO_PATTERNS else ""
            leaders = " ".join(list(h.LEADER_TICKERS)[:4]) if h.LEADER_TICKERS else ""
            bull = " ".join(list(h.NEWS_BULL_PHRASES)[:4]) if h.NEWS_BULL_PHRASES else ""
        except Exception:
            yahoo = leaders = bull = ""
        profiles[iid] = _tokenize(
            " ".join(
                [
                    spec.display_name,
                    spec.sector_group,
                    spec.definition,
                    spec.algo_key_metric,
                    spec.prediction_feature,
                    spec.correlation,
                    " ".join(spec.group_keywords),
                    " ".join(spec.bull_keywords),
                    yahoo,
                    leaders,
                    bull,
                ]
            )
        )
    return profiles


def _ensure_vectorizer():
    global _VECTORIZER, _PROFILE_MATRIX, _PROFILE_IDS
    if _PROFILE_MATRIX is not None:
        return
    from sklearn.feature_extraction.text import TfidfVectorizer

    profiles = category_text_profiles()
    _PROFILE_IDS = sorted(profiles.keys())
    corpus = [profiles[iid] for iid in _PROFILE_IDS]
    _VECTORIZER = TfidfVectorizer(max_features=4000, ngram_range=(1, 2), min_df=1)
    _PROFILE_MATRIX = _VECTORIZER.fit_transform(corpus)


def company_context_text(
    symbol: str,
    base_row: dict[str, Any] | None = None,
    *,
    news_headlines: list[str] | None = None,
) -> str:
    row = base_row or {}
    parts = [
        symbol,
        row.get("short_name"),
        row.get("industry_name"),
        row.get("yahoo_industry"),
        row.get("sector"),
        row.get("business_summary"),
        " ".join(row.get("tags") or []),
    ]
    if news_headlines:
        parts.extend(news_headlines[:8])
    reasons = row.get("reasons") or []
    if reasons:
        parts.append(" ".join(str(r) for r in reasons[:4]))
    return _tokenize(" ".join(str(p) for p in parts if p))


def similarity_scores(
    symbol: str,
    base_row: dict[str, Any] | None = None,
    *,
    news_headlines: list[str] | None = None,
) -> dict[str, float]:
    """Cosine similarity of company context vs each industry profile."""
    if not _enabled():
        return {}
    _ensure_vectorizer()
    text = company_context_text(symbol, base_row, news_headlines=news_headlines)
    if not text:
        return {}
    vec = _VECTORIZER.transform([text])
    sims = (_PROFILE_MATRIX @ vec.T).toarray().ravel()
    return {iid: float(max(0.0, sim)) for iid, sim in zip(_PROFILE_IDS or [], sims)}


def _softmax_weights(scores: dict[str, float], *, temperature: float, top_k: int) -> dict[str, float]:
    if not scores:
        return {}
    top_k = max(1, int(top_k))
    temperature = max(0.04, float(temperature))
    ranked = sorted(scores.items(), key=lambda x: -x[1])[:top_k]
    ids, vals = zip(*ranked)
    arr = np.asarray(vals, dtype=np.float64)
    if arr.max() <= 1e-9:
        w = np.ones(len(arr)) / len(arr)
    else:
        z = arr / temperature
        z -= z.max()
        ex = np.exp(z)
        w = ex / ex.sum()
    return {str(iid): round(float(wi), 4) for iid, wi in zip(ids, w)}


def merge_with_base(
    symbol: str,
    base_row: dict[str, Any],
    sim_weights: dict[str, float],
    *,
    news_headlines: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """Blend rule/AI primary with similarity spread for hybrid companies."""
    base_iid = str(base_row.get("industry_id") or base_row.get("primary_industry_id") or "unclassified")
    base_conf = float(base_row.get("confidence") or base_row.get("ai_confidence") or 0.0)

    if not sim_weights:
        if base_iid != "unclassified":
            inds = [{"industry_id": base_iid, "weight": 1.0, "role": "primary", "rationale": "base_only"}]
            return inds, {base_iid: 1.0}
        return [], {}

    top_k = int(os.getenv("INDUSTRY_SIMILARITY_TOP_K", "4"))
    temperature = float(os.getenv("INDUSTRY_SIMILARITY_TEMP", "0.15"))

    if base_iid == "unclassified" or base_conf < 0.45:
        blend = _softmax_weights(sim_weights, temperature=temperature, top_k=top_k)
        rationale = "similarity_primary"
        base_share = 0.0
    elif base_conf >= 0.85:
        blend = _softmax_weights(sim_weights, temperature=temperature, top_k=min(3, top_k))
        base_share = float(os.getenv("INDUSTRY_SIMILARITY_BASE_SHARE_HIGH", "0.72"))
        rationale = "high_conf_base+similarity"
    else:
        blend = _softmax_weights(sim_weights, temperature=temperature, top_k=top_k)
        base_share = float(os.getenv("INDUSTRY_SIMILARITY_BASE_SHARE_MED", "0.50"))
        rationale = "medium_conf_blend"

    if base_share > 0 and base_iid != "unclassified":
        rest = 1.0 - base_share
        for k in list(blend.keys()):
            blend[k] *= rest
        blend[base_iid] = blend.get(base_iid, 0.0) + base_share

    total = sum(blend.values()) or 1.0
    blend = {k: round(v / total, 4) for k, v in blend.items() if v > 0.005}
    total = sum(blend.values()) or 1.0
    blend = {k: round(v / total, 4) for k, v in blend.items()}

    ranked = sorted(blend.items(), key=lambda x: -x[1])
    if base_share > 0 and base_share < 1.0 and len(ranked) < 2 and sim_weights:
        alt = sorted(sim_weights.items(), key=lambda x: -x[1])
        for iid, _ in alt:
            if iid != base_iid and iid not in blend:
                blend[iid] = round(max(0.08, 1.0 - base_share), 4)
                blend[base_iid] = round(base_share, 4)
                break
        total = sum(blend.values()) or 1.0
        blend = {k: round(v / total, 4) for k, v in blend.items()}
        ranked = sorted(blend.items(), key=lambda x: -x[1])
    inds: list[dict[str, Any]] = []
    for i, (iid, w) in enumerate(ranked[:5]):
        inds.append(
            {
                "industry_id": iid,
                "weight": w,
                "role": "primary" if i == 0 else "secondary",
                "rationale": rationale if i == 0 else "similarity_neighbor",
            }
        )
    return inds, blend


def enrich_blend(
    symbol: str,
    base_row: dict[str, Any],
    existing_blend: dict[str, float] | None = None,
    *,
    news_headlines: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, float], dict[str, float]]:
    """Return (industries list, final blend, raw similarity scores)."""
    from analytics.industries.hybrid_symbols import hybrid_blend

    preset = hybrid_blend(symbol)
    sims = similarity_scores(symbol, base_row, news_headlines=news_headlines)
    if preset:
        inds = [
            {
                "industry_id": iid,
                "weight": w,
                "role": "primary" if i == 0 else "secondary",
                "rationale": "hybrid_preset" if i == 0 else "hybrid_neighbor",
            }
            for i, (iid, w) in enumerate(sorted(preset.items(), key=lambda x: -x[1]))
        ]
        blend = dict(preset)
    else:
        inds, blend = merge_with_base(symbol, base_row, sims, news_headlines=news_headlines)

    if existing_blend and len(existing_blend) > 1:
        alpha = float(os.getenv("INDUSTRY_SIMILARITY_AI_BLEND", "0.35"))
        merged: dict[str, float] = {}
        all_ids = set(existing_blend) | set(blend)
        for iid in all_ids:
            merged[iid] = (1.0 - alpha) * existing_blend.get(iid, 0.0) + alpha * blend.get(iid, 0.0)
        total = sum(merged.values()) or 1.0
        blend = {k: round(v / total, 4) for k, v in merged.items() if v > 0.008}
        total = sum(blend.values()) or 1.0
        blend = {k: round(v / total, 4) for k, v in sorted(blend.items(), key=lambda x: -x[1])[:5]}
        ranked = sorted(blend.items(), key=lambda x: -x[1])
        inds = [
            {
                "industry_id": iid,
                "weight": w,
                "role": "primary" if i == 0 else "secondary",
                "rationale": "ai+similarity" if i == 0 else "blend_neighbor",
            }
            for i, (iid, w) in enumerate(ranked)
        ]

    return inds, blend, sims


def nearest_categories(
    symbol: str,
    base_row: dict[str, Any] | None = None,
    *,
    top_k: int = 5,
    news_headlines: list[str] | None = None,
) -> list[tuple[str, float]]:
    sims = similarity_scores(symbol, base_row, news_headlines=news_headlines)
    return sorted(sims.items(), key=lambda x: -x[1])[:top_k]
