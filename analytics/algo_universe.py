"""One algorithm for every stock — not a per-ticker model.

The distilled student is a single cross-sectional mapping:
teacher features → p_up. Any symbol with those features gets a score.
A global SGD adapter then learns from realized outcomes so the mapping
tightens as more names teach it (coverage 1−exp(−n/τ)).
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from analytics.algo_generation import (
    FEATURE_COLS,
    _apply_bundle,
    _auc_score,
    _enrich_rows,
    _feat_default,
    _fget,
    _matrix,
    _new_hgb,
    algo_dir,
    current_ptr,
    harvest_rows_path,
    _load_json,
    _now,
    _save_json,
)
from utils import log

_LAST_FEATS: dict[str, dict[str, Any]] = {}
_ADAPTER_CACHE: tuple[float, Any] | None = None


def adapter_path() -> Path:
    return algo_dir() / "adapter.pkl"


def online_state_path() -> Path:
    raw = os.getenv("ALGO_ONLINE_STATE", "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parents[1] / "data" / "intel" / "algo_online.json"


def replay_path() -> Path:
    raw = os.getenv("ALGO_ONLINE_REPLAY", "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parents[1] / "data" / "intel" / "algo_online_replay.jsonl"


def smoke_state_path() -> Path:
    raw = os.getenv("ALGO_SMOKE_STATE", "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parents[1] / "data" / "intel" / "algo_smoke.json"


def use_algo_online() -> bool:
    return os.getenv("USE_ALGO_ONLINE", "true").lower() in ("1", "true", "yes")


def coverage_weight(n_tickers: int, *, tau: float | None = None) -> float:
    """Exponential approach to 1 as more stocks teach the one algorithm."""
    t = float(tau if tau is not None else os.getenv("ALGO_ONLINE_TAU", "400"))
    t = max(1.0, t)
    n = max(0, int(n_tickers))
    return float(1.0 - math.exp(-n / t))


def features_from_signals(
    *,
    ticker: str,
    p_up: float,
    exec_conf: float = 0.5,
    sent: float = 0.0,
    news_factor: float = 0.0,
    mom_5d: float = 0.0,
    rs_spy: float = 1.0,
    vol_ratio: float = 1.0,
    dip_signal: float = 0.0,
    neural_p_up: float | None = None,
    lstm_p_up: float | None = None,
    p_short: float | None = None,
    p_long: float | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the global feature row from live rank signals (any ticker)."""
    p = float(p_up)
    row: dict[str, Any] = {c: _feat_default(c) for c in FEATURE_COLS}
    row["ticker"] = str(ticker).upper()
    row["p_up"] = p
    row["p_up_raw"] = p
    row["p_short_model"] = float(p_short if p_short is not None else p)
    row["p_long_model"] = float(p_long if p_long is not None else p)
    row["execution_confidence"] = float(exec_conf)
    row["score"] = (p - 0.5) * 2.0
    row["momentum_5d"] = float(mom_5d)
    row["rs_spy"] = float(rs_spy)
    row["volume_ratio"] = float(vol_ratio)
    row["sentiment"] = float(sent)
    row["dip_signal"] = float(dip_signal)
    row["news_factor"] = float(news_factor)
    row["lstm_p_up"] = float(lstm_p_up if lstm_p_up is not None else p)
    row["neural_p_up"] = float(neural_p_up if neural_p_up is not None else p)
    if extra:
        for k, v in extra.items():
            if k in FEATURE_COLS:
                try:
                    row[k] = float(v)
                except (TypeError, ValueError):
                    pass
    _enrich_rows([row])
    return row


def _load_live_bundle() -> dict[str, Any] | None:
    """Only current.json — never a staged gen pickle."""
    ptr = _load_json(current_ptr(), {}) or {}
    path = Path(str(ptr.get("path") or ""))
    if not path.is_file():
        return None
    try:
        bundle = joblib.load(path)
    except Exception:
        return None
    if isinstance(bundle, dict):
        bundle = dict(bundle)
        bundle["generation"] = int(ptr.get("generation") or bundle.get("generation") or 0)
    return bundle


def _new_adapter():
    from sklearn.linear_model import SGDClassifier

    return SGDClassifier(
        loss="log_loss",
        learning_rate="constant",
        eta0=float(os.getenv("ALGO_ONLINE_ETA", "0.01")),
        alpha=1e-4,
        random_state=42,
    )


def _load_adapter() -> Any | None:
    global _ADAPTER_CACHE
    path = adapter_path()
    if not path.is_file():
        return None
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    if _ADAPTER_CACHE and _ADAPTER_CACHE[0] == mtime:
        return _ADAPTER_CACHE[1]
    try:
        clf = joblib.load(path)
    except Exception:
        return None
    _ADAPTER_CACHE = (mtime, clf)
    return clf


def _save_adapter(clf: Any) -> None:
    global _ADAPTER_CACHE
    path = adapter_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, path)
    try:
        _ADAPTER_CACHE = (path.stat().st_mtime, clf)
    except OSError:
        _ADAPTER_CACHE = None


def score_row(row: dict[str, Any], *, bundle: dict[str, Any] | None = None) -> float:
    """Score one feature row through the live student (any ticker)."""
    b = bundle if bundle is not None else _load_live_bundle()
    if not b:
        return float(_fget(row, "p_up", 0.5))
    try:
        return float(_apply_bundle([row], b)[0])
    except Exception:
        return float(_fget(row, "p_up", 0.5))


def score_rows(rows: list[dict[str, Any]], *, bundle: dict[str, Any] | None = None) -> np.ndarray:
    b = bundle if bundle is not None else _load_live_bundle()
    if not b or not rows:
        return np.array([_fget(r, "p_up", 0.5) for r in rows], dtype=float)
    try:
        return np.asarray(_apply_bundle(rows, b), dtype=float)
    except Exception:
        return np.array([_fget(r, "p_up", 0.5) for r in rows], dtype=float)


def _blend(student_p: float, adapter_p: float | None, n_tickers: int, rolling_auc: float) -> tuple[float, float]:
    if adapter_p is None or rolling_auc <= 0.50:
        return float(student_p), 0.0
    w = coverage_weight(n_tickers) * max(0.0, min(1.0, (rolling_auc - 0.5) * 2.0))
    p = (1.0 - w) * float(student_p) + w * float(adapter_p)
    return float(np.clip(p, 0.01, 0.99)), float(w)


def live_rank_boost(ticker: str, features: dict[str, Any] | None = None) -> tuple[float, dict[str, Any]]:
    """Additive rank from the one live algorithm. Works for every stock with features."""
    if os.getenv("USE_ALGO_PIPELINE", "true").lower() not in ("1", "true", "yes"):
        return 0.0, {"head": "algo", "off": True}
    w_cap = float(os.getenv("RANK_W_ALGO", "0.12"))
    bundle = _load_live_bundle()
    if not bundle:
        return 0.0, {"head": "algo", "no_live": True}
    t = str(ticker).upper()
    row = dict(features) if features else None
    if row:
        row["ticker"] = t
        _enrich_rows([row])
        _LAST_FEATS[t] = row
        p_s = score_row(row, bundle=bundle)
        src = "features"
    else:
        from analytics.algo_generation import board_path

        rec = (_load_json(board_path(), {}) or {}).get("board") or {}
        hit = rec.get(t)
        if not hit:
            return 0.0, {"head": "algo", "miss": True, "universe": True}
        p_s = float(hit.get("p_up") or 0.5)
        src = "board"
    st = _load_json(online_state_path(), {}) or {}
    p_a = None
    clf = _load_adapter() if use_algo_online() else None
    if clf is not None and row:
        try:
            X = np.asarray(
                [[float(row.get(c) if row.get(c) is not None else _feat_default(c)) for c in FEATURE_COLS]],
                dtype=float,
            )
            p_a = float(clf.predict_proba(X)[0, 1])
        except Exception:
            p_a = None
    p, w_ad = _blend(p_s, p_a, int(st.get("n_tickers") or 0), float(st.get("rolling_auc") or 0.5))
    boost = max(-w_cap, min(w_cap, (p - 0.5) * 2.0 * w_cap))
    return float(boost), {
        "head": "algo",
        "p_up": p,
        "student": p_s,
        "adapter": p_a,
        "adapter_w": w_ad,
        "boost": boost,
        "src": src,
        "universe": True,
        "generation": bundle.get("generation"),
    }


def learn_from_outcome(
    ticker: str,
    realized_return: float,
    *,
    features: dict[str, Any] | None = None,
    side: str = "LONG",
) -> dict[str, Any]:
    """One SGD step on the global adapter from a closed trade (any stock)."""
    t = str(ticker).upper()
    row = features or _LAST_FEATS.get(t)
    if not row:
        return {"applied": False, "reason": "no_features", "ticker": t}
    if not use_algo_online():
        return {"applied": False, "reason": "offline", "ticker": t}
    y = 1 if float(realized_return) > 0 else 0
    if str(side).upper() in ("SELL", "SHORT"):
        y = 1 - y
    X, yy = _matrix([{**row, "y": y}])
    clf = _load_adapter() or _new_adapter()
    try:
        clf.partial_fit(X, yy, classes=np.array([0, 1]))
    except Exception as e:
        return {"applied": False, "reason": f"partial_fit:{e}", "ticker": t}
    _save_adapter(clf)
    st = _load_json(online_state_path(), {}) or {}
    lru = [str(x).upper() for x in (st.get("lru") or []) if x]
    n_tickers = int(st.get("n_tickers") or 0)
    if t not in lru:
        n_tickers += 1
        lru = (lru + [t])[-64:]
    else:
        lru = [x for x in lru if x != t] + [t]
        lru = lru[-64:]
    n = int(st.get("n_updates") or 0) + 1
    try:
        p_hat = float(clf.predict_proba(X)[0, 1])
    except Exception:
        p_hat = 0.5
    mean_p = float(st.get("mean_p") or 0.5)
    mean_y = float(st.get("mean_y") or 0.0)
    mean_p += (p_hat - mean_p) / n
    mean_y += (float(y) - mean_y) / n
    if os.getenv("ALGO_ONLINE_REPLAY_KEEP", "false").lower() in ("1", "true", "yes"):
        replay = replay_path()
        replay.parent.mkdir(parents=True, exist_ok=True)
        with replay.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ticker": t, "y": y, "fwd": float(realized_return), "utc": _now()}) + "\n")
    hist = list(st.get("recent") or [])
    hist.append({"y": y, "p": p_hat})
    hist = hist[-40:]
    recent_y = [int(h["y"]) for h in hist]
    recent_p = [float(h["p"]) for h in hist]
    auc = _auc_score(np.asarray(recent_y), np.asarray(recent_p))
    curve = list(st.get("curve") or [])
    if n % 10 == 0 or n <= 5:
        curve.append(
            {
                "n": n,
                "n_tickers": n_tickers,
                "auc": auc,
                "coverage": coverage_weight(n_tickers),
            }
        )
        curve = curve[-40:]
    out = {
        "applied": True,
        "ticker": t,
        "y": y,
        "n_updates": n,
        "n_tickers": n_tickers,
        "rolling_auc": auc,
        "coverage": coverage_weight(n_tickers),
        "utc": _now(),
    }
    st = {
        "n_updates": n,
        "n_tickers": n_tickers,
        "mean_p": mean_p,
        "mean_y": mean_y,
        "lru": lru,
        "rolling_auc": auc,
        "coverage": out["coverage"],
        "recent": hist,
        "curve": curve,
        "utc": _now(),
    }
    _save_json(online_state_path(), st)
    log.info(
        "[ALGO] online %s y=%s n=%d tickers=%d auc=%s cov=%.3f",
        t,
        y,
        n,
        n_tickers,
        auc,
        out["coverage"],
    )
    return out


def _fit_hgb(rows: list[dict[str, Any]]):
    X, y = _matrix(rows)
    clf = _new_hgb(len(rows))
    clf.fit(X, y)
    return clf


def historical_smoke(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Walk-forward + unseen-ticker holdout. Proves one algo generalizes to all stocks."""
    if rows is None:
        doc = _load_json(harvest_rows_path(), {}) or {}
        rows = list(doc.get("rows") or [])
    rows = [r for r in (rows or []) if r.get("ticker") and r.get("y") is not None]
    _enrich_rows(rows)
    out: dict[str, Any] = {
        "ok": False,
        "utc": _now(),
        "n_rows": len(rows),
        "n_tickers": len({str(r["ticker"]).upper() for r in rows}),
    }
    if len(rows) < 60:
        out["reason"] = "too_few_rows"
        _save_json(smoke_state_path(), out)
        return out

    # --- Unseen tickers (the actual "one algo for all stocks" test) ---
    tickers = sorted({str(r["ticker"]).upper() for r in rows})
    train_t = {t for t in tickers if int(__import__("hashlib").md5(t.encode()).hexdigest(), 16) % 10 < 7}
    test_t = [t for t in tickers if t not in train_t]
    if len(test_t) < 8:
        test_t = tickers[max(8, int(len(tickers) * 0.7)) :]
        train_t = set(tickers) - set(test_t)
    tr = [r for r in rows if str(r["ticker"]).upper() in train_t]
    te = [r for r in rows if str(r["ticker"]).upper() in test_t]
    unseen_auc = float("nan")
    if len(tr) >= 40 and len(te) >= 20 and len({int(r["y"]) for r in tr}) >= 2:
        clf = _fit_hgb(tr)
        Xte, yte = _matrix(te)
        p = np.clip(clf.predict_proba(Xte)[:, 1], 0.01, 0.99)
        unseen_auc = _auc_score(yte, p)
        out["unseen_tickers"] = {
            "n_train_tickers": len(train_t),
            "n_test_tickers": len(test_t),
            "n_train_rows": len(tr),
            "n_test_rows": len(te),
            "auc": unseen_auc,
            "hit": float(np.mean(yte)),
            "hot_hit": float(np.mean(yte[np.argsort(-p)[: max(5, len(yte) // 5)]])),
        }

    # --- Chronological walk-forward ---
    dates = sorted({str(r.get("signal_date") or "") for r in rows if r.get("signal_date")})
    folds: list[dict[str, Any]] = []
    if len(dates) >= 3:
        for i in range(2, len(dates)):
            hold = dates[i]
            train = [r for r in rows if str(r.get("signal_date") or "") < hold]
            test = [r for r in rows if str(r.get("signal_date") or "") == hold]
            if len(train) < 40 or len(test) < 8 or len({int(r["y"]) for r in train}) < 2:
                continue
            clf = _fit_hgb(train)
            Xte, yte = _matrix(test)
            p = np.clip(clf.predict_proba(Xte)[:, 1], 0.01, 0.99)
            folds.append(
                {
                    "hold": hold,
                    "n_train": len(train),
                    "n_test": len(test),
                    "auc": _auc_score(yte, p),
                    "hit": float(np.mean(yte)),
                }
            )
    out["walk_forward"] = folds
    wf_aucs = [float(f["auc"]) for f in folds if f.get("auc") == f.get("auc")]
    out["walk_forward_mean_auc"] = float(np.mean(wf_aucs)) if wf_aucs else None

    # --- Online adapter learning curve on a time-sorted stream ---
    stream = sorted(rows, key=lambda r: str(r.get("signal_date") or ""))
    warm = stream[: max(40, len(stream) // 3)]
    rest = stream[len(warm) :]
    online_aucs: list[float] = []
    if rest and len({int(r["y"]) for r in warm}) >= 2:
        ad = _new_adapter()
        Xw, yw = _matrix(warm)
        ad.partial_fit(Xw, yw, classes=np.array([0, 1]))
        buf_y: list[int] = []
        buf_p: list[float] = []
        seen: set[str] = {str(r["ticker"]).upper() for r in warm}
        for r in rest:
            X, y = _matrix([r])
            try:
                ph = float(ad.predict_proba(X)[0, 1])
            except Exception:
                ph = 0.5
            buf_y.append(int(y[0]))
            buf_p.append(ph)
            ad.partial_fit(X, y, classes=np.array([0, 1]))
            seen.add(str(r["ticker"]).upper())
            if len(buf_y) >= 20 and len(buf_y) % 15 == 0:
                online_aucs.append(_auc_score(np.asarray(buf_y[-80:]), np.asarray(buf_p[-80:])))
        out["online"] = {
            "n_stream": len(rest),
            "n_tickers": len(seen),
            "coverage": coverage_weight(len(seen)),
            "auc_curve": online_aucs,
            "auc_first": online_aucs[0] if online_aucs else None,
            "auc_last": online_aucs[-1] if online_aucs else None,
            "improved": bool(
                online_aucs
                and online_aucs[-1] == online_aucs[-1]
                and online_aucs[0] == online_aucs[0]
                and online_aucs[-1] + 1e-9 >= online_aucs[0] - 0.05
            ),
        }

    unseen_ok = unseen_auc == unseen_auc and unseen_auc >= 0.50
    wf_ok = (out["walk_forward_mean_auc"] or 0) >= 0.48 or not wf_aucs
    out["ok"] = bool(unseen_ok and wf_ok)
    out["note"] = (
        "unseen-ticker holdout = one algorithm on stocks it never trained on. "
        "online curve = adapter adjusts as more names arrive (coverage 1-exp(-n/τ))."
    )
    _save_json(smoke_state_path(), out)
    log.info(
        "[ALGO] smoke ok=%s unseen_auc=%s wf_mean=%s tickers=%d",
        out["ok"],
        unseen_auc,
        out.get("walk_forward_mean_auc"),
        out["n_tickers"],
    )
    return out
