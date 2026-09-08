#!/usr/bin/env python3
"""
Monthly (and on-demand) universe maintenance:
  1) Refresh exchange universe snapshot
  2) Detect corporate actions (rename, delist, split)
  3) Refresh top-100 + top-50% market-cap tiers
  4) Run tiered training protocol on changed symbols
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from universe_lifecycle.corporate_actions import detect_corporate_events, load_registry
from universe_lifecycle.paths import STATE_PATH, TRAIN_QUEUE_PATH
from universe_lifecycle.protocol import (
    run_corporate_protocol,
    run_new_listing_protocol,
    run_top100_protocol,
    run_top50_protocol,
)
from universe_lifecycle.rankings import refresh_market_cap_tiers
from universe_lifecycle.snapshot import diff_universe, load_snapshot, save_snapshot


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


def _model_symbols() -> list[str]:
    from fortress_universe import symbols_with_daily_models

    return symbols_with_daily_models()


def _current_universe() -> list[str]:
    from universe_provider import load_universe_with_cap

    refresh = os.getenv("UNIVERSE_REFRESH_ON_MAINT", "true").lower() in ("1", "true", "yes")
    return load_universe_with_cap(max_symbols=None, refresh=refresh)


def _split_scan_symbols(udiff: dict, models: list[str]) -> list[str]:
    """Keep corporate split scan bounded — never scan full model dir (6000+ yfinance calls)."""
    try:
        from fortress_universe import load_top100_symbols

        seed = list(load_top100_symbols()[:60])
    except Exception:
        seed = []
    removed = list(udiff.get("removed") or [])[:30]
    return list(dict.fromkeys([*(s.upper() for s in seed), *(s.upper() for s in removed)]))


def build_maintenance_plan(*, dry_run: bool = False) -> dict[str, Any]:
    """Compute maintenance plan; dry_run avoids network / full-universe scans."""
    prev_snap = load_snapshot()
    prev_syms = prev_snap.get("symbols") or []
    if dry_run:
        current = list(prev_syms)
    else:
        current = _current_universe()
    udiff = diff_universe(prev_syms, current)

    if dry_run:
        from universe_lifecycle.paths import TOP100_PATH, TOP50_PATH
        import json

        prev100 = []
        prev50 = []
        if TOP100_PATH.is_file():
            try:
                prev100 = json.loads(TOP100_PATH.read_text(encoding="utf-8")).get("symbols") or []
            except Exception:
                pass
        if TOP50_PATH.is_file():
            try:
                prev50 = json.loads(TOP50_PATH.read_text(encoding="utf-8")).get("symbols") or []
            except Exception:
                pass
        tiers = {
            "top100": prev100,
            "top50pct": prev50,
            "top100_diff": {"entered": [], "exited": []},
            "top50_diff": {"entered": [], "exited": []},
        }
        corp = {"renames": [], "delistings": [], "splits": [], "migrations_applied": []}
    else:
        models = _model_symbols()
        corp = detect_corporate_events(
            removed_symbols=udiff["removed"],
            model_symbols=models,
            split_scan_symbols=_split_scan_symbols(udiff, models),
        )
        tiers = refresh_market_cap_tiers()

    retrain_corp: list[str] = []
    for ev in corp.get("splits") or []:
        retrain_corp.append(str(ev.get("symbol", "")).upper())
    for m in corp.get("migrations_applied") or []:
        if m.get("retrain") and m.get("new"):
            retrain_corp.append(str(m["new"]).upper())

    # Enrich snapshot-diff "added" with multi-source IPO discovery (Finnhub/Nasdaq/…)
    ipo_extra: list[str] = []
    if not dry_run:
        try:
            from intel.ipo_news_discovery import discover_from_news
            from model_trainer import training_saved_model
            from tools.listing_watch import is_queueable_listing_ticker

            ipo_doc = discover_from_news()
            for sym in ipo_doc.get("tickers") or []:
                s = str(sym).upper()
                if is_queueable_listing_ticker(s) and not training_saved_model(s):
                    ipo_extra.append(s)
        except Exception:
            ipo_extra = []

    new_listings = list(
        dict.fromkeys([*(udiff.get("added") or []), *ipo_extra])
    )

    plan = {
        "universe_diff": udiff,
        "corporate": corp,
        "tiers": tiers,
        "ipo_discovery": {"count": len(ipo_extra), "symbols": ipo_extra[:40]},
        "train": {
            "top100_entered": tiers.get("top100_diff", {}).get("entered") or [],
            "top100_all": bool(os.getenv("TOP100_FULL_REBUILD_MONTHLY", "false").lower() in ("1", "true", "yes")),
            "top50_entered": tiers.get("top50_diff", {}).get("entered") or [],
            "new_listings": new_listings,
            "corporate": sorted(set(retrain_corp)),
        },
    }
    return plan


def run_maintenance(
    *,
    mode: str = "monthly",
    dry_run: bool = False,
    skip_train: bool = False,
    top100_full: bool = False,
) -> dict[str, Any]:
    from fortress_universe import load_top100_symbols, load_top50pct_symbols

    print("[universe-monthly] building plan…", flush=True)
    plan = build_maintenance_plan(dry_run=dry_run)
    report: dict[str, Any] = {"mode": mode, "dry_run": dry_run, "plan": plan, "results": {}}

    if dry_run:
        print(json.dumps(plan, indent=2, default=str))
        return report

    current = _current_universe()
    print(f"[universe-monthly] snapshot {len(current)} symbols", flush=True)
    save_snapshot(current)

    tiers = plan["tiers"]
    train = plan["train"]
    results = report["results"]

    from tools.change_cleaner import run_builtin_cleaner

    if skip_train:
        print("[universe-monthly] running built-in cleaner…", flush=True)
        results["cleaner"] = run_builtin_cleaner(reason=f"universe_{mode}_sync", plan=plan)
        _save_state({"last_sync_utc": _now(), "last_plan": plan})
        print(json.dumps(report, indent=2, default=str))
        return report

    try:
        from tools.train_coordination import should_defer_secondary_training

        if should_defer_secondary_training() and mode != "force":
            print("[universe-monthly] deferred — top100_perfect running", flush=True)
            run_builtin_cleaner(reason=f"universe_{mode}_deferred", plan=plan)
            _save_state({"last_deferred_utc": _now(), "last_plan": plan})
            return report
    except Exception:
        pass

    if top100_full or train.get("top100_all"):
        results["top100"] = run_top100_protocol(full_perfect=True)
    else:
        top_syms = list(dict.fromkeys(load_top100_symbols()))
        entered = train.get("top100_entered") or []
        batch = entered if entered else []
        if batch:
            results["top100"] = run_top100_protocol(batch, full_perfect=False)
        elif mode == "monthly":
            # Monthly: light strong pass on full top100 weak only
            from tools.retrain_weak_models import find_weak_symbols

            weak = list(find_weak_symbols(min_top20=0.52, min_meta=0.48, top100_only=True).keys())
            # Always attempt short-history top100 names (SPCX) when online.
            try:
                from fortress_universe import load_top100_symbols
                from pathlib import Path

                short_hist = {
                    x.strip().upper()
                    for x in os.getenv("TOP100_ONLINE_SHORT_HIST", "SPCX").split(",")
                    if x.strip()
                }
                top = {s.upper() for s in load_top100_symbols()}
                for s in sorted(short_hist & top):
                    if not (Path("models") / f"{s}_model.pkl").is_file() and s not in weak:
                        weak.append(s)
            except Exception:
                pass
            if weak:
                from universe_lifecycle.protocol import strong_retrain_symbols

                results["top100_weak"] = strong_retrain_symbols(weak, min_top20=0.52, min_meta=0.48)
            # Dedicated short-history pass (reduced horizons) — does not block monthly.
            try:
                import subprocess
                from pathlib import Path as _P

                _root = _P(__file__).resolve().parents[1]
                py = str(_root / "venv" / "bin" / "python")
                if not _P(py).is_file():
                    py = sys.executable
                rc = subprocess.call(
                    [py, "-u", "tools/train_spcx_online.py", "--min-top20", "0.28", "--min-meta", "0.40"],
                    cwd=str(_root),
                )
                results["short_hist_online"] = {"rc": rc}
            except Exception as e:
                results["short_hist_online"] = {"error": str(e)}

    top50 = load_top50pct_symbols()
    top50_entered = train.get("top50_entered") or []
    if top50_entered:
        results["top50"] = run_top50_protocol(top50_entered)
    elif mode == "monthly" and top50:
        # Monthly refresh: train any top50 missing models
        from model_trainer import training_saved_model

        missing = [s for s in top50 if not training_saved_model(s)][: int(os.getenv("TOP50_MONTHLY_CAP", "80"))]
        if missing:
            results["top50_missing"] = run_top50_protocol(missing)

    new_syms = train.get("new_listings") or []
    if new_syms:
        cap = int(os.getenv("NEW_LISTING_MONTHLY_CAP", "40"))
        results["new"] = run_new_listing_protocol(new_syms[:cap])

    corp_syms = train.get("corporate") or []
    if corp_syms:
        results["corporate"] = run_corporate_protocol(corp_syms)

    # Built-in cleaner after any universe/tier/corporate change
    results["cleaner"] = run_builtin_cleaner(reason=f"universe_{mode}", plan=plan)

    if os.getenv("INDUSTRY_AI_ON_MAINT", "false").lower() in ("1", "true", "yes"):
        try:
            from tools.industry_ai_weekly import main as industry_ai_main

            import sys

            argv_bak = list(sys.argv)
            sys.argv = ["industry_ai_weekly.py", "--tier", os.getenv("INDUSTRY_AI_TIER", "top50")]
            results["industry_ai"] = {"ran": True}
            industry_ai_main()
            sys.argv = argv_bak
        except Exception as e:
            results["industry_ai"] = {"ran": False, "error": str(e)}

    _save_state(
        {
            "last_maintenance_utc": _now(),
            "mode": mode,
            "plan_summary": {
                "top100_entered": train.get("top100_entered"),
                "top50_entered": len(train.get("top50_entered") or []),
                "new": len(new_syms),
                "corporate": len(corp_syms),
            },
            "results_keys": list(results.keys()),
        }
    )
    TRAIN_QUEUE_PATH.write_text(json.dumps({"cleared_at": _now(), "plan": plan.get("train")}, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Universe lifecycle: tiers + corporate actions + tiered training")
    ap.add_argument("--dry-run", action="store_true", help="Plan only, no writes/train")
    ap.add_argument("--skip-train", action="store_true", help="Sync tiers + corporate only")
    ap.add_argument("--mode", default="monthly", choices=("monthly", "weekly", "force"))
    ap.add_argument("--top100-full", action="store_true", help="Run train_top100_perfect.py")
    ap.add_argument("--plan-only", action="store_true", help="Alias for --dry-run")
    args = ap.parse_args()
    os.chdir(ROOT)

    if args.plan_only:
        args.dry_run = True

    run_maintenance(
        mode=args.mode,
        dry_run=args.dry_run,
        skip_train=args.skip_train,
        top100_full=args.top100_full,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
