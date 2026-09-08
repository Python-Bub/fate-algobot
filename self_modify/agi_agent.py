"""
AGI-style autonomous agent — observe, plan, act toward primary objective.

Primary objective (default): "Make portfolio account larger"

Actions (guarded):
  - evolve strategy overlay (code_evolver)
  - evolve custom hooks (code_editor)
  - tune runtime policy params (policy_agent)
  - restart safe trainers / stack health (allowlisted shell commands)
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from self_modify.audit_trail import log_audit
from self_modify.objective_engine import (
    enrich_signals,
    primary_objective,
    should_aggress_self_modify,
)

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = Path(os.getenv("AGI_AGENT_STATE_PATH", "data/self_improve/agi_agent_state.json"))
LOG_PATH = Path(os.getenv("AGI_AGENT_LOG", "data/self_improve/agi_agent_log.jsonl"))

# Safe stack commands the agent may invoke (no stop/pause/prune).
ALLOWED_STACK_COMMANDS = frozenset(
    {
        "ensure-stack",
        "ensure-training",
        "train-lstm",
        "train-gaps",
        "ensure-execution-monitor",
    }
)


def _log(event: str, payload: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts_utc": datetime.now(timezone.utc).isoformat(), "event": event, **payload}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"generation": 0, "recipe_idx": 0, "last_run_ts": 0.0}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"generation": 0, "recipe_idx": 0, "last_run_ts": 0.0}


def _save_state(st: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")


def _collect_base_signals() -> dict[str, Any]:
    try:
        from self_modify.code_evolver import collect_signals

        return collect_signals()
    except Exception:
        return {}


def observe() -> dict[str, Any]:
    sig = enrich_signals(_collect_base_signals())
    sig["primary_objective"] = primary_objective()
    return sig


def _run_stack_command(cmd: str) -> dict[str, Any]:
    if cmd not in ALLOWED_STACK_COMMANDS:
        return {"ok": False, "reason": f"command_blocked:{cmd}"}
    script = ROOT / "run_all.sh"
    if not script.is_file():
        return {"ok": False, "reason": "missing_run_all"}
    try:
        r = subprocess.run(
            [str(script), cmd],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
        )
        tail = ((r.stdout or "") + (r.stderr or ""))[-500:]
        return {"ok": r.returncode == 0, "cmd": cmd, "detail": tail}
    except Exception as e:
        return {"ok": False, "cmd": cmd, "reason": str(e)[:200]}


def _plan_actions(ctx: dict[str, Any], st: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    aggressive = should_aggress_self_modify(ctx)
    equity_delta = float(ctx.get("equity_delta") or 0.0)
    deployed = float(ctx.get("deployed_frac") or 0.0)

    if aggressive:
        actions.extend(["evolve_hooks", "evolve_overlay", "tune_policy"])
    else:
        actions.append("tune_policy")

    if equity_delta <= 0 and deployed < float(os.getenv("FORTRESS_TARGET_DEPLOY_FRAC", "0.88")):
        actions.append("ensure_training")

    if aggressive and int(st.get("generation", 0)) % 5 == 0:
        actions.append("ensure_stack")

    # Deduplicate preserving order
    seen: set[str] = set()
    out: list[str] = []
    for a in actions:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


def _execute_action(action: str, ctx: dict[str, Any], st: dict[str, Any]) -> dict[str, Any]:
    gen = int(st.get("generation", 0)) + 1
    recipe_idx = int(st.get("recipe_idx", 0))

    if action == "evolve_overlay":
        from self_modify.code_evolver import evolve_once

        force = should_aggress_self_modify(ctx)
        return {"action": action, **evolve_once(force=force)}

    if action == "evolve_hooks":
        from self_modify.code_editor import evolve_custom_hooks

        return {"action": action, **evolve_custom_hooks(ctx, generation=gen, recipe_idx=recipe_idx)}

    if action == "tune_policy":
        from self_modify.policy_agent import GuardedPolicyAgent, get_runtime_param

        agent = GuardedPolicyAgent()
        metrics = dict(ctx)
        metrics["cur_buy"] = float(get_runtime_param("BUY_THRESHOLD", 0.55))
        metrics["cur_notional"] = float(get_runtime_param("ORDER_NOTIONAL", 5000))
        try:
            from self_modify.custom_hooks import policy_priority_hints

            hints = policy_priority_hints(metrics)
            if hints:
                return {"action": action, **agent.apply_if_valid(hints, metrics)}
        except Exception:
            pass
        return {"action": action, **agent.observe_and_maybe_adapt(metrics)}

    if action == "ensure_training":
        return {"action": action, **_run_stack_command("ensure-training")}

    if action == "ensure_stack":
        return {"action": action, **_run_stack_command("ensure-stack")}

    return {"action": action, "ok": False, "reason": "unknown_action"}


def agi_step(*, force: bool = False) -> dict[str, Any]:
    if os.getenv("AGI_AGENT_ENABLED", "true").lower() not in ("1", "true", "yes"):
        return {"ok": False, "reason": "disabled"}

    if os.getenv("AGI_HUMAN_LOCK", "false").lower() in ("1", "true", "yes"):
        return {"ok": False, "reason": "human_lock"}

    st = _load_state()
    now = datetime.now(timezone.utc).timestamp()
    min_sec = int(os.getenv("AGI_MIN_INTERVAL_SEC", "90"))
    if not force and now - float(st.get("last_run_ts") or 0.0) < min_sec:
        return {"ok": False, "reason": "interval", "wait_sec": int(min_sec - (now - float(st.get("last_run_ts") or 0)))}

    ctx = observe()
    actions = _plan_actions(ctx, st)
    results: list[dict[str, Any]] = []
    any_ok = False

    for action in actions:
        try:
            res = _execute_action(action, ctx, st)
            results.append(res)
            if res.get("ok") or res.get("applied"):
                any_ok = True
                # One successful mutation per cycle — avoid stacking slow test suites.
                if action in ("evolve_hooks", "evolve_overlay", "tune_policy"):
                    break
        except Exception as e:
            results.append({"action": action, "ok": False, "reason": str(e)[:200]})

    st["generation"] = int(st.get("generation", 0)) + 1
    st["recipe_idx"] = (int(st.get("recipe_idx", 0)) + 1) % 8
    st["last_run_ts"] = now
    st["last_run_utc"] = datetime.now(timezone.utc).isoformat()
    st["last_objective"] = ctx.get("objective")
    st["last_equity"] = ctx.get("equity")
    st["last_equity_delta"] = ctx.get("equity_delta")
    _save_state(st)

    payload = {
        "ok": any_ok,
        "objective": ctx.get("objective"),
        "equity": ctx.get("equity"),
        "equity_delta": ctx.get("equity_delta"),
        "objective_reward": ctx.get("objective_reward"),
        "actions_planned": actions,
        "results": results,
        "generation": st["generation"],
    }
    log_audit("agi_step", payload)
    _log("agi_step", payload)
    return payload


def main() -> int:
    import sys

    force = "--force" in sys.argv
    out = agi_step(force=force)
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
