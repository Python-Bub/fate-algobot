#!/usr/bin/env python3
"""All tickers × horizon heads — model probabilities (not certainties) + neural status."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

HORIZONS: list[tuple[str, int, str, str]] = [
    ("1d", 1, "p_daily", "fwd_1d_return"),
    ("5d", 5, "p_short", "fwd_5d_return"),
    ("1mo", 21, "p_long", "fwd_20d_return"),
    ("3mo", 63, "p_xlong", "fwd_20d_return"),
    ("6mo", 126, "p_xlong", "fwd_20d_return"),
    ("1yr", 252, "p_xlong", "fwd_20d_return"),
]


def _pct_label(p: float | None, *, raw: bool = False) -> str:
    if p is None:
        return "—"
    from analytics.probability_calibrate import display_chance_pct

    ch = display_chance_pct(float(p))
    opp = 100 - ch
    if raw:
        return f"p_up={ch}% (p_down={opp}%)"
    if ch >= 50:
        return f"↑{ch}%"
    return f"↓{opp}%"


def _resolve_p(row: dict, prefix: str, hold_days: int) -> float | None:
    from analytics.family_horizons import horizon_effective_probability

    raw, _ = horizon_effective_probability(row, prefix, hold_days=hold_days)
    return raw


def _neural_blend(p: float | None, neural: float | None, *, weight: float) -> float | None:
    if p is None:
        return None
    if neural is None:
        return float(p)
    nw = max(0.0, min(1.0, weight))
    return float((1.0 - nw) * float(p) + nw * float(neural))


def _neural_status(sym: str, row: dict) -> dict[str, Any]:
    """Live neural readiness (not stale report snapshot)."""
    from online_learning.neural_ensemble import (
        _load_replay,
        _model_paths,
        neural_ensemble_details,
        use_neural_ensemble,
    )

    if not use_neural_ensemble():
        return {
            "status": "disabled",
            "reason": "USE_NEURAL_ENSEMBLE=false or torch missing",
            "replay_rows": 0,
            "models_loaded": 0,
            "ensemble_p_up": None,
        }

    replay = len(_load_replay(sym, max_samples=5000))
    models = sum(1 for p in _model_paths(sym).values() if p.is_file())
    state = row.get("online_state") if isinstance(row.get("online_state"), dict) else {}
    if not state:
        state = {
            "p_up_base": float(row.get("p_up") or 0.5),
            "p_short_model": float(row.get("p_short_model") or 0.5),
            "p_long_model": float(row.get("p_long_model") or row.get("p_up") or 0.5),
            "execution_confidence": float(row.get("execution_confidence") or 0.5),
            "sentiment": float(row.get("sentiment") or 0.0),
            "news_factor": float(row.get("news_factor") or 0.0),
            "transcript_factor": float(row.get("transcript_factor") or 0.0),
            "volume_ratio": float(row.get("volume_ratio") or 1.0),
            "momentum_5d": float(row.get("momentum_5d") or 0.0),
            "rs_spy": float(row.get("rs_spy") or 1.0),
            "dip_signal": float(row.get("dip_signal") or 0.0),
            "atr_14": float(row.get("atr_14") or 1.0),
            "alpha_proxy_20": float(row.get("rs_spy") or 1.0) - 1.0,
        }
    det = neural_ensemble_details(sym, state)
    if det and det.get("ensemble_p_up") is not None:
        return {
            "status": "ready",
            "reason": "ok",
            "replay_rows": replay,
            "models_loaded": int(det.get("n_models_loaded") or models),
            "ensemble_p_up": float(det["ensemble_p_up"]),
            "disagreement_std": det.get("disagreement_std"),
        }
    if models > 0 and replay >= 8:
        return {
            "status": "partial",
            "reason": "checkpoints exist but ensemble returned no preds",
            "replay_rows": replay,
            "models_loaded": models,
            "ensemble_p_up": None,
        }
    if replay < 8:
        return {
            "status": "offline",
            "reason": f"insufficient replay ({replay} rows; need ~24+ to train)",
            "replay_rows": replay,
            "models_loaded": models,
            "ensemble_p_up": None,
        }
    return {
        "status": "offline",
        "reason": "no neural checkpoints — run train-top100 or paper-sim with trades",
        "replay_rows": replay,
        "models_loaded": models,
        "ensemble_p_up": None,
    }


def _report_meta() -> dict[str, Any]:
    from analytics.paper_report import latest_valid_report, report_age_hours_from_doc

    path, doc = latest_valid_report(min_rows=1)
    if not doc or not path:
        return {"ok": False}
    age_h = report_age_hours_from_doc(doc, path)
    rows = doc.get("rows") or []
    sig_dates = [str(r.get("signal_date") or "")[:10] for r in rows if r.get("signal_date")]
    newest_sig = max(sig_dates) if sig_dates else ""
    return {
        "ok": True,
        "path": str(path),
        "generated_at_utc": str(doc.get("generated_at_utc", ""))[:19],
        "age_hours": round(age_h, 1),
        "symbols_scored": len(rows),
        "newest_signal_date": newest_sig,
        "stale": age_h > float(os.getenv("HORIZON_MATRIX_MAX_AGE_HOURS", "24")),
        "doc": doc,
    }


def _backtest_row(row: dict) -> dict[str, Any]:
    """Did historical fwd returns match bullish model calls on this row?"""
    out: dict[str, Any] = {}
    for label, _days, prefix, fwd_key in HORIZONS:
        p = _resolve_p(row, prefix, hold_days=_days)
        fwd = row.get(fwd_key)
        if p is None or fwd is None:
            continue
        try:
            ret = float(fwd)
            pred_up = float(p) >= 0.5
            actual_up = ret > 0
            out[label] = {
                "p_up": round(float(p), 4),
                "fwd_return": round(ret, 4),
                "correct": pred_up == actual_up,
            }
        except (TypeError, ValueError):
            continue
    return out


def _build_entry(
    row: dict,
    *,
    neural_weight: float,
    require_neural: bool,
    live_neural: bool,
) -> dict | None:
    sym = str(row.get("ticker") or "").upper()
    if not sym:
        return None

    neural_report = row.get("neural_p_up")
    neural_live = None
    nstat: dict[str, Any] = {"status": "snapshot"}
    if live_neural:
        nstat = _neural_status(sym, row)
        neural_live = nstat.get("ensemble_p_up")

    neural = neural_live if neural_live is not None else neural_report
    trade_ready = nstat.get("status") == "ready" or (
        neural is not None and nstat.get("status") in ("snapshot", "ready")
    )
    if require_neural and neural is None:
        return None

    entry: dict[str, Any] = {
        "ticker": sym,
        "signal_date": row.get("signal_date"),
        "sig_close": row.get("sig_close"),
        "neural_p_up": neural,
        "neural_status": nstat.get("status"),
        "neural_reason": nstat.get("reason", ""),
        "trade_ready": trade_ready,
        "disclaimer": "Model probability — not a guarantee. Opposite outcome often still likely.",
    }

    for label, days, prefix, _fwd in HORIZONS:
        raw = _resolve_p(row, prefix, hold_days=days)
        blended = _neural_blend(raw, neural, weight=neural_weight if neural is not None else 0.0)
        entry[f"{label}_raw"] = raw
        entry[f"{label}_raw_pct"] = _pct_label(raw, raw=True) if raw is not None else None
        entry[f"{label}_pct"] = _pct_label(blended)
        entry[f"{label}_p"] = blended

    entry["neural_pct"] = _pct_label(neural)
    entry["backtest"] = _backtest_row(row)
    return entry


def _rows_from_report(
    *,
    min_p: float,
    limit: int,
    neural_weight: float,
    require_neural: bool,
    live_neural: bool,
) -> tuple[list[dict], dict]:
    meta = _report_meta()
    if not meta.get("ok"):
        return [], meta

    doc = meta["doc"]
    out: list[dict] = []
    for row in doc.get("rows") or []:
        entry = _build_entry(
            row,
            neural_weight=neural_weight,
            require_neural=require_neural,
            live_neural=live_neural,
        )
        if not entry:
            continue
        best_p = max(float(entry.get(f"{h[0]}_p") or 0) for h in HORIZONS)
        if best_p >= min_p or min_p <= 0.5:
            out.append(entry)

    out.sort(
        key=lambda r: (
            0 if r.get("trade_ready") else 1,
            -(float(r.get("5d_p") or 0) + float(r.get("neural_p_up") or 0)),
            r["ticker"],
        )
    )
    if limit > 0:
        out = out[:limit]
    return out, meta


def _print_table(rows: list[dict], *, meta: dict, neural_weight: float) -> None:
    print("=" * 72)
    print("  HORIZON MATRIX — model probabilities (NOT trading advice / NOT certainty)")
    print("=" * 72)
    if meta.get("ok"):
        stale = " ⚠ STALE" if meta.get("stale") else ""
        print(
            f"  Report: {Path(meta['path']).name}  age={meta['age_hours']}h{stale}  "
            f"signal_through={meta.get('newest_signal_date')}  n={meta.get('symbols_scored')}"
        )
    print(f"  Neural blend weight: {neural_weight:.0%} (skipped when neural offline)")
    print()

    cols = ["TICKER", "READY", "1d", "5d", "1mo", "3mo", "6mo", "1yr", "NEURAL"]
    widths = [8, 5, 7, 7, 7, 7, 7, 7, 8]
    print("  ".join(c.ljust(w) for c, w in zip(cols, widths)))
    print("-" * 72)
    for r in rows:
        ready = "YES" if r.get("trade_ready") else "NO*"
        print(
            "  ".join(
                [
                    str(r["ticker"])[:8].ljust(8),
                    ready.ljust(5),
                    str(r.get("1d_pct", "—")).ljust(7),
                    str(r.get("5d_pct", "—")).ljust(7),
                    str(r.get("1mo_pct", "—")).ljust(7),
                    str(r.get("3mo_pct", "—")).ljust(7),
                    str(r.get("6mo_pct", "—")).ljust(7),
                    str(r.get("1yr_pct", "—")).ljust(7),
                    str(r.get("neural_pct", "—")).ljust(8),
                ]
            )
        )
    print()
    print("  * READY=NO → neural offline; do NOT treat as validated trade signal.")
    print("  ↓55% on 3mo means ~55% model-estimated DOWN chance (~45% UP still possible).")
    print("  Refresh: ./run_all.sh paper-sim   Diagnose: ./run_all.sh horizon-matrix --diagnose GOOG")


def _diagnose(ticker: str) -> int:
    meta = _report_meta()
    if not meta.get("ok"):
        print("[diagnose] no paper_sim report")
        return 1
    sym = ticker.upper()
    row = next((r for r in meta["doc"].get("rows") or [] if str(r.get("ticker", "")).upper() == sym), None)
    if not row:
        print(f"[diagnose] {sym} not in latest report — run ./run_all.sh paper-sim")
        return 1

    entry = _build_entry(row, neural_weight=0.0, require_neural=False, live_neural=True)
    nstat = _neural_status(sym, row)
    print(json.dumps(
        {
            "ticker": sym,
            "report": {
                "path": meta.get("path"),
                "age_hours": meta.get("age_hours"),
                "signal_date": row.get("signal_date"),
                "sig_close": row.get("sig_close"),
            },
            "neural": nstat,
            "report_snapshot_neural_p_up": row.get("neural_p_up"),
            "horizons_raw": {h[0]: entry.get(f"{h[0]}_raw_pct") for h in HORIZONS},
            "backtest_on_report_row": entry.get("backtest") if entry else {},
            "trade_ready": entry.get("trade_ready") if entry else False,
            "fix_commands": [
                "./run_all.sh paper-sim",
                f"venv/bin/python -c \"from online_learning.neural_ensemble import train_neural_ensemble_for_ticker; print(train_neural_ensemble_for_ticker('{sym}'))\"",
            ],
        },
        indent=2,
    ))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Horizon probability matrix with neural validation gates")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--ticker", "-t")
    ap.add_argument("--diagnose", metavar="TICKER", help="Why neural is null / data stale for one symbol")
    ap.add_argument("--limit", type=int, default=int(os.getenv("HORIZON_MATRIX_LIMIT", "50")))
    ap.add_argument("--min-p", type=float, default=float(os.getenv("HORIZON_MATRIX_MIN_P", "0.52")))
    ap.add_argument("--neural-weight", type=float, default=float(os.getenv("HORIZON_MATRIX_NEURAL_WEIGHT", "0.45")))
    ap.add_argument("--require-neural", action="store_true", help="Hide rows where neural layer is offline")
    ap.add_argument("--live-neural", action="store_true", default=True, help="Re-check neural at runtime (default on)")
    ap.add_argument("--snapshot-only", action="store_true", help="Use report neural_p_up only (no live check)")
    args = ap.parse_args()

    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=True)
    except ImportError:
        pass

    if args.diagnose:
        return _diagnose(args.diagnose)

    rows, meta = _rows_from_report(
        min_p=args.min_p,
        limit=args.limit,
        neural_weight=args.neural_weight,
        require_neural=args.require_neural,
        live_neural=not args.snapshot_only,
    )
    if args.ticker:
        rows = [r for r in rows if r["ticker"] == args.ticker.upper()]

    if not rows:
        print("[horizon-matrix] No rows — run: ./run_all.sh paper-sim")
        return 1

    payload = {
        "disclaimer": "Probabilities from statistical models — not certainties. Does not include breaking news.",
        "report": {k: meta[k] for k in ("path", "age_hours", "generated_at_utc", "newest_signal_date", "stale") if meta.get(k) is not None},
        "neural_weight": args.neural_weight,
        "horizons": [h[0] for h in HORIZONS],
        "rows": rows,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    _print_table(rows, meta=meta, neural_weight=args.neural_weight)
    print(f"Showing {len(rows)} tickers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
