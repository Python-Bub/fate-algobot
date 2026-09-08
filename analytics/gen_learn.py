"""Next-gen combiner: walk-forward ridge on proven expert votes.

Hedge MW is the live prior. This student predicts next-day return from the
vote vector + residual momentum. Deploys only when OOS IC > 0.02; otherwise
skill → 0 and rank is unchanged. Online SGD keeps it moving after each fill.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "intel" / "gen_learn_state.json"
REPORT_PATH = ROOT / "data" / "intel" / "gen_learn_report.json"

VOTE_KEYS: tuple[str, ...] = (
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
FEATURE_NAMES: tuple[str, ...] = ("bias",) + VOTE_KEYS + ("resid_raw", "mom_5d", "rs_spy", "p_up")
_PRIOR = {
    "bias": 0.0,
    "model": 0.35,
    "tsmom": 0.45,
    "resid_mom": 0.40,
    "trend": 0.25,
    "exec": 0.20,
    "quality_tape": 0.15,
    "mom_5d": 0.30,
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
    return _b("USE_GEN_LEARN", True)


def _clip01(p: float) -> float:
    return float(max(0.01, min(0.99, p)))


def _sigmoid(z: float) -> float:
    z = max(-20.0, min(20.0, float(z)))
    return 1.0 / (1.0 + math.exp(-z))


def default_state() -> dict[str, Any]:
    return {
        "w": [0.0] * len(FEATURE_NAMES),
        "skill": 0.0,
        "ic": 0.0,
        "n": 0,
        "n_updates": 0,
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
    w = list(st["w"])
    raw = doc.get("w") or []
    if isinstance(raw, list) and len(raw) == len(FEATURE_NAMES):
        w = [float(x) for x in raw]
    st["w"] = w
    st["skill"] = float(doc.get("skill") or 0.0)
    st["ic"] = float(doc.get("ic") or 0.0)
    st["n"] = int(doc.get("n") or 0)
    st["n_updates"] = int(doc.get("n_updates") or 0)
    return st


def save_state(st: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    st["updated"] = time.time()
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(st, indent=2, default=float), encoding="utf-8")
    os.replace(tmp, STATE_PATH)


def vectorize(
    votes: dict[str, int],
    *,
    resid_raw: float = 0.0,
    mom_5d: float = 0.0,
    rs_spy: float = 1.0,
    p_up: float = 0.5,
) -> np.ndarray:
    x = np.zeros(len(FEATURE_NAMES), dtype=np.float64)
    x[0] = 1.0
    for i, k in enumerate(VOTE_KEYS, start=1):
        x[i] = float(int(votes.get(k) or 0))
    x[-4] = float(max(-2.0, min(2.0, resid_raw)))
    x[-3] = float(max(-0.5, min(0.5, mom_5d)))
    x[-2] = float(max(0.5, min(1.5, rs_spy)))
    x[-1] = _clip01(p_up)
    return x


def _fit_ridge(X: np.ndarray, y: np.ndarray, *, l2: float = 1.5, prior: np.ndarray | None = None) -> np.ndarray:
    n, p = X.shape
    if n < 12 or p < 1:
        return prior.copy() if prior is not None else np.zeros(p)
    xtx = X.T @ X + l2 * np.eye(p)
    xty = X.T @ y
    if prior is not None:
        xty = xty + l2 * 0.30 * prior
    try:
        return np.linalg.solve(xtx, xty)
    except np.linalg.LinAlgError:
        return np.linalg.pinv(xtx) @ xty


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 12:
        return 0.0
    ra = np.argsort(np.argsort(a)).astype(np.float64)
    rb = np.argsort(np.argsort(b)).astype(np.float64)
    ra -= ra.mean()
    rb -= rb.mean()
    den = float(np.sqrt((ra * ra).sum() * (rb * rb).sum()))
    if den < 1e-12:
        return 0.0
    return float((ra * rb).sum() / den)


def _prior_vec() -> np.ndarray:
    v = np.zeros(len(FEATURE_NAMES), dtype=np.float64)
    idx = {n: i for i, n in enumerate(FEATURE_NAMES)}
    for k, val in _PRIOR.items():
        if k in idx:
            v[idx[k]] = float(val)
    return v


def walk_forward(X: np.ndarray, y: np.ndarray, *, min_train: int = 400) -> dict[str, Any]:
    n = int(X.shape[0])
    if n < min_train + 40:
        return {"ok": False, "reason": "too_few", "n": n, "ic": 0.0, "acc": 0.5}
    pred: list[float] = []
    real: list[float] = []
    i = min_train
    prior = _prior_vec()
    while i < n:
        j = min(n, i + 80)
        w = _fit_ridge(X[:i], y[:i], prior=prior)
        for k in range(i, j):
            pred.append(float(np.dot(w, X[k])))
            real.append(float(y[k]))
        i = j
    if len(pred) < 20:
        return {"ok": False, "reason": "short_oos", "n": n, "ic": 0.0, "acc": 0.5}
    pm = np.asarray(pred)
    ry = np.asarray(real)
    ic = _spearman(pm, ry)
    acc = float(np.mean(((pm > 0) == (ry > 0)).astype(np.float64)))
    return {
        "ok": True,
        "n": n,
        "n_oos": len(pred),
        "ic": round(float(ic), 5),
        "acc": round(acc, 5),
        "mean_pred": round(float(pm.mean()), 6),
        "mean_y": round(float(ry.mean()), 6),
    }


def fit_and_deploy(X: np.ndarray, y: np.ndarray, *, min_train: int = 400) -> dict[str, Any]:
    met = walk_forward(X, y, min_train=min_train)
    st = load_state()
    ic = float(met.get("ic") or 0.0)
    floor = _f("GEN_LEARN_MIN_IC", 0.02)
    skill = 0.0
    if met.get("ok") and ic > floor:
        skill = float(max(0.0, min(1.0, ic / 0.08)))
        st["w"] = _fit_ridge(X, y, prior=_prior_vec()).tolist()
    else:
        # Keep prior weights at skill 0 so live rank is not hurt.
        st["w"] = _prior_vec().tolist()
    st["skill"] = skill
    st["ic"] = ic
    st["n"] = int(X.shape[0])
    st["acc"] = met.get("acc")
    st["ok"] = bool(met.get("ok"))
    save_state(st)
    report = {**met, "skill": skill, "ts": time.time()}
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, default=float), encoding="utf-8")
    return report


def predict_p(
    votes: dict[str, int],
    *,
    resid_raw: float = 0.0,
    mom_5d: float = 0.0,
    rs_spy: float = 1.0,
    p_up: float = 0.5,
    st: dict[str, Any] | None = None,
) -> tuple[float, dict[str, Any]]:
    st = st if st is not None else load_state()
    skill = float(st.get("skill") or 0.0)
    meta = {"skill": skill, "p_gen": 0.5, "applied": False}
    if not enabled() or skill <= 0.02:
        return 0.5, meta
    w = np.asarray(st.get("w") or [], dtype=np.float64)
    if w.size != len(FEATURE_NAMES):
        return 0.5, meta
    x = vectorize(votes, resid_raw=resid_raw, mom_5d=mom_5d, rs_spy=rs_spy, p_up=p_up)
    z = float(np.dot(w, x))
    # Scale a return-like score into a probability.
    p = _clip01(_sigmoid(8.0 * z))
    meta["p_gen"] = round(p, 6)
    meta["applied"] = True
    meta["z"] = round(z, 6)
    return p, meta


def mix_p(
    p_cal: float,
    votes: dict[str, int],
    *,
    row: Any = None,
    p_up: float = 0.5,
    mom_5d: float = 0.0,
    rs_spy: float = 1.0,
) -> tuple[float, dict[str, Any]]:
    resid = 0.0
    if row is not None:
        getter = row.get if isinstance(row, dict) else getattr(row, "get", None)
        if getter is not None:
            try:
                resid = float(getter("resid_mom_12_1") or getter("resid_mom") or 0.0)
            except (TypeError, ValueError):
                resid = 0.0
        else:
            try:
                resid = float(row["resid_mom_12_1"])
            except Exception:
                resid = 0.0
    p_g, meta = predict_p(
        votes, resid_raw=resid, mom_5d=mom_5d, rs_spy=rs_spy, p_up=p_up
    )
    skill = float(meta.get("skill") or 0.0)
    if not meta.get("applied") or skill <= 0.02:
        return float(p_cal), meta
    w = min(0.40, 0.20 + 0.40 * skill)
    mixed = (1.0 - w) * float(p_cal) + w * float(p_g)
    meta["p_mix"] = round(_clip01(mixed), 6)
    meta["mix_w"] = round(w, 4)
    return _clip01(mixed), meta


def online_update(
    votes: dict[str, int],
    realized_return: float,
    *,
    p_up: float = 0.5,
    mom_5d: float = 0.0,
    rs_spy: float = 1.0,
    resid_raw: float = 0.0,
    persist: bool = True,
    st: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not enabled():
        return {"applied": False}
    st = st if st is not None else load_state()
    if float(st.get("skill") or 0.0) <= 0.02:
        return {"applied": False, "reason": "no_skill"}
    w = np.asarray(st.get("w") or [], dtype=np.float64)
    if w.size != len(FEATURE_NAMES):
        return {"applied": False, "reason": "bad_w"}
    x = vectorize(votes, resid_raw=resid_raw, mom_5d=mom_5d, rs_spy=rs_spy, p_up=p_up)
    z = float(np.dot(w, x))
    p = _sigmoid(8.0 * z)
    y = 1.0 if float(realized_return) > 0 else 0.0
    lr = _f("GEN_LEARN_LR", 0.03)
    grad = (p - y) * 8.0
    w = w - lr * grad * x
    st["w"] = w.tolist()
    st["n_updates"] = int(st.get("n_updates") or 0) + 1
    if persist:
        save_state(st)
    return {"applied": True, "n_updates": st["n_updates"], "st": st}
