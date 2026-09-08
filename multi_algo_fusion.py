"""Multi-algorithm fusion engine:
- Existing ensemble probability (short/long blend)
- Auxiliary SVM-RBF / RF models (if trained)
- LLM/news/transcript intelligence factors
- Insider-flow proxy factor
"""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict

import joblib
import numpy as np
import pandas as pd

from intel.news_factor_engine import score_symbol_news_factors
from intel.transcript_factor_engine import score_symbol_transcripts
from intel.llm_signal_agent import score_documents_with_llm
from news_reader import fetch_news
from utils import log


@dataclass
class FusionDecision:
    p_final: float
    p_base: float
    p_aux: float
    intel_factor: float
    insider_factor: float
    action: str
    rationale: dict


def _clip(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


def _insider_flow_proxy(ticker: str) -> float:
    """C-suite weighted insider flow (sells → bearish)."""
    try:
        from intel.insider_signals import insider_flow_factor

        return insider_flow_factor(ticker)
    except Exception:
        return 0.0


def _aux_probs(bundle: dict, x: pd.DataFrame) -> float:
    """Average auxiliary model probabilities if available."""
    ps: list[float] = []
    for k in ("model_svm_rbf", "model_rf_aux"):
        m = bundle.get(k)
        if m is None:
            continue
        try:
            p = m.predict_proba(x)[0]
            classes = list(getattr(m, "classes_", [0, 1]))
            up = float(p[classes.index(1)]) if 1 in classes else float(np.max(p))
            ps.append(up)
        except Exception as e:
            log.debug("[FUSION] aux %s skipped: %s", k, e)
    if not ps:
        return 0.5
    return float(np.mean(ps))


def fused_decision(
    ticker: str,
    model_bundle_path: str,
    row: pd.Series,
    p_base: float,
    min_conf: float,
) -> dict:
    x = pd.DataFrame([row]).replace([np.inf, -np.inf], 0).fillna(0)
    bundle = joblib.load(model_bundle_path) if os.path.isfile(model_bundle_path) else {}

    p_aux = _aux_probs(bundle, x[x.columns.intersection(bundle.get("features", list(x.columns)))])
    use_intel = os.getenv("USE_INTEL_FACTORS", "true").lower() in ("1", "true", "yes")
    nf = {}
    tf = {}
    llm = {}
    if use_intel and os.getenv("DISABLE_SENTIMENT", "false").lower() not in ("1", "true", "yes"):
        nf = score_symbol_news_factors(ticker)
        tf = score_symbol_transcripts(ticker)
        docs = []
        try:
            docs = [(a.get("headline", "") + " " + a.get("summary", "")).strip() for a in fetch_news(ticker)]
        except Exception:
            docs = []
        llm = score_documents_with_llm(ticker, docs)
    intel_factor = (
        float(os.getenv("FUSION_INTEL_NEWS_W", "0.42")) * float(nf.get("final_factor", 0.0))
        + float(os.getenv("FUSION_INTEL_TRANSCRIPT_W", "0.18")) * float(tf.get("final_factor", 0.0))
        + float(os.getenv("FUSION_INTEL_LLM_SENT_W", "0.24")) * float(llm.get("sentiment", 0.0))
        + float(os.getenv("FUSION_INTEL_LLM_BIAS_W", "0.16")) * float(llm.get("action_bias", 0.0))
    )
    insider = _insider_flow_proxy(ticker)
    unified_adj = 0.0
    try:
        from intel.unified_intel import unified_intel_for

        u = unified_intel_for(ticker)
        unified_adj = float(u.get("boost") or 0.0)
        if u.get("block_long"):
            unified_adj = min(unified_adj, -0.35)
    except Exception:
        pass

    w_base = float(os.getenv("FUSION_WEIGHT_BASE", "0.56"))
    w_aux = float(os.getenv("FUSION_WEIGHT_AUX", "0.17"))
    w_intel = float(os.getenv("FUSION_WEIGHT_INTEL_TANH", "0.18"))
    w_ins = float(os.getenv("FUSION_WEIGHT_INSIDER_TANH", "0.09"))
    w_uni = float(os.getenv("FUSION_UNIFIED_INTEL_W", "0.08"))
    s = w_base + w_aux + w_intel + w_ins + w_uni
    if s <= 0:
        s = 1.0
    w_base, w_aux, w_intel, w_ins, w_uni = (
        w_base / s,
        w_aux / s,
        w_intel / s,
        w_ins / s,
        w_uni / s,
    )

    from analytics.vector_math import factor_to_prob, fuse_probs, lea_enabled

    p_intel = factor_to_prob(intel_factor)
    p_ins = factor_to_prob(insider)
    p_uni = factor_to_prob(unified_adj * 2.0)
    probs = [float(p_base), float(p_aux), p_intel, p_ins, p_uni]
    weights = [w_base, w_aux, w_intel, w_ins, w_uni]
    if lea_enabled():
        p = fuse_probs(probs, weights)
    else:
        p = float(np.dot(weights, probs))
    p = _clip(p, 0.0, 1.0)
    action = "BUY" if p >= min_conf else ("SELL" if p <= (1 - min_conf) else "HOLD")
    out = FusionDecision(
        p_final=float(p),
        p_base=float(p_base),
        p_aux=float(p_aux),
        intel_factor=float(intel_factor),
        insider_factor=float(insider),
        action=action,
        rationale={
            "news_factor": float(nf.get("final_factor", 0.0)),
            "transcript_factor": float(tf.get("final_factor", 0.0)),
            "llm_sentiment": float(llm.get("sentiment", 0.0)),
            "llm_action_bias": float(llm.get("action_bias", 0.0)),
        },
    )
    return asdict(out)

