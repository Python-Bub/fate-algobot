"""
Matrix engine — universe tick: laws → neurons fire → laws enforce → manifest.

Each tick is one pulse through the matrix. Neurons work; laws govern what reaches the world.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cortex.consciousness import load_self_model, save_self_model
from cortex.cortex_graph import ASSOC_IDS, CortexGraph, META_IDS, MOTOR_IDS, SENSORY_IDS, normalize_inputs
from cortex.universe_laws import enforce_laws, load_laws, log_enforcement

RUNTIME_PATH = Path(os.getenv("CORTEX_RUNTIME_PATH", "data/cortex/cortex_runtime.json"))
ACTIVITY_PATH = Path(os.getenv("CORTEX_MATRIX_ACTIVITY", "data/cortex/matrix_activity.jsonl"))
MANIFEST_PATH = Path(os.getenv("CORTEX_MATRIX_MANIFEST", "data/cortex/matrix_manifest.json"))
TICK_STATE_PATH = Path(os.getenv("CORTEX_TICK_STATE", "data/cortex/matrix_tick.json"))


def _motor_gain() -> float:
    return float(os.getenv("CORTEX_MOTOR_GAIN", "1.25"))


def _load_tick() -> int:
    if not TICK_STATE_PATH.is_file():
        return 0
    try:
        return int(json.loads(TICK_STATE_PATH.read_text(encoding="utf-8")).get("tick", 0))
    except Exception:
        return 0


def _save_tick(tick: int) -> None:
    TICK_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TICK_STATE_PATH.write_text(
        json.dumps({"tick": tick, "updated_utc": datetime.now(timezone.utc).isoformat()}, indent=2),
        encoding="utf-8",
    )


def matrix_tick(
    context: dict[str, Any] | None = None,
    *,
    learn: bool = False,
    reward: float | None = None,
) -> dict[str, Any]:
    """
    One universe pulse:
      1. Read written laws
      2. Neurons fire (forward pass)
      3. Laws enforce on motor outputs
      4. Write manifest + runtime for trading stack
    """
    if os.getenv("CORTEX_ENABLED", "true").lower() not in ("1", "true", "yes"):
        return {"ok": False, "reason": "disabled"}

    from cortex.rl_trader import compute_awareness, compute_rl_reward, decode_action, encode_spikes

    tick = _load_tick() + 1
    ctx = dict(context or {})
    graph = CortexGraph.load_or_seed()
    spike_inputs = encode_spikes(ctx)
    inputs = {**normalize_inputs(ctx), **spike_inputs}
    raw_motor = graph.forward(inputs)
    rl_reward = float(reward) if reward is not None else compute_rl_reward(ctx)

    gain = _motor_gain()
    scaled = {k: float(v) * gain for k, v in raw_motor.items() if k in ("buy_bias", "rank_tilt", "paper_boost", "hft_conf_delta")}
    scaled["size_mult"] = max(0.85, min(1.25, 1.0 + float(raw_motor.get("size_mult", 0.0)) * 0.15 * gain))

    lawful, law_events = enforce_laws(scaled, ctx)
    urge_bump = sum(e.get("applied", {}).get("self_improve_urge", 0) for e in law_events)

    if learn:
        graph.learn(rl_reward)
        graph.save()

    # Neuron firing snapshot (matrix rain — what's alive right now)
    firings = {
        "sensory": {nid: round(float(graph.neurons[nid].activation), 4) for nid in SENSORY_IDS if nid in graph.neurons},
        "association_top": _top_active(graph, ASSOC_IDS, n=5),
        "motor": {mid[2:]: round(float(graph.neurons[mid].activation), 4) for mid in MOTOR_IDS if mid in graph.neurons},
        "meta": {xid[2:]: round(float(graph.neurons[xid].activation), 4) for xid in META_IDS if xid in graph.neurons},
    }

    self_model = load_self_model()
    awareness = compute_awareness(firings)
    action = decode_action(lawful)
    self_model.update_from_meta(
        firings.get("meta") or {},
        rl_reward,
        ctx.get("alpha"),
        awareness=awareness,
    )
    if urge_bump:
        self_model.self_improve_urge = min(1.0, self_model.self_improve_urge + urge_bump)
    self_model.generation = graph.generation
    save_self_model(self_model)

    runtime = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "tick": tick,
        "generation": graph.generation,
        "laws_active": len(load_laws()),
        "laws_fired": [e["law_id"] for e in law_events],
        "awareness": round(awareness, 4),
        "rl_reward": round(rl_reward, 4),
        "rl_action": action,
        "buy_bias": lawful.get("buy_bias", 0.0),
        "rank_tilt": lawful.get("rank_tilt", 0.0),
        "paper_boost": lawful.get("paper_boost", 0.0),
        "hft_conf_delta": lawful.get("hft_conf_delta", 0.0),
        "size_mult": lawful.get("size_mult", 1.0),
        "firings": firings,
        "alpha": ctx.get("alpha"),
        "deployed_frac": ctx.get("deployed_frac"),
    }
    RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_PATH.write_text(json.dumps(runtime, indent=2), encoding="utf-8")

    manifest = {
        "matrix": "FATE_UNIVERSE",
        "tick": tick,
        "ts_utc": runtime["ts_utc"],
        "generation": graph.generation,
        "synapse_count": len(graph.synapses),
        "neuron_count": len(graph.neurons),
        "laws_written": len(load_laws()),
        "laws_enforced": law_events,
        "motor_lawful": {k: round(float(v), 6) for k, v in lawful.items()},
        "top_firings": firings,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log_enforcement(law_events, lawful, tick=tick)
    _log_activity(tick, lawful, law_events, ctx)
    _save_tick(tick)

    return {
        "ok": True,
        "tick": tick,
        "motor": lawful,
        "laws_fired": law_events,
        "firings": firings,
        "awareness": round(awareness, 4),
        "reward": round(rl_reward, 4),
        "rl_action": action,
        "manifest": str(MANIFEST_PATH),
    }


def _top_active(graph: CortexGraph, ids: tuple[str, ...], n: int = 5) -> dict[str, float]:
    ranked = sorted(
        ((nid, abs(float(graph.neurons[nid].activation))) for nid in ids if nid in graph.neurons),
        key=lambda x: -x[1],
    )
    return {nid: round(float(graph.neurons[nid].activation), 4) for nid, _ in ranked[:n]}


def _log_activity(tick: int, motor: dict, events: list, ctx: dict) -> None:
    ACTIVITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "tick": tick,
        "symbol": ctx.get("symbol"),
        "motor": {k: round(float(v), 6) for k, v in motor.items()},
        "laws": [e.get("law_id") for e in events],
        "alpha": ctx.get("alpha"),
    }
    with ACTIVITY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")


def collect_matrix_context() -> dict[str, Any]:
    """Pull live universe state for matrix ticks."""
    ctx: dict[str, Any] = {
        "deployed_frac": 0.0,
        "hit_rate": 0.5,
        "drawdown": 0.0,
        "paper_pnl": 0.0,
        "alpha": None,
        "losing_to_market": False,
        "neural_p_up": None,
    }
    root = Path(__file__).resolve().parents[1]
    reps = sorted((root / "reports").glob("paper_sim_*.json")) if (root / "reports").is_dir() else []
    if reps:
        try:
            doc = json.loads(reps[-1].read_text(encoding="utf-8"))
            ctx["paper_pnl"] = float(doc.get("sum_hypothetical_pnl_usd", 0.0))
            m = doc.get("asym_filter_metrics") or {}
            ctx["hit_rate"] = float(m.get("hit_rate", 0.5))
        except Exception:
            pass
    try:
        from alpaca_broker import get_account, list_positions, intraday_buying_power
        from self_modify.market_benchmark import beat_market_snapshot

        acct = get_account() or {}
        eq = float(acct.get("equity") or 0.0)
        pos = list_positions()
        mv = sum(abs(float(p.get("market_value") or 0)) for p in pos)
        if eq > 0:
            ctx["deployed_frac"] = mv / eq
        ctx.update(beat_market_snapshot(eq))
    except Exception:
        pass
    return ctx
