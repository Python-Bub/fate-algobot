"""
Walk-forward: train on rolling past window, validate on next chunk (hidden forward).

Reports test accuracy AND **top-20% confidence** accuracy per split — the metric that
actually maps to trade quality (vs the noisy "every bar" headline). Uses the same
`FEATURES` list and pruning rules as the production trainer so the numbers are
directly comparable.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score

from feature_engineering import build_features
from model_estimators import make_short_classifier
from ml_model import FEATURES

from utils import log


def _acc_at_top_q(y_true: np.ndarray, proba: np.ndarray, q: float = 0.2) -> float:
    n = len(y_true)
    if n == 0:
        return float("nan")
    k = max(1, int(n * q))
    order = np.argsort(-np.asarray(proba))[:k]
    y_arr = np.asarray(y_true)
    return float((y_arr[order] == 1).mean())


def walk_forward_validate(
    ticker: str,
    start: str,
    n_splits: int = 5,
    min_train: int = 200,
) -> list[dict]:
    df = build_features(ticker, start, None)
    df = df.dropna(subset=["target", "target_long"])
    if len(df) < min_train + 50:
        log.warning("[WF] Not enough rows for %s", ticker)
        return []

    use_cols = [c for c in FEATURES if c in df.columns]
    X = df[use_cols].replace([np.inf, -np.inf], 0).fillna(0).astype(np.float64)
    y = df["target"].astype(int)
    idx = np.array_split(np.arange(len(df)), n_splits)
    results = []
    for i in range(1, len(idx)):
        train_ix = np.concatenate(idx[:i])
        test_ix = idx[i]
        if len(train_ix) < min_train or len(test_ix) < 10:
            continue
        mdl = make_short_classifier(42 + i)
        mdl.fit(X.iloc[train_ix], y.iloc[train_ix])
        proba = mdl.predict_proba(X.iloc[test_ix])[:, 1]
        pred = (proba > 0.5).astype(int)
        acc = accuracy_score(y.iloc[test_ix], pred)
        top_q = float(os.getenv("WF_TOP_Q", "0.2"))
        top_acc = _acc_at_top_q(y.iloc[test_ix].to_numpy(), proba, q=top_q)
        results.append(
            {
                "split": i,
                "acc": acc,
                "acc_top20": top_acc,
                "train_n": len(train_ix),
                "test_n": len(test_ix),
            }
        )
        log.info(
            "[WF] %s split %s acc=%.4f acc@top20=%.4f train=%d test=%d",
            ticker, i, acc, top_acc, len(train_ix), len(test_ix),
        )
    if results:
        accs = [r["acc"] for r in results]
        top = [r["acc_top20"] for r in results if not np.isnan(r["acc_top20"])]
        log.warning(
            "[WF] %s summary mean_acc=%.4f mean_top20=%.4f splits=%d",
            ticker,
            float(np.mean(accs)),
            float(np.mean(top)) if top else float("nan"),
            len(results),
        )
    return results


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default=os.getenv("WF_EXAMPLE_TICKER", "SPY"))
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--splits", type=int, default=int(os.getenv("WF_SPLITS", "5")))
    args = ap.parse_args()
    walk_forward_validate(args.ticker, args.start, n_splits=args.splits)
