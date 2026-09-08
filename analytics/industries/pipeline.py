"""Industry pipeline orchestrator — runs specialized logic per classification."""

from __future__ import annotations

import os
from typing import Any

from analytics.industries.base import IndustryContext
from analytics.industries.engine import build_context, get_factor_snapshot
from analytics.industries.integration import get_industry_profile
from analytics.industries.pipeline_models import IndustryPipelineResult
from analytics.industries.registry import get_handler
from analytics.industries.specialized import get_specialized


def _enabled() -> bool:
    return os.getenv("USE_INDUSTRY_PIPELINE", "true").lower() in ("1", "true", "yes")


def _row_features(row: Any) -> dict[str, float]:
    rf: dict[str, float] = {}
    if row is None:
        return rf
    if isinstance(row, dict):
        for k, v in row.items():
            if isinstance(v, (int, float)):
                rf[str(k)] = float(v)
        return rf
    try:
        import numpy as np

        for k in row.index:
            v = row.get(k)
            if isinstance(v, (int, float, np.floating)):
                rf[str(k)] = float(v)
    except Exception:
        pass
    return rf


def run_industry_pipeline(
    symbol: str,
    row: Any = None,
    *,
    macro_bundle: dict[str, Any] | None = None,
    news_headlines: list[str] | None = None,
) -> dict[str, Any]:
    """Execute specialized pipeline for primary + blended secondary industries."""
    sym = symbol.strip().upper()
    if not sym or not _enabled():
        return {"symbol": sym, "enabled": False, "score_delta": 0.0}

    profile = get_industry_profile(sym, news_headlines=news_headlines)
    blend = profile.get("blend_weights") or {}
    if not blend:
        primary = profile.get("primary_industry_id") or "unclassified"
        blend = {primary: 1.0}

    rf = _row_features(row)
    ctx_base = build_context(
        sym,
        macro_bundle=macro_bundle,
        news_headlines=news_headlines,
        row_features=rf,
    )
    macro = ctx_base.macro or get_factor_snapshot(macro_bundle)
    primary_iid = profile.get("primary_industry_id") or "unclassified"

    merged = IndustryPipelineResult()
    parts: list[dict[str, Any]] = []

    for iid, w in blend.items():
        handler = get_handler(str(iid))
        specialized = get_specialized(str(iid))
        ctx = IndustryContext(
            symbol=sym,
            sector=ctx_base.sector,
            yahoo_industry=ctx_base.yahoo_industry,
            market_cap=ctx_base.market_cap,
            macro=macro,
            news_headlines=news_headlines or [],
            row_features=rf,
            company_name=ctx_base.company_name,
            parent_symbol=ctx_base.parent_symbol,
            is_spinoff=ctx_base.is_spinoff,
            is_ipo=ctx_base.is_ipo,
        )
        part = specialized.run(ctx, handler)
        try:
            from analytics.industries.enhancements import get_enhancement

            enhancement = get_enhancement(str(iid))
            part = enhancement.enhance(part, ctx, handler)
        except Exception:
            pass
        weight = float(w)
        if iid != primary_iid:
            weight *= 0.85
        merged.merge_weighted(part, weight)
        parts.append(
            {
                "industry_id": iid,
                "weight": w,
                "effective_weight": weight,
                **part.to_dict(),
            }
        )

    # Enhancement-biased floor: avoid systematic score drag unless hard block
    if not merged.block_long and merged.score_delta < -0.02:
        merged.pipeline_notes.append(f"score_floor:{merged.score_delta:.4f}->-0.02")
        merged.score_delta = -0.02

    out = merged.to_dict()
    out.update(
        {
            "symbol": sym,
            "enabled": True,
            "industry_id": primary_iid,
            "industries": profile.get("industries"),
            "multi_industry": len(blend) > 1,
            "blend_parts": parts,
        }
    )
    return out


def industry_feature_weight_columns(symbol: str) -> dict[str, float]:
    """Static per-symbol ML feature multipliers from industry pipeline."""
    sym = symbol.strip().upper()
    if not sym:
        return {}
    try:
        pipe = run_industry_pipeline(sym)
        return dict(pipe.get("feature_weights") or {})
    except Exception:
        return {}


def enrich_training_feature_weights(df, symbol: str):
    """Add fpw_* columns (constant per symbol) for model training."""
    weights = industry_feature_weight_columns(symbol)
    if not weights:
        defaults = {
            "fpw_factor_rate": 1.0,
            "fpw_factor_expansion": 1.0,
            "fpw_industry_sympathy": 1.0,
            "fpw_combined_tilt": 1.0,
        }
        for k, v in defaults.items():
            if k not in df.columns:
                df[k] = v
        return df
    for k, v in weights.items():
        df[k] = float(v)
    return df


def apply_pipeline_to_score(
    symbol: str,
    score: float,
    p_up: float,
    row: Any = None,
    *,
    macro_bundle: dict | None = None,
    news_headlines: list[str] | None = None,
) -> tuple[float, float, dict[str, Any]]:
    """Apply pipeline score/p_up deltas; return updated values + metadata."""
    pipe = run_industry_pipeline(
        symbol,
        row,
        macro_bundle=macro_bundle,
        news_headlines=news_headlines,
    )
    w = float(os.getenv("RANK_W_INDUSTRY_PIPELINE", "0.11"))
    new_score = float(score) + w * float(pipe.get("score_delta") or 0.0)
    new_p_up = max(0.0, min(1.0, float(p_up) + float(pipe.get("p_up_delta") or 0.0)))
    return new_score, new_p_up, pipe


def family_rank_bias(
    symbol: str,
    *,
    macro_bundle: dict | None = None,
    row: dict | None = None,
    news_headlines: list[str] | None = None,
) -> float:
    """Rank-key bump for family forecast selection."""
    light = os.getenv("FAMILY_LIGHT_INDUSTRY", "true").lower() in ("1", "true", "yes")
    bias = 0.0
    if not light:
        pipe = run_industry_pipeline(symbol, row, macro_bundle=macro_bundle, news_headlines=news_headlines)
        w = float(os.getenv("FAMILY_W_INDUSTRY_BIAS", "0.08"))
        bias = w * float(pipe.get("family_bias") or 0.0)
    if os.getenv("USE_CATEGORY_DECISION", "true").lower() in ("1", "true", "yes"):
        try:
            from analytics.industries.category_decision import evaluate_category_decision

            rf = dict(row or {})
            rf.setdefault("industry_id", (rf.get("industry") or {}).get("primary"))
            cd = evaluate_category_decision(symbol, rf, macro_bundle, news_headlines)
            cw = float(os.getenv("FAMILY_W_CATEGORY_BIAS", "1.0"))
            bias += cw * float(cd.family_bias)
            bq = float(cd.buy_quality or 0.0)
            if bq > 0.55:
                bias += (bq - 0.5) * 0.06
            elif bq < 0.35:
                bias -= (0.5 - bq) * 0.05
        except Exception:
            pass
    return bias
