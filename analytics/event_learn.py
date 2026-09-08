"""Self-adjusting event-outcome learner for the whole universe.

Does not predict unpublished trial/earnings *results*. It learns, from history:

  • how large the next 1d move is around a public clock (earnings DTE, trial/guidance heat)
  • a directional tilt from pre-print tape + exhaustion

Walk-forward ridge + online SGD. If out-of-sample IC dies, skill → 0 so rank is not hurt.
Weights keep moving after every realized print / closed trade.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "intel" / "event_learn_state.json"
REPORT_PATH = ROOT / "data" / "intel" / "event_learn_report.json"

# Locked feature set — do not delete names; redesign zeros them via `active`.
FEATURE_NAMES: tuple[str, ...] = (
    "bias",
    "dte_0",
    "dte_1",
    "dte_2_5",
    "dte_le_10",
    "dse_0",
    "dse_1",
    "in_window",
    "hour_bmo",
    "hour_amc",
    "hist_abs_1d",
    "hist_abs_5d",
    "log_n_prints",
    "cal_pre",
    "live_binary",
    "guidance",
    "conference",
    "exhaustion",
    "mom_5d",
    "ret_1d",
    "vol_20",
    "proximity",
    "is_event_day",
    # Ingenious public tells — appended, never replacing the clock set.
    "peer_gap_signed",
    "peer_gap_abs",
    "peer_printed",
    "crowding",
    "eightk_burst",
    "silence",
    "form4_sell",
    "form4_buy",
    "vol_z5",
    "range_expand",
    "link_peer_gap",
    "straddle_proxy",
)

_DIR_PRIOR = {
    "bias": 0.0,
    "mom_5d": 0.85,
    "ret_1d": 0.25,
    "exhaustion": -0.45,
    "cal_pre": 0.20,
    "live_binary": 0.10,
    "hour_bmo": -0.08,
    "dte_0": 0.0,
    "proximity": 0.05,
    "peer_gap_signed": 0.95,
    "form4_sell": -0.40,
    "form4_buy": 0.15,
    "link_peer_gap": 0.55,
    "eightk_burst": 0.08,
}
_MAG_PRIOR = {
    "bias": 0.008,
    "hist_abs_1d": 0.85,
    "hist_abs_5d": 0.25,
    "dte_0": 0.018,
    "dte_1": 0.012,
    "dse_0": 0.010,
    "in_window": 0.006,
    "live_binary": 0.012,
    "cal_pre": 0.008,
    "vol_20": 0.15,
    "is_event_day": 0.015,
    "proximity": 0.010,
    "peer_gap_abs": 0.55,
    "peer_printed": 0.008,
    "crowding": 0.010,
    "eightk_burst": 0.006,
    "silence": 0.008,
    "vol_z5": 0.12,
    "range_expand": 0.08,
    "straddle_proxy": 0.70,
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


def enabled() -> bool:
    return _b("USE_EVENT_LEARN", True)


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _sigmoid(z: float) -> float:
    z = max(-40.0, min(40.0, float(z)))
    return 1.0 / (1.0 + math.exp(-z))


def _i(val: Any) -> int | None:
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


@dataclass
class EventSample:
    symbol: str
    as_of: date
    feats: dict[str, float]
    y_sign: float  # +1 up / -1 down
    y_abs: float
    is_event: bool = True


def backfill_peer_feats(samples: list[EventSample]) -> int:
    """Causal peer-print features from other names that already printed.

    Same-morning sympathy (WMT BMO → COST) is live-only (session gaps).
    History uses peers whose print date is 1–5 days *before* as_of.
    """
    if not samples:
        return 0
    try:
        from analytics.event_ingenuity import HARD_PEERS, industry_id, score_crowding, score_peer_cascade, straddle_proxy
    except Exception:
        return 0
    events = [s for s in samples if s.is_event]
    by_sym: dict[str, list[tuple[date, float]]] = {}
    earn_dates: dict[str, list[date]] = {}
    for s in events:
        signed = float(s.y_sign) * float(s.y_abs)
        by_sym.setdefault(s.symbol, []).append((s.as_of, signed))
        earn_dates.setdefault(s.symbol, []).append(s.as_of)
    n = 0
    for s in samples:
        peers = [p for p in HARD_PEERS.get(s.symbol, ()) if p != s.symbol]
        iid = industry_id(s.symbol)
        if iid and iid != "unclassified":
            for other in list(by_sym.keys()):
                if other == s.symbol:
                    continue
                if industry_id(other) == iid and other not in peers:
                    peers.append(other)
                if len(peers) >= 12:
                    break
        gaps: list[float] = []
        n_crowd = 0
        for p in peers:
            for d, g in by_sym.get(p, []):
                lag = (s.as_of - d).days
                if 1 <= lag <= 5:
                    gaps.append(g)
            for d in earn_dates.get(p, []):
                if abs((d - s.as_of).days) <= 2:
                    n_crowd += 1
        extra = score_peer_cascade(gaps)
        s.feats["peer_gap_signed"] = float(extra.get("peer_gap_signed") or 0.0)
        s.feats["peer_gap_abs"] = float(extra.get("peer_gap_abs") or 0.0)
        s.feats["peer_printed"] = float(extra.get("peer_printed") or 0.0)
        s.feats["crowding"] = float(score_crowding(n_crowd))
        hist = float(s.feats.get("hist_abs_1d") or s.feats.get("hist_abs_5d") or 0.0)
        dte = 1 if float(s.feats.get("dte_1") or 0) >= 0.5 else (0 if float(s.feats.get("dte_0") or 0) >= 0.5 else 5)
        s.feats["straddle_proxy"] = float(straddle_proxy(hist, dte if s.is_event else 20))
        if extra.get("peer_printed"):
            n += 1
    return n


def empty_feats() -> dict[str, float]:
    return {k: (1.0 if k == "bias" else 0.0) for k in FEATURE_NAMES}


def featurize(
    *,
    dte: Any = None,
    dse: Any = None,
    in_window: bool = False,
    hour: str | None = None,
    hist_abs_1d: float | None = None,
    hist_abs_5d: float | None = None,
    n_prints: float | None = None,
    cal_pre: float = 0.0,
    live_binary: float = 0.0,
    guidance: float = 0.0,
    conference: float = 0.0,
    exhaustion: float = 0.0,
    mom_5d: float = 0.0,
    ret_1d: float = 0.0,
    vol_20: float = 0.0,
    is_event_day: bool = False,
    extra: dict[str, float] | None = None,
) -> dict[str, float]:
    """Public-clock + tape features. No unpublished result fields."""
    f = empty_feats()
    dte_i = _i(dte)
    dse_i = _i(dse)
    if dte_i == 0:
        f["dte_0"] = 1.0
    elif dte_i == 1:
        f["dte_1"] = 1.0
    elif dte_i is not None and 2 <= dte_i <= 5:
        f["dte_2_5"] = 1.0
    if dte_i is not None and 0 <= dte_i <= 10:
        f["dte_le_10"] = 1.0
    if dse_i == 0:
        f["dse_0"] = 1.0
    elif dse_i == 1:
        f["dse_1"] = 1.0
    f["in_window"] = 1.0 if in_window or (dte_i is not None and 0 <= dte_i <= 5) else 0.0
    h = str(hour or "").strip().lower()
    f["hour_bmo"] = 1.0 if h == "bmo" else 0.0
    f["hour_amc"] = 1.0 if h == "amc" else 0.0
    f["hist_abs_1d"] = float(hist_abs_1d or 0.0)
    f["hist_abs_5d"] = float(hist_abs_5d or 0.0)
    f["log_n_prints"] = math.log1p(max(0.0, float(n_prints or 0.0)))
    f["cal_pre"] = max(0.0, min(1.0, float(cal_pre or 0.0)))
    f["live_binary"] = max(0.0, min(1.0, float(live_binary or 0.0)))
    f["guidance"] = max(0.0, min(1.0, float(guidance or 0.0)))
    f["conference"] = max(0.0, min(1.0, float(conference or 0.0)))
    f["exhaustion"] = max(0.0, min(1.0, float(exhaustion or 0.0)))
    f["mom_5d"] = max(-0.5, min(0.5, float(mom_5d or 0.0)))
    f["ret_1d"] = max(-0.3, min(0.3, float(ret_1d or 0.0)))
    f["vol_20"] = max(0.0, min(0.2, float(vol_20 or 0.0)))
    if dte_i is not None:
        f["proximity"] = float(math.exp(-abs(dte_i) / 5.0))
    elif dse_i is not None and 0 <= dse_i <= 5:
        f["proximity"] = float(math.exp(-dse_i / 5.0))
    f["is_event_day"] = 1.0 if is_event_day or dte_i == 0 else 0.0
    f["bias"] = 1.0
    if extra:
        for k, v in extra.items():
            if k in f:
                try:
                    f[k] = float(v)
                except (TypeError, ValueError):
                    pass
    return f


def vectorize(feats: dict[str, float], active: list[str] | None = None) -> np.ndarray:
    names = active or list(FEATURE_NAMES)
    return np.asarray([float(feats.get(k, 0.0)) for k in names], dtype=np.float64)


def _prior_vec(prior: dict[str, float], names: list[str]) -> np.ndarray:
    return np.asarray([float(prior.get(k, 0.0)) for k in names], dtype=np.float64)


def default_state() -> dict[str, Any]:
    names = list(FEATURE_NAMES)
    return {
        "version": 1,
        "active": names,
        "w_dir": {k: float(_DIR_PRIOR.get(k, 0.0)) for k in names},
        "w_mag": {k: float(_MAG_PRIOR.get(k, 0.0)) for k in names},
        "skill": 0.35,  # modest until walk-forward proves it
        "oos_ic": None,
        "oos_acc": None,
        "baseline_mae": None,
        "model_mae": None,
        "n_samples": 0,
        "n_updates": 0,
        "n_redesign": 0,
        "dropped": [],
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
    st.update({k: doc[k] for k in doc if k in st or k in ("w_dir", "w_mag", "active", "dropped")})
    for key in ("w_dir", "w_mag"):
        merged = dict(st[key])
        merged.update({k: float(v) for k, v in (doc.get(key) or {}).items()})
        st[key] = {k: float(merged.get(k, 0.0)) for k in FEATURE_NAMES}
    act = doc.get("active")
    if isinstance(act, list) and act:
        st["active"] = [str(x) for x in act if str(x) in FEATURE_NAMES]
        if "bias" not in st["active"]:
            st["active"] = ["bias"] + st["active"]
        # New public-tell features stay live even if an older state.json froze `active`.
        have = set(st["active"])
        try:
            from analytics.event_ingenuity import INGENUITY_KEYS

            for k in INGENUITY_KEYS:
                if k in FEATURE_NAMES and k not in have:
                    st["active"].append(k)
        except Exception:
            pass
    return st


def save_state(st: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    st["updated"] = time.time()
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(st, indent=2, default=float), encoding="utf-8")
    os.replace(tmp, STATE_PATH)


def _weights_arr(st: dict[str, Any], which: str, active: list[str]) -> np.ndarray:
    w = st.get(which) or {}
    return np.asarray([float(w.get(k, 0.0)) for k in active], dtype=np.float64)


def predict_from_feats(
    feats: dict[str, float],
    st: dict[str, Any] | None = None,
) -> dict[str, Any]:
    st = st or load_state()
    active = [k for k in (st.get("active") or FEATURE_NAMES) if k in FEATURE_NAMES]
    if "bias" not in active:
        active = ["bias"] + active
    x = vectorize(feats, active)
    z = float(np.dot(_weights_arr(st, "w_dir", active), x))
    p_up = _clip01(_sigmoid(z))
    mag = float(max(0.0, np.dot(_weights_arr(st, "w_mag", active), x)))
    mag = min(0.25, mag)
    skill = _clip01(float(st.get("skill") or 0.0))
    if not enabled():
        skill = 0.0
    # Rank boost: skill * direction * size-vs-typical (typical ~ 2%)
    typical = max(0.012, mag if mag > 0 else 0.02)
    boost = skill * (p_up - 0.5) * 2.0 * min(2.0, mag / 0.02)
    boost = max(-1.0, min(1.0, float(boost)))
    return {
        "p_up": round(p_up, 6),
        "mag": round(mag, 6),
        "skill": round(skill, 6),
        "boost": round(boost, 6),
        "typical": round(typical, 6),
        "applied": abs(boost) > 1e-6 and skill > 0.02,
    }


def features_for_ticker(
    ticker: str,
    *,
    mom_5d: float = 0.0,
    ret_1d: float = 0.0,
    vol_20: float = 0.0,
    as_of: date | None = None,
) -> dict[str, float]:
    """Live / as-of features for any symbol (earnings clock + event calendar)."""
    dte = dse = hour = None
    in_win = False
    hist1 = hist5 = n_prints = None
    cal_pre = live = guidance = conference = 0.0
    try:
        from intel.historical_events import earnings_event

        snap = earnings_event(ticker, as_of=as_of)
        dte = snap.get("days_to")
        dse = snap.get("days_since")
        in_win = bool(snap.get("in_window"))
        hour = snap.get("hour") or snap.get("session")
        hist1 = snap.get("avg_abs_move_1d")
        hist5 = snap.get("avg_abs_move_5d")
        n_prints = snap.get("n_prints_used")
    except Exception:
        pass
    try:
        from analytics.event_calendar import exhaustion, ticker_row

        row = ticker_row(ticker)
        if row:
            cal_pre = float(row.get("pre") or 0.0)
            live = float(row.get("live_binary") or 0.0)
            guidance = float(row.get("guidance") or 0.0)
            conference = float(row.get("conference") or 0.0)
        ex = exhaustion(ret_1d if ret_1d else None, mom_5d, live=live)
    except Exception:
        ex = 0.0
    extra = None
    try:
        from analytics.event_ingenuity import live_features

        extra = live_features(
            ticker,
            as_of=as_of,
            dte=_i(dte),
            hist_abs_1d=float(hist1 or 0.0),
        )
    except Exception:
        extra = None
    return featurize(
        dte=dte,
        dse=dse,
        in_window=in_win,
        hour=hour,
        hist_abs_1d=hist1,
        hist_abs_5d=hist5,
        n_prints=n_prints,
        cal_pre=cal_pre,
        live_binary=live,
        guidance=guidance,
        conference=conference,
        exhaustion=ex,
        mom_5d=mom_5d,
        ret_1d=ret_1d,
        vol_20=vol_20,
        is_event_day=(_i(dte) == 0),
        extra=extra,
    )


def predict_ticker(
    ticker: str,
    *,
    mom_5d: float = 0.0,
    ret_1d: float = 0.0,
    vol_20: float = 0.0,
    as_of: date | None = None,
    st: dict[str, Any] | None = None,
) -> dict[str, Any]:
    feats = features_for_ticker(ticker, mom_5d=mom_5d, ret_1d=ret_1d, vol_20=vol_20, as_of=as_of)
    out = predict_from_feats(feats, st=st)
    out["symbol"] = ticker.strip().upper()
    out["feats"] = feats
    return out


def event_learn_rank_boost(
    ticker: str,
    *,
    mom_5d: float = 0.0,
    ret_1d: float | None = None,
    vol_20: float = 0.0,
    sleeve: str | None = None,
) -> tuple[float, dict[str, Any]]:
    meta: dict[str, Any] = {"applied": 0.0, "skill": 0.0}
    if not enabled() or str(sleeve or "").lower() == "hft":
        meta["skipped"] = "disabled_or_hft"
        return 0.0, meta
    pred = predict_ticker(ticker, mom_5d=mom_5d, ret_1d=float(ret_1d or 0.0), vol_20=vol_20)
    boost = float(pred.get("boost") or 0.0)
    try:
        from analytics.catalyst_horizon import catalyst_horizon_fit
        from intel.historical_events import earnings_event

        dte = earnings_event(ticker).get("days_to")
        fit = float(catalyst_horizon_fit(dte, sleeve))
        boost *= max(0.15, fit)
    except Exception:
        fit = 1.0
    boost = max(-1.0, min(1.0, boost))
    meta.update(
        {
            "applied": round(boost, 4),
            "skill": pred.get("skill"),
            "p_up": pred.get("p_up"),
            "mag": pred.get("mag"),
            "fit": round(fit, 4),
        }
    )
    return boost, meta


def fit_ridge(
    X: np.ndarray,
    y: np.ndarray,
    *,
    l2: float = 1.0,
    prior: np.ndarray | None = None,
    sample_w: np.ndarray | None = None,
) -> np.ndarray:
    """Closed-form ridge. prior pulls unused coords toward a structured guess."""
    n, p = X.shape
    if n < 8 or p < 1:
        return prior.copy() if prior is not None else np.zeros(p)
    if sample_w is None:
        Xs, ys = X, y
    else:
        sw = np.sqrt(np.clip(np.asarray(sample_w, dtype=np.float64), 1e-6, 1e6))
        Xs = X * sw[:, None]
        ys = y * sw
    xtx = Xs.T @ Xs + l2 * np.eye(p)
    xty = Xs.T @ ys
    if prior is not None:
        xty = xty + l2 * 0.35 * prior
    try:
        return np.linalg.solve(xtx, xty)
    except np.linalg.LinAlgError:
        return np.linalg.pinv(xtx) @ xty


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 8:
        return 0.0
    ra = np.argsort(np.argsort(a))
    rb = np.argsort(np.argsort(b))
    ra = ra.astype(np.float64)
    rb = rb.astype(np.float64)
    ra -= ra.mean()
    rb -= rb.mean()
    den = float(np.sqrt((ra * ra).sum() * (rb * rb).sum()))
    if den < 1e-12:
        return 0.0
    return float((ra * rb).sum() / den)


def walk_forward_metrics(
    samples: list[EventSample],
    *,
    active: list[str] | None = None,
    min_train: int = 64,
    l2: float = 1.25,
) -> dict[str, Any]:
    """Expanding-window walk-forward. Train on the past, score the next chunk."""
    names = active or list(FEATURE_NAMES)
    ordered = sorted(samples, key=lambda s: s.as_of)
    if len(ordered) < min_train + 20:
        return {"ok": False, "reason": "too_few", "n": len(ordered), "ic": 0.0, "acc": 0.5, "mae": 9.0, "base_mae": 9.0}
    xs = np.stack([vectorize(s.feats, names) for s in ordered])
    y_s = np.asarray([1.0 if s.y_sign > 0 else 0.0 for s in ordered], dtype=np.float64)
    y_a = np.asarray([float(s.y_abs) for s in ordered], dtype=np.float64)
    ev = np.asarray([1.0 if s.is_event else 0.0 for s in ordered], dtype=np.float64)
    dates = [s.as_of for s in ordered]
    pred_mag: list[float] = []
    pred_p: list[float] = []
    real_a: list[float] = []
    real_s: list[float] = []
    real_ev: list[float] = []
    i = min_train
    while i < len(ordered):
        j = min(len(ordered), i + 40)
        Xtr, ytr_s, ytr_a, evtr = xs[:i], y_s[:i], y_a[:i], ev[:i]
        prior_d = _prior_vec(_DIR_PRIOR, names)
        prior_m = _prior_vec(_MAG_PRIOR, names)
        sw_dir = 1.0 + 5.0 * evtr
        wd = fit_ridge(Xtr, ytr_s * 2.0 - 1.0, l2=l2, prior=prior_d, sample_w=sw_dir)
        wm = fit_ridge(Xtr, ytr_a, l2=l2, prior=prior_m, sample_w=1.0 + 3.0 * evtr)
        for k in range(i, j):
            z = float(np.dot(wd, xs[k]))
            pred_p.append(_sigmoid(z))
            pred_mag.append(max(0.0, float(np.dot(wm, xs[k]))))
            real_a.append(float(y_a[k]))
            real_s.append(float(y_s[k]))
            real_ev.append(float(ev[k]))
        i = j
    if len(pred_mag) < 12:
        return {"ok": False, "reason": "short_oos", "n": len(ordered), "ic": 0.0, "acc": 0.5, "mae": 9.0, "base_mae": 9.0}
    pm = np.asarray(pred_mag)
    pa = np.asarray(pred_p)
    ra = np.asarray(real_a)
    rs = np.asarray(real_s)
    rev = np.asarray(real_ev) >= 0.5
    ic = _spearman(pm, ra)
    acc = float(np.mean(((pa >= 0.5) == (rs >= 0.5)).astype(np.float64)))
    acc_event = acc
    if rev.sum() >= 6:
        acc_event = float(np.mean(((pa[rev] >= 0.5) == (rs[rev] >= 0.5)).astype(np.float64)))
    mae = float(np.mean(np.abs(pm - ra)))
    base = float(np.mean(y_a[:min_train]))
    base_mae = float(np.mean(np.abs(base - ra)))
    mae_event = mae
    base_mae_event = base_mae
    beat_event = False
    if int(rev.sum()) >= 8:
        mae_event = float(np.mean(np.abs(pm[rev] - ra[rev])))
        ev_tr = ev[:min_train] >= 0.5
        if int(ev_tr.sum()) >= 8:
            base_e = float(np.mean(y_a[:min_train][ev_tr]))
            base_mae_event = float(np.mean(np.abs(base_e - ra[rev])))
            beat_event = mae_event < base_mae_event - 1e-6
    return {
        "ok": True,
        "n": len(ordered),
        "n_oos": len(pred_mag),
        "n_oos_event": int(rev.sum()),
        "ic": round(ic, 5),
        "acc": round(acc, 5),
        "acc_event": round(acc_event, 5),
        "mae": round(mae, 5),
        "base_mae": round(base_mae, 5),
        "mae_event": round(mae_event, 5),
        "base_mae_event": round(base_mae_event, 5),
        "beat_baseline": bool(mae < base_mae - 1e-6 or beat_event),
        "first_oos": dates[min_train].isoformat() if min_train < len(dates) else None,
    }


def redesign_until_best(
    samples: list[EventSample],
    *,
    max_rounds: int = 8,
    l2: float = 1.25,
    min_train: int = 64,
) -> dict[str, Any]:
    """Drop features that hurt OOS IC; keep iterating while the score rises."""
    active = list(FEATURE_NAMES)
    dropped: list[str] = []
    best: dict[str, Any] | None = None
    for rnd in range(max_rounds):
        met = walk_forward_metrics(samples, active=active, l2=l2, min_train=min_train)
        names = list(active)
        X = np.stack([vectorize(s.feats, names) for s in samples])
        y_s = np.asarray([1.0 if s.y_sign > 0 else 0.0 for s in samples])
        y_a = np.asarray([float(s.y_abs) for s in samples])
        evw = np.asarray([1.0 if s.is_event else 0.0 for s in samples])
        wd = fit_ridge(
            X, y_s * 2.0 - 1.0, l2=l2, prior=_prior_vec(_DIR_PRIOR, names), sample_w=1.0 + 5.0 * evw
        )
        wm = fit_ridge(
            X, y_a, l2=l2, prior=_prior_vec(_MAG_PRIOR, names), sample_w=1.0 + 3.0 * evw
        )
        cand = {
            "metrics": met,
            "active": names,
            "w_dir": {k: float(wd[i]) for i, k in enumerate(names)},
            "w_mag": {k: float(wm[i]) for i, k in enumerate(names)},
            "round": rnd,
        }
        ic = float(met.get("ic") or 0.0)
        if best is None or ic > float((best.get("metrics") or {}).get("ic") or -9):
            best = cand
        # Ablate one feature: if removing it raises IC, drop it and continue.
        worst_name = None
        worst_gain = 0.0
        for f in names:
            if f == "bias":
                continue
            sub = [k for k in names if k != f]
            m2 = walk_forward_metrics(samples, active=sub, l2=l2, min_train=min_train)
            gain = float(m2.get("ic") or 0.0) - ic
            if gain > worst_gain:
                worst_gain = gain
                worst_name = f
        if worst_name and worst_gain >= 0.008:
            active = [k for k in active if k != worst_name]
            dropped.append(worst_name)
            continue
        break
    assert best is not None
    met = best["metrics"]
    ic = float(met.get("ic") or 0.0)
    acc = float(met.get("acc_event") or met.get("acc") or 0.5)
    beat = bool(met.get("beat_baseline"))
    # Skill: only deploy when OOS IC is positive *and* we beat naive |move| MAE.
    skill = 0.0
    if ic > 0.02 and (beat or ic > 0.08):
        skill = _clip01((ic - 0.02) / 0.23)
        skill = max(skill, 0.15 if beat else 0.0)
        if acc >= 0.53:
            skill = min(1.0, skill + 0.08)
    st = default_state()
    st["active"] = best["active"]
    st["w_dir"] = {k: float(best["w_dir"].get(k, 0.0)) for k in FEATURE_NAMES}
    st["w_mag"] = {k: float(best["w_mag"].get(k, 0.0)) for k in FEATURE_NAMES}
    st["skill"] = round(skill, 5)
    st["oos_ic"] = met.get("ic")
    st["oos_acc"] = met.get("acc_event") or met.get("acc")
    st["baseline_mae"] = met.get("base_mae")
    st["model_mae"] = met.get("mae")
    st["n_samples"] = len(samples)
    st["n_redesign"] = int(best.get("round") or 0) + 1
    st["dropped"] = dropped
    st["beat_baseline"] = beat
    return st


def online_update(
    feats: dict[str, float],
    *,
    y_sign: float,
    y_abs: float,
    st: dict[str, Any] | None = None,
    lr: float | None = None,
) -> dict[str, Any]:
    """One SGD step. Skill EMA from signed agreement. Self-gates if it starts losing."""
    st = st or load_state()
    if not enabled():
        return st
    names = [k for k in (st.get("active") or FEATURE_NAMES) if k in FEATURE_NAMES]
    if "bias" not in names:
        names = ["bias"] + names
    x = vectorize(feats, names)
    lr = float(lr if lr is not None else _f("EVENT_LEARN_LR", 0.04))
    l2 = _f("EVENT_LEARN_L2", 0.08)
    wd = _weights_arr(st, "w_dir", names)
    wm = _weights_arr(st, "w_mag", names)
    p = _sigmoid(float(np.dot(wd, x)))
    y = 1.0 if float(y_sign) > 0 else 0.0
    wd = wd - lr * ((p - y) * x + l2 * wd)
    err = float(np.dot(wm, x) - max(0.0, float(y_abs)))
    wm = wm - lr * (err * x + l2 * wm)
    w_dir = dict(st.get("w_dir") or {})
    w_mag = dict(st.get("w_mag") or {})
    for i, k in enumerate(names):
        w_dir[k] = float(wd[i])
        w_mag[k] = float(wm[i])
    st["w_dir"] = w_dir
    st["w_mag"] = w_mag
    agree = 1.0 if (p >= 0.5) == (y >= 0.5) else 0.0
    mag_err = abs(float(np.dot(wm, x)) - float(y_abs))
    mag_ok = 1.0 if mag_err < max(0.01, 0.6 * float(y_abs) + 0.005) else 0.0
    pulse = 0.6 * agree + 0.4 * mag_ok
    eta = _f("EVENT_LEARN_SKILL_EMA", 0.08)
    skill = float(st.get("skill") or 0.35)
    skill = (1.0 - eta) * skill + eta * pulse
    # Collapse if the last stretch is noise
    st["skill"] = round(_clip01(skill), 5)
    st["n_updates"] = int(st.get("n_updates") or 0) + 1
    save_state(st)
    return st


def credit_event_outcome(
    ticker: str,
    realized_1d: float,
    *,
    mom_5d: float = 0.0,
    ret_1d: float = 0.0,
    vol_20: float = 0.0,
) -> dict[str, Any]:
    """Live self-adjust after a print move or a closed trade in an event window."""
    if not enabled():
        return {"applied": False}
    feats = features_for_ticker(ticker, mom_5d=mom_5d, ret_1d=ret_1d, vol_20=vol_20)
    # Only learn when we were actually in an event neighborhood (don't fit noise days).
    if (
        float(feats.get("dte_0") or 0) < 0.5
        and float(feats.get("dte_1") or 0) < 0.5
        and float(feats.get("dse_0") or 0) < 0.5
        and float(feats.get("is_event_day") or 0) < 0.5
        and float(feats.get("in_window") or 0) < 0.5
        and float(feats.get("cal_pre") or 0) < 0.15
    ):
        return {"applied": False, "reason": "not_event_window"}
    y_abs = abs(float(realized_1d))
    y_sign = 1.0 if float(realized_1d) >= 0 else -1.0
    st = online_update(feats, y_sign=y_sign, y_abs=y_abs)
    return {"applied": True, "symbol": ticker.strip().upper(), "skill": st.get("skill"), "n_updates": st.get("n_updates")}


def samples_from_closes(
    symbol: str,
    closes: Any,
    earnings_dates: list[date],
    *,
    hour: str | None = None,
    control_stride: int = 18,
) -> list[EventSample]:
    """Build leak-free samples from a daily close series (index = dates).

    Label at print E uses only closes strictly before E for features;
    y is the gap E vs last close before E.
    """
    import pandas as pd

    if closes is None:
        return []
    s = closes
    if isinstance(s, pd.DataFrame):
        col = "Adj Close" if "Adj Close" in s.columns else "Close"
        s = s[col]
    s = pd.Series(s).astype(float).dropna()
    if s.empty or len(s) < 40:
        return []
    idx = pd.to_datetime(s.index).normalize()
    s.index = idx
    s = s[s > 0].sort_index()
    earn = sorted({d if isinstance(d, date) else date.fromisoformat(str(d)[:10]) for d in earnings_dates})
    earn_set = set(earn)
    out: list[EventSample] = []

    def _hist_abs(before: date, n: int = 6) -> tuple[float, int]:
        past = [d for d in earn if d < before][-n:]
        vals: list[float] = []
        for ed in past:
            ed_ts = pd.Timestamp(ed)
            after = s[s.index >= ed_ts]
            before_px = s[s.index < ed_ts]
            if after.empty or before_px.empty:
                continue
            p0 = float(before_px.iloc[-1])
            p1 = float(after.iloc[0])
            if p0 > 0:
                vals.append(abs(p1 / p0 - 1.0))
        if not vals:
            return 0.0, 0
        return float(sum(vals) / len(vals)), len(vals)

    def _row_at(ts: pd.Timestamp, *, event: bool, dte: int | None, y_abs: float, y_sign: float) -> EventSample | None:
        loc = s.index.get_indexer([ts], method="pad")
        if loc[0] < 0:
            return None
        i = int(loc[0])
        if i < 25:
            return None
        px = float(s.iloc[i])
        px1 = float(s.iloc[i - 1]) if i >= 1 else px
        px5 = float(s.iloc[i - 5]) if i >= 5 else px
        rets = s.iloc[max(0, i - 20) : i + 1].pct_change().dropna()
        vol = float(rets.std()) if len(rets) >= 8 else 0.0
        mom = (px / px5 - 1.0) if px5 > 0 else 0.0
        ret1 = (px / px1 - 1.0) if px1 > 0 else 0.0
        hist1, npr = _hist_abs(ts.date())
        as_of = ts.date()
        dse = None
        past = [d for d in earn if d < as_of]
        if past:
            dse = (as_of - past[-1]).days
        feats = featurize(
            dte=dte,
            dse=dse if not event else None,
            in_window=bool(event or (dte is not None and 0 <= dte <= 5)),
            hour=hour if event else None,
            hist_abs_1d=hist1,
            hist_abs_5d=hist1,
            n_prints=npr,
            mom_5d=mom,
            ret_1d=ret1,
            vol_20=vol,
            is_event_day=event,
        )
        return EventSample(symbol.upper(), as_of, feats, y_sign, y_abs, is_event=event)

    for ed in earn:
        ed_ts = pd.Timestamp(ed)
        before = s[s.index < ed_ts]
        after = s[s.index >= ed_ts]
        if before.empty or after.empty:
            continue
        p0 = float(before.iloc[-1])
        p1 = float(after.iloc[0])
        if p0 <= 0:
            continue
        gap = p1 / p0 - 1.0
        # Features as of last close *before* the print (dte=1 from that bar's view if next session is print)
        ts_feat = before.index[-1]
        samp = _row_at(ts_feat, event=True, dte=1, y_abs=abs(gap), y_sign=1.0 if gap >= 0 else -1.0)
        if samp:
            samp.feats["dte_0"] = 0.0
            samp.feats["dte_1"] = 1.0
            samp.feats["is_event_day"] = 1.0
            samp.feats["proximity"] = float(math.exp(-1.0 / 5.0))
            out.append(samp)

    # Control days so magnitude is not always "earnings-sized".
    if control_stride > 0:
        for i in range(25, len(s) - 1, max(1, int(control_stride))):
            ts = s.index[i]
            d = ts.date()
            if d in earn_set:
                continue
            future = [e for e in earn if e >= d]
            dte = (future[0] - d).days if future else 90
            if dte <= 5:
                continue
            p0 = float(s.iloc[i])
            p1 = float(s.iloc[i + 1])
            if p0 <= 0:
                continue
            gap = p1 / p0 - 1.0
            samp = _row_at(ts, event=False, dte=dte, y_abs=abs(gap), y_sign=1.0 if gap >= 0 else -1.0)
            if samp:
                out.append(samp)
    return out
