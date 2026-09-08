#!/usr/bin/env python3
"""Full-stack historical evaluation: models + industry + category + family rank."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _acc_top_q(y: np.ndarray, p: np.ndarray, q: float = 0.2) -> float:
    n = len(y)
    if n < 5:
        return float("nan")
    k = max(1, int(n * q))
    order = np.argsort(-p)[:k]
    return float((y[order] == 1).mean())


def eval_symbol(
    symbol: str,
    *,
    start: str,
    end: str | None,
    hold_days: int = 5,
) -> dict:
    from feature_engineering import build_features
    from ml_model import load_raw_bundle, predict_row_details
    from symbol_aliases import resolve_model_ticker

    sym = symbol.strip().upper()
    model_sym = resolve_model_ticker(sym) or sym
    out: dict = {"symbol": sym, "ok": False}
    if model_sym != sym:
        out["model_symbol"] = model_sym
    if not resolve_model_ticker(sym):
        out["error"] = "no_model"
        return out

    try:
        df = build_features(sym, start, end)
    except Exception as e:
        out["error"] = f"features:{e}"
        return out
    if df.empty or "target" not in df.columns:
        out["error"] = "empty_features"
        return out

    model_path = str(ROOT / "models" / f"{model_sym}_model.pkl")
    try:
        load_raw_bundle(model_path)
    except Exception as e:
        out["error"] = f"model_load:{e}"
        return out

    probs: list[float] = []
    targets: list[int] = []
    fwd_rets: list[float] = []
    industry_deltas: list[float] = []
    category_deltas: list[float] = []
    blocks = 0
    warns = 0

    tail = df.tail(min(120, len(df)))
    for i, (_, row) in enumerate(tail.iterrows()):
        try:
            det = predict_row_details(model_path, row)
            p = float(det.get("p_up") or 0.5)
        except Exception:
            continue
        probs.append(p)
        targets.append(int(row.get("target", 0)))
        ret_col = f"fwd_ret_{hold_days}d" if f"fwd_ret_{hold_days}d" in row.index else "returns"
        fwd_rets.append(float(row.get(ret_col, row.get("returns", 0.0)) or 0.0))

        if i == len(tail) - 1:
            try:
                from analytics.industries.integration import blended_rank_adjustment, get_industry_profile

                rf = {k: float(row[k]) for k in row.index if isinstance(row.get(k), (int, float, np.floating))}
                prof = get_industry_profile(sym)
                adj = blended_rank_adjustment(sym, rf)
                industry_deltas.append(float(adj.get("score_delta") or 0.0))
                cd = adj.get("category_decision") or {}
                category_deltas.append(float(cd.get("score_delta") or 0.0))
                if cd.get("block_buy"):
                    blocks += 1
                if cd.get("warn_buy"):
                    warns += 1
                out["industry_id"] = prof.get("primary_industry_id")
                out["ai_confidence"] = prof.get("ai_confidence") or prof.get("confidence")
            except Exception:
                pass

    if len(probs) < 20:
        out["error"] = f"too_few_rows:{len(probs)}"
        return out

    y = np.array(targets)
    p = np.array(probs)
    r = np.array(fwd_rets)
    top_mask = p >= np.quantile(p, 0.8)
    out.update(
        {
            "ok": True,
            "rows": len(probs),
            "acc_all": float(((p > 0.5).astype(int) == y).mean()) if len(y) else float("nan"),
            "acc_top20": _acc_top_q(y, p, 0.2),
            "avg_fwd_ret_top20": float(r[top_mask].mean()) if top_mask.any() else float("nan"),
            "avg_fwd_ret_all": float(r.mean()),
            "industry_score_delta": industry_deltas[-1] if industry_deltas else 0.0,
            "category_score_delta": category_deltas[-1] if category_deltas else 0.0,
            "category_blocks": blocks,
            "category_warns": warns,
        }
    )
    return out


def _valid_symbols(symbols: list[str]) -> list[str]:
    from symbol_aliases import resolve_model_ticker

    out: list[str] = []
    for s in symbols:
        sym = str(s or "").strip().upper()
        if not sym or len(sym) > 6:
            continue
        if sym.startswith("T") and sym[1:].isdigit():
            continue
        if not resolve_model_ticker(sym):
            continue
        out.append(sym)
    return out


def _megacap_fallback(limit: int) -> list[str]:
    return [
        "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "BRK-B", "AVGO", "JPM", "XOM",
        "ORCL", "JNJ", "V", "MA", "COST", "HD", "PG", "UNH", "LLY", "BAC",
    ][:limit]


def run_eval(
    *,
    symbols: list[str],
    start: str,
    end: str | None,
    hold_days: int = 5,
) -> dict:
    results: list[dict] = []
    ok_rows: list[dict] = []
    for sym in symbols:
        rep = eval_symbol(sym, start=start, end=end, hold_days=hold_days)
        results.append(rep)
        if rep.get("ok"):
            ok_rows.append(rep)
        status = "OK" if rep.get("ok") else rep.get("error", "?")
        print(f"  [{status}] {sym}", flush=True)

    def _mean(key: str) -> float:
        vals = [float(r[key]) for r in ok_rows if key in r and not np.isnan(r[key])]
        return float(np.mean(vals)) if vals else float("nan")

    summary = {
        "evaluated_at_utc": _now(),
        "start": start,
        "end": end,
        "hold_days": hold_days,
        "symbols_requested": len(symbols),
        "symbols_ok": len(ok_rows),
        "mean_acc_top20": _mean("acc_top20"),
        "mean_acc_all": _mean("acc_all"),
        "mean_fwd_ret_top20": _mean("avg_fwd_ret_top20"),
        "mean_fwd_ret_all": _mean("avg_fwd_ret_all"),
        "mean_industry_delta": _mean("industry_score_delta"),
        "mean_category_delta": _mean("category_score_delta"),
        "total_category_blocks": sum(int(r.get("category_blocks") or 0) for r in ok_rows),
        "results": results,
    }
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Full-stack historical evaluation")
    ap.add_argument("--symbol", "-s", action="append", default=[], help="Evaluate one symbol (repeatable)")
    ap.add_argument("--start", default=os.getenv("FULL_STACK_EVAL_START", "2023-01-01"))
    ap.add_argument("--end", default=os.getenv("FULL_STACK_EVAL_END") or None)
    ap.add_argument("--limit", type=int, default=int(os.getenv("FULL_STACK_EVAL_LIMIT", "30")))
    ap.add_argument("--tier", default="top100", choices=("top100", "anchors", "config"))
    ap.add_argument("--hold-days", type=int, default=int(os.getenv("FULL_STACK_HOLD_DAYS", "5")))
    ap.add_argument("--json-out", default=str(ROOT / "reports" / "full_stack_historical_eval.json"))
    args = ap.parse_args()

    if args.symbol:
        symbols = [s.strip().upper() for s in args.symbol if s.strip()]
        tier_label = "single"
    elif args.tier == "top100":
        from fortress_universe import load_top100_symbols

        raw = load_top100_symbols()
        symbols = _valid_symbols(raw)
        if len(symbols) < max(5, args.limit // 2):
            symbols = _valid_symbols(_megacap_fallback(args.limit * 2))
        symbols = symbols[: args.limit]
        tier_label = "top100"
    elif args.tier == "anchors":
        from analytics.industries.anchors import ALL_ANCHORS

        symbols = []
        for iid, anc in ALL_ANCHORS.items():
            if iid == "unclassified":
                continue
            t = getattr(anc, "ANCHOR_TICKER", "") or (getattr(anc, "SMOKE_TICKERS", ()) or [""])[0]
            if t:
                symbols.append(t)
            if len(symbols) >= args.limit:
                break
        tier_label = "anchors"
    else:
        import config

        symbols = list(config.TRAIN_TICKERS)[: args.limit]
        tier_label = args.tier

    symbols = _valid_symbols(symbols) if not args.symbol else symbols
    if not symbols:
        print("[full-stack] no valid symbols/models", flush=True)
        return 1

    print(f"=== full-stack historical eval tier={tier_label} n={len(symbols)} start={args.start} ===", flush=True)
    summary = run_eval(symbols=symbols, start=args.start, end=args.end, hold_days=args.hold_days)

    if args.symbol and len(symbols) == 1:
        rep = summary["results"][0] if summary.get("results") else {}
        print(json.dumps(rep, indent=2), flush=True)

    out_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n=== SUMMARY ===", flush=True)
    print(f"  symbols ok:     {summary['symbols_ok']}/{summary['symbols_requested']}", flush=True)
    print(f"  acc@top20:      {summary['mean_acc_top20']:.4f}", flush=True)
    print(f"  acc all:        {summary['mean_acc_all']:.4f}", flush=True)
    print(f"  fwd ret top20:  {summary['mean_fwd_ret_top20']:.4f}", flush=True)
    print(f"  industry delta: {summary['mean_industry_delta']:+.4f}", flush=True)
    print(f"  category delta: {summary['mean_category_delta']:+.4f}", flush=True)
    print(f"  report:         {out_path}", flush=True)
    return 0 if summary["symbols_ok"] >= max(5, len(symbols) // 4) else 1


if __name__ == "__main__":
    raise SystemExit(main())
