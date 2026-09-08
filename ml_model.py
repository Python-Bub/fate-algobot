import os
import time
import typing
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

from feature_engineering import build_features
from model_estimators import make_long_classifier, make_short_classifier
from utils import log

_BUNDLE_CACHE: dict[str, tuple[float, dict]] = {}

FEATURES = [
    "rsi",
    "volatility",
    "vol_ch",
    "price_range",
    "lag_1_return",
    "lag_2_return",
    "lag_3_return",
    "lag_1_sentiment",
    "lag_2_sentiment",
    "lag_3_sentiment",
    "sentiment",
    "is_earnings_day",
    "days_to_earnings",
    "vol_regime_ratio",
    "vol_of_vol_20",
    "tail_risk_30",
    "earnings_decay",
    "event_pre_window",
    "event_post_window",
    "event_dte_le1",
    "sentiment_decay_3",
    "sentiment_decay_10",
    "sentiment_impulse",
    "intraday_spread",
    "close_loc_in_range",
    "turnover_z_20",
    "range_compression_5",
    "trend_state_5",
    "trend_state_20",
    "regime_transition_flag",
    "shock_state",
    "mom_20",
    "mom_60",
    "mom_accel",
    "beta_proxy_60",
    "alpha_proxy_20",
    # Causal extras (same in train + live via `signals/train_feature_enrich.py`)
    "ur_score",
    "fred_spread_10y2y",
    # Industry co-movement (50-bucket baskets, factor rotation)
    "industry_ret_1d",
    "industry_ret_5d",
    "industry_beta_60",
    "industry_residual_1d",
    "industry_z_20",
    "nasdaq_beta_60",
    "factor_rate_tilt",
    "factor_expansion_tilt",
    "industry_sympathy_score",
    "industry_leader_momentum",
    # Classic quant strategies (analytics/classic_quant_features.py).
    "sma_50_over_200",
    "sma_golden_cross",
    "ema_12_over_26",
    "macd_line",
    "macd_signal",
    "macd_hist",
    "price_roc_5",
    "volume_ratio_20",
    "vol_confirmed_mom",
    "dist_from_20d_high",
    "dist_from_52w_high",
    "dist_from_52w_low",
    "breakout_20d_high",
    "bb_pct_b",
    "bb_width",
    "bb_oversold",
    "bb_overbought",
    "rsi_oversold",
    "rsi_overbought",
    "rsi_centered",
    "atr_14",
    "atr_frac",
    "vwap_20",
    "close_vs_vwap",
    "donchian_pos_55",
    "vol_climax_z",
    "atr_channel_pos",
    "close_stretch_20",
    "wick_reject",
    # Historical Finnhub news + optional dated transcripts (`signals/train_news_history.py`)
    "news_sent_roll_5d",
    "news_intensity_roll_5d",
    "news_sent_trend_10d",
    "transcript_sent_roll_5d",
]


def _sanitize_X(X: pd.DataFrame) -> pd.DataFrame:
    X = X.replace([np.inf, -np.inf], 0).fillna(0)
    return X.astype(np.float64)


def _neutral_earnings_defaults() -> dict[str, float]:
    nd = float(os.getenv("EARNINGS_NEUTRAL_DTE", "90"))
    return {
        "days_to_earnings": nd,
        "is_earnings_day": 0.0,
        "earnings_decay": float(np.exp(-abs(nd) / 5.0)),
        "event_pre_window": 0.0,
        "event_post_window": 0.0,
        "event_dte_le1": 0.0,
    }


def _row_to_feature_matrix(row: pd.Series, feats: list[str]) -> pd.DataFrame:
    """Align inference row to bundle feature list — fill missing cols with train-time neutrals."""
    defaults = _neutral_earnings_defaults()
    data: dict[str, float] = {}
    for c in feats:
        if c in row.index:
            try:
                data[c] = float(row[c])
            except (TypeError, ValueError):
                data[c] = float(defaults.get(c, 0.0))
        elif c in defaults:
            data[c] = defaults[c]
        else:
            data[c] = 0.0
    if "earnings_decay" in feats and "days_to_earnings" in data:
        dte = data.get("days_to_earnings", defaults["days_to_earnings"])
        data.setdefault("earnings_decay", float(np.exp(-abs(dte) / 5.0)))
    return _sanitize_X(pd.DataFrame([data]))


def _align_x_to_model(model: typing.Any, x: pd.DataFrame) -> pd.DataFrame:
    """Reindex inference matrix to the columns each estimator was trained on."""
    names = getattr(model, "feature_names_in_", None)
    if names is not None and len(names):
        return x.reindex(columns=list(names), fill_value=0.0)
    fn = getattr(model, "feature_name_", None)
    if fn:
        return x.reindex(columns=list(fn), fill_value=0.0)
    if hasattr(model, "clfs"):  # ProbaBlend
        return x
    n = getattr(model, "n_features_in_", None)
    if n is not None and x.shape[1] > int(n):
        return x.iloc[:, : int(n)]
    return x


def _proba_up(model: typing.Any, x: pd.DataFrame) -> float:
    x = _align_x_to_model(model, x)
    proba = model.predict_proba(x)[0]
    classes = list(model.classes_)
    if 1 in classes:
        return float(proba[classes.index(1)])
    if 0 in classes:
        # One-class "down" model: P(up) = 1 - P(down), not proba.max() (~1.0).
        return float(1.0 - proba[classes.index(0)])
    return 0.5


def train_model(df: pd.DataFrame, model_path: str) -> None:
    if df.empty or "target" not in df.columns or "target_long" not in df.columns:
        raise ValueError("Training dataframe is empty or missing targets")

    d = df.dropna(subset=["target", "target_long"])
    missing = [c for c in FEATURES if c not in d.columns]
    if missing:
        raise ValueError(f"Missing feature columns: {missing}")

    active = []
    dropped = []
    for c in FEATURES:
        if c not in d.columns:
            dropped.append(c)
            continue
        s = d[c].astype(float)
        if int(s.nunique(dropna=False)) <= 1 or float(s.var()) < 1e-12:
            dropped.append(c)
            continue
        active.append(c)
    if len(active) < 6:
        raise ValueError(f"Too few active features after pruning: {len(active)}")
    if dropped:
        log.info("[ML] Dropped %d dead features: %s", len(dropped), dropped[:20])

    X = _sanitize_X(d[active])
    y_s = d["target"].astype(int)
    y_l = d["target_long"].astype(int)

    use_ts = os.getenv("TRAIN_TIME_ORDER_SPLIT", "true").lower() in ("1", "true", "yes")
    if use_ts:
        X = X.sort_index()
        y_s = y_s.reindex(X.index)
        y_l = y_l.reindex(X.index)
        frac = float(os.getenv("TRAIN_TEST_FRACTION", "0.2"))
        n = len(X)
        k = int(n * (1.0 - frac))
        k = max(min(10, n // 3), min(k, n - max(5, int(n * 0.05))))
        X_train, X_test = X.iloc[:k], X.iloc[k:]
        y_train, y_test = y_s.iloc[:k], y_s.iloc[k:]
        yl_train, yl_test = y_l.iloc[:k], y_l.iloc[k:]
    else:
        X_train, X_test, y_train, y_test, yl_train, yl_test = train_test_split(
            X,
            y_s,
            y_l,
            test_size=0.2,
            random_state=42,
            stratify=y_s if y_s.nunique() > 1 else None,
        )

    ms = make_short_classifier(42)
    ms.fit(X_train, y_train)
    acc_s = accuracy_score(y_test, ms.predict(X_test))
    log.info("[ML] Short horizon hold-out accuracy: %.4f (backend=%s)", acc_s, os.getenv("ML_BACKEND", "rf"))

    ml = make_long_classifier(43)
    ml.fit(X_train, yl_train)
    acc_l = accuracy_score(yl_test, ml.predict(X_test))
    log.info("[ML] Long horizon hold-out accuracy: %.4f", acc_l)

    os.makedirs(os.path.dirname(model_path) or ".", exist_ok=True)
    bundle = {
        "model_short": ms,
        "model_long": ml,
        "model": ms,
        "features": list(active),
        "long_horizon_days": int(os.getenv("LONG_HORIZON_DAYS", "20")),
        "ml_backend": os.getenv("ML_BACKEND", "rf"),
        "price_source": os.getenv("PRICE_DATA_SOURCE", "yfinance"),
    }
    joblib.dump(bundle, model_path)
    try:
        from analytics.feature_decision_weights import column_ic_weights

        icw = column_ic_weights(X_train, y_train)
        bundle["feature_ic_weights"] = icw
        joblib.dump(bundle, model_path)
    except Exception as e:
        log.debug("[ML] feature IC weights skipped: %s", e)
    log.info("[ML] Saved dual bundle to %s", model_path)


def optimize_model(ticker: str, start_date: str = "2023-01-01", end_date: str | None = None) -> str:
    df = build_features(ticker, start_date, end_date)
    if df.empty:
        raise RuntimeError(f"No features for {ticker}")
    model_path = os.path.join("models", f"{ticker}_model.pkl")
    train_model(df, model_path)
    return model_path


def load_raw_bundle(model_path: str) -> dict:
    if not os.path.isfile(model_path):
        raise FileNotFoundError(model_path)
    try:
        mtime = os.path.getmtime(model_path)
    except OSError:
        mtime = 0.0
    max_sz = int(os.getenv("MODEL_BUNDLE_CACHE_SIZE", "512"))
    if max_sz > 0:
        cached = _BUNDLE_CACHE.get(model_path)
        if cached is not None and cached[0] == mtime:
            return cached[1]
    # Strong-retrain bundles may pickle ProbaBlend as __main__._ProbaBlend; register alias.
    try:
        import __main__

        from analytics.proba_blend import ProbaBlend

        if not hasattr(__main__, "_ProbaBlend"):
            __main__._ProbaBlend = ProbaBlend
    except Exception:
        pass
    raw = joblib.load(model_path)
    if not isinstance(raw, dict):
        raw = {"model": raw, "features": list(FEATURES)}
    if max_sz > 0:
        if len(_BUNDLE_CACHE) >= max_sz:
            _BUNDLE_CACHE.pop(next(iter(_BUNDLE_CACHE)))
        _BUNDLE_CACHE[model_path] = (mtime, raw)
    return raw


def load_bundle(model_path: str) -> tuple[typing.Any, list[str]]:
    raw = load_raw_bundle(model_path)
    m = raw.get("model_short") or raw.get("model")
    if m is None:
        raise ValueError("Invalid model bundle")
    feats = list(raw.get("features", FEATURES))
    return m, feats


def _safe_head_proba(raw: dict, key: str, x: pd.DataFrame) -> float | None:
    head = raw.get(key)
    if head is None:
        return None
    try:
        return float(_proba_up(head, x))
    except Exception:
        return None


def predict_row_details(model_path: str, row: pd.Series) -> dict[str, typing.Any]:
    """Return pred, final p_up, and short/long/daily/xlong components for multi-TF gating."""
    raw = load_raw_bundle(model_path)
    feats = list(raw.get("features", FEATURES))
    x = _row_to_feature_matrix(row, feats)

    ms = raw.get("model_short") or raw.get("model")
    ml = raw.get("model_long")
    mm = raw.get("model_meta")

    out: dict[str, typing.Any] = {
        "pred": 0,
        "p_up": 0.0,
        "p_short": None,
        "p_long": None,
        "p_daily": None,
        "p_xlong": None,
        "p_blend": None,
    }

    if ms is not None and ml is not None:
        ps = _proba_up(ms, x)
        pl = _proba_up(ml, x)
        pdaily = _safe_head_proba(raw, "model_daily", x)
        pxlong = _safe_head_proba(raw, "model_xlong", x)
        w = float(os.getenv("SHORT_MODEL_WEIGHT", "0.55"))
        try:
            from analytics.vector_math import logit_blend

            p_blend = logit_blend([ps, pl], [w, 1.0 - w])
        except Exception:
            p_blend = w * ps + (1.0 - w) * pl
        p_up = float(p_blend)
        if mm is not None and os.getenv("USE_META_STACK_INFER", "true").lower() in ("1", "true", "yes"):
            try:
                from analytics.meta_stack import apply_meta_stack

                meta_row = row.to_dict()
                meta_row["p_short"] = float(ps)
                meta_row["p_long"] = float(pl)
                meta_row["p_daily"] = float(pdaily if pdaily is not None else ps)
                meta_row["p_xlong"] = float(pxlong if pxlong is not None else pl)
                p_up = float(apply_meta_stack(mm, meta_row))
            except Exception as e:
                log.debug("[ML] meta infer skipped: %s", e)
        # Soft multi-TF blend: smart path uses all horizons, not just speed (HFT).
        if os.getenv("USE_MULTI_TF_BLEND", "true").lower() in ("1", "true", "yes"):
            w_d = float(os.getenv("TF_BLEND_DAILY", "0.12"))
            w_x = float(os.getenv("TF_BLEND_XLONG", "0.12"))
            parts: list[tuple[float, float]] = [(max(0.0, 1.0 - w_d - w_x), float(p_up))]
            if pdaily is not None:
                parts.append((w_d, float(pdaily)))
            if pxlong is not None:
                parts.append((w_x, float(pxlong)))
            tw = sum(w for w, _ in parts) or 1.0
            try:
                from analytics.vector_math import logit_blend

                p_up = logit_blend([p for _, p in parts], [w for w, _ in parts])
            except Exception:
                p_up = float(sum(w * p for w, p in parts) / tw)
        out["p_short"] = float(ps)
        out["p_long"] = float(pl)
        out["p_daily"] = float(pdaily) if pdaily is not None else None
        out["p_xlong"] = float(pxlong) if pxlong is not None else None
        out["p_blend"] = float(p_blend)
        out["p_up"] = float(p_up)
        out["pred"] = 1 if p_up >= 0.5 else 0
        return out

    if ms is None:
        raise ValueError("No model in bundle")
    p_up = float(_proba_up(ms, x))
    out["p_up"] = p_up
    out["pred"] = int(ms.predict(x)[0])
    return out


def predict_row(model_path: str, row: pd.Series) -> tuple[int, float]:
    d = predict_row_details(model_path, row)
    return int(d["pred"]), float(d["p_up"])


# Map a desired holding window in days → which head to use.
_HORIZON_ALIAS = {
    "daily": "model_daily",
    "1d": "model_daily",
    "weekly": "model_short",   # SHORT_TARGET_HORIZON defaults to 5
    "5d": "model_short",
    "short": "model_short",
    "long": "model_long",
    "20d": "model_long",
    "xlong": "model_xlong",
    "60d": "model_xlong",
    "quarterly": "model_xlong",
}


def _resolve_horizon_key(horizon: str | int | None) -> str:
    if horizon is None:
        return "model_short"
    if isinstance(horizon, int):
        # Pick nearest by absolute distance to known horizons.
        candidates = [(1, "model_daily"), (5, "model_short"), (20, "model_long"), (60, "model_xlong")]
        return min(candidates, key=lambda c: abs(c[0] - horizon))[1]
    key = str(horizon).lower().strip()
    return _HORIZON_ALIAS.get(key, "model_short")


def _min_head_top20_live() -> float:
    return float(os.getenv("MIN_HEAD_TOP20", "0.45"))


def _pick_head(raw: dict, preferred: str, *, strict: bool = False) -> str:
    """Choose model head; fall back when preferred is missing or failed quality gate."""
    if strict:
        return preferred if raw.get(preferred) is not None else preferred

    hq = raw.get("head_quality") or {}
    min_top = _min_head_top20_live()

    def _ok(key: str) -> bool:
        if raw.get(key) is None:
            return False
        # Prefer a filled multi-TF head over silence — weak heads still beat fallbacks.
        if os.getenv("LIVE_ALLOW_WEAK_HEADS", "true").lower() in ("1", "true", "yes"):
            return True
        q = hq.get(key) or {}
        top = q.get("top20")
        if top is None:
            return True
        try:
            return float(top) >= min_top
        except (TypeError, ValueError):
            return True

    if _ok(preferred):
        return preferred

    fallbacks = {
        "model_daily": ["model_short", "model_long", "model_xlong"],
        "model_xlong": ["model_long", "model_short", "model_daily"],
        "model_long": ["model_short", "model_daily", "model_xlong"],
        "model_short": ["model_long", "model_daily", "model_xlong"],
    }
    for key in fallbacks.get(preferred, ["model_short", "model_long"]):
        if _ok(key):
            return key
    return preferred if raw.get(preferred) is not None else "model_short"


def predict_row_horizon(model_path: str, row: pd.Series, horizon: str | int = "weekly") -> dict[str, typing.Any]:
    """Like ``predict_row_details`` but explicitly picks the head matching ``horizon``.

    Falls back to ``model_short`` (current weekly default) when the requested head
    wasn't trained for this ticker. Returns the same dict shape as ``predict_row_details``
    so existing callers can drop-in upgrade.
    """
    raw = load_raw_bundle(model_path)
    feats = list(raw.get("features", FEATURES))
    x = _row_to_feature_matrix(row, feats)

    strict = os.getenv("HORIZON_STRICT_HEADS", "true").lower() in ("1", "true", "yes")
    key = _resolve_horizon_key(horizon)
    preferred = key
    key = _pick_head(raw, key, strict=strict)
    head = raw.get(key)
    if head is None:
        if strict:
            return {
                "pred": 0,
                "p_up": None,
                "p_short": None,
                "p_long": None,
                "p_blend": None,
                "head_used": preferred,
                "head_missing": True,
                "horizon_days": None,
            }
        head = raw.get("model_short") or raw.get("model")
    if head is None:
        raise ValueError("No model in bundle")

    p_up = float(_proba_up(head, x))
    horizons_meta = raw.get("horizons") or {}
    return {
        "pred": 1 if p_up >= 0.5 else 0,
        "p_up": p_up,
        "p_short": None,
        "p_long": None,
        "p_blend": None,
        "head_used": key,
        "head_missing": False,
        "horizon_days": horizons_meta.get(key.replace("model_", ""), None),
    }


def predict(model_path: str | None, features: list | np.ndarray) -> int:
    if not model_path or not os.path.isfile(model_path):
        log.warning("[ML] MODEL_PATH missing or file not found; returning hold (0)")
        return 0
    model, feats = load_bundle(model_path)
    arr = np.asarray(features, dtype=float).reshape(1, -1)
    if arr.shape[1] != len(feats):
        raise ValueError(f"Expected {len(feats)} features, got {arr.shape[1]}")
    x = _sanitize_X(pd.DataFrame(arr, columns=feats))
    return int(model.predict(x)[0])


def load_model_and_predict(model_path: str, row: pd.Series) -> tuple[int, float]:
    return predict_row(model_path, row)


if __name__ == "__main__":
    _ex = os.getenv("ML_EXAMPLE_TICKER", "SPY")
    mp = optimize_model(_ex, "2023-01-01", None)
    df = build_features(_ex, "2023-01-01", None)
    df = df.dropna(subset=["target", "target_long"])
    sig, conf = predict_row(mp, df.iloc[-2])
    print(f"Example signal={sig} p_up={conf:.3f} path={mp}")
