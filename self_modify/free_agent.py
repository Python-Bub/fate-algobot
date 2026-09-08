"""
Free agent — reads user prompts, consults online LLM, executes autonomous actions.

Objective: Make portfolio account larger.

Runs continuously via tools/free_agent_loop.py (wired into cortex singularity).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from self_modify.audit_trail import log_audit
from self_modify.objective_engine import enrich_signals, primary_objective
from self_modify.prompt_inbox import (
    combined_prompt_text,
    mark_processed,
    read_pending_prompts,
    write_outbox_response,
)

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = Path(os.getenv("FREE_AGENT_STATE", "data/agi/free_agent_state.json"))
LOG_PATH = Path(os.getenv("FREE_AGENT_LOG", "data/agi/free_agent_log.jsonl"))

# Expanded autonomous action set (still allowlisted — no pause/stop/prune).
FREE_ACTIONS = frozenset(
    {
        "read_prompt",
        "llm_plan",
        "evolve_hooks",
        "evolve_hooks_llm",
        "evolve_overlay",
        "tune_policy",
        "train_lstm",
        "train_gaps",
        "train_100gb",
        "train_neural",
        "retrain_weak",
        "self_improve",
        "ensure_training",
        "ensure_stack",
        "evolve_gainz",
    }
)


def _log(event: str, payload: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts_utc": datetime.now(timezone.utc).isoformat(), "event": event, **payload}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"generation": 0, "last_run_ts": 0.0}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"generation": 0, "last_run_ts": 0.0}


def _save_state(st: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")


def _collect_context() -> dict[str, Any]:
    try:
        from self_modify.code_evolver import collect_signals

        base = collect_signals()
    except Exception:
        base = {}
    return enrich_signals(base)


_LLM_COOLDOWN_PATH = Path(os.getenv("FREE_AGENT_LLM_COOLDOWN_FILE", "data/agi/llm_cooldown.ts"))


def _llm_in_cooldown() -> bool:
    """After a 429/rate-limit, stop hammering the API for a cooldown window."""
    try:
        from intel.llm_cooldown import active

        return active()
    except Exception:
        pass
    try:
        until = float(_LLM_COOLDOWN_PATH.read_text(encoding="utf-8").strip())
        return datetime.now(timezone.utc).timestamp() < until
    except Exception:
        return False


def _set_llm_cooldown() -> None:
    try:
        from intel.llm_cooldown import trip

        trip(float(os.getenv("FREE_AGENT_LLM_COOLDOWN_SEC", "900")), reason="free_agent_429")
        return
    except Exception:
        pass
    secs = int(os.getenv("FREE_AGENT_LLM_COOLDOWN_SEC", "900"))
    try:
        _LLM_COOLDOWN_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LLM_COOLDOWN_PATH.write_text(
            str(datetime.now(timezone.utc).timestamp() + secs), encoding="utf-8"
        )
    except Exception:
        pass


def _llm_plan(ctx: dict[str, Any], prompts: list[dict[str, Any]]) -> dict[str, Any] | None:
    if os.getenv("FREE_AGENT_USE_LLM", "true").lower() not in ("1", "true", "yes"):
        return None
    if _llm_in_cooldown():
        return None
    try:
        from intel.llm_signal_agent import _extract_json, _post_chat
        from intel.api_budget import llm_allowed

        if not llm_allowed():
            return None
    except Exception:
        return None

    prompt_text = combined_prompt_text(prompts)
    system = (
        "You are the autonomous trading AGI for FATE_AlgoBot. "
        f"PRIMARY OBJECTIVE: {primary_objective()}. "
        "You may choose multiple actions each cycle to grow portfolio equity.\n"
        "Return strict JSON only:\n"
        "{\n"
        '  "rationale": "short why",\n'
        '  "user_reply": "1-3 sentences acknowledging user prompt",\n'
        '  "actions": ["train_lstm","evolve_hooks_llm","tune_policy", ...],\n'
        '  "hooks_proposal": {\n'
        '    "rationale": "...",\n'
        '    "equity_rules": ["python lines"],\n'
        '    "size_rules": ["python lines"],\n'
        '    "policy_lines": ["python lines"]\n'
        "  }\n"
        "}\n"
        f"Allowed actions: {sorted(FREE_ACTIONS)}\n"
        "Prefer training + code evolution when equity_delta <= 0. "
        "No imports, no I/O in hooks_proposal lines."
    )
    user = json.dumps(
        {
            "metrics": {
                k: ctx.get(k)
                for k in (
                    "equity",
                    "equity_delta",
                    "equity_growth_pct",
                    "deployed_frac",
                    "alpha",
                    "hit_rate",
                    "n_positions",
                    "buying_power",
                )
            },
            "user_prompts": prompt_text[:12000],
        },
        indent=2,
    )[:14000]
    try:
        raw = _post_chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        )
        obj = _extract_json(raw)
        actions = [str(a) for a in (obj.get("actions") or []) if str(a) in FREE_ACTIONS]
        if not _heavy_train_allowed():
            heavy = {"train_lstm", "train_gaps", "train_100gb", "train_neural", "retrain_weak"}
            actions = [a for a in actions if a not in heavy]
        if not actions:
            actions = ["tune_policy", "evolve_hooks"]
        return {
            "rationale": str(obj.get("rationale", "llm_plan"))[:400],
            "user_reply": str(obj.get("user_reply", ""))[:800],
            "actions": actions[:8],
            "hooks_proposal": obj.get("hooks_proposal") or {},
        }
    except Exception as e:
        msg = str(e)[:200]
        if "429" in msg or "Too Many Requests" in msg or "rate" in msg.lower():
            _set_llm_cooldown()
        _log("llm_plan_failed", {"error": msg})
        return None


def _heavy_train_allowed() -> bool:
    """The stack watchdog already keeps train-lstm/intraday alive. The free agent
    must NOT spawn duplicate heavy trainers by default — on a memory-constrained
    host that doubles RAM use and gets the whole agent group jetsam-killed."""
    if os.getenv("FREE_AGENT_ALLOW_HEAVY_TRAIN", "false").lower() not in ("1", "true", "yes"):
        return False
    try:
        from self_modify.online_trainer import memory_guard

        return bool(memory_guard()["ok"])
    except Exception:
        return False


def _default_plan(ctx: dict[str, Any]) -> dict[str, Any]:
    delta = float(ctx.get("equity_delta") or 0.0)
    # Core, lightweight, high-value loop: read prompts, evolve code, tune policy.
    actions = ["read_prompt", "evolve_hooks", "evolve_overlay", "evolve_gainz", "tune_policy"]
    if delta <= 0:
        actions = ["read_prompt", "evolve_hooks", "evolve_overlay", "evolve_hooks_llm", "tune_policy"]
    if _heavy_train_allowed():
        actions += ["train_lstm", "train_gaps"]
    return {"rationale": "rule_plan", "user_reply": "", "actions": actions, "hooks_proposal": {}}


def _execute(action: str, ctx: dict[str, Any], plan: dict[str, Any], st: dict[str, Any]) -> dict[str, Any]:
    gen = int(st.get("generation", 0)) + 1
    recipe_idx = int(st.get("recipe_idx", 0))

    if action == "read_prompt":
        prompts = read_pending_prompts()
        new_paths = [p["path"] for p in prompts if not p.get("persistent")]
        if new_paths:
            mark_processed(new_paths)
        return {"action": action, "ok": True, "count": len(prompts)}

    if action in ("train_lstm", "train_gaps", "train_100gb", "train_neural", "retrain_weak", "self_improve"):
        from self_modify.online_trainer import execute_train_action

        return execute_train_action(action)

    if action == "evolve_overlay":
        from self_modify.code_evolver import evolve_once

        return {"action": action, **evolve_once(force=True)}

    if action == "evolve_gainz":
        from self_modify.gainz_evolver import evolve_once as gainz_evolve

        return {"action": action, **gainz_evolve()}

    if action == "evolve_hooks":
        from self_modify.code_editor import evolve_custom_hooks

        return {"action": action, **evolve_custom_hooks(ctx, generation=gen, recipe_idx=recipe_idx)}

    if action == "evolve_hooks_llm":
        from self_modify.code_editor import propose_hooks_edit, render_hooks_proposal, write_allowlisted_file
        from self_modify.objective_engine import primary_objective

        proposal = plan.get("hooks_proposal") or {}
        if not proposal.get("equity_rules"):
            proposal = propose_hooks_edit(ctx, recipe_idx=recipe_idx)
        source = render_hooks_proposal(proposal, gen, primary_objective())
        return {
            "action": action,
            **write_allowlisted_file("self_modify/custom_hooks.py", source, tag=f"llm_hooks_g{gen}"),
        }

    if action == "tune_policy":
        from self_modify.agi_agent import _execute_action as agi_exec

        return agi_exec("tune_policy", ctx, st)

    if action == "ensure_training":
        from self_modify.agi_agent import _run_stack_command

        return {"action": action, **_run_stack_command("ensure-training")}

    if action == "ensure_stack":
        from self_modify.agi_agent import _run_stack_command

        return {"action": action, **_run_stack_command("ensure-stack")}

    return {"action": action, "ok": False, "reason": "unknown"}


_LOCK_PATH = Path(os.getenv("FREE_AGENT_LOCK", "data/agi/free_agent.lock"))


def free_agent_step(*, force: bool = False) -> dict[str, Any]:
    """Single guarded step. Held behind a non-blocking single-instance lock so the
    standalone daemon and any in-process callers (e.g. cortex singularity) can never
    run two steps concurrently and deadlock on shared files / evolution subprocesses."""
    if os.getenv("FREE_AGENT_ENABLED", "true").lower() not in ("1", "true", "yes"):
        return {"ok": False, "reason": "disabled"}

    import fcntl

    _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(str(_LOCK_PATH), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return {"ok": False, "reason": "busy"}
        return _free_agent_step_locked(force=force)
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except Exception:
            pass
        os.close(lock_fd)


def _free_agent_step_locked(*, force: bool = False) -> dict[str, Any]:
    st = _load_state()
    now = datetime.now(timezone.utc).timestamp()
    min_sec = int(os.getenv("FREE_AGENT_MIN_INTERVAL_SEC", "30"))
    if not force and now - float(st.get("last_run_ts") or 0.0) < min_sec:
        return {"ok": False, "reason": "interval", "wait_sec": int(min_sec - (now - float(st.get("last_run_ts") or 0)))}

    ctx = _collect_context()
    prompts = read_pending_prompts()
    plan = _llm_plan(ctx, prompts) or _default_plan(ctx)
    actions = list(plan.get("actions") or [])
    if "read_prompt" not in actions:
        actions.insert(0, "read_prompt")

    results: list[dict[str, Any]] = []
    any_ok = False
    max_actions = int(os.getenv("FREE_AGENT_MAX_ACTIONS_PER_STEP", "4"))

    for action in actions[:max_actions]:
        if action not in FREE_ACTIONS:
            continue
        try:
            res = _execute(action, ctx, plan, st)
            results.append(res)
            if res.get("ok") or res.get("applied"):
                any_ok = True
        except Exception as e:
            results.append({"action": action, "ok": False, "reason": str(e)[:200]})

    new_prompts = [p for p in prompts if not p.get("persistent")]
    reply = str(plan.get("user_reply") or "").strip()
    if reply:
        write_outbox_response(
            f"# Agent reply (gen {st.get('generation', 0)})\n\n{reply}\n\n"
            f"**Rationale:** {plan.get('rationale', '')}\n",
            tag="reply",
        )
    elif new_prompts:
        # LLM unavailable (e.g. API 429) but the user sent a prompt — acknowledge it
        # with the concrete actions taken this cycle so the prompt→reply loop still works.
        done = ", ".join(str(r.get("action")) for r in results if r.get("ok") or r.get("applied"))
        write_outbox_response(
            f"# Agent reply (gen {st.get('generation', 0)}) — offline planner\n\n"
            f"Objective: {ctx.get('objective')}. Equity {ctx.get('equity')} "
            f"(delta {ctx.get('equity_delta')}).\n\n"
            f"Online LLM is rate-limited right now, so I planned with the built-in rules.\n"
            f"Actions this cycle: {done or 'none'}.\n",
            tag="reply",
        )

    st["generation"] = int(st.get("generation", 0)) + 1
    st["recipe_idx"] = (int(st.get("recipe_idx", 0)) + 1) % 16
    st["last_run_ts"] = now
    st["last_run_utc"] = datetime.now(timezone.utc).isoformat()
    _save_state(st)

    payload = {
        "ok": any_ok,
        "objective": ctx.get("objective"),
        "equity": ctx.get("equity"),
        "equity_delta": ctx.get("equity_delta"),
        "plan": {k: plan.get(k) for k in ("rationale", "actions", "user_reply")},
        "results": results,
        "generation": st["generation"],
    }
    log_audit("free_agent_step", payload)
    _log("free_agent_step", payload)
    return payload
