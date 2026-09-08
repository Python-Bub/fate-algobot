"""Trading-stack hooks — matrix tick → lawful motor outputs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cortex.matrix_engine import RUNTIME_PATH, collect_matrix_context, matrix_tick

ACTIVITY_PATH = Path(os.getenv("CORTEX_MATRIX_ACTIVITY", "data/cortex/matrix_activity.jsonl"))


def cortex_enabled() -> bool:
    return os.getenv("CORTEX_ENABLED", "true").lower() in ("1", "true", "yes")


def _load_runtime() -> dict[str, Any]:
    if not RUNTIME_PATH.is_file():
        return {}
    try:
        return json.loads(RUNTIME_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _live_tick(context: dict[str, Any] | None) -> dict[str, float]:
    ctx = collect_matrix_context()
    if context:
        ctx.update(context)
    out = matrix_tick(ctx, learn=False)
    if not out.get("ok"):
        return {}
    motor = out.get("motor") or {}
    return {
        "buy_bias": float(motor.get("buy_bias", 0.0)),
        "rank_tilt": float(motor.get("rank_tilt", 0.0)),
        "paper_boost": float(motor.get("paper_boost", 0.0)),
        "hft_conf_delta": float(motor.get("hft_conf_delta", 0.0)),
        "size_mult": float(motor.get("size_mult", 1.0)),
        "tick": int(out.get("tick", 0)),
        "laws": [e.get("law_id") for e in (out.get("laws_fired") or [])],
    }


def cortex_decision(context: dict[str, Any] | None = None) -> dict[str, float]:
    if not cortex_enabled():
        return {}
    # Live matrix tick fetches Polygon benchmarks — can stall fortress for minutes.
    # Default: use cached motors from cortex-singularity unless explicitly forced live.
    live = os.getenv("CORTEX_LIVE_FORWARD", "true").lower() in ("1", "true", "yes")
    if os.getenv("FORTRESS_LITE_INTEL", "false").lower() in ("1", "true", "yes"):
        live = False
    if os.getenv("CORTEX_LIVE_IN_FORTRESS", "").lower() in ("0", "false", "no"):
        live = False
    if live:
        try:
            return _live_tick(context)
        except Exception:
            pass
    rt = _load_runtime()
    return {
        "buy_bias": float(rt.get("buy_bias", 0.0)),
        "rank_tilt": float(rt.get("rank_tilt", 0.0)),
        "paper_boost": float(rt.get("paper_boost", 0.0)),
        "hft_conf_delta": float(rt.get("hft_conf_delta", 0.0)),
        "size_mult": float(rt.get("size_mult", 1.0)),
        "tick": int(rt.get("tick", 0)),
        "laws": list(rt.get("laws_fired") or []),
    }


def cortex_rank_tilt(symbol: str, p_up: float, metrics: dict) -> float:
    ctx = dict(metrics or {})
    ctx["symbol"] = symbol
    ctx["neural_p_up"] = ctx.get("neural_p_up", p_up)
    d = cortex_decision(ctx)
    return float(d.get("rank_tilt", 0.0))


def cortex_paper_boost(symbol: str, score: float, metrics: dict) -> float:
    ctx = dict(metrics or {})
    ctx["symbol"] = symbol
    d = cortex_decision(ctx)
    return float(d.get("paper_boost", 0.0))


def cortex_buy_bias(symbol: str, metrics: dict | None = None) -> float:
    ctx = dict(metrics or {})
    ctx["symbol"] = symbol
    d = cortex_decision(ctx)
    return float(d.get("buy_bias", 0.0))


def cortex_hft_conf_delta(metrics: dict | None = None) -> float:
    d = cortex_decision(metrics)
    return float(d.get("hft_conf_delta", 0.0))


def cortex_size_mult(metrics: dict | None = None) -> float:
    d = cortex_decision(metrics)
    return float(d.get("size_mult", 1.0))
