"""Regime-aware meta stack over base probabilities."""

from __future__ import annotations

import os
from dataclasses import dataclass

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

from utils import log


@dataclass
class MetaStackResult:
    auc: float
    rows: int
    features: list[str]
    # rows == meta_fit_rows (training rows for the meta learner)
    bars_total: int = 0
    meta_eval_rows: int = 0


def _meta_feature_columns(*, multi_tf: bool | None = None) -> list[str]:
    cols = [
        "p_short",
        "p_long",
        "p_gap",
        "vol_regime_ratio",
        "sentiment_impulse",
        "regime_transition_flag",
        "alpha_proxy_20",
    ]
    if multi_tf is None:
        multi_tf = os.getenv("USE_MULTI_TF_META", "true").lower() in ("1", "true", "yes")
    if multi_tf:
        cols.extend(["p_daily", "p_xlong", "p_mix", "p_prod"])
    return cols


def _meta_features(df: pd.DataFrame, *, multi_tf: bool | None = None) -> pd.DataFrame:
    cols = _meta_feature_columns(multi_tf=multi_tf)
    out = df.copy()
    if "p_short" not in out.columns:
        out["p_short"] = 0.5
    if "p_long" not in out.columns:
        out["p_long"] = 0.5
    if "p_gap" not in out.columns:
        out["p_gap"] = out["p_short"].astype(float) - out["p_long"].astype(float)
    if "p_daily" not in out.columns:
        out["p_daily"] = out.get("p_short", 0.5)
    if "p_xlong" not in out.columns:
        out["p_xlong"] = out.get("p_long", 0.5)
    if "p_mix" not in out.columns:
        out["p_mix"] = (out["p_short"].astype(float) + out["p_long"].astype(float)) / 2.0
    if "p_prod" not in out.columns:
        out["p_prod"] = out["p_short"].astype(float) * out["p_long"].astype(float)
    for c in cols:
        if c not in out.columns:
            out[c] = 0.5 if c.startswith("p_") else 0.0
    return out[cols].replace([np.inf, -np.inf], 0).fillna(0)


def train_meta_stack_train_test(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    target_col: str = "target",
    bars_total: int = 0,
    random_state: int = 42,
) -> tuple[LogisticRegression, MetaStackResult]:
    """Fit meta on train rows; report AUC on held-out test (no leakage from test into fit)."""
    tr = train_df.dropna(subset=[target_col]).copy()
    te = test_df.dropna(subset=[target_col]).copy()
    Xtr = _meta_features(tr)
    ytr = tr[target_col].astype(int)
    if len(Xtr) < 5 or ytr.nunique() < 2:
        m = LogisticRegression(max_iter=400, random_state=random_state, class_weight="balanced")
        m.fit(Xtr, ytr)
        return m, MetaStackResult(
            auc=0.5,
            rows=len(Xtr),
            features=list(Xtr.columns),
            bars_total=bars_total or (len(tr) + len(te)),
            meta_eval_rows=len(te),
        )

    model = LogisticRegression(max_iter=1200, random_state=random_state, C=0.5, class_weight="balanced")
    model.fit(Xtr, ytr)

    Xte = _meta_features(te)
    yte = te[target_col].astype(int)
    if len(Xte) > 0 and yte.nunique() > 1 and yte.value_counts().min() >= 1:
        prob = model.predict_proba(Xte)[:, 1]
        auc = float(roc_auc_score(yte, prob))
    else:
        auc = 0.5

    return model, MetaStackResult(
        auc=auc,
        rows=len(Xtr),
        features=list(Xtr.columns),
        bars_total=bars_total or (len(tr) + len(te)),
        meta_eval_rows=len(te),
    )


def train_meta_stack(df: pd.DataFrame, target_col: str = "target", random_state: int = 42) -> tuple[LogisticRegression, MetaStackResult]:
    data = df.dropna(subset=[target_col]).copy()
    X = _meta_features(data)
    y = data[target_col].astype(int)
    if len(X) < 80 or y.nunique() < 2 or y.value_counts().min() < 3:
        # fallback tiny model
        m = LogisticRegression(max_iter=300, random_state=random_state, class_weight="balanced")
        m.fit(X, y)
        return m, MetaStackResult(
            auc=0.5, rows=len(X), features=list(X.columns), bars_total=len(X), meta_eval_rows=0
        )

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=random_state, stratify=y
    )
    model = LogisticRegression(max_iter=1200, random_state=random_state, C=0.5, class_weight="balanced")
    model.fit(X_train, y_train)
    prob = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, prob)
    return model, MetaStackResult(
        auc=float(auc),
        rows=len(X_train),
        features=list(X.columns),
        bars_total=len(X),
        meta_eval_rows=len(X_test),
    )


def apply_meta_stack(model: LogisticRegression, row: pd.Series | dict) -> float:
    one = pd.DataFrame([row if isinstance(row, dict) else row.to_dict()])
    # Always build rich multi-TF features, then align to whatever the pickled meta saw.
    rich = _meta_features(one, multi_tf=True)
    names = getattr(model, "feature_names_in_", None)
    if names is not None and len(names):
        for c in names:
            if c not in rich.columns:
                rich[c] = 0.5 if str(c).startswith("p_") else 0.0
        X = rich[[str(c) for c in names]]
    else:
        X = _meta_features(one, multi_tf=False)
    p = model.predict_proba(X)[0, 1]
    return float(p)


def save_meta_stack(ticker: str, model: LogisticRegression, result: MetaStackResult) -> str:
    os.makedirs("models/meta", exist_ok=True)
    path = os.path.join("models", "meta", f"{ticker}_meta.pkl")
    joblib.dump({"model": model, "result": result.__dict__}, path)
    return path


def load_meta_stack(ticker: str):
    path = os.path.join("models", "meta", f"{ticker}_meta.pkl")
    if not os.path.isfile(path):
        return None
    try:
        obj = joblib.load(path)
        return obj.get("model")
    except Exception as e:
        log.warning("[META] failed load for %s: %s", ticker, e)
        return None

