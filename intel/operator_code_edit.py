"""Operator Doc AI — guarded code-edit autonomy.

When the Doc AI judges something actually bad, it explains why and applies
real repo edits via:
  1. Allowlisted writes (hooks, overlay, math weight overrides)
  2. Enqueue free-agent inbox prompts
  3. Trigger evolve_once / free_agent_step

Hard rules (optimize never remove):
  - Never delete models/, never shrink universe, never skip train phases
  - Never force-push / never touch destructive git
  - Never write .env secrets or credentials
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "data" / "intel" / "operator_edits.jsonl"
INBOX = ROOT / "data" / "agi" / "inbox"

OPERATOR_WRITABLE = frozenset(
    {
        "self_modify/custom_hooks.py",
        "data/self_improve/strategy_overlay.py",
        "data/intel/operator_math_overrides.json",
        "data/intel/operator_chat.md",
        "data/agi/inbox/OPERATOR_DOC_PROMPT.md",
    }
)

_FORBIDDEN_SNIPPETS = (
    "models/",
    "shutil.rmtree",
    "force-push",
    "git push --force",
    "git reset --hard",
    "rm -rf models",
    "UNIVERSE_SHRINK",
    "skip_train",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(event: str, payload: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts_utc": _now(), "event": event, **payload}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")


def _safe_rel(path: str) -> Path | None:
    rel = path.replace("\\", "/").lstrip("./")
    if ".." in rel.split("/"):
        return None
    if rel not in OPERATOR_WRITABLE:
        return None
    return ROOT / rel


def write_allowlisted(rel_path: str, content: str, *, reason: str = "") -> dict[str, Any]:
    try:
        from intel.talk_edit_gate import require_edits

        gate = require_edits(source="operator_code_edit.write_allowlisted", action=f"write:{rel_path}")
        if not gate.get("ok"):
            _log("edit_denied_billion_gate", {"path": rel_path, "gate": gate})
            return gate
    except Exception as e:
        _log("edit_gate_error", {"err": str(e)[:200]})
        return {"ok": False, "reason": "edit_gate_unavailable", "error": str(e)[:200]}

    for bad in _FORBIDDEN_SNIPPETS:
        if bad.lower() in (content or "").lower() and bad.startswith(("rm ", "git ", "shutil")):
            return {"ok": False, "reason": f"forbidden_content:{bad}"}

    target = _safe_rel(rel_path)
    if target is None:
        return {"ok": False, "reason": "path_not_allowlisted", "path": rel_path}

    if rel_path in ("self_modify/custom_hooks.py", "data/self_improve/strategy_overlay.py"):
        try:
            from self_modify.code_editor import write_allowlisted_file

            out = write_allowlisted_file(rel_path, content, tag=reason or "operator_doc")
            _log("code_editor_write", {"path": rel_path, "ok": bool(out.get("ok")), "reason": reason})
            return out
        except Exception as e:
            _log("code_editor_fallback", {"path": rel_path, "err": str(e)[:200]})

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix == ".py":
        try:
            import ast

            ast.parse(content)
        except SyntaxError as e:
            return {"ok": False, "reason": f"syntax_error:{e}"}

    target.write_text(content, encoding="utf-8")
    _log("direct_write", {"path": rel_path, "bytes": len(content), "reason": reason[:300]})
    return {"ok": True, "path": rel_path, "mode": "direct"}


def bump_math_weight(component: str, mult: float, *, note: str = "") -> dict[str, Any]:
    try:
        from intel.talk_edit_gate import require_edits

        gate = require_edits(source="operator_code_edit.bump_math_weight", action=f"math:{component}")
        if not gate.get("ok"):
            _log("edit_denied_billion_gate", {"component": component, "gate": gate})
            return gate
    except Exception as e:
        return {"ok": False, "reason": "edit_gate_unavailable", "error": str(e)[:200]}

    from analytics.math_pivot import load_operator_overrides, save_operator_overrides

    m = max(0.15, min(2.5, float(mult)))
    cur = load_operator_overrides()
    cur[component.strip().lower()] = m
    save_operator_overrides(cur, note=note or f"operator adjust {component}→{m}")
    _log("math_weight_bump", {"component": component, "mult": m, "note": note[:200]})
    return {"ok": True, "component": component, "mult": m}


def enqueue_free_agent_prompt(text: str, *, name: str = "OPERATOR_DOC_PROMPT.md") -> dict[str, Any]:
    INBOX.mkdir(parents=True, exist_ok=True)
    path = INBOX / name
    body = (
        f"# Operator Doc request ({_now()})\n\n"
        f"{text.strip()}\n\n"
        "Constraints: optimize never remove; no model deletes; no universe shrink; no force-push.\n"
        "Prefer math-first: residuals, cointegration, z-scores, ML on prices.\n"
        "Be honest about defects; fix with specifics, not theatrics.\n"
    )
    path.write_text(body, encoding="utf-8")
    _log("enqueue_free_agent", {"path": str(path), "chars": len(body)})
    return {"ok": True, "path": str(path)}


def trigger_evolve(*, force: bool = False) -> dict[str, Any]:
    try:
        from intel.talk_edit_gate import require_edits

        gate = require_edits(source="operator_code_edit.trigger_evolve", action="evolve")
        if not gate.get("ok"):
            _log("edit_denied_billion_gate", {"gate": gate})
            return gate
    except Exception as e:
        return {"ok": False, "reason": "edit_gate_unavailable", "error": str(e)[:200]}

    results: dict[str, Any] = {"ok": True, "actions": []}
    try:
        from self_modify.code_evolver import evolve_once

        ev = evolve_once()
        results["actions"].append({"evolve_once": ev})
    except Exception as e:
        results["actions"].append({"evolve_once_err": str(e)[:200]})
    try:
        from self_modify.free_agent import free_agent_step

        fa = free_agent_step(force=force)
        results["actions"].append(
            {
                "free_agent_step": {
                    k: fa.get(k) for k in ("ok", "reason", "plan", "generation") if k in fa
                }
            }
        )
    except Exception as e:
        results["actions"].append({"free_agent_err": str(e)[:200]})
    _log("trigger_evolve", results)
    return results


def apply_honest_fix(topic: str, *, user_text: str = "") -> dict[str, Any]:
    """When assessment says something is actually bad — explain (caller) and edit."""
    try:
        from intel.talk_edit_gate import require_edits

        gate = require_edits(source="operator_code_edit.apply_honest_fix", action="honest_fix")
        if not gate.get("ok"):
            _log("edit_denied_billion_gate", {"topic": topic[:200], "gate": gate})
            return {**gate, "actions": []}
    except Exception as e:
        _log("edit_gate_error", {"err": str(e)[:200]})
        return {"ok": False, "reason": "edit_gate_unavailable", "actions": [], "error": str(e)[:200]}

    topic_l = (topic + " " + user_text).lower()
    actions: list[dict[str, Any]] = []
    if any(k in topic_l for k in ("news", "sentiment", "narrative", "cramer", "headline")):
        actions.append(
            bump_math_weight("news", 0.45, note="honest: narrative weight too high vs math")
        )
        actions.append(bump_math_weight("hedge_fund", 1.45, note="honest: prefer factor stack"))
        actions.append(bump_math_weight("cross_company", 1.40, note="honest: linkage math"))
        actions.append(bump_math_weight("hidden_anomaly", 1.40, note="honest: residual anomalies"))

    if any(k in topic_l for k in ("loss", "losing", "drawdown", "red", "pnl", "poor", "bleeding", "trash", "weak")):
        actions.append(bump_math_weight("exec_conf", 1.25, note="honest: gate on exec conf"))
        actions.append(bump_math_weight("value_investing", 1.30, note="honest: MoS when losing"))
        actions.append(
            enqueue_free_agent_prompt(
                "Paper performance is weak — state that honestly. Evolve hooks/overlay toward "
                "math-first: residual IR, pair z, DCF MoS; reduce narrative weight. "
                f"User said: {user_text[:800]}"
            )
        )
        actions.append(trigger_evolve(force=True))

    if any(k in topic_l for k in ("fix", "bug", "broken", "edit", "code", "refactor", "quality", "bad")):
        actions.append(
            enqueue_free_agent_prompt(
                "Operator Doc found concrete quality issues. Self-improve allowlisted "
                f"hooks/overlay. Topic: {topic[:200]}\nUser: {user_text[:800]}"
            )
        )
        actions.append(trigger_evolve(force=False))

    if not actions:
        actions.append(
            enqueue_free_agent_prompt(f"Operator note: {user_text[:1200] or topic[:400]}")
        )

    _log("apply_honest_fix", {"topic": topic[:200], "n_actions": len(actions)})
    return {"ok": True, "actions": actions}


# Back-compat alias (old name) — same behavior, honest path
def apply_roast_fix(topic: str, *, user_text: str = "") -> dict[str, Any]:
    return apply_honest_fix(topic, user_text=user_text)


_CMD_RE = re.compile(
    r"\[\[\s*(status|train|explain\s+last\s+loss|evolve|fix|math|mood|help)\s*\]\]",
    re.I,
)


def parse_command_tags(text: str) -> list[str]:
    return [m.group(1).strip().lower() for m in _CMD_RE.finditer(text or "")]
