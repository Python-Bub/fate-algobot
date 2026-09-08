import joblib
import numpy as np

def adjust_thresholds(perf_history, base_thresh=0.005):
    """
    Given a rolling history of daily returns, nudge your spike threshold.
    perf_history: list of past N daily returns
    """
    avg = np.mean(perf_history[-10:])
    # if we’re crushing daily >target, widen threshold; else tighten
    adj = base_thresh * (1 + (avg - 0.2))
    return max(0.001, min(0.02, adj))

def meta_signal(df):
    """
    Use the trained meta‐model to override base signals.
    """
    scaler = joblib.load("models/meta_scaler.pkl")
    meta_m = joblib.load("models/meta_model.pkl")
    # assume df has base model preds as columns: ["rf","xgb","lgb"]
    Xm = scaler.transform(df[["rf","xgb","lgb"]])
    meta_pred = meta_m.predict(Xm)
    return meta_pred  # 1=buy signal, 0/–1=ignore or sell
