#!/usr/bin/env python3
"""Scan repo for syntax errors, missing price data, and broken model pipelines."""

from __future__ import annotations

import argparse
import compileall
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=True)
except ImportError:
    pass

DEFAULT_SYMBOLS = ("GOOG", "GOOGL", "AAPL", "MSFT", "NVDA", "SPY")
SKIP_DIRS = re.compile(r"(^|/)(venv|\.git|__pycache__|hft/node_modules)(/|$)")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def scan_syntax(*, roots: tuple[str, ...] = ("tools", "analytics", "intel", "signals")) -> dict:
    errors: list[dict] = []
    for rel in roots:
        base = ROOT / rel
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if SKIP_DIRS.search(str(path.relative_to(ROOT))):
                continue
            try:
                src = path.read_text(encoding="utf-8")
                compile(src, str(path), "exec")
            except SyntaxError as e:
                errors.append(
                    {
                        "file": str(path.relative_to(ROOT)),
                        "line": e.lineno,
                        "msg": e.msg,
                    }
                )
    return {"ok": not errors, "errors": errors, "roots": list(roots)}


def scan_price_data(symbols: list[str], *, start: str = "2023-01-01") -> dict:
    from feature_engineering import build_features, load_price_data

    rows: list[dict] = []
    for sym in symbols:
        row: dict = {"symbol": sym}
        try:
            px = load_price_data(sym, start, None)
            row["price_rows"] = int(len(px))
            row["price_ok"] = len(px) >= 60
        except Exception as e:
            row["price_rows"] = 0
            row["price_ok"] = False
            row["price_error"] = str(e)[:200]
        try:
            df = build_features(sym, start, None)
            row["feature_rows"] = int(len(df))
            row["features_ok"] = len(df) >= 60 and "target" in df.columns
            if df.empty:
                row["feature_error"] = "empty_features"
        except Exception as e:
            row["feature_rows"] = 0
            row["features_ok"] = False
            row["feature_error"] = str(e)[:200]
        rows.append(row)
    ok_n = sum(1 for r in rows if r.get("price_ok") and r.get("features_ok"))
    return {"ok": ok_n == len(rows), "symbols_ok": ok_n, "symbols": len(rows), "rows": rows}


def scan_models(symbols: list[str]) -> dict:
    from ml_model import load_raw_bundle
    from symbol_aliases import resolve_model_ticker

    rows: list[dict] = []
    for sym in symbols:
        model_sym = resolve_model_ticker(sym)
        row: dict = {"symbol": sym, "model_ok": model_sym is not None}
        if model_sym and model_sym != sym:
            row["model_symbol"] = model_sym
        if not row["model_ok"]:
            row["error"] = "no_model"
            rows.append(row)
            continue
        path = ROOT / "models" / f"{model_sym}_model.pkl"
        try:
            bundle = load_raw_bundle(str(path))
            heads = {
                k.replace("model_", ""): bundle.get(k) is not None
                for k in ("model_daily", "model_short", "model_long", "model_xlong")
            }
            row["heads"] = heads
            row["model_ok"] = heads.get("short", False) and heads.get("long", False)
        except Exception as e:
            row["model_ok"] = False
            row["error"] = str(e)[:200]
        rows.append(row)
    ok_n = sum(1 for r in rows if r.get("model_ok"))
    return {"ok": ok_n == len(rows), "models_ok": ok_n, "symbols": len(rows), "rows": rows}


def scan_hft() -> dict:
    dist = ROOT / "hft" / "dist" / "obi-tape" / "index.js"
    earnings = ROOT / "hft" / "dist" / "earnings" / "index.js"
    pkg = ROOT / "hft" / "package.json"
    return {
        "ok": dist.is_file() and earnings.is_file(),
        "built": dist.is_file() and earnings.is_file(),
        "package": pkg.is_file(),
        "obi_tape": str(dist.relative_to(ROOT)) if dist.is_file() else None,
        "earnings": str(earnings.relative_to(ROOT)) if earnings.is_file() else None,
    }


def run_scan(*, symbols: list[str], start: str, json_out: str | None = None) -> dict:
    report = {
        "scanned_at_utc": _now(),
        "syntax": scan_syntax(),
        "price_data": scan_price_data(symbols, start=start),
        "models": scan_models(symbols),
        "hft": scan_hft(),
    }
    report["ok"] = all(report[k]["ok"] for k in ("syntax", "price_data", "models", "hft"))
    if json_out:
        out = Path(json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Repo data + syntax health scan")
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    ap.add_argument("--start", default=os.getenv("DATA_HEALTH_START", "2023-01-01"))
    ap.add_argument("--json-out", default=str(ROOT / "reports" / "data_health.json"))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    report = run_scan(symbols=syms, start=args.start, json_out=args.json_out)

    if not args.quiet:
        print("=== DATA HEALTH SCAN ===")
        print(f"  syntax:     {'OK' if report['syntax']['ok'] else 'FAIL'} ({len(report['syntax']['errors'])} errors)")
        print(
            f"  price/feats: {'OK' if report['price_data']['ok'] else 'PARTIAL'} "
            f"({report['price_data']['symbols_ok']}/{report['price_data']['symbols']})"
        )
        print(
            f"  models:     {'OK' if report['models']['ok'] else 'PARTIAL'} "
            f"({report['models']['models_ok']}/{report['models']['symbols']})"
        )
        print(f"  hft build:  {'OK' if report['hft']['ok'] else 'NOT BUILT'}")
        if report["syntax"]["errors"]:
            for err in report["syntax"]["errors"][:10]:
                print(f"    SYNTAX {err['file']}:{err['line']} — {err['msg']}")
        for row in report["price_data"]["rows"]:
            if not row.get("features_ok"):
                print(f"    DATA  {row['symbol']}: price={row.get('price_rows')} feat={row.get('feature_rows')} {row.get('feature_error','')}")
        for row in report["models"]["rows"]:
            if not row.get("model_ok"):
                print(f"    MODEL {row['symbol']}: {row.get('error') or row.get('heads')}")
        print(f"  report:     {args.json_out}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
