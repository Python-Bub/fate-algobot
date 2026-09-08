#!/usr/bin/env python3
"""Maximum industry AI training — Yahoo data, neural MLP, similarity, optional LLM mega-batch."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _apply_yahoo_env() -> None:
    os.environ["USE_YAHOO_FIRST"] = "true"
    os.environ["USE_YAHOO_ONLY"] = "true"
    os.environ["PRICE_DATA_SOURCE"] = "yfinance"
    os.environ["FORCE_YAHOO_PRICES"] = "true"
    os.environ["TRAIN_FORCE_YAHOO"] = "true"
    os.environ["SKIP_YAHOO_FALLBACK"] = "false"
    from data_platform.price_fetch_policy import apply_price_env_defaults

    apply_price_env_defaults(training=True)


def run_max_train(
    *,
    tier: str = "top50",
    chunk: int | None = None,
    max_chunks: int | None = None,
    skip_llm: bool = True,
    skip_bootstrap: bool = False,
) -> dict:
    _apply_yahoo_env()
    report: dict = {"started_at_utc": _now(), "tier": tier, "phases": []}

    # Phase 1: rule bootstrap
    if not skip_bootstrap:
        from tools.bootstrap_industry_ai_registry import bootstrap

        rep = bootstrap(tier="all", min_confidence=0.55)
        report["phases"].append({"name": "bootstrap", **rep})

    # Phase 2: train neural MLP on all local labels
    from analytics.industries.neural_classifier import train_neural_classifier

    neural_rep = train_neural_classifier(min_samples=30)
    report["phases"].append({"name": "neural_mlp", **neural_rep})

    # Phase 3: Yahoo + neural classify universe (zero OpenAI)
    from tools.industry_ai_weekly import _universe_for_tier
    from analytics.industries.neural_classifier import batch_classify_neural
    from analytics.industries.ai_registry import emit_ai_override_module

    universe = _universe_for_tier(tier)
    chunk_size = chunk or int(os.getenv("INDUSTRY_NEURAL_BATCH", "64"))
    max_c = max_chunks if max_chunks is not None else int(os.getenv("INDUSTRY_MAX_CHUNKS", "9999"))
    classified = 0
    chunks_done = 0
    for i in range(0, len(universe), chunk_size):
        if chunks_done >= max_c:
            break
        batch = universe[i : i + chunk_size]
        hits = batch_classify_neural(batch, persist=True)
        classified += sum(1 for h in hits if h.get("registry_row") or h.get("industries"))
        chunks_done += 1
        print(f"[industry-max] neural chunk {chunks_done} ok={classified} batch={len(batch)}", flush=True)

    emit_ai_override_module()
    report["phases"].append({"name": "neural_classify", "classified": classified, "chunks": chunks_done})

    # Phase 4: optional LLM mega-batch for low-confidence only
    if not skip_llm and os.getenv("OPENAI_API_KEY", "").strip():
        os.environ["USE_INDUSTRY_NEURAL_FIRST"] = "false"
        from analytics.industries.ai_registry import load_ai_registry, symbols_needing_ai_refresh
        from intel.industry_ai_classifier import classify_batch_with_ai, apply_ai_to_industry_map

        due = symbols_needing_ai_refresh(universe, include_unclassified=True)[: int(os.getenv("INDUSTRY_LLM_MAX_SYMBOLS", "200"))]
        llm_ok = 0
        bs = int(os.getenv("INDUSTRY_AI_MEGA_BATCH", "24"))
        for j in range(0, len(due), bs):
            chunk_syms = due[j : j + bs]
            results = classify_batch_with_ai(chunk_syms, persist=True, use_mega_batch=True)
            llm_ok += sum(1 for r in results if r.get("registry_row"))
        apply_ai_to_industry_map(due)
        emit_ai_override_module()
        report["phases"].append({"name": "llm_mega_batch", "classified": llm_ok, "due": len(due)})
    else:
        report["phases"].append({"name": "llm_mega_batch", "skipped": True})

    try:
        from tools.emit_peer_ticker_map import main as emit_peer

        emit_peer()
    except Exception:
        pass

    report["finished_at_utc"] = _now()
    out = ROOT / "reports" / "industry_max_train.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Max industry train: Yahoo + neural + optional LLM")
    ap.add_argument("--tier", default=os.getenv("INDUSTRY_AI_TIER", "top50"))
    ap.add_argument("--chunk", type=int, default=None)
    ap.add_argument("--max-chunks", type=int, default=None)
    ap.add_argument("--with-llm", action="store_true", help="Also run mega-batch LLM for low-conf symbols")
    ap.add_argument("--skip-bootstrap", action="store_true")
    args = ap.parse_args()

    rep = run_max_train(
        tier=args.tier,
        chunk=args.chunk,
        max_chunks=args.max_chunks,
        skip_llm=not args.with_llm,
        skip_bootstrap=args.skip_bootstrap,
    )
    print(json.dumps(rep, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
