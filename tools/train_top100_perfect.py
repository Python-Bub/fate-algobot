#!/usr/bin/env python3
"""Deep retrain top-100 market-cap names: daily + intraday + LSTM + neural replay."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _clear_checkpoint_symbols(path: Path, symbols: list[str]) -> None:
    if not path.is_file():
        return
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    sym_set = {s.upper() for s in symbols}
    data["done"] = sorted(set(data.get("done", [])) - sym_set)
    failed = dict(data.get("failed", {}))
    for s in sym_set:
        failed.pop(s, None)
    data["failed"] = failed
    path.write_text(json.dumps(data, indent=0), encoding="utf-8")


def _missing_daily() -> list[str]:
    from fortress_universe import load_top100_symbols
    from model_trainer import training_saved_model

    return [s for s in load_top100_symbols() if not training_saved_model(s)]


def _run(cmd: list[str], env: dict, label: str, step_timeout: int) -> int:
    print(f"\n[top100-perfect] === {label} ===", flush=True)
    try:
        return subprocess.call(cmd, cwd=ROOT, env=env, timeout=step_timeout or None)
    except subprocess.TimeoutExpired:
        print(
            f"[top100-perfect] TIMEOUT: {label} exceeded {step_timeout}s — "
            "killing stuck pool and continuing",
            file=sys.stderr,
            flush=True,
        )
        subprocess.call(["pkill", "-KILL", "-f", "parallel_train.py"], cwd=ROOT)
        return 124


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    from fortress_universe import load_top100_symbols
    from model_trainer import training_saved_model

    syms = load_top100_symbols()
    fresh = str(os.getenv("FRESH_MODEL_REBUILD", "false")).strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
        "on",
    )
    missing_daily = _missing_daily()
    # Gap-fill by default: only touch symbols without a saved daily model.
    # Full rebuild (clear all checkpoints) only when FRESH_MODEL_REBUILD=true.
    target_daily = syms if fresh else missing_daily
    print(
        f"[top100-perfect] {len(syms)} symbols — "
        f"{'FRESH full rebuild' if fresh else f'gap-fill {len(missing_daily)} missing daily'} "
        "+ intraday + LSTM + neural",
        flush=True,
    )

    if target_daily:
        _clear_checkpoint_symbols(ROOT / "data/train_checkpoint.json", target_daily)
    if fresh:
        _clear_checkpoint_symbols(ROOT / "data/intraday_train_checkpoint.json", syms)
        ck_lstm = ROOT / "data/lstm_train_checkpoint.json"
        if ck_lstm.is_file():
            import json

            try:
                data = json.loads(ck_lstm.read_text(encoding="utf-8"))
                sym_set = {s.upper() for s in syms}
                data["done"] = sorted(set(data.get("done", [])) - sym_set)
                ck_lstm.write_text(json.dumps(data, indent=0), encoding="utf-8")
            except Exception:
                pass

    from tools.proper_finish_env import max_quality_env

    env = os.environ.copy()
    env.update(max_quality_env())
    # Prefer explicit lean workers over proper_finish's default of 4 (429s under Yahoo).
    daily_workers = (
        os.getenv("TOP100_DAILY_WORKERS")
        or os.getenv("PROPER_TOP100_DAILY_WORKERS")
        or "2"
    )
    intra_workers = os.getenv("TOP100_INTRADAY_WORKERS") or "2"
    # Polygon first (Alpaca paper keys often 403 on market data). Allow explicit
    # Yahoo override for leftovers after Polygon 429 exhaustion.
    force_yahoo = str(os.getenv("FORCE_YAHOO_PRICES", "false")).lower() in (
        "1",
        "true",
        "yes",
    ) or str(os.getenv("USE_YAHOO_FIRST", "false")).lower() in ("1", "true", "yes")
    has_poly = bool(env.get("POLYGON_API_KEY", "").strip())
    has_alpaca = bool(env.get("ALPACA_API_KEY", "").strip()) and bool(
        env.get("ALPACA_SECRET_KEY", "").strip()
    )
    if force_yahoo:
        price_src = "yfinance"
        has_poly = False
    elif has_poly:
        price_src = "hybrid_polygon"
    elif has_alpaca:
        price_src = "hybrid_alpaca"
    else:
        price_src = env.get("PRICE_DATA_SOURCE", "yfinance")
    env.update(
        {
            "TRAIN_TOP100_ONLY": "true",
            # Never purge megas before rewrite — that left AAPL/etc empty when Yahoo/data stalled.
            "FRESH_MODEL_REBUILD": "true" if fresh else "false",
            "TRAIN_FORCE_YAHOO": "true" if force_yahoo else "false",
            "FORCE_YAHOO_PRICES": "true" if force_yahoo else "false",
            "USE_YAHOO_FIRST": "true" if force_yahoo else "false",
            "USE_POLYGON_FIRST": "false" if force_yahoo else ("true" if has_poly else "false"),
            "USE_PRICE_CACHE": "true",
            "PRICE_DATA_SOURCE": price_src,
            "PRICE_FETCH_BLOCK": "true",
            "YAHOO_SKIP_WHEN_LIMITED": "false",
            "YAHOO_MIN_INTERVAL_SEC": os.getenv("YAHOO_MIN_INTERVAL_SEC", "0.75"),
            "YAHOO_RATE_LIMIT_COOLDOWN_SEC": os.getenv("YAHOO_RATE_LIMIT_COOLDOWN_SEC", "45"),
            "SKIP_YAHOO_FALLBACK": "false",
            "TRAIN_JUNK_SKIP_TOP100": "false",
            "TRAIN_MISSING_USE_SYMBOLS_FILE": "false",
            "TRAIN_TIME_ORDER_SPLIT": "true",
            "MULTI_HORIZON_TRAIN": "true",
            "USE_CLASSIC_QUANT_FEATURES": "true",
            "HEAVY_NEWS_INTEL": os.getenv("HEAVY_NEWS_INTEL", env.get("HEAVY_NEWS_INTEL", "true")),
            "USE_TRAIN_NEWS_HISTORY": os.getenv("USE_TRAIN_NEWS_HISTORY", env.get("USE_TRAIN_NEWS_HISTORY", "true")),
            "USE_AI_TRAINING_GRADER": os.getenv("USE_AI_TRAINING_GRADER", env.get("USE_AI_TRAINING_GRADER", "true")),
            "FAST_UNIVERSE_TRAIN": os.getenv(
                "TOP100_FAST_UNIVERSE_TRAIN", env.get("FAST_UNIVERSE_TRAIN", "false")
            ),
            "LSTM_TRAIN_SCOPE": "top100",
            "LSTM_EPOCHS": env.get("TOP100_LSTM_EPOCHS", "24"),
            "LSTM_WORKERS": os.getenv("TOP100_LSTM_WORKERS", "2"),
            "INTRADAY_LOOKBACK_DAYS": env.get("TOP100_INTRADAY_LOOKBACK", "365"),
            "INTRADAY_GAP_SKIP_CACHED_PLACEHOLDER": "false",
            "NEURAL_EPOCHS": env.get("TOP100_NEURAL_EPOCHS", "6"),
            "NEURAL_MIN_SAMPLES": env.get("TOP100_NEURAL_MIN_SAMPLES", "40"),
            "TRAIN_TICKER_TIMEOUT_SEC": os.getenv("TOP100_TRAIN_TIMEOUT_SEC", "300"),
            "AUTO_RETRAIN_LOW_TOP20": "false",
            "NETWORK_FIRST": "true",
            "TOP100_DAILY_WORKERS": daily_workers,
            "TOP100_INTRADAY_WORKERS": intra_workers,
            "OMP_NUM_THREADS": os.getenv("OMP_NUM_THREADS", "1"),
            "MKL_NUM_THREADS": os.getenv("MKL_NUM_THREADS", "1"),
            "OPENBLAS_NUM_THREADS": os.getenv("OPENBLAS_NUM_THREADS", "1"),
            "JOBLIB_NUM_THREADS": os.getenv("JOBLIB_NUM_THREADS", "1"),
        }
    )
    print(
        f"[top100-perfect] price_source={price_src} daily_workers={daily_workers} "
        f"cache=on fetch_block=on",
        flush=True,
    )

    py = ROOT / "venv" / "bin" / "python"
    run = ROOT / "run_all.sh"
    step_timeout = int(os.getenv("TOP100_STEP_TIMEOUT_SEC", "7200"))  # 2h default

    _run([str(py), "-u", "tools/refresh_top100.py"], env, "refresh top100 list", step_timeout)

    # Daily gap-fill with retries — never advance while megas are still empty.
    daily_rounds = max(1, int(os.getenv("TOP100_DAILY_ROUNDS", "4")))
    for round_i in range(1, daily_rounds + 1):
        miss = _missing_daily()
        if not miss and not fresh:
            print("[top100-perfect] daily models complete", flush=True)
            break
        if fresh and round_i > 1:
            miss = _missing_daily()
            if len(miss) <= 5:
                break
        daily_cmd = [
            str(py),
            "-u",
            "parallel_train.py",
            "--pipeline",
            "daily",
            "--workers",
            daily_workers,
        ]
        if not fresh or round_i > 1:
            daily_cmd.append("--missing-only")
        label = f"daily multi-horizon {'rebuild' if fresh and round_i == 1 else 'gap-fill'} round {round_i}/{daily_rounds} (missing={len(miss) if not fresh or round_i > 1 else len(syms)})"
        rc = _run(daily_cmd, env, label, step_timeout)
        if rc != 0:
            print(f"[top100-perfect] WARNING: {label} exited {rc}", file=sys.stderr, flush=True)
        miss_after = _missing_daily()
        hard = {x.strip().upper() for x in os.getenv("TOP100_HARD_SKIP", "SPCX").split(",") if x.strip()}
        blocking = [s for s in miss_after if s.upper() not in hard]
        print(
            f"[top100-perfect] after daily round {round_i}: missing={len(miss_after)} "
            f"blocking={len(blocking)}",
            flush=True,
        )
        if len(blocking) <= 2:
            break
        # Back off so Yahoo/Alpaca 429 cooldowns clear before the next blast.
        pause = int(os.getenv("TOP100_DAILY_RETRY_PAUSE_SEC", "60"))
        print(f"[top100-perfect] sleeping {pause}s before daily retry…", flush=True)
        time.sleep(pause)

    # SPCX (and similar) often lack enough history — don't block the queue forever.
    _hard_skip = {x.strip().upper() for x in os.getenv("TOP100_HARD_SKIP", "SPCX").split(",") if x.strip()}
    miss_after_daily = _missing_daily()
    miss_blocking = [s for s in miss_after_daily if s.upper() not in _hard_skip]
    if len(miss_blocking) > 2:
        print(
            f"[top100-perfect] skipping intraday/LSTM — still {len(miss_blocking)} daily missing "
            f"(total_gap={len(miss_after_daily)} hard_skip={sorted(_hard_skip & {s.upper() for s in miss_after_daily})})",
            flush=True,
        )
    else:
        rc = _run(
            [
                str(py),
                "-u",
                "parallel_train.py",
                "--pipeline",
                "intraday",
                "--missing-only",
                "--workers",
                intra_workers,
            ],
            env,
            "intraday gap-fill top100",
            step_timeout,
        )
        if rc != 0:
            print(f"[top100-perfect] WARNING: intraday exited {rc}", file=sys.stderr, flush=True)
        rc = _run([str(run), "train-lstm"], env, "LSTM heads top100", step_timeout)
        if rc != 0:
            print(f"[top100-perfect] WARNING: lstm exited {rc}", file=sys.stderr, flush=True)

        try:
            from online_learning.neural_ensemble import (
                bootstrap_replay_from_reports,
                train_neural_ensemble_for_ticker,
            )

            bootstrap_replay_from_reports(max_files=21)
            for t in syms[: int(os.getenv("TOP100_NEURAL_TRAIN_CAP", "100"))]:
                train_neural_ensemble_for_ticker(t)
        except Exception as e:
            print(f"[top100-perfect] neural pass skipped: {e}", flush=True)

    still_miss = _missing_daily()
    still_blocking = [s for s in still_miss if s.upper() not in _hard_skip]
    print(
        f"[top100-perfect] done — daily still missing: {len(still_miss)} "
        f"(blocking={len(still_blocking)})",
        flush=True,
    )

    # Standalone run (or queue subprocess): advance so `./run_all.sh resume` continues at LSTM-all.
    # Do not advance while megas are still empty — that marked the queue "done" prematurely.
    state_path = ROOT / "data/enhancement_queue_state.json"
    if state_path.is_file():
        import json

        try:
            st = json.loads(state_path.read_text(encoding="utf-8"))
            if st.get("phase") == "top100_perfect":
                notes = list(st.get("notes") or [])
                if len(still_blocking) > 2:
                    notes.append(
                        f"top100_perfect incomplete ({len(still_blocking)} blocking, "
                        f"{len(still_miss)} total missing)"
                    )
                    st["notes"] = notes[-8:]
                    state_path.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")
                    print(
                        "[top100-perfect] queue stays at top100_perfect — "
                        f"{len(still_blocking)} blocking daily models still missing",
                        flush=True,
                    )
                else:
                    st["phase"] = "lstm_all"
                    notes.append(
                        f"top100_perfect completed (blocking={len(still_blocking)} "
                        f"hard_skip_missing={sorted(set(still_miss) & _hard_skip)})"
                    )
                    st["notes"] = notes[-8:]
                    state_path.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")
                    print(
                        "[top100-perfect] queue → lstm_all (run ./run_all.sh resume to continue)",
                        flush=True,
                    )
        except Exception:
            pass

    return 0 if len(still_blocking) <= 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
