"""Local paper book for the government, across the cached stock market.

Never sends an Alpaca order. This Mac is the observe host. Each pass ranks
every cached common stock, lets the desks vote, and credits a new close once.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ["LEARN_FIT_NEURAL_ON_FILL"] = "false"
os.environ.setdefault("FATE_ORDER_ROLE", "observe")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analytics.government_paper import learn_close, load_market_panels, run_market_book, study_losses

JOURNAL = ROOT / "data" / "ops" / "government_paper.json"


def _key(trade: dict) -> str:
    return f"{trade.get('symbol')}|{trade.get('entry_t')}|{trade.get('t')}|{trade.get('reason')}"


def _load_credited() -> set[str]:
    if not JOURNAL.is_file():
        return set()
    try:
        doc = json.loads(JOURNAL.read_text(encoding="utf-8"))
    except Exception:
        return set()
    return {str(k) for k in (doc.get("credited") or [])}


def _grow(have: set[str], n: int = 20) -> int:
    """Pull a few model names that are not in the price cache yet."""
    from fortress_universe import is_core_trainable_equity, symbols_with_daily_models
    from data_platform.market_prices import fetch_daily

    missing = [s for s in symbols_with_daily_models() if s not in have and is_core_trainable_equity(s)]
    if not missing:
        return 0
    # Rotate so each pass reaches a different slice of the model universe.
    shift = int(time.time() // 60) % len(missing)
    batch = missing[shift:] + missing[:shift]
    added = 0
    root = ROOT / "data" / "cache" / "prices"
    root.mkdir(parents=True, exist_ok=True)
    for sym in batch[:n]:
        try:
            df = fetch_daily(sym, "2026-03-01", time.strftime("%Y-%m-%d"))
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


def cycle(end: str, *, learn: bool) -> dict:
    panels = load_market_panels()
    if not panels:
        raise SystemExit("no cached names")
    prior_weights: dict[str, float] = {}
    if JOURNAL.is_file():
        try:
            prior_weights = {
                str(k): float(v)
                for k, v in (json.loads(JOURNAL.read_text(encoding="utf-8")).get("weights") or {}).items()
            }
        except Exception:
            prior_weights = {}
    credited = _load_credited()

    def _learn(sym: str, gain: float, extra: dict | None = None) -> dict:
        extra = extra or {}
        key = f"{sym}|{extra.get('entry_t')}|{extra.get('t')}|{extra.get('reason')}"
        if key in credited:
            return {"skipped": key}
        credited.add(key)
        return learn_close(sym, gain, extra)

    book = run_market_book(
        panels,
        equity=100_000,
        ticket=100_000,
        max_names=10,
        sessions=60,
        learn=_learn if learn else None,
        progress=lambda msg: print(msg, flush=True),
        start_weights=prior_weights or None,
    )
    print("studying the closed losses", flush=True)
    lesson = study_losses(book["trades"], book["weights"], rounds=3)
    print(
        f"studied losses={lesson['losses']} steps={lesson['steps']} neural={lesson['neural']}",
        flush=True,
    )
    book["weights"] = lesson["weights"]
    for trade in book["trades"]:
        if trade.get("side") == "SELL":
            credited.add(_key(trade))
    sells = [t for t in book["trades"] if t.get("side") == "SELL"]
    out = {
        "asof": book.get("asof") or end,
        "equity": book["equity"],
        "cash": book["cash"],
        "start": book["start"],
        "pnl": book["equity"] - book["start"],
        "n_trades": len(book["trades"]),
        "open": book["open"],
        "lots": book["lots"],
        "trades": book["trades"],
        "curve": [round(float(x), 2) for x in book["curve"]],
        "dates": book.get("dates") or [],
        "weights": {k: round(float(v), 4) for k, v in book["weights"].items()},
        "learns": len(book["learns"]),
        "study": {
            "losses": lesson["losses"],
            "steps": lesson["steps"],
            "rounds": lesson["rounds"],
            "neural": lesson["neural"],
        },
        "credited": sorted(credited),
        "names": book.get("names"),
        "desk_rounds": book.get("desk_rounds"),
        "convened": book.get("convened"),
        "screened": book.get("screened"),
        "census": book.get("census"),
        "sections": {k: round(float(v), 4) for k, v in (book.get("sections") or {}).items()},
        "wanted": book.get("wanted") or [],
        "closed": book.get("closed"),
        "wins": book.get("wins"),
        "order_role": "observe",
        "broker": "local-ledger",
        "scope": "cached-common-stocks",
    }
    out["closed"] = len(sells)
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    JOURNAL.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(
        f"paper equity={out['equity']:.2f} pnl={out['pnl']:.2f} "
        f"open={out['open']} closed={out['closed']} wins={out['wins']} "
        f"names={out['names']} desks={out['desk_rounds']} asof={out['asof']}",
        flush=True,
    )
    try:
        added = _grow(set(panels), 20)
        print(f"grew {added} names into the price cache", flush=True)
    except Exception as e:
        print(f"grow failed: {e}", flush=True)
    return out


def main() -> None:
    import datetime as dt

    once = "--once" in sys.argv
    while True:
        end = dt.date.today().isoformat()
        # First pass records closes already in the journal and does not
        # teach them a second time. Later passes teach only a new close.
        learn = JOURNAL.is_file() and bool(_load_credited())
        try:
            cycle(end, learn=learn)
        except Exception as e:
            print(f"cycle failed: {e}", flush=True)
        if once:
            return
        time.sleep(20)


if __name__ == "__main__":
    main()
