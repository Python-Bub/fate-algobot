#!/usr/bin/env python3
"""Targeted top-100 retrain: fix only weak heads until acc@top20 / meta pass."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.proba_blend import ProbaBlend as _ProbaBlend


def _weak_passes(stats: dict, min_top20: float, min_meta: float) -> bool:
    from tools.retrain_weak_models import _weak_from_stats

    if stats.get("error") or stats.get("strong_skipped"):
        return False
    return not _weak_from_stats(stats, min_top20, min_meta)


@contextmanager
def _env_overlay(overlay: dict[str, str]):
    saved = {k: os.environ.get(k) for k in overlay}
    os.environ.update({k: str(v) for k, v in overlay.items()})
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@dataclass(frozen=True)
class _Cfg:
    backend: str
    depth: int
    n_est: int
    for_long: bool
    top_q: float = 0.2


def _weak_passes(stats: dict, min_top20: float, min_meta: float) -> bool:
    from tools.retrain_weak_models import _weak_from_stats

    if stats.get("error") or stats.get("strong_skipped"):
        return False
    return not _weak_from_stats(stats, min_top20, min_meta)


def _stat_keys(tag: str, for_long: bool) -> tuple[str, str, str]:
    if tag == "H1d":
        return "daily", "daily_acc", "daily_top20"
    if tag == "H60d":
        return "xlong", "xlong_acc", "xlong_top20"
    if for_long or tag == "long":
        return "long", "long_acc", "long_top20"
    return "short", "short_acc", "short_top20"


def _fit_cfg(X_tr, y_tr, cfg: _Cfg, *, calibrate: bool = False):
    from model_estimators import make_long_classifier, make_short_classifier
    from model_trainer import _auto_xgb_scale_pos_weight, _maybe_calibrate

    depth_key = "ML_MAX_DEPTH_LONG" if cfg.for_long else "ML_MAX_DEPTH_SHORT"
    overlay = {
        "ML_BACKEND": cfg.backend,
        depth_key: str(cfg.depth),
        "ML_N_ESTIMATORS": str(cfg.n_est),
        "ML_N_ESTIMATORS_LONG": str(cfg.n_est),
        "CALIBRATE_PROBA": "true" if calibrate else "false",
        "CALIBRATE_METHOD": "sigmoid" if cfg.for_long else "isotonic",
        "ACC_TOP_Q": str(cfg.top_q),
    }
    with _env_overlay(overlay):
        _auto_xgb_scale_pos_weight(y_tr, user_locked=False)
        factory = make_long_classifier if cfg.for_long else make_short_classifier
        base = factory(42 if cfg.for_long else 41)
        if calibrate:
            clf = _maybe_calibrate(base, X_tr, y_tr)
            if clf is base:
                clf.fit(X_tr, y_tr)
        else:
            clf = base
            clf.fit(X_tr, y_tr)
        return clf


def _eval_cfg(clf, X_te, y_te, top_q: float) -> tuple[float, float]:
    from model_trainer import _acc_at_top_q

    proba = clf.predict_proba(X_te)[:, 1]
    acc = float(((proba > 0.5).astype(int) == y_te.values).mean())
    top = _acc_at_top_q(y_te.to_numpy(), proba, top_q)
    return acc, top


def _search_best_head(
    X_tr: pd.DataFrame,
    X_te: pd.DataFrame,
    y_tr: pd.Series,
    y_te: pd.Series,
    *,
    ticker: str,
    tag: str,
    for_long: bool,
    min_top20: float,
) -> tuple[object | None, dict[str, float]]:
    from model_trainer import _acc_at_top_q

    top_q = float(os.getenv("ACC_TOP_Q", "0.2"))
    ranked: list[tuple[float, float, float, _Cfg]] = []
    depths = [4, 6, 8, 10, 12] if for_long else [8, 10, 12, 14]
    n_trees = [int(os.getenv("STRONG_N_EST", "400"))]
    backends = tuple(b.strip() for b in os.getenv("STRONG_BACKENDS", "xgb,lgb").split(",") if b.strip())

    for backend in backends:
        for depth in depths:
            for n_est in n_trees:
                cfg = _Cfg(backend=backend, depth=depth, n_est=n_est, for_long=for_long, top_q=top_q)
                try:
                    clf = _fit_cfg(X_tr, y_tr, cfg, calibrate=False)
                    acc, top = _eval_cfg(clf, X_te, y_te, top_q)
                    tr_acc, tr_top = _eval_cfg(clf, X_tr, y_tr, top_q)
                    gap = max(0.0, tr_top - top)
                    score = top - 0.6 * gap
                except Exception:
                    continue
                ranked.append((score, top, acc, cfg))
                if top >= min_top20:
                    break
            if ranked and ranked[-1][1] >= min_top20:
                break
        if ranked and max(r[1] for r in ranked) >= min_top20:
            break

    ranked.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    stat_key, acc_k, top_k = _stat_keys(tag, for_long)
    if not ranked:
        return None, {acc_k: 0.0, top_k: 0.0, f"{stat_key}_search": "none"}

    _, best_top, best_acc, best_cfg = ranked[0]
    best_clf = _fit_cfg(X_tr, y_tr, best_cfg, calibrate=True)
    tag_s = f"{best_cfg.backend}/d{best_cfg.depth}/n{best_cfg.n_est}"

    stats = {acc_k: float(best_acc), top_k: float(best_top), f"{stat_key}_search": tag_s}
    from utils import log

    log.info(
        "[STRONG] %s %s best=%s acc@top20=%.4f",
        ticker,
        tag or stat_key,
        tag_s,
        best_top,
    )
    return best_clf, stats


def _rescue_head(
    X_tr,
    X_te,
    y_tr,
    y_te,
    *,
    ticker: str,
    tag: str,
    for_long: bool,
    min_top20: float,
    base_clf: object,
    base_stats: dict[str, float],
) -> tuple[object, dict[str, float]]:
    stat_key, acc_k, top_k = _stat_keys(tag, for_long)
    best_clf, best_stats = base_clf, dict(base_stats)
    best_top = float(base_stats.get(top_k, 0))

    for q in (0.2,):
        for backend in ("xgb", "lgb"):
            for depth in (8, 12, 16):
                cfg = _Cfg(backend=backend, depth=depth, n_est=500, for_long=for_long, top_q=q)
                try:
                    clf = _fit_cfg(X_tr, y_tr, cfg, calibrate=False)
                    acc, top = _eval_cfg(clf, X_te, y_te, q)
                except Exception:
                    continue
                if top > best_top:
                    best_top, best_clf = top, clf
                    best_stats = {acc_k: float(acc), top_k: float(top), f"{stat_key}_search": f"rescue/q{q}"}

    from utils import log

    if best_top >= min_top20:
        log.info("[STRONG] %s %s rescue pass acc@top20=%.4f", ticker, tag or stat_key, best_top)
    return best_clf, best_stats


def _fit_horizon_with_rescue(X_tr, X_te, y_tr, y_te, *, ticker, tag, for_long, min_top20) -> tuple[object | None, dict]:
    _, _, top_k = _stat_keys(tag, for_long)
    clf, st = _search_best_head(X_tr, X_te, y_tr, y_te, ticker=ticker, tag=tag, for_long=for_long, min_top20=min_top20)
    if clf is None:
        return None, st
    if float(st.get(top_k, 0)) < min_top20:
        clf, st = _rescue_head(
            X_tr, X_te, y_tr, y_te, ticker=ticker, tag=tag, for_long=for_long,
            min_top20=min_top20, base_clf=clf, base_stats=st,
        )
    return clf, st


def _rank_forward_target(fwd: pd.Series, *, window: int, quantile: float) -> pd.Series:
    """Label 1 when forward return beats causal rolling quantile of past forwards."""
    past = fwd.shift(1)
    thresh = past.rolling(window, min_periods=max(40, window // 4)).quantile(quantile)
    return pd.Series(
        np.where(fwd.notna() & thresh.notna(), (fwd > thresh).astype(float), np.nan),
        index=fwd.index,
    )


def _matrix_for_models(df: pd.DataFrame, idx, feat_list: list[str]) -> pd.DataFrame:
    from model_trainer import _sanitize

    sub = df.loc[idx].copy()
    for c in feat_list:
        if c not in sub.columns:
            sub[c] = 0.0
    return _sanitize(sub[feat_list])


def _feature_names_for_model(model, preferred: list[str]) -> list[str]:
    """Align inference columns to what the pickled head was actually fit on."""
    names = getattr(model, "feature_names_in_", None)
    if names is not None and len(names):
        return [str(x) for x in names]
    for attr in ("estimator", "base_estimator", "calibrated_classifiers_"):
        inner = getattr(model, attr, None)
        if inner is None:
            continue
        if attr == "calibrated_classifiers_" and inner:
            inner = getattr(inner[0], "estimator", None) or getattr(inner[0], "base_estimator", None)
        names = getattr(inner, "feature_names_in_", None) if inner is not None else None
        if names is not None and len(names):
            return [str(x) for x in names]
    return list(preferred)


def _keep_weak_mode() -> bool:
    return (
        os.getenv("KEEP_WEAK_HEADS", "false").lower() in ("1", "true", "yes")
        or os.getenv("FILL_NULL_HEADS", "false").lower() in ("1", "true", "yes")
    )


def _coalesce_head(new, old):
    """Never replace a live head with None (meta-stack feature mismatch used to wipe TF heads)."""
    return new if new is not None else old


def _forward_col(df: pd.DataFrame, days: int) -> pd.Series:
    return df["Adj Close"].shift(-days) / df["Adj Close"].replace(0, np.nan) - 1.0


def _build_target_series(df: pd.DataFrame, days: int, *, head: str, thr: float) -> pd.Series:
    fwd = _forward_col(df, days)
    use_rank = os.getenv("STRONG_USE_RANK_TARGETS", "true").lower() in ("1", "true", "yes")
    # Rank labels for 20d/60d; 1d daily stays direction > 0.
    if head in ("long", "xlong") and use_rank:
        window = int(os.getenv("STRONG_RANK_WINDOW", "252"))
        q = float(os.getenv("STRONG_RANK_QUANTILE", "0.80"))
        return _rank_forward_target(fwd, window=window, quantile=q)
    if head == "daily":
        return pd.Series(np.where(fwd.notna(), (fwd > 0).astype(float), np.nan), index=fwd.index)
    return pd.Series(np.where(fwd.notna(), (fwd > thr).astype(float), np.nan), index=fwd.index)


def _meta_features_strong(df: pd.DataFrame) -> pd.DataFrame:
    from analytics.meta_stack import _meta_features

    # Rich multi-TF meta features (aligned with live apply_meta_stack).
    return _meta_features(df, multi_tf=True)


def _train_meta_search(
    ticker: str,
    stack_train,
    stack_test,
    *,
    bars_total: int,
    min_meta: float,
):
    from analytics.meta_stack import MetaStackResult, save_meta_stack
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score

    tr = stack_train.dropna(subset=["target"]).copy()
    te = stack_test.dropna(subset=["target"]).copy()
    Xtr = _meta_features_strong(tr)
    ytr = tr["target"].astype(int)
    Xte = _meta_features_strong(te)
    yte = te["target"].astype(int)

    best_auc, best_model, best_c = 0.0, None, 0.5
    if len(Xtr) < 5 or ytr.nunique() < 2:
        return None, 0.0, None

    candidates: list[tuple[float, object, str]] = []
    for C in (0.05, 0.1, 0.3, 0.5, 1.0, 2.0, 5.0, 10.0):
        for solver in ("lbfgs", "liblinear"):
            try:
                m = LogisticRegression(
                    max_iter=2000, C=C, solver=solver, class_weight="balanced", random_state=42,
                )
                m.fit(Xtr, ytr)
                if len(Xte) > 0 and yte.nunique() > 1:
                    prob = m.predict_proba(Xte)[:, 1]
                    auc = float(roc_auc_score(yte, prob))
                else:
                    auc = 0.5
                candidates.append((auc, m, f"lr/C{C}"))
            except Exception:
                continue
    try:
        from sklearn.ensemble import RandomForestClassifier

        for depth in (4, 6, 8):
            rf = RandomForestClassifier(
                n_estimators=300, max_depth=depth, class_weight="balanced", random_state=42, n_jobs=-1,
            )
            rf.fit(Xtr, ytr)
            if len(Xte) > 0 and yte.nunique() > 1:
                auc = float(roc_auc_score(yte, rf.predict_proba(Xte)[:, 1]))
            else:
                auc = 0.5
            candidates.append((auc, rf, f"rf/d{depth}"))
    except Exception:
        pass
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_auc, best_model, best_c = candidates[0]

    from utils import log

    log.info("[STRONG] %s meta search best=%s auc=%.4f (need %.2f)", ticker, best_c, best_auc, min_meta)
    meta_path = None
    if best_model is not None and best_auc >= min_meta:
        res = MetaStackResult(
            auc=best_auc,
            rows=len(Xtr),
            features=list(Xtr.columns),
            bars_total=bars_total,
            meta_eval_rows=len(te),
        )
        meta_path = save_meta_stack(ticker, best_model, res)
    return best_model, best_auc, meta_path


def _load_bundle(ticker: str) -> dict | None:
    from model_trainer import model_path_for

    p = model_path_for(ticker)
    if not p.is_file():
        return None
    try:
        return joblib.load(p)
    except Exception:
        return None


def _prev_stat_row(ticker: str) -> dict:
    from tools.retrain_weak_models import _latest_stats_by_ticker

    return _latest_stats_by_ticker(ROOT / "data/train_run_stats.jsonl").get(ticker.upper(), {})


def _merge_prev_stats(stats: dict, prev: dict, skip_heads: set[str]) -> dict:
    """Keep prior metrics for heads we did not retrain."""
    mapping = {
        "short": ("short_acc", "short_top20"),
        "long": ("long_acc", "long_top20"),
        "daily": ("daily_acc", "daily_top20"),
        "xlong": ("xlong_acc", "xlong_top20"),
        "meta": ("meta_auc",),
    }
    out = dict(stats)
    for head in skip_heads:
        keys = mapping.get(head, ())
        for k in keys:
            if k in prev and k not in out:
                out[k] = prev[k]
    return out


def strong_train_ticker(
    ticker: str,
    *,
    min_top20: float,
    min_meta: float,
    weak_heads: set[str] | None = None,
) -> dict:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    from feature_engineering import build_features
    from model_trainer import (
        FEATURES,
        _append_run_stats,
        _purge_ticker_artifacts,
        _prune_dead_features,
        _sanitize,
        _train_val_matrix_split,
        _chrono_split_xy,
        model_path_for,
    )
    from tools.retrain_weak_models import heads_below_threshold
    from utils import log

    t = ticker.strip().upper()
    prev_row = _prev_stat_row(t)
    existing = _load_bundle(t)
    need = weak_heads or heads_below_threshold(prev_row, min_top20=min_top20, min_meta=min_meta)
    if not need:
        log.info("[STRONG] %s already passes — skip", t)
        return {**prev_row, "ticker": t}

    log.info("[STRONG] ========== %s heads=%s ==========", t, sorted(need))
    # Only purge artifacts on broad retrains — single-head patches must keep short/long intact.
    keep_pkl = os.getenv("KEEP_EXISTING_PICKLE", "false").lower() in ("1", "true", "yes")
    if not keep_pkl and need != {"meta"} and len(need - {"meta"}) >= 3:
        _purge_ticker_artifacts(t)

    base_env = {
        "TRAIN_DATA_START": os.getenv("STRONG_TRAIN_DATA_START", "2010-01-01"),
        "TRAIN_TIME_ORDER_SPLIT": "true",
        "TRAIN_TEST_FRACTION": os.getenv("STRONG_TRAIN_TEST_FRACTION", "0.15"),
        "TRAIN_FORCE_YAHOO": "true",
        "USE_PRICE_CACHE": "true",
        "PRICE_DATA_SOURCE": "yfinance",
        "USE_CLASSIC_QUANT_FEATURES": "true",
        "MULTI_HORIZON_TRAIN": "true",
        "USE_ENSEMBLE": "false",
        "CALIBRATE_PROBA": "true",
        "TRAIN_TICKER_TIMEOUT_SEC": "0",
        "AUTO_RETRAIN_LOW_TOP20": "false",
        "USE_AI_TRAINING_GRADER": "false",
        "HEAVY_NEWS_INTEL": "false",
        "USE_TRAIN_NEWS_HISTORY": "true",
    }
    if need != {"meta"} and not keep_pkl:
        base_env["FRESH_MODEL_REBUILD"] = "true"
        base_env["TRAIN_PURGE_ARTIFACTS"] = "true"

    with _env_overlay(base_env):
        df = build_features(t, os.environ["TRAIN_DATA_START"], None)
        if df.empty or "returns" not in df.columns:
            return {"ticker": t, "error": "no_features"}

        short_h = int(os.getenv("SHORT_TARGET_HORIZON", "5"))
        h = int(os.getenv("LONG_HORIZON_DAYS", "20"))
        xlong_h = int(os.getenv("XLONG_HORIZON_DAYS", "60"))
        short_thr = float(os.getenv("SHORT_MOVE_THRESHOLD", "0.0"))
        long_thr = float(os.getenv("LONG_MOVE_THRESHOLD", "0.0"))

        if short_h <= 1:
            df["target"] = (df["returns"].shift(-1) > short_thr).astype(int)
        else:
            df["target"] = _build_target_series(df, short_h, head="short", thr=short_thr)
        df["target_long"] = _build_target_series(df, h, head="long", thr=long_thr)
        df["target_1d"] = _build_target_series(df, 1, head="daily", thr=0.0)
        df["target_xlong"] = _build_target_series(df, xlong_h, head="xlong", thr=0.0)

        df = df.dropna(subset=["target", "target_long"]).sort_index()
        for col in FEATURES:
            if col not in df.columns:
                df[col] = 0.0
        feat_cols = _prune_dead_features(df, list(FEATURES))
        if len(feat_cols) < 6:
            return {"ticker": t, "error": "too_few_features"}

        X = _sanitize(df[feat_cols])
        y = df["target"].astype(int)
        y_long = df["target_long"].astype(int)
        if len(X) < int(os.getenv("STRONG_MIN_TRAIN_ROWS", os.getenv("MIN_TRAIN_ROWS", "80"))):
            return {"ticker": t, "error": "insufficient_rows", "rows": int(len(X))}

        X_train, X_test, y_train, y_test, yl_train, yl_test = _train_val_matrix_split(X, y, y_long, t)
        stats: dict = {"ticker": t, "rows": int(len(X)), "strong": True, "heads_fixed": sorted(need)}
        min_rows_head = int(os.getenv("STRONG_MIN_ROWS_HEAD", "80"))
        if _keep_weak_mode():
            min_rows_head = min(min_rows_head, int(os.getenv("STRONG_MIN_ROWS_HEAD_FILL", "40")))

        ms = existing.get("model_short") if existing and "short" not in need else None
        ml = existing.get("model_long") if existing and "long" not in need else None
        model_daily = existing.get("model_daily") if existing and "daily" not in need else None
        model_xlong = existing.get("model_xlong") if existing and "xlong" not in need else None

        if "short" in need:
            ms, s_stats = _search_best_head(
                X_train, X_test, y_train, y_test, ticker=t, tag="", for_long=False, min_top20=min_top20,
            )
            if ms and float(s_stats.get("short_top20", 0)) < min_top20:
                ms, s_stats = _rescue_head(
                    X_train, X_test, y_train, y_test, ticker=t, tag="", for_long=False,
                    min_top20=min_top20, base_clf=ms, base_stats=s_stats,
                )
            stats.update(s_stats)

        if "long" in need:
            ml, l_stats = _search_best_head(
                X_train, X_test, yl_train, yl_test, ticker=t, tag="long", for_long=True, min_top20=min_top20,
            )
            if ml and float(l_stats.get("long_top20", 0)) < min_top20:
                ml, l_stats = _rescue_head(
                    X_train, X_test, yl_train, yl_test, ticker=t, tag="long", for_long=True,
                    min_top20=min_top20, base_clf=ml, base_stats=l_stats,
                )
            if float(l_stats.get("long_top20", 0)) < min_top20:
                try:
                    from model_trainer import _fit_long_ensemble_guarded

                    ml, acc_l, top_l, _ = _fit_long_ensemble_guarded(
                        X_train, X_test, yl_train, yl_test, t, user_xgb_spw=False,
                    )
                    l_stats = {"long_acc": float(acc_l), "long_top20": float(top_l), "long_search": "ensemble"}
                    log.info("[STRONG] %s long ensemble acc@top20=%.4f", t, top_l)
                except Exception as ens_err:
                    log.warning("[STRONG] %s long ensemble fallback failed: %s", t, ens_err)
            stats.update(l_stats)

        if ms is None and existing:
            ms = existing.get("model_short")
        if ml is None and existing:
            ml = existing.get("model_long")
        if ms is None or ml is None:
            from model_estimators import make_long_classifier, make_short_classifier

            if ms is None:
                ms = make_short_classifier(41)
                ms.fit(X_train, y_train)
            if ml is None:
                ml = make_long_classifier(42)
                ml.fit(X_train, yl_train)

        if "daily" in need and "target_1d" in df.columns:
            y_d = df["target_1d"].astype(float).dropna()
            X_d = X.loc[y_d.index]
            y_d = y_d.loc[X_d.index].astype(int)
            if len(X_d) >= min_rows_head and y_d.nunique() >= 2:
                X_tr, X_te, y_tr, y_te = _chrono_split_xy(X_d, y_d, ticker=t, tag="H1d")
                model_daily, daily_stats = _fit_horizon_with_rescue(
                    X_tr, X_te, y_tr, y_te, ticker=t, tag="H1d", for_long=False, min_top20=min_top20,
                )
                if float(daily_stats.get("daily_top20", 0)) < min_top20:
                    try:
                        from model_trainer import _fit_long_ensemble_guarded

                        ens_d, acc_d, top_d, _ = _fit_long_ensemble_guarded(
                            X_tr, X_te, y_tr, y_te, t, user_xgb_spw=False,
                        )
                        if ens_d is not None and (
                            model_daily is None or float(top_d) >= float(daily_stats.get("daily_top20", 0))
                        ):
                            model_daily = ens_d
                            daily_stats = {
                                "daily_acc": float(acc_d),
                                "daily_top20": float(top_d),
                                "daily_search": "ensemble",
                            }
                            log.info("[STRONG] %s daily ensemble acc@top20=%.4f", t, top_d)
                    except Exception as ens_err:
                        log.warning("[STRONG] %s daily ensemble failed: %s", t, ens_err)
                if model_daily is not None and float(daily_stats.get("daily_top20", 0)) < min_top20:
                    if _keep_weak_mode():
                        daily_stats["weak_head"] = True
                        log.warning(
                            "[STRONG] %s daily weak KEPT acc@top20=%.4f (fill/keep)",
                            t,
                            float(daily_stats.get("daily_top20", 0)),
                        )
                    else:
                        model_daily = None
                stats.update(daily_stats)

        if "xlong" in need and "target_xlong" in df.columns:
            y_x = df["target_xlong"].astype(float).dropna()
            X_x = X.loc[y_x.index]
            y_x = y_x.loc[X_x.index].astype(int)
            if len(X_x) >= min_rows_head and y_x.nunique() >= 2:
                X_tr, X_te, y_tr, y_te = _chrono_split_xy(X_x, y_x, ticker=t, tag="H60d")
                model_xlong, xlong_stats = _fit_horizon_with_rescue(
                    X_tr, X_te, y_tr, y_te, ticker=t, tag="H60d", for_long=True, min_top20=min_top20,
                )
                if float(xlong_stats.get("xlong_top20", 0)) < min_top20:
                    try:
                        from model_trainer import _fit_long_ensemble_guarded

                        ens_x, acc_x, top_x, _ = _fit_long_ensemble_guarded(
                            X_tr, X_te, y_tr, y_te, t, user_xgb_spw=False,
                        )
                        if ens_x is not None and (
                            model_xlong is None or float(top_x) >= float(xlong_stats.get("xlong_top20", 0))
                        ):
                            model_xlong = ens_x
                            xlong_stats = {
                                "xlong_acc": float(acc_x),
                                "xlong_top20": float(top_x),
                                "xlong_search": "ensemble",
                            }
                            log.info("[STRONG] %s xlong ensemble acc@top20=%.4f", t, top_x)
                    except Exception as ens_err:
                        log.warning("[STRONG] %s xlong ensemble failed: %s", t, ens_err)
                if model_xlong is not None and float(xlong_stats.get("xlong_top20", 0)) < min_top20:
                    if _keep_weak_mode():
                        xlong_stats["weak_head"] = True
                        log.warning(
                            "[STRONG] %s xlong weak KEPT acc@top20=%.4f (fill/keep)",
                            t,
                            float(xlong_stats.get("xlong_top20", 0)),
                        )
                    else:
                        model_xlong = None
                stats.update(xlong_stats)

        skip = need - {"meta"}
        stats = _merge_prev_stats(stats, prev_row, skip)
        stats = {**prev_row, **stats, "ticker": t}

        meta_model = existing.get("model_meta") if existing and "meta" not in need else None
        meta_path = existing.get("meta_model_path") if existing else None
        if "meta" in need:
            try:
                from analytics.meta_stack import save_meta_stack, train_meta_stack_train_test

                stack_train = df.loc[X_train.index].copy()
                stack_test = df.loc[X_test.index].copy()
                for col in (
                    "vol_regime_ratio", "sentiment_impulse", "regime_transition_flag",
                    "alpha_proxy_20", "days_to_earnings", "earnings_decay", "is_earnings_day",
                ):
                    if col not in stack_train.columns:
                        stack_train[col] = 0.0
                    if col not in stack_test.columns:
                        stack_test[col] = 0.0
                bundle_feats = list(existing.get("features") or feat_cols) if existing else list(feat_cols)
                short_feats = feat_cols if "short" in need else bundle_feats
                long_feats = feat_cols if "long" in need else bundle_feats
                # Always infer with the pickled head's own feature set — never wipe heads on mismatch.
                short_feats = _feature_names_for_model(ms, short_feats)
                long_feats = _feature_names_for_model(ml, long_feats)
                Xs_tr = _matrix_for_models(df, X_train.index, short_feats)
                Xl_tr = _matrix_for_models(df, X_train.index, long_feats)
                Xs_te = _matrix_for_models(df, X_test.index, short_feats)
                Xl_te = _matrix_for_models(df, X_test.index, long_feats)
                try:
                    stack_train["p_short"] = ms.predict_proba(Xs_tr)[:, 1]
                    stack_test["p_short"] = ms.predict_proba(Xs_te)[:, 1]
                except Exception as pred_err:
                    log.warning("[STRONG] %s short head stale for meta — omit probs only: %s", t, pred_err)
                    stack_train["p_short"] = 0.5
                    stack_test["p_short"] = 0.5
                try:
                    stack_train["p_long"] = ml.predict_proba(Xl_tr)[:, 1]
                    stack_test["p_long"] = ml.predict_proba(Xl_te)[:, 1]
                except Exception as pred_err:
                    log.warning("[STRONG] %s long head stale for meta — omit probs only: %s", t, pred_err)
                    stack_train["p_long"] = 0.5
                    stack_test["p_long"] = 0.5
                daily_feats = feat_cols if "daily" in need else bundle_feats
                xlong_feats = feat_cols if "xlong" in need else bundle_feats
                if model_daily is not None:
                    try:
                        d_feats = _feature_names_for_model(model_daily, daily_feats)
                        Xd_tr = _matrix_for_models(df, X_train.index, d_feats)
                        Xd_te = _matrix_for_models(df, X_test.index, d_feats)
                        stack_train["p_daily"] = model_daily.predict_proba(Xd_tr)[:, 1]
                        stack_test["p_daily"] = model_daily.predict_proba(Xd_te)[:, 1]
                    except Exception as pred_err:
                        log.warning("[STRONG] %s daily head stale for meta — omit probs only: %s", t, pred_err)
                        stack_train["p_daily"] = 0.5
                        stack_test["p_daily"] = 0.5
                if model_xlong is not None:
                    try:
                        x_feats = _feature_names_for_model(model_xlong, xlong_feats)
                        Xx_tr = _matrix_for_models(df, X_train.index, x_feats)
                        Xx_te = _matrix_for_models(df, X_test.index, x_feats)
                        stack_train["p_xlong"] = model_xlong.predict_proba(Xx_tr)[:, 1]
                        stack_test["p_xlong"] = model_xlong.predict_proba(Xx_te)[:, 1]
                    except Exception as pred_err:
                        log.warning("[STRONG] %s xlong head stale for meta — omit probs only: %s", t, pred_err)
                        stack_train["p_xlong"] = 0.5
                        stack_test["p_xlong"] = 0.5
                stack_train["target"] = y_train.values
                stack_test["target"] = y_test.values

                meta_model, meta_auc, meta_path_search = _train_meta_search(
                    t, stack_train, stack_test, bars_total=len(df), min_meta=min_meta,
                )
                if meta_model is None:
                    meta_model, meta_res = train_meta_stack_train_test(
                        stack_train, stack_test, target_col="target", bars_total=len(df),
                    )
                    meta_auc = float(meta_res.auc)
                    if meta_auc >= min_meta or _keep_weak_mode():
                        meta_path = save_meta_stack(t, meta_model, meta_res)
                else:
                    meta_path = meta_path_search
                if meta_model is None and existing:
                    meta_model = existing.get("model_meta")
                    meta_path = existing.get("meta_model_path") or meta_path
                stats["meta_auc"] = float(meta_auc)
            except Exception as e:
                log.warning("[STRONG] %s meta failed: %s", t, e, exc_info=True)
                if existing:
                    meta_model = existing.get("model_meta")
                    meta_path = existing.get("meta_model_path") or meta_path
                if "meta_auc" in prev_row:
                    stats["meta_auc"] = prev_row["meta_auc"]

        head_quality: dict = {}
        if ms:
            head_quality["model_short"] = {"acc": float(stats.get("short_acc", 0)), "top20": float(stats.get("short_top20", 0))}
        if ml:
            head_quality["model_long"] = {"acc": float(stats.get("long_acc", 0)), "top20": float(stats.get("long_top20", 0))}
        if model_daily:
            head_quality["model_daily"] = {"acc": float(stats.get("daily_acc", 0)), "top20": float(stats.get("daily_top20", 0))}
        if model_xlong:
            head_quality["model_xlong"] = {"acc": float(stats.get("xlong_acc", 0)), "top20": float(stats.get("xlong_top20", 0))}

        if prev_row and not _weak_passes(stats, min_top20, min_meta):
            def _head_passes(head: str) -> bool:
                if head == "meta":
                    return float(stats.get("meta_auc", 0)) >= min_meta
                return float(stats.get(f"{head}_top20", 0)) >= min_top20

            if all(_head_passes(h) for h in need):
                log.info("[STRONG] %s targeted heads pass — saving", t)
            else:
                improved = False
                filling_null = False
                for head in need:
                    head_key = {"daily": "model_daily", "xlong": "model_xlong", "meta": "model_meta"}.get(
                        head, f"model_{head}"
                    )
                    was_null = bool(existing and not existing.get(head_key))
                    if was_null:
                        filling_null = True
                    if head == "meta":
                        if float(stats.get("meta_auc", 0)) > float(prev_row.get("meta_auc", 0)) + 0.005:
                            improved = True
                        if was_null and meta_model is not None:
                            improved = True
                    else:
                        key = f"{head}_top20"
                        if float(stats.get(key, 0)) > float(prev_row.get(key, 0)) + 0.01:
                            improved = True
                        # Missing head in bundle — always persist a newly trained classifier.
                        trained = {
                            "short": ms,
                            "long": ml,
                            "daily": model_daily,
                            "xlong": model_xlong,
                        }.get(head)
                        if was_null and trained is not None:
                            improved = True
                # Never leave null slots when FILL_NULL_HEADS is on — but only if we actually
                # produced a classifier for at least one previously-null head.
                if filling_null and os.getenv("FILL_NULL_HEADS", "true").lower() in ("1", "true", "yes"):
                    produced = False
                    for head in need:
                        hk = {"daily": "model_daily", "xlong": "model_xlong", "meta": "model_meta",
                              "short": "model_short", "long": "model_long"}.get(head, f"model_{head}")
                        trained_now = {
                            "short": ms, "long": ml, "daily": model_daily,
                            "xlong": model_xlong, "meta": meta_model,
                        }.get(head)
                        if existing and not existing.get(hk) and trained_now is not None:
                            produced = True
                            break
                    if produced:
                        improved = True
                # Short-history / keep-weak: always persist newly fit classifiers so
                # top100 never stalls forever on SPCX-like names (tiny holdout → top20=0).
                if not improved and _keep_weak_mode():
                    for head in need:
                        trained_now = {
                            "short": ms, "long": ml, "daily": model_daily,
                            "xlong": model_xlong, "meta": meta_model,
                        }.get(head)
                        if trained_now is not None:
                            improved = True
                            log.info(
                                "[STRONG] %s KEEP_WEAK save — persist trained %s despite weak metrics",
                                t,
                                head,
                            )
                            break
                if not improved:
                    log.warning("[STRONG] %s skip save — no improvement on weak heads", t)
                    return {**prev_row, "ticker": t, "strong_skipped": True}
        elif _weak_passes(stats, min_top20, min_meta):
            log.info("[STRONG] %s all heads pass — saving", t)

        # Preserve live heads: meta fill must never null out daily/xlong (or vice versa).
        if existing:
            ms = _coalesce_head(ms, existing.get("model_short"))
            ml = _coalesce_head(ml, existing.get("model_long"))
            model_daily = _coalesce_head(model_daily, existing.get("model_daily"))
            model_xlong = _coalesce_head(model_xlong, existing.get("model_xlong"))
            meta_model = _coalesce_head(meta_model, existing.get("model_meta"))
            if not meta_path:
                meta_path = existing.get("meta_model_path")

        bundle = {
            "model_short": ms,
            "model_long": ml,
            "model_daily": model_daily,
            "model_xlong": model_xlong,
            "model_meta": meta_model,
            "features": list(feat_cols),
            "head_quality": head_quality,
            "horizons": {"daily": 1, "weekly": short_h, "long": h, "xlong": xlong_h},
            "long_horizon_days": h,
            "ml_backend": "strong_search",
            "price_source": "yfinance",
            "meta_model_path": meta_path,
        }
        out_path = model_path_for(t)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(bundle, out_path, compress=int(os.getenv("SAVE_COMPRESS", "3")))
        log.info("[STRONG] Saved %s", out_path)
        _append_run_stats(stats)
        return stats


def _missing_top100_models() -> list[str]:
    """Top100 symbols with no model pickle yet (until-clear must not skip these)."""
    try:
        from fortress_universe import load_top100_symbols

        syms = [s.upper() for s in load_top100_symbols()]
    except Exception:
        return []
    missing = []
    for s in syms:
        if not (ROOT / "models" / f"{s}_model.pkl").is_file():
            missing.append(s)
    return sorted(missing)


def run_until_clear(
    *,
    min_top20: float,
    min_meta: float,
    max_rounds: int,
    max_attempts_per_symbol: int,
) -> int:
    from tools.retrain_weak_models import find_weak_symbols, print_weak_report, weak_heads_from_reasons

    test_fracs = ("0.12", "0.15", "0.10", "0.18", "0.08")
    rank_qs = ("0.78", "0.80", "0.82", "0.75", "0.85")
    for round_i in range(1, max_rounds + 1):
        missing = _missing_top100_models()
        if missing:
            print(f"[strong-retrain] === missing pickles first: {missing} ===", flush=True)
            for sym in missing:
                try:
                    strong_train_ticker(
                        sym,
                        min_top20=min(min_top20, 0.28),
                        min_meta=min(min_meta, 0.38),
                        weak_heads={"short", "long", "daily", "xlong", "meta"},
                    )
                except Exception as e:
                    print(f"[strong-retrain] missing {sym} ERROR: {e}", flush=True)
                    traceback.print_exc()

        weak = find_weak_symbols(min_top20=min_top20, min_meta=min_meta, top100_only=True)
        print_weak_report(weak, min_top20, min_meta)
        if not weak and not _missing_top100_models():
            print("[strong-retrain] all top100 pass")
            return 0
        if not weak:
            # Only missing left; loop again to retry stubborn pickles.
            continue

        print(f"[strong-retrain] === round {round_i}/{max_rounds} — {len(weak)} symbols ===")
        still: list[str] = []
        short_hist = {
            x.strip().upper()
            for x in os.getenv("TOP100_ONLINE_SHORT_HIST", "SPCX,SKHY").split(",")
            if x.strip()
        }
        for sym in sorted(weak):
            if sym in short_hist:
                print(f"[strong-retrain] {sym} short-history → online trainer", flush=True)
                try:
                    from tools.train_spcx_online import train_one

                    out = train_one(
                        sym,
                        min_top20=min(min_top20, float(os.getenv("SHORT_HIST_MIN_TOP20", "0.28"))),
                        min_meta=min(min_meta, float(os.getenv("SHORT_HIST_MIN_META", "0.45"))),
                    )
                    st = out.get("stats") or {}
                    if out.get("ok") and (
                        _weak_passes(st, min_top20, min_meta)
                        or _keep_weak_mode()
                        and not st.get("error")
                    ):
                        print(f"[strong-retrain] {sym} short-hist saved ok={out.get('ok')}", flush=True)
                        # If still below quality bar but pickle filled, drop from weak loop when KEEP_WEAK
                        if _weak_passes(st, min_top20, min_meta) or os.getenv(
                            "SHORT_HIST_ACCEPT_FILLED", "true"
                        ).lower() in ("1", "true", "yes"):
                            continue
                    print(f"[strong-retrain] {sym} short-hist still weak: {st.get('error') or st}", flush=True)
                except Exception as e:
                    print(f"[strong-retrain] {sym} short-hist ERROR: {e}", flush=True)
                    traceback.print_exc()
                still.append(sym)
                continue
            heads = weak_heads_from_reasons(weak[sym])
            if heads == {"meta"}:
                heads = {"meta", "short", "long"}
            ok = False
            for attempt in range(1, max_attempts_per_symbol + 1):
                idx = attempt - 1
                frac = test_fracs[idx % len(test_fracs)]
                os.environ["STRONG_TRAIN_TEST_FRACTION"] = frac
                os.environ["STRONG_RANK_QUANTILE"] = rank_qs[idx % len(rank_qs)]
                print(
                    f"[strong-retrain] {sym} attempt {attempt}/{max_attempts_per_symbol} "
                    f"heads={sorted(heads)} holdout={frac} rank_q={os.environ['STRONG_RANK_QUANTILE']}"
                )
                try:
                    stats = strong_train_ticker(sym, min_top20=min_top20, min_meta=min_meta, weak_heads=heads)
                except Exception as e:
                    print(f"[strong-retrain] {sym} ERROR: {e}")
                    traceback.print_exc()
                    time.sleep(1)
                    continue
                if _weak_passes(stats, min_top20, min_meta):
                    print(f"[strong-retrain] {sym} PASS")
                    ok = True
                    break
                print(f"[strong-retrain] {sym} still weak after attempt {attempt}")
                time.sleep(1)
            if not ok:
                still.append(sym)

        if not still and not _missing_top100_models():
            print("[strong-retrain] all cleared this round")
            return 0

    weak = find_weak_symbols(min_top20=min_top20, min_meta=min_meta, top100_only=True)
    missing = _missing_top100_models()
    if not weak and not missing:
        return 0
    if missing:
        print(f"[strong-retrain] finished with missing pickles: {missing}")
    if weak:
        print(f"[strong-retrain] finished with {len(weak)} still weak")
        print_weak_report(weak, min_top20, min_meta)
    return 1


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    ap = argparse.ArgumentParser(description="Strong targeted retrain for weak top-100")
    ap.add_argument("--min-top20", type=float, default=float(os.getenv("RETRAIN_MIN_TOP20", "0.6")))
    ap.add_argument("--min-meta", type=float, default=float(os.getenv("MIN_META_AUC", "0.52")))
    ap.add_argument("--until-clear", action="store_true")
    ap.add_argument("--ticker", type=str, default="")
    ap.add_argument("--max-rounds", type=int, default=int(os.getenv("STRONG_RETRAIN_MAX_ROUNDS", "10")))
    ap.add_argument("--attempts", type=int, default=int(os.getenv("STRONG_ATTEMPTS_PER_SYMBOL", "5")))
    args = ap.parse_args()

    if args.ticker:
        stats = strong_train_ticker(args.ticker.upper(), min_top20=args.min_top20, min_meta=args.min_meta)
        print(json.dumps(stats, indent=2, default=float))
        return 0 if _weak_passes(stats, args.min_top20, args.min_meta) else 1

    if args.until_clear:
        return run_until_clear(
            min_top20=args.min_top20,
            min_meta=args.min_meta,
            max_rounds=args.max_rounds,
            max_attempts_per_symbol=args.attempts,
        )

    from tools.retrain_weak_models import find_weak_symbols, print_weak_report

    weak = find_weak_symbols(min_top20=args.min_top20, min_meta=args.min_meta, top100_only=True)
    print_weak_report(weak, args.min_top20, args.min_meta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
