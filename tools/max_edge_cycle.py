#!/usr/bin/env python3
"""Max-edge overnight / pre-open cycle — training hygiene + media intel + self-checks.

Designed to run every ~20m for several hours without self-sabotage:
  - never wipe HFT / never null model heads
  - refresh podcasts/articles/captions into unified intel
  - keep ONE strong retrain path
  - verify overnight buy-block is NOT starving afternoon RTH
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LOG = ROOT / "logs" / "max_edge_cycle.log"


def _log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _pgrep(pat: str) -> list[int]:
    try:
        out = subprocess.check_output(["pgrep", "-f", pat], text=True)
        return [int(x) for x in out.split() if x.strip().isdigit()]
    except Exception:
        return []


def hygiene_trainers() -> dict:
    """Allow at most one heavy strong retrain; park duplicate parallel_train."""
    strong = _pgrep("retrain_top100_strong.py")
    parallel = _pgrep("parallel_train.py --pipeline daily")
    monthly = _pgrep("universe_monthly_maintenance.py")
    killed = []
    # Keep oldest strong; kill extras
    if len(strong) > 1:
        for pid in sorted(strong)[1:]:
            try:
                os.kill(pid, 9)
                killed.append(pid)
            except Exception:
                pass
    # Prefer strong over parallel when both fight for RAM
    if strong and parallel:
        for pid in parallel:
            try:
                os.kill(pid, 9)
                killed.append(pid)
            except Exception:
                pass
    # One monthly max
    if len(monthly) > 1:
        for pid in sorted(monthly)[1:]:
            try:
                os.kill(pid, 9)
                killed.append(pid)
            except Exception:
                pass
    return {"strong": strong[:1], "killed": killed, "monthly_n": min(1, len(monthly))}


def refresh_intel() -> dict:
    os.environ.setdefault("MEDIA_INTEL_ENABLED", "true")
    from intel.media_intel import refresh_media_intel

    syms = ["AAPL", "NVDA", "MSFT", "META", "AMZN", "GOOGL", "TSLA", "SPCX", "JNJ", "AMD"]
    try:
        from fortress_universe import load_top100_symbols

        syms = list(dict.fromkeys(syms + [s.upper() for s in load_top100_symbols()[:25]]))
    except Exception:
        pass
    report = refresh_media_intel(symbols=syms[:30])
    # Cramer post-market sync
    try:
        from intel.cramer_post_market import sync_post_market_cramer

        report["cramer_post"] = sync_post_market_cramer(force=False)
    except Exception as e:
        report["cramer_post"] = {"error": str(e)}
    return {"n_podcast": (report.get("podcast") or {}).get("n"), "syms": len(report.get("symbols") or {})}


def verify_gates() -> dict:
    from analytics.overnight_risk import (
        block_new_buys_for_overnight,
        in_overnight_buy_block_window,
        in_preclose_window,
    )

    block, reason = block_new_buys_for_overnight()
    return {
        "buy_block": block,
        "reason": reason,
        "in_buy_block_window": in_overnight_buy_block_window(),
        "in_trim_window": in_preclose_window(),
    }


def verify_models() -> dict:
    from tools.audit_blank_heads import main as _  # noqa: F401
    import importlib

    # lightweight count
    from fortress_universe import load_top100_symbols
    import joblib

    miss = []
    blank = []
    for s in load_top100_symbols():
        p = ROOT / "models" / f"{s}_model.pkl"
        if not p.is_file():
            miss.append(s)
            continue
        try:
            b = joblib.load(p)
            for k in ("model_short", "model_long", "model_daily", "model_xlong", "model_meta"):
                if b.get(k) is None:
                    blank.append(f"{s}:{k}")
        except Exception:
            miss.append(s)
    return {"missing": miss, "blank_slots": blank[:20], "n_blank_slots": len(blank)}


def smoke_unified(sym: str = "AAPL") -> dict:
    from intel.unified_intel import unified_intel_for

    u = unified_intel_for(sym, force_refresh=True)
    return {
        "symbol": sym,
        "boost": u.get("boost"),
        "sources": u.get("sources"),
        "media_boost": u.get("media_boost"),
        "block_long": u.get("block_long"),
    }


def ensure_live() -> dict:
    out = {
        "fortress": bool(_pgrep("fortress_live.py")),
        "hft": bool(_pgrep("obi-tape/index")),
        "day_trade": bool(_pgrep("day_trade_daemon")),
        "strong": bool(_pgrep("retrain_top100_strong")),
        "spcx_loop": bool(_pgrep("train_spcx_online")),
    }
    if not out["fortress"]:
        subprocess.Popen(
            [
                str(ROOT / "venv" / "bin" / "python"),
                str(ROOT / "tools" / "spawn_daemon.py"),
                str(ROOT / "logs" / "intraday_latest.log"),
                "bash",
                str(ROOT / "tools" / "daemon_loop.sh"),
                "30",
                str(ROOT / "venv" / "bin" / "python"),
                "-u",
                "fortress_live.py",
            ],
            cwd=str(ROOT),
        )
        out["fortress_spawned"] = True
    return out


def main() -> int:
    os.chdir(ROOT)
    report = {
        "ts": time.time(),
        "hygiene": hygiene_trainers(),
        "live": ensure_live(),
        "gates": verify_gates(),
        "intel": {},
        "models": {},
        "unified": {},
    }
    try:
        report["intel"] = refresh_intel()
    except Exception as e:
        report["intel"] = {"error": str(e)}
    try:
        report["models"] = verify_models()
    except Exception as e:
        report["models"] = {"error": str(e)}
    try:
        report["unified"] = smoke_unified("NVDA")
    except Exception as e:
        report["unified"] = {"error": str(e)}

    # If blank slots appear, kick fill (lean)
    blanks = (report.get("models") or {}).get("n_blank_slots") or 0
    if blanks > 0 and not _pgrep("fill_null_horizon_heads"):
        env = os.environ.copy()
        env.update(
            {
                "FILL_NULL_HEADS": "true",
                "KEEP_WEAK_HEADS": "true",
                "STRONG_N_EST": "120",
                "OMP_NUM_THREADS": "1",
            }
        )
        subprocess.Popen(
            [
                str(ROOT / "venv" / "bin" / "python"),
                str(ROOT / "tools" / "spawn_daemon.py"),
                str(ROOT / "logs" / "fill_null_heads_latest.log"),
                str(ROOT / "venv" / "bin" / "python"),
                "-u",
                "tools/fill_null_horizon_heads.py",
                "--top100-only",
                "--min-top20",
                "0.30",
                "--min-meta",
                "0.40",
            ],
            cwd=str(ROOT),
            env=env,
        )
        report["fill_spawned"] = True

    out = ROOT / "data" / "max_edge_last.json"
    out.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    _log(json.dumps({k: report[k] for k in ("hygiene", "live", "gates", "intel", "unified")}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
