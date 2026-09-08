"""Ultimate Learning Engine (ULE) — single learned LEA hub for the whole stack.

Everything connects through LogitEvidence Algebra (see analytics/vector_math.py
and math_catalog ``logit_evidence_algebra`` / ``ultimate_learning_engine``):

  Producers emit evidence only (p_i or Δℓ_i) — they do NOT pre-blend p*.
  skill_i ← clip( skill_i · (1 ± η · reward) )
  w_i     = softmax( skill / T )
  ℓ_fuse  = Σ_i w_i · logit(p_i)     # absolute channels
  ℓ*      = ℓ_fuse + Σ_j α_j · Δℓ_j  # relative tilts (overlay/cortex/regime)
  p*      = σ(ℓ*)

Never sizes alone — Kelly / heat stay in risk gates.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "intel" / "ule_state.json"
HIST_PATH = ROOT / "data" / "intel" / "ule_history.jsonl"

# Absolute evidence channels (have their own p_i)
_ABS = ("base", "hidden", "neural", "lstm", "crowd", "news", "event", "proven")
# Relative evidence (Δℓ applied after absolute LEA fuse)
_REL = ("overlay", "cortex", "regime")
_SUBSYSTEMS = _ABS + _REL

_DEFAULT_SKILL = {k: 1.0 for k in _SUBSYSTEMS}

# Last forward-pass active set (per thread) for honest credit_outcome
_LAST_ACTIVE = threading.local()
_ACTIVE_PATH = ROOT / "data" / "intel" / "ule_last_active.json"
_ACTIVE_LOCK = threading.Lock()


def _b(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def enabled() -> bool:
    return _b("USE_ULE", True)


def _load_state() -> dict[str, Any]:
    empty = {
        "skill": dict(_DEFAULT_SKILL),
        "n_updates": 0,
        "n_cycles": 0,
        "updated": 0.0,
        "last_cycle": {},
    }
    if not STATE_PATH.is_file():
        return empty
    try:
        doc = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return empty
    skill = dict(_DEFAULT_SKILL)
    skill.update({k: float(v) for k, v in (doc.get("skill") or {}).items() if k in skill})
    doc["skill"] = skill
    return doc


def _save_state(doc: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc["updated"] = time.time()
    STATE_PATH.write_text(json.dumps(doc, indent=2, default=float), encoding="utf-8")


def _append_hist(row: dict[str, Any]) -> None:
    HIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HIST_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=float) + "\n")


def skill_weights(state: dict[str, Any] | None = None) -> dict[str, float]:
    """Softmax over subsystem skills → LEA fusion weights."""
    st = state or _load_state()
    skill = {k: float((st.get("skill") or {}).get(k, 1.0)) for k in _SUBSYSTEMS}
    temp = max(0.15, _f("ULE_SOFTMAX_TEMP", 0.85))
    import math

    vals = [skill[k] / temp for k in _SUBSYSTEMS]
    m = max(vals)
    exps = [math.exp(v - m) for v in vals]
    s = sum(exps) or 1.0
    return {k: exps[i] / s for i, k in enumerate(_SUBSYSTEMS)}


def last_active() -> list[str]:
    return list(getattr(_LAST_ACTIVE, "active", []) or [])


def remember_active(symbol: str, active: list[str]) -> None:
    """Persist channels used on the last fortress/ULE forward for this ticker.

    credit_outcome runs in continuous_learn / trade_feedback (other processes),
    so thread-local last_active() was always empty there and only `base` learned.
    """
    sym = str(symbol or "").strip().upper()
    if not sym:
        return
    chans = [k for k in (active or []) if k in _SUBSYSTEMS]
    if not chans:
        return
    with _ACTIVE_LOCK:
        doc: dict[str, Any] = {}
        if _ACTIVE_PATH.is_file():
            try:
                doc = json.loads(_ACTIVE_PATH.read_text(encoding="utf-8"))
            except Exception:
                doc = {}
        if not isinstance(doc, dict):
            doc = {}
        doc[sym] = {"active": chans, "ts": time.time()}
        if len(doc) > 8000:
            oldest = sorted(doc.items(), key=lambda kv: float((kv[1] or {}).get("ts") or 0))[: len(doc) - 6000]
            for k, _ in oldest:
                doc.pop(k, None)
        _ACTIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _ACTIVE_PATH.write_text(json.dumps(doc, default=float), encoding="utf-8")


def active_for_symbol(symbol: str, *, max_age_sec: float = 14 * 86400) -> list[str]:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return []
    if not _ACTIVE_PATH.is_file():
        return []
    try:
        doc = json.loads(_ACTIVE_PATH.read_text(encoding="utf-8"))
        row = doc.get(sym) or {}
        ts = float(row.get("ts") or 0)
        if ts and (time.time() - ts) > float(max_age_sec):
            return []
        return [k for k in (row.get("active") or []) if k in _SUBSYSTEMS]
    except Exception:
        return []


def credit_outcome(
    *,
    success: bool,
    active: list[str] | None = None,
    reward: float = 0.0,
) -> dict[str, Any]:
    """Bump skill for subsystems that participated; decay quiet ones slightly."""
    if not enabled():
        return {"applied": False}
    st = _load_state()
    skill = {k: float((st.get("skill") or {}).get(k, 1.0)) for k in _SUBSYSTEMS}
    eta = _f("ULE_LEARN_RATE", 0.12)
    amp = min(0.35, abs(float(reward)) * 2.0 + eta)
    active_set = set(active if active is not None else last_active() or ["base", "hidden"])
    active_set &= set(_SUBSYSTEMS)
    if not active_set:
        active_set = {"base"}
    lo, hi = _f("ULE_SKILL_MIN", 0.35), _f("ULE_SKILL_MAX", 3.0)
    for k in _SUBSYSTEMS:
        if k in active_set:
            if success:
                skill[k] = min(hi, skill[k] * (1.0 + amp))
            else:
                skill[k] = max(lo, skill[k] * (1.0 - amp * 0.85))
        else:
            skill[k] = 0.98 * skill[k] + 0.02 * 1.0
    st["skill"] = skill
    st["n_updates"] = int(st.get("n_updates") or 0) + 1
    _save_state(st)
    _append_hist(
        {
            "ts": time.time(),
            "success": success,
            "reward": reward,
            "active": sorted(active_set),
            "skill": skill,
        }
    )
    return {"applied": True, "skill": skill, "weights": skill_weights(st)}


def _clip01(p: float) -> float:
    return float(max(0.01, min(0.99, p)))


def collect_evidence(
    symbol: str,
    p_base: float,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Gather absolute p_i and relative Δℓ_j — no fusion yet."""
    ctx = context or {}
    abs_p: dict[str, float] = {"base": _clip01(float(p_base))}
    abs_w_mult: dict[str, float] = {"base": 1.0}
    rel_dell: dict[str, float] = {}
    meta: dict[str, Any] = {"symbol": symbol.upper()}

    # Hidden pattern — raw p_pat (never pre-mixed into base)
    try:
        from analytics.hidden_pattern_learn import pattern_evidence

        ev = pattern_evidence(symbol)
        if ev.get("applied"):
            abs_p["hidden"] = _clip01(float(ev["p_pattern"]))
            abs_w_mult["hidden"] = float(max(0.05, min(1.0, float(ev.get("w_eff") or 0.2) * 2.5)))
            meta["hidden"] = ev
    except Exception as e:
        meta["hidden_err"] = str(e)[:80]

    # Neural ensemble p (from context or live infer)
    p_n = ctx.get("neural_p_up")
    if p_n is None:
        try:
            from online_learning.neural_ensemble import neural_ensemble_p_up, use_neural_ensemble

            if use_neural_ensemble():
                st = dict(ctx) if ctx else {}
                st.setdefault("p_up_base", abs_p["base"])
                p_n = neural_ensemble_p_up(symbol, st)
        except Exception:
            p_n = None
    if p_n is not None:
        abs_p["neural"] = _clip01(float(p_n))
        abs_w_mult["neural"] = 1.0
        meta["neural_p"] = abs_p["neural"]

    # LSTM head probability if caller passed it
    if ctx.get("lstm_p_up") is not None:
        abs_p["lstm"] = _clip01(float(ctx["lstm_p_up"]))
        abs_w_mult["lstm"] = 1.0
        meta["lstm_p"] = abs_p["lstm"]

    # Crowd pressure → factor_to_prob
    crowd = float(ctx.get("crowd_pressure") or 0.0)
    if abs(crowd) > 1e-6:
        try:
            from analytics.vector_math import factor_to_prob

            abs_p["crowd"] = _clip01(factor_to_prob(crowd, scale=_f("ULE_CROWD_SCALE", 1.0)))
        except Exception:
            abs_p["crowd"] = _clip01(0.5 + 0.5 * max(-1.0, min(1.0, crowd)))
        abs_w_mult["crowd"] = 1.0
        meta["crowd_pressure"] = crowd

    # News / transcript factor
    news = float(ctx.get("news_factor") or 0.0)
    if abs(news) > 1e-6:
        try:
            from analytics.vector_math import factor_to_prob

            abs_p["news"] = _clip01(factor_to_prob(news, scale=_f("ULE_NEWS_SCALE", 1.2)))
        except Exception:
            abs_p["news"] = _clip01(0.5 + 0.5 * max(-1.0, min(1.0, news)))
        abs_w_mult["news"] = 1.0
        meta["news_factor"] = news

    # Learned event-outcome p (print-gap model) — history + online SGD
    mom = float(ctx.get("mom_5d") or ctx.get("momentum_5d") or 0.0)
    r1 = float(ctx.get("ret_1d") or 0.0)
    vol = float(ctx.get("vol_20") or ctx.get("volatility") or 0.0)
    if _b("USE_EVENT_LEARN", True):
        try:
            from analytics.event_learn import predict_ticker

            ev = predict_ticker(symbol, mom_5d=mom, ret_1d=r1, vol_20=vol)
            if ev.get("applied") and float(ev.get("skill") or 0) > 0.05:
                abs_p["event"] = _clip01(float(ev["p_up"]))
                abs_w_mult["event"] = float(max(0.05, min(1.0, float(ev.get("skill") or 0.2))))
                meta["event_learn"] = {
                    "p_up": ev.get("p_up"),
                    "mag": ev.get("mag"),
                    "skill": ev.get("skill"),
                }
        except Exception as e:
            meta["event_err"] = str(e)[:80]

    # Peer cascade / 8-K / Form 4 — fires even if the ridge skill is still warming up.
    if _b("USE_EVENT_INGENUITY", True):
        try:
            from analytics.event_ingenuity import event_ingenuity_rank_boost

            dte_i = ctx.get("days_to_earnings") or ctx.get("dte")
            ing_b, ing_m = event_ingenuity_rank_boost(
                symbol,
                mom_5d=mom,
                ret_1d=r1,
                dte=int(dte_i) if dte_i is not None else None,
                sleeve=str(ctx.get("sleeve") or ""),
            )
            if abs(float(ing_b)) > 1e-6:
                if "event" in abs_p:
                    abs_p["event"] = _clip01(float(abs_p["event"]) + 0.28 * float(ing_b))
                else:
                    abs_p["event"] = _clip01(0.5 + 0.40 * float(ing_b))
                    abs_w_mult["event"] = 0.45
                meta["event_ingenuity"] = ing_m
        except Exception as e:
            meta["event_ingenuity_err"] = str(e)[:80]

    if _b("USE_PROVEN_ONLINE", True):
        try:
            from analytics.proven_online import evaluate as proven_eval

            mom = float(ctx.get("mom_5d") or ctx.get("momentum_5d") or 0.0)
            evp = proven_eval(
                symbol,
                p_up=float(abs_p.get("base") or p_base),
                exec_c=float(ctx.get("execution_confidence") or ctx.get("exec_conf") or 0.5),
                mom_5d=mom,
                rs_spy=float(ctx.get("rs_spy") or 1.0),
                hmm=float(ctx.get("bull_bear_score") or ctx.get("hmm") or 0.0),
                row=ctx.get("row"),
                sleeve=str(ctx.get("sleeve") or ""),
            )
            if not evp.get("skipped"):
                abs_p["proven"] = _clip01(float(evp.get("p_cal") or 0.5))
                abs_w_mult["proven"] = 1.15 if evp.get("ok") else 0.55
                meta["proven_online"] = {
                    "p_cal": evp.get("p_cal"),
                    "agree": evp.get("agree"),
                    "ok": evp.get("ok"),
                }
        except Exception as e:
            meta["proven_err"] = str(e)[:80]

    # Overlay / cortex — convert legacy Δp tilts → Δℓ at base operating point
    try:
        from analytics.vector_math import delta_p_to_delta_ell
        from self_modify.strategy_overlay import rank_tilt

        rsi = float(ctx.get("rsi_14", 50) or 50)
        tilt = float(rank_tilt(symbol, abs_p["base"], {"rsi_14": rsi}) or 0.0)
        if abs(tilt) > 1e-6:
            rel_dell["overlay"] = delta_p_to_delta_ell(abs_p["base"], tilt)
            meta["overlay_tilt_p"] = tilt
            meta["overlay_delta_ell"] = rel_dell["overlay"]
    except Exception:
        pass

    try:
        from analytics.vector_math import delta_p_to_delta_ell
        from cortex.integrate import cortex_rank_tilt

        rsi = float(ctx.get("rsi_14", 50) or 50)
        tilt = float(cortex_rank_tilt(symbol, abs_p["base"], {"rsi_14": rsi}) or 0.0)
        if abs(tilt) > 1e-6:
            rel_dell["cortex"] = delta_p_to_delta_ell(abs_p["base"], tilt)
            meta["cortex_tilt_p"] = tilt
            meta["cortex_delta_ell"] = rel_dell["cortex"]
    except Exception:
        pass

    # Regime / bull-bear score as z → Δℓ
    bb = ctx.get("bull_bear_score")
    if bb is not None and abs(float(bb)) > 1e-6:
        try:
            from analytics.vector_math import z_to_delta_ell

            rel_dell["regime"] = z_to_delta_ell(float(bb), scale=_f("ULE_REGIME_ELL_SCALE", 0.25))
            meta["bull_bear_score"] = float(bb)
        except Exception:
            pass

    return {
        "abs_p": abs_p,
        "abs_w_mult": abs_w_mult,
        "rel_dell": rel_dell,
        "meta": meta,
    }


def apply_to_p_up(
    symbol: str,
    p_base: float,
    *,
    context: dict[str, Any] | None = None,
) -> tuple[float, dict[str, Any]]:
    """Main live path: LEA-fuse absolute evidence, then add relative Δℓ tilts."""
    out_meta: dict[str, Any] = {"ule": True, "applied": False, "math": "LEA"}
    if not enabled():
        return float(p_base), {**out_meta, "enabled": False}

    bundle = collect_evidence(symbol, p_base, context=context)
    abs_p: dict[str, float] = bundle["abs_p"]
    abs_w_mult: dict[str, float] = bundle["abs_w_mult"]
    rel_dell: dict[str, float] = bundle["rel_dell"]
    out_meta.update(bundle.get("meta") or {})

    w = skill_weights()
    use_abs = [k for k in _ABS if k in abs_p]
    if "base" not in use_abs:
        use_abs.insert(0, "base")
        abs_p["base"] = _clip01(float(p_base))

    ww = [max(1e-6, float(w.get(k, 0.0)) * float(abs_w_mult.get(k, 1.0))) for k in use_abs]
    pp = [float(abs_p[k]) for k in use_abs]

    try:
        from analytics.vector_math import apply_logit_tilt, fuse_probs, lea_enabled, logit

        if lea_enabled():
            p_star = fuse_probs(pp, ww)
            # Relative channels: skill-scaled Δℓ after absolute fuse
            w_mean = sum(w.values()) / max(1, len(w))
            for name in _REL:
                if name not in rel_dell:
                    continue
                scale = float(w.get(name, 0.0)) / max(1e-6, w_mean)
                # Bound relative influence so one tilt can't dominate
                scale = min(_f("ULE_REL_TILT_CAP", 1.8), max(0.15, scale))
                p_star = apply_logit_tilt(p_star, scale * float(rel_dell[name]))
                out_meta.setdefault("rel_applied", []).append(name)
            # Track logit for diagnostics
            out_meta["logit_star"] = float(logit(p_star))
        else:
            s = sum(ww) or 1.0
            p_star = sum(wi / s * pi for wi, pi in zip(ww, pp))
            for name in _REL:
                if name in rel_dell:
                    # approximate: Δp ≈ Δℓ · p(1-p) near mid
                    p_star = _clip01(p_star + 0.25 * float(rel_dell[name]) * float(w.get(name, 0.2)))
                    out_meta.setdefault("rel_applied", []).append(name)
    except Exception as e:
        s = sum(ww) or 1.0
        p_star = sum(wi / s * pi for wi, pi in zip(ww, pp))
        out_meta["fuse_err"] = str(e)[:80]

    active = list(use_abs) + [n for n in _REL if n in rel_dell]
    _LAST_ACTIVE.active = active
    try:
        remember_active(symbol, active)
    except Exception:
        pass
    p_star = _clip01(float(p_star))
    out_meta.update(
        {
            "applied": True,
            "active": active,
            "weights": {k: float(w.get(k, 0)) for k in active},
            "abs_w_mult": {k: float(abs_w_mult.get(k, 1)) for k in use_abs},
            "probs": {k: float(abs_p[k]) for k in use_abs},
            "rel_dell": {k: float(rel_dell[k]) for k in rel_dell},
            "p_before": float(p_base),
            "p_after": p_star,
        }
    )
    return p_star, out_meta


def ingest_paper_sim_history(*, limit: int = 200) -> dict[str, Any]:
    """Train ULE from latest paper_sim report forward returns (historical self-play)."""
    from online_learning.trade_feedback import learn_from_realized_trade

    n_ok = 0
    n_skip = 0
    try:
        from analytics.paper_report import latest_valid_report

        max_age = _f("ULE_REPORT_MAX_AGE_HOURS", 8760.0)
        _path, doc = latest_valid_report(
            min_rows=1,
            require_usable=False,
            max_age_hours=max_age,
        )
    except Exception as e:
        return {"ok": False, "error": f"report: {e}"}
    if not doc:
        return {"ok": False, "error": "no_paper_report"}

    rows = list(doc.get("rows") or doc.get("results") or [])
    scored = []
    for r in rows:
        if not isinstance(r, dict) or r.get("skipped"):
            continue
        sym = str(r.get("ticker") or r.get("symbol") or "").upper()
        if not sym:
            continue
        ret = r.get("fwd_ret")
        if ret is None:
            ret = r.get("fwd_1d_return")
        if ret is None:
            ret = r.get("fwd_5d_return")
        if ret is None:
            ret = r.get("realized_return")
        if ret is None:
            ret = r.get("ret")
        if ret is None:
            n_skip += 1
            continue
        try:
            ret_f = float(ret)
        except (TypeError, ValueError):
            n_skip += 1
            continue
        sig = str(r.get("signal") or r.get("decision") or r.get("action") or "BUY").upper()
        side = "SHORT" if sig in ("SELL", "DOWN", "SHORT") else "LONG"
        if sig in ("HOLD", "FLAT", "NONE", ""):
            try:
                p = float(r.get("p_up") or 0.5)
                if "chance_pct" in r and r.get("p_up") is None:
                    p = float(r["chance_pct"]) / 100.0
                side = "LONG" if p >= 0.5 else "SHORT"
            except (TypeError, ValueError):
                side = "LONG"
        scored.append((sym, side, ret_f, r))

    scored.sort(key=lambda x: abs(x[2]), reverse=True)
    _prev_neural = os.environ.get("USE_NEURAL_ENSEMBLE")
    if _b("ULE_HIST_SKIP_NEURAL", True):
        os.environ["USE_NEURAL_ENSEMBLE"] = "false"
    try:
        for sym, side, ret_f, row in scored[: max(1, limit)]:
            try:
                # Seed last_active from report fields when available
                act = ["base"]
                if row.get("hidden_pattern") or row.get("pattern_score"):
                    act.append("hidden")
                if row.get("neural_p_up") is not None:
                    act.append("neural")
                _LAST_ACTIVE.active = act
                learn_from_realized_trade(
                    sym,
                    side,
                    ret_f,
                    source="ule_paper_hist",
                    bars_held=int(row.get("hold_days") or os.getenv("HOLD_DAYS_DEFAULT", "5")),
                )
                n_ok += 1
            except Exception:
                n_skip += 1
    finally:
        if _prev_neural is None:
            os.environ.pop("USE_NEURAL_ENSEMBLE", None)
        else:
            os.environ["USE_NEURAL_ENSEMBLE"] = _prev_neural
    return {"ok": True, "learned": n_ok, "skipped": n_skip, "report_rows": len(rows)}


def discover_and_code() -> dict[str, Any]:
    """Subtle-tie discovery → write detector modules (never deletes old)."""
    if not _b("ULE_CODEGEN", True):
        return {"enabled": False}
    try:
        from analytics.pattern_code_evolver import discover_and_emit

        return discover_and_emit()
    except Exception as e:
        return {"error": str(e)[:160]}


def run_cycle(
    *,
    hist_limit: int | None = None,
    do_codegen: bool | None = None,
    do_pattern_scan: bool | None = None,
) -> dict[str, Any]:
    """One full ULE cycle: history → credit → discover/codegen → optional anomaly scan."""
    if not enabled():
        return {"ok": False, "reason": "USE_ULE=false"}

    t0 = time.time()
    hist_limit = hist_limit if hist_limit is not None else int(_f("ULE_HIST_LIMIT", 150))
    do_codegen = _b("ULE_CODEGEN", True) if do_codegen is None else do_codegen
    do_pattern_scan = _b("ULE_PATTERN_SCAN", True) if do_pattern_scan is None else do_pattern_scan

    out: dict[str, Any] = {"ts": t0}
    out["history"] = ingest_paper_sim_history(limit=hist_limit)
    if do_codegen:
        out["codegen"] = discover_and_code()
    if do_pattern_scan:
        try:
            from analytics.hidden_pattern_anomaly import run_scan_cycle

            out["pattern_scan"] = run_scan_cycle()
        except Exception as e:
            out["pattern_scan"] = {"error": str(e)[:120]}

    st = _load_state()
    st["n_cycles"] = int(st.get("n_cycles") or 0) + 1
    st["last_cycle"] = {
        "ts": time.time(),
        "elapsed_sec": time.time() - t0,
        "history_learned": (out.get("history") or {}).get("learned"),
        "codegen_written": (out.get("codegen") or {}).get("written"),
    }
    _save_state(st)
    out["skill"] = st.get("skill")
    out["weights"] = skill_weights(st)
    out["ok"] = True
    out["elapsed_sec"] = time.time() - t0
    return out
