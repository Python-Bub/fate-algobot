"""Tiered training protocol — same quality stack as top100_perfect / strong retrain."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "venv" / "bin" / "python"


def _write_symbol_batch(symbols: list[str], name: str) -> Path:
    p = ROOT / "data" / f"universe_protocol_{name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted({s.upper() for s in symbols if s})), encoding="utf-8")
    return p


def _base_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    from tools.proper_finish_env import max_quality_env

    env = os.environ.copy()
    env.update(max_quality_env())
    if extra:
        env.update({k: str(v) for k, v in extra.items()})
    return env


def _run(cmd: list[str], env: dict[str, str], label: str) -> int:
    print(f"[protocol] === {label} ===", flush=True)
    return subprocess.call(cmd, cwd=ROOT, env=env)


def train_tier_daily(symbols: list[str], *, workers: int | None = None, fresh: bool = False) -> int:
    if not symbols:
        return 0
    batch = _write_symbol_batch(symbols, "daily")
    w = workers or int(os.getenv("UNIVERSE_DAILY_WORKERS", "4"))
    env = _base_env(
        {
            "TRAIN_SYMBOLS_FILE": str(batch),
            "FRESH_MODEL_REBUILD": "true" if fresh else os.getenv("FRESH_MODEL_REBUILD", "false"),
            "TRAIN_TIME_ORDER_SPLIT": "true",
            "MULTI_HORIZON_TRAIN": "true",
            "AUTO_RETRAIN_LOW_TOP20": "false",
            "TRAIN_TICKER_TIMEOUT_SEC": os.getenv("UNIVERSE_TRAIN_TIMEOUT_SEC", "0"),
        }
    )
    return _run([str(PY), "-u", "parallel_train.py", "--pipeline", "daily", "--workers", str(w)], env, f"daily x{len(symbols)}")


def train_tier_intraday(symbols: list[str], *, workers: int | None = None) -> int:
    if not symbols:
        return 0
    batch = _write_symbol_batch(symbols, "intraday")
    w = workers or int(os.getenv("UNIVERSE_INTRADAY_WORKERS", "3"))
    env = _base_env(
        {
            "TRAIN_SYMBOLS_FILE": str(batch),
            "INTRADAY_GAP_SKIP_CACHED_PLACEHOLDER": "false",
            "INTRADAY_LOOKBACK_DAYS": os.getenv("UNIVERSE_INTRADAY_LOOKBACK", "365"),
        }
    )
    return _run(
        [str(PY), "-u", "parallel_train.py", "--pipeline", "intraday", "--missing-only", "--workers", str(w)],
        env,
        f"intraday x{len(symbols)}",
    )


def strong_retrain_symbols(
    symbols: list[str],
    *,
    min_top20: float = 0.52,
    min_meta: float = 0.48,
    attempts: int = 6,
) -> dict[str, bool]:
    sys.path.insert(0, str(ROOT))
    from tools.retrain_weak_models import find_weak_symbols

    results: dict[str, bool] = {}
    for sym in symbols:
        try:
            from tools.train_coordination import should_defer_secondary_training

            if should_defer_secondary_training():
                print(f"[protocol] defer strong {sym} — heavy trainer active", flush=True)
                results[sym.upper()] = False
                continue
        except Exception:
            pass
        env = _base_env(
            {
                "STRONG_BACKENDS": os.getenv("STRONG_BACKENDS", "lgb,xgb"),
                "STRONG_N_EST": os.getenv("STRONG_N_EST", "200"),
                "STRONG_ATTEMPTS_PER_SYMBOL": str(attempts),
                "TRAIN_TICKER_TIMEOUT_SEC": "0",
                "KEEP_WEAK_HEADS": "true",
                "FILL_NULL_HEADS": "true",
                "COALESCE_EXISTING_HEADS": "true",
                "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
            }
        )
        rc = subprocess.run(
            [
                str(PY),
                "-u",
                "tools/retrain_top100_strong.py",
                "--ticker",
                sym,
                "--min-top20",
                str(min_top20),
                "--min-meta",
                str(min_meta),
            ],
            cwd=ROOT,
            env=env,
            check=False,
        ).returncode
        still = sym.upper() in find_weak_symbols(min_top20=min_top20, min_meta=min_meta, top100_only=False)
        results[sym.upper()] = rc == 0 and not still
        print(f"[protocol] strong {sym} rc={rc} ok={results[sym.upper()]}", flush=True)
    return results


def run_top100_protocol(symbols: list[str] | None = None, *, full_perfect: bool = False) -> dict[str, Any]:
    """Full top-100 stack: refresh caps → daily rebuild → intraday → strong weak pass."""
    sys.path.insert(0, str(ROOT))
    from fortress_universe import load_top100_symbols

    syms = symbols or load_top100_symbols()
    out: dict[str, Any] = {"tier": "top100", "symbols": syms}

    if full_perfect:
        rc = subprocess.call([str(PY), "-u", "tools/train_top100_perfect.py"], cwd=ROOT, env=_base_env())
        out["train_top100_perfect_rc"] = rc
        return out

    out["daily_rc"] = train_tier_daily(syms, fresh=True)
    out["intraday_rc"] = train_tier_intraday(syms)
    weak = [s for s in syms if s]
    out["strong"] = strong_retrain_symbols(weak, min_top20=0.52, min_meta=0.48, attempts=8)
    return out


def train_tier_lstm(symbols: list[str], *, workers: int | None = None) -> int:
    """Train/refresh LSTM heads for symbols that already have daily models."""
    if not symbols:
        return 0
    if os.getenv("PROTOCOL_TRAIN_LSTM", "true").lower() not in ("1", "true", "yes"):
        return 0
    batch = _write_symbol_batch(symbols, "lstm")
    w = int(workers or os.getenv("LSTM_WORKERS", "3"))
    env = _base_env(
        {
            "USE_LSTM_HEAD": "true",
            "TRAIN_FORCE_YAHOO": "true",
            "LSTM_TRAIN_SCOPE": "all",
            "LSTM_WORKERS": str(w),
            "LSTM_REQUEUE_WEAK": "true",
            "LSTM_MIN_TEST_ACC": os.getenv("LSTM_MIN_TEST_ACC", "0.45"),
            "TRAIN_SYMBOLS_FILE": str(batch),
        }
    )
    # train_lstm_heads uses scope env; also pass symbol file via LSTM_SYMBOLS_FILE if supported
    return _run(
        [str(PY), "-u", "tools/train_lstm_heads.py"],
        env,
        f"lstm n={len(symbols)}",
    )


def run_top50_protocol(symbols: list[str]) -> dict[str, Any]:
    """Top-50% names (excluding pure top100 pass): daily + intraday + relaxed strong + LSTM."""
    sys.path.insert(0, str(ROOT))
    from fortress_universe import load_top100_symbols

    top_set = set(load_top100_symbols())
    syms = [s for s in symbols if s.upper() not in top_set]
    out: dict[str, Any] = {"tier": "top50pct", "symbols": syms}
    if not syms:
        return out
    out["daily_rc"] = train_tier_daily(syms, fresh=False)
    out["intraday_rc"] = train_tier_intraday(syms)
    from model_trainer import training_saved_model
    from tools.retrain_weak_models import find_weak_symbols

    have = [s for s in syms if training_saved_model(s)]
    weak = [s for s in have if s in find_weak_symbols(min_top20=0.50, min_meta=0.46, top100_only=False)]
    if weak:
        out["strong"] = strong_retrain_symbols(weak[: int(os.getenv("TOP50_STRONG_CAP", "40"))], min_top20=0.50, min_meta=0.46)
    out["lstm_rc"] = train_tier_lstm(have[: int(os.getenv("TOP50_LSTM_CAP", "200"))])
    return out


def run_new_listing_protocol(symbols: list[str]) -> dict[str, Any]:
    """New universe entrants — queue + daily train batch + LSTM after daily exists."""
    sys.path.insert(0, str(ROOT))
    from tools.listing_watch import queue_symbols, train_queued_if_idle

    added = queue_symbols(symbols)
    rc = train_queued_if_idle(max_symbols=int(os.getenv("NEW_LISTING_TRAIN_BATCH", "8"))) if added else 0
    from model_trainer import training_saved_model

    have = [s for s in symbols if training_saved_model(s)]
    lstm_rc = train_tier_lstm(have) if have else 0
    return {"tier": "new", "queued": added, "train_rc": rc, "lstm_rc": lstm_rc}


def run_corporate_protocol(symbols: list[str]) -> dict[str, Any]:
    """Post split/rename: force fresh daily + intraday + strong."""
    syms = list(dict.fromkeys(s.upper() for s in symbols if s))
    out: dict[str, Any] = {"tier": "corporate", "symbols": syms}
    if not syms:
        return out
    out["daily_rc"] = train_tier_daily(syms, fresh=True)
    out["intraday_rc"] = train_tier_intraday(syms)
    out["strong"] = strong_retrain_symbols(syms, min_top20=0.50, min_meta=0.46, attempts=6)
    return out
