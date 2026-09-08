#!/usr/bin/env python3
"""One-shot go-live: tighten policy, final clean, smoke — ready for years of unattended paper trading."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "venv/bin/python"
POLICY = ROOT / "data/policy/runtime_policy_overrides.json"
AUTONOMOUS = ROOT / "data/autonomous_mode.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def apply_go_live_policy() -> dict:
    """Lock trade-friendly gates; cap policy agent from blocking entries."""
    doc = {
        "BUY_THRESHOLD": float(os.getenv("GO_LIVE_BUY_THRESHOLD", "0.58")),
        "ORDER_NOTIONAL": float(os.getenv("GO_LIVE_ORDER_NOTIONAL", os.getenv("ORDER_NOTIONAL", "4500"))),
        "MIN_MODEL_CONFIDENCE": float(os.getenv("GO_LIVE_MIN_MODEL_CONF", "0.58")),
        "note": "go_autonomous — trade-enabled; policy agent capped",
        "updated_at_utc": _now(),
        "autonomous": True,
    }
    POLICY.parent.mkdir(parents=True, exist_ok=True)
    POLICY.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    mode = {
        "enabled": True,
        "started_at_utc": _now(),
        "policy_cap": float(os.getenv("POLICY_BUY_THRESHOLD_CAP", "0.65")),
        "gates": {
            "BUY_THRESHOLD": doc["BUY_THRESHOLD"],
            "MIN_EXECUTION_CONFIDENCE": float(os.getenv("GO_LIVE_MIN_EXEC_CONF", "0.58")),
            "FORTRESS_MIN_CONF": doc["MIN_MODEL_CONFIDENCE"],
        },
    }
    AUTONOMOUS.write_text(json.dumps(mode, indent=2), encoding="utf-8")
    return doc


def _run(cmd: list[str], *, timeout: int | None = None) -> int:
    print(f"[go-autonomous] {' '.join(cmd[:5])}{'…' if len(cmd) > 5 else ''}", flush=True)
    try:
        return subprocess.run(cmd, cwd=ROOT, timeout=timeout, check=False).returncode
    except subprocess.TimeoutExpired:
        return 124


def _train_missing_top100(max_symbols: int = 8, *, background: bool = True) -> list[str]:
    from fortress_universe import load_top100_symbols
    from model_trainer import training_saved_model

    missing = [s for s in load_top100_symbols() if not training_saved_model(s)]
    batch = missing[:max_symbols]
    if not batch:
        return []
    if background:
        sym_file = ROOT / "data" / "go_live_top100_missing.json"
        sym_file.write_text(json.dumps(batch), encoding="utf-8")
        env = os.environ.copy()
        env["TRAIN_SYMBOLS_FILE"] = str(sym_file)
        env["FAST_UNIVERSE_TRAIN"] = "true"
        env["TRAIN_TICKER_TIMEOUT_SEC"] = os.getenv("GO_LIVE_TRAIN_TIMEOUT", "600")
        subprocess.Popen(
            [str(PY), "-u", "parallel_train.py", "--pipeline", "daily", "--workers", "2"],
            cwd=ROOT,
            env=env,
            stdout=open(ROOT / "logs/go_live_top100_train.log", "a"),
            stderr=subprocess.STDOUT,
        )
        print(f"[go-autonomous] background train queued: {batch}", flush=True)
        return batch
    from model_trainer import _train_single_ticker

    for sym in batch:
        print(f"[go-autonomous] training missing top100: {sym}", flush=True)
        try:
            _train_single_ticker(sym)
        except Exception as e:
            print(f"[go-autonomous] {sym} train error: {e}", flush=True)
    return [s for s in load_top100_symbols() if not training_saved_model(s)]


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    print("=== GO AUTONOMOUS — final tighten + clean + verify ===", flush=True)

    policy = apply_go_live_policy()
    print(f"[go-autonomous] policy BUY_THRESHOLD={policy['BUY_THRESHOLD']} notional={policy['ORDER_NOTIONAL']}", flush=True)

    _run([str(PY), "-u", "tools/sync_recent_trades.py"], timeout=120)
    _run([str(PY), "-u", "tools/repatch_paper_report_asym.py"], timeout=120)

    from tools.change_cleaner import run_builtin_cleaner

    run_builtin_cleaner(reason="go_autonomous_final")

    still = _train_missing_top100(max_symbols=int(os.getenv("GO_LIVE_TOP100_TRAIN_CAP", "8")), background=True)
    if still:
        print(f"[go-autonomous] top100 gap-fill running in background ({len(still)}): {still}", flush=True)

    fast = os.getenv("GO_AUTONOMOUS_FAST", "").lower() in ("1", "true", "yes")
    if fast:
        print("[go-autonomous] FAST mode — skip readiness/smoke (stack already verified)", flush=True)
        _run([str(PY), "-u", "tools/health_check.py"], timeout=90)
        print("\n[go-autonomous] READY (fast)", flush=True)
        return 0

    lr = _run([str(PY), "-u", "tools/launch_readiness.py"], timeout=240)
    if lr != 0 and os.getenv("GO_AUTONOMOUS_SKIP_READINESS", "").lower() not in ("1", "true", "yes"):
        print("[go-autonomous] launch-readiness failed — fix before trading", flush=True)
        return lr

    env = os.environ.copy()
    env["SMOKE_SKIP_DAEMONS"] = "true"
    env.setdefault("FAMILY_LIGHT_INDUSTRY", "true")
    env.setdefault("ENABLE_INSIDER_PROXY", "true")
    env.setdefault("USE_EARNINGS_DEFENSIVE", "true")
    env.setdefault("USE_LIQUIDITY_IMPACT", "true")
    rc = subprocess.run([str(PY), "-u", "tools/smoke_launch.py"], cwd=ROOT, env=env, check=False).returncode
    if rc != 0:
        if os.getenv("GO_AUTONOMOUS_SKIP_SMOKE", "").lower() in ("1", "true", "yes"):
            print(f"[go-autonomous] smoke exit={rc} (skipped — GO_AUTONOMOUS_SKIP_SMOKE)", flush=True)
        else:
            print("[go-autonomous] SMOKE FAILED — fix before trading", flush=True)
            return rc

    _run([str(PY), "-u", "tools/health_check.py"], timeout=120)

    print("\n[go-autonomous] READY — family picks:", flush=True)
    print("  ./run_all.sh family-forecast", flush=True)
    print("  ./run_all.sh family-forecast --json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
