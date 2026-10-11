"""Score the 5-day holdout on prices and models already on disk.

No orders. No live-money path. Yahoo and Finnhub are not called: a missing
cache row is skipped, and earnings dates come from the local earnings file.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["USE_PRICE_CACHE"] = "true"
os.environ["PRICE_CACHE_STALE_OK_DAYS"] = "3650"
os.environ["PRICE_CACHE_MAX_START_GAP_DAYS"] = "20000"
os.environ["USE_HISTORICAL_EVENTS"] = "false"
os.environ["ENABLE_EARNINGS_FEATURES"] = "false"
os.environ["EARNINGS_FINNHUB_PER_SYMBOL"] = "false"
os.environ["NETWORK_FIRST"] = "false"
os.environ["FRED_API_KEY"] = ""
os.environ["SAVE_REPLAY_FEATURES"] = "false"


def _offline_earnings(ticker: str, lookback_quarters: int = 8) -> list:
    from intel.earnings_calendar import _disk_dates

    return list(_disk_dates(str(ticker).strip().upper()) or [])


def _block_network_features() -> None:
    import feature_engineering as fe

    fe.load_earnings_dates = _offline_earnings
    try:
        import signals.fred_macro as fred

        fred.fred_spread_daily_series = lambda start, end: __import__("pandas").Series(dtype=float)
        fred._yf_yield_daily_series = lambda series_id, start, end: __import__("pandas").Series(dtype=float)
    except Exception:
        pass


def eligible_symbols(root: Path = ROOT) -> list[str]:
    """Models with a real bundle and an OHLC parquet of at least 800 bars."""
    import pyarrow.parquet as pq

    out = []
    prices = root / "data" / "cache" / "prices"
    for path in sorted((root / "models").glob("*_model.pkl")):
        if path.stat().st_size < 20_000:
            continue
        sym = path.name[: -len("_model.pkl")]
        px = prices / f"{sym}.parquet"
        if not px.is_file() or px.stat().st_size < 5_000:
            continue
        try:
            pf = pq.ParquetFile(px)
            names = set(pf.schema.names)
            rows = int(pf.metadata.num_rows)
        except Exception:
            continue
        if rows < 800 or "High" not in names or "Volume" not in names:
            continue
        if "Close" not in names and "Adj Close" not in names:
            continue
        out.append(sym)
    return out


def score_symbol(symbol: str, root: str | None = None) -> dict:
    """One name: frozen 5-day head, online timeframes, causal down-day size."""
    _block_network_features()
    base = Path(root) if root else ROOT
    sym = symbol.strip().upper()
    try:
        from analytics.holdout_edge import combiner_probs, daily_accuracy, lever_grid, shot_returns, train_threshold
        from analytics.model_edge import _batch_p_up
        from analytics.timeframe_learner import horizon_votes
        from analytics.trade_kernel import move_sizes
        from feature_engineering import build_features
        from ml_model import load_raw_bundle

        model_path = base / "models" / f"{sym}_model.pkl"
        raw = load_raw_bundle(str(model_path))
        short = raw.get("model_short") or raw.get("model")
        daily = raw.get("model_daily")
        long_m = raw.get("model_long")
        feats = list(raw.get("features") or [])
        if short is None or not feats:
            return {"symbol": sym, "error": "no_short_head"}
        feat = build_features(sym, "2008-01-01", None)
        if feat is None or feat.empty or "Adj Close" not in feat.columns:
            return {"symbol": sym, "error": "no_features"}
        p_short = _batch_p_up(short, feat, feats)
        if not p_short:
            return {"symbol": sym, "error": "no_probs"}
        closes = [float(x) for x in feat["Adj Close"].tolist()]
        if len(closes) != len(p_short):
            return {"symbol": sym, "error": "length_mismatch"}
        p_long = _batch_p_up(long_m, feat, feats) if long_m is not None else None
        p_daily = _batch_p_up(daily, feat, feats) if daily is not None else None
        sizes = [move_sizes(closes, i) for i in range(len(closes))]
        avg_up = [None if s is None else float(s[0]) for s in sizes]
        avg_down = [None if s is None else float(s[1]) for s in sizes]
        votes = horizon_votes(closes)
        p_comb = combiner_probs(closes, p_short, votes, avg_up, avg_down)
        shots = shot_returns(
            closes,
            p_short,
            avg_down=avg_down,
            votes=votes,
            p_long=p_long,
            p_comb=p_comb,
        )
        grid = {k: v for k, v in lever_grid(closes, p_short, votes).items() if v["n"]}
        bar = train_threshold(p_short)
        daily = {"n": 0, "hit": None}
        if p_daily is not None and bar is not None and len(p_daily) == len(closes):
            daily = daily_accuracy(p_daily, closes, bar[0])
        return {
            "symbol": sym,
            "n_rows": len(closes),
            "cut": None if bar is None else bar[0],
            "thr": None if bar is None else bar[1],
            "daily": daily,
            "shots": shots,
            "grid": grid,
        }
    except Exception as exc:
        return {"symbol": sym, "error": f"{type(exc).__name__}: {exc}"}


def _print_table(title: str, summary: dict) -> None:
    print(title)
    for key in ("U", "P62", "A", "B", "C", "D", "E", "L", "F"):
        row = summary.get(key) or {}
        mean = row.get("mean")
        net = row.get("mean_net")
        hit = row.get("hit")
        mean_s = "n/a" if mean is None else f"{mean * 100:.3f}%"
        net_s = "n/a" if net is None else f"{net * 100:.3f}%"
        hit_s = "n/a" if hit is None else f"{hit * 100:.1f}%"
        print(f"  {key:4} n={int(row.get('n') or 0):6} hit={hit_s:7} mean5d={mean_s:10} net={net_s}")


def main() -> None:
    from analytics.holdout_edge import (
        choose_lever,
        clearly_better,
        even_symbols,
        five_day_equivalent,
        pool_buckets,
        pool_summaries,
        split_halves,
        walk_levers,
    )

    names = eligible_symbols()
    sample = even_symbols(names, 48)
    select, confirm = split_halves(sample)
    extra = ["SLYV", "ADEA", "AMRN", "AXG", "APT", "IAUX", "JZ", "ACON", "AVGO", "GEV", "MDLZ", "HUHU"]
    eligible_set = set(names)
    wanted = list(dict.fromkeys(sample + [s for s in extra if s in eligible_set]))
    print(f"eligible={len(names)} sample={len(sample)} select={len(select)} confirm={len(confirm)}", flush=True)

    import multiprocessing as mp

    ctx = mp.get_context("spawn")
    rows = []
    with ctx.Pool(processes=4) as pool:
        for row in pool.imap_unordered(score_symbol, wanted):
            rows.append(row)
            err = row.get("error")
            n_a = len((row.get("shots") or {}).get("A") or [])
            print(f"  {row.get('symbol')} err={err} shotsA={n_a}", flush=True)

    by_sym = {r["symbol"]: r for r in rows}
    select_sum = pool_summaries(rows, select)
    confirm_sum = pool_summaries(rows, confirm)
    sample_sum = pool_summaries(rows, sample)
    base12 = [s for s in extra if s in by_sym and not by_sym[s].get("error")]
    base_sum = pool_summaries(rows, base12)
    lever = choose_lever(select_sum)
    confirmed = bool(lever) and clearly_better(confirm_sum.get(lever) or {}, confirm_sum.get("A") or {})
    select_grid = pool_buckets(rows, select)
    confirm_grid = pool_buckets(rows, confirm)
    walked = walk_levers(select_grid, confirm_grid)

    def _daily(symbols: list[str]) -> dict:
        n = 0
        hit_w = 0.0
        for sym in symbols:
            row = by_sym.get(sym) or {}
            d = row.get("daily") or {}
            if d.get("hit") is None or not d.get("n"):
                continue
            n += int(d["n"])
            hit_w += float(d["hit"]) * int(d["n"])
        return {"n": n, "hit": (hit_w / n) if n else None}

    def _line(label: str, summary: dict, rule: str) -> None:
        mean = summary.get("mean")
        eq = five_day_equivalent(mean, 5 if "_hold" not in rule else int(rule.rsplit("_hold", 1)[1]))
        mean_s = "n/a" if mean is None else f"{mean * 100:.3f}%"
        eq_s = "n/a" if eq is None else f"{eq * 100:.3f}%"
        print(f"  {label:22} n={int(summary.get('n') or 0):6} mean={mean_s:10} per5d={eq_s}")

    print("WALK")
    for step in walked["steps"]:
        cand = step["candidate"]
        print(
            f"  {step['family']:8} candidate={cand} action={step['action']} rule={step['rule']}"
        )
        if cand and cand in select_grid:
            _line("select " + cand, select_grid[cand], cand)
        if cand and cand in confirm_grid:
            _line("confirm " + cand, confirm_grid[cand], cand)
    print("kept", walked["rule"])
    for key in (
        "U",
        "cut70",
        "cut80",
        "cut90",
        "cut95",
        "cut62",
        "cut80_agree1",
        "cut80_agree2",
        "cut80_agree3",
        "cut80_agree4",
        "cut80_h_5",
        "cut80_h_1",
        "cut80_h_20",
        "cut80_h_60",
        "cut80_h_1-5",
        "cut80_h_5-20",
        "cut80_h_1-5-20",
        "cut80_h_20-60",
        "cut80_hold1",
        "cut80_hold5",
        "cut80_hold10",
        "cut80_hold20",
    ):
        print("SELECT", end=" ")
        _line(key, select_grid.get(key) or {}, key)
        print("CONFIRM", end=" ")
        _line(key, confirm_grid.get(key) or {}, key)

    _print_table("SELECT (chooses the lever)", select_sum)
    print("lever", lever)
    _print_table("CONFIRM (untouched)", confirm_sum)
    print("confirmed", confirmed)
    _print_table("SAMPLE", sample_sum)
    _print_table("ORIGINAL_NAMES_STILL_ON_DISK " + ",".join(base12), base_sum)
    print("daily_select", _daily(select))
    print("daily_confirm", _daily(confirm))
    print("daily_sample", _daily(sample))

    out = {
        "eligible": len(names),
        "sample": sample,
        "select": select,
        "confirm": confirm,
        "baseline12_scored": base12,
        "lever": lever,
        "confirmed": confirmed,
        "walk": walked,
        "select_grid": select_grid,
        "confirm_grid": confirm_grid,
        "select_summary": select_sum,
        "confirm_summary": confirm_sum,
        "sample_summary": sample_sum,
        "baseline12_summary": base_sum,
        "daily_select": _daily(select),
        "daily_confirm": _daily(confirm),
        "daily_sample": _daily(sample),
        "symbols": [
            {
                "symbol": r.get("symbol"),
                "error": r.get("error"),
                "n_rows": r.get("n_rows"),
                "thr": r.get("thr"),
                "daily": r.get("daily"),
                "n": {k: len(v) for k, v in (r.get("shots") or {}).items()},
            }
            for r in rows
        ],
    }
    dest = ROOT / "data" / "ops" / "holdout_edge_result.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("wrote", dest)


if __name__ == "__main__":
    main()
