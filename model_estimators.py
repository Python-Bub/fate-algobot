"""
Classifier factory: RandomForest (default), XGBoost, or LightGBM via env.

ML_BACKEND=rf | xgb | lgb  (default rf)
Install optional: pip install xgboost lightgbm
"""

from __future__ import annotations

import os

from sklearn.ensemble import RandomForestClassifier


def _rf_class_weight() -> str:
    cw = os.getenv("RF_CLASS_WEIGHT", "balanced").strip().lower()
    if cw not in ("balanced", "balanced_subsample"):
        return "balanced"
    return cw


def make_short_classifier(random_state: int = 42):
    backend = os.getenv("ML_BACKEND", "rf").lower()
    n = int(os.getenv("ML_N_ESTIMATORS", "220"))
    depth = int(os.getenv("ML_MAX_DEPTH_SHORT", "12"))

    if backend == "xgb":
        from xgboost import XGBClassifier

        return XGBClassifier(
            n_estimators=n,
            max_depth=depth,
            learning_rate=float(os.getenv("XGB_LEARNING_RATE", "0.06")),
            subsample=0.85,
            colsample_bytree=0.85,
            scale_pos_weight=float(os.getenv("XGB_SCALE_POS_WEIGHT", "1.0")),
            random_state=random_state,
            n_jobs=-1,
            eval_metric="logloss",
        )

    if backend == "lgb":
        from lightgbm import LGBMClassifier

        return LGBMClassifier(
            n_estimators=n,
            max_depth=depth,
            learning_rate=float(os.getenv("LGB_LEARNING_RATE", "0.06")),
            subsample=0.85,
            colsample_bytree=0.85,
            class_weight="balanced",
            random_state=random_state,
            n_jobs=-1,
            verbose=-1,
        )

    return RandomForestClassifier(
        n_estimators=n,
        max_depth=depth,
        min_samples_leaf=2,
        class_weight=_rf_class_weight(),
        random_state=random_state,
        n_jobs=-1,
    )


def make_long_classifier(random_state: int = 43):
    backend = os.getenv("ML_BACKEND", "rf").lower()
    n = int(os.getenv("ML_N_ESTIMATORS_LONG", str(int(os.getenv("ML_N_ESTIMATORS", "240")))))
    depth = int(os.getenv("ML_MAX_DEPTH_LONG", "14"))

    if backend == "xgb":
        from xgboost import XGBClassifier

        return XGBClassifier(
            n_estimators=n,
            max_depth=depth,
            learning_rate=float(os.getenv("XGB_LEARNING_RATE", "0.05")),
            subsample=0.85,
            colsample_bytree=0.85,
            scale_pos_weight=float(os.getenv("XGB_SCALE_POS_WEIGHT", "1.0")),
            random_state=random_state,
            n_jobs=-1,
            eval_metric="logloss",
        )

    if backend == "lgb":
        from lightgbm import LGBMClassifier

        return LGBMClassifier(
            n_estimators=n,
            max_depth=depth,
            learning_rate=float(os.getenv("LGB_LEARNING_RATE", "0.05")),
            subsample=0.85,
            colsample_bytree=0.85,
            class_weight="balanced",
            random_state=random_state,
            n_jobs=-1,
            verbose=-1,
        )

    return RandomForestClassifier(
        n_estimators=n,
        max_depth=depth,
        min_samples_leaf=2,
        class_weight=_rf_class_weight(),
        random_state=random_state,
        n_jobs=-1,
    )


def make_fast_classifier(random_state: int, for_long: bool = False):
    """Used by bulk universe training when FAST_UNIVERSE_TRAIN=true."""
    backend = os.getenv("ML_BACKEND", "rf").lower()
    n = int(os.getenv("FAST_RF_TREES", "160"))
    depth = 14 if for_long else 12

    if backend == "xgb":
        from xgboost import XGBClassifier

        return XGBClassifier(
            n_estimators=n,
            max_depth=min(depth, 10),
            learning_rate=0.08,
            scale_pos_weight=float(os.getenv("XGB_SCALE_POS_WEIGHT", "1.0")),
            random_state=random_state,
            n_jobs=-1,
            eval_metric="logloss",
        )

    if backend == "lgb":
        from lightgbm import LGBMClassifier

        return LGBMClassifier(
            n_estimators=n,
            max_depth=min(depth, 12),
            learning_rate=0.08,
            class_weight="balanced",
            random_state=random_state,
            n_jobs=-1,
            verbose=-1,
        )

    return RandomForestClassifier(
        n_estimators=n,
        max_depth=depth,
        min_samples_leaf=2,
        class_weight=_rf_class_weight(),
        random_state=random_state,
        n_jobs=-1,
    )
