import numpy as np


def _ret(df):
    col = "returns" if "returns" in df.columns else "ret"
    return df[col]


def detect_spike(df, thresh=0.005):
    return _ret(df) > thresh


def detect_top(df, window=5):
    return (df["rsi"] > 70) & (_ret(df).rolling(window).sum() < 0)


def detect_bottom(df, window=5):
    return (df["rsi"] < 30) & (_ret(df).rolling(window).sum() > 0)


def generate_signals(df):
    sig = np.zeros(len(df), dtype=int)
    sig[detect_spike(df)] = 1
    sig[detect_top(df)] = -1
    sig[detect_bottom(df)] = 1
    return sig
