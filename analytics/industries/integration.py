"""Unified industry profile API — use in paper sim, family forecast, training, risk."""

from __future__ import annotations

import os
from typing import Any

from analytics.industries.ai_registry import (
    get_symbol_industries,
    industry_blend_weights,
    merge_ai_into_industry_row,
    primary_industry_id,
)
from analytics.industries.classifier import classify_ticker


def get_industry_profile(
    symbol: str,
    *,
    use_ai: bool = True,
    use_cache: bool = True,
    news_headlines: list[str] | None = None,
) -> dict[str, Any]:
    """Full industry view: primary + secondary + blend weights + handler metadata."""
    sym = symbol.strip().upper()
    row = classify_ticker(
        sym,
        use_cache=use_cache,
        use_yfinance=False,
        news_headlines=news_headlines,
    )
    if (row.get("industry_id") == "unclassified" or not row.get("industry_id")) and os.getenv(
        "INDUSTRY_YF_FALLBACK", "true"
    ).lower() in ("1", "true", "yes"):
        try:
            row = classify_ticker(
                sym,
                use_cache=False,
                use_yfinance=True,
                news_headlines=news_headlines,
            )
        except Exception:
            pass
    if use_ai:
        row = merge_ai_into_industry_row(sym, row)

    if (not row.get("industries") or row.get("industry_id") == "unclassified") and os.getenv(
        "USE_INDUSTRY_NEURAL", "true"
    ).lower() in ("1", "true", "yes"):
        try:
            from analytics.industries.neural_classifier import classify_symbol_neural

            neural = classify_symbol_neural(sym, persist=False)
            if neural.get("industries"):
                row = dict(row)
                row["industries"] = neural["industries"]
                row["primary_industry_id"] = neural["industries"][0]["industry_id"]
                row["industry_id"] = row["primary_industry_id"]
                row["confidence"] = max(float(row.get("confidence") or 0), float(neural.get("confidence") or 0))
                row["reasons"] = list(row.get("reasons") or []) + ["neural_mlp"]
        except Exception:
            pass

    inds = row.get("industries") or get_symbol_industries(sym)
    if not inds and row.get("industry_id") and row.get("industry_id") != "unclassified":
        inds = [
            {
                "industry_id": row["industry_id"],
                "weight": 1.0,
                "role": "primary",
                "rationale": "rule_based",
            }
        ]

    blend = industry_blend_weights(sym) or {i["industry_id"]: float(i["weight"]) for i in inds}
    similarity_scores: dict[str, float] = {}
    similarity_neighbors: list[tuple[str, float]] = []

    try:
        if os.getenv("USE_INDUSTRY_SIMILARITY", "true").lower() in ("1", "true", "yes"):
            from analytics.industries.similarity_engine import enrich_blend

            sim_inds, sim_blend, similarity_scores = enrich_blend(
                sym, row, blend if len(blend) > 1 else None, news_headlines=news_headlines
            )
            if sim_inds and sim_blend:
                inds = sim_inds
                blend = sim_blend
                row = dict(row)
                row["industries"] = inds
                row["primary_industry_id"] = inds[0]["industry_id"]
                row["industry_id"] = inds[0]["industry_id"]
                row["secondary_industry_ids"] = [i["industry_id"] for i in inds[1:]]
                row["reasons"] = list(row.get("reasons") or []) + ["similarity_blend"]
            similarity_neighbors = sorted(similarity_scores.items(), key=lambda x: -x[1])[:5]
    except Exception:
        pass

    try:
        if os.getenv("USE_INDUSTRY_RL", "true").lower() in ("1", "true", "yes"):
            from analytics.industries.industry_rl import apply_rl_to_blend

            blend = apply_rl_to_blend(sym, blend)
            if inds:
                inds = sorted(
                    [{"industry_id": iid, "weight": w, "role": "primary" if i == 0 else "secondary", "rationale": "rl_adjusted" if i == 0 else "rl_neighbor"} for i, (iid, w) in enumerate(sorted(blend.items(), key=lambda x: -x[1]))],
                    key=lambda x: -x["weight"],
                )
                if inds:
                    inds[0]["role"] = "primary"
    except Exception:
        pass

    primary = primary_industry_id(sym) or str(row.get("industry_id") or "unclassified")
    if blend:
        primary = max(blend.items(), key=lambda x: x[1])[0]

    return {
        "symbol": sym,
        "primary_industry_id": primary,
        "industry_id": primary,
        "industries": inds,
        "blend_weights": blend,
        "similarity_scores": similarity_scores,
        "similarity_neighbors": [{"industry_id": i, "score": round(s, 4)} for i, s in similarity_neighbors],
        "industry_name": row.get("industry_name"),
        "etf_proxy": row.get("etf_proxy"),
        "comovement_mode": row.get("comovement_mode"),
        "confidence": float(row.get("confidence") or 0.0),
        "ai_confidence": float(row.get("ai_confidence") or 0.0),
        "secondary_industry_ids": row.get("secondary_industry_ids") or [i["industry_id"] for i in inds[1:]],
        "rate_sensitive": bool(row.get("rate_sensitive")),
        "nasdaq_heavy": bool(row.get("nasdaq_heavy")),
        "source": row.get("ai_source") or (row.get("reasons") or ["rules"])[0],
    }


def blended_rank_adjustment(
    symbol: str,
    row_features: dict | None = None,
    *,
    macro_bundle: dict | None = None,
    news_headlines: list[str] | None = None,
) -> dict[str, Any]:
    """Score delta blended across primary + secondary industries."""
    import os

    from analytics.industries.base import IndustryContext
    from analytics.industries.engine import build_context, get_factor_snapshot
    from analytics.industries.registry import get_handler

    profile = get_industry_profile(symbol, news_headlines=news_headlines)
    blend = profile.get("blend_weights") or {}
    if not blend:
        iid = profile.get("primary_industry_id") or "unclassified"
        blend = {iid: 1.0}

    rf = row_features or {}
    sym = symbol.strip().upper()
    ctx_base = build_context(sym, macro_bundle=macro_bundle, news_headlines=news_headlines, row_features=rf)
    industry_z = float(rf.get("industry_z_20", 0.0))
    residual = float(rf.get("industry_residual_1d", 0.0))

    total_delta = 0.0
    parts: list[dict[str, Any]] = []
    primary_iid = profile.get("primary_industry_id")

    for iid, w in blend.items():
        handler = get_handler(str(iid))
        ctx = IndustryContext(
            symbol=sym,
            sector=ctx_base.sector,
            yahoo_industry=ctx_base.yahoo_industry,
            market_cap=ctx_base.market_cap,
            macro=ctx_base.macro or get_factor_snapshot(macro_bundle),
            news_headlines=news_headlines or [],
            row_features=rf,
            company_name=ctx_base.company_name,
        )
        factors = handler.compute_factor_tilts(ctx)
        comove = handler.compute_comovement(ctx, industry_z=industry_z, residual=residual)
        news_tilt = handler.news_factor_tilt(ctx)
        score_delta = handler.rank_score_delta(ctx, factors, comove, news_tilt)
        if iid != primary_iid:
            score_delta *= 0.85
        # Enhancement bias: handler reversion can drag scores; floor mild penalties
        if score_delta < -0.025:
            score_delta = -0.025
        part_delta = float(score_delta) * float(w)
        total_delta += part_delta
        parts.append(
            {
                "industry_id": iid,
                "weight": w,
                "delta": part_delta,
                "score_delta": score_delta,
                "factor_combined": factors.combined,
            }
        )

    primary_part = parts[0] if parts else {}
    pipeline: dict[str, Any] = {}
    try:
        from analytics.industries.pipeline import run_industry_pipeline

        pipeline = run_industry_pipeline(
            sym,
            rf,
            macro_bundle=macro_bundle,
            news_headlines=news_headlines,
        )
        pw = float(os.getenv("RANK_W_INDUSTRY_PIPELINE", "0.11"))
        total_delta += pw * float(pipeline.get("score_delta") or 0.0)
    except Exception:
        pipeline = {}

    category_decision: dict[str, Any] = {}
    try:
        if os.getenv("USE_CATEGORY_DECISION", "true").lower() in ("1", "true", "yes"):
            from analytics.industries.category_decision import evaluate_category_decision

            rf.setdefault("industry_id", primary_iid)
            try:
                prof_blend = profile.get("blend_weights") or blend
                rf["blend_weights"] = prof_blend
                rf["industries"] = profile.get("industries") or []
            except Exception:
                pass
            cd = evaluate_category_decision(sym, rf, macro_bundle, news_headlines)
            cw = float(os.getenv("RANK_W_CATEGORY_DECISION", "1.0"))
            total_delta += cw * float(cd.score_delta)
            category_decision = cd.to_dict()
    except Exception:
        pass

    return {
        "industry_id": primary_iid,
        "industries": profile.get("industries"),
        "score_delta": total_delta,
        "multi_industry": len(blend) > 1,
        "blend_parts": parts,
        "factor_tilts": {"combined": primary_part.get("factor_combined", 0.0)},
        "sympathy": {},
        "beta": rf.get("industry_beta_60", 1.0),
        "pipeline": pipeline,
        "category_decision": category_decision,
    }


def family_industry_note(symbol: str) -> str:
    """Short human-readable industry line for family forecast."""
    p = get_industry_profile(symbol)
    primary = p.get("primary_industry_id") or "unclassified"
    secs = p.get("secondary_industry_ids") or []
    name = p.get("industry_name") or primary.replace("_", " ").title()
    if secs:
        sec_txt = ", ".join(s.replace("_", " ") for s in secs[:2])
        return f"{name} (+ {sec_txt})"
    return str(name)


def enrich_report_row(row: dict) -> dict:
    """Attach industry block to a paper_sim / family forecast row."""
    sym = str(row.get("ticker") or "").upper()
    if not sym:
        return row
    prof = get_industry_profile(sym)
    out = dict(row)
    out["industry"] = {
        "primary": prof.get("primary_industry_id"),
        "name": prof.get("industry_name"),
        "etf": prof.get("etf_proxy"),
        "mode": prof.get("comovement_mode"),
        "industries": prof.get("industries"),
        "confidence": prof.get("confidence"),
        "ai_confidence": prof.get("ai_confidence"),
    }
    try:
        from analytics.industries.pipeline import run_industry_pipeline

        pipe = run_industry_pipeline(sym, row)
        out["industry_pipeline"] = {
            "score_delta": pipe.get("score_delta"),
            "p_up_delta": pipe.get("p_up_delta"),
            "block_long": pipe.get("block_long"),
            "warn_long": pipe.get("warn_long"),
            "family_bias": pipe.get("family_bias"),
            "notes": (pipe.get("pipeline_notes") or [])[:6],
        }
    except Exception:
        pass
    try:
        from analytics.industries.category_decision import evaluate_category_decision

        headlines = None
        ns = (out.get("news_ai") or {}).get("top_bullish") or []
        if ns:
            headlines = [str(h) for h in ns[:10]]
        cd = evaluate_category_decision(sym, out, None, headlines)
        out["category_decision"] = cd.to_dict()
    except Exception:
        pass
    return out


def blended_pipeline_actions(
    symbol: str,
    row_features: dict | None = None,
    *,
    macro_bundle: dict | None = None,
    news_headlines: list[str] | None = None,
) -> dict[str, Any]:
    """Full specialized pipeline output (gates, ML weights, family bias)."""
    from analytics.industries.pipeline import run_industry_pipeline

    return run_industry_pipeline(
        symbol,
        row_features,
        macro_bundle=macro_bundle,
        news_headlines=news_headlines,
    )
