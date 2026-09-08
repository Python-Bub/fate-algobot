"""AI training grader.

Reads the per-ticker accuracy stats emitted by `model_trainer._append_run_stats`,
summarises the run, and (optionally) asks the LLM signal agent to grade the
training quality. Designed to fail closed — even if the LLM has no API key,
the deterministic summary still gets logged so the operator sees the real
distribution of test-side accuracy.
"""

from __future__ import annotations

import json
import os
import statistics
from typing import Iterable

from utils import log


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((pct / 100.0) * (len(s) - 1)))))
    return float(s[k])


def _load_stats(path: str) -> list[dict]:
    rows: list[dict] = []
    if not os.path.isfile(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except Exception:
                continue
    return rows


def _summarise(rows: Iterable[dict]) -> dict:
    rows = list(rows)
    n = len(rows)

    def _col(key: str) -> list[float]:
        out: list[float] = []
        for r in rows:
            v = r.get(key)
            if isinstance(v, (int, float)) and v == v:
                out.append(float(v))
        return out

    def _stats(values: list[float]) -> dict:
        if not values:
            return {"n": 0}
        return {
            "n": len(values),
            "mean": float(statistics.fmean(values)),
            "median": float(statistics.median(values)),
            "p25": _percentile(values, 25),
            "p75": _percentile(values, 75),
            "p90": _percentile(values, 90),
            "min": float(min(values)),
            "max": float(max(values)),
        }

    return {
        "tickers": n,
        "short_acc": _stats(_col("short_acc")),
        "short_top20": _stats(_col("short_top20")),
        "long_acc": _stats(_col("long_acc")),
        "long_top20": _stats(_col("long_top20")),
        "meta_auc": _stats(_col("meta_auc")),
    }


def _format_summary(summary: dict) -> str:
    def _line(label: str, blob: dict) -> str:
        if not blob or blob.get("n", 0) == 0:
            return f"{label}: no data"
        return (
            f"{label}: n={blob['n']} mean={blob['mean']:.3f} "
            f"median={blob['median']:.3f} p25={blob['p25']:.3f} "
            f"p75={blob['p75']:.3f} p90={blob['p90']:.3f}"
        )

    lines = [
        f"Tickers trained: {summary.get('tickers', 0)}",
        _line("short_acc       (5-bar dir, chronological holdout)", summary.get("short_acc", {})),
        _line("short_top20  (acc on top 20% confidence)         ", summary.get("short_top20", {})),
        _line("long_acc        (20-bar dir, chronological holdout)", summary.get("long_acc", {})),
        _line("long_top20   (acc on top 20% confidence)         ", summary.get("long_top20", {})),
        _line("meta_auc        (ranker on held-out tail)          ", summary.get("meta_auc", {})),
    ]
    return "\n".join(lines)


def grade_training_run(
    stats_path: str | None = None,
    use_llm: bool | None = None,
) -> dict:
    """Run-end AI grader. Returns the deterministic summary always; adds llm verdict if enabled."""
    path = stats_path or os.getenv("TRAIN_STATS_PATH", "data/train_run_stats.jsonl")
    rows = _load_stats(path)
    summary = _summarise(rows)
    text = _format_summary(summary)
    log.warning("[AI-GRADER] Training accuracy summary:\n%s", text)

    if use_llm is None:
        use_llm = os.getenv("USE_AI_TRAINING_GRADER", "true").lower() in ("1", "true", "yes")
    if not use_llm:
        return {"summary": summary, "summary_text": text}

    key_present = bool((os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip())
    if not key_present:
        log.warning(
            "[AI-GRADER] No LLM_API_KEY / OPENAI_API_KEY set — skipping LLM verdict. "
            "Export one of those env vars (and optionally LLM_MODEL, LLM_BASE_URL) to enable the AI grader."
        )
        return {"summary": summary, "summary_text": text, "llm_skipped": "no_api_key"}

    try:
        from intel.llm_signal_agent import score_text_with_llm
    except Exception as e:
        log.warning("[AI-GRADER] LLM import failed: %s", e)
        return {"summary": summary, "summary_text": text}

    os.environ["USE_LLM_SIGNAL"] = "true"
    prompt_doc = (
        "Quant ML training run summary across thousands of tickers. "
        "Test-side accuracy is from chronological holdout (last 20% of bars). "
        "acc@top20 is accuracy on the top 20% confidence predictions, which represents the trades the bot would actually take.\n\n"
        f"{text}\n\n"
        "Treat this as a financial-signal payload. Set:\n"
        "- sentiment in [-1,1]: -1 if the run is broken (mostly < 0.5 across all metrics), +1 if the meta_auc median is meaningfully above 0.55 and acc@top20 medians are meaningfully above 0.55.\n"
        "- confidence in [0,1]: how confident you are in the verdict.\n"
        "- action_bias in [-1,1]: +1 if the operator should deploy these models live, -1 if they should retrain with different settings.\n"
        "- horizon_days: how many days the dominant edge appears to last (1 for short_acc, 20 for long_acc).\n"
        "- key_thesis: ONE short sentence explaining the verdict.\n"
    )
    verdict = score_text_with_llm(prompt_doc, symbol="TRAINING_RUN")
    log.warning(
        "[AI-GRADER] LLM verdict: sentiment=%.2f confidence=%.2f action_bias=%.2f "
        "horizon_days=%.0f thesis=%s",
        verdict.get("sentiment", 0.0),
        verdict.get("confidence", 0.0),
        verdict.get("action_bias", 0.0),
        verdict.get("horizon_days", 0.0),
        verdict.get("key_thesis", ""),
    )
    return {"summary": summary, "summary_text": text, "llm_verdict": verdict}
