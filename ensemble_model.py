"""
Calibrated ensemble: RandomForest + XGBoost + LightGBM stacked via probability
averaging with isotonic CalibratedClassifierCV when enough data exists.

Why a "bigger" model: averaging three diverse, well-tuned learners with calibrated
probabilities gives sharper *and* better-ranked p_up — what we need for TOP-K stock
selection (a strong absolute confidence is not as useful as a reliable ranking).

Used as a drop-in for short/long classifiers (predict_proba interface).
"""

from __future__ import annotations

import os
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier

from utils import log


def _has(pkg: str) -> bool:
    try:
        __import__(pkg)
        return True
    except ImportError:
        return False


class CalibratedAverageEnsemble:
    """Average calibrated probabilities of multiple base learners.

    classes_  : np.ndarray([0, 1])
    predict_proba(X) -> shape (n, 2) with column index 1 == P(class=1)
    """

    def __init__(self, base_models: list, calibrate: bool = True, cv: int = 3):
        self.base_models = base_models
        self.calibrate = calibrate
        self.cv = cv
        self.fitted_: list = []
        self.classes_ = np.array([0, 1])

    def _wrap(self, m, X, y):
        if not self.calibrate:
            m.fit(X, y)
            return m
        vc = pd.Series(y).value_counts() if len(y) else pd.Series(dtype=int)
        n_per_class = int(vc.min()) if len(vc) else 0
        n_classes = int(len(vc))

        # Need >=2 classes and >=2 of each just to do an isotonic/sigmoid calibration.
        if n_classes < 2 or n_per_class < 2:
            m.fit(X, y)
            return m

        # Adaptive CV: never demand more folds than the minority class can provide.
        # CalibratedClassifierCV fits a base estimator on each fold AND a calibrator,
        # so each fold needs at least 1 sample of each class — meaning cv <= min count.
        cv = max(2, min(self.cv, n_per_class))
        method = "isotonic" if n_per_class >= 5 else "sigmoid"
        try:
            cal = CalibratedClassifierCV(m, method=method, cv=cv)
            cal.fit(X, y)
            return cal
        except Exception as e:
            log.warning(
                "[ENSEMBLE] Calibration failed (%s, cv=%d, method=%s); using raw base",
                e, cv, method,
            )
            try:
                m.fit(X, y)
                return m
            except Exception as e2:
                log.warning("[ENSEMBLE] Raw fit also failed: %s", e2)
                return None

    def fit(self, X, y):
        y_arr = np.asarray(y).astype(int)
        self.fitted_ = []
        for m in self.base_models:
            try:
                fitted = self._wrap(m, X, y_arr)
                if fitted is not None:
                    self.fitted_.append(fitted)
            except Exception as e:
                log.warning("[ENSEMBLE] Base learner skipped: %s", e)
        if not self.fitted_:
            raise RuntimeError("No base learner fit succeeded")
        self.classes_ = np.array([0, 1])
        return self

    def predict_proba(self, X) -> np.ndarray:
        if isinstance(X, pd.DataFrame):
            X_in = X
        else:
            X_in = np.asarray(X)
        probas: list[np.ndarray] = []
        for m in self.fitted_:
            Xi = X_in
            names = getattr(m, "feature_names_in_", None)
            if names is None and hasattr(m, "estimator"):
                names = getattr(m.estimator, "feature_names_in_", None)
            if isinstance(X_in, pd.DataFrame) and names is not None:
                cols = list(names)
                Xi = X_in.reindex(columns=cols, fill_value=0.0)
            p = m.predict_proba(Xi)
            classes = list(getattr(m, "classes_", [0, 1]))
            idx_pos = classes.index(1) if 1 in classes else (1 if p.shape[1] > 1 else 0)
            idx_neg = classes.index(0) if 0 in classes else (1 - idx_pos)
            up = p[:, idx_pos]
            dn = p[:, idx_neg] if p.shape[1] > 1 else 1.0 - up
            probas.append(np.column_stack([dn, up]))
        avg = np.mean(np.stack(probas, axis=0), axis=0)
        avg = avg / avg.sum(axis=1, keepdims=True)
        return avg

    def predict(self, X) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


def _rf(seed: int, depth: int, n: int):
    cw = os.getenv("RF_CLASS_WEIGHT", "balanced").strip().lower()
    if cw not in ("balanced", "balanced_subsample"):
        cw = "balanced"
    return RandomForestClassifier(
        n_estimators=n,
        max_depth=depth,
        min_samples_leaf=2,
        class_weight=cw,
        random_state=seed,
        n_jobs=-1,
    )


def _xgb(seed: int, depth: int, n: int):
    if not _has("xgboost"):
        return None
    from xgboost import XGBClassifier

    return XGBClassifier(
        n_estimators=n,
        max_depth=min(depth, 10),
        learning_rate=float(os.getenv("XGB_LEARNING_RATE", "0.05")),
        subsample=0.85,
        colsample_bytree=0.85,
        scale_pos_weight=float(os.getenv("XGB_SCALE_POS_WEIGHT", "1.0")),
        random_state=seed,
        n_jobs=-1,
        eval_metric="logloss",
        tree_method="hist",
    )


def _lgb(seed: int, depth: int, n: int):
    if not _has("lightgbm"):
        return None
    from lightgbm import LGBMClassifier

    return LGBMClassifier(
        n_estimators=n,
        max_depth=min(depth, 12),
        learning_rate=float(os.getenv("LGB_LEARNING_RATE", "0.05")),
        subsample=0.85,
        colsample_bytree=0.85,
        class_weight="balanced",
        random_state=seed,
        n_jobs=-1,
        verbose=-1,
    )


def build_short_ensemble(random_state: int = 42) -> CalibratedAverageEnsemble:
    n = int(os.getenv("ENSEMBLE_N_TREES_SHORT", "220"))
    depth = int(os.getenv("ML_MAX_DEPTH_SHORT", "10"))
    bases = [b for b in (_rf(random_state, depth, n), _xgb(random_state + 1, depth, n), _lgb(random_state + 2, depth, n)) if b is not None]
    return CalibratedAverageEnsemble(bases, calibrate=os.getenv("ENSEMBLE_CALIBRATE", "true").lower() in ("1", "true", "yes"))


def build_long_ensemble(random_state: int = 43) -> CalibratedAverageEnsemble:
    n = int(os.getenv("ENSEMBLE_N_TREES_LONG", "240"))
    depth = int(os.getenv("ML_MAX_DEPTH_LONG", "12"))
    bases = [b for b in (_rf(random_state, depth, n), _xgb(random_state + 1, depth, n), _lgb(random_state + 2, depth, n)) if b is not None]
    return CalibratedAverageEnsemble(bases, calibrate=os.getenv("ENSEMBLE_CALIBRATE", "true").lower() in ("1", "true", "yes"))
