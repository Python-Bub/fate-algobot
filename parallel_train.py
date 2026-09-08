"""
Parallel universe trainer — runs N worker processes against a shared checkpoint.

Each worker pulls a ticker off a queue, calls the per-ticker trainer (daily-and-up
or intraday), and atomically appends the result to the shared checkpoint.

Defaults to 4 workers (leaves CPU/IO headroom and respects Alpaca's 200 req/min
rate limit).  Use --workers N to override; >6 risks rate limits.

Usage:
    # Daily-and-up (1d / 5d / 20d / 60d heads)
    python parallel_train.py --pipeline daily   --workers 6

    # Intraday (5-min + 60-min heads)
    python parallel_train.py --pipeline intraday --workers 4
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import signal
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
CHECKPOINT_DAILY = str(ROOT / "data" / "train_checkpoint.json")
CHECKPOINT_INTRADAY = str(ROOT / "data" / "intraday_train_checkpoint.json")


def _abs_checkpoint(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (ROOT / p)


def _load_checkpoint(path: str) -> tuple[set[str], dict[str, str]]:
    p = _abs_checkpoint(path)
    if not p.is_file():
        return set(), {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return set(), {}
    return set(data.get("done", [])), dict(data.get("failed", {}))


def _atomic_write_json(path: str | Path, payload: dict) -> None:
    """Write JSON via a unique tmp file. Retry when iCloud/cleaner deletes the tmp mid-replace."""
    dest = _abs_checkpoint(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, indent=0)
    last_err: Exception | None = None
    for attempt in range(8):
        tmp = dest.parent / f".{dest.name}.{os.getpid()}.{time.time_ns()}.tmp"
        try:
            tmp.write_text(data, encoding="utf-8")
            os.replace(tmp, dest)
            return
        except Exception as e:  # noqa: BLE001 — never crash the writer process
            last_err = e
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            dest.parent.mkdir(parents=True, exist_ok=True)
            time.sleep(0.05 * (attempt + 1))
    if last_err is not None:
        print(f"[PARALLEL] checkpoint persist failed after retries: {last_err}", flush=True)


def _checkpoint_writer(checkpoint_path: str, in_q: mp.Queue, queue_size: int) -> None:
    """Single writer process: drains result events and persists atomically.

    Must never exit on a persist error — a dead writer fills out_q and deadlocks workers
    (Aug 2026 stall: FileNotFoundError on os.replace left intraday idle for 3 days).
    """
    done, failed = _load_checkpoint(checkpoint_path)
    cp = _abs_checkpoint(checkpoint_path)
    cp.parent.mkdir(parents=True, exist_ok=True)

    started = time.time()
    last_log = started
    seen = 0
    session_ok = 0
    session_fail = 0
    while True:
        msg = in_q.get()
        if msg is None:
            break
        try:
            sym, ok, err = msg
        except Exception as e:  # noqa: BLE001
            print(f"[PARALLEL] bad checkpoint event {msg!r}: {e}", flush=True)
            continue
        seen += 1
        if ok:
            session_ok += 1
            done.add(sym)
            failed.pop(sym, None)
        else:
            session_fail += 1
            failed[sym] = err

        _atomic_write_json(cp, {"done": sorted(done), "failed": failed})

        now = time.time()
        if now - last_log >= 10:
            rate = seen / max(now - started, 1.0) * 60  # symbols processed/min (this queue)
            left = max(0, queue_size - seen)
            eta_hours = left / max(rate, 1e-6) / 60.0 if rate else float("inf")
            print(
                f"[PROGRESS] session {seen}/{queue_size}  saved={session_ok}  "
                f"failed={session_fail}  left={left}  rate={rate:.1f}/min  ETA={eta_hours:.1f}h  "
                f"(checkpoint entries={len(done)})",
                flush=True,
            )
            last_log = now


def _worker_daily(sym: str, out_q: mp.Queue) -> None:
    """Daily-and-up trainer.  Imported lazily inside the worker."""
    try:
        from model_trainer import _train_single_ticker, training_saved_model

        _train_single_ticker(sym)
        if training_saved_model(sym):
            out_q.put((sym, True, ""))
        else:
            out_q.put((sym, False, "skipped_no_model"))
    except Exception as e:  # noqa: BLE001
        out_q.put((sym, False, f"{type(e).__name__}: {str(e)[:160]}"))


def _worker_intraday(sym: str, out_q: mp.Queue) -> None:
    try:
        from fortress_universe import has_trained_intraday_bundle
        from intraday.intraday_trainer import train_intraday

        train_intraday(sym)
        if has_trained_intraday_bundle(sym):
            out_q.put((sym, True, ""))
        else:
            out_q.put((sym, False, "placeholder_intraday"))
    except Exception as e:  # noqa: BLE001
        out_q.put((sym, False, f"{type(e).__name__}: {str(e)[:160]}"))


def _recover_daily_save(sym: str, err: str) -> tuple[str, bool, str]:
    """If the worker timed out or died after writing the bundle, count it as success."""
    try:
        from model_trainer import training_saved_model

        if training_saved_model(sym):
            return sym, True, f"recovered:{err}"
    except Exception:
        pass
    return sym, False, err


def _run_ticker_isolated(fn, sym: str, timeout_sec: int) -> tuple[str, bool, str]:
    """Run one ticker in a child process; hard-kill if it hangs (macOS-safe)."""
    ctx = mp.get_context("spawn")
    result_q: mp.Queue = ctx.Queue(maxsize=1)
    p = ctx.Process(target=fn, args=(sym, result_q), daemon=True)
    p.start()
    p.join(timeout_sec)
    if timeout_sec > 0 and p.is_alive():
        p.terminate()
        p.join(10)
        if p.is_alive():
            p.kill()
            p.join(5)
        return _recover_daily_save(sym, f"Timeout: exceeded {timeout_sec}s")
    try:
        return result_q.get_nowait()
    except Exception:
        return _recover_daily_save(sym, "WorkerExitNoResult")


def _worker_loop(in_q: mp.Queue, out_q: mp.Queue, pipeline: str) -> None:
    """Pull tickers off the input queue until a sentinel."""
    fn = _worker_daily if pipeline == "daily" else _worker_intraday
    timeout_sec = int(float(os.getenv("TRAIN_TICKER_TIMEOUT_SEC", "0")))
    while True:
        sym = in_q.get()
        if sym is None:
            return
        try:
            if timeout_sec > 0:
                result = _run_ticker_isolated(fn, sym, timeout_sec)
                out_q.put(result)
            else:
                fn(sym, out_q)
        except Exception as e:  # noqa: BLE001  (defensive)
            out_q.put((sym, False, f"WorkerCrash: {str(e)[:160]}"))


def _load_symbol_override(*, honor_size_caps: bool = True) -> list[str] | None:
    """Optional symbol subset. Size caps (top50/top100) shrink the universe — skip for gap-fill."""
    if honor_size_caps:
        if os.getenv("TRAIN_TOP50_ONLY", "false").lower() in ("1", "true", "yes"):
            from fortress_universe import load_top50pct_symbols

            return load_top50pct_symbols()
        if os.getenv("TRAIN_TOP100_ONLY", "false").lower() in ("1", "true", "yes"):
            from fortress_universe import load_top100_symbols

            return load_top100_symbols()
    path = os.getenv("TRAIN_SYMBOLS_FILE", "").strip()
    # Empty / unset = full universe. Gap-fill must not inherit a stale top50 file from .env.
    if path and os.path.isfile(path) and not honor_size_caps:
        # missing-only: only honor explicit batch files when TRAIN_MISSING_USE_SYMBOLS_FILE=true
        if os.getenv("TRAIN_MISSING_USE_SYMBOLS_FILE", "false").lower() not in (
            "1",
            "true",
            "yes",
        ):
            return None
    if path and os.path.isfile(path):
        import json

        try:
            doc = json.loads(open(path, encoding="utf-8").read())
            if isinstance(doc, list):
                return [str(s).upper() for s in doc if s]
            return [str(s).upper() for s in doc.get("symbols", []) if s]
        except Exception:
            return None
    return None


def _load_universe(pipeline: str) -> list[str]:
    override = _load_symbol_override()
    if override:
        return list(dict.fromkeys(override))
    if os.getenv("TRAIN_CONFIG_TICKERS_ONLY", "false").lower() in ("1", "true", "yes"):
        try:
            from config import TRAIN_TICKERS

            return list(dict.fromkeys(TRAIN_TICKERS))
        except Exception:
            return []
    from universe_provider import load_universe_with_cap
    from fortress_universe import prioritize_training_universe

    raw = load_universe_with_cap(max_symbols=None)
    return prioritize_training_universe(raw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--pipeline",
        choices=["daily", "intraday"],
        required=True,
        help="which trainer to parallelize",
    )
    ap.add_argument("--workers", type=int, default=4, help="worker process count")
    ap.add_argument(
        "--max-symbols",
        type=int,
        default=None,
        help="cap the universe at the first N (after de-dup)",
    )
    ap.add_argument(
        "--missing-only",
        action="store_true",
        help="daily: no *_model.pkl yet; intraday: has daily but no real intraday bundle (round-robin)",
    )
    args = ap.parse_args()

    try:
        from data_platform.market_prices import configure_process_prices

        configure_process_prices(training=True)
    except Exception:
        pass

    checkpoint = CHECKPOINT_DAILY if args.pipeline == "daily" else CHECKPOINT_INTRADAY
    done, failed = _load_checkpoint(checkpoint)
    if args.missing_only and args.pipeline == "daily":
        # Gap-fill defaults to full universe (letter-fair). Explicit TRAIN_TOP100_ONLY /
        # TRAIN_TOP50_ONLY must still apply — otherwise top100_perfect --missing-only
        # trains 9k junk and megas stay empty under memory pressure.
        honor_caps = (
            os.getenv("TRAIN_TOP100_ONLY", "false").lower() in ("1", "true", "yes")
            or os.getenv("TRAIN_TOP50_ONLY", "false").lower() in ("1", "true", "yes")
            or os.getenv("TRAIN_MISSING_HONOR_SIZE_CAPS", "false").lower()
            in ("1", "true", "yes")
        )
        override = _load_symbol_override(honor_size_caps=honor_caps)
        from model_trainer import training_saved_model

        if override:
            universe = [
                s
                for s in dict.fromkeys(override)
                if not training_saved_model(s)
            ]
        else:
            from fortress_universe import is_core_trainable_equity, load_top100_symbols, prioritize_training_universe
            from universe_provider import load_universe_with_cap

            universe = [
                s
                for s in load_universe_with_cap(max_symbols=None)
                if is_core_trainable_equity(s) and not training_saved_model(s)
            ]
            if os.getenv("TRAIN_JUNK_SKIP_TOP100", "true").lower() in ("1", "true", "yes"):
                top = {x.upper() for x in load_top100_symbols()}
                before = len(universe)
                universe = [s for s in universe if s.upper() not in top]
                skipped = before - len(universe)
                if skipped:
                    print(
                        f"[PARALLEL] junk pass skips {skipped} top-100 names "
                        f"(top100_perfect rebuilds them later)",
                        flush=True,
                    )
            universe = prioritize_training_universe(universe)
        if honor_caps:
            print(
                f"[PARALLEL] missing-only honor size caps → {len(universe)} symbols",
                flush=True,
            )
    elif args.missing_only and args.pipeline == "intraday":
        from fortress_universe import (
            has_trained_intraday_bundle,
            intraday_cached_gap_skip,
            is_core_trainable_equity,
            prioritize_training_universe,
        )
        from model_trainer import training_saved_model

        model_dir = Path(os.getenv("MODEL_DIR", "models"))
        universe = [
            p.name[: -len("_model.pkl")].upper()
            for p in model_dir.glob("*_model.pkl")
            if p.stat().st_size > 1000
            and is_core_trainable_equity(p.name[: -len("_model.pkl")].upper())
            and training_saved_model(p.name[: -len("_model.pkl")].upper())
            and not has_trained_intraday_bundle(p.name[: -len("_model.pkl")].upper())
            and not intraday_cached_gap_skip(p.name[: -len("_model.pkl")].upper())
        ]
        universe = prioritize_training_universe(universe)
        # Honor TRAIN_TOP100_ONLY / TRAIN_TOP50_ONLY when set (top100_perfect).
        honor_caps = (
            os.getenv("TRAIN_TOP100_ONLY", "false").lower() in ("1", "true", "yes")
            or os.getenv("TRAIN_TOP50_ONLY", "false").lower() in ("1", "true", "yes")
        )
        override = _load_symbol_override(honor_size_caps=honor_caps)
        if override:
            allow = {s.upper() for s in override}
            universe = [s for s in universe if s in allow]
    else:
        universe = _load_universe(args.pipeline)
    if args.max_symbols:
        universe = universe[: args.max_symbols]
    if args.missing_only and args.pipeline == "daily":
        from model_trainer import training_saved_model

        pruned = sorted(s for s in done if training_saved_model(s))
        if len(pruned) < len(done):
            print(
                f"[PARALLEL] pruned checkpoint done {len(done)} → {len(pruned)} "
                f"(dropped symbols with no model file on disk)",
                flush=True,
            )
            done = set(pruned)
            _atomic_write_json(checkpoint, {"done": pruned, "failed": failed})
    elif args.missing_only and args.pipeline == "intraday":
        from fortress_universe import has_trained_intraday_bundle

        pruned = sorted(s for s in done if has_trained_intraday_bundle(s))
        if len(pruned) < len(done):
            print(
                f"[PARALLEL] pruned intraday checkpoint done {len(done)} → {len(pruned)} "
                f"(dropped placeholder-only entries)",
                flush=True,
            )
            done = set(pruned)
            _atomic_write_json(checkpoint, {"done": pruned, "failed": failed})

    skip = done | set(failed.keys()) if not args.missing_only else set()
    pending = [s for s in universe if s not in skip]

    print(
        f"[PARALLEL] pipeline={args.pipeline}  workers={args.workers}  "
        f"queue={len(pending)}  (candidates={len(universe)})  checkpoint_done={len(done)}  "
        f"checkpoint_failed={len(failed)}",
        flush=True,
    )
    if not pending:
        print("[PARALLEL] nothing to do — checkpoint complete.")
        return 0

    ctx = mp.get_context("spawn")  # safe with joblib/sklearn under macOS
    in_q: mp.Queue = ctx.Queue()
    out_q: mp.Queue = ctx.Queue(maxsize=args.workers * 4)
    checkpoint_abs = str(_abs_checkpoint(checkpoint))

    def _spawn_writer() -> mp.Process:
        proc = ctx.Process(
            target=_checkpoint_writer,
            args=(checkpoint_abs, out_q, len(pending)),
            daemon=False,
        )
        proc.start()
        return proc

    writer = _spawn_writer()

    workers = [
        ctx.Process(target=_worker_loop, args=(in_q, out_q, args.pipeline), daemon=False)
        for _ in range(args.workers)
    ]
    for w in workers:
        w.start()

    def _shutdown(_signum=None, _frame=None):  # graceful SIGINT
        print("\n[PARALLEL] SIGINT — draining and stopping workers cleanly…", flush=True)
        for _ in workers:
            in_q.put(None)
        for w in workers:
            w.join(timeout=120)
        out_q.put(None)
        writer.join(timeout=30)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    for sym in pending:
        in_q.put(sym)
    for _ in workers:
        in_q.put(None)

    for w in workers:
        while w.is_alive():
            w.join(timeout=5)
            if not writer.is_alive():
                print("[PARALLEL] checkpoint writer died — restarting (queue drain)", flush=True)
                writer = _spawn_writer()
    out_q.put(None)
    writer.join(timeout=60)
    if writer.is_alive():
        writer.terminate()
        writer.join(timeout=10)
    print("[PARALLEL] all workers complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
