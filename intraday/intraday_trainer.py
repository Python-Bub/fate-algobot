"""Train per-ticker minute (5-minute fwd) and hourly (60-minute fwd) heads.

Saves ``models/intraday/{TICKER}_intraday.pkl`` for **every** ticker: real GBDT heads
when data allows, otherwise a **placeholder** bundle (neutral p=0.5, ``placeholder`` flag).

Inference: ``predict_intraday(...)`` — placeholders return ``p_up=0.5`` and ``placeholder: True``.
Bulk fill without overwriting trained files: ``python tools/backfill_intraday_placeholders.py``.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import GradientBoostingClassifier

from utils import log

from .data_loader_intraday import fetch_minute_bars
from .feature_engineering_intraday import (
    INTRADAY_FEATURES,
    add_intraday_targets,
    build_intraday_features,
)

MODEL_DIR = Path("models/intraday")
STATS_PATH = Path("data/intraday_train_stats.jsonl")


class _NeutralHead:
    """Picklable stand-in classifier: always p(up)=0.5 so every ticker can have a bundle on disk."""

    __slots__ = ()

    def predict(self, X) -> np.ndarray:  # noqa: ANN001
        n = len(X) if hasattr(X, "__len__") else 1
        return np.zeros(n, dtype=np.int64)

    def predict_proba(self, X) -> np.ndarray:  # noqa: ANN001
        n = len(X) if hasattr(X, "__len__") else 1
        return np.full((n, 2), 0.5, dtype=np.float64)


def _dump_intraday_bundle(
    ticker: str,
    *,
    model_minute: object | None,
    model_hour: object | None,
    trained_at: str,
    rows: int,
    stats: dict[str, object],
    placeholder: bool = False,
) -> Path:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = MODEL_DIR / f"{ticker.upper()}_intraday.pkl"
    mm = model_minute if model_minute is not None else _NeutralHead()
    mh = model_hour if model_hour is not None else _NeutralHead()
    payload: dict[str, object] = {
        "model_minutely": mm,
        "model_hourly": mh,
        "features": INTRADAY_FEATURES,
        "trained_at": trained_at,
        "rows": rows,
        "stats": {k: v for k, v in stats.items() if k not in ("ticker", "trained_at")},
    }
    if placeholder:
        payload["placeholder"] = True
    joblib.dump(payload, out_path)
    return out_path


def save_intraday_placeholder(
    ticker: str,
    reason: str,
    *,
    rows: int = 0,
    start: str | None = None,
    record_stats: bool = True,
    quiet: bool = False,
) -> Path | None:
    """Write a neutral bundle, or register in checkpoint only (network-first / slim disk)."""
    sym = ticker.upper()
    trained_at = dt.datetime.utcnow().isoformat()
    st = start or ""
    stats: dict[str, object] = {
        "ticker": sym,
        "rows": rows,
        "trained_at": trained_at,
        "start": st,
        "skipped": reason,
    }
    try:
        from data_platform.network_data import register_intraday_placeholder, skip_intraday_placeholder_disk

        if skip_intraday_placeholder_disk():
            register_intraday_placeholder(sym, reason, rows=rows)
            if not quiet:
                log.info("[INTRADAY] placeholder registered %s (%s) — no disk file", sym, reason)
            if record_stats:
                _append_stats({**stats, "saved": "", "placeholder": True, "disk": False})
            return None
    except ImportError:
        pass
    out = _dump_intraday_bundle(
        sym,
        model_minute=None,
        model_hour=None,
        trained_at=trained_at,
        rows=rows,
        stats=stats,
        placeholder=True,
    )
    if not quiet:
        log.info("[INTRADAY] placeholder saved %s (%s)", out, reason)
    if record_stats:
        _append_stats({**stats, "saved": str(out), "placeholder": True})
    return out


def _maybe_calibrate(base, X_train, y_train):
    """Wrap in isotonic CalibratedClassifierCV when there's enough class diversity."""
    if os.getenv("CALIBRATE_PROBA", "true").lower() not in ("1", "true", "yes"):
        return base
    try:
        if y_train.nunique() < 2 or len(y_train) < 200:
            return base
        cv = int(os.getenv("CALIBRATE_CV", "3"))
        cal = CalibratedClassifierCV(base, method=os.getenv("CALIBRATE_METHOD", "isotonic"), cv=cv)
        cal.fit(X_train, y_train)
        return cal
    except Exception:
        return base


def _acc_at_top_q(y_true: np.ndarray, proba: np.ndarray, q: float = 0.2) -> float:
    n = len(y_true)
    if n == 0:
        return float("nan")
    k = max(1, int(n * q))
    order = np.argsort(-np.asarray(proba))[:k]
    return float((np.asarray(y_true)[order] == 1).mean())


def _chronological_split(X: pd.DataFrame, y: pd.Series, frac: float = 0.8):
    cut = int(len(X) * frac)
    cut = max(50, min(cut, len(X) - 20))
    return X.iloc[:cut], X.iloc[cut:], y.iloc[:cut], y.iloc[cut:]


def _fit_head(X: pd.DataFrame, y: pd.Series, label: str, ticker: str) -> tuple[object | None, dict]:
    if len(X) < 200 or y.nunique() < 2:
        return None, {"skipped": "too_few_rows_or_classes"}
    Xtr, Xte, ytr, yte = _chronological_split(X, y, float(os.getenv("INTRADAY_TRAIN_FRAC", "0.8")))
    base = GradientBoostingClassifier(
        n_estimators=int(os.getenv("INTRADAY_TREES", "120")),
        max_depth=int(os.getenv("INTRADAY_MAX_DEPTH", "3")),
        learning_rate=float(os.getenv("INTRADAY_LR", "0.07")),
        random_state=42,
    )
    clf = _maybe_calibrate(base, Xtr, ytr)
    if clf is base:
        clf.fit(Xtr, ytr)
    proba = clf.predict_proba(Xte)[:, 1]
    acc = float(((proba > 0.5).astype(int) == yte.values).mean())
    top = _acc_at_top_q(yte.to_numpy(), proba, float(os.getenv("ACC_TOP_Q", "0.2")))
    log.info(
        "[INTRADAY] %s %s acc=%.4f acc@top20=%.4f train=%d test=%d",
        ticker, label, acc, top, len(Xtr), len(Xte),
    )
    return clf, {f"{label}_acc": acc, f"{label}_top20": top, f"{label}_train": len(Xtr), f"{label}_test": len(Xte)}


def train_intraday(ticker: str, start: str | None = None) -> dict:
    """Train minute + hourly heads for a single ticker. Returns a stats dict."""
    if start is None:
        # Alpaca free tier serves the last ~2 years of IEX minute data.
        days_back = int(os.getenv("INTRADAY_LOOKBACK_DAYS", "240"))
        start = (dt.date.today() - dt.timedelta(days=days_back)).isoformat()

    sym = ticker.upper()
    log.info("[INTRADAY] %s begin (start=%s)", sym, start)
    bars = fetch_minute_bars(sym, start=start, timeframe="1Min")
    if bars.empty or len(bars) < 800:
        log.warning("[INTRADAY] %s skipped — only %d minute bars", sym, len(bars))
        out = save_intraday_placeholder(sym, "insufficient_data", rows=int(len(bars)), start=start)
        return {"ticker": sym, "skipped": "insufficient_data", "rows": int(len(bars)), "saved": str(out), "placeholder": True}

    feats = build_intraday_features(bars)
    feats = add_intraday_targets(feats, horizons=(5, 60))
    feats = feats.dropna(subset=INTRADAY_FEATURES + ["target_h5", "target_h60"])
    if feats.empty:
        out = save_intraday_placeholder(sym, "all_nan_after_features", rows=0, start=start)
        return {"ticker": sym, "skipped": "all_nan_after_features", "saved": str(out), "placeholder": True}

    X = feats[INTRADAY_FEATURES].astype(np.float64)
    y_min = feats["target_h5"].astype(int)
    y_hr = feats["target_h60"].astype(int)

    trained_at = dt.datetime.utcnow().isoformat()
    stats: dict[str, object] = {
        "ticker": sym,
        "rows": int(len(X)),
        "trained_at": trained_at,
        "start": start,
    }

    model_minute, mstats = _fit_head(X, y_min, "minute", sym)
    model_hour, hstats = _fit_head(X, y_hr, "hour", sym)
    stats.update(mstats)
    stats.update(hstats)

    used_ph = model_minute is None and model_hour is None
    out_path = _dump_intraday_bundle(
        sym,
        model_minute=model_minute,
        model_hour=model_hour,
        trained_at=trained_at,
        rows=int(len(X)),
        stats=stats,
        placeholder=bool(used_ph),
    )
    log.info("[INTRADAY] saved %s", out_path)
    stats["saved"] = str(out_path)
    if used_ph:
        stats["placeholder"] = True
    _append_stats(stats)
    return stats


def _append_stats(stats: dict) -> None:
    try:
        STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with STATS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({k: (str(v) if isinstance(v, dt.datetime) else v) for k, v in stats.items()}) + "\n")
    except Exception:
        pass


def predict_intraday(ticker: str, row: pd.Series, horizon: str = "minutely") -> dict[str, object]:
    """Predict from a saved intraday bundle. ``row`` must contain the INTRADAY_FEATURES."""
    p = MODEL_DIR / f"{ticker.upper()}_intraday.pkl"
    if not p.is_file():
        return {"pred": 0, "p_up": 0.5, "missing": True}
    bundle = joblib.load(p)
    placeholder = bool(bundle.get("placeholder"))
    if placeholder:
        return {"pred": 0, "p_up": 0.5, "missing": True, "placeholder": True}
    feats = list(bundle.get("features", INTRADAY_FEATURES))
    head_key = "model_minutely" if horizon in ("minutely", "minute", "5m", "5min") else "model_hourly"
    head = bundle.get(head_key)
    if head is None:
        head = bundle.get("model_minutely") or bundle.get("model_hourly")
    if head is None:
        return {"pred": 0, "p_up": 0.5, "missing": True}
    vals = {}
    idx = getattr(row, "index", None)
    for c in feats:
        try:
            if idx is not None and c in idx:
                v = row[c]
            elif isinstance(row, dict) and c in row:
                v = row[c]
            else:
                v = 0.0
            vals[c] = 0.0 if v is None or (isinstance(v, float) and v != v) else float(v)
        except Exception:
            vals[c] = 0.0
    x = pd.DataFrame([vals])
    x = x.replace([np.inf, -np.inf], 0).fillna(0)
    p_up = float(head.predict_proba(x)[0, 1])
    return {"pred": 1 if p_up >= 0.5 else 0, "p_up": p_up, "head_used": head_key}


def train_intraday_universe(
    tickers: list[str] | None = None,
    checkpoint_path: str = "data/intraday_train_checkpoint.json",
    max_symbols: int | None = None,
    full_universe: bool = False,
) -> None:
    """Loop over tickers training both minute and hourly heads. Resumable."""
    if tickers is None:
        if full_universe:
            try:
                from universe_provider import load_universe_with_cap

                tickers = load_universe_with_cap(max_symbols=max_symbols)
                log.warning(
                    "[INTRADAY] FULL-UNIVERSE mode: %d tickers queued from universe_provider",
                    len(tickers),
                )
            except Exception as e:
                log.exception("[INTRADAY] full-universe load failed (%s) — falling back to config", e)
                tickers = []
        if not tickers:
            try:
                from config import TRAIN_TICKERS as _t

                tickers = list(_t)
            except Exception:
                tickers = []
    if not tickers:
        log.warning("[INTRADAY] no tickers provided")
        return
    if max_symbols:
        tickers = tickers[:max_symbols]

    done: set[str] = set()
    cp = Path(checkpoint_path)
    if cp.is_file():
        try:
            done = set(json.loads(cp.read_text()).get("done", []))
        except Exception:
            pass

    for i, t in enumerate(tickers, 1):
        sym = t.upper()
        if sym in done:
            log.info("[INTRADAY] (%d/%d) %s skip (checkpoint)", i, len(tickers), sym)
            continue
        try:
            train_intraday(sym)
            done.add(sym)
            try:
                cp.parent.mkdir(parents=True, exist_ok=True)
                cp.write_text(json.dumps({"done": sorted(done)}))
            except Exception:
                pass
        except Exception as e:
            log.warning("[INTRADAY] %s failed: %s", sym, e)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default=None, help="single ticker")
    ap.add_argument("--all", action="store_true", help="train all config.TRAIN_TICKERS")
    ap.add_argument(
        "--full-universe",
        action="store_true",
        help="train EVERY ticker in the US universe (~11k, resumable via checkpoint)",
    )
    ap.add_argument("--max-symbols", type=int, default=None)
    args = ap.parse_args()
    if args.ticker:
        train_intraday(args.ticker)
    else:
        train_intraday_universe(max_symbols=args.max_symbols, full_universe=args.full_universe)
