#!/usr/bin/env python3
"""Full industry AI training run — classifies entire top-50% (or all) in auto-resuming chunks."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

STATE_PATH = ROOT / "data" / "industry" / "ai_train_state.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_state() -> dict:
    if not STATE_PATH.is_file():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(doc: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc["updated_at_utc"] = _now()
    STATE_PATH.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def _universe(tier: str) -> list[str]:
    from tools.industry_ai_weekly import _universe_for_tier

    return _universe_for_tier(tier)


def run_train(
    *,
    tier: str = "top50",
    chunk_size: int | None = None,
    max_chunks: int | None = None,
    force: bool = False,
    refresh_peer: bool = True,
) -> dict:
    chunk = chunk_size or int(os.getenv("INDUSTRY_AI_TRAIN_CHUNK", "32"))
    max_c = max_chunks if max_chunks is not None else int(os.getenv("INDUSTRY_AI_TRAIN_MAX_CHUNKS", "9999"))

    universe = _universe(tier)
    state = _load_state()

    from analytics.industries.ai_registry import emit_ai_override_module, symbols_needing_ai_refresh
    from intel.industry_ai_classifier import apply_ai_to_industry_map, classify_batch_with_ai

    if force:
        due_all = list(universe)
    else:
        due_set = set(symbols_needing_ai_refresh(universe, include_unclassified=True))
        due_all = [s for s in universe if s in due_set]

    report: dict = {
        "tier": tier,
        "universe_size": len(universe),
        "due_total": len(due_all),
        "chunks_run": 0,
        "classified": 0,
        "errors": 0,
        "started_at_utc": _now(),
    }

    if not due_all:
        report["finished_at_utc"] = _now()
        report["progress"] = f"0/0"
        report["complete"] = True
        _save_state(
            {
                "tier": tier,
                "complete_at_utc": _now(),
                "due_total": 0,
                "universe_size": len(universe),
            }
        )
        return report

    print(
        f"[industry-ai-train] tier={tier} universe={len(universe)} due={len(due_all)} chunk={chunk}",
        flush=True,
    )

    chunks_done = 0
    classified_total = int(state.get("classified_total") or 0)

    while chunks_done < max_c and due_all:
        batch = due_all[:chunk]
        print(
            f"[industry-ai-train] chunk {chunks_done + 1} batch={len(batch)} remaining={len(due_all)} …",
            flush=True,
        )
        t0 = time.perf_counter()
        results = classify_batch_with_ai(batch, persist=True, use_mega_batch=True)
        ok = [r for r in results if r.get("registry_row")]
        err = [r for r in results if r.get("error") or r.get("skipped")]
        syms_ok = [r.get("symbol") for r in ok if r.get("symbol")]
        if syms_ok:
            apply_ai_to_industry_map(syms_ok)
        emit_ai_override_module()

        classified_total += len(ok)
        chunks_done += 1
        report["classified"] += len(ok)
        report["errors"] += len(err)
        report["chunks_run"] = chunks_done

        if not force:
            due_set = set(symbols_needing_ai_refresh(universe, include_unclassified=True))
            due_all = [s for s in universe if s in due_set]
        else:
            due_all = due_all[chunk:]

        _save_state(
            {
                "tier": tier,
                "universe_size": len(universe),
                "due_total": len(due_all) + len(batch) if force else len(due_all) + len(ok),
                "remaining": len(due_all),
                "classified_total": classified_total,
                "last_chunk": len(batch),
                "last_ok": len(ok),
                "last_err": len(err),
                "last_elapsed_sec": round(time.perf_counter() - t0, 1),
            }
        )
        print(
            f"[industry-ai-train] chunk done ok={len(ok)} err={len(err)} "
            f"elapsed={time.perf_counter() - t0:.0f}s remaining={len(due_all)}",
            flush=True,
        )
        time.sleep(float(os.getenv("INDUSTRY_AI_TRAIN_CHUNK_PAUSE", "3.0")))

        if chunks_done >= max_c:
            break

    if refresh_peer and report["classified"] > 0:
        try:
            from tools.emit_peer_ticker_map import main as emit_peer

            emit_peer()
            print("[industry-ai-train] peer_ticker_map refreshed", flush=True)
        except Exception as e:
            print(f"[industry-ai-train] peer map skipped: {e}", flush=True)

    report["finished_at_utc"] = _now()
    report["remaining"] = len(due_all)
    report["progress"] = f"{len(universe) - len(due_all)}/{len(universe)}"
    report["complete"] = len(due_all) == 0
    if report["complete"]:
        _save_state(
            {
                "tier": tier,
                "complete_at_utc": _now(),
                "due_total": 0,
                "remaining": 0,
                "classified_total": classified_total,
                "universe_size": len(universe),
            }
        )
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Train industry AI on full top-50% universe")
    ap.add_argument("--tier", default=os.getenv("INDUSTRY_AI_TIER", "top50"))
    ap.add_argument("--chunk", type=int, default=int(os.getenv("INDUSTRY_AI_TRAIN_CHUNK", "32")))
    ap.add_argument("--max-chunks", type=int, default=int(os.getenv("INDUSTRY_AI_TRAIN_MAX_CHUNKS", "9999")))
    ap.add_argument("--force", action="store_true", help="Reclassify from start")
    ap.add_argument("--no-peer-map", action="store_true")
    args = ap.parse_args()
    os.chdir(ROOT)

    if not (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")):
        print("[industry-ai-train] ERROR: set LLM_API_KEY or OPENAI_API_KEY", flush=True)
        return 1

    report = run_train(
        tier=args.tier,
        chunk_size=args.chunk,
        max_chunks=args.max_chunks,
        force=args.force,
        refresh_peer=not args.no_peer_map,
    )
    print(json.dumps(report, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
