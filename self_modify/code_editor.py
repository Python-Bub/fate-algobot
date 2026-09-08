"""
Guarded repository code editor for the AGI agent.

Only allowlisted paths may be written. Every change is snapshotted, AST-validated,
smoke-tested, and rolled back on failure.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from self_modify.audit_trail import log_audit
from self_modify.rollback_manager import rollback_snapshot, snapshot_files

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = Path("data/self_improve/code_editor_log.jsonl")

# Relative paths the agent may modify (no models/, .env, credentials).
EDITABLE_REL_PATHS = frozenset(
    {
        "self_modify/custom_hooks.py",
        "data/self_improve/strategy_overlay.py",
        "data/self_improve/gainz_student.py",
    }
)

HOOKS_REQUIRED_FUNCS = frozenset(
    {
        "equity_rank_boost",
        "fortress_size_mult",
        "policy_priority_hints",
        "VERSION",
        "GENERATION",
        "RATIONALE",
    }
)

HOOKS_FORBIDDEN = frozenset(
    {
        "import",
        "Import",
        "ImportFrom",
        "exec",
        "eval",
        "compile",
        "open",
        "__import__",
        "subprocess",
        "os",
        "sys",
        "pathlib",
        "shutil",
        "socket",
        "requests",
    }
)

HOOKS_TEMPLATE = '''"""
Agent-editable extension hooks — safe surface for self-modifying rank/execution logic.
GENERATION={generation}  RATIONALE={rationale!r}
Objective: {objective}
"""

VERSION = 1
GENERATION = {generation}
RATIONALE = {rationale!r}


def equity_rank_boost(symbol: str, score: float, metrics: dict) -> float:
    boost = 0.0
{equity_body}
    return max(-0.08, min(0.08, float(boost)))


def fortress_size_mult(metrics: dict) -> float:
    mult = 1.0
{size_body}
    return max(0.85, min(1.25, float(mult)))


def policy_priority_hints(metrics: dict) -> dict:
    hints: dict = {{}}
{policy_body}
    return hints
'''

_HOOK_RECIPES: list[dict[str, Any]] = [
    {
        "rationale": "grow_equity — deploy idle capital",
        "equity_rules": [
            "if float(metrics.get('deployed_frac') or 0.0) < 0.60:",
            "    boost += 0.025",
            "if float(metrics.get('equity_delta') or 0.0) <= 0:",
            "    boost += 0.02",
        ],
        "size_rules": [
            "if float(metrics.get('deployed_frac') or 0.0) < 0.65:",
            "    mult += 0.08",
        ],
        "policy_lines": [
            'hints["ORDER_NOTIONAL"] = min(float(metrics.get("cur_notional", 8000)) * 1.08, 48000.0)',
            'hints["BUY_THRESHOLD"] = max(0.52, float(metrics.get("cur_buy", 0.55)) - 0.012)',
        ],
    },
    {
        "rationale": "grow_equity — high-conviction tilt",
        "equity_rules": [
            "p = float(metrics.get('p_up') or metrics.get('neural_p_up') or 0.5)",
            "if p > 0.60:",
            "    boost += 0.03",
        ],
        "size_rules": ["if float(metrics.get('equity_delta') or 0.0) > 0:", "    mult += 0.04"],
        "policy_lines": ['hints["BUY_THRESHOLD"] = max(0.52, float(metrics.get("cur_buy", 0.55)) - 0.008)'],
    },
]


def _log(event: str, payload: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts_utc": datetime.now(timezone.utc).isoformat(), "event": event, **payload}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")


def _body_lines(lines: list[str]) -> str:
    kept = [str(ln).rstrip() for ln in lines if str(ln).strip()]
    if not kept:
        return "    pass"
    out: list[str] = []
    for ln in kept:
        stripped = ln.lstrip()
        extra = len(ln) - len(stripped)
        out.append(" " * (4 + extra) + stripped)
    return "\n".join(out)


def _validate_hooks_source(source: str) -> tuple[bool, str]:
    max_bytes = int(os.getenv("AGI_CODE_MAX_BYTES", "16000"))
    if len(source) > max_bytes:
        return False, "too_large"
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return False, f"syntax:{e}"
    for node in ast.walk(tree):
        name = type(node).__name__
        if name in HOOKS_FORBIDDEN:
            return False, f"forbidden:{name}"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in HOOKS_FORBIDDEN:
                return False, f"forbidden_call:{node.func.id}"
    funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    required_funcs = {"equity_rank_boost", "fortress_size_mult", "policy_priority_hints"}
    if not required_funcs.issubset(funcs):
        return False, "missing_required_functions"
    extra = funcs - required_funcs
    if extra:
        return False, f"extra_functions:{extra}"
    return True, "ok"


def _run_smoke() -> tuple[bool, str]:
    tests = [
        str(ROOT / "tests" / "test_self_improve.py"),
        str(ROOT / "tests" / "test_agi_objective.py"),
    ]
    existing = [t for t in tests if Path(t).is_file()]
    if not existing:
        return True, "no_tests"
    py = ROOT / "venv" / "bin" / "python"
    cmd = [str(py), "-m", "pytest", "-q", "--tb=no", *existing]
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=120)
        tail = (r.stdout or "")[-300:] + (r.stderr or "")[-300:]
        return r.returncode == 0, tail.strip() or f"exit={r.returncode}"
    except Exception as e:
        return False, str(e)


def _resolve_rel(rel: str) -> Path:
    rel = rel.replace("\\", "/").lstrip("/")
    if rel not in EDITABLE_REL_PATHS:
        raise PermissionError(f"path_not_allowlisted:{rel}")
    return ROOT / rel


def write_allowlisted_file(rel: str, content: str, *, tag: str) -> dict[str, Any]:
    path = _resolve_rel(rel)
    if rel == "self_modify/custom_hooks.py":
        ok, reason = _validate_hooks_source(content)
        if not ok:
            return {"ok": False, "reason": f"hooks_invalid:{reason}"}
    elif rel == "data/self_improve/strategy_overlay.py":
        from self_modify.code_evolver import _validate_overlay_source

        ok, reason = _validate_overlay_source(content)
        if not ok:
            return {"ok": False, "reason": f"overlay_invalid:{reason}"}
    elif rel == "data/self_improve/gainz_student.py":
        from self_modify.gainz_evolver import detect_escape

        if "def student_signal" not in content:
            return {"ok": False, "reason": "missing_student_signal"}
        hits = detect_escape(content)
        real = [h for h in hits if not str(h).startswith("cheat:")]
        if real:
            return {"ok": False, "reason": f"sandbox_escape:{real}"}
        if any(str(h).startswith("cheat:") for h in hits):
            return {"ok": False, "reason": f"teacher_cheat:{hits}"}
    else:
        return {"ok": False, "reason": "unknown_validator"}

    snap = snapshot_files([str(path)], tag=tag)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    test_ok, detail = _run_smoke()
    if not test_ok:
        rollback_snapshot(str(snap))
        if rel == "self_modify/custom_hooks.py":
            try:
                import importlib
                import self_modify.custom_hooks as ch

                importlib.reload(ch)
            except Exception:
                pass
        return {"ok": False, "reason": "tests_failed", "detail": detail}

    if rel == "self_modify/custom_hooks.py":
        try:
            import importlib
            import self_modify.custom_hooks as ch

            importlib.reload(ch)
        except Exception:
            pass

    log_audit("code_editor_applied", {"path": rel, "tag": tag, "bytes": len(content)})
    _log("written", {"path": rel, "tag": tag})
    return {"ok": True, "path": rel, "snapshot": str(snap), "detail": detail}


def render_hooks_proposal(proposal: dict[str, Any], generation: int, objective: str) -> str:
    return HOOKS_TEMPLATE.format(
        generation=generation,
        rationale=str(proposal.get("rationale", "agent"))[:240],
        objective=objective[:120],
        equity_body=_body_lines(list(proposal.get("equity_rules") or ["pass"])),
        size_body=_body_lines(list(proposal.get("size_rules") or ["pass"])),
        policy_body=_body_lines(list(proposal.get("policy_lines") or ["pass"])),
    )


def propose_hooks_edit(metrics: dict, *, recipe_idx: int = 0) -> dict[str, Any]:
    recipe = _HOOK_RECIPES[recipe_idx % len(_HOOK_RECIPES)]
    return {
        "rationale": recipe["rationale"],
        "equity_rules": list(recipe.get("equity_rules") or []),
        "size_rules": list(recipe.get("size_rules") or []),
        "policy_lines": list(recipe.get("policy_lines") or []),
    }


def evolve_custom_hooks(metrics: dict, *, generation: int, recipe_idx: int = 0) -> dict[str, Any]:
    from self_modify.objective_engine import primary_objective

    proposal = propose_hooks_edit(metrics, recipe_idx=recipe_idx)
    source = render_hooks_proposal(proposal, generation, primary_objective())
    return write_allowlisted_file(
        "self_modify/custom_hooks.py",
        source,
        tag=f"hooks_g{generation}",
    )
