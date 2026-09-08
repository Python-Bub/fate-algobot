#!/usr/bin/env python3
"""Triple-check that earning stack daemons + strategy modules are online/connected.

Exit 0 only if all critical checks pass. Used by: ./run_all.sh online
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
PIDDIR = ROOT / ".pids"
REPORT = ROOT / "data" / "online_verify.json"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _pgrep(pattern: str) -> list[int]:
    try:
        r = subprocess.run(
            ["pgrep", "-f", pattern],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode != 0:
            return []
        return [int(x) for x in r.stdout.split() if x.strip().isdigit()]
    except Exception:
        return []


def _daemon_ok(name: str, patterns: list[str]) -> tuple[bool, str]:
    pf = PIDDIR / f"{name}.pid"
    if pf.is_file():
        try:
            pid = int(pf.read_text().strip())
            if _pid_alive(pid):
                return True, f"pid={pid}"
        except (ValueError, OSError):
            pass
    for pat in patterns:
        pids = _pgrep(pat)
        if pids:
            # heal pid file
            try:
                pf.write_text(str(pids[0]) + "\n", encoding="utf-8")
            except OSError:
                pass
            return True, f"pgrep={pids[0]}"
    return False, "missing"


CRITICAL = [
    ("stack-watchdog", [r"tools/stack_watchdog\.py"]),
    ("intraday", [r"fortress_live\.py"]),
    ("weekly", [r"daemon_loop\.sh 3600.*paper_sim_today", r"HOLD_DAYS_DEFAULT=5.*paper_sim_today"]),
    ("subsecond-obi", [r"dist/obi-tape/index\.js"]),
    ("hft-rotator", [r"hft_earnings_rotator\.sh"]),
    ("day-trade", [r"day_trade_daemon\.py"]),
    ("paper-awake", [r"caffeinate"]),
    ("paper-hygiene", [r"paper_portfolio_hygiene\.py"]),
    ("execution-monitor", [r"monitor_execution\.py"]),
    ("stack-autotune", [r"tools/stack_autotune\.py"]),
    ("self-improve", [r"tools/self_improve_loop\.py"]),
    ("cortex-singularity", [r"cortex_singularity_loop\.py"]),
    ("free-agent", [r"free_agent_loop\.py"]),
    ("bottom-fisher-watch", [r"bottom_fisher_watch\.py"]),
    ("industry-ai-watch", [r"industry_ai_watch\.py"]),
    ("universe-lifecycle-watch", [r"universe_lifecycle_watch\.py"]),
    ("disk-cleanup", [r"change_cleaner\.py.*disk_cleanup", r"disk_cleanup"]),
]

# Softer — warn only (training gap-fill may be idle when complete)
OPTIONAL = [
    ("longterm", [r"daemon_loop\.sh 7200.*paper_sim_today", r"HOLD_DAYS_DEFAULT=20.*paper_sim_today"]),
    ("hft-news-watch", [r"hft_news_watch\.py"]),
    ("retrain-weak-loop", [r"retrain_weak_models|finish_weak_top100"]),
    ("gainz-v2", [r"gainz_v2_daemon\.py"]),
    ("gainz-escape-watch", [r"gainz_escape_watch\.py"]),
]

STRATEGY_MODULES = [
    "analytics.strategy_registry",
    "analytics.rank_pipeline",
    "analytics.structure_patterns",
    "analytics.sequence_discover",
    "analytics.hidden_pattern_anomaly",
    "analytics.gainz_v2",
    "analytics.market_imbalance",
    "analytics.value_investing",
    "investing.catalog",
    "investing.integrate",
    "bottom_fisher.integrate",
]


def _import_ok(mod: str) -> tuple[bool, str]:
    try:
        importlib.import_module(mod)
        return True, "ok"
    except Exception as e:
        return False, str(e)[:120]


def run_once(pass_n: int) -> dict:
    daemons: dict[str, dict] = {}
    fails: list[str] = []
    warns: list[str] = []

    for name, pats in CRITICAL:
        ok, detail = _daemon_ok(name, pats)
        daemons[name] = {"ok": ok, "detail": detail, "tier": "critical"}
        if not ok:
            fails.append(name)

    for name, pats in OPTIONAL:
        ok, detail = _daemon_ok(name, pats)
        daemons[name] = {"ok": ok, "detail": detail, "tier": "optional"}
        if not ok:
            warns.append(name)

    modules: dict[str, dict] = {}
    for mod in STRATEGY_MODULES:
        ok, detail = _import_ok(mod)
        modules[mod] = {"ok": ok, "detail": detail}
        if not ok:
            fails.append(f"import:{mod}")

    # Strategy catalog connectivity (env-gated families present)
    try:
        from analytics.strategy_registry import STRATEGY_CATALOG

        catalog_ids = [f.id for f in STRATEGY_CATALOG]
        modules["strategy_catalog"] = {"ok": True, "detail": f"n={len(catalog_ids)}"}
    except Exception as e:
        modules["strategy_catalog"] = {"ok": False, "detail": str(e)[:120]}
        fails.append("strategy_catalog")

    paused = False
    try:
        st = json.loads((ROOT / "data" / "autopilot_state.json").read_text())
        paused = bool(st.get("paused"))
        if paused:
            fails.append("autopilot_paused")
    except Exception:
        pass

    return {
        "pass": pass_n,
        "ts": datetime.now(timezone.utc).isoformat(),
        "ok": len(fails) == 0,
        "fails": fails,
        "warns": warns,
        "daemons": daemons,
        "modules": modules,
        "paused": paused,
    }


def main() -> int:
    passes = int(os.getenv("ONLINE_VERIFY_PASSES", "3"))
    pause = float(os.getenv("ONLINE_VERIFY_SLEEP_SEC", "2"))
    results = []
    all_ok = True
    for i in range(1, passes + 1):
        r = run_once(i)
        results.append(r)
        tag = "PASS" if r["ok"] else "FAIL"
        print(f"[online-verify] pass {i}/{passes}: {tag}", flush=True)
        if r["fails"]:
            print(f"  fails: {', '.join(r['fails'])}", flush=True)
        if r["warns"]:
            print(f"  warns: {', '.join(r['warns'])}", flush=True)
        if not r["ok"]:
            all_ok = False
        if i < passes:
            time.sleep(pause)

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps({"all_ok": all_ok, "results": results}, indent=2),
        encoding="utf-8",
    )
    print(f"[online-verify] report → {REPORT}", flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
