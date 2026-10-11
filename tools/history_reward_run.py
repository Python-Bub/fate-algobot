"""Full historical reward run. One pass, all cached history, all cores.

No web calls during the walk. A win grants reward. A loss denies it.
This process does not send broker orders.
"""

from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

os.environ["LEARN_FIT_NEURAL_ON_FILL"] = "false"
os.environ["FATE_ORDER_ROLE"] = "observe"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROGRESS = ROOT / "data" / "ops" / "history_train_progress.json"
STATE = ROOT / "data" / "ops" / "history_train_state.json"
BROWSE_MAX = int(os.getenv("HISTORY_BROWSE_MAX", "40"))


def _signal_job(item: tuple[str, str]) -> dict | None:
    sym, path = item
    import pandas as pd

    from analytics.history_reward import online_signals

    try:
        df = pd.read_parquet(path, columns=["Close"])
    except Exception:
        return None
    if df is None or df.empty or "Close" not in df.columns:
        return None
    dates = [str(x)[:10] for x in df.index]
    closes = [float(x) for x in df["Close"].tolist()]
    keep = [(d, c) for d, c in zip(dates, closes) if c > 0]
    if len(keep) < 80 or keep[-1][1] < 1.0:
        return None
    dates = [d for d, _ in keep]
    closes = [c for _, c in keep]
    sig = online_signals(closes)
    hold = 0
    if os.getenv("HISTORY_TIMEFRAMES", "false").lower() in ("1", "true", "yes"):
        from analytics.timeframe_learner import timeframe_signals

        sig = timeframe_signals(closes)
        hold = 5
    elif os.getenv("HISTORY_USE_MODELS", "false").lower() in ("1", "true", "yes"):
        from analytics.model_edge import holdout_confident_p

        model = Path(path).resolve().parents[3] / "models" / f"{sym}_model.pkl"
        confident = holdout_confident_p(sym, model, Path(path))
        blended: list = []
        for i, d in enumerate(dates):
            base = sig[i]
            p_model = confident.get(d)
            if base is None or p_model is None:
                blended.append(None)
            else:
                _p, avg_up, avg_down = base
                blended.append((float(p_model), avg_up, avg_down))
        sig = blended
        hold = 5
    return {"symbol": sym, "dates": dates, "closes": closes, "sig": sig, "hold": hold}


def _convene_batch(cases: list[tuple]) -> list[dict]:
    from analytics.ai_government import convene

    return [convene(case, weights=weights, record=False) for case, weights in cases]


def _yahoo_symbol(sym: str) -> str:
    return sym.strip().upper().replace(".", "-")


def _listed_stocks() -> list[str]:
    """Every US common listing Nasdaq publishes. Test issues are already dropped."""
    os.environ["UNIVERSE_FETCH_NETWORK"] = "true"
    from fortress_universe import is_core_trainable_equity
    from universe_provider import download_us_listed_symbols

    out = []
    for raw in download_us_listed_symbols(ROOT / "data" / "universe" / "us_equity_symbols.txt"):
        sym = _yahoo_symbol(raw)
        if is_core_trainable_equity(sym):
            out.append(sym)
    return sorted(set(out))


def _save_closes(path: Path, series) -> bool:
    import pandas as pd

    series = series.dropna()
    if len(series) < 80:
        return False
    frame = pd.DataFrame({"Close": [float(x) for x in series.tolist()]}, index=series.index)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path)
    return True


def _closes_for(df, sym: str):
    import pandas as pd

    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        for level in (0, 1):
            values = df.columns.get_level_values(level)
            if sym not in values:
                continue
            sub = df.xs(sym, axis=1, level=level)
            if "Close" in getattr(sub, "columns", []):
                return sub["Close"]
        return None
    if "Close" in df.columns:
        return df["Close"]
    return None


def _yahoo_fill(symbols: list[str], price_root: Path) -> int:
    """Daily bars from Yahoo for listings we do not already have. Before the walk."""
    import yfinance as yf

    need = []
    for sym in symbols:
        path = price_root / f"{sym}.parquet"
        try:
            have_it = path.is_file() and path.stat().st_size >= 5_000
        except OSError:
            have_it = False
        if not have_it:
            need.append(sym)
    print(f"yahoo missing={len(need)} of {len(symbols)}", flush=True)
    added = 0
    batch = 40
    for i in range(0, len(need), batch):
        chunk = need[i : i + batch]
        try:
            df = yf.download(
                chunk,
                period="max",
                auto_adjust=True,
                group_by="ticker",
                threads=True,
                progress=False,
            )
        except Exception as exc:
            print(f"yahoo batch {i} failed {exc}", flush=True)
            time.sleep(2)
            continue
        for sym in chunk:
            series = _closes_for(df, sym)
            if series is None:
                continue
            if _save_closes(price_root / f"{sym}.parquet", series):
                added += 1
        print(f"yahoo {min(i + batch, len(need))}/{len(need)} saved={added}", flush=True)
        time.sleep(0.5)
    return added


def _browse(have: set[str]) -> int:
    """A small quota of past-price fetches before the walk. Not during it."""
    if os.getenv("HISTORY_BROWSE", "true").lower() not in ("1", "true", "yes"):
        return 0
    from data_platform.market_prices import fetch_daily
    from fortress_universe import is_core_trainable_equity, symbols_with_daily_models

    missing = [s for s in symbols_with_daily_models() if s not in have and is_core_trainable_equity(s)]
    end = time.strftime("%Y-%m-%d")
    added = 0
    root = ROOT / "data" / "cache" / "prices"
    root.mkdir(parents=True, exist_ok=True)
    for sym in missing[:BROWSE_MAX]:
        try:
            df = fetch_daily(sym, "2016-01-01", end)
        except Exception:
            continue
        if df is None or df.empty or "Close" not in getattr(df, "columns", []):
            continue
        try:
            df.to_parquet(root / f"{sym}.parquet")
        except Exception:
            continue
        added += 1
    return added


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    from fortress_universe import is_core_trainable_equity

    workers = max(1, os.cpu_count() or 1)
    price_root = ROOT / "data" / "cache" / "prices"
    price_root.mkdir(parents=True, exist_ok=True)
    all_stocks = os.getenv("HISTORY_ALL_STOCKS", "false").lower() in ("1", "true", "yes")
    model_root = ROOT / "models"
    trained = {
        p.name[: -len("_model.pkl")].upper()
        for p in model_root.glob("*_model.pkl")
        if p.stat().st_size >= 20_000
    }
    yahoo_added = 0
    if all_stocks:
        listed = _listed_stocks()
        print(f"listed stocks={len(listed)}", flush=True)
        if os.getenv("HISTORY_SKIP_YAHOO", "false").lower() in ("1", "true", "yes"):
            yahoo_added = 0
            print("yahoo skipped, using prices already on disk", flush=True)
        else:
            yahoo_added = _yahoo_fill(listed, price_root)
        wanted = set(listed)
    else:
        wanted = None
    items = []
    for path in sorted(price_root.glob("*.parquet")):
        sym = path.stem.upper()
        if not is_core_trainable_equity(sym):
            continue
        if wanted is not None and sym not in wanted:
            continue
        if wanted is None and trained and sym not in trained:
            continue
        items.append((sym, str(path)))
    browsed = 0 if all_stocks else _browse({sym for sym, _ in items})
    if browsed:
        have = {sym for sym, _ in items}
        for path in sorted(price_root.glob("*.parquet")):
            sym = path.stem.upper()
            if sym in have or not is_core_trainable_equity(sym):
                continue
            if trained and sym not in trained:
                continue
            items.append((sym, str(path)))
    print(
        f"history names={len(items)} workers={workers} browsed={browsed} "
        f"yahoo={yahoo_added} all_stocks={all_stocks}",
        flush=True,
    )
    t0 = time.time()
    panels: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        done = 0
        for rec in pool.map(_signal_job, items, chunksize=8):
            done += 1
            if rec:
                sym = rec.pop("symbol")
                panels[sym] = rec
            if done % 100 == 0 or done == len(items):
                print(f"signals {done}/{len(items)} kept={len(panels)}", flush=True)

        def batch_fn(cases: list[tuple]) -> list[dict]:
            if len(cases) < 64:
                return _convene_batch(cases)
            chunks = [cases[i : i + 32] for i in range(0, len(cases), 32)]
            out: list[dict] = []
            for part in pool.map(_convene_batch, chunks, chunksize=1):
                out.extend(part)
            return out

        state = None
        if STATE.is_file() and "--fresh" not in sys.argv:
            try:
                state = json.loads(STATE.read_text(encoding="utf-8"))
            except Exception:
                state = None

        def on_progress(snap: dict) -> None:
            elapsed = time.time() - t0
            done_n = int(snap["dates_done"])
            total = max(1, int(snap["dates_total"]))
            rate = done_n / elapsed if elapsed > 0 else 0
            eta_h = ((total - done_n) / rate / 3600.0) if rate else None
            public = {
                "phase": "walk",
                "date": snap["date"],
                "dates_done": done_n,
                "dates_total": total,
                "pct": round(100.0 * done_n / total, 2),
                "equity": snap["equity"],
                "cash": snap["cash"],
                "open": snap["open"],
                "bought": snap["bought"],
                "closed": snap["closed"],
                "days_invested": snap.get("days_invested"),
                "turnover": "one session",
                "wins": snap["wins"],
                "losses": snap["losses"],
                "reward_granted": snap["granted"],
                "reward_denied": snap["denied"],
                "reward_sum": snap["reward_sum"],
                "convened": snap["convened"],
                "names": snap["names"],
                "workers": workers,
                "browsed": browsed,
                "yahoo_added": yahoo_added,
                "all_stocks": all_stocks,
                "internet_during_walk": False,
                "why": snap["why"],
                "elapsed_h": round(elapsed / 3600.0, 3),
                "eta_h": None if eta_h is None else round(eta_h, 2),
            }
            _write(PROGRESS, public)
            _write(
                STATE,
                {
                    "last_date": snap["last_date"],
                    "cash": snap["cash_state"],
                    "weights": snap["weights"],
                    "lots": snap["lots"],
                    "wins": snap["wins_n"],
                    "losses": snap["losses_n"],
                    "closed": snap["closed_n"],
                    "convened": snap["convened_n"],
                    "bought": snap["bought_n"],
                    "granted": snap["granted_n"],
                    "denied": snap["denied_n"],
                    "reward_sum": snap["reward_n"],
                },
            )
            print(
                f"progress {public['pct']}% {public['date']} equity={public['equity']} "
                f"closed={public['closed']} reward={public['reward_sum']} "
                f"granted={public['reward_granted']} denied={public['reward_denied']} "
                f"eta_h={public['eta_h']}",
                flush=True,
            )
            if snap["why"]:
                print(f"why {snap['why']}", flush=True)

        from analytics.history_reward import run_history

        result = run_history(
            panels,
            batch_fn=batch_fn,
            progress=on_progress,
            state=state,
            review_every=1,
            max_avg_down=0.05 if os.getenv("HISTORY_USE_MODELS", "false").lower() in ("1", "true", "yes") else 0.025,
        )
    public = {
        "phase": "done",
        "equity": result["equity"],
        "closed": result["closed"],
        "wins": result["wins"],
        "losses": result["losses"],
        "reward_sum": result["reward_sum"],
        "reward_granted": result["granted"],
        "reward_denied": result["denied"],
        "convened": result["convened"],
        "bought": result["bought"],
        "dates": result["dates"],
        "names": len(panels),
        "actions": result["actions"],
        "vetoes": result["vetoes"],
        "internet_during_walk": False,
        "elapsed_h": round((time.time() - t0) / 3600.0, 3),
    }
    _write(PROGRESS, public)
    print("done", json.dumps({k: public[k] for k in ("equity", "closed", "wins", "losses", "reward_sum")}), flush=True)


if __name__ == "__main__":
    main()
