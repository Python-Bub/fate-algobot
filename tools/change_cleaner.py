#!/usr/bin/env python3
"""
Built-in cleaner — run after universe/tier/corporate changes.

Safe by default: protects top100, top50, paper-active, IPO queue, bottom-fisher picks.
Delegates general disk hygiene to tools/prune_disk.py.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "venv/bin/python"
LOG = ROOT / "logs" / "change_cleaner.log"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str) -> None:
    line = f"[{_now()}] {msg}\n"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line)
    print(f"[cleaner] {msg}", flush=True)


def _protected_symbols() -> set[str]:
    protected: set[str] = set()
    sys.path.insert(0, str(ROOT))
    try:
        from fortress_universe import load_top100_symbols, load_top50pct_symbols, symbols_paper_active_universe

        protected.update(load_top100_symbols())
        protected.update(load_top50pct_symbols())
        protected.update(symbols_paper_active_universe())
    except Exception:
        pass
    for rel in (
        "data/new_listing_train_queue.json",
        "data/tier2_retrain_queue.json",
        "data/universe_lifecycle_train_queue.json",
    ):
        p = ROOT / rel
        if not p.is_file():
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            syms = doc if isinstance(doc, list) else doc.get("symbols", [])
            protected.update(str(s).upper() for s in syms if s)
        except Exception:
            pass
    try:
        from bottom_fisher.store import load_scan

        for p in load_scan().get("picks") or []:
            if p.get("trade_eligible", True):
                protected.add(str(p["ticker"]).upper())
    except Exception:
        pass
    extra = os.getenv("CLEANER_PROTECT_TICKERS", "")
    protected.update(s.strip().upper() for s in extra.split(",") if s.strip())
    return protected


def _artifact_paths(sym: str) -> list[Path]:
    sym = sym.upper()
    model_dir = Path(os.getenv("MODEL_DIR", "models"))
    intra_dir = Path(os.getenv("INTRADAY_MODEL_DIR", "models/intraday"))
    lstm_dir = Path(os.getenv("LSTM_MODEL_DIR", "models/lstm"))
    cache_dir = Path(os.getenv("PRICE_CACHE_DIR", "data/cache/prices"))
    return [
        model_dir / f"{sym}_model.pkl",
        model_dir / "meta" / f"{sym}_meta.pkl",
        intra_dir / f"{sym}_intraday.pkl",
        lstm_dir / f"{sym}_lstm.pt",
        cache_dir / f"{sym}.parquet",
        cache_dir / f"{sym}.csv",
    ]


def _rm_file(p: Path, *, dry: bool) -> int:
    if not p.is_file():
        return 0
    try:
        n = p.stat().st_size
    except OSError:
        n = 0
    if dry:
        return n
    p.unlink(missing_ok=True)
    return n


def cleanup_orphan_symbols(symbols: list[str], *, dry: bool = False) -> dict[str, Any]:
    """Drop model/cache artifacts for delisted / removed names (never protected).

    Hard guard: CLEANER_NEVER_DELETE_MODELS / AUTO_IMPROVE_NEVER_DELETE=true
    refuses to remove any model pickle — only logs what would have been cleaned.
    """
    if os.getenv("CLEANER_NEVER_DELETE_MODELS", "true").lower() in ("1", "true", "yes") or os.getenv(
        "AUTO_IMPROVE_NEVER_DELETE", "true"
    ).lower() in ("1", "true", "yes"):
        return {
            "symbols": [],
            "bytes_freed": 0,
            "skipped": "never_delete_guard",
            "would_touch": [s.strip().upper() for s in symbols if s.strip()][:50],
        }
    protected = _protected_symbols()
    removed: list[str] = []
    freed = 0
    for raw in symbols:
        sym = raw.strip().upper()
        if not sym or sym in protected:
            continue
        hits = [p for p in _artifact_paths(sym) if p.is_file()]
        if not hits:
            continue
        for p in hits:
            freed += _rm_file(p, dry=dry)
        removed.append(sym)
    return {"symbols": removed, "bytes_freed": freed}


def cleanup_stale_temp_files(*, dry: bool = False, max_age_hours: float = 24) -> dict[str, Any]:
    """Remove short-lived protocol/batch JSON written during training runs."""
    freed = 0
    removed: list[str] = []
    cutoff = time.time() - max_age_hours * 3600
    patterns = (
        "data/universe_protocol_*.json",
        "data/new_listing_batch.json",
        "data/universe_lifecycle_train_queue.json.tmp",
    )
    for pat in patterns:
        for p in ROOT.glob(pat):
            try:
                if p.stat().st_mtime > cutoff and max_age_hours > 0:
                    continue
            except OSError:
                pass
            freed += _rm_file(p, dry=dry) if p.is_file() else 0
            if p.is_file():
                continue
            removed.append(str(p.relative_to(ROOT)))
    # Always clear empty listing batch after a run
    batch = ROOT / "data/new_listing_batch.json"
    if batch.is_file():
        try:
            doc = json.loads(batch.read_text(encoding="utf-8"))
            if not doc:
                freed += _rm_file(batch, dry=dry)
                removed.append("data/new_listing_batch.json")
        except Exception:
            pass
    return {"files": removed, "bytes_freed": freed}


def cleanup_tier_exits(plan: dict | None, *, dry: bool = False) -> dict[str, Any]:
    """Remove artifacts for symbols that exited top100/top50 AND left the exchange universe."""
    if not plan:
        return {"symbols": [], "bytes_freed": 0}
    tiers = plan.get("tiers") or {}
    udiff = plan.get("universe_diff") or {}
    removed_set = set(udiff.get("removed") or [])
    exited = set(tiers.get("top100_diff", {}).get("exited") or [])
    exited |= set(tiers.get("top50_diff", {}).get("exited") or [])
    candidates = sorted(exited & removed_set)
    return cleanup_orphan_symbols(candidates, dry=dry)


def run_prune_disk(*, dry: bool = False) -> int:
    cmd = [str(PY), "-u", "tools/prune_disk.py"]
    if dry:
        cmd.append("--dry-run")
    return subprocess.call(cmd, cwd=ROOT)


def run_builtin_cleaner(
    *,
    reason: str = "change",
    plan: dict | None = None,
    extra_orphans: list[str] | None = None,
    dry_run: bool = False,
    skip_disk: bool = False,
) -> dict[str, Any]:
    """
    Full post-change cleanup. Call after universe sync, monthly maint, corporate migrations.
    """
    _log(f"start reason={reason} dry_run={dry_run}")
    report: dict[str, Any] = {"reason": reason, "started_at_utc": _now(), "steps": {}}

    orphans: list[str] = list(extra_orphans or [])
    if plan:
        udiff = plan.get("universe_diff") or {}
        orphans.extend(udiff.get("removed") or [])
        corp = plan.get("corporate") or {}
        for ev in corp.get("delistings") or []:
            sym = ev.get("old") or ev.get("symbol")
            if sym:
                orphans.append(str(sym).upper())
        for m in corp.get("migrations_applied") or []:
            old = m.get("old")
            if old and m.get("kind") == "delist":
                orphans.append(str(old).upper())

    orphans = list(dict.fromkeys(s.upper() for s in orphans if s))
    report["steps"]["orphans"] = cleanup_orphan_symbols(orphans, dry=dry_run)
    report["steps"]["tier_exits"] = cleanup_tier_exits(plan, dry=dry_run)
    report["steps"]["temp_files"] = cleanup_stale_temp_files(dry=dry_run)

    if not skip_disk:
        rc = run_prune_disk(dry=dry_run)
        report["steps"]["prune_disk_rc"] = rc

    total = sum(
        s.get("bytes_freed", 0)
        for s in report["steps"].values()
        if isinstance(s, dict)
    )
    report["bytes_freed_estimate"] = total
    report["finished_at_utc"] = _now()
    _log(f"done freed~{total} bytes orphans={report['steps']['orphans'].get('symbols', [])}")
    return report


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Built-in cleaner after universe/tier changes")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reason", default="manual")
    ap.add_argument("--plan-file", default="", help="JSON plan from universe_monthly_maintenance")
    args = ap.parse_args()
    os.chdir(ROOT)
    plan = None
    if args.plan_file and Path(args.plan_file).is_file():
        plan = json.loads(Path(args.plan_file).read_text(encoding="utf-8"))
    run_builtin_cleaner(reason=args.reason, plan=plan, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
