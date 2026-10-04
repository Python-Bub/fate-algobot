"""Guarded policy agent for live parameter adaptation."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from self_modify.audit_trail import log_audit
from self_modify.change_validator import validate_live_metrics, validate_param_changes, as_dict
from self_modify.shadow_validator import validate_candidate_changes


OVERRIDE_PATH = Path(os.getenv("POLICY_OVERRIDE_PATH", "data/policy/runtime_policy_overrides.json"))
STATE_PATH = Path(os.getenv("POLICY_STATE_PATH", "data/policy/policy_agent_state.json"))


def _load_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def clamp_loss_chasing(
    change: dict,
    *,
    equity_delta: float,
    cur_buy: float,
    cur_notional: float,
) -> dict:
    """Do not lower the buy bar or raise size while equity is falling.

    Self-modify hooks were doing both ("grow_equity — deploy idle capital")
    and the book bought more as it lost money.
    """
    out = dict(change)
    if float(equity_delta) >= 0:
        return out
    cap = float(os.getenv("POLICY_BUY_THRESHOLD_CAP", "0.72"))
    bt = out.get("BUY_THRESHOLD")
    if bt is not None and float(bt) < float(cur_buy):
        out["BUY_THRESHOLD"] = min(cap, max(float(cur_buy), 0.55) + 0.01)
    nt = out.get("ORDER_NOTIONAL")
    if nt is not None and float(nt) > float(cur_notional):
        out["ORDER_NOTIONAL"] = float(cur_notional)
    return out


def _save_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def get_runtime_param(name: str, default):
    """Live param. Deploy-scale env wins over stale policy JSON (losing book was easing gates)."""
    if os.getenv("POLICY_ENV_WINS", "true").lower() in ("1", "true", "yes", "on"):
        raw = os.getenv(name)
        if raw is not None and str(raw).strip() != "":
            if isinstance(default, bool):
                return str(raw).lower() in ("1", "true", "yes", "on")
            try:
                return type(default)(raw)
            except (TypeError, ValueError):
                return raw
    overrides = _load_json(OVERRIDE_PATH, {})
    if name in overrides:
        return overrides[name]
    # Policy historically wrote BUY_THRESHOLD; fortress reads MIN_MODEL_CONFIDENCE.
    aliases = {
        "MIN_MODEL_CONFIDENCE": "BUY_THRESHOLD",
        "BUY_THRESHOLD": "MIN_MODEL_CONFIDENCE",
    }
    alt = aliases.get(name)
    if alt and alt in overrides:
        return overrides[alt]
    return default


@dataclass
class GuardedPolicyAgent:
    mode: str = "live_guarded_self_modify"
    min_interval_sec: int = 300

    def __post_init__(self):
        self.enabled = os.getenv("POLICY_AGENT_ENABLED", "true").lower() in ("1", "true", "yes")
        self.human_lock = os.getenv("POLICY_HUMAN_LOCK", "false").lower() in ("1", "true", "yes")
        self.last_apply_ts = float(_load_json(STATE_PATH, {}).get("last_apply_ts", 0.0))

    def propose(self, metrics: dict) -> dict:
        """Simple adaptive policy: tune threshold and size by edge + drawdown."""
        hit = float(metrics.get("hit_rate", 0.5))
        drawdown = float(metrics.get("drawdown", 0.0))
        sharpe = float(metrics.get("sharpe_proxy", 0.0))
        deployed = float(metrics.get("deployed_frac", 1.0))
        target_deploy = float(os.getenv("FORTRESS_TARGET_DEPLOY_FRAC", "0.88"))
        cur_buy = float(get_runtime_param("BUY_THRESHOLD", float(os.getenv("BUY_THRESHOLD", "0.58"))))
        try:
            max_notional = float(
                os.getenv(
                    "POLICY_MAX_NOTIONAL",
                    os.getenv("HARD_MAX_ORDER_NOTIONAL", os.getenv("MAX_ORDER_NOTIONAL", "0")),
                )
                or 0
            )
        except (TypeError, ValueError):
            max_notional = 0.0
        hard_cap = float(os.getenv("HARD_MAX_ORDER_NOTIONAL", "0") or 0)
        if hard_cap > 0:
            max_notional = min(max_notional, hard_cap) if max_notional > 0 else hard_cap
        if max_notional <= 0:
            try:
                from analytics.buying_power import clip_ceiling_usd

                max_notional = clip_ceiling_usd(float(metrics.get("equity") or 0) or 100_000.0)
            except Exception:
                max_notional = 10_000.0
        cur_notional = float(get_runtime_param("ORDER_NOTIONAL", float(os.getenv("ORDER_NOTIONAL", "500"))))
        change = {}
        eq_delta = float(metrics.get("equity_delta") or 0.0)

        def _finish(ch: dict) -> dict:
            return clamp_loss_chasing(
                ch,
                equity_delta=eq_delta,
                cur_buy=cur_buy,
                cur_notional=cur_notional,
            )

        try:
            from self_modify.strategy_overlay import policy_hints

            hints = policy_hints({**metrics, "cur_buy": cur_buy, "cur_notional": cur_notional})
            for k in ("BUY_THRESHOLD", "ORDER_NOTIONAL"):
                if k in hints:
                    change[k] = hints[k]
        except Exception:
            pass
        # Losing / churning: tighten buys, shrink size — don't inflate tickets to 45k.
        if drawdown < -0.005 or hit < 0.48:
            cap = float(os.getenv("POLICY_BUY_THRESHOLD_CAP", "0.72"))
            change["BUY_THRESHOLD"] = min(cap, max(cur_buy, 0.55) + 0.02)
            change["ORDER_NOTIONAL"] = max(
                float(os.getenv("MIN_ORDER_NOTIONAL", "500")),
                min(cur_notional * 0.85, max_notional),
            )
            return _finish(change)
        # Under-invested book: size up and ease gates — do not tighten on small drawdowns.
        # A falling account is not "idle cash to deploy"; clamp_loss_chasing undoes the ease.
        if deployed < target_deploy - 0.15:
            change.setdefault("BUY_THRESHOLD", max(0.52, cur_buy - 0.01))
            change.setdefault("ORDER_NOTIONAL", min(cur_notional * 1.08, max_notional))
            return _finish(change)
        if hit > 0.58 and sharpe > 0.2 and drawdown > -0.04:
            change.setdefault("BUY_THRESHOLD", max(0.52, cur_buy - 0.01))
            change.setdefault("ORDER_NOTIONAL", min(cur_notional * 1.05, max_notional))
        elif hit < 0.45 or drawdown < -0.06:
            cap = float(os.getenv("POLICY_BUY_THRESHOLD_CAP", "0.72"))
            change.setdefault("BUY_THRESHOLD", min(cap, cur_buy + 0.015))
            change.setdefault("ORDER_NOTIONAL", max(cur_notional * 0.90, 100.0))
        if "ORDER_NOTIONAL" in change:
            change["ORDER_NOTIONAL"] = min(float(change["ORDER_NOTIONAL"]), max_notional)
        return _finish(change)

    def apply_if_valid(self, changes: dict, metrics: dict) -> dict:
        if not self.enabled:
            return {"applied": False, "reason": "disabled"}
        if self.human_lock:
            return {"applied": False, "reason": "human_lock"}

        vm = validate_live_metrics(metrics)
        if not vm.ok:
            log_audit("policy_rejected_metrics", {"metrics": metrics, "validation": as_dict(vm)})
            return {"applied": False, "reason": vm.reason}

        vp = validate_param_changes(changes)
        if not vp.accepted:
            log_audit("policy_rejected_params", {"changes": changes, "validation": as_dict(vp)})
            return {"applied": False, "reason": vp.reason}

        if os.getenv("POLICY_REQUIRE_SHADOW", "true").lower() in ("1", "true", "yes"):
            shadow = validate_candidate_changes(vp.accepted)
            if not shadow.get("ok", False):
                log_audit("policy_rejected_shadow", {"accepted": vp.accepted, "shadow": shadow})
                return {"applied": False, "reason": f"shadow:{shadow.get('reason', 'fail')}"}

        current = _load_json(OVERRIDE_PATH, {})
        accepted = dict(vp.accepted)
        if "BUY_THRESHOLD" in accepted and "MIN_MODEL_CONFIDENCE" not in accepted:
            accepted["MIN_MODEL_CONFIDENCE"] = accepted["BUY_THRESHOLD"]
        if "MIN_MODEL_CONFIDENCE" in accepted and "BUY_THRESHOLD" not in accepted:
            accepted["BUY_THRESHOLD"] = accepted["MIN_MODEL_CONFIDENCE"]
        current.update(accepted)
        current["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        _save_json(OVERRIDE_PATH, current)
        st = _load_json(STATE_PATH, {})
        st["last_apply_ts"] = datetime.now(timezone.utc).timestamp()
        _save_json(STATE_PATH, st)
        log_audit("policy_applied", {"accepted": accepted, "metrics": metrics})
        return {"applied": True, "accepted": accepted}

    def observe_and_maybe_adapt(self, metrics: dict) -> dict:
        proposed = self.propose(metrics)
        if not proposed:
            return {"applied": False, "reason": "no_change"}
        return self.apply_if_valid(proposed, metrics)

