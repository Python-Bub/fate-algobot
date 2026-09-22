"""
Matrix universe laws — foundational rules neurons must obey.

Laws are written to data/cortex/universe_laws.json (the 'source').
Neurons propose motor outputs; laws clip, boost, or override them.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LAWS_PATH = Path(os.getenv("CORTEX_UNIVERSE_LAWS_PATH", "data/cortex/universe_laws.json"))
ENFORCE_LOG = Path(os.getenv("CORTEX_LAW_LOG", "data/cortex/law_enforcement.jsonl"))


def _eval_when(expr: str, ctx: dict[str, Any]) -> bool:
    """Safe-ish eval of simple comparison expressions against context."""
    if not expr or expr == "always":
        return True
    env: dict[str, Any] = {}
    for k, v in ctx.items():
        if isinstance(v, (int, float, bool)) or v is None:
            env[k] = v
        elif isinstance(v, str):
            try:
                env[k] = float(v)
            except ValueError:
                env[k] = v
    # booleans from strings
    for k in ("losing_to_market", "beating_market"):
        if k in ctx:
            env[k] = bool(ctx[k])
    try:
        # Only allow comparisons on known keys — no calls/imports
        allowed = set(env.keys()) | {"True", "False", "true", "false"}
        tokens = expr.replace("(", " ").replace(")", " ").split()
        if any(t not in allowed and t not in ("<", ">", "<=", ">=", "==", "!=", "and", "or", "not") for t in tokens if not t.replace(".", "").replace("-", "").isdigit()):
            # fallback: simple key op val
            pass
        return bool(eval(expr, {"__builtins__": {}}, env))  # noqa: S307 — gated expr from our JSON
    except Exception:
        return False


DEFAULT_LAWS: list[dict[str, Any]] = [
    {
        "id": "underdeployed_buy",
        "name": "Buy when idle cash is high",
        "axiom": "never sit in cash when alpha is available",
        "priority": 10,
        "when": "deployed_frac < 0.55",
        "motor": {"buy_bias": 0.06, "paper_boost": 0.04, "size_mult": 1.08},
    },
    {
        "id": "losing_to_market_tilt",
        "name": "Tilt rank when lagging the tape",
        "axiom": "catch up without panic",
        "priority": 20,
        "when": "losing_to_market",
        "motor": {"buy_bias": 0.04, "rank_tilt": 0.03},
    },
]


def load_laws() -> list[dict[str, Any]]:
    if not LAWS_PATH.is_file():
        return list(DEFAULT_LAWS)
    try:
        doc = json.loads(LAWS_PATH.read_text(encoding="utf-8"))
        laws = sorted(doc.get("laws") or [], key=lambda x: int(x.get("priority", 99)))
        return laws or list(DEFAULT_LAWS)
    except Exception:
        return list(DEFAULT_LAWS)


def enforce_laws(
    motor: dict[str, float],
    context: dict[str, Any],
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """
    Apply universe laws to raw neuron motor outputs.
    Returns (lawful motor, list of enforcement events).
    """
    ctx = dict(context or {})
    alpha = ctx.get("alpha")
    if alpha is not None:
        ctx.setdefault("losing_to_market", float(alpha) < 0)
    out = {k: float(v) for k, v in motor.items()}
    events: list[dict[str, Any]] = []
    gain = float(os.getenv("CORTEX_LAW_GAIN", "1.0"))

    for law in load_laws():
        when = str(law.get("when", ""))
        if not _eval_when(when, ctx):
            continue
        deltas = law.get("motor") or {}
        applied: dict[str, float] = {}
        for key, delta in deltas.items():
            if key == "self_improve_urge":
                applied[key] = float(delta) * gain
                continue
            if key == "size_mult":
                out[key] = float(out.get(key, 1.0)) * (1.0 + (float(delta) - 1.0) * gain)
            else:
                out[key] = float(out.get(key, 0.0)) + float(delta) * gain
            applied[key] = round(float(out.get(key, applied.get(key, 0))), 6)
        events.append(
            {
                "law_id": law.get("id"),
                "law_name": law.get("name"),
                "axiom": law.get("axiom"),
                "when": when,
                "applied": applied,
            }
        )

    # Constitutional floors — laws override timid neurons when universe demands action
    deployed = float(ctx.get("deployed_frac", 1.0) or 0.0)
    if deployed < 0.55:
        out["buy_bias"] = max(float(out.get("buy_bias", 0.0)), 0.05 * gain)
        out["paper_boost"] = max(float(out.get("paper_boost", 0.0)), 0.04 * gain)
        out["hft_conf_delta"] = min(float(out.get("hft_conf_delta", 0.0)), -0.02 * gain)
        out["size_mult"] = max(float(out.get("size_mult", 1.0)), 1.06)
    alpha = ctx.get("alpha")
    if alpha is not None and float(alpha) < 0:
        out["buy_bias"] = max(float(out.get("buy_bias", 0.0)), 0.03 * gain)
        out["rank_tilt"] = max(float(out.get("rank_tilt", 0.0)), 0.02 * gain)

    # Hard clamps — physics of this universe
    out["buy_bias"] = max(-0.15, min(0.15, float(out.get("buy_bias", 0.0))))
    out["rank_tilt"] = max(-0.15, min(0.15, float(out.get("rank_tilt", 0.0))))
    out["paper_boost"] = max(-0.20, min(0.20, float(out.get("paper_boost", 0.0))))
    out["hft_conf_delta"] = max(-0.10, min(0.10, float(out.get("hft_conf_delta", 0.0))))
    out["size_mult"] = max(0.75, min(1.35, float(out.get("size_mult", 1.0))))
    return out, events


def log_enforcement(events: list[dict], motor: dict[str, float], *, tick: int = 0) -> None:
    if not events:
        return
    ENFORCE_LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "tick": tick,
        "motor": {k: round(float(v), 6) for k, v in motor.items()},
        "laws_fired": events,
    }
    with ENFORCE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")
