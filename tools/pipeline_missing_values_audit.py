#!/usr/bin/env python3
"""Extensive missing-value audit across trading / train / talk pipelines."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def _ok(v) -> bool:
    if v is None:
        return False
    if isinstance(v, float) and v != v:  # NaN
        return False
    if isinstance(v, str) and not v.strip():
        return False
    if isinstance(v, (list, dict)) and len(v) == 0:
        return False
    return True


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=True)
    load_dotenv(ROOT / "data" / "deploy_scale.env", override=True)

    findings: list[dict] = []
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str, *, severity: str = "warn"):
        row = {"name": name, "ok": ok, "detail": detail, "severity": severity if not ok else "info"}
        checks.append(row)
        if not ok:
            findings.append(row)

    # --- env / deploy_scale critical keys ---
    crit_env = [
        "ALPACA_API_KEY",
        "ALPACA_SECRET_KEY",
        "FINNHUB_API_KEY",
        "MATH_P_UP_FLOOR",
        "USE_DOWNWARD_PRESSURE_GATE",
        "FORTRESS_ALLOW_OVERNIGHT",
        "USE_MONTHLY_DRAWDOWN_HALT",
        "MICRO_SCALP_ENABLED",
        "TALK_ALLOW_EDITS",
        "NETWORK_FIRST",
        "DAY_TRADE_MODE",
        "FORTRESS_STOP_LOSS_PCT",
        "BUY_THRESHOLD",
    ]
    for k in crit_env:
        v = os.getenv(k)
        if "KEY" in k or "SECRET" in k or "TOKEN" in k:
            shown = "set" if _ok(v) else "missing"
            check(f"env.{k}", _ok(v), f"value={shown}", severity="crit")
        else:
            check(f"env.{k}", _ok(v), f"value={v!r}"[:120], severity="warn")

    check("talk.edits_locked", os.getenv("TALK_ALLOW_EDITS", "false").lower() in ("0", "false", ""), f"TALK_ALLOW_EDITS={os.getenv('TALK_ALLOW_EDITS')}")

    # --- risk / policy JSON ---
    for path in [
        "data/risk/monthly_equity.json",
        "data/deploy_scale.env",
        "data/policy/runtime_policy_overrides.json",
        "data/intel/earnings_radar.json",
        "data/intel/earnings_time_overrides.json",
        "data/intel/unique_playbook.json",
        "data/algo_risk_config.json",
    ]:
        p = ROOT / path
        check(f"file.{path}", p.is_file() and p.stat().st_size > 0, f"exists={p.is_file()} size={p.stat().st_size if p.is_file() else 0}", severity="crit")

    me = {}
    try:
        me = json.loads((ROOT / "data/risk/monthly_equity.json").read_text())
        check("risk.peak_equity", _ok(me.get("peak_equity")), f"peak={me.get('peak_equity')} start={me.get('start_equity')}")
        check("risk.month_key", _ok(me.get("month_key")), f"month_key={me.get('month_key')}")
    except Exception as e:
        check("risk.monthly_equity_parse", False, str(e), severity="crit")

    # --- earnings calendar ---
    cal_path = ROOT / "data/intel/earnings_calendar.json"
    if cal_path.is_file():
        cal = json.loads(cal_path.read_text())
        sbux = cal.get("sbux") or (cal.get("symbols") or {}).get("SBUX") or {}
        check("earnings.calendar_exists", True, f"with_date={cal.get('with_next_date')} with_hour={cal.get('with_session_hour')}")
        check("earnings.sbux_date", _ok(sbux.get("next_earnings_date") or sbux.get("date")), f"date={sbux.get('next_earnings_date') or sbux.get('date')}", severity="crit")
        check(
            "earnings.sbux_call_1315_pt",
            str(sbux.get("call_time_pt") or "") in ("13:15", "1:15", "13:15:00"),
            f"call_pt={sbux.get('call_time_pt')} hour={sbux.get('hour')} et={sbux.get('call_time_et')}",
            severity="crit",
        )
        # sample other names not null
        samples_ok = 0
        samples_null = []
        for s in ("AAPL", "MSFT", "META", "AMZN", "NVDA"):
            row = (cal.get("symbols") or {}).get(s) or {}
            if row.get("next_earnings_date"):
                samples_ok += 1
                if not row.get("hour") and not row.get("next_datetime_et"):
                    samples_null.append(s)
            else:
                samples_null.append(s + ":no_date")
        check("earnings.sample_dates", samples_ok >= 3, f"ok={samples_ok} issues={samples_null[:8]}")
    else:
        check("earnings.calendar_exists", False, "missing data/intel/earnings_calendar.json", severity="crit")

    # --- model paths ---
    models = ROOT / "models"
    n_daily = len(list(models.glob("*_model.pkl"))) if models.is_dir() else 0
    n_lstm = len(list((models / "lstm").glob("*.pt"))) if (models / "lstm").is_dir() else len(list(models.glob("*lstm*")))
    check("models.daily_pkl", n_daily > 0, f"n_daily={n_daily}", severity="crit")
    check("models.dir", models.is_dir(), f"du_hint={n_daily} pkl")

    # --- train checkpoints ---
    for ck in ("data/train_checkpoint.json", "data/intraday_train_checkpoint.json", "data/lstm_train_checkpoint.json", "data/enhancement_queue_state.json"):
        p = ROOT / ck
        if not p.is_file():
            check(f"train.{ck}", False, "missing", severity="warn")
            continue
        try:
            doc = json.loads(p.read_text())
            check(f"train.{ck}", True, f"keys={list(doc.keys())[:8]}")
        except Exception as e:
            check(f"train.{ck}", False, str(e), severity="warn")

    # --- talk harness ---
    eg = ROOT / "data/talk_brain/edit_gate_status.json"
    if eg.is_file():
        doc = json.loads(eg.read_text())
        check("talk.problems_done", _ok(doc.get("problems_done")), f"done={doc.get('problems_done')} pct={doc.get('pct_of_1b')}")
        check("talk.edits_still_locked", not bool(doc.get("edits_allowed")), f"edits_allowed={doc.get('edits_allowed')}")
    else:
        check("talk.edit_gate", False, "missing", severity="warn")

    # --- live alpaca ---
    try:
        import alpaca_broker as ab

        ab._ACCT_CACHE = None
        acct = ab.get_account() or {}
        check("alpaca.equity", _ok(acct.get("equity")), f"equity={acct.get('equity')}", severity="crit")
        check("alpaca.status", str(acct.get("status") or "").upper() == "ACTIVE", f"status={acct.get('status')}")
    except Exception as e:
        check("alpaca.account", False, str(e)[:160], severity="crit")

    # --- process heartbeats (pid files / pgrep) ---
    import subprocess

    procs = {
        "fortress/intraday": r"fortress_live\.py",
        "hft_obi": r"dist/obi-tape/index.js",
        "day_trade": r"day_trade_daemon\.py",
        "weekly": r"paper_sim_today",
        "stack_watchdog": r"stack_watchdog\.py",
        "paper_awake": r"caffeinate",
        "talk_overnight": r"overnight_talk_trillion",
        "pattern": r"hidden_pattern_scan\.py",
        "universe_lifecycle": r"universe_lifecycle_watch\.py",
        "cramer": r"cramer_cnbc_poll\.py",
    }
    for name, pat in procs.items():
        r = subprocess.run(["pgrep", "-f", pat], capture_output=True, text=True)
        alive = r.returncode == 0 and bool(r.stdout.strip())
        # micro-scalp intentionally paused
        check(f"proc.{name}", alive, f"pgrep={r.stdout.strip().split()[:1]}", severity="warn")

    ms = os.getenv("MICRO_SCALP_ENABLED", "false").lower() in ("1", "true", "yes")
    check("micro_scalp.paused_intentionally", not ms, f"MICRO_SCALP_ENABLED={os.getenv('MICRO_SCALP_ENABLED')} (paused during bleed)")

    # --- Yahoo NaN smoke (one liquid name) ---
    try:
        from multi_source_data import fetch_yahoo
        import pandas as pd

        df = fetch_yahoo("SPY", "2026-06-01", "2026-07-29")
        if df is None or df.empty:
            check("yahoo.SPY", False, "empty frame", severity="warn")
        else:
            nan_close = int(df["Close"].isna().sum()) if "Close" in df.columns else -1
            check("yahoo.SPY_close_nan", nan_close == 0, f"rows={len(df)} nan_close={nan_close}", severity="warn")
    except Exception as e:
        check("yahoo.SPY", False, str(e)[:160], severity="warn")

    crit_fail = [f for f in findings if f.get("severity") == "crit"]
    warn_fail = [f for f in findings if f.get("severity") != "crit"]
    summary = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "n_checks": len(checks),
        "n_ok": sum(1 for c in checks if c["ok"]),
        "n_fail": len(findings),
        "n_crit_fail": len(crit_fail),
        "n_warn_fail": len(warn_fail),
        "green": len(crit_fail) == 0,
        "crit_failures": crit_fail,
        "warn_failures": warn_fail[:40],
        "checks": checks,
    }
    out = ROOT / "data/ops/pipeline_missing_values_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in ("ts", "n_checks", "n_ok", "n_fail", "n_crit_fail", "green", "crit_failures")}, indent=2))
    return 0 if summary["green"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
