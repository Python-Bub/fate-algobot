#!/usr/bin/env python3
"""Find tickers with weak acc@top20 (or inverted horizon splits) and re-queue for daily retrain."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _latest_stats_by_ticker(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not path.is_file():
        return out
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue
        t = str(r.get("ticker", "")).upper()
        if t:
            out[t] = r
    return out


def _weak_from_stats(r: dict, min_top20: float, min_meta: float) -> list[str]:
    reasons: list[str] = []
    for key, label in (
        ("short_top20", "short"),
        ("long_top20", "long"),
        ("daily_top20", "daily"),
        ("xlong_top20", "xlong"),
    ):
        v = r.get(key)
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv != fv:
            continue
        if fv < min_top20:
            reasons.append(f"{label}@{fv:.3f}")
    ma = r.get("meta_auc")
    if ma is not None:
        try:
            if float(ma) < min_meta:
                reasons.append(f"meta@{float(ma):.3f}")
        except (TypeError, ValueError):
            pass
    return reasons


def weak_heads_from_reasons(reasons: list[str]) -> set[str]:
    """Map weak reason strings to head names needing retrain."""
    heads: set[str] = set()
    for r in reasons:
        if r.startswith("short@") or r.startswith("null:short"):
            heads.add("short")
        elif r.startswith("long@") or r.startswith("null:long"):
            heads.add("long")
        elif r.startswith("daily@") or r.startswith("null:daily"):
            heads.add("daily")
        elif r.startswith("xlong@") or r.startswith("null:xlong"):
            heads.add("xlong")
        elif r.startswith("meta@") or r.startswith("null:meta"):
            heads.add("meta")
        elif r == "inverted_h_split":
            heads.update({"daily", "xlong"})
        elif r == "corrupt_bundle":
            heads.update({"short", "long", "daily", "xlong", "meta"})
    return heads


def heads_below_threshold(row: dict, *, min_top20: float, min_meta: float) -> set[str]:
    return weak_heads_from_reasons(_weak_from_stats(row, min_top20, min_meta))


def _null_heads_from_bundles(universe: set[str] | None) -> dict[str, list[str]]:
    """Scan on-disk daily pickles for missing horizon/meta heads (stats alone miss these)."""
    import joblib

    models = ROOT / "models"
    out: dict[str, list[str]] = {}
    if not models.is_dir():
        return out
    head_keys = (
        ("model_short", "null:short"),
        ("model_long", "null:long"),
        ("model_daily", "null:daily"),
        ("model_xlong", "null:xlong"),
        ("model_meta", "null:meta"),
    )
    for p in models.glob("*_model.pkl"):
        if p.stat().st_size < 1000:
            continue
        sym = p.name[: -len("_model.pkl")].upper()
        if universe is not None and sym not in universe:
            continue
        try:
            b = joblib.load(p)
        except Exception:
            out[sym] = ["corrupt_bundle"]
            continue
        if not isinstance(b, dict):
            out[sym] = ["corrupt_bundle"]
            continue
        reasons = [label for key, label in head_keys if b.get(key) is None]
        if reasons:
            out[sym] = reasons
    return out


def _inverted_horizon_from_log(log_path: Path) -> set[str]:
    """Tickers whose H1d/H60d logged test>train (pre-fix inverted split)."""
    bad: set[str] = set()
    if not log_path.is_file():
        return bad
    pat = re.compile(
        r"\[(H1d|H60d)\]\s+([A-Z0-9.-]+)\s+acc=[\d.]+ acc@top20=[\d.]+ train=(\d+) test=(\d+)"
    )
    for ln in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = pat.search(ln)
        if not m:
            continue
        ticker, tr, te = m.group(2), int(m.group(3)), int(m.group(4))
        if te > tr * 2:
            bad.add(ticker.upper())
    return bad


def _clear_checkpoint(symbols: list[str], ck_path: Path) -> None:
    if not symbols or not ck_path.is_file():
        return
    try:
        data = json.loads(ck_path.read_text(encoding="utf-8"))
    except Exception:
        return
    sym_set = {s.upper() for s in symbols}
    data["done"] = sorted(set(data.get("done", [])) - sym_set)
    failed = dict(data.get("failed", {}))
    for s in sym_set:
        failed.pop(s, None)
    data["failed"] = failed
    ck_path.write_text(json.dumps(data, indent=0), encoding="utf-8")


def find_weak_symbols(
    *,
    min_top20: float,
    min_meta: float,
    top100_only: bool,
    stats_path: Path | None = None,
    log_path: Path | None = None,
) -> dict[str, list[str]]:
    stats_path = stats_path or ROOT / "data/train_run_stats.jsonl"
    log_path = log_path or ROOT / "logs/enhancement_queue_latest.log"
    latest = _latest_stats_by_ticker(stats_path)
    inverted = _inverted_horizon_from_log(log_path)

    universe: set[str] | None = None
    if top100_only:
        sys.path.insert(0, str(ROOT))
        from fortress_universe import load_top100_symbols

        universe = {s.upper() for s in load_top100_symbols()}
    elif os.getenv("RETRAIN_QUALITY_ONLY", "").lower() in ("1", "true", "yes"):
        sys.path.insert(0, str(ROOT))
        from fortress_universe import trade_quality_universe

        universe = set(trade_quality_universe())

    weak: dict[str, list[str]] = {}
    for t, r in sorted(latest.items()):
        if universe is not None and t not in universe:
            continue
        reasons = _weak_from_stats(r, min_top20, min_meta)
        if t in inverted:
            reasons.append("inverted_h_split")
        if reasons:
            weak[t] = reasons

    # Bundle nulls are invisible in stats (rejected heads never write daily_top20).
    if os.getenv("RETRAIN_SCAN_NULL_HEADS", "true").lower() in ("1", "true", "yes"):
        for t, reasons in _null_heads_from_bundles(universe).items():
            weak.setdefault(t, [])
            for r in reasons:
                if r not in weak[t]:
                    weak[t].append(r)

    # Short listings (SPCX): tiny holdouts yield top20=0 forever — if the pickle
    # has all horizon heads filled, treat as cleared when ACCEPT_FILLED is on.
    if os.getenv("SHORT_HIST_ACCEPT_FILLED", "true").lower() in ("1", "true", "yes"):
        short_hist = {
            x.strip().upper()
            for x in os.getenv("TOP100_ONLINE_SHORT_HIST", "SPCX,SKHY").split(",")
            if x.strip()
        }
        for t in list(weak):
            if t not in short_hist:
                continue
            # Keep if null heads remain
            if any(str(r).startswith("null:") for r in weak[t]):
                continue
            p = ROOT / "models" / f"{t}_model.pkl"
            if not p.is_file():
                continue
            try:
                import joblib

                b = joblib.load(p)
                heads = ("model_short", "model_long", "model_daily", "model_xlong", "model_meta")
                if all(b.get(h) is not None for h in heads):
                    weak.pop(t, None)
            except Exception:
                pass
    return weak


def print_weak_report(weak: dict[str, list[str]], min_top20: float, min_meta: float) -> None:
    print(f"[retrain-weak] candidates: {len(weak)} (min_top20={min_top20}, min_meta={min_meta})")
    for t in sorted(weak)[:60]:
        print(f"  {t:8} {' | '.join(weak[t])}")
    if len(weak) > 60:
        print(f"  ... +{len(weak) - 60} more")


def _batch_env(
    syms: list[str],
    *,
    min_top20: float,
    min_meta: float,
    attempt: int,
) -> dict[str, str]:
    from tools.proper_finish_env import max_quality_env

    sym_file = ROOT / "data/retrain_weak_symbols.json"
    sym_file.write_text(json.dumps(sorted(syms)), encoding="utf-8")

    env = os.environ.copy()
    env.update(max_quality_env())
    env["TRAIN_TICKER_TIMEOUT_SEC"] = os.getenv("RETRAIN_WEAK_TIMEOUT_SEC", "0")
    env["PROPER_TRAIN_TIMEOUT_SEC"] = "0"
    auto_retrain = os.getenv("RETRAIN_WEAK_AUTO_IN_TRAINER", "true").lower() in ("1", "true", "yes")
    env.update(
        {
            "FRESH_MODEL_REBUILD": "true",
            "MULTI_HORIZON_TRAIN": "true",
            "HORIZON_USE_ENSEMBLE": "true",
            "MIN_HEAD_TOP20": str(min_top20),
            "RETRAIN_MIN_TOP20": str(min_top20),
            "MIN_META_AUC": str(min_meta),
            "TRAIN_SYMBOLS_FILE": str(sym_file),
            "AUTO_RETRAIN_LOW_TOP20": "true" if auto_retrain or attempt > 1 else "false",
            "TRAIN_TICKER_TIMEOUT_SEC": os.getenv("RETRAIN_WEAK_TIMEOUT_SEC", "0"),
            "HEAVY_NEWS_INTEL": "true",
            "USE_TRAIN_NEWS_HISTORY": "true",
            "USE_AI_TRAINING_GRADER": "true" if attempt >= 2 else os.getenv("USE_AI_TRAINING_GRADER", "true"),
        }
    )
    # Hard names: fewer parallel workers + stronger in-trainer retry from pass 1.
    if attempt >= 3:
        env["ML_MAX_DEPTH_LONG"] = str(max(4, int(env.get("ML_MAX_DEPTH_LONG", "12")) - 2))
        env["ML_MAX_DEPTH_SHORT"] = str(max(4, int(env.get("ML_MAX_DEPTH_SHORT", "10")) - 2))
    if attempt >= 5:
        env["TRAIN_TIME_ORDER_SPLIT"] = "true"
        env["LONG_OVERFIT_TRAIN_TEST_GAP"] = "0.22"
    return env


def _workers_for_attempt(base_workers: int, attempt: int, n_syms: int) -> int:
    if n_syms <= 2:
        return 1
    if attempt >= 4:
        return 1
    if attempt >= 2:
        return max(1, min(base_workers, 2))
    return base_workers


def run_retrain_batch(
    syms: list[str],
    *,
    min_top20: float,
    min_meta: float,
    workers: int,
    attempt: int = 1,
) -> int:
    if not syms:
        return 0

    _clear_checkpoint(syms, ROOT / "data/train_checkpoint.json")
    print(f"[retrain-weak] round {attempt}: cleared {len(syms)} from train_checkpoint.json")

    env = _batch_env(syms, min_top20=min_top20, min_meta=min_meta, attempt=attempt)
    w = _workers_for_attempt(workers, attempt, len(syms))

    py = ROOT / "venv/bin/python"
    cmd = [str(py), "-u", "parallel_train.py", "--pipeline", "daily", "--workers", str(w)]
    log_dir = ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logf = log_dir / f"retrain_weak_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    latest = log_dir / "retrain_weak_latest.log"
    try:
        latest.unlink(missing_ok=True)
    except OSError:
        pass
    latest.symlink_to(logf.name)
    print(f"[retrain-weak] round {attempt} launching: {' '.join(cmd)}  workers={w}")
    print(f"[retrain-weak] log → {logf}")
    with open(logf, "w", encoding="utf-8") as logfh:
        return subprocess.call(cmd, cwd=ROOT, env=env, stdout=logfh, stderr=subprocess.STDOUT)


def run_until_clear(
    *,
    min_top20: float,
    min_meta: float,
    top100_only: bool,
    workers: int,
    max_rounds: int,
    pause_sec: int,
) -> int:
    for attempt in range(1, max_rounds + 1):
        weak = find_weak_symbols(min_top20=min_top20, min_meta=min_meta, top100_only=top100_only)
        print_weak_report(weak, min_top20, min_meta)
        if not weak:
            print("[retrain-weak] all top100 metrics pass — done")
            return 0

        syms = sorted(weak)
        print(f"[retrain-weak] === round {attempt}/{max_rounds} — {len(syms)} symbols ===")
        rc = run_retrain_batch(
            syms,
            min_top20=min_top20,
            min_meta=min_meta,
            workers=workers,
            attempt=attempt,
        )
        if rc != 0:
            print(f"[retrain-weak] round {attempt} exited rc={rc}")

        if attempt < max_rounds:
            time.sleep(max(0, pause_sec))

    weak = find_weak_symbols(min_top20=min_top20, min_meta=min_meta, top100_only=top100_only)
    if not weak:
        print("[retrain-weak] all clear after final round")
        return 0
    print(f"[retrain-weak] stopped after {max_rounds} rounds — {len(weak)} still weak:")
    print_weak_report(weak, min_top20, min_meta)
    return 1


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    ap = argparse.ArgumentParser(description="Re-queue weak-accuracy models for daily retrain")
    ap.add_argument(
        "--min-top20",
        type=float,
        default=float(os.getenv("RETRAIN_MIN_TOP20", os.getenv("MIN_HEAD_TOP20", "0.6"))),
    )
    ap.add_argument("--min-meta", type=float, default=float(os.getenv("MIN_META_AUC", "0.52")))
    ap.add_argument("--top100-only", action="store_true", help="Limit to top-100 universe")
    ap.add_argument("--run", action="store_true", help="Clear checkpoint and launch parallel_train daily")
    ap.add_argument(
        "--until-clear",
        action="store_true",
        help="Repeat retrain rounds until no weak top100 names remain (or --max-rounds)",
    )
    ap.add_argument("--max-rounds", type=int, default=int(os.getenv("RETRAIN_WEAK_MAX_ROUNDS", "12")))
    ap.add_argument("--pause-sec", type=int, default=int(os.getenv("RETRAIN_WEAK_PAUSE_SEC", "5")))
    ap.add_argument("--workers", type=int, default=int(os.getenv("RETRAIN_WEAK_WORKERS", "4")))
    args = ap.parse_args()

    weak = find_weak_symbols(
        min_top20=args.min_top20,
        min_meta=args.min_meta,
        top100_only=args.top100_only,
    )
    print_weak_report(weak, args.min_top20, args.min_meta)

    if args.until_clear:
        if not weak:
            print("[retrain-weak] nothing to do")
            return 0
        return run_until_clear(
            min_top20=args.min_top20,
            min_meta=args.min_meta,
            top100_only=args.top100_only,
            workers=args.workers,
            max_rounds=args.max_rounds,
            pause_sec=args.pause_sec,
        )

    if not args.run or not weak:
        if not weak:
            print("[retrain-weak] nothing to do")
        else:
            print("[retrain-weak] dry-run only — pass --run or --until-clear")
        return 0

    return run_retrain_batch(
        sorted(weak),
        min_top20=args.min_top20,
        min_meta=args.min_meta,
        workers=args.workers,
        attempt=1,
    )


if __name__ == "__main__":
    raise SystemExit(main())
