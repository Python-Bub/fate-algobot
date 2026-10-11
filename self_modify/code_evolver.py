"""
Guarded self-improvement: evolve strategy overlay code + policy params to beat the market.

Writes to data/self_improve/strategy_overlay.py and archives every generation under
data/self_improve/archive/gen_N.py.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from self_modify.audit_trail import log_audit
from self_modify.change_validator import as_dict, validate_live_metrics, validate_param_changes
from self_modify.policy_agent import GuardedPolicyAgent, get_runtime_param
from self_modify.rollback_manager import rollback_snapshot, snapshot_files
from self_modify.strategy_overlay import OVERLAY_PATH, invalidate_cache

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = Path(os.getenv("SELF_IMPROVE_STATE_PATH", "data/self_improve/evolver_state.json"))
LOG_PATH = Path("data/self_improve/evolver_log.jsonl")
ARCHIVE_DIR = Path(os.getenv("SELF_IMPROVE_ARCHIVE_DIR", "data/self_improve/archive"))

OVERLAY_TEMPLATE = '''"""
Auto-evolved strategy overlay — written by self_modify/code_evolver.py.
GENERATION={generation}  RATIONALE={rationale!r}
Objective: beat {benchmark} alpha target {alpha_target}
"""

VERSION = 1
GENERATION = {generation}
RATIONALE = {rationale!r}


def beat_market_mode(metrics: dict) -> bool:
    alpha = metrics.get("alpha")
    if alpha is None:
        return bool(metrics.get("losing_to_market"))
    return float(alpha) < {alpha_target}


def hf_weight_deltas() -> dict[str, float]:
    return {hf_deltas}


def rank_tilt(symbol: str, p_up: float, metrics: dict) -> float:
    sym = str(symbol).upper()
    tilt = 0.0
{rank_body}
    return max(-0.12, min(0.12, float(tilt)))


def paper_score_boost(symbol: str, score: float, metrics: dict) -> float:
    boost = 0.0
{paper_body}
    return max(-0.15, min(0.15, float(boost)))


def hft_confidence_delta(metrics: dict) -> float:
    delta = 0.0
{hft_body}
    return max(-0.08, min(0.08, float(delta)))


def policy_hints(metrics: dict) -> dict:
    hints = {{}}
{policy_body}
    return hints
'''

ALLOWED_AST_NAMES = frozenset(
    {
        "hf_weight_deltas",
        "rank_tilt",
        "policy_hints",
        "paper_score_boost",
        "hft_confidence_delta",
        "beat_market_mode",
        "VERSION",
        "GENERATION",
        "RATIONALE",
    }
)
FORBIDDEN_AST = frozenset(
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

# Rotate exploration recipes so every generation writes meaningfully new code.
_EXPLORER_RECIPES: list[dict[str, Any]] = [
    {
        "rationale": "beat_market — momentum surge",
        "hf_deltas": {"HF_W_MOMENTUM": 0.035, "HF_W_TREND": 0.025},
        "rank_rules": [
            "if metrics.get('alpha') is not None and float(metrics.get('alpha', 0)) < 0:",
            "    tilt += 0.03",
            "if p_up > 0.58 and float(metrics.get('rsi_14', 50)) < 55:",
            "    tilt += 0.02",
        ],
        "paper_rules": [
            "if float(metrics.get('alpha', 0) or 0) < 0:",
            "    boost += 0.04",
            "if score > 0.55:",
            "    boost += 0.02",
        ],
        "hft_rules": ["if float(metrics.get('alpha', 0) or 0) < 0:", "    delta -= 0.02"],
        "policy_lines": [
            'if float(metrics.get("equity_delta") or metrics.get("alpha") or 0) < 0:',
            '    hints["BUY_THRESHOLD"] = min(0.72, float(metrics.get("cur_buy", 0.55)) + 0.01)',
            '    hints["ORDER_NOTIONAL"] = max(500.0, float(metrics.get("cur_notional", 8000)) * 0.90)',
            'else:',
            '    hints["BUY_THRESHOLD"] = max(0.55, float(metrics.get("cur_buy", 0.55)))',
        ],
    },
    {
        "rationale": "beat_market — stat-arb + mean-rev",
        "hf_deltas": {"HF_W_STAT_ARB": 0.04, "HF_W_MEAN_REV": 0.03, "HF_W_MOMENTUM": -0.015},
        "rank_rules": [
            "if float(metrics.get('rsi_14', 50)) > 70:",
            "    tilt -= 0.025",
            "elif float(metrics.get('rsi_14', 50)) < 35:",
            "    tilt += 0.025",
        ],
        "paper_rules": ["boost += 0.03 * float(metrics.get('hit_rate', 0.5) - 0.5)"],
        "hft_rules": ["delta -= 0.01"],
        "policy_lines": [
            'if float(metrics.get("equity_delta") or 0.0) <= 0:',
            '    hints["BUY_THRESHOLD"] = min(0.72, float(metrics.get("cur_buy", 0.55)) + 0.01)',
            'else:',
            '    hints["BUY_THRESHOLD"] = max(0.55, float(metrics.get("cur_buy", 0.55)))',
        ],
    },
    {
        "rationale": "beat_market — quality + deploy hard",
        "hf_deltas": {"HF_W_QUALITY": 0.03, "HF_W_VALUE": 0.02, "HF_W_LIQUIDITY_MM": 0.02},
        "rank_rules": ["if p_up > 0.60:", "    tilt += 0.02"],
        "paper_rules": [
            "if float(metrics.get('deployed_frac', 0) or 0) < 0.5:",
            "    boost += 0.05",
        ],
        "hft_rules": ["if float(metrics.get('deployed_frac', 0) or 0) < 0.4:", "    delta -= 0.03"],
        "policy_lines": [
            'if float(metrics.get("equity_delta") or 0.0) <= 0:',
            '    hints["ORDER_NOTIONAL"] = max(500.0, float(metrics.get("cur_notional", 8000)) * 0.90)',
            'else:',
            '    hints["ORDER_NOTIONAL"] = min(float(metrics.get("cur_notional", 8000)) * 1.04, 12000.0)',
        ],
    },
]


def _log(event: str, payload: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts_utc": datetime.now(timezone.utc).isoformat(), "event": event, **payload}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")


def _load_state() -> dict:
    if not STATE_PATH.is_file():
        return {"generation": 0, "last_run_utc": None, "recipe_idx": 0}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"generation": 0, "last_run_utc": None, "recipe_idx": 0}


def _save_state(st: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")


def _archive_generation(source: str, generation: int) -> Path:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    path = ARCHIVE_DIR / f"gen_{generation:05d}.py"
    path.write_text(source, encoding="utf-8")
    return path


def collect_signals() -> dict[str, Any]:
    sig: dict[str, Any] = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "deployed_frac": 0.0,
        "hit_rate": 0.5,
        "drawdown": 0.0,
        "sharpe_proxy": 0.0,
        "paper_pnl": 0.0,
        "paper_n_picks": 0,
        "alpha": None,
        "beating_market": False,
        "losing_to_market": False,
    }
    rep_dir = ROOT / "reports"
    if rep_dir.is_dir():
        reps = sorted(rep_dir.glob("paper_sim_*.json"))
        if reps:
            try:
                doc = json.loads(reps[-1].read_text(encoding="utf-8"))
                sig["paper_pnl"] = float(doc.get("sum_hypothetical_pnl_usd", 0.0))
                sig["paper_n_picks"] = int(doc.get("n_picks", 0) or len(doc.get("picks") or []))
                m = doc.get("asym_filter_metrics") or {}
                sig["hit_rate"] = float(m.get("hit_rate", sig["hit_rate"]))
            except Exception:
                pass
    try:
        from alpaca_broker import get_account, list_positions, intraday_buying_power

        acct = get_account() or {}
        eq = float(acct.get("equity") or 0.0)
        pos = list_positions()
        mv = sum(abs(float(p.get("market_value") or 0)) for p in pos)
        if eq > 0:
            sig["deployed_frac"] = mv / eq
        sig["equity"] = eq
        sig["buying_power"] = float(intraday_buying_power(acct))
        sig["n_positions"] = len(pos)
        from self_modify.market_benchmark import beat_market_snapshot

        bench = beat_market_snapshot(eq)
        sig.update(bench)
    except Exception:
        pass
    try:
        from self_modify.policy_agent import _load_json, OVERRIDE_PATH

        sig["policy_overrides"] = _load_json(OVERRIDE_PATH, {})
    except Exception:
        pass
    return sig


def _validate_overlay_source(source: str) -> tuple[bool, str]:
    max_bytes = int(os.getenv("SELF_IMPROVE_MAX_BYTES", "24000"))
    if len(source) > max_bytes:
        return False, "too_large"
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return False, f"syntax:{e}"
    for node in ast.walk(tree):
        name = type(node).__name__
        if name in FORBIDDEN_AST:
            return False, f"forbidden:{name}"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_AST:
                return False, f"forbidden_call:{node.func.id}"
    funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    if not funcs <= ALLOWED_AST_NAMES:
        return False, f"extra_functions:{funcs - ALLOWED_AST_NAMES}"
    required = {
        "hf_weight_deltas",
        "rank_tilt",
        "policy_hints",
        "paper_score_boost",
        "hft_confidence_delta",
        "beat_market_mode",
    }
    if not required.issubset(funcs):
        return False, "missing_required_functions"
    return True, "ok"


def _run_smoke_tests() -> tuple[bool, str]:
    tests = [
        str(ROOT / "tests" / "test_hedge_fund_stack.py"),
        str(ROOT / "tests" / "test_self_improve.py"),
    ]
    existing = [t for t in tests if Path(t).is_file()]
    if not existing:
        return True, "no_tests"
    py = ROOT / "venv" / "bin" / "python"
    cmd = [str(py), "-m", "pytest", "-q", "--tb=no", *existing]
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=120)
        ok = r.returncode == 0
        tail = (r.stdout or "")[-400:] + (r.stderr or "")[-400:]
        return ok, tail.strip() or f"exit={r.returncode}"
    except Exception as e:
        return False, str(e)


def _explore_recipe(metrics: dict, recipe_idx: int) -> dict[str, Any]:
    recipe = _EXPLORER_RECIPES[recipe_idx % len(_EXPLORER_RECIPES)]
    return {
        "rationale": recipe["rationale"],
        "hf_deltas": dict(recipe.get("hf_deltas") or {}),
        "rank_rules": list(recipe.get("rank_rules") or ["pass"]),
        "paper_rules": list(recipe.get("paper_rules") or ["pass"]),
        "hft_rules": list(recipe.get("hft_rules") or ["pass"]),
        "policy_lines": list(recipe.get("policy_lines") or ["pass"]),
        "param_changes": {},
    }


def _rule_based_proposal(metrics: dict, *, recipe_idx: int = 0) -> dict[str, Any]:
    losing = bool(metrics.get("losing_to_market")) or float(metrics.get("alpha") or 0) < 0
    always = os.getenv("SELF_IMPROVE_ALWAYS_MUTATE", "true").lower() in ("1", "true", "yes")

    if losing or always:
        return _explore_recipe(metrics, recipe_idx)

    deployed = float(metrics.get("deployed_frac", 0.0))
    pnl = float(metrics.get("paper_pnl", 0.0))
    hit = float(metrics.get("hit_rate", 0.5))
    target = float(os.getenv("FORTRESS_TARGET_DEPLOY_FRAC", "0.92"))

    if deployed < target - 0.12:
        return _explore_recipe(metrics, recipe_idx)

    if pnl < 0 and hit < 0.48:
        p = _explore_recipe(metrics, (recipe_idx + 1) % len(_EXPLORER_RECIPES))
        p["rationale"] = "negative_edge — " + p["rationale"]
        return p

    return _explore_recipe(metrics, recipe_idx)


def _llm_proposal(metrics: dict) -> dict[str, Any] | None:
    if os.getenv("SELF_IMPROVE_USE_LLM", "true").lower() not in ("1", "true", "yes"):
        return None
    try:
        from intel.llm_signal_agent import _post_chat, _extract_json
    except Exception:
        return None
    try:
        from intel.api_budget import llm_allowed

        if not llm_allowed():
            return None
    except Exception:
        pass

    system = (
        "You evolve Python strategy overlay code for a US equity algo bot. "
        "PRIMARY OBJECTIVE: Make portfolio account larger (grow equity). "
        "Secondary: beat SPY when possible. Do anything legal/safe to improve edge.\n"
        "Return strict JSON:\n"
        "rationale, hf_weight_deltas (HF_W_* in [-0.05,0.05]),\n"
        "rank_rules (Python lines using symbol,p_up,metrics,tilt),\n"
        "paper_rules (lines using symbol,score,metrics,boost),\n"
        "hft_rules (lines using metrics,delta),\n"
        "policy_hints_lines (BUY_THRESHOLD/ORDER_NOTIONAL),\n"
        "param_changes (optional). No imports, no I/O, no exec."
    )
    user = json.dumps(metrics, indent=2)[:8000]
    try:
        raw = _post_chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}]
        )
        obj = _extract_json(raw)
        hf = obj.get("hf_weight_deltas") or {}
        hf_clean = {
            str(k): max(-0.05, min(0.05, float(v)))
            for k, v in hf.items()
            if str(k).startswith("HF_W_")
        }
        return {
            "rationale": str(obj.get("rationale", "llm_beat_market"))[:240],
            "hf_deltas": hf_clean,
            "rank_rules": [str(x) for x in (obj.get("rank_rules") or ["pass"])][:16],
            "paper_rules": [str(x) for x in (obj.get("paper_rules") or ["pass"])][:12],
            "hft_rules": [str(x) for x in (obj.get("hft_rules") or ["pass"])][:8],
            "policy_lines": [str(x) for x in (obj.get("policy_hints_lines") or ["pass"])][:10],
            "param_changes": obj.get("param_changes") or {},
        }
    except Exception as e:
        _log("llm_proposal_failed", {"error": str(e)[:200]})
        return None


def _body_lines(lines: list[str]) -> str:
    """Indent recipe lines into a function body; preserve relative nesting (if/elif bodies)."""
    kept = [str(ln).rstrip() for ln in lines if str(ln).strip()]
    if not kept:
        return "    pass"
    out: list[str] = []
    for ln in kept:
        stripped = ln.lstrip()
        extra = len(ln) - len(stripped)
        out.append(" " * (4 + extra) + stripped)
    return "\n".join(out)


def _export_hft_runtime(metrics: dict, generation: int) -> None:
    path = Path(os.getenv("SELF_IMPROVE_HFT_RUNTIME_PATH", "data/self_improve/hft_runtime.json"))
    try:
        from self_modify.strategy_overlay import hft_confidence_delta

        delta = float(hft_confidence_delta(dict(metrics)))
    except Exception:
        delta = 0.0
    delta = max(-0.08, min(0.08, delta))
    path.parent.mkdir(parents=True, exist_ok=True)
    prev: dict = {}
    if path.is_file():
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
    doc = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "generation": generation,
        "confidence_floor_delta": delta,
        "losing_to_market": bool(metrics.get("losing_to_market")),
        "alpha": metrics.get("alpha"),
    }
    for k in ("gainz_buys", "gainz_ts"):
        if k in prev:
            doc[k] = prev[k]
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def _render_overlay(proposal: dict, generation: int, metrics: dict) -> str:
    hf_items = ", ".join(f'"{k}": {v:.4f}' for k, v in sorted(proposal.get("hf_deltas", {}).items()))
    hf_block = "{" + hf_items + "}" if hf_items else "{}"
    alpha_target = float(os.getenv("SELF_IMPROVE_ALPHA_TARGET", "0.0"))
    bench = str(metrics.get("benchmark") or os.getenv("SELF_IMPROVE_BENCHMARK", "SPY"))
    return OVERLAY_TEMPLATE.format(
        generation=generation,
        rationale=proposal.get("rationale", ""),
        benchmark=bench,
        alpha_target=alpha_target,
        hf_deltas=hf_block,
        rank_body=_body_lines(proposal.get("rank_rules") or ["pass"]),
        paper_body=_body_lines(proposal.get("paper_rules") or ["pass"]),
        hft_body=_body_lines(proposal.get("hft_rules") or ["pass"]),
        policy_body=_body_lines(proposal.get("policy_lines") or ["pass"]),
    )


def _apply_params_aggressive(changes: dict, metrics: dict) -> dict[str, Any]:
    if not changes:
        return {"applied": False, "reason": "no_changes"}
    vp = validate_param_changes(changes)
    if not vp.accepted:
        return {"applied": False, "reason": vp.reason}
    aggressive = os.getenv("SELF_IMPROVE_BEAT_MARKET_MODE", "true").lower() in ("1", "true", "yes")
    losing = bool(metrics.get("losing_to_market"))
    under_deployed = float(metrics.get("deployed_frac", 1.0) or 0) < 0.55
    shadow_off = os.getenv("POLICY_REQUIRE_SHADOW", "true").lower() not in ("1", "true", "yes")
    if aggressive and (losing or under_deployed or shadow_off):
        from self_modify.policy_agent import OVERRIDE_PATH, _load_json, _save_json

        current = _load_json(OVERRIDE_PATH, {})
        current.update(vp.accepted)
        current["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        _save_json(OVERRIDE_PATH, current)
        log_audit(
            "self_improve_params_applied",
            {"accepted": vp.accepted, "shadow": "bypass_beat_market", "losing": losing, "under_deployed": under_deployed},
        )
        return {"applied": True, "accepted": vp.accepted, "shadow_bypass": True}
    agent = GuardedPolicyAgent()
    return agent.apply_if_valid(vp.accepted, metrics)


def evolve_once(*, force: bool = False) -> dict[str, Any]:
    if os.getenv("SELF_IMPROVE_ENABLED", "true").lower() not in ("1", "true", "yes"):
        return {"ok": False, "reason": "disabled"}
    if os.getenv("SELF_IMPROVE_HUMAN_LOCK", "false").lower() in ("1", "true", "yes"):
        return {"ok": False, "reason": "human_lock"}

    st = _load_state()
    losing = False
    min_sec = int(os.getenv("SELF_IMPROVE_MIN_INTERVAL_SEC", "180"))
    if os.getenv("SELF_IMPROVE_BEAT_MARKET_MODE", "true").lower() in ("1", "true", "yes"):
        min_sec = int(os.getenv("SELF_IMPROVE_LOSING_INTERVAL_SEC", "120"))

    last = st.get("last_run_ts") or 0.0
    now = datetime.now(timezone.utc).timestamp()

    metrics_preview = collect_signals()
    losing = bool(metrics_preview.get("losing_to_market"))
    if losing:
        min_sec = int(os.getenv("SELF_IMPROVE_LOSING_INTERVAL_SEC", "90"))

    if not force and now - float(last) < min_sec:
        return {"ok": False, "reason": "interval", "wait_sec": int(min_sec - (now - last))}

    metrics = metrics_preview
    metrics["cur_buy"] = float(get_runtime_param("BUY_THRESHOLD", 0.55))
    metrics["cur_notional"] = float(get_runtime_param("ORDER_NOTIONAL", 5000))

    vm = validate_live_metrics(metrics)
    if not vm.ok and not force and not losing:
        log_audit("self_improve_rejected_metrics", {"metrics": metrics, "validation": as_dict(vm)})
        return {"ok": False, "reason": vm.reason}

    recipe_idx = int(st.get("recipe_idx", 0))
    proposal = _llm_proposal(metrics) or _rule_based_proposal(metrics, recipe_idx=recipe_idx)
    generation = int(st.get("generation", 0)) + 1
    source = _render_overlay(proposal, generation, metrics)

    valid, reason = _validate_overlay_source(source)
    if not valid:
        _log("overlay_rejected", {"reason": reason})
        return {"ok": False, "reason": f"overlay_invalid:{reason}"}

    snap = snapshot_files([str(OVERLAY_PATH)], tag=f"overlay_g{generation}")
    OVERLAY_PATH.parent.mkdir(parents=True, exist_ok=True)
    OVERLAY_PATH.write_text(source, encoding="utf-8")
    archive_path = _archive_generation(source, generation)
    invalidate_cache()
    _export_hft_runtime(metrics, generation)

    test_ok, test_detail = _run_smoke_tests()
    if not test_ok:
        rollback_snapshot(str(snap))
        invalidate_cache()
        _log("overlay_rollback", {"reason": "tests_failed", "detail": test_detail[:500]})
        return {"ok": False, "reason": "tests_failed", "detail": test_detail}

    changes = dict(proposal.get("param_changes") or {})
    try:
        from self_modify.strategy_overlay import policy_hints

        hints = policy_hints(metrics)
        for k in ("BUY_THRESHOLD", "ORDER_NOTIONAL"):
            if k in hints:
                changes[k] = hints[k]
    except Exception:
        pass
    param_result = _apply_params_aggressive(changes, metrics)

    st["generation"] = generation
    st["recipe_idx"] = (recipe_idx + 1) % len(_EXPLORER_RECIPES)
    st["last_run_ts"] = now
    st["last_run_utc"] = datetime.now(timezone.utc).isoformat()
    st["last_rationale"] = proposal.get("rationale", "")
    st["last_alpha"] = metrics.get("alpha")
    _save_state(st)
    log_audit(
        "self_improve_applied",
        {
            "generation": generation,
            "archive": str(archive_path),
            "rationale": proposal.get("rationale"),
            "alpha": metrics.get("alpha"),
            "param_result": param_result,
        },
    )
    _log("evolved", {"generation": generation, "alpha": metrics.get("alpha"), "archive": str(archive_path)})
    return {
        "ok": True,
        "generation": generation,
        "rationale": proposal.get("rationale"),
        "alpha": metrics.get("alpha"),
        "archive": str(archive_path),
        "param_result": param_result,
        "test_detail": test_detail,
    }


def main() -> int:
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
    except Exception:
        pass
    force = "--force" in sys.argv
    out = evolve_once(force=force)
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
