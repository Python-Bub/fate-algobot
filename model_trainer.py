import json
import os
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.metrics import accuracy_score

from feature_engineering import build_features
from ml_model import FEATURES
from model_estimators import make_fast_classifier, make_short_classifier, make_long_classifier
from utils import log


def _sanitize(df):
    return df.replace([np.inf, -np.inf], 0).fillna(0).astype(np.float64)


def _safe_stratify(y, min_per_class: int = 2):
    """Return y when stratification is safe, else None.

    sklearn's stratified split needs >=2 of each class; many micro-cap or new tickers
    only ever drift one direction in their short history (e.g. ARQQW), so we just
    fall back to a non-stratified split instead of crashing the whole batch.
    """
    try:
        vc = y.value_counts()
        if len(vc) < 2 or int(vc.min()) < min_per_class:
            return None
        return y
    except Exception:
        return None


def _class_health(y) -> tuple[int, int]:
    vc = y.value_counts()
    return int(vc.min() if len(vc) else 0), int(len(vc))


def _prune_dead_features(X, cols: list[str]) -> list[str]:
    """Drop a column only when it's *truly* constant for this ticker.

    Two safeguards from the previous overly-aggressive version:
      1. We drop on `nunique <= 1` only (no low-variance cutoff). A column with
         small but real variance (e.g. ``rsi_oversold`` that triggers once) still
         carries information.
      2. Columns in `KEEP_CROSS_SECTIONAL` are preserved even if constant for *this*
         ticker, because they vary across the universe (FRED spread, classic-quant
         flags, news rolls). The model can ignore them via tree splits but the
         column must stay in the feature matrix so inference rows align.
    """
    import pandas as pd

    keep_cross = {
        # Macro / regime (varies across tickers, may be flat for one name)
        "fred_spread_10y2y",
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
        # Classic quant flags (binary; flat for some symbols)
        "sma_golden_cross",
        "breakout_20d_high",
        "bb_oversold",
        "bb_overbought",
        "rsi_oversold",
        "rsi_overbought",
        # News + transcripts (zero by design for tickers without coverage)
        "news_sent_roll_5d",
        "news_intensity_roll_5d",
        "news_sent_trend_10d",
        "transcript_sent_roll_5d",
        # Causal U&R (rare event score; can be 0 on quiet names)
        "ur_score",
    }

    if not isinstance(X, pd.DataFrame):
        return cols
    kept: list[str] = []
    dropped: list[str] = []
    kept_constant: list[str] = []
    for c in cols:
        if c not in X.columns:
            dropped.append(c)
            continue
        s = X[c].astype(float)
        nun = int(s.nunique(dropna=False))
        if nun <= 1:
            if c in keep_cross:
                kept.append(c)
                kept_constant.append(c)
                continue
            dropped.append(c)
            continue
        kept.append(c)
    if dropped:
        log.info("[TRAIN] Dropped %d dead features: %s", len(dropped), dropped[:20])
    if kept_constant:
        log.debug("[TRAIN] Kept %d cross-sectional constants: %s", len(kept_constant), kept_constant)
    return kept


def _auto_xgb_scale_pos_weight(y, user_locked: bool) -> None:
    """Set XGB scale_pos_weight from class counts unless user explicitly set it."""
    if user_locked:
        return
    vc = pd.Series(y).value_counts()
    if len(vc) < 2 or 0 not in vc.index or 1 not in vc.index:
        return
    n0, n1 = float(vc[0]), float(vc[1])
    spw = max(n0 / max(n1, 1e-9), 1e-6)
    os.environ["XGB_SCALE_POS_WEIGHT"] = str(spw)


def _purge_ticker_artifacts(ticker: str) -> None:
    """Hard reset of saved models for this ticker before retraining.

    Enable with `TRAIN_PURGE_ARTIFACTS=true` or `FRESH_MODEL_REBUILD=true` (kill-switch redo).
    """
    purge = (
        os.getenv("TRAIN_PURGE_ARTIFACTS", "").lower() in ("1", "true", "yes")
        or os.getenv("FRESH_MODEL_REBUILD", "").lower() in ("1", "true", "yes")
    )
    if not purge:
        return
    paths = [
        os.path.join("models", f"{ticker}_model.pkl"),
        os.path.join("models", "meta", f"{ticker}_meta.pkl"),
    ]
    for p in paths:
        if os.path.isfile(p):
            try:
                os.remove(p)
                log.warning("[TRAIN] Purged stale artifact %s", p)
            except OSError as e:
                log.warning("[TRAIN] Could not purge %s: %s", p, e)


def _train_val_matrix_split(
    X: pd.DataFrame, y: pd.Series, y_long: pd.Series, ticker: str
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Chronological holdout (default) avoids random-split leakage that inflates accuracy."""
    use_ts = os.getenv("TRAIN_TIME_ORDER_SPLIT", "true").lower() in ("1", "true", "yes")
    if not use_ts:
        return train_test_split(
            X,
            y,
            y_long,
            test_size=float(os.getenv("TRAIN_TEST_FRACTION", "0.2")),
            random_state=42,
            stratify=_safe_stratify(y),
        )
    Xtr, Xte, ytr, yte = _chrono_split_xy(X, y, ticker=ticker, tag="H20d")
    yltr = y_long.reindex(Xtr.index)
    ylte = y_long.reindex(Xte.index)
    return Xtr, Xte, ytr, yte, yltr, ylte


def _embargo_bars_for_tag(tag: str) -> int:
    """Gap between train end and test start so forward labels cannot see the holdout."""
    raw = os.getenv("TRAIN_EMBARGO_BARS", "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    t = (tag or "").lower()
    if "60" in t or "xlong" in t:
        return int(os.getenv("TRAIN_EMBARGO_XLONG", "60"))
    if "20" in t or t.endswith("long") or "h20" in t:
        return int(os.getenv("TRAIN_EMBARGO_LONG", "20"))
    if "5d" in t or "week" in t or "short" in t or "h5" in t:
        return int(os.getenv("TRAIN_EMBARGO_SHORT", "5"))
    if "1d" in t or "daily" in t or "h1d" in t:
        return int(os.getenv("TRAIN_EMBARGO_DAILY", "1"))
    return int(os.getenv("TRAIN_EMBARGO_DEFAULT", "0"))


def _chrono_split_xy(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    ticker: str = "",
    tag: str = "",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Same holdout semantics as main trainer: TRAIN_TEST_FRACTION = *test* size (default 20%).

    When ``tag`` implies a forward horizon (H1d/H20d/H60d), drop an embargo
    of that many bars from the *end of train* so labels cannot peek into test.
    """
    Xs = X.sort_index()
    ys = y.reindex(Xs.index)
    n = len(Xs)
    frac = float(os.getenv("TRAIN_TEST_FRACTION", "0.2"))
    k = int(n * (1.0 - frac))
    k = max(min(10, n // 3), min(k, n - max(5, max(3, int(n * 0.05)))))
    emb = _embargo_bars_for_tag(tag)
    min_train = max(20, int(n * 0.35))
    train_end = k
    if emb > 0:
        train_end = min(k, max(min_train, k - emb))
    label = f"{ticker} {tag}".strip()
    if ticker:
        log.info(
            "[TRAIN] %s chronological split train=%d embargo=%d test=%d (last %.0f%% = holdout)",
            label or ticker,
            train_end,
            max(0, k - train_end),
            n - k,
            100 * frac,
        )
    return Xs.iloc[:train_end], Xs.iloc[k:], ys.iloc[:train_end], ys.iloc[k:]


def _maybe_calibrate(clf, X_train, y_train):
    """Wrap classifier in isotonic calibration when CALIBRATE_PROBA=true.

    Calibration makes "p=0.7" mean roughly 70% empirical hit-rate, which is what we
    actually need for confidence-thresholded trading. Falls back to the raw clf on
    any failure (e.g. too-few rows for cv) so a single ticker never aborts the batch.
    """
    if os.getenv("CALIBRATE_PROBA", "true").lower() not in ("1", "true", "yes"):
        return clf
    try:
        from sklearn.calibration import CalibratedClassifierCV
        method = os.getenv("CALIBRATE_METHOD", "isotonic")
        cv = int(os.getenv("CALIBRATE_CV", "3"))
        cal = CalibratedClassifierCV(estimator=clf, method=method, cv=cv)
        cal.fit(X_train, y_train)
        return cal
    except Exception as e:
        log.debug("[CAL] fallback to raw clf: %s", e)
        return clf


def _model_base_count(est) -> int:
    """Ensemble base count for logs; calibrated / single estimators → 1."""
    fitted = getattr(est, "fitted_", None)
    if isinstance(fitted, list):
        return len(fitted)
    return 1


def _acc_at_top_q(y_true, proba, q: float = 0.2) -> float:
    """Precision@top-q: share of the top predicted-P(up) rows that were actually up.

    This is NOT classification accuracy. Tiny holdouts (k=1) used to print 1.0
    and look 'perfect'. Require ACC_TOP_MIN_K rows or return NaN.
    """
    try:
        n = len(y_true)
        if n == 0:
            return float("nan")
        min_k = int(os.getenv("ACC_TOP_MIN_K", "20"))
        k = max(1, int(n * q))
        if k < min_k:
            return float("nan")
        order = np.argsort(-np.asarray(proba, dtype=float), kind="mergesort")[:k]
        y_arr = np.asarray(y_true)
        return float((y_arr[order] == 1).mean())
    except Exception:
        return float("nan")


def _min_head_top20() -> float:
    return float(os.getenv("MIN_HEAD_TOP20", "0.45"))


def _retrain_min_top20() -> float:
    """If any head acc@top20 is below this after training, run one automatic retry."""
    return float(os.getenv("RETRAIN_MIN_TOP20", "0.6"))


def _min_meta_auc() -> float:
    return float(os.getenv("MIN_META_AUC", "0.52"))


def _head_passes_quality(top20: float, acc: float) -> bool:
    min_top = _min_head_top20()
    min_acc = float(os.getenv("MIN_HEAD_ACC", "0.45"))
    try:
        if top20 != top20 or acc != acc:
            return False
    except Exception:
        return False
    return top20 >= min_top and acc >= min_acc


def _stats_need_retrain(stats: dict) -> bool:
    if os.getenv("AUTO_RETRAIN_LOW_TOP20", "true").lower() not in ("1", "true", "yes"):
        return False
    if os.environ.get("_RETRAIN_LOW_TOP20"):
        return False
    thresh = _retrain_min_top20()
    for key in ("short_top20", "long_top20", "daily_top20", "xlong_top20"):
        v = stats.get(key)
        if v is None:
            continue
        try:
            fv = float(v)
            if fv == fv and fv < thresh:
                return True
        except (TypeError, ValueError):
            pass
    return False


def _apply_retrain_tightening() -> None:
    """Stronger regularization for the automatic low-acc@top20 retry pass."""
    for key, default in (
        ("ML_MAX_DEPTH_LONG", "12"),
        ("ML_MAX_DEPTH_SHORT", "10"),
        ("ENSEMBLE_N_TREES_LONG", "240"),
        ("ENSEMBLE_N_TREES_SHORT", "220"),
    ):
        cur = int(os.getenv(key, default))
        os.environ[key] = str(max(4 if "DEPTH" in key else 80, cur // 2))


def _eval_holdout(clf, X_te: pd.DataFrame, y_te: pd.Series, top_q: float) -> tuple[float, float]:
    if len(y_te) == 0:
        return float("nan"), float("nan")
    proba = clf.predict_proba(X_te)[:, 1]
    acc = float(((proba > 0.5).astype(int) == y_te.values).mean())
    top = _acc_at_top_q(y_te.to_numpy(), proba, top_q)
    return acc, top


def _fit_long_ensemble_guarded(
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
    ticker: str,
    *,
    user_xgb_spw: bool,
) -> tuple[object, float, float, float]:
    """Fit long ensemble; on severe overfit retry with shallower / fewer trees."""
    from ensemble_model import build_long_ensemble

    top_q = float(os.getenv("ACC_TOP_Q", "0.2"))
    gap_thresh = float(os.getenv("LONG_OVERFIT_TRAIN_TEST_GAP", "0.30"))
    min_top = _min_head_top20()

    def _fit_once() -> tuple[object, float, float, float]:
        _auto_xgb_scale_pos_weight(y_train, user_xgb_spw)
        ml = build_long_ensemble(43)
        ml.fit(X_train, y_train)
        acc_tr = accuracy_score(y_train, ml.predict(X_train))
        acc, top = _eval_holdout(ml, X_test, y_test, top_q)
        return ml, acc_tr, acc, top

    ml, acc_l_tr, acc_l, top_l = _fit_once()
    try:
        from analytics.quant_risk import overfitting_warning

        ow = overfitting_warning(acc_l_tr, acc_l, gap_warn=gap_thresh, label=f"{ticker}/long")
        if ow["warn"]:
            log.warning("[ENSEMBLE] %s", ow["message"])
    except Exception:
        pass
    if top_l < min_top and (acc_l_tr - acc_l) > gap_thresh:
        log.warning(
            "[ENSEMBLE] %s long overfit train=%.4f test=%.4f acc@top20=%.4f — retry tighter",
            ticker,
            acc_l_tr,
            acc_l,
            top_l,
        )
        old_depth = os.environ.get("ML_MAX_DEPTH_LONG")
        old_trees = os.environ.get("ENSEMBLE_N_TREES_LONG")
        try:
            os.environ["ML_MAX_DEPTH_LONG"] = str(max(4, int(os.getenv("ML_MAX_DEPTH_LONG", "12")) // 2))
            os.environ["ENSEMBLE_N_TREES_LONG"] = str(max(80, int(os.getenv("ENSEMBLE_N_TREES_LONG", "240")) // 2))
            ml2, acc2_tr, acc2, top2 = _fit_once()
            if top2 > top_l or (top2 >= min_top and acc2 > acc_l):
                ml, acc_l_tr, acc_l, top_l = ml2, acc2_tr, acc2, top2
                log.info("[ENSEMBLE] %s long retry acc@top20=%.4f test=%.4f", ticker, top_l, acc_l)
        finally:
            if old_depth is None:
                os.environ.pop("ML_MAX_DEPTH_LONG", None)
            else:
                os.environ["ML_MAX_DEPTH_LONG"] = old_depth
            if old_trees is None:
                os.environ.pop("ENSEMBLE_N_TREES_LONG", None)
            else:
                os.environ["ENSEMBLE_N_TREES_LONG"] = old_trees

    if top_l < min_top:
        from model_estimators import make_long_classifier

        log.warning("[ENSEMBLE] %s long still weak acc@top20=%.4f — compact RF fallback", ticker, top_l)
        raw = make_long_classifier(44)
        compact = _maybe_calibrate(raw, X_train, y_train)
        if compact is raw:
            compact.fit(X_train, y_train)
        acc_c, top_c = _eval_holdout(compact, X_test, y_test, top_q)
        acc_c_tr = accuracy_score(y_train, compact.predict(X_train))
        if top_c > top_l or (top_c >= min_top and acc_c > acc_l):
            ml, acc_l_tr, acc_l, top_l = compact, acc_c_tr, acc_c, top_c
            log.info("[ENSEMBLE] %s long compact acc@top20=%.4f test=%.4f", ticker, top_l, acc_l)
    return ml, acc_l_tr, acc_l, top_l


def _fit_horizon_head(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    ticker: str,
    tag: str,
    for_long: bool,
    user_xgb_spw: bool,
) -> tuple[object | None, dict[str, float]]:
    """Train 1d or 60d head; drop from bundle when holdout quality is too weak."""
    min_rows = int(os.getenv("MIN_TRAIN_ROWS", "40"))
    if len(X) < min_rows or y.nunique() < 2:
        return None, {}

    top_q = float(os.getenv("ACC_TOP_Q", "0.2"))
    X_tr, X_te, y_tr, y_te = _chrono_split_xy(X, y, ticker=ticker, tag=tag)
    use_ens = os.getenv("USE_ENSEMBLE", "true").lower() in ("1", "true", "yes") and os.getenv(
        "HORIZON_USE_ENSEMBLE", "true"
    ).lower() in ("1", "true", "yes")

    if use_ens:
        from ensemble_model import build_long_ensemble, build_short_ensemble

        _auto_xgb_scale_pos_weight(y_tr, user_xgb_spw)
        head = build_long_ensemble(46) if for_long else build_short_ensemble(45)
        head.fit(X_tr, y_tr)
    else:
        from model_estimators import make_long_classifier, make_short_classifier

        base = make_long_classifier(46) if for_long else make_short_classifier(45)
        head = _maybe_calibrate(base, X_tr, y_tr)
        if head is base:
            head.fit(X_tr, y_tr)

    acc, top = _eval_holdout(head, X_te, y_te, top_q)
    log.info("[%s] %s acc=%.4f acc@top20=%.4f train=%d test=%d", tag, ticker, acc, top, len(X_tr), len(X_te))

    stat_key = "xlong" if for_long else "daily"
    stats = {f"{stat_key}_acc": acc, f"{stat_key}_top20": top}

    if not _head_passes_quality(top, acc):
        # Null-fill mode: keep best-effort head so multi-TF inference has a calibrated signal
        # instead of permanently falling back. Mark weak so retrain loops can still improve it.
        keep_weak = os.getenv("KEEP_WEAK_HEADS", "false").lower() in ("1", "true", "yes")
        fill_null = os.getenv("FILL_NULL_HEADS", "false").lower() in ("1", "true", "yes")
        multi_tf = os.getenv("MULTI_HORIZON_TRAIN", "true").lower() in ("1", "true", "yes")
        if keep_weak or fill_null or multi_tf:
            stats["weak_head"] = True
            log.warning(
                "[%s] %s weak head KEPT acc@top20=%.4f acc=%.4f (fill/keep/multi-tf)",
                tag,
                ticker,
                top,
                acc,
            )
            return head, stats
        log.warning(
            "[%s] %s head rejected acc@top20=%.4f acc=%.4f (min top20=%.2f) — inference falls back",
            tag,
            ticker,
            top,
            acc,
            _min_head_top20(),
        )
        return None, stats
    return head, stats


def _fit_fast_short_long(X_train, X_test, y_train, y_test, yl_train, yl_test, ticker: str):
    ms_raw = make_fast_classifier(42, for_long=False)
    ms_raw.fit(X_train, y_train)
    ms = _maybe_calibrate(ms_raw, X_train, y_train)
    proba_s = ms.predict_proba(X_test)[:, 1]
    acc_s = accuracy_score(y_test, (proba_s > 0.5).astype(int))
    top_s = _acc_at_top_q(y_test, proba_s, float(os.getenv("ACC_TOP_Q", "0.2")))
    log.info("[FAST] %s short acc=%.4f acc@top20=%.4f", ticker, acc_s, top_s)

    ml_raw = make_fast_classifier(43, for_long=True)
    ml_raw.fit(X_train, yl_train)
    ml = _maybe_calibrate(ml_raw, X_train, yl_train)
    proba_l = ml.predict_proba(X_test)[:, 1]
    acc_l = accuracy_score(yl_test, (proba_l > 0.5).astype(int))
    top_l = _acc_at_top_q(yl_test, proba_l, float(os.getenv("ACC_TOP_Q", "0.2")))
    log.info("[FAST] %s long acc=%.4f acc@top20=%.4f", ticker, acc_l, top_l)
    return ms, ml, (acc_s, top_s, acc_l, top_l)


def _fit_grid_short(X_train, X_test, y_train, y_test, ticker: str):
    param_grid = {
        "n_estimators": [100, 200],
        "max_depth": [5, 10, None],
        "min_samples_split": [2, 5],
        "min_samples_leaf": [1, 2],
    }
    grid = GridSearchCV(
        RandomForestClassifier(random_state=42, n_jobs=-1, class_weight="balanced"),
        param_grid,
        cv=3,
        scoring="accuracy",
        n_jobs=-1,
    )
    grid.fit(X_train, y_train)
    acc = accuracy_score(y_test, grid.best_estimator_.predict(X_test))
    log.info("[TUNE] %s short accuracy: %.4f | %s", ticker, acc, grid.best_params_)
    return grid.best_estimator_


def model_path_for(ticker: str) -> Path:
    return Path(os.getenv("MODEL_DIR", "models")) / f"{ticker.strip().upper()}_model.pkl"


def training_saved_model(ticker: str, *, min_bytes: int = 1000) -> bool:
    p = model_path_for(ticker)
    try:
        return p.is_file() and p.stat().st_size >= int(min_bytes)
    except OSError:
        return False


def build_training_frame_for_lstm(ticker: str) -> tuple[pd.DataFrame, list[str]] | None:
    """Build feature matrix + targets for LSTM head training (no daily model retrain)."""
    start_train = os.getenv("TRAIN_DATA_START", "2023-01-01")
    df = build_features(ticker, start_train, None)
    if df.empty or "returns" not in df.columns:
        return None

    short_h = int(os.getenv("SHORT_TARGET_HORIZON", "5"))
    short_thr = float(os.getenv("SHORT_MOVE_THRESHOLD", "0.0"))
    if short_h <= 1:
        df["target"] = (df["returns"].shift(-1) > short_thr).astype(int)
    else:
        fwd_s = df["Adj Close"].shift(-short_h) / df["Adj Close"].replace(0, np.nan) - 1.0
        df["target"] = np.where(fwd_s.notna(), (fwd_s > short_thr).astype(float), np.nan)
    h = int(os.getenv("LONG_HORIZON_DAYS", "20"))
    thr = float(os.getenv("LONG_MOVE_THRESHOLD", "0.0"))
    fwd = df["Adj Close"].shift(-h) / df["Adj Close"].replace(0, np.nan) - 1.0
    df["target_long"] = np.where(fwd.notna(), (fwd > thr).astype(float), np.nan)

    df = df.dropna(subset=["target", "target_long"]).sort_index()
    missing = [col for col in FEATURES if col not in df.columns]
    for c in missing:
        df[c] = 0.0
    feat_cols = _prune_dead_features(df, list(FEATURES))
    if len(feat_cols) < 6:
        return None
    return df, feat_cols


def _train_single_ticker(ticker: str) -> bool:
    """Train daily bundle for one ticker. Returns True only if a model file was saved."""
    log.info("[TRAIN] Processing %s", ticker)
    _purge_ticker_artifacts(ticker)
    built = build_training_frame_for_lstm(ticker)
    if built is None:
        log.warning("[TRAIN] Skipping %s — no valid features", ticker)
        return False
    df, feat_cols = built
    short_h = int(os.getenv("SHORT_TARGET_HORIZON", "5"))
    h = int(os.getenv("LONG_HORIZON_DAYS", "20"))

    multi_horizon = os.getenv("MULTI_HORIZON_TRAIN", "true").lower() in ("1", "true", "yes")
    if multi_horizon:
        fwd_1 = df["Adj Close"].shift(-1) / df["Adj Close"].replace(0, np.nan) - 1.0
        df["target_1d"] = np.where(fwd_1.notna(), (fwd_1 > 0).astype(float), np.nan)
        xlong_h = int(os.getenv("XLONG_HORIZON_DAYS", "60"))
        fwd_x = df["Adj Close"].shift(-xlong_h) / df["Adj Close"].replace(0, np.nan) - 1.0
        df["target_xlong"] = np.where(fwd_x.notna(), (fwd_x > 0).astype(float), np.nan)
    X = _sanitize(df[feat_cols])
    y = df["target"].astype(int)
    y_long = df["target_long"].astype(int)

    if len(X) < int(os.getenv("MIN_TRAIN_ROWS", "40")):
        log.warning("[TRAIN] Skipping %s — only %s rows", ticker, len(X))
        return False

    y_min, y_classes = _class_health(y)
    yl_min, yl_classes = _class_health(y_long)
    if y_classes < 2 or yl_classes < 2:
        log.warning(
            "[TRAIN] Skipping %s — single-class targets (short=%d cls / long=%d cls). "
            "History is too monotonic to learn from.",
            ticker, y_classes, yl_classes,
        )
        return False
    if min(y_min, yl_min) < int(os.getenv("MIN_CLASS_SAMPLES", "2")):
        log.warning(
            "[TRAIN] Skipping %s — minority class too small (short_min=%d, long_min=%d). "
            "Need at least 2 samples per class for a stable split.",
            ticker, y_min, yl_min,
        )
        return False

    X_train, X_test, y_train, y_test, yl_train, yl_test = _train_val_matrix_split(X, y, y_long, ticker)

    fast = os.getenv("FAST_UNIVERSE_TRAIN", "false").lower() in ("1", "true", "yes")
    if not fast:
        try:
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                warnings.simplefilter("ignore", RuntimeWarning)
                selector = SelectKBest(score_func=f_classif, k="all")
                selector.fit(X_train, y_train)
            scores = dict(zip(X_train.columns, np.nan_to_num(selector.scores_, nan=0.0)))
            log.info("[FE] %s feature scores: %s", ticker, scores)
        except Exception as e:
            log.warning("[FE] selector skipped for %s: %s", ticker, e)

    use_ensemble = os.getenv("USE_ENSEMBLE", "true").lower() in ("1", "true", "yes")

    stats = {"ticker": ticker, "rows": int(len(X)), "train_rows": int(len(X_train)), "test_rows": int(len(X_test))}
    if fast:
        ms, ml, (acc_s, top_s, acc_l, top_l) = _fit_fast_short_long(
            X_train, X_test, y_train, y_test, yl_train, yl_test, ticker
        )
        stats.update({"short_acc": acc_s, "short_top20": top_s, "long_acc": acc_l, "long_top20": top_l})
    elif use_ensemble:
        from ensemble_model import build_short_ensemble, build_long_ensemble

        user_xgb_spw = bool((os.getenv("XGB_SCALE_POS_WEIGHT") or "").strip())
        _auto_xgb_scale_pos_weight(y_train, user_xgb_spw)
        ms = build_short_ensemble(42)
        ms.fit(X_train, y_train)
        acc_s_tr = accuracy_score(y_train, ms.predict(X_train))
        proba_s = ms.predict_proba(X_test)[:, 1]
        acc_s = accuracy_score(y_test, (proba_s > 0.5).astype(int))
        top_s = _acc_at_top_q(y_test, proba_s, float(os.getenv("ACC_TOP_Q", "0.2")))
        log.info(
            "[ENSEMBLE] %s short acc train=%.4f test=%.4f acc@top20=%.4f bases=%d",
            ticker,
            acc_s_tr,
            acc_s,
            top_s,
            _model_base_count(ms),
        )
        stats.update({"short_acc": acc_s, "short_top20": top_s, "short_acc_train": acc_s_tr})

        ml, acc_l_tr, acc_l, top_l = _fit_long_ensemble_guarded(
            X_train, X_test, yl_train, yl_test, ticker, user_xgb_spw=user_xgb_spw
        )
        log.info(
            "[ENSEMBLE] %s long acc train=%.4f test=%.4f acc@top20=%.4f bases=%d",
            ticker,
            acc_l_tr,
            acc_l,
            top_l,
            _model_base_count(ml),
        )
        stats.update({"long_acc": acc_l, "long_top20": top_l, "long_acc_train": acc_l_tr})
    else:
        if os.getenv("ML_BACKEND", "rf").lower() == "rf":
            ms = _fit_grid_short(X_train, X_test, y_train, y_test, ticker)
        else:
            ms = make_short_classifier(42)
            ms.fit(X_train, y_train)
            acc_s = accuracy_score(y_test, ms.predict(X_test))
            log.info("[TUNE] %s short accuracy: %.4f (backend=%s)", ticker, acc_s, os.getenv("ML_BACKEND"))
        ml = make_long_classifier(44)
        ml.fit(X_train, yl_train)
        acc_l = accuracy_score(yl_test, ml.predict(X_test))
        log.info("[TUNE] %s long accuracy: %.4f", ticker, acc_l)

    meta_model = None
    meta_path = None
    if os.getenv("USE_META_STACK", "true").lower() in ("1", "true", "yes"):
        try:
            from analytics.meta_stack import train_meta_stack_train_test, save_meta_stack

            # Meta fit on train split (~80% of bars); AUC on test split (no leakage).
            stack_train = df.loc[X_train.index].copy()
            stack_train["p_short"] = ms.predict_proba(X_train)[:, 1]
            stack_train["p_long"] = ml.predict_proba(X_train)[:, 1]
            stack_train["target"] = y_train.values
            stack_test = df.loc[X_test.index].copy()
            stack_test["p_short"] = ms.predict_proba(X_test)[:, 1]
            stack_test["p_long"] = ml.predict_proba(X_test)[:, 1]
            stack_test["target"] = y_test.values
            meta_model, meta_res = train_meta_stack_train_test(
                stack_train,
                stack_test,
                target_col="target",
                bars_total=len(df),
            )
            stats["meta_auc"] = float(meta_res.auc)
            if meta_res.auc < _min_meta_auc():
                log.warning(
                    "[META] %s discarded auc=%.4f < %.2f (would hurt ranking)",
                    ticker,
                    meta_res.auc,
                    _min_meta_auc(),
                )
                meta_model = None
                meta_path = None
            else:
                meta_path = save_meta_stack(ticker, meta_model, meta_res)
                log.info(
                    "[META] %s auc=%.4f meta_fit_rows=%d bars_total=%d meta_eval_rows=%d",
                    ticker,
                    meta_res.auc,
                    meta_res.rows,
                    meta_res.bars_total,
                    meta_res.meta_eval_rows,
                )
        except Exception as e:
            log.warning("[META] %s skipped: %s", ticker, e)

    svm_rbf = None
    rf_aux = None
    if os.getenv("USE_AUX_MODELS", "true").lower() in ("1", "true", "yes"):
        try:
            svm_rbf = SVC(
                kernel="rbf",
                C=float(os.getenv("SVM_RBF_C", "2.0")),
                gamma=os.getenv("SVM_RBF_GAMMA", "scale"),
                probability=True,
                class_weight="balanced",
                random_state=42,
            )
            svm_rbf.fit(X_train, y_train)
        except Exception as e:
            log.warning("[AUX] %s svm_rbf skipped: %s", ticker, e)
        try:
            rf_aux = RandomForestClassifier(
                n_estimators=int(os.getenv("RF_AUX_TREES", "180")),
                max_depth=int(os.getenv("RF_AUX_MAX_DEPTH", "10")),
                min_samples_leaf=2,
                class_weight="balanced",
                random_state=44,
                n_jobs=-1,
            )
            rf_aux.fit(X_train, y_train)
        except Exception as e:
            log.warning("[AUX] %s rf_aux skipped: %s", ticker, e)

    os.makedirs("models", exist_ok=True)
    out_path = os.path.join("models", f"{ticker}_model.pkl")

    # --- Multi-horizon heads (daily 1d, extra-long 60d) ---
    # `model_short` is already the weekly (5d) head; `model_long` is the 20d head.
    # We additionally fit a 1d head and a 60d head so each holding window has a
    # dedicated classifier. All four are saved in the same bundle and selected
    # at inference time by `predict_row_horizon(..., horizon="daily|weekly|long|xlong")`.
    model_daily = None
    model_xlong = None
    daily_stats: dict[str, float] = {}
    xlong_stats: dict[str, float] = {}
    user_xgb_spw = bool((os.getenv("XGB_SCALE_POS_WEIGHT") or "").strip())
    if os.getenv("MULTI_HORIZON_TRAIN", "true").lower() in ("1", "true", "yes"):
        try:
            if "target_1d" in df.columns:
                y_d = df["target_1d"].astype(float).dropna()
                X_d = X.loc[y_d.index]
                y_d = y_d.loc[X_d.index].astype(int)
                model_daily, daily_stats = _fit_horizon_head(
                    X_d, y_d, ticker=ticker, tag="H1d", for_long=False, user_xgb_spw=user_xgb_spw
                )

            if "target_xlong" in df.columns:
                y_x = df["target_xlong"].astype(float).dropna()
                X_x = X.loc[y_x.index]
                y_x = y_x.loc[X_x.index].astype(int)
                model_xlong, xlong_stats = _fit_horizon_head(
                    X_x, y_x, ticker=ticker, tag="H60d", for_long=True, user_xgb_spw=user_xgb_spw
                )
        except Exception as e:
            log.warning("[H-multi] %s skipped: %s", ticker, e)

    if daily_stats:
        stats.update(daily_stats)
    if xlong_stats:
        stats.update(xlong_stats)

    # Compression: gzip-compressed pickles cut on-disk size 3-5x without
    # affecting quality.  Override via SAVE_COMPRESS=0..9 (0=none).
    _save_compress = int(os.getenv("SAVE_COMPRESS", "3"))
    # Drop the deprecated SVM/RF aux + duplicated "model" key unless the
    # user explicitly opts back in.  Saves ~3-4 MB per ticker (≈40 GB / universe).
    _legacy_heads = os.getenv("SAVE_LEGACY_HEADS", "false").lower() in ("1", "true", "yes")
    head_quality: dict[str, dict[str, float]] = {}
    if not fast and use_ensemble:
        head_quality["model_short"] = {"acc": float(stats.get("short_acc", 0)), "top20": float(stats.get("short_top20", 0))}
        head_quality["model_long"] = {"acc": float(stats.get("long_acc", 0)), "top20": float(stats.get("long_top20", 0))}
    if daily_stats:
        head_quality["model_daily"] = {
            "acc": float(daily_stats.get("daily_acc", 0)),
            "top20": float(daily_stats.get("daily_top20", 0)),
        }
    if xlong_stats:
        head_quality["model_xlong"] = {
            "acc": float(xlong_stats.get("xlong_acc", 0)),
            "top20": float(xlong_stats.get("xlong_top20", 0)),
        }

    _bundle = {
        "model_short": ms,
        "model_long": ml,
        "model_daily": model_daily,
        "model_xlong": model_xlong,
        "model_meta": meta_model,
        "features": list(feat_cols),
        "head_quality": head_quality,
        "horizons": {
            "daily": 1,
            "weekly": short_h,
            "long": h,
            "xlong": int(os.getenv("XLONG_HORIZON_DAYS", "60")),
        },
        "long_horizon_days": h,
        "ml_backend": os.getenv("ML_BACKEND", "rf"),
        "price_source": os.getenv("PRICE_DATA_SOURCE", "yfinance"),
        "meta_model_path": meta_path,
    }
    # Never wipe a live multi-TF head with None (bulk retrain used to re-null filled heads).
    if os.path.isfile(out_path) and os.getenv("COALESCE_EXISTING_HEADS", "true").lower() in (
        "1",
        "true",
        "yes",
    ):
        try:
            prev = joblib.load(out_path)
            if isinstance(prev, dict):
                for k in ("model_short", "model_long", "model_daily", "model_xlong", "model_meta"):
                    if _bundle.get(k) is None and prev.get(k) is not None:
                        _bundle[k] = prev.get(k)
                        log.info("[TRAIN] %s coalesced kept %s from prior bundle", ticker, k)
                if not _bundle.get("meta_model_path") and prev.get("meta_model_path"):
                    _bundle["meta_model_path"] = prev.get("meta_model_path")
                prev_hq = prev.get("head_quality") or {}
                if isinstance(prev_hq, dict):
                    merged_hq = dict(prev_hq)
                    merged_hq.update(head_quality or {})
                    _bundle["head_quality"] = merged_hq
        except Exception as e:
            log.warning("[TRAIN] %s coalesce skipped: %s", ticker, e)
    if _legacy_heads:
        _bundle["model_svm_rbf"] = svm_rbf
        _bundle["model_rf_aux"] = rf_aux
        _bundle["model"] = ms
    joblib.dump(_bundle, out_path, compress=_save_compress)
    log.info("[TRAIN] Saved %s", out_path)

    # --- Optional LSTM meta head (opt-in: USE_LSTM_HEAD=true) ---
    if os.getenv("USE_LSTM_HEAD", "false").lower() in ("1", "true", "yes"):
        try:
            from analytics.lstm_head import train_lstm_head

            lstm_res = train_lstm_head(
                ticker, df, list(feat_cols), target_col="target_long", force=True
            )
            if lstm_res.get("saved"):
                log.info("[LSTM] %s saved %s test_acc=%.4f", ticker, lstm_res["saved"], float(lstm_res.get("test_acc", 0.0)))
                stats["lstm_test_acc"] = float(lstm_res.get("test_acc", 0.0))
            else:
                log.debug("[LSTM] %s skipped: %s", ticker, lstm_res.get("skipped"))
        except Exception as e:
            log.warning("[LSTM] %s failed: %s", ticker, e)

    _append_run_stats(stats)

    if _stats_need_retrain(stats):
        low = [
            f"{k}={float(stats[k]):.3f}"
            for k in ("short_top20", "long_top20", "daily_top20", "xlong_top20")
            if stats.get(k) is not None and float(stats[k]) == float(stats[k]) and float(stats[k]) < _retrain_min_top20()
        ]
        log.warning(
            "[RETRAIN] %s acc@top20 below %.2f (%s) — automatic second pass",
            ticker,
            _retrain_min_top20(),
            ", ".join(low) or "n/a",
        )
        os.environ["_RETRAIN_LOW_TOP20"] = "1"
        try:
            _apply_retrain_tightening()
            return _train_single_ticker(ticker)
        finally:
            os.environ.pop("_RETRAIN_LOW_TOP20", None)

    return training_saved_model(ticker)


def _append_run_stats(stats: dict) -> None:
    """Per-ticker line of accuracy stats — used by `analytics.ai_training_grader` at run end."""
    path = os.getenv("TRAIN_STATS_PATH", "data/train_run_stats.jsonl")
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(stats, default=float) + "\n")
    except Exception as e:
        log.debug("[STATS] append failed: %s", e)


def train_models():
    try:
        from config import TRAIN_TICKERS as tickers
    except Exception:
        tickers = []
    if not tickers:
        log.warning("[TRAIN] No TRAIN_TICKERS in config — set TRAIN_CONFIG_TICKERS_ONLY or pass symbols")
        return

    lim = os.getenv("TRAIN_LIMIT")
    if lim:
        tickers = tickers[: int(lim)]

    extra_path = os.path.join("data", "universe_extra.txt")
    if os.path.isfile(extra_path):
        with open(extra_path, encoding="utf-8") as f:
            extra = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
        tickers = list(dict.fromkeys(list(tickers) + extra))

    for t in tickers:
        try:
            _train_single_ticker(t)
        except Exception:
            log.exception("[TRAIN] Failed for %s", t)


def train_universe_batch(
    max_symbols: int | None = None,
    refresh_universe: bool = False,
    checkpoint_path: str = "data/train_checkpoint.json",
):
    from universe_provider import load_universe_with_cap
    from data_platform.market_prices import configure_process_prices

    configure_process_prices(training=True)

    if os.getenv("TRAIN_FORCE_YAHOO", "false").lower() in ("1", "true", "yes"):
        os.environ["PRICE_DATA_SOURCE"] = "yfinance"
        os.environ["FORCE_YAHOO_PRICES"] = "true"

    if os.getenv("TRAIN_KILL_SWITCH_ALL", "false").lower() in ("1", "true", "yes"):
        os.environ["FRESH_MODEL_REBUILD"] = "true"
        os.environ["RESET_TRAINING"] = "true"
        log.error(
            "[BATCH] TRAIN_KILL_SWITCH_ALL — forcing full universe redo "
            "(checkpoint wipe + per-ticker model purge + chronological split defaults)."
        )

    os.makedirs(os.path.dirname(checkpoint_path) or ".", exist_ok=True)

    if os.getenv("RESET_TRAINING", "false").lower() in ("1", "true", "yes"):
        if os.path.isfile(checkpoint_path):
            os.remove(checkpoint_path)
            log.warning("[BATCH] RESET_TRAINING=true — removed %s", checkpoint_path)
        stats_path = os.getenv("TRAIN_STATS_PATH", "data/train_run_stats.jsonl")
        if os.path.isfile(stats_path):
            os.remove(stats_path)
            log.warning("[BATCH] RESET_TRAINING=true — removed %s", stats_path)

    done: set[str] = set()
    failed: dict[str, str] = {}
    if os.path.isfile(checkpoint_path):
        try:
            with open(checkpoint_path, encoding="utf-8") as f:
                ck = json.load(f)
                done = set(ck.get("done", []))
                failed = dict(ck.get("failed", {}))
        except Exception:
            done = set()
            failed = {}

    if os.getenv("RESET_FAILED", "false").lower() in ("1", "true", "yes"):
        log.warning("[BATCH] RESET_FAILED=true — clearing %d failed entries", len(failed))
        failed = {}

    if os.getenv("TRAIN_CONFIG_TICKERS_ONLY", "false").lower() in ("1", "true", "yes"):
        try:
            from config import TRAIN_TICKERS

            syms = list(dict.fromkeys(TRAIN_TICKERS))
        except Exception:
            syms = []
        if max_symbols is not None:
            syms = syms[: int(max_symbols)]
        log.warning(
            "[BATCH] TRAIN_CONFIG_TICKERS_ONLY=true — training %d symbols from config.TRAIN_TICKERS "
            "(full US universe skipped).",
            len(syms),
        )
    else:
        raw = load_universe_with_cap(max_symbols=None, refresh=refresh_universe)
        from fortress_universe import prioritize_training_universe

        syms = prioritize_training_universe(raw, cap=max_symbols)
    skip = done | set(failed.keys())
    pending = [s for s in syms if s not in skip]
    log.info(
        "[BATCH] Universe size: %d  cap=%s  done=%d  failed=%d  pending=%d",
        len(syms),
        max_symbols,
        len(done),
        len(failed),
        len(pending),
    )

    if not pending:
        log.warning(
            "[BATCH] Nothing pending. Use RESET_TRAINING=true (purge done) or "
            "RESET_FAILED=true (retry only failed) to rerun. Checkpoint: %s",
            checkpoint_path,
        )
        return

    def _persist():
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump({"done": sorted(done), "failed": failed}, f, indent=0)

    for i, sym in enumerate(pending, 1):
        try:
            log.info("[BATCH] (%d/%d) %s", i, len(pending), sym)
            saved = _train_single_ticker(sym)
            if saved:
                done.add(sym)
                failed.pop(sym, None)
            else:
                done.discard(sym)
                failed[sym] = "skipped_no_model"
            _persist()
        except Exception as e:
            log.exception("[BATCH] %s failed", sym)
            done.discard(sym)
            failed[sym] = type(e).__name__ + ": " + str(e)[:160]
            _persist()

    try:
        from analytics.ai_training_grader import grade_training_run

        grade_training_run()
    except Exception as e:
        log.warning("[AI-GRADER] skipped: %s", e)
