"""Honest completeness — file existence is not a finished model.

`phase=done` used to mean the enhancement queue exited its list. This module
answers: are daily heads, LSTM, and intraday actually present and non-null?
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _min_daily_bytes() -> int:
    return int(os.getenv("TRAINED_MODEL_MIN_BYTES", "1000"))


def daily_heads_present(ticker: str) -> dict[str, Any]:
    """Inspect one daily pickle without treating size as quality."""
    p = ROOT / "models" / f"{ticker.strip().upper()}_model.pkl"
    out: dict[str, Any] = {
        "ticker": ticker.strip().upper(),
        "path": str(p),
        "exists": False,
        "complete": False,
        "missing_heads": [],
        "bytes": 0,
    }
    try:
        if not p.is_file():
            out["missing_heads"] = ["file"]
            return out
        out["bytes"] = int(p.stat().st_size)
        out["exists"] = out["bytes"] >= _min_daily_bytes()
    except OSError:
        out["missing_heads"] = ["file"]
        return out
    try:
        import joblib

        b = joblib.load(p)
    except Exception as e:
        out["missing_heads"] = [f"load:{type(e).__name__}"]
        return out
    need = ("model_short", "model_long", "model_daily", "model_xlong", "model_meta")
    missing = [h for h in need if b.get(h) is None]
    out["missing_heads"] = missing
    out["complete"] = out["exists"] and not missing
    stats = b.get("stats") or b.get("head_quality") or {}
    if isinstance(stats, dict):
        out["weak"] = bool(stats.get("weak_head") or stats.get("weak"))
    return out


def queue_reopen_phase() -> str | None:
    """Which enhancement phase to re-enter, or None if gaps are within tolerance."""
    try:
        from fortress_universe import load_top100_symbols
        from model_trainer import training_saved_model

        top = [s.upper() for s in (load_top100_symbols() or [])]
        top_miss = sum(1 for s in top if not training_saved_model(s))
    except Exception:
        top = []
        top_miss = 0

    if top_miss > 0:
        return "top100_perfect"

    try:
        pri = ROOT / "data" / "priority_force_train.txt"
        if pri.is_file():
            names = [
                ln.strip().upper()
                for ln in pri.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.strip().startswith("#")
            ]
            from model_trainer import training_saved_model

            if any(not training_saved_model(s) for s in names):
                return "daily_junk"
    except Exception:
        pass

    old_scope = os.environ.get("LSTM_TRAIN_SCOPE")
    os.environ["LSTM_TRAIN_SCOPE"] = "all"
    try:
        from tools.train_lstm_heads import _pending_symbols

        if _pending_symbols():
            return "lstm_all"
    except Exception:
        pass
    finally:
        if old_scope is None:
            os.environ.pop("LSTM_TRAIN_SCOPE", None)
        else:
            os.environ["LSTM_TRAIN_SCOPE"] = old_scope

    try:
        from fortress_universe import has_trained_intraday_bundle, load_top100_symbols

        intra_miss = sum(1 for s in load_top100_symbols() if not has_trained_intraday_bundle(s))
        if intra_miss > 0:
            return "intraday_proper_gap"
    except Exception:
        pass

    # Null heads on megas: fill via top100 path (does not delete existing pickles).
    probe = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "GLD", "SLV", "USO"]
    for s in probe:
        try:
            info = daily_heads_present(s)
            if info.get("exists") and info.get("missing_heads"):
                return "top100_perfect"
        except Exception:
            continue
    return None


def completeness_snapshot() -> dict[str, Any]:
    phase = queue_reopen_phase()
    return {
        "reopen_phase": phase,
        "is_complete": phase is None,
    }
