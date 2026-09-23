"""Proven factors + textbook online combiners → tight picks.

Most-replicated, most-used edges (long-only):

  • Cross-section / TS momentum (Jegadeesh–Titman, Moskowitz–Ooi–Pedersen)
  • Residual / idiosyncratic momentum (Blitz–Huij–Martens 2011)
  • Trend (SMA/EMA — what desks actually run)
  • Volume-confirmed momentum
  • Turtle Donchian
  • Execution confidence (don't pay a bad print)
  • Regime (HMM) as a veto, not a chase
  • Event / peer-dump veto (public clocks)
  • Quality tape — do not chase RSI 70+
  • Next-gen ridge student on the vote vector (deploys only if OOS IC > 0.02)

Online combiners (the approved ones, not novelty):

  • Hedge / multiplicative weights (Freund & Schapire 1997)
  • Beta–Bernoulli skill (Thompson mean) per expert
  • Online Platt / logit SGD on the fused p
  • Feeds ULE as an absolute evidence channel

Tight pick: CORE experts must agree. Does not flatten greens. Does not
require 1d/5d/20d heads to agree (horizon-independent stays). HFT skipped.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "intel" / "proven_online_state.json"

# Desk-order: most replicated / most used first. Priors are Hedge starting weights.
EXPERTS: tuple[str, ...] = (
    "model",
    "tsmom",
    "trend",
    "exec",
    "event_ok",
    "vol_mom",
    "donchian",
    "hmm",
    "value",
    "quality_tape",
    "resid_mom",
)
CORE_EXPERTS: tuple[str, ...] = ("model", "tsmom", "exec", "event_ok", "hmm")
_PRIOR_W: dict[str, float] = {
    "model": 1.45,
    "tsmom": 1.40,
    "trend": 1.30,
    "exec": 1.35,
    "event_ok": 1.25,
    "vol_mom": 1.10,
    "donchian": 1.05,
    "hmm": 0.95,
    "value": 1.10,
    "quality_tape": 1.05,
    "resid_mom": 1.30,
}


def _b(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def enabled() -> bool:
    return _b("USE_PROVEN_ONLINE", True)


def tight_enabled() -> bool:
    return enabled() and _b("USE_TIGHT_PICKS", True)


def _clip01(p: float) -> float:
    return float(max(0.01, min(0.99, p)))


def _sigmoid(z: float) -> float:
    z = max(-20.0, min(20.0, float(z)))
    return 1.0 / (1.0 + math.exp(-z))


def _logit(p: float) -> float:
    x = _clip01(p)
    return math.log(x / (1.0 - x))


def _row_f(row: Any, *keys: str, default: float = 0.0) -> float:
    if row is None:
        return default
    getter = row.get if isinstance(row, dict) else getattr(row, "get", None)
    if getter is None:
        try:
            getter = dict(row).get
        except Exception:
            return default
    for k in keys:
        v = getter(k)
        if v is None or v == "":
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return default


_LAST_VOTES: dict[str, dict[str, int]] = {}


def _remember_votes(ticker: str, votes: dict[str, int]) -> None:
    _LAST_VOTES[str(ticker).strip().upper()] = {k: int(votes.get(k) or 0) for k in EXPERTS}


def default_state() -> dict[str, Any]:
    return {
        "version": 1,
        "w": dict(_PRIOR_W),
        "alpha": {k: 2.0 for k in EXPERTS},  # Beta prior
        "beta": {k: 2.0 for k in EXPERTS},
        "platt_a": 0.0,
        "platt_b": 1.0,
        "n_updates": 0,
        "last_votes": {},
        "updated": 0.0,
    }


def load_state() -> dict[str, Any]:
    st = default_state()
    if not STATE_PATH.is_file():
        return st
    try:
        doc = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return st
    if not isinstance(doc, dict):
        return st
    w = dict(_PRIOR_W)
    w.update({k: float(v) for k, v in (doc.get("w") or {}).items() if k in w})
    st["w"] = w
    for key in ("alpha", "beta"):
        merged = dict(st[key])
        merged.update({k: float(v) for k, v in (doc.get(key) or {}).items() if k in merged})
        st[key] = merged
    st["platt_a"] = float(doc.get("platt_a") or 0.0)
    st["platt_b"] = float(doc.get("platt_b") or 1.0)
    st["n_updates"] = int(doc.get("n_updates") or 0)
    lv = doc.get("last_votes")
    st["last_votes"] = lv if isinstance(lv, dict) else {}
    return st


def save_state(st: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    st["updated"] = time.time()
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(st, indent=2, default=float), encoding="utf-8")
    os.replace(tmp, STATE_PATH)


def expert_votes(
    *,
    p_up: float,
    exec_c: float = 0.5,
    mom_5d: float = 0.0,
    rs_spy: float = 1.0,
    hmm: float = 0.0,
    row: Any = None,
    event_signed: float | None = None,
) -> dict[str, int]:
    """+1 / 0 / −1. 0 is abstain (missing tape), never a fake yes."""
    v: dict[str, int] = {k: 0 for k in EXPERTS}
    p = float(p_up)
    floor = _f("TIGHT_PICK_MIN_P", 0.64)
    v["model"] = 1 if p >= floor else (-1 if p < 0.48 else 0)
    if mom_5d > 0.0 and float(rs_spy) >= 1.0:
        v["tsmom"] = 1
    elif mom_5d < -0.015 or float(rs_spy) < 0.97:
        v["tsmom"] = -1
    golden = _row_f(row, "sma_golden_cross")
    ema = _row_f(row, "ema_12_over_26", default=1.0)
    macd = _row_f(row, "macd_hist")
    if golden >= 0.5 or ema > 1.002 or macd > 0:
        v["trend"] = 1
    elif ema < 0.995 or macd < 0:
        v["trend"] = -1
    exec_floor = _f("TIGHT_PICK_MIN_EXEC", 0.62)
    v["exec"] = 1 if float(exec_c) >= exec_floor else (-1 if float(exec_c) < 0.50 else 0)
    signed = event_signed
    if signed is not None:
        if float(signed) <= -0.03:
            v["event_ok"] = -1
        elif float(signed) >= 0:
            v["event_ok"] = 1
        else:
            v["event_ok"] = 0
    else:
        v["event_ok"] = 1  # no dump in the book → don't veto
    vcm = _row_f(row, "vol_confirmed_mom", "price_roc_5")
    if vcm > 0:
        v["vol_mom"] = 1
    elif vcm < 0:
        v["vol_mom"] = -1
    don = _row_f(row, "donchian_pos_55", default=0.5)
    if don >= 0.65:
        v["donchian"] = 1
    elif don <= 0.35:
        v["donchian"] = -1
    if hmm > 0.02:
        v["hmm"] = 1
    elif hmm < -0.02:
        v["hmm"] = -1
    bb_os = _row_f(row, "bb_oversold")
    rsi_os = _row_f(row, "rsi_oversold")
    if bb_os >= 0.5 or rsi_os >= 0.5:
        v["value"] = 1
    rsi_ob = _row_f(row, "rsi_overbought")
    bb_ob = _row_f(row, "bb_overbought")
    if rsi_ob >= 0.5 or bb_ob >= 0.5:
        v["quality_tape"] = -1  # chase veto
        if v["value"] == 0:
            v["value"] = -1
    elif rsi_ob == 0 and bb_ob == 0:
        v["quality_tape"] = 1
    rm = _row_f(row, "resid_mom_12_1", "resid_mom")
    if rm > 0.02:
        v["resid_mom"] = 1
    elif rm < -0.02:
        v["resid_mom"] = -1
    return v


def _event_signed_for(ticker: str) -> float:
    try:
        from analytics.event_ingenuity import load_book_gaps, peer_universe, score_peer_cascade

        book = load_book_gaps()
        peers = peer_universe(ticker, cap=12)
        gaps = [book[p] for p in peers if p in book]
        return float(score_peer_cascade(gaps).get("peer_gap_signed") or 0.0)
    except Exception:
        return 0.0


def hedge_fuse(votes: dict[str, int], st: dict[str, Any] | None = None) -> tuple[float, dict[str, float]]:
    """Multiplicative-weights expert advice → probability.

    Also mixes in Thompson mean α/(α+β) so winners keep share.
    """
    st = st or load_state()
    w = {k: max(1e-6, float((st.get("w") or {}).get(k, _PRIOR_W.get(k, 1.0)))) for k in EXPERTS}
    alpha = st.get("alpha") or {}
    beta = st.get("beta") or {}
    num = 0.0
    den = 0.0
    used: dict[str, float] = {}
    for k in EXPERTS:
        vote = int(votes.get(k) or 0)
        if vote == 0:
            continue
        thom = float(alpha.get(k, 2.0)) / max(1e-9, float(alpha.get(k, 2.0)) + float(beta.get(k, 2.0)))
        ww = w[k] * (0.55 + 0.90 * thom)
        num += ww * float(vote)
        den += ww
        used[k] = ww
    if den <= 1e-12:
        return 0.5, used
    # Map mean vote in [-1,1] through a scaled sigmoid (Hedge advice).
    z = 1.35 * (num / den)
    return _clip01(_sigmoid(z)), used


def platt_calibrate(p_raw: float, st: dict[str, Any] | None = None) -> float:
    st = st or load_state()
    a = float(st.get("platt_a") or 0.0)
    b = float(st.get("platt_b") or 1.0)
    return _clip01(_sigmoid(a + b * _logit(p_raw)))


def evaluate(
    ticker: str,
    *,
    p_up: float,
    exec_c: float = 0.5,
    mom_5d: float = 0.0,
    rs_spy: float = 1.0,
    hmm: float = 0.0,
    row: Any = None,
    sleeve: str | None = None,
    use_live_events: bool = True,
    st: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Votes + Hedge p + tight-pick decision. HFT skipped."""
    out: dict[str, Any] = {
        "ok": False,
        "p_hedge": 0.5,
        "p_cal": 0.5,
        "boost": 0.0,
        "agree": 0,
        "need": 0,
        "votes": {},
        "skipped": None,
    }
    if not enabled() or str(sleeve or "").lower() == "hft":
        out["skipped"] = "disabled_or_hft"
        return out
    signed = _event_signed_for(ticker) if use_live_events else 0.0
    votes = expert_votes(
        p_up=p_up,
        exec_c=exec_c,
        mom_5d=mom_5d,
        rs_spy=rs_spy,
        hmm=hmm,
        row=row,
        event_signed=signed,
    )
    st = st if st is not None else load_state()
    p_h, used = hedge_fuse(votes, st)
    p_c = platt_calibrate(p_h, st)
    try:
        from analytics.gen_learn import mix_p

        p_c, gmeta = mix_p(
            p_c, votes, row=row, p_up=p_up, mom_5d=mom_5d, rs_spy=rs_spy
        )
    except Exception:
        gmeta = {}
    core_yes = sum(1 for k in CORE_EXPERTS if int(votes.get(k) or 0) == 1)
    core_no = sum(1 for k in CORE_EXPERTS if int(votes.get(k) or 0) == -1)
    need = _i("TIGHT_PICK_MIN_AGREE", 4)
    p_floor = _f("TIGHT_PICK_MIN_P", 0.64)
    hedge_floor = _f("TIGHT_PICK_MIN_HEDGE", 0.58)
    chase = int(votes.get("quality_tape") or 0) < 0
    ok = (
        core_yes >= need
        and core_no == 0
        and float(p_up) >= p_floor
        and p_c >= hedge_floor
        and not chase
    )
    if p_c != p_c or p_c in (float("inf"), float("-inf")):
        p_c = 0.5
    boost = max(-1.0, min(1.0, (p_c - 0.5) * 2.0))
    if boost != boost:
        boost = 0.0
    _remember_votes(ticker, votes)
    out.update(
        {
            "ok": bool(ok),
            "p_hedge": round(p_h, 6),
            "p_cal": round(p_c, 6),
            "boost": round(boost, 6),
            "agree": int(core_yes),
            "need": int(need),
            "core_no": int(core_no),
            "votes": votes,
            "used_w": {k: round(v, 4) for k, v in used.items()},
            "event_signed": round(float(signed), 5),
            "chase": bool(chase),
            "gen": gmeta,
        }
    )
    return out


def tight_pick(
    ticker: str,
    *,
    p_up: float,
    exec_c: float = 0.5,
    mom_5d: float = 0.0,
    rs_spy: float = 1.0,
    hmm: float = 0.0,
    row: Any = None,
    sleeve: str | None = None,
    force_stick: bool = False,
    use_live_events: bool = True,
) -> dict[str, Any]:
    """Gate for NEW buys. STICK/PRED force still allowed (pre-print SBUX)."""
    ev = evaluate(
        ticker,
        p_up=p_up,
        exec_c=exec_c,
        mom_5d=mom_5d,
        rs_spy=rs_spy,
        hmm=hmm,
        row=row,
        sleeve=sleeve,
        use_live_events=use_live_events,
    )
    if force_stick:
        ev["ok"] = True
        ev["forced"] = "stick"
        return ev
    if not tight_enabled():
        ev["ok"] = True
        ev["skipped"] = ev.get("skipped") or "tight_off"
        return ev
    return ev


def proven_online_rank_boost(
    ticker: str,
    *,
    p_up: float,
    exec_c: float = 0.5,
    mom_5d: float = 0.0,
    rs_spy: float = 1.0,
    hmm: float = 0.0,
    row: Any = None,
    sleeve: str | None = None,
) -> tuple[float, dict[str, Any]]:
    ev = evaluate(
        ticker,
        p_up=p_up,
        exec_c=exec_c,
        mom_5d=mom_5d,
        rs_spy=rs_spy,
        hmm=hmm,
        row=row,
        sleeve=sleeve,
    )
    if ev.get("skipped"):
        return 0.0, ev
    return float(ev.get("boost") or 0.0), ev


def credit_outcome(
    ticker: str,
    realized_return: float,
    *,
    side: str = "LONG",
    persist: bool = True,
    st: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Hedge MW + Beta update + Platt SGD. Call from trade_feedback."""
    if not enabled():
        return {"applied": False, "reason": "disabled"}
    st = st if st is not None else load_state()
    votes = _LAST_VOTES.get(str(ticker).strip().upper()) or (st.get("last_votes") or {}).get(
        str(ticker).strip().upper()
    ) or {}
    if not votes:
        return {"applied": False, "reason": "no_votes"}
    ret = float(realized_return)
    if str(side or "LONG").upper() != "LONG":
        ret = -ret
    win = ret > 0.0
    eta = _f("PROVEN_ONLINE_ETA", 0.08)
    lr = _f("PROVEN_ONLINE_PLATT_LR", 0.04)
    w = dict(st.get("w") or _PRIOR_W)
    alpha = dict(st.get("alpha") or {})
    beta = dict(st.get("beta") or {})
    for k in EXPERTS:
        vote = int(votes.get(k) or 0)
        if vote == 0:
            continue
        # Hedge: raise weight when the expert's sign matched the realized move.
        agree = 1.0 if (vote > 0 and win) or (vote < 0 and not win) else -1.0
        w[k] = float(max(0.08, min(6.0, w[k] * math.exp(eta * agree))))
        if agree > 0:
            alpha[k] = float(alpha.get(k, 2.0)) + 1.0
        else:
            beta[k] = float(beta.get(k, 2.0)) + 1.0
    p_h, _ = hedge_fuse({k: int(votes.get(k) or 0) for k in EXPERTS}, {"w": w, "alpha": alpha, "beta": beta})
    y = 1.0 if win else 0.0
    # Online Platt: one SGD step on log-loss of σ(a + b logit(p)).
    a = float(st.get("platt_a") or 0.0)
    b = float(st.get("platt_b") or 1.0)
    z = a + b * _logit(p_h)
    p_hat = _sigmoid(z)
    grad = p_hat - y
    a -= lr * grad
    b -= lr * grad * _logit(p_h)
    b = max(0.25, min(3.0, b))
    a = max(-2.0, min(2.0, a))
    st["w"] = w
    st["alpha"] = alpha
    st["beta"] = beta
    st["platt_a"] = a
    st["platt_b"] = b
    st["n_updates"] = int(st.get("n_updates") or 0) + 1
    try:
        from analytics.gen_learn import online_update as gen_online

        gen_online(votes, ret, p_up=p_h, persist=persist)
    except Exception:
        pass
    if persist:
        save_state(st)
    return {"applied": True, "n_updates": st["n_updates"], "win": win, "p_hedge": p_h, "st": st}
