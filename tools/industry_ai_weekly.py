#!/usr/bin/env python3
"""Weekly AI industry classification — web search + LLM, multi-industry, code emission."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _universe_for_tier(tier: str) -> list[str]:
    from analytics.industries.classifier import iter_universe_symbols

    tier = tier.strip().lower()
    if tier in ("all", "full"):
        return list(iter_universe_symbols(tier="all"))
    if tier in ("top50", "top50pct", "half"):
        return list(iter_universe_symbols(tier="top50"))
    if tier in ("top100", "mega"):
        return list(iter_universe_symbols(tier="top100"))
    return list(iter_universe_symbols(tier="top50"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Weekly AI industry classifier with web search")
    ap.add_argument("--tier", default=os.getenv("INDUSTRY_AI_TIER", "top50"), help="top50|top100|all")
    ap.add_argument("--limit", type=int, default=int(os.getenv("INDUSTRY_AI_WEEKLY_BATCH", "120")))
    ap.add_argument("--offset", type=int, default=0, help="Skip first N due symbols")
    ap.add_argument("--dry-run", action="store_true", help="List due symbols only")
    ap.add_argument("--force-all", action="store_true", help="Ignore staleness — reclassify batch")
    ap.add_argument("--apply-map", action="store_true", default=True, help="Merge into industry_map.json")
    ap.add_argument("--emit-code", action="store_true", default=True, help="Write ai_generated_overrides.py")
    ap.add_argument("--refresh-peer-map", action="store_true", help="Regenerate peer_ticker_map.py")
    args = ap.parse_args()

    os.chdir(ROOT)

    universe = _universe_for_tier(args.tier)
    print(f"[industry-ai-weekly] tier={args.tier} universe={len(universe)}", flush=True)

    from analytics.industries.ai_registry import emit_ai_override_module, symbols_needing_ai_refresh

    if args.force_all:
        due = universe
    else:
        due = symbols_needing_ai_refresh(universe, include_unclassified=True)

    if args.offset > 0:
        due = due[args.offset :]
    if args.limit > 0:
        due = due[: args.limit]

    print(f"[industry-ai-weekly] due={len(due)} batch={min(len(due), args.limit)}", flush=True)
    if args.dry_run:
        for s in due[:30]:
            print(f"  {s}")
        if len(due) > 30:
            print(f"  … +{len(due) - 30} more")
        return 0

    if not due:
        print("[industry-ai-weekly] nothing due — all fresh", flush=True)
    else:
        from intel.industry_ai_classifier import apply_ai_to_industry_map, classify_batch_with_ai

        results = classify_batch_with_ai(due, persist=True)
        ok = sum(1 for r in results if r.get("registry_row"))
        err = sum(1 for r in results if r.get("error") or r.get("skipped"))
        print(f"[industry-ai-weekly] classified={ok} skipped_or_err={err}", flush=True)

        if args.apply_map:
            n = apply_ai_to_industry_map([r.get("symbol") for r in results if r.get("registry_row")])
            print(f"[industry-ai-weekly] industry_map updated={n}", flush=True)

    if args.emit_code:
        path = emit_ai_override_module()
        print(f"[industry-ai-weekly] emitted {path}", flush=True)

    if args.refresh_peer_map:
        from tools.emit_peer_ticker_map import main as emit_main

        emit_main()

    # Optional cap tier refresh (skip during train — rankings may lack caps mid-run)
    if os.getenv("INDUSTRY_AI_REFRESH_TOP50", "false").lower() in ("1", "true", "yes"):
        try:
            from universe_lifecycle.rankings import refresh_market_cap_tiers

            out = refresh_market_cap_tiers()
            print(
                f"[industry-ai-weekly] top50={len(out['top50pct'])} / universe={out['universe_size']} "
                f"(target {out['top50_target']})",
                flush=True,
            )
        except Exception as e:
            print(f"[industry-ai-weekly] top50 refresh skipped: {e}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
