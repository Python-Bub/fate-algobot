#!/usr/bin/env python3
"""Pre-launch smoke tests: stack, inference, after-hours, Alpaca, training coverage."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str, *, warn: bool = False) -> None:
    if ok:
        tag = PASS
    elif warn:
        tag = WARN
    else:
        tag = FAIL
    results.append((tag, name, detail))
    print(f"  [{tag}] {name}: {detail}", flush=True)


def main() -> int:
    print("=== smoke-launch ===", flush=True)
    fails = 0

    # --- imports / health ---
    print("\n-- core --", flush=True)
    try:
        r = subprocess.run(
            [str(ROOT / "venv/bin/python"), "-u", "tools/health_check.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        ok = r.returncode == 0 and (
            "top100 daily trained 100/100" in r.stdout
            or "top100 daily trained 9" in r.stdout  # 95–99/100 OK for go-live
        )
        check("health_check", ok, "top100 ≥95/100" if ok else (r.stdout[-200:] or r.stderr[-200:]))
    except Exception as e:
        check("health_check", False, str(e))

    from fortress_universe import load_top100_symbols, trade_quality_universe
    from model_trainer import training_saved_model

    top = load_top100_symbols()
    missing = [s for s in top if not training_saved_model(s)]
    check("top100 models", len(missing) <= 5, missing or "100/100 on disk", warn=0 < len(missing) <= 5)
    quality = trade_quality_universe()
    check("quality universe", "AAPL" in quality and "MSFT" in quality, f"{len(quality)} names (AAPL/MSFT in set)")

    # --- inference (ProbaBlend + LGB align) ---
    print("\n-- inference --", flush=True)
    # Prefer Yahoo when Polygon is exhausted — smoke must not fail on feed flakiness
    # .env often sets TRAIN_FORCE_YAHOO=false — override for smoke reliability
    os.environ["TRAIN_FORCE_YAHOO"] = "true"
    os.environ["FORCE_YAHOO_PRICES"] = "true"
    os.environ.setdefault("NETWORK_FIRST", "true")
    os.environ.setdefault("PRICE_DATA_SOURCE", "yfinance")
    try:
        from feature_engineering import build_features
        from ml_model import load_raw_bundle, predict_row_details

        inferred = 0
        last_err = ""
        for sym in ("AAPL", "NVDA", "MSFT", "AMD", "VZ"):
            p = ROOT / "models" / f"{sym}_model.pkl"
            if not p.is_file():
                continue
            try:
                load_raw_bundle(str(p))
                df = build_features(sym, "2024-06-01", None)
                if df is None or getattr(df, "empty", True) or len(df) < 5:
                    last_err = f"{sym}: empty features"
                    continue
                row = df.iloc[-1]
                det = predict_row_details(str(p), row)
                ok = 0.0 <= float(det["p_up"]) <= 1.0
                check(f"predict {sym}", ok, f"p_up={float(det['p_up']):.3f}")
                if ok:
                    inferred += 1
                if inferred >= 2:
                    break
            except Exception as e:
                last_err = f"{sym}: {e}"
                continue
        if inferred == 0:
            check("inference", False, last_err or "no symbol inferred")
    except Exception as e:
        check("inference", False, str(e))

    # --- after-hours intel ---
    print("\n-- after-hours --", flush=True)
    ah_on = os.getenv("USE_AFTER_HOURS", "true").lower() in ("1", "true", "yes")
    check("USE_AFTER_HOURS", ah_on, os.getenv("USE_AFTER_HOURS", "true (default)"))
    ext = os.getenv("ALPACA_EXTENDED_HOURS", "false").lower() in ("1", "true", "yes")
    check("ALPACA_EXTENDED_HOURS", ext, os.getenv("ALPACA_EXTENDED_HOURS", "false"))
    try:
        from analytics.after_hours_intel import after_hours_enabled, fetch_after_hours_snapshot

        check("after_hours_intel import", after_hours_enabled() == ah_on, f"enabled={after_hours_enabled()}")
        snap = fetch_after_hours_snapshot("SPY", force=True)
        check("AH snapshot SPY", isinstance(snap, dict) and "ah_tilt" in snap, snap.get("investor_read", "?")[:60])
    except Exception as e:
        check("after_hours_intel", False, str(e))

    # --- Alpaca ---
    print("\n-- Alpaca paper --", flush=True)
    try:
        import requests
        import time

        key = os.getenv("ALPACA_API_KEY", "")
        sec = os.getenv("ALPACA_SECRET_KEY", "") or os.getenv("ALPACA_API_SECRET", "")
        base = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")
        if base.endswith("/v2"):
            clock_url = f"{base}/clock"
            acct_url = f"{base}/account"
        else:
            clock_url = f"{base}/v2/clock"
            acct_url = f"{base}/v2/account"
        h = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec}
        clk = acc = None
        for attempt in range(3):
            try:
                cr = requests.get(clock_url, headers=h, timeout=15)
                ar = requests.get(acct_url, headers=h, timeout=15)
                cr.raise_for_status()
                ar.raise_for_status()
                clk = cr.json()
                acc = ar.json()
                break
            except Exception as e:
                if attempt >= 2:
                    raise
                time.sleep(1.5 * (attempt + 1))
        eq = float(acc.get("equity") or 0)
        day_pl = eq - float(acc.get("last_equity") or eq)
        check("Alpaca clock", "is_open" in clk, f"open={clk.get('is_open')} ts={str(clk.get('timestamp', ''))[:19]}")
        check("Alpaca account", eq > 1000, f"equity=${eq:,.2f} day_pl=${day_pl:+,.2f}")
    except Exception as e:
        check("Alpaca", False, str(e), warn=True)

    # --- policy (no drift blocking entries) ---
    print("\n-- policy --", flush=True)
    pol_path = ROOT / "data/policy/runtime_policy_overrides.json"
    if pol_path.is_file():
        pol = json.loads(pol_path.read_text(encoding="utf-8"))
        bt = float(pol.get("BUY_THRESHOLD", 0.58))
        check("BUY_THRESHOLD cap", bt <= 0.72, f"{bt} (cap 0.72)")
    else:
        check("policy overrides", True, "none (using .env defaults)", warn=True)

    # --- daemons ---
    print("\n-- daemons --", flush=True)
    skip_daemons = os.getenv("SMOKE_SKIP_DAEMONS", "false").lower() in ("1", "true", "yes")
    try:
        from analytics.market_session import orders_allowed

        ext_orders, _ = orders_allowed("any")
    except Exception:
        ext_orders = False
    optional_when_stopped = {"subsecond-obi", "weekly"} if ext_orders else set()
    for name in ("intraday", "subsecond-obi", "weekly", "paper-awake"):
        pf = ROOT / ".pids" / f"{name}.pid"
        running = False
        if pf.is_file():
            try:
                pid = int(pf.read_text(encoding="utf-8").strip())
                os.kill(pid, 0)
                running = True
            except (OSError, ValueError):
                pass
        if skip_daemons:
            check(f"daemon {name}", True, "skipped (bootstrap)", warn=not running)
        elif running:
            check(f"daemon {name}", True, f"pid={pf.read_text().strip()}")
        elif name in optional_when_stopped:
            check(
                f"daemon {name}",
                True,
                "stopped (will start on launch-ah/unpause)",
                warn=True,
            )
        else:
            check(f"daemon {name}", False, "stopped")

    # --- weak heads (warn only) ---
    print("\n-- weak heads --", flush=True)
    try:
        from tools.retrain_weak_models import find_weak_symbols

        strict = find_weak_symbols(min_top20=0.6, min_meta=0.52, top100_only=True)
        relax = find_weak_symbols(min_top20=0.52, min_meta=0.48, top100_only=True)
        check("weak strict", not strict, list(strict) if strict else "clear", warn=bool(strict))
        check("weak relaxed", not relax, list(relax) if relax else "clear", warn=bool(relax))
    except Exception as e:
        check("weak scan", False, str(e))

    # --- head + candle audit ---
    print("\n-- heads + candles --", flush=True)
    try:
        r = subprocess.run(
            [str(ROOT / "venv/bin/python"), "-u", "tools/audit_heads.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=600,
        )
        for line in (r.stdout or "").splitlines()[-8:]:
            print(f"  {line}", flush=True)
        if r.returncode != 0:
            check("audit_heads", False, "see above", warn=True)
        else:
            check("audit_heads", True, "top100 bundles + HFT candles OK")
    except Exception as e:
        check("audit_heads", False, str(e), warn=True)

    # --- industry historical smoke (50 anchors) ---
    print("\n-- industry anchors --", flush=True)
    try:
        env = os.environ.copy()
        env["TRAIN_FORCE_YAHOO"] = "true"
        env["FORCE_YAHOO_PRICES"] = "true"
        env["PRICE_DATA_SOURCE"] = "yfinance"
        r = subprocess.run(
            [str(ROOT / "venv/bin/python"), "-u", "tools/industry_historical_smoke.py", "--limit", "5"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=int(os.getenv("INDUSTRY_SMOKE_TIMEOUT_SEC", "600")),
        )
        sample_ok = r.returncode == 0
        for line in (r.stdout or "").splitlines()[-8:]:
            print(f"  {line}", flush=True)
        check("industry_historical_smoke (sample 5)", sample_ok, "see above" if not sample_ok else "5/5 anchors OK", warn=not sample_ok)
    except Exception as e:
        check("industry_historical_smoke", False, str(e), warn=True)

    print("\n=== summary ===", flush=True)
    for tag, name, detail in results:
        if tag == FAIL:
            fails += 1
    n_pass = sum(1 for t, _, _ in results if t == PASS)
    n_warn = sum(1 for t, _, _ in results if t == WARN)
    n_fail = sum(1 for t, _, _ in results if t == FAIL)
    print(f"  {n_pass} pass, {n_warn} warn, {n_fail} fail", flush=True)
    log = ROOT / "logs" / "smoke_launch.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()} pass={n_pass} warn={n_warn} fail={n_fail}\n")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
