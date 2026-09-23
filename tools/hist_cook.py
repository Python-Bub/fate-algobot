"""Walk-forward cook of proven/tight picks on historical daily bars.

Does not stop other trainers. Writes:
  data/intel/hist_cook_report.json
  data/intel/proven_online_state.json  (Hedge + Platt after history)

  ./venv/bin/python tools/hist_cook.py --once
  ./run_all.sh hist-cook
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

try:
    from data_platform.runtime_env import load_runtime_env

    # Process pins win, so HIST_COOK_TRAIN_LSTM=false is not rewritten by deploy_scale.env.
    load_runtime_env()
except Exception:
    pass

REPORT_PATH = ROOT / "data" / "intel" / "hist_cook_report.json"

_COOK_UNIVERSE = (
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA", "AVGO", "AMD",
    "JPM", "BAC", "WMT", "COST", "XOM", "CVX", "JNJ", "UNH", "LLY", "ABBV",
    "PFE", "MRNA", "ORCL", "V", "MA", "NFLX", "DIS", "KO", "PEP", "SBUX",
    "MCD", "HD", "TGT", "MU", "INTC", "AMAT", "LRCX", "QCOM", "CRM", "NOW",
    "ADBE", "INTU", "IBM", "CAT", "GE", "BA", "GS", "MS", "BLK",
    "TSM", "ASML", "NVO", "SAP", "TM", "HSBC", "BABA", "SHOP", "PANW",
    "CRWD", "UBER", "PLTR", "ARM", "BKNG", "ISRG", "AXP", "WFC", "C",
    "MRK", "AMGN", "GILD", "TMO", "DHR", "SYK", "LOW", "NKE", "DE",
    "UNP", "HON", "RTX", "LMT", "CVS", "ELV", "PGR", "SPGI",
)


def _cook_symbols(max_n: int) -> list[str]:
    """Mega-caps first, then the rest of the listed universe — never a shrink of the cook set."""
    seen: list[str] = []
    for s in _COOK_UNIVERSE:
        u = str(s).strip().upper()
        if u and u not in seen:
            seen.append(u)
    if len(seen) >= max_n:
        return seen[: max(1, max_n)]
    try:
        from universe_provider import load_universe_symbols

        for s in load_universe_symbols():
            u = str(s).strip().upper()
            if u and u not in seen:
                seen.append(u)
            if len(seen) >= max_n:
                break
    except Exception as e:
        print(f"[HIST_COOK] universe expand skipped: {e}", flush=True)
    return seen[: max(1, max_n)]


def _train_hist_lstm(symbol: str) -> dict:
    if os.getenv("HIST_COOK_TRAIN_LSTM", "true").lower() not in ("1", "true", "yes"):
        return {"skipped": "off"}
    os.environ.setdefault("USE_LSTM_HEAD", "true")
    os.environ.setdefault("TRAIN_DATA_START", "2010-01-01")
    try:
        from analytics.lstm_head import train_lstm_head
        from model_trainer import build_training_frame_for_lstm

        built = build_training_frame_for_lstm(symbol)
        if not built:
            return {"skipped": "no_frame"}
        df, cols = built
        return train_lstm_head(symbol, df, cols, force=True)
    except Exception as e:
        return {"skipped": f"{type(e).__name__}:{e}"[:180]}


def _closes(symbol: str, start: str, end: str) -> pd.DataFrame | None:
    """Fetch daily bars, but don't let one stuck request stall the whole cook."""
    import concurrent.futures

    def _go() -> pd.DataFrame | None:
        try:
            from data_platform.market_prices import fetch_daily

            df = fetch_daily(symbol, start, end)
            if df is not None and not getattr(df, "empty", True):
                return df
        except Exception:
            pass
        try:
            from feature_engineering import load_price_data

            return load_price_data(symbol, start, end)
        except Exception:
            return None

    timeout = float(os.getenv("HIST_COOK_FETCH_TIMEOUT", "40"))
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    fut = pool.submit(_go)
    try:
        return fut.result(timeout=timeout)
    except Exception as e:
        print(f"[HIST_COOK] {symbol} bars timed out ({timeout:.0f}s): {e}", flush=True)
        return None
    finally:
        # Don't wait on a stuck download — the context-manager shutdown would hang the cook.
        pool.shutdown(wait=False, cancel_futures=True)


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1.0 / n, adjust=False).mean()
    down = (-d.clip(upper=0)).ewm(alpha=1.0 / n, adjust=False).mean()
    rs = up / down.replace(0, np.nan)
    return (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)


def _enrich(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "Close" not in out.columns and "Adj Close" in out.columns:
        out["Close"] = out["Adj Close"]
    c = out["Close"].astype(float) if "Close" in out.columns else out.iloc[:, 0].astype(float)
    out["rsi"] = _rsi(c)
    try:
        from analytics.classic_quant_features import enrich_classic_quant_features

        out = enrich_classic_quant_features(out)
    except Exception:
        pass
    return out


def _p_from_mom(mom60: float) -> float:
    z = max(-12.0, min(12.0, 8.0 * float(mom60)))
    return float(1.0 / (1.0 + math.exp(-z)))


def cook_symbol(
    symbol: str,
    df: pd.DataFrame,
    spy: pd.Series | None,
    *,
    stride: int,
    st: dict[str, Any],
) -> dict[str, Any]:
    from analytics.gen_learn import vectorize
    from analytics.proven_online import credit_outcome, evaluate
    from analytics.residual_mom import residual_mom_12_1

    out = _enrich(df)
    c = out["Close"].astype(float) if "Close" in out.columns else out["Adj Close"].astype(float)
    spy_al = None
    if spy is not None:
        spy_al = spy.reindex(c.index).ffill()
    if len(c) < 280:
        return {"symbol": symbol, "n": 0, "X": [], "y": []}
    from analytics.horizon_picks import directional_conviction

    tight_rets: list[float] = []
    loose_rets: list[float] = []
    mom_rets: list[float] = []
    conv_rets: list[float] = []
    xs: list[np.ndarray] = []
    ys: list[float] = []
    n_tight = n_loose = 0
    for i in range(260, len(c) - 1, max(1, int(stride))):
        px = float(c.iloc[i])
        px1 = float(c.iloc[i + 1])
        if px <= 0:
            continue
        fwd = px1 / px - 1.0
        px5 = float(c.iloc[i - 5]) if i >= 5 else px
        px60 = float(c.iloc[i - 60]) if i >= 60 else px
        mom5 = px / px5 - 1.0 if px5 > 0 else 0.0
        mom60 = px / px60 - 1.0 if px60 > 0 else 0.0
        p_up = _p_from_mom(mom60)
        rs = 1.0
        hmm = 0.0
        if spy_al is not None:
            try:
                s_now = float(spy_al.iloc[i])
                s_20 = float(spy_al.iloc[max(0, i - 20)])
                s_5 = float(spy_al.iloc[max(0, i - 5)])
                if s_20 > 0:
                    hmm = s_now / s_20 - 1.0
                spy5 = (s_now / s_5 - 1.0) if s_5 > 0 else 0.0
                rs = 1.02 if mom5 >= spy5 else 0.98
            except Exception:
                pass
        row = out.iloc[i].copy()
        rm = residual_mom_12_1(
            c.iloc[: i + 1],
            spy_al.iloc[: i + 1] if spy_al is not None else None,
        )
        try:
            row["resid_mom_12_1"] = rm
        except Exception:
            pass
        volr = float(row["volume_ratio_20"]) if "volume_ratio_20" in out.columns else 1.0
        exec_c = 0.70 if volr >= 0.85 else 0.48
        ev = evaluate(
            symbol,
            p_up=p_up,
            exec_c=exec_c,
            mom_5d=mom5,
            rs_spy=rs,
            hmm=hmm,
            row=row,
            sleeve="fortress",
            use_live_events=False,
            st=st,
        )
        loose_rets.append(fwd)
        n_loose += 1
        if mom5 > 0:
            mom_rets.append(fwd)
        conv = directional_conviction(p_up)
        # Same rule the live book sorts on: a real long edge, not a flat 0.50.
        conviction_long = p_up >= 0.55 and conv >= 0.12
        if conviction_long:
            conv_rets.append(fwd)
        if ev.get("ok") or conviction_long:
            if ev.get("ok"):
                tight_rets.append(fwd)
                n_tight += 1
            cr = credit_outcome(symbol, fwd, side="LONG", persist=False, st=st)
            if cr.get("st"):
                st = cr["st"]
        try:
            xs.append(
                vectorize(
                    ev.get("votes") or {},
                    resid_raw=rm,
                    mom_5d=mom5,
                    rs_spy=rs,
                    p_up=p_up,
                )
            )
            ys.append(fwd)
        except Exception:
            pass
    return {
        "symbol": symbol,
        "n": n_loose,
        "n_tight": n_tight,
        "tight_mean": float(np.mean(tight_rets)) if tight_rets else None,
        "loose_mean": float(np.mean(loose_rets)) if loose_rets else None,
        "mom_mean": float(np.mean(mom_rets)) if mom_rets else None,
        "n_conv": len(conv_rets),
        "conv_mean": float(np.mean(conv_rets)) if conv_rets else None,
        "conv_hit": float(np.mean([1.0 if r > 0 else 0.0 for r in conv_rets])) if conv_rets else None,
        "tight_hit": float(np.mean([1.0 if r > 0 else 0.0 for r in tight_rets])) if tight_rets else None,
        "loose_hit": float(np.mean([1.0 if r > 0 else 0.0 for r in loose_rets])) if loose_rets else None,
        "st": st,
        "X": xs,
        "y": ys,
    }


def _cook_event_history(frames: list[tuple[str, pd.Series]]) -> dict[str, Any]:
    """Walk-forward the event model on the same historical closes. Deploy only if it beats naive."""
    from analytics.event_learn import redesign_until_best, samples_from_closes, save_state

    samples: list[Any] = []
    for sym, closes in frames:
        dates: list[date] = []
        try:
            from feature_engineering import load_earnings_dates

            dates = list(load_earnings_dates(sym) or [])
        except Exception:
            dates = []
        try:
            samples.extend(samples_from_closes(sym, closes, dates))
        except Exception as e:
            print(f"[HIST_COOK] event samples {sym}: {e}", flush=True)
        if len(samples) >= 6000:
            break
    if len(samples) < 80:
        print(f"[HIST_COOK] event-learn skip: {len(samples)} samples", flush=True)
        return {"ok": False, "n": len(samples)}
    st = redesign_until_best(samples)
    deployed = float(st.get("skill") or 0) > 0 or bool(st.get("beat_baseline"))
    if deployed:
        save_state(st)
    print(
        f"[HIST_COOK] event-learn n={st.get('n_samples')} ic={st.get('oos_ic')} "
        f"acc={st.get('oos_acc')} skill={st.get('skill')} deployed={deployed}",
        flush=True,
    )
    return {
        "ok": True,
        "deployed": deployed,
        "n": st.get("n_samples"),
        "ic": st.get("oos_ic"),
        "acc": st.get("oos_acc"),
        "skill": st.get("skill"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--max-symbols", type=int, default=int(os.getenv("HIST_COOK_MAX_SYMBOLS", "400")))
    ap.add_argument("--years", type=int, default=int(os.getenv("HIST_COOK_YEARS", "16")))
    ap.add_argument("--stride", type=int, default=int(os.getenv("HIST_COOK_STRIDE", "1")))
    args = ap.parse_args()
    from analytics.proven_online import default_state, save_state

    end = date.today()
    start = end - timedelta(days=max(365 * max(2, args.years), 800))
    start_s, end_s = start.isoformat(), end.isoformat()
    os.environ.setdefault("TRAIN_DATA_START", start_s)
    os.environ.setdefault("NETWORK_FIRST", "true")
    os.environ.setdefault("TRAIN_FORCE_YAHOO", "true")
    os.environ.setdefault("USE_LSTM_HEAD", "true")
    syms = _cook_symbols(max(1, int(args.max_symbols)))
    print(f"[HIST_COOK] proven walk-forward names={len(syms)} window={start_s}..{end_s} stride={args.stride}", flush=True)
    print("[HIST_COOK] fetching SPY", flush=True)
    spy_df = _closes("SPY", start_s, end_s)
    print(f"[HIST_COOK] SPY bars={0 if spy_df is None else len(spy_df)}", flush=True)
    spy = None
    if spy_df is not None and not spy_df.empty:
        col = "Adj Close" if "Adj Close" in spy_df.columns else "Close"
        spy = spy_df[col].astype(float)
    st = default_state()
    rows: list[dict[str, Any]] = []
    rows_closes: list[tuple[str, pd.Series]] = []
    used = 0
    for i, sym in enumerate(syms, 1):
        try:
            df = _closes(sym, start_s, end_s)
            if df is None or getattr(df, "empty", True):
                print(f"[HIST_COOK] skip {sym}: no bars", flush=True)
                continue
            col = "Adj Close" if "Adj Close" in df.columns else "Close"
            if col in df.columns:
                rows_closes.append((sym, df[col].astype(float)))
            rec = cook_symbol(sym, df, spy, stride=max(1, int(args.stride)), st=st)
            if rec.get("st"):
                st = rec.pop("st")
            lstm_rep = _train_hist_lstm(sym)
            rec["lstm"] = lstm_rep
            rows.append(rec)
            used += 1
            if i % 8 == 0 or rec.get("n_tight"):
                print(
                    f"[HIST_COOK] {i}/{len(syms)} {sym} bars={rec.get('n')} tight={rec.get('n_tight')} "
                    f"conv={rec.get('n_conv')} tight_mean={rec.get('tight_mean')} "
                    f"conv_mean={rec.get('conv_mean')} loose_mean={rec.get('loose_mean')}",
                    flush=True,
                )
        except Exception as e:
            print(f"[HIST_COOK] skip {sym}: {e}", flush=True)
    save_state(st)
    tights = [r for r in rows if r.get("n_tight")]
    tight_n = int(sum(int(r.get("n_tight") or 0) for r in rows))
    loose_n = int(sum(int(r.get("n") or 0) for r in rows))

    def _wavg(key: str, wkey: str) -> float | None:
        num = den = 0.0
        for r in rows:
            v, w = r.get(key), r.get(wkey)
            if v is None or not w:
                continue
            num += float(v) * float(w)
            den += float(w)
        return float(num / den) if den else None

    report = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "n_symbols": used,
        "n_loose": loose_n,
        "n_tight": tight_n,
        "tight_mean_1d": _wavg("tight_mean", "n_tight"),
        "loose_mean_1d": _wavg("loose_mean", "n"),
        "mom_mean_1d": _wavg("mom_mean", "n"),
        "conv_mean_1d": _wavg("conv_mean", "n_conv"),
        "conv_hit": _wavg("conv_hit", "n_conv"),
        "n_conv": int(sum(int(r.get("n_conv") or 0) for r in rows)),
        "tight_hit": _wavg("tight_hit", "n_tight"),
        "loose_hit": _wavg("loose_hit", "n"),
        "n_updates": st.get("n_updates"),
        "w": st.get("w"),
        "by_symbol": [{k: v for k, v in r.items() if k not in ("st", "X", "y")} for r in rows],
    }
    xs_all: list[Any] = []
    ys_all: list[float] = []
    for r in rows:
        xs_all.extend(r.get("X") or [])
        ys_all.extend(r.get("y") or [])
    if len(ys_all) >= 400:
        try:
            from analytics.gen_learn import fit_and_deploy

            X = np.stack(xs_all)
            y = np.asarray(ys_all, dtype=np.float64)
            gl = fit_and_deploy(X, y)
            report["gen_learn"] = {k: gl.get(k) for k in ("ok", "n", "n_oos", "ic", "acc", "skill")}
            print(
                f"[HIST_COOK] gen-learn n={gl.get('n')} oos={gl.get('n_oos')} "
                f"ic={gl.get('ic')} acc={gl.get('acc')} skill={gl.get('skill')}",
                flush=True,
            )
        except Exception as e:
            report["gen_learn"] = {"ok": False, "error": str(e)[:200]}
            print(f"[HIST_COOK] gen-learn skip: {e}", flush=True)
    try:
        report["event_learn"] = _cook_event_history(rows_closes)
    except Exception as e:
        report["event_learn"] = {"ok": False, "error": str(e)[:200]}
        print(f"[HIST_COOK] event-learn skip: {e}", flush=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, default=float), encoding="utf-8")
    print(
        f"[HIST_COOK] done names={used} tight_n={tight_n}/{loose_n} "
        f"tight_mean={report['tight_mean_1d']} loose_mean={report['loose_mean_1d']} "
        f"tight_hit={report['tight_hit']} updates={st.get('n_updates')}",
        flush=True,
    )
    beat = (report["tight_mean_1d"] or -1) >= (report["loose_mean_1d"] or 0)
    conv_beat = (report.get("conv_mean_1d") or -1) >= (report["loose_mean_1d"] or 0)
    print(f"[HIST_COOK] tight vs always-long: {'BEATS' if beat else 'lags (weights still cooked)'}", flush=True)
    print(
        f"[HIST_COOK] conviction vs always-long: {'BEATS' if conv_beat else 'lags'} "
        f"n={report.get('n_conv')} mean={report.get('conv_mean_1d')} hit={report.get('conv_hit')}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback

        traceback.print_exc()
        raise SystemExit(1)
