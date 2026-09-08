"""Project-wide industry wiring — use in paper sim, family forecast, training, risk, Monday playbook."""

from __future__ import annotations

import os
from typing import Any


def _enabled() -> bool:
    return os.getenv("USE_INDUSTRY_PROJECT_WIRING", "true").lower() in ("1", "true", "yes")


def _category_decision_enabled() -> bool:
    return os.getenv("USE_CATEGORY_DECISION", "true").lower() in ("1", "true", "yes")


def _apply_category_decision(
    symbol: str,
    score: float,
    p_up: float,
    row: dict | None,
    *,
    macro_bundle: dict | None = None,
    news_headlines: list[str] | None = None,
) -> tuple[float, float, dict[str, Any]]:
    """Apply taxonomy spec decision layer to score / probability."""
    if not _category_decision_enabled():
        return score, p_up, {}
    try:
        from analytics.industries.category_decision import evaluate_category_decision

        rf = dict(row or {})
        rf.setdefault("industry_id", (rf.get("industry") or {}).get("primary"))
        try:
            from analytics.industries.integration import get_industry_profile

            prof = get_industry_profile(sym, news_headlines=news_headlines)
            rf["blend_weights"] = prof.get("blend_weights") or {}
            rf["industries"] = prof.get("industries") or []
            rf["ai_confidence"] = prof.get("ai_confidence") or rf.get("ai_confidence")
        except Exception:
            pass
        cd = evaluate_category_decision(symbol, rf, macro_bundle, news_headlines)
        w = float(os.getenv("RANK_W_CATEGORY_DECISION", "1.0"))
        new_score = float(score) + w * float(cd.score_delta)
        new_p_up = max(0.0, min(1.0, float(p_up) + w * float(cd.p_up_delta)))
        return new_score, new_p_up, {"category_decision": cd.to_dict()}
    except Exception:
        return score, p_up, {}


def wire_paper_sim_row(row: dict[str, Any]) -> dict[str, Any]:
    """Full industry enrichment for a paper_sim report row."""
    if not _enabled():
        return row
    sym = str(row.get("ticker") or "").upper()
    if not sym:
        return row
    try:
        from analytics.industries.integration import enrich_report_row

        out = enrich_report_row(row)
    except Exception:
        out = dict(row)
    try:
        from analytics.industries.categories import category_slug_for_industry, get_category

        iid = (out.get("industry") or {}).get("primary") or "unclassified"
        slug = category_slug_for_industry(iid)
        cat = get_category(iid)
        out["category"] = {
            "number": getattr(cat, "CATEGORY_NUMBER", 0),
            "slug": slug,
            "name": getattr(cat, "DISPLAY_NAME", ""),
            "file": f"{slug}.py",
        }
        try:
            from analytics.industries.categories.specs import get_spec

            spec = get_spec(slug)
            if spec:
                out["category"]["spec"] = {
                    "sector_group": spec.sector_group,
                    "definition": spec.definition,
                    "algo_key_metric": spec.algo_key_metric,
                    "prediction_feature": spec.prediction_feature,
                    "correlation": spec.correlation,
                    "whole_group_movement": spec.whole_group_movement,
                    "metric_type": spec.metric_type,
                    "correlation_type": spec.correlation_type,
                }
        except Exception:
            pass
    except Exception:
        pass
    try:
        ns = (out.get("news_ai") or {}).get("top_bullish") or []
        headlines = list(dict.fromkeys(str(h) for h in ns if h))[:10] or None
        _, _, cd_meta = _apply_category_decision(
            sym, float(out.get("score") or 0.0), float(out.get("p_adj") or out.get("p_up") or 0.5),
            out, news_headlines=headlines,
        )
        if cd_meta.get("category_decision"):
            out["category_decision"] = cd_meta["category_decision"]
    except Exception:
        pass
    try:
        from analytics.industries.anchors import anchor_for_symbol

        anchor = anchor_for_symbol(sym)
        out = anchor.enhance_row(out)
    except Exception:
        pass
    return out


def wire_score(
    symbol: str,
    score: float,
    p_up: float,
    row: dict | None = None,
    *,
    macro_bundle: dict | None = None,
    news_headlines: list[str] | None = None,
    apply_pipeline: bool = True,
) -> tuple[float, float, dict[str, Any]]:
    """Apply pipeline (optional) + anchor score adjustments."""
    sym = symbol.strip().upper()
    s, p = float(score), float(p_up)
    meta: dict[str, Any] = {}
    if not _enabled() or not sym:
        return s, p, meta
    if apply_pipeline:
        try:
            from analytics.industries.pipeline import apply_pipeline_to_score

            s, p, meta = apply_pipeline_to_score(
                sym, s, p, row, macro_bundle=macro_bundle, news_headlines=news_headlines
            )
        except Exception:
            pass
    try:
        from analytics.industries.anchors import anchor_for_symbol

        anchor = anchor_for_symbol(sym)
        s, p = anchor.enhance_score(sym, s, p, row=row)
    except Exception:
        pass
    s, p, cd_meta = _apply_category_decision(
        sym, s, p, row, macro_bundle=macro_bundle, news_headlines=news_headlines
    )
    meta.update(cd_meta)
    return s, p, meta


def wire_training_frame(df, symbol: str, start_date: str, end_date: str | None):
    """Training path: industry comovement + pipeline fpw columns."""
    if not _enabled():
        return df
    try:
        from signals.train_feature_enrich import enrich_training_features

        return enrich_training_features(df, symbol, start_date, end_date)
    except Exception:
        return df


def wire_risk_result(symbol: str, risk: dict[str, Any]) -> dict[str, Any]:
    """Attach industry pipeline context to algo risk screen result."""
    if not _enabled():
        return risk
    sym = symbol.strip().upper()
    try:
        from analytics.industries.integration import get_industry_profile
        from analytics.industries.pipeline import run_industry_pipeline

        prof = get_industry_profile(sym)
        pipe = run_industry_pipeline(sym)
        out = dict(risk)
        out["industry"] = {
            "primary": prof.get("primary_industry_id"),
            "name": prof.get("industry_name"),
            "pipeline_block": pipe.get("block_long"),
            "pipeline_score_delta": pipe.get("score_delta"),
        }
        _, _, cd_meta = _apply_category_decision(sym, 0.0, 0.5)
        if cd_meta.get("category_decision"):
            out["category_decision"] = cd_meta["category_decision"]
        return out
    except Exception:
        return risk


def wire_monday_pick(row: dict[str, Any]) -> dict[str, Any]:
    """Enhance Monday playbook candidate row."""
    out = wire_paper_sim_row(row)
    sym = str(out.get("ticker") or "").upper()
    if sym:
        s = float(out.get("score") or 0.0)
        p = float(out.get("p_adj") or out.get("p_up") or 0.5)
        ns = (out.get("news_ai") or {}).get("top_bullish") or []
        new_s, new_p, _ = wire_score(sym, s, p, out, news_headlines=list(ns)[:10] if ns else None)
        out["score"] = new_s
        out["p_adj"] = new_p
    return out


def run_all_historical_smoke(*, limit: int | None = None) -> dict[str, Any]:
    """Smoke all 50 category modules on historical data."""
    from analytics.industries.categories import ALL_CATEGORIES, list_category_slugs

    slugs = [s for s in list_category_slugs() if s != "unclassified"]
    if limit:
        slugs = slugs[: int(limit)]
    results: list[dict[str, Any]] = []
    passed = 0
    for slug in slugs:
        cat = ALL_CATEGORIES.get(slug)
        if not cat:
            continue
        try:
            rep = cat.historical_smoke()
        except Exception as e:
            rep = {"category_slug": slug, "ok": False, "error": str(e), "checks": []}
        results.append(rep)
        if rep.get("ok"):
            passed += 1
    total = len(results)
    return {
        "passed": passed,
        "total": total,
        "all_ok": passed == total and total > 0,
        "results": results,
    }
