"""Quick benchmark for feature build + model inference latency."""

from __future__ import annotations

import os
import sys
import time
from statistics import mean
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from feature_engineering import build_features
from ml_model import predict_row


def bench_features(symbols: list[str], start: str = "2022-01-01") -> dict:
    lat = []
    for s in symbols:
        t0 = time.perf_counter()
        _ = build_features(s, start, None)
        lat.append((time.perf_counter() - t0) * 1000.0)
    return {"count": len(lat), "avg_ms": mean(lat) if lat else 0.0, "max_ms": max(lat) if lat else 0.0}


def bench_infer(symbols: list[str], start: str = "2022-01-01") -> dict:
    lat = []
    for s in symbols:
        path = os.path.join("models", f"{s}_model.pkl")
        if not os.path.isfile(path):
            continue
        d = build_features(s, start, None)
        if d.empty:
            continue
        row = d.iloc[-1]
        t0 = time.perf_counter()
        _ = predict_row(path, row)
        lat.append((time.perf_counter() - t0) * 1000.0)
    return {"count": len(lat), "avg_ms": mean(lat) if lat else 0.0, "max_ms": max(lat) if lat else 0.0}


def main():
    symbols = [s.strip().upper() for s in os.getenv("BENCH_SYMBOLS", "AAPL,MSFT,SPY,QQQ,NVDA").split(",") if s.strip()]
    rep = {
        "symbols": symbols,
        "feature_build": bench_features(symbols),
        "infer": bench_infer(symbols),
    }
    print(rep)


if __name__ == "__main__":
    main()

