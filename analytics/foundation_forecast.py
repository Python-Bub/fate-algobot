"""Online foundation forecasts (Chronos / stats) → conservative p_up for blending.

Install optional deps for best quality:
  pip install chronos-forecasting torch

Without Chronos, uses a lightweight momentum+EMA statistical head (always local).
"""
from __future__ import annotations

import os
import time
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

from utils import log

_CHRONOS_PIPELINES: dict[str, Any] = {}
_CHRONOS_TRIED: set[str] = set()


def use_foundation_forecast() -> bool:
    return os.getenv("USE_FOUNDATION_FORECAST", "true").lower() in ("1", "true", "yes")


def _context_len() -> int:
    return int(os.getenv("FOUNDATION_CONTEXT_LEN", "160"))


def _horizon() -> int:
    return int(os.getenv("FOUNDATION_HORIZON", "5"))


@lru_cache(maxsize=1)
def _chronos_model_id() -> str:
    return os.getenv("FOUNDATION_CHRONOS_MODEL", "amazon/chronos-bolt-mini")


def _chronos_infer_ids() -> list[str]:
    primary = _chronos_model_id().strip()
    extra = os.getenv("FOUNDATION_CHRONOS_INFER_EXTRA", "amazon/chronos-bolt-small").strip()
    out: list[str] = []
    seen: set[str] = set()
    for mid in [primary, *[p.strip() for p in extra.replace(";", ",").split(",")]]:
        if not mid or mid in seen:
            continue
        seen.add(mid)
        out.append(mid)
    return out


def _load_chronos_id(model_id: str):
    if model_id in _CHRONOS_PIPELINES:
        return _CHRONOS_PIPELINES[model_id]
    if model_id in _CHRONOS_TRIED:
        return None
    _CHRONOS_TRIED.add(model_id)
    if os.getenv("FOUNDATION_DISABLE_CHRONOS", "false").lower() in ("1", "true", "yes"):
        return None
    try:
        import torch

        pipe = None
        for importer in (
            lambda: __import__("chronos", fromlist=["ChronosBoltPipeline"]).ChronosBoltPipeline,
            lambda: __import__("chronos", fromlist=["BaseChronosPipeline"]).BaseChronosPipeline,
            lambda: __import__("chronos", fromlist=["ChronosPipeline"]).ChronosPipeline,
        ):
            try:
                cls = importer()
                pipe = cls.from_pretrained(model_id, device_map="cpu", torch_dtype=torch.float32)
                break
            except (ImportError, AttributeError, Exception):
                continue
        if pipe is None:
            raise RuntimeError("no Chronos pipeline class")
        _CHRONOS_PIPELINES[model_id] = pipe
        log.info("[FOUNDATION] loaded %s", model_id)
        return pipe
    except Exception as e:
        log.warning("[FOUNDATION] Chronos %s unavailable (%s)", model_id, e)
        return None


def _load_chronos():
    return _load_chronos_id(_chronos_model_id())


def _closes_from_df(df: pd.DataFrame) -> np.ndarray:
    if df is None or df.empty:
        return np.asarray([], dtype=np.float64)
    col = "Close" if "Close" in df.columns else df.columns[0]
    s = df[col].astype(float).replace([np.inf, -np.inf], np.nan).dropna()
    return s.to_numpy(dtype=np.float64)


def _statistical_p_up(closes: np.ndarray, horizon: int) -> tuple[float, dict[str, Any]]:
    """Local baseline: EMA trend + momentum → p_up in [0.35, 0.65] (conservative)."""
    if len(closes) < 30:
        return 0.5, {"source": "stat", "reason": "short_history"}
    c = closes[-_context_len() :]
    ret_h = float(c[-1] / c[-1 - min(horizon, len(c) - 1)] - 1.0)
    ema12 = pd.Series(c).ewm(span=12, adjust=False).mean().iloc[-1]
    ema26 = pd.Series(c).ewm(span=26, adjust=False).mean().iloc[-1]
    trend = float(ema12 / ema26 - 1.0) if ema26 > 0 else 0.0
    mom5 = float(c[-1] / c[-6] - 1.0) if len(c) > 6 else 0.0
    raw = 0.5 + 2.2 * ret_h + 1.8 * trend + 0.9 * mom5
    p = float(np.clip(raw, 0.35, 0.65))
    return p, {
        "source": "stat",
        "ret_h": ret_h,
        "trend": trend,
        "mom5": mom5,
    }


def _chronos_p_up_one(model_id: str, closes: np.ndarray, horizon: int) -> tuple[float | None, dict[str, Any]]:
    pipe = _load_chronos_id(model_id)
    if pipe is None or len(closes) < 32:
        return None, {"source": model_id, "reason": "unavailable"}
    try:
        import torch

        ctx = closes[-_context_len() :].astype(np.float32)
        if np.any(ctx <= 0):
            return None, {"source": model_id, "reason": "bad_prices"}
        t = torch.tensor(ctx, dtype=torch.float32).unsqueeze(0)
        t0 = time.perf_counter()
        out = pipe.predict(t, prediction_length=horizon)
        if hasattr(out, "detach"):
            fc = out.detach().cpu().numpy()
        else:
            fc = np.asarray(out)
        if fc.ndim >= 2:
            path = fc[0, :, 0] if fc.shape[-1] >= 1 else fc[0]
        else:
            path = fc
        med = float(np.median(path))
        last = float(ctx[-1])
        fwd_ret = (med / last - 1.0) if last > 0 else 0.0
        p = float(np.clip(0.5 + 8.0 * fwd_ret, 0.38, 0.62))
        ms = int((time.perf_counter() - t0) * 1000)
        return p, {"source": model_id, "fwd_ret": fwd_ret, "latency_ms": ms}
    except Exception as e:
        log.debug("[FOUNDATION] %s infer failed: %s", model_id, e)
        return None, {"source": model_id, "reason": str(e)[:120]}


def _chronos_p_up(closes: np.ndarray, horizon: int) -> tuple[float | None, dict[str, Any]]:
    votes: list[float] = []
    diags: list[dict[str, Any]] = []
    for mid in _chronos_infer_ids():
        p, d = _chronos_p_up_one(mid, closes, horizon)
        diags.append(d)
        if p is not None:
            votes.append(p)
    if not votes:
        return None, {"source": "chronos", "reason": "unavailable", "diag": diags}
    p = float(np.clip(float(np.mean(votes)), 0.38, 0.62))
    return p, {"source": "chronos-ensemble" if len(votes) > 1 else "chronos", "n": len(votes), "votes": votes, "diag": diags}


def foundation_forecast_p(
    ticker: str,
    df: pd.DataFrame | None = None,
    closes: np.ndarray | None = None,
) -> dict[str, Any] | None:
    """Return {p_up, source, diag} or None if disabled."""
    if not use_foundation_forecast():
        return None
    arr = closes if closes is not None else _closes_from_df(df if df is not None else pd.DataFrame())
    if len(arr) < 20:
        return None
    h = _horizon()
    p_c, d_c = _chronos_p_up(arr, h)
    p_s, d_s = _statistical_p_up(arr, h)
    if p_c is not None:
        # Ensemble chronos + stat (slight stat anchor — reduces wild Chronos swings)
        w_c = float(os.getenv("FOUNDATION_CHRONOS_WEIGHT", "0.72"))
        p = float(np.clip(w_c * p_c + (1.0 - w_c) * p_s, 0.35, 0.65))
        return {
            "ticker": ticker.upper(),
            "p_up": p,
            "source": "chronos+stat",
            "chronos_p": p_c,
            "stat_p": p_s,
            "diag": {"chronos": d_c, "stat": d_s},
        }
    return {
        "ticker": ticker.upper(),
        "p_up": p_s,
        "source": "stat",
        "diag": d_s,
    }
