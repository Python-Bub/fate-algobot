#!/usr/bin/env python3
"""Walk-forward historical test of the 4-chart HFT stack.

Batteries (no lookahead):
  1. Synthetic — planted marubozu, key reversals, range-break (always on).
  2. Yahoo 1m/7d, 5m/60d, 15m/60d, 60m/2y, 1d/10y on liquid names.

A trade fires only when bar-geometry (candle or HLOC) AND close-path (line or
PnF) agree on the same close — the cross-family filter. Round-trip cost is
subtracted. Volume-z overlay approximates live tape confirmation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.hft_advanced_charts import vote_series  # noqa: E402

OUT_PATH = ROOT / "data" / "intel" / "hft_chart_hist.json"

DEFAULT_TICKERS = (
    "SPY,QQQ,IWM,DIA,NVDA,AMD,TSLA,AAPL,AMZN,META,GOOGL,MSFT,NFLX,JPM,XOM,WMT,"
    "HD,KO,V,MA,COST,CRM,AVGO,ORCL,BA,DIS,NKE,INTC,MU,QCOM,UNH,LLY,CVX,GE,CAT,"
    "GS,BAC,WFC,PFE,MRK,ABBV,PEP,TMO,ACN,ADBE,NOW,UBER,PLTR"
)

YAHOD_BATTERIES = (
    ("yahoo_1m", "1m", "7d"),
    ("yahoo_5m", "5m", "60d"),
    ("yahoo_15m", "15m", "60d"),
    ("yahoo_1h", "60m", "2y"),
    ("yahoo_1d", "1d", "10y"),
)


def _ohlc_from_df(
    df: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray | None] | None:
    if df is None or df.empty:
        return None
    colmap = {str(c).lower(): c for c in df.columns}

    def col(*names: str) -> str | None:
        for n in names:
            if n in df.columns:
                return n
            if n.lower() in colmap:
                return str(colmap[n.lower()])
        return None

    oc, hc, lc, cc = col("Open"), col("High"), col("Low"), col("Close", "Adj Close")
    vc = col("Volume")
    if not all([oc, hc, lc, cc]):
        return None
    o = df[oc].astype(float).to_numpy()
    h = df[hc].astype(float).to_numpy()
    l = df[lc].astype(float).to_numpy()
    c = df[cc].astype(float).to_numpy()
    vol = df[vc].astype(float).to_numpy() if vc else None
    mask = np.isfinite(o) & np.isfinite(h) & np.isfinite(l) & np.isfinite(c) & (c > 0) & (h >= l)
    if int(mask.sum()) < 40:
        return None
    v_out = vol[mask] if vol is not None and len(vol) == len(mask) else None
    return o[mask], h[mask], l[mask], c[mask], v_out


def _vol_z(volume: np.ndarray | None, i: int, look: int = 20) -> float:
    if volume is None or i < look:
        return 0.0
    window = volume[i - look : i]
    if not np.isfinite(window).all():
        return 0.0
    mu = float(np.mean(window))
    sd = float(np.std(window))
    if sd <= 1e-12 or mu <= 0:
        return 0.0
    return float((volume[i] - mu) / sd)


def walk_forward(
    o: np.ndarray,
    h: np.ndarray,
    l: np.ndarray,
    c: np.ndarray,
    *,
    cost_bps: float,
    min_agree: int,
    min_abs: float,
    horizons: tuple[int, ...],
    jp_bias: np.ndarray | None = None,
    volume: np.ndarray | None = None,
    cooldown: int = 3,
    min_vol_z: float = 0.0,
    require_cross: bool = True,
) -> dict:
    votes = vote_series(o, h, l, c, jp_bias=jp_bias)
    n = len(c)
    buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    n_sig = 0
    n_long = 0
    n_short = 0
    n_cross = 0
    last_fire = -10_000
    agree_hist = [0, 0, 0, 0, 0]
    for i, v in enumerate(votes):
        if v.n_agree <= 4:
            agree_hist[v.n_agree] += 1
        if v.cross_family:
            n_cross += 1
        if require_cross and not v.cross_family:
            continue
        if v.n_agree < min_agree or abs(v.score) < min_abs or v.bias == 0:
            continue
        if i - last_fire < cooldown:
            continue
        if min_vol_z > 0 and _vol_z(volume, i) < min_vol_z:
            continue
        n_sig += 1
        last_fire = i
        if v.bias > 0:
            n_long += 1
        else:
            n_short += 1
        side = v.bias
        px0 = float(c[i])
        if px0 <= 0:
            continue
        cost = cost_bps / 10_000.0
        for hz in horizons:
            j = i + hz
            if j >= n:
                continue
            px1 = float(c[j])
            raw = (px1 / px0 - 1.0) * side
            ret = raw - cost
            buckets[f"h{hz}"]["rets"].append(ret)
            buckets[f"h{hz}"]["raw"].append(raw)
            buckets[f"h{hz}"]["hits"].append(1.0 if ret > 0 else 0.0)
            buckets[f"h{hz}"]["hits_raw"].append(1.0 if raw > 0 else 0.0)
            for name, val in (("candle", v.candle), ("line", v.line), ("hloc", v.hloc), ("pnf", v.pnf), ("hidden", v.hidden)):
                if abs(val) < 0.08:
                    continue
                fam_side = 1 if val > 0 else -1
                fam_raw = (px1 / px0 - 1.0) * fam_side
                fam_ret = fam_raw - cost
                buckets[f"fam_{name}_h{hz}"]["rets"].append(fam_ret)
                buckets[f"fam_{name}_h{hz}"]["raw"].append(fam_raw)
                buckets[f"fam_{name}_h{hz}"]["hits"].append(1.0 if fam_ret > 0 else 0.0)

    def _summ(key: str) -> dict:
        rets = buckets[key]["rets"]
        hits = buckets[key]["hits"]
        raws = buckets[key]["raw"]
        hits_raw = buckets[key]["hits_raw"]
        if not rets:
            return {"n": 0, "hit_rate": None, "mean_ret": None, "median_ret": None, "hit_rate_raw": None, "mean_raw": None}
        arr = np.array(rets, dtype=float)
        raw_arr = np.array(raws, dtype=float) if raws else arr
        out = {
            "n": int(len(arr)),
            "hit_rate": round(float(np.mean(hits)), 4),
            "mean_ret": round(float(np.mean(arr)), 6),
            "median_ret": round(float(np.median(arr)), 6),
            "sum_ret": round(float(np.sum(arr)), 6),
        }
        if raws:
            out["hit_rate_raw"] = round(float(np.mean(hits_raw)), 4) if hits_raw else None
            out["mean_raw"] = round(float(np.mean(raw_arr)), 6)
        return out

    horizons_out = {f"h{hz}": _summ(f"h{hz}") for hz in horizons}
    families = {}
    for name in ("candle", "line", "hloc", "pnf", "hidden"):
        families[name] = {f"h{hz}": _summ(f"fam_{name}_h{hz}") for hz in horizons}
    return {
        "bars": n,
        "signals": n_sig,
        "long": n_long,
        "short": n_short,
        "cross_family_bars": n_cross,
        "agree_hist": agree_hist,
        "horizons": horizons_out,
        "families": families,
    }


def planted_synthetic(n: int = 24_000, seed: int = 7) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Random-walk with planted 3-bar soldiers, key reversals, and range breaks."""
    rng = np.random.default_rng(seed)
    close = np.empty(n, dtype=float)
    close[0] = 100.0
    for i in range(1, n):
        close[i] = close[i - 1] * (1.0 + rng.normal(0.00015, 0.0018))
        if close[i] < 20:
            close[i] = 20.0
    # Plant bullish marubozu bursts every 400 bars
    for start in range(80, n - 12, 400):
        for k in range(4):
            close[start + k] = close[start + k - 1] * 1.012
    # Plant dump then key-reversal reclaim
    for start in range(200, n - 12, 550):
        close[start] = close[start - 1] * 0.985
        close[start + 1] = close[start] * 0.988
        close[start + 2] = close[start + 1] * 1.018
    # Plant a quiet range then a close-path breakout
    for start in range(320, n - 30, 700):
        base = close[start - 1]
        for k in range(18):
            close[start + k] = base * (1.0 + 0.0008 * np.sin(k))
        close[start + 18] = base * 1.016
        close[start + 19] = base * 1.022
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    noise = rng.normal(0, 0.0012, n)
    high = np.maximum(open_, close) * (1.0 + np.abs(noise) * 1.4)
    low = np.minimum(open_, close) * (1.0 - np.abs(noise) * 1.4)
    return open_, high, low, close


def _yahoo_frame(tickers: list[str], *, interval: str, period: str) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    out: dict[str, pd.DataFrame] = {}
    chunk = 6
    for i in range(0, len(tickers), chunk):
        group = tickers[i : i + chunk]
        try:
            raw = yf.download(
                group,
                period=period,
                interval=interval,
                auto_adjust=True,
                progress=False,
                group_by="ticker",
                threads=True,
            )
        except Exception:
            time.sleep(0.8)
            continue
        time.sleep(0.25)
        if raw is None or raw.empty:
            continue
        if len(group) == 1:
            out[group[0]] = raw.dropna(how="all")
            continue
        for t in group:
            try:
                if t in raw.columns.get_level_values(0):
                    sl = raw[t].dropna(how="all")
                    if sl is not None and not sl.empty:
                        out[t] = sl
            except Exception:
                continue
    return out


def _merge_stats(parts: list[dict], horizons: tuple[int, ...]) -> dict:
    if not parts:
        return {}
    bars = sum(int(p.get("bars") or 0) for p in parts)
    signals = sum(int(p.get("signals") or 0) for p in parts)
    long_n = sum(int(p.get("long") or 0) for p in parts)
    short_n = sum(int(p.get("short") or 0) for p in parts)
    cross_n = sum(int(p.get("cross_family_bars") or 0) for p in parts)
    agree = [0, 0, 0, 0, 0]
    for p in parts:
        ah = p.get("agree_hist") or []
        for i, v in enumerate(ah[:5]):
            agree[i] += int(v)

    def _wavg(key_path: tuple[str, ...]) -> dict:
        ns: list[int] = []
        hits: list[float] = []
        means: list[float] = []
        hits_raw: list[float] = []
        means_raw: list[float] = []
        for p in parts:
            cur: object = p
            for k in key_path:
                if not isinstance(cur, dict):
                    cur = None
                    break
                cur = cur.get(k)
            if not isinstance(cur, dict) or not cur.get("n"):
                continue
            n = int(cur["n"])
            ns.append(n)
            if cur.get("hit_rate") is not None:
                hits.append(n * float(cur["hit_rate"]))
            if cur.get("mean_ret") is not None:
                means.append(n * float(cur["mean_ret"]))
            if cur.get("hit_rate_raw") is not None:
                hits_raw.append(n * float(cur["hit_rate_raw"]))
            if cur.get("mean_raw") is not None:
                means_raw.append(n * float(cur["mean_raw"]))
        ntot = sum(ns)
        if not ntot:
            return {"n": 0, "hit_rate": None, "mean_ret": None}
        out = {
            "n": ntot,
            "hit_rate": round(sum(hits) / ntot, 4) if hits else None,
            "mean_ret": round(sum(means) / ntot, 6) if means else None,
        }
        if hits_raw:
            out["hit_rate_raw"] = round(sum(hits_raw) / ntot, 4)
        if means_raw:
            out["mean_raw"] = round(sum(means_raw) / ntot, 6)
        return out

    horizons_out = {f"h{hz}": _wavg(("horizons", f"h{hz}")) for hz in horizons}
    families = {}
    for name in ("candle", "line", "hloc", "pnf", "hidden"):
        families[name] = {f"h{hz}": _wavg(("families", name, f"h{hz}")) for hz in horizons}
    return {
        "bars": bars,
        "signals": signals,
        "long": long_n,
        "short": short_n,
        "cross_family_bars": cross_n,
        "agree_hist": agree,
        "horizons": horizons_out,
        "families": families,
        "names": len(parts),
    }


def _edge(block: dict | None) -> dict:
    if not block:
        return {}
    h3 = (block.get("horizons") or {}).get("h3") or {}
    hr = h3.get("hit_rate")
    mean = h3.get("mean_ret")
    ok = bool(hr is not None and mean is not None and hr > 0.52 and mean > 0)
    return {
        "h3_n": h3.get("n"),
        "h3_hit_rate": hr,
        "h3_mean_ret": mean,
        "h3_hit_rate_raw": h3.get("hit_rate_raw"),
        "h3_mean_raw": h3.get("mean_raw"),
        "positive_after_cost": ok,
    }


def run(
    *,
    tickers: list[str],
    cost_bps: float,
    min_agree: int,
    min_abs: float,
    horizons: tuple[int, ...],
    yahoo: bool,
    synthetic_bars: int,
    cooldown: int,
    min_vol_z: float,
) -> dict:
    report: dict = {
        "at_utc": datetime.now(timezone.utc).isoformat(),
        "cost_bps": cost_bps,
        "min_agree": min_agree,
        "min_abs": min_abs,
        "cooldown": cooldown,
        "min_vol_z": min_vol_z,
        "horizons": list(horizons),
        "engine": "event_cross_family_v2",
    }
    o, h, l, c = planted_synthetic(synthetic_bars)
    report["synthetic"] = walk_forward(
        o, h, l, c,
        cost_bps=cost_bps,
        min_agree=min_agree,
        min_abs=min_abs,
        horizons=horizons,
        cooldown=cooldown,
    )
    # Volume-less second pass is the synthetic itself.
    if yahoo:
        for key, interval, period in YAHOD_BATTERIES:
            print(f"[hist] {key}  {interval} {period} × {len(tickers)} names ...", flush=True)
            frames = _yahoo_frame(tickers, interval=interval, period=period)
            parts = []
            parts_vol = []
            for t, df in frames.items():
                arr = _ohlc_from_df(df)
                if arr is None:
                    continue
                oo, hh, ll, cc, vol = arr
                st = walk_forward(
                    oo, hh, ll, cc,
                    cost_bps=cost_bps,
                    min_agree=min_agree,
                    min_abs=min_abs,
                    horizons=horizons,
                    volume=vol,
                    cooldown=cooldown,
                    min_vol_z=0.0,
                )
                st["ticker"] = t
                parts.append(st)
                if vol is not None and min_vol_z > 0:
                    stv = walk_forward(
                        oo, hh, ll, cc,
                        cost_bps=cost_bps,
                        min_agree=min_agree,
                        min_abs=min_abs,
                        horizons=horizons,
                        volume=vol,
                        cooldown=cooldown,
                        min_vol_z=min_vol_z,
                    )
                    stv["ticker"] = t
                    parts_vol.append(stv)
                h3 = st["horizons"].get("h3")
                print(f"  {t:6s} bars={st['bars']:6d} sig={st['signals']:4d} h3={h3}", flush=True)
            report[key] = _merge_stats(parts, horizons)
            report[f"{key}_n_names"] = len(parts)
            if parts_vol:
                report[f"{key}_vol"] = _merge_stats(parts_vol, horizons)

    verdict = {
        "synthetic": _edge(report.get("synthetic")),
        "note": (
            "Live HFT still requires OBI/tape. Chart stack is a confirmation overlay. "
            "positive_after_cost means 3-bar forward hit-rate >52% AND mean ret >0 after costs. "
            "hit_rate_raw is directional accuracy before spread/cost."
        ),
    }
    for key, _, _ in YAHOD_BATTERIES:
        verdict[key] = _edge(report.get(key))
        if report.get(f"{key}_vol"):
            verdict[f"{key}_vol"] = _edge(report.get(f"{key}_vol"))
    report["verdict"] = verdict
    return report


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tickers", default=os.getenv("HFT_CHART_HIST_TICKERS", DEFAULT_TICKERS))
    p.add_argument("--cost-bps", type=float, default=float(os.getenv("HFT_CHART_COST_BPS", "6")))
    p.add_argument("--min-agree", type=int, default=int(os.getenv("HFT_CHART_MIN_AGREE", "2")))
    p.add_argument("--min-abs", type=float, default=float(os.getenv("HFT_CHART_MIN_ABS", "0.18")))
    p.add_argument("--cooldown", type=int, default=int(os.getenv("HFT_CHART_COOLDOWN_BARS", "3")))
    p.add_argument("--min-vol-z", type=float, default=float(os.getenv("HFT_CHART_MIN_VOL_Z", "0.8")))
    p.add_argument("--synthetic-bars", type=int, default=24_000)
    p.add_argument("--no-yahoo", action="store_true")
    args = p.parse_args()
    tickers = [t.strip().upper() for t in str(args.tickers).split(",") if t.strip()]
    horizons = (1, 3, 5, 10)
    report = run(
        tickers=tickers,
        cost_bps=args.cost_bps,
        min_agree=args.min_agree,
        min_abs=args.min_abs,
        horizons=horizons,
        yahoo=not args.no_yahoo,
        synthetic_bars=args.synthetic_bars,
        cooldown=args.cooldown,
        min_vol_z=args.min_vol_z,
    )
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    slim = {
        "wrote": str(OUT_PATH),
        "verdict": report.get("verdict"),
        "synthetic": report.get("synthetic", {}).get("horizons"),
        "bars": {k: (report.get(k) or {}).get("bars") for k, _, _ in YAHOD_BATTERIES},
        "signals": {k: (report.get(k) or {}).get("signals") for k, _, _ in YAHOD_BATTERIES},
    }
    print(json.dumps(slim, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
