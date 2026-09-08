"""Neural soft industry classifier — Yahoo context + TF-IDF + MLP blend (no OpenAI cap).

Trains on bootstrap registry, hybrid presets, overrides, and RL-adjusted labels.
At inference: combines similarity prior with MLP softmax blend prediction.
"""

from __future__ import annotations

import json
import os
import pickle
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "models" / "industry_neural"
MODEL_PATH = MODEL_DIR / "blend_mlp.pkl"
META_PATH = MODEL_DIR / "blend_mlp_meta.json"


def _enabled() -> bool:
    return os.getenv("USE_INDUSTRY_NEURAL", "true").lower() in ("1", "true", "yes")


def _industry_ids() -> list[str]:
    from analytics.industry_taxonomy import all_industry_ids

    ids = [i for i in all_industry_ids() if i != "unclassified"]
    return sorted(ids)


def _yahoo_context(symbol: str) -> dict[str, Any]:
    from intel.industry_ai_classifier import fetch_company_context

    return fetch_company_context(symbol)


def _feature_text(symbol: str, ctx: dict[str, Any] | None = None) -> str:
    from analytics.industries.similarity_engine import company_context_text

    ctx = ctx or _yahoo_context(symbol)
    row = {
        "short_name": ctx.get("short_name") or ctx.get("long_name"),
        "yahoo_industry": ctx.get("industry"),
        "sector": ctx.get("sector"),
        "business_summary": ctx.get("summary"),
    }
    headlines = ctx.get("news_headlines") or []
    snippets = " ".join(str(s) for s in (ctx.get("snippets") or [])[:3])
    base = company_context_text(symbol, row, news_headlines=headlines)
    return f"{base} {snippets}".strip()


def _collect_training_samples() -> tuple[list[str], list[dict[str, float]]]:
    """Build (text, blend_dict) training pairs from all local sources."""
    from analytics.industries.ai_registry import load_ai_registry, normalize_industries
    from analytics.industries.hybrid_symbols import HYBRID_BLEND
    from analytics.industries.classifier import load_overrides, load_industry_map
    from analytics.industry_taxonomy import load_catalog

    catalog = load_catalog()
    texts: list[str] = []
    blends: list[dict[str, float]] = []
    seen: set[str] = set()

    def _add(sym: str, blend: dict[str, float], ctx: dict | None = None) -> None:
        sym = sym.strip().upper()
        if not sym or sym in seen or not blend:
            return
        clean = {k: float(v) for k, v in blend.items() if k in catalog and float(v) > 0}
        if not clean:
            return
        total = sum(clean.values()) or 1.0
        clean = {k: round(v / total, 4) for k, v in clean.items()}
        texts.append(_feature_text(sym, ctx))
        blends.append(clean)
        seen.add(sym)

    reg = load_ai_registry(reload=True)
    for sym, row in reg.items():
        inds = normalize_industries(row.get("industries"))
        if inds:
            _add(sym, {i["industry_id"]: i["weight"] for i in inds})

    for sym, blend in HYBRID_BLEND.items():
        _add(sym, blend)

    for sym, iid in load_overrides().items():
        _add(sym, {iid: 1.0})

    imap = load_industry_map()
    for sym, row in imap.items():
        iid = str(row.get("industry_id") or "")
        conf = float(row.get("confidence") or 0.0)
        if iid and iid != "unclassified" and conf >= 0.55:
            _add(sym, {iid: 1.0})

    return texts, blends


def train_neural_classifier(*, min_samples: int = 40) -> dict[str, Any]:
    """Train MLP blend regressor on TF-IDF features."""
    if not _enabled():
        return {"ok": False, "reason": "disabled"}

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.neural_network import MLPRegressor

    ids = _industry_ids()
    texts, blends = _collect_training_samples()
    if len(texts) < min_samples:
        return {"ok": False, "reason": f"too_few_samples:{len(texts)}", "need": min_samples}

    vec = TfidfVectorizer(max_features=6000, ngram_range=(1, 2), min_df=1)
    X = vec.fit_transform(texts).toarray()
    Y = np.zeros((len(blends), len(ids)), dtype=np.float64)
    id_idx = {iid: j for j, iid in enumerate(ids)}
    for i, blend in enumerate(blends):
        for iid, w in blend.items():
            if iid in id_idx:
                Y[i, id_idx[iid]] = w

    mlp = MLPRegressor(
        hidden_layer_sizes=(256, 128, 64),
        activation="relu",
        max_iter=int(os.getenv("INDUSTRY_NEURAL_EPOCHS", "400")),
        early_stopping=True,
        validation_fraction=0.12,
        random_state=42,
        learning_rate_init=float(os.getenv("INDUSTRY_NEURAL_LR", "0.001")),
    )
    mlp.fit(X, Y)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with MODEL_PATH.open("wb") as f:
        pickle.dump({"vectorizer": vec, "model": mlp, "industry_ids": ids}, f)
    meta = {
        "samples": len(texts),
        "industries": len(ids),
        "loss": float(getattr(mlp, "loss_", 0.0) or 0.0),
        "n_iter": int(getattr(mlp, "n_iter_", 0) or 0),
    }
    META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"ok": True, **meta}


@lru_cache(maxsize=1)
def _load_model() -> dict | None:
    if not MODEL_PATH.is_file():
        return None
    try:
        with MODEL_PATH.open("rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def predict_neural_blend(
    symbol: str,
    *,
    ctx: dict[str, Any] | None = None,
    top_k: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, float], float]:
    """Return (industries list, blend dict, confidence)."""
    if not _enabled():
        return [], {}, 0.0
    bundle = _load_model()
    if not bundle:
        return [], {}, 0.0

    top_k = top_k or int(os.getenv("INDUSTRY_NEURAL_TOP_K", "4"))
    ids: list[str] = bundle["industry_ids"]
    vec = bundle["vectorizer"]
    mlp = bundle["model"]

    text = _feature_text(symbol, ctx)
    X = vec.transform([text]).toarray()
    raw = mlp.predict(X)[0]
    raw = np.clip(raw, 0.0, None)
    if raw.sum() <= 1e-9:
        return [], {}, 0.0
    probs = raw / raw.sum()

    order = np.argsort(-probs)[:top_k]
    blend: dict[str, float] = {}
    for j in order:
        if probs[j] >= 0.04:
            blend[ids[j]] = round(float(probs[j]), 4)
    total = sum(blend.values()) or 1.0
    blend = {k: round(v / total, 4) for k, v in blend.items()}
    ranked = sorted(blend.items(), key=lambda x: -x[1])
    inds = [
        {
            "industry_id": iid,
            "weight": w,
            "role": "primary" if i == 0 else "secondary",
            "rationale": "neural_mlp" if i == 0 else "neural_neighbor",
        }
        for i, (iid, w) in enumerate(ranked)
    ]
    conf = float(ranked[0][1]) if ranked else 0.0
    return inds, blend, conf


def classify_symbol_neural(
    symbol: str,
    *,
    ctx: dict[str, Any] | None = None,
    persist: bool = False,
) -> dict[str, Any]:
    """Full neural classification result compatible with AI registry upsert."""
    from analytics.industries.similarity_engine import enrich_blend

    sym = symbol.strip().upper()
    ctx = ctx or _yahoo_context(sym)
    base_row = {
        "industry_id": ctx.get("industry") or "unclassified",
        "yahoo_industry": ctx.get("industry"),
        "sector": ctx.get("sector"),
        "confidence": 0.5,
        "business_summary": ctx.get("summary"),
    }
    sim_inds, sim_blend, _ = enrich_blend(sym, base_row, news_headlines=ctx.get("news_headlines"))
    n_inds, n_blend, n_conf = predict_neural_blend(sym, ctx=ctx)

    alpha = float(os.getenv("INDUSTRY_NEURAL_BLEND_ALPHA", "0.55"))
    if not n_blend:
        final_blend = sim_blend
        final_inds = sim_inds
        conf = 0.55
    else:
        merged: dict[str, float] = {}
        for iid in set(sim_blend) | set(n_blend):
            merged[iid] = (1.0 - alpha) * sim_blend.get(iid, 0.0) + alpha * n_blend.get(iid, 0.0)
        total = sum(merged.values()) or 1.0
        final_blend = {k: round(v / total, 4) for k, v in merged.items() if v > 0.01}
        total = sum(final_blend.values()) or 1.0
        final_blend = {k: round(v / total, 4) for k, v in final_blend.items()}
        ranked = sorted(final_blend.items(), key=lambda x: -x[1])
        final_inds = [
            {
                "industry_id": iid,
                "weight": w,
                "role": "primary" if i == 0 else "secondary",
                "rationale": "neural+similarity" if i == 0 else "soft_neighbor",
            }
            for i, (iid, w) in enumerate(ranked[:5])
        ]
        conf = max(n_conf, 0.62)

    hit = {
        "symbol": sym,
        "industries": final_inds,
        "confidence": round(conf, 4),
        "model": "industry_neural_mlp",
        "search_used": bool(ctx.get("snippets")),
        "search_evidence": ctx.get("snippets") or [],
        "business_summary": str(ctx.get("summary") or "")[:200],
    }
    if persist and final_inds:
        from analytics.industries.ai_registry import upsert_ai_classification

        row = upsert_ai_classification(
            sym,
            industries=final_inds,
            source="neural_yahoo_similarity",
            confidence=conf,
            search_evidence=ctx.get("snippets"),
            model="industry_neural_mlp",
            persist=True,
        )
        hit["registry_row"] = row
    return hit


def batch_classify_neural(
    symbols: list[str],
    *,
    persist: bool = True,
    workers: int | None = None,
) -> list[dict[str, Any]]:
    """Classify many symbols using Yahoo + neural (zero OpenAI calls)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    syms = [s.strip().upper() for s in symbols if s]
    w = workers or int(os.getenv("INDUSTRY_NEURAL_WORKERS", "8"))
    results: list[dict] = []

    def _one(s: str) -> dict:
        ctx = _yahoo_context(s)
        return classify_symbol_neural(s, ctx=ctx, persist=persist)

    with ThreadPoolExecutor(max_workers=max(1, w)) as pool:
        futs = {pool.submit(_one, s): s for s in syms}
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as e:
                results.append({"symbol": futs[fut], "error": str(e)})
    return results
