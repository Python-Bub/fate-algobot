"""
Recursive self-improvement cycle — RL neurons sense, act, learn, mutate, evolve code.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cortex.consciousness import EpisodicMemory, load_self_model, save_self_model
from cortex.cortex_graph import CortexGraph
from cortex.matrix_engine import matrix_tick
from cortex.rl_trader import compute_rl_reward

LOG_PATH = Path(os.getenv("CORTEX_SINGULARITY_LOG", "data/cortex/singularity_log.jsonl"))


def _collect_signals() -> dict[str, Any]:
    sig: dict[str, Any] = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "deployed_frac": 0.0,
        "hit_rate": 0.5,
        "drawdown": 0.0,
        "paper_pnl": 0.0,
        "alpha": None,
        "neural_p_up": None,
        "hft_pulse": 0.5,
    }
    root = Path(__file__).resolve().parents[1]
    rep_dir = root / "reports"
    if rep_dir.is_dir():
        reps = sorted(rep_dir.glob("paper_sim_*.json"))
        if reps:
            try:
                doc = json.loads(reps[-1].read_text(encoding="utf-8"))
                sig["paper_pnl"] = float(doc.get("sum_hypothetical_pnl_usd", 0.0))
                m = doc.get("asym_filter_metrics") or {}
                sig["hit_rate"] = float(m.get("hit_rate", sig["hit_rate"]))
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
            sig["deployed_frac"] = mv / eq
        sig["equity"] = eq
        sig["buying_power"] = float(intraday_buying_power(acct))
        sig.update(beat_market_snapshot(eq))
    except Exception:
        pass
    return sig


def singularity_step(*, force_evolve: bool = False) -> dict[str, Any]:
    if os.getenv("CORTEX_ENABLED", "true").lower() not in ("1", "true", "yes"):
        return {"ok": False, "reason": "disabled"}

    self_model = load_self_model()
    memory = EpisodicMemory()
    memory.load()

    try:
        from self_modify.objective_engine import enrich_signals, primary_objective

        sig = enrich_signals(_collect_signals())
        self_model.primary_objective = primary_objective()
    except Exception:
        sig = _collect_signals()

    reward = compute_rl_reward(sig, goal_deploy=self_model.goal_deploy)

    tick_out = matrix_tick(sig, learn=True, reward=reward)
    motor = tick_out.get("motor") or {}
    awareness = float(tick_out.get("awareness", 0.0))
    action = tick_out.get("rl_action", "HOLD")

    graph = CortexGraph.load_or_seed()
    exploration = self_model.exploration_drive
    mutate_events = graph.mutate(exploration=exploration)
    self_model.singularity_depth += 1
    self_model.generation = graph.generation
    graph.save()

    episode = {
        "reward": reward,
        "alpha": sig.get("alpha"),
        "action": action,
        "awareness": awareness,
        "motor": {k: round(float(v), 4) for k, v in motor.items()},
        "meta": tick_out.get("firings", {}).get("meta"),
        "mutations": mutate_events,
    }
    memory.append(episode)
    memory.save()
    save_self_model(self_model)

    evolve_result = None
    agi_result = None
    if force_evolve or self_model.should_trigger_code_evolve():
        try:
            from self_modify.code_evolver import evolve_once

            evolve_result = evolve_once(force=force_evolve)
            if evolve_result.get("ok"):
                self_model.self_improve_urge = max(0.2, self_model.self_improve_urge - 0.15)
                save_self_model(self_model)
        except Exception as e:
            evolve_result = {"ok": False, "reason": str(e)[:200]}

    if os.getenv("AGI_AGENT_ENABLED", "true").lower() in ("1", "true", "yes"):
        try:
            from self_modify.agi_agent import agi_step

            agi_result = agi_step(force=force_evolve)
            if agi_result.get("ok"):
                self_model.self_improve_urge = max(0.15, self_model.self_improve_urge - 0.10)
                save_self_model(self_model)
        except Exception as e:
            agi_result = {"ok": False, "reason": str(e)[:200]}

    free_result = None
    if os.getenv("FREE_AGENT_ENABLED", "true").lower() in ("1", "true", "yes"):
        try:
            from self_modify.free_agent import free_agent_step

            free_result = free_agent_step(force=force_evolve)
        except Exception as e:
            free_result = {"ok": False, "reason": str(e)[:200]}

    _log(
        "singularity_step",
        {
            "generation": graph.generation,
            "reward": reward,
            "awareness": awareness,
            "action": action,
            "mutations": mutate_events,
            "evolved": bool(evolve_result and evolve_result.get("ok")),
            "agi": bool(agi_result and agi_result.get("ok")),
            "free_agent": bool(free_result and free_result.get("ok")),
            "equity": sig.get("equity"),
            "equity_delta": sig.get("equity_delta"),
            "objective": sig.get("objective"),
        },
    )

    return {
        "ok": True,
        "generation": graph.generation,
        "singularity_depth": self_model.singularity_depth,
        "awareness": round(awareness, 4),
        "self_improve_urge": round(self_model.self_improve_urge, 4),
        "reward": round(reward, 4),
        "rl_action": action,
        "motor": motor,
        "mutations": mutate_events,
        "code_evolve": evolve_result,
        "agi_agent": agi_result,
        "free_agent": free_result,
        "objective": sig.get("objective"),
        "equity": sig.get("equity"),
        "equity_delta": sig.get("equity_delta"),
    }


def _log(event: str, payload: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts_utc": datetime.now(timezone.utc).isoformat(), "event": event, **payload}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")
