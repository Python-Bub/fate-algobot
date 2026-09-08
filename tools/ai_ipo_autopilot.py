#!/usr/bin/env python3
"""Autopilot: NewsAPI IPO discovery for any listing + trade liquid AI proxies until tickers exist."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Tradeable today while private names have no symbol (optional env override).
_DEFAULT_PROXY_TICKERS = ("MSFT", "NVDA", "GOOGL", "AMZN", "META", "AMD", "AVGO", "ORCL")


def autopilot_enabled() -> bool:
    return os.getenv("AI_IPO_AUTOPILOT", "true").lower() in ("1", "true", "yes")


def proxy_tickers() -> list[str]:
    raw = os.getenv("AI_IPO_PROXY_TICKERS", ",".join(_DEFAULT_PROXY_TICKERS))
    return list(dict.fromkeys(s.strip().upper() for s in raw.split(",") if s.strip()))


def watch_names() -> list[str]:
    """Optional extra names from env only — primary discovery is NewsAPI (intel.ipo_news_discovery)."""
    names: list[str] = []
    raw = os.getenv("IPO_WATCH_NAMES", "")
    names.extend(n.strip() for n in raw.split(",") if n.strip())
    wl = ROOT / "data/ipo_watchlist.txt"
    if wl.is_file():
        for ln in wl.read_text(encoding="utf-8", errors="replace").splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                names.append(ln.split("#", 1)[0].strip())
    return list(dict.fromkeys(names))


def is_proxy_ticker(ticker: str) -> bool:
    return ticker.strip().upper() in set(proxy_tickers())


def paper_proxy_score_boost() -> float:
    return float(os.getenv("AI_IPO_PROXY_SCORE_BOOST", "0.35"))


def bootstrap(*, train: bool = True) -> dict:
    """News-driven IPO queue + ensure proxy models exist (unattended)."""
    if not autopilot_enabled():
        return {"skipped": "AI_IPO_AUTOPILOT=false"}

    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    out: dict = {"proxies": proxy_tickers()}

    from tools.listing_watch import collect_new_listing_candidates, queue_symbols, train_queued_if_idle

    found = collect_new_listing_candidates()
    queued = queue_symbols(found)
    out["ipo_discovered"] = found
    out["ipo_queued"] = queued

    from fortress_universe import is_tradeable_equity
    from model_trainer import training_saved_model

    # Proxies are a separate path — never mix megacaps into new_listing_train_queue.
    need_train = [
        t
        for t in proxy_tickers()
        if is_tradeable_equity(t) and not training_saved_model(t)
    ]
    out["proxies_need_train"] = need_train

    if train and need_train:
        try:
            from tools.train_coordination import should_defer_secondary_training

            if should_defer_secondary_training():
                out["train_deferred"] = "top100_perfect running"
                need_train = []
        except Exception:
            pass

    if train and need_train:
        batch = int(os.getenv("IPO_TRAIN_BATCH", "8"))
        sym_file = ROOT / "data/ai_ipo_proxy_batch.json"
        py = ROOT / "venv/bin/python"
        for i in range(0, len(need_train), batch):
            try:
                from tools.train_coordination import should_defer_secondary_training

                if should_defer_secondary_training():
                    out.setdefault("proxy_train_rc", []).append("deferred_heavy")
                    break
            except Exception:
                pass
            chunk = need_train[i : i + batch]
            sym_file.write_text(json.dumps(chunk), encoding="utf-8")
            env = os.environ.copy()
            env.update(
                {
                    "TRAIN_SYMBOLS_FILE": str(sym_file),
                    "TRAIN_TICKER_TIMEOUT_SEC": os.getenv("IPO_TRAIN_TIMEOUT_SEC", "600"),
                    "AUTO_RETRAIN_LOW_TOP20": "false",
                    "MULTI_HORIZON_TRAIN": "true",
                    "KEEP_WEAK_HEADS": "true",
                    "COALESCE_EXISTING_HEADS": "true",
                }
            )
            rc = subprocess.call(
                [str(py), "-u", "parallel_train.py", "--pipeline", "daily", "--workers", "2"],
                cwd=ROOT,
                env=env,
            )
            out.setdefault("proxy_train_rc", []).append(rc)
            if rc != 0:
                break

    # Also train any real new-listing queue symbols (non-proxies) if idle.
    if train and os.getenv("AI_IPO_TRAIN_LISTING_QUEUE", "true").lower() in (
        "1",
        "true",
        "yes",
    ):
        try:
            from tools.train_coordination import should_defer_secondary_training

            deferred = should_defer_secondary_training()
        except Exception:
            deferred = False
        if not deferred:
            rc = train_queued_if_idle(max_symbols=int(os.getenv("IPO_TRAIN_BATCH", "8")))
            out.setdefault("listing_train_rc", []).append(rc)

    # Advanced multi-head stack for IPO proxies + newly listed tickers
    # (SpaceX/OpenAI stay private-watch; liquid proxies get daily+intraday+LSTM+strong).
    if train and os.getenv("AI_IPO_ADVANCED_TRAIN", "true").lower() in ("1", "true", "yes"):
        try:
            from universe_lifecycle.protocol import run_new_listing_protocol, run_top50_protocol

            proxies_have = [t for t in proxy_tickers() if training_saved_model(t)]
            if proxies_have:
                out["advanced"] = run_top50_protocol(
                    proxies_have[: int(os.getenv("AI_IPO_ADVANCED_CAP", "12"))]
                )
            real_new = [s for s in (queued or []) if s and not is_proxy_ticker(s)]
            if real_new:
                out["advanced_new"] = run_new_listing_protocol(
                    real_new[: int(os.getenv("AI_IPO_NEW_CAP", "8"))]
                )
        except Exception as e:
            out["advanced_error"] = str(e)

    state = ROOT / "data/autopilot_state.json"
    st = {}
    if state.is_file():
        try:
            st = json.loads(state.read_text(encoding="utf-8"))
        except Exception:
            st = {}
    st["last_bootstrap"] = datetime.now(timezone.utc).isoformat()
    st["paused"] = False
    st.update({k: v for k, v in out.items() if k != "train_rc"})
    state.write_text(json.dumps(st, indent=2), encoding="utf-8")
    return out


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--no-train", action="store_true")
    args = ap.parse_args()
    r = bootstrap(train=not args.no_train)
    print(json.dumps(r, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
