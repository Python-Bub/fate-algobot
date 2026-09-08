"""Convert news/recommendation streams into numeric alpha factors."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import re

from intel.news_sentiment_lexicon import classify_headline

from intel.headline_fetch_parallel import fetch_headline_groups_parallel
from intel.repetition_weighting import phrase_repetition_score, weighted_signal
from intel.llm_signal_agent import score_documents_with_llm


SRC_RELIABILITY = {
    "finnhub": 0.80,
    "newsapi": 0.70,
    "cramer_proxy": 0.60,
}

UPGRADE_RE = re.compile(r"\b(upgrade|raised target|outperform|buy rating|overweight)\b", re.I)
DOWNGRADE_RE = re.compile(r"\b(downgrade|underperform|sell rating|cut target|underweight)\b", re.I)


@dataclass
class NewsFactors:
    sentiment: float
    conviction: float
    recommendation_bias: float
    source_reliability: float
    repetition_persistence: float
    contradiction_penalty: float
    final_factor: float
    sample_count: int
    generated_at_utc: str


def _sent_stats(texts: list[str]) -> tuple[float, float, float]:
    if not texts:
        return 0.0, 0.0, 0.0
    vals = [float(classify_headline(t).score) for t in texts if t.strip()]
    if not vals:
        return 0.0, 0.0, 0.0
    mean = sum(vals) / len(vals)
    abs_mean = sum(abs(v) for v in vals) / len(vals)
    contradictions = sum(1 for v in vals if v * mean < -0.15) / len(vals)
    return float(mean), float(abs_mean), float(contradictions)


def _rec_bias(texts: list[str]) -> float:
    if not texts:
        return 0.0
    up = sum(1 for t in texts if UPGRADE_RE.search(t or ""))
    dn = sum(1 for t in texts if DOWNGRADE_RE.search(t or ""))
    tot = max(1, up + dn)
    return (up - dn) / tot


def score_symbol_news_factors(symbol: str) -> dict:
    a, b, c = fetch_headline_groups_parallel(symbol, finnhub_limit=30, news_limit=30, cramer_limit=12)
    all_txt = list(a) + list(b) + list(c)

    sent, conv, contrad = _sent_stats(all_txt)
    rep = phrase_repetition_score(all_txt, ngram=3)
    rec = _rec_bias(all_txt)
    src_rel = 0.0
    n = max(1, len(all_txt))
    src_rel += SRC_RELIABILITY["finnhub"] * len(a) / n
    src_rel += SRC_RELIABILITY["newsapi"] * len(b) / n
    src_rel += SRC_RELIABILITY["cramer_proxy"] * len(c) / n

    blended = 0.65 * sent + 0.20 * rec + 0.15 * conv
    blended = weighted_signal(blended, rep.persistence_score, cap=1.3)
    llm = score_documents_with_llm(symbol, all_txt)
    llm_sent = float(llm.get("sentiment", 0.0))
    llm_conf = float(llm.get("confidence", 0.0))
    llm_action = float(llm.get("action_bias", 0.0))
    llm_novel = float(llm.get("novelty", 0.0))
    blended = 0.70 * blended + 0.20 * llm_sent + 0.10 * llm_action
    # contradiction suppresses noisy flip-flop narratives
    final = blended * (1.0 - min(contrad, 0.8) * 0.7) * max(0.4, src_rel)
    final *= (0.85 + 0.15 * max(0.0, llm_conf))
    final *= (0.9 + 0.1 * max(0.0, llm_novel))

    # Math pivot: also emit z-scored / embedding-proxy numerics (do not remove pipelines).
    math_fields: dict = {}
    try:
        from intel.text_to_math import score_texts_to_math

        tm = score_texts_to_math(
            all_txt,
            conviction=float(conv),
            reliability=float(src_rel),
            contradiction=float(contrad),
        )
        math_fields = tm.to_dict()
        # Blend legacy final with pure-math final so narrative never sizes alone
        final = 0.55 * float(final) + 0.45 * float(tm.final_math)
    except Exception:
        pass

    out = NewsFactors(
        sentiment=float(sent),
        conviction=float(conv),
        recommendation_bias=float(rec),
        source_reliability=float(src_rel),
        repetition_persistence=float(rep.persistence_score),
        contradiction_penalty=float(contrad),
        final_factor=float(final),
        sample_count=len(all_txt),
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    ret = asdict(out)
    ret["llm_sentiment"] = llm_sent
    ret["llm_confidence"] = llm_conf
    ret["llm_action_bias"] = llm_action
    ret["llm_novelty"] = llm_novel
    ret["llm_key_thesis"] = str(llm.get("key_thesis", ""))
    ret.update({f"math_{k}" if not k.startswith("math_") else k: v for k, v in math_fields.items()})
    if math_fields:
        ret["sentiment_z"] = math_fields.get("sentiment_z", 0.0)
        ret["event_surprise_z"] = math_fields.get("event_surprise_z", 0.0)
        ret["embedding_polarity"] = math_fields.get("embedding_polarity", 0.0)
        ret["final_math"] = math_fields.get("final_math", 0.0)
    return ret

