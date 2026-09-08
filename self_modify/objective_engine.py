"""
Primary objective engine — reward signals tied to growing portfolio account equity.

Default objective: "Make portfolio account larger"
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = Path(os.getenv("OBJECTIVE_EQUITY_HISTORY", "data/self_improve/equity_history.jsonl"))
STATE_PATH = Path(os.getenv("OBJECTIVE_STATE_PATH", "data/self_improve/objective_state.json"))

DEFAULT_OBJECTIVE = "Make portfolio account larger"


def primary_objective() -> str:
    return os.getenv("AGI_PRIMARY_OBJECTIVE", DEFAULT_OBJECTIVE).strip() or DEFAULT_OBJECTIVE


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(st: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(st, indent=2), encoding="utf-8")


def _append_history(row: dict[str, Any]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def fetch_account_equity() -> dict[str, Any]:
    out: dict[str, Any] = {
        "equity": 0.0,
        "cash": 0.0,
        "buying_power": 0.0,
        "portfolio_value": 0.0,
        "n_positions": 0,
        "ok": False,  # False => fetch failed (e.g. 429); equity=0 is NOT a real reading
    }
    try:
        from alpaca_broker import get_account, intraday_buying_power, list_positions

        acct = get_account() or {}
        eq = float(acct.get("equity") or acct.get("portfolio_value") or 0.0)
        if eq <= 0:
            # No usable equity (failed/empty account fetch) — leave ok=False.
            return out
        cash = float(acct.get("cash") or 0.0)
        bp = float(intraday_buying_power(acct))
        pos = list_positions()
        mv = sum(abs(float(p.get("market_value") or 0)) for p in pos)
        out.update(
            {
                "equity": eq,
                "cash": cash,
                "buying_power": bp,
                "portfolio_value": float(acct.get("portfolio_value") or eq),
                "n_positions": len(pos),
                "deployed_mv": mv,
                "deployed_frac": (mv / eq) if eq > 0 else 0.0,
                "ok": True,
            }
        )
    except Exception:
        pass
    return out


def record_equity_snapshot(*, source: str = "objective_engine") -> dict[str, Any]:
    acct = fetch_account_equity()
    eq = float(acct.get("equity") or 0.0)
    st = _load_state()
    prev = float(st.get("last_equity") or 0.0)

    # Guard: a failed account fetch (e.g. 429) returns equity=0. Treating that as a
    # real reading produces delta=-prev (garbage), poisons the RL reward, resets the
    # growth streak, and then a +eq spike on the next good read. Carry forward the
    # last known equity with a neutral delta instead.
    if not acct.get("ok") or eq <= 0:
        eq_known = prev if prev > 0 else 0.0
        row = {
            "ts_utc": _now_iso(),
            "source": source,
            "equity": eq_known,
            "delta": 0.0,
            "growth_pct": 0.0,
            "growth_vs_baseline": float(st.get("growth_vs_baseline") or 0.0),
            "objective": primary_objective(),
            "stale": True,
            **{k: st.get(k) for k in ("cash", "buying_power", "n_positions", "deployed_frac")},
        }
        return row

    baseline = float(st.get("baseline_equity") or eq or prev)
    if baseline <= 0 and eq > 0:
        baseline = eq

    delta = eq - prev if prev > 0 else 0.0
    growth_vs_baseline = ((eq / baseline) - 1.0) if baseline > 0 and eq > 0 else 0.0
    growth_pct = (delta / prev) if prev > 0 else 0.0

    row = {
        "ts_utc": _now_iso(),
        "source": source,
        "equity": eq,
        "delta": delta,
        "growth_pct": growth_pct,
        "growth_vs_baseline": growth_vs_baseline,
        "objective": primary_objective(),
        **{k: acct.get(k) for k in ("cash", "buying_power", "n_positions", "deployed_frac")},
    }
    _append_history(row)

    streak = int(st.get("growth_streak", 0))
    if delta > 0:
        streak += 1
    elif delta < 0:
        streak = 0

    st.update(
        {
            "last_equity": eq,
            "baseline_equity": baseline,
            "last_delta": delta,
            "last_growth_pct": growth_pct,
            "growth_vs_baseline": growth_vs_baseline,
            "growth_streak": streak,
            "updated_utc": row["ts_utc"],
            "objective": primary_objective(),
        }
    )
    _save_state(st)
    return row


def objective_reward(ctx: dict[str, Any]) -> float:
    """
    Scalar reward in [-1, 1] — primary signal is account equity growth.
    """
    eq = float(ctx.get("equity") or ctx.get("last_equity") or 0.0)
    delta = float(ctx.get("equity_delta") or ctx.get("last_delta") or 0.0)
    growth_pct = float(ctx.get("equity_growth_pct") or ctx.get("last_growth_pct") or 0.0)
    vs_base = float(ctx.get("growth_vs_baseline") or 0.0)
    deployed = float(ctx.get("deployed_frac") or 0.0)
    target_deploy = float(os.getenv("FORTRESS_TARGET_DEPLOY_FRAC", "0.88"))

    import math

    r = 0.0
    if eq > 0:
        r += math.tanh(growth_pct * 40.0) * 0.55
        r += math.tanh(delta / max(eq * 0.01, 50.0)) * 0.25
        r += math.tanh(vs_base * 8.0) * 0.20

    # Under-deployed capital slows objective progress — nudge toward deployment.
    if deployed < target_deploy - 0.12:
        r -= min(0.25, (target_deploy - deployed) * 0.20)
    elif deployed >= target_deploy - 0.05:
        r += 0.06

    alpha = ctx.get("alpha")
    if alpha is not None:
        r += float(alpha) * 4.0

    return max(-1.0, min(1.0, r))


def enrich_signals(sig: dict[str, Any]) -> dict[str, Any]:
    """Attach objective metrics to any signal bundle."""
    snap = record_equity_snapshot(source="enrich_signals")
    st = _load_state()
    out = dict(sig)
    out["objective"] = primary_objective()
    out["equity"] = float(snap.get("equity") or out.get("equity") or 0.0)
    out["equity_delta"] = float(snap.get("delta") or 0.0)
    out["equity_growth_pct"] = float(snap.get("growth_pct") or 0.0)
    out["growth_vs_baseline"] = float(snap.get("growth_vs_baseline") or 0.0)
    out["growth_streak"] = int(st.get("growth_streak") or 0)
    out["objective_reward"] = objective_reward(out)
    out["equity_flat_or_down"] = out["equity_delta"] <= 0.0
    return out


def should_aggress_self_modify(ctx: dict[str, Any]) -> bool:
    """Trigger code/param mutation when objective is not advancing."""
    if os.getenv("FREE_AGENT_ENABLED", "false").lower() in ("1", "true", "yes"):
        return True
    if os.getenv("AGI_ALWAYS_IMPROVE", "true").lower() in ("1", "true", "yes"):
        return True
    delta = float(ctx.get("equity_delta") or 0.0)
    vs_base = float(ctx.get("growth_vs_baseline") or 0.0)
    flat_thresh = float(os.getenv("AGI_FLAT_GROWTH_THRESH", "0.0005"))
    if delta <= 0 or vs_base < flat_thresh:
        return True
    alpha = ctx.get("alpha")
    if alpha is not None and float(alpha) < 0:
        return True
    return False
