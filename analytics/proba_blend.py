"""Simple probability blender for multi-backend strong retrains."""
from __future__ import annotations

import numpy as np


class ProbaBlend:
    """Average predict_proba across fitted classifiers (xgb + lgb, etc.)."""

    classes_ = np.array([0, 1])

    def __init__(self, clfs: list):
        self.clfs = clfs

    def predict_proba(self, X):
        ps = np.column_stack([_align_clf_proba(c, X) for c in self.clfs])
        mean_p = ps.mean(axis=1)
        return np.column_stack([1.0 - mean_p, mean_p])

    def fit(self, X, y):
        return self


def _align_clf_proba(clf, X):
    names = getattr(clf, "feature_names_in_", None)
    if names is not None and len(names):
        X = X.reindex(columns=list(names), fill_value=0.0)
    else:
        fn = getattr(clf, "feature_name_", None)
        if fn:
            X = X.reindex(columns=list(fn), fill_value=0.0)
    return clf.predict_proba(X)[:, 1]


# Legacy alias for pickles saved as __main__._ProbaBlend from retrain scripts.
_ProbaBlend = ProbaBlend
