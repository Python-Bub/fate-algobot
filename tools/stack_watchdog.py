#!/usr/bin/env python3
"""Always-on stack supervisor — restarts critical daemons unless autopilot is paused."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
AUTOPILOT_STATE = ROOT / "data" / "autopilot_state.json"
LOG_PATH = ROOT / "data" / "watchdog_log.jsonl"
PIDDIR = ROOT / ".pids"


def _log(action: str, detail: str, *, ok: bool = True) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "detail": detail,
        "ok": ok,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    tag = "OK" if ok else "WARN"
    print(f"[watchdog][{tag}] {action}: {detail}", flush=True)


def _thermal_cool() -> bool:
    """Mac too hot — keep fortress/HFT/day-trade, skip trainer relaunch until flag cleared."""
    if os.getenv("THERMAL_COOL", "").lower() in ("1", "true", "yes", "on"):
        return True
    p = ROOT / "data" / "ops" / "thermal_cool.json"
    if not p.is_file():
        return False
    try:
        return bool(json.loads(p.read_text(encoding="utf-8")).get("cool", False))
    except Exception:
        return False


def _paper_order_host() -> bool:
    """GCP paper box posts orders; heavy cooks belong on fate-algobot-trainer."""
    role = (os.getenv("FATE_ORDER_ROLE") or "").strip().lower()
    hn = (os.getenv("HOSTNAME") or socket.gethostname() or "").lower()
    return role in ("gcp-paper", "order", "paper-vm") or "algobot-paper" in hn


def _autopilot_paused() -> bool:
    # GCP paper must keep trading even if a Mac pause file was rsynced.
    if _paper_order_host():
        return False
    if not AUTOPILOT_STATE.is_file():
        return False
    try:
        return bool(json.loads(AUTOPILOT_STATE.read_text(encoding="utf-8")).get("paused", False))
    except Exception:
        return False


def _set_autopilot_state(**fields: object) -> None:
    st: dict = {}
    if AUTOPILOT_STATE.is_file():
        try:
            st = json.loads(AUTOPILOT_STATE.read_text(encoding="utf-8"))
        except Exception:
            st = {}
    st.update(fields)
    st["updated_at"] = datetime.now(timezone.utc).isoformat()
    AUTOPILOT_STATE.parent.mkdir(parents=True, exist_ok=True)
    AUTOPILOT_STATE.write_text(json.dumps(st, indent=2), encoding="utf-8")


def _maybe_auto_unpause() -> bool:
    """Unpause stack once per trading day (AUTO_UNPAUSE_ET, default 06:00 ET)."""
    if not _autopilot_paused():
        return False
    try:
        from analytics.market_session import auto_unpause_window_open, now_et

        ok, reason = auto_unpause_window_open()
        if not ok:
            return False
        today = now_et().date().isoformat()
        st = {}
        if AUTOPILOT_STATE.is_file():
            try:
                st = json.loads(AUTOPILOT_STATE.read_text(encoding="utf-8"))
            except Exception:
                st = {}
        if st.get("last_auto_unpause_date") == today:
            return False
        _log("auto_unpause", f"trading day {today} ({reason})")
        rc = _run(["./run_all.sh", "unpause"], timeout=240)
        if rc == 0:
            _set_autopilot_state(paused=False, last_auto_unpause_date=today)
            return True
        _log("auto_unpause_fail", f"exit={rc}", ok=False)
    except Exception as e:
        _log("auto_unpause_error", str(e), ok=False)
    return False


def _run_trading_day_autorun() -> None:
    if os.getenv("TRADING_DAY_AUTORUN", "true").lower() not in ("1", "true", "yes"):
        return
    try:
        from analytics.market_session import intel_window_open, is_trading_day, now_et

        today = now_et().date().isoformat()
        autorun_state = ROOT / "data" / "trading_day_autorun.json"
        st: dict = {}
        if autorun_state.is_file():
            try:
                st = json.loads(autorun_state.read_text(encoding="utf-8"))
            except Exception:
                st = {}
        if st.get("last_run_date") == today:
            return
        if not is_trading_day():
            return
        if not intel_window_open()[0]:
            return
        _log("trading_day_autorun", f"start {today}")
        py = os.getenv("PYTHON", str(ROOT / "venv/bin/python"))
        rc = _run([py, "-u", str(ROOT / "tools/trading_day_autorun.py")], timeout=7200)
        if rc != 0:
            _log("trading_day_autorun_fail", f"exit={rc}", ok=False)
    except Exception as e:
        _log("trading_day_autorun_error", str(e), ok=False)


def _maybe_ensure_paper_sim() -> None:
    """Background paper sim when report stale/unusable (works even if weekly daemon exists)."""
    if _paper_order_host():
        return
    if os.getenv("AUTO_PAPER_SIM", "true").lower() not in ("1", "true", "yes"):
        return
    if _autopilot_paused():
        return
    try:
        sys.path.insert(0, str(ROOT))
        from tools.ensure_paper_sim import ensure_paper_sim

        result = ensure_paper_sim()
        if result.get("started"):
            _log("ensure_paper_sim", str(result.get("reason", "started")))
    except Exception as e:
        _log("ensure_paper_sim_error", str(e), ok=False)


def _maybe_cramer_sync() -> None:
    """Autonomous Cramer email/article + post-market Mad Money fetch."""
    if os.getenv("CRAMER_AUTO_FETCH_ONLINE", "true").lower() not in ("1", "true", "yes"):
        return
    try:
        import time

        from analytics.market_session import intel_window_open, now_et

        ok, reason = intel_window_open()
        # Also run in post-market / Mad Money window (4pm–8:30pm ET weekdays)
        et = now_et()
        hhmm = et.hour * 60 + et.minute
        pm_start = int(os.getenv("CRAMER_PM_SYNC_START_MIN", str(16 * 60)))  # 16:00 ET
        pm_end = int(os.getenv("CRAMER_PM_SYNC_END_MIN", str(20 * 60 + 30)))  # 20:30 ET
        post_market_window = et.weekday() < 5 and pm_start <= hhmm <= pm_end
        if not ok and not post_market_window:
            return
        # Faster cadence after the close so Homestretch / Mad Money land quickly
        default_iv = "900" if post_market_window else "2700"
        interval = int(os.getenv("CRAMER_SYNC_INTERVAL_SEC", default_iv if post_market_window else "2700"))
        if post_market_window:
            interval = min(interval, int(os.getenv("CRAMER_PM_SYNC_INTERVAL_SEC", "900")))
        st: dict = {}
        if AUTOPILOT_STATE.is_file():
            try:
                st = json.loads(AUTOPILOT_STATE.read_text(encoding="utf-8"))
            except Exception:
                st = {}
        last = float(st.get("last_cramer_sync_ts") or 0)
        if time.time() - last < interval:
            return
        _log("cramer_sync", f"{reason if ok else 'post_market'} pm={post_market_window}")
        py = os.getenv("PYTHON", str(ROOT / "venv/bin/python"))
        rc = _run([py, "-u", str(ROOT / "tools/cramer_daily_sync.py")], timeout=90)
        if rc == 0:
            _set_autopilot_state(last_cramer_sync_ts=time.time())
            # Always refresh post-market scrape on PM window even if digest skipped
            if post_market_window or os.getenv("CRAMER_PM_ALWAYS", "true").lower() in ("1", "true", "yes"):
                _run([py, "-u", str(ROOT / "tools/cramer_post_market_once.py")], timeout=120)
        else:
            _log("cramer_sync_fail", f"exit={rc}", ok=False)
    except Exception as e:
        _log("cramer_sync_error", str(e), ok=False)


def _maybe_morning_prefetch() -> None:
    """Run 06:00 ET intel warmup once per trading day."""
    try:
        from analytics.market_session import intel_window_open, now_et

        ok, reason = intel_window_open()
        if not ok:
            return
        today = now_et().date().isoformat()
        st = {}
        if AUTOPILOT_STATE.is_file():
            try:
                st = json.loads(AUTOPILOT_STATE.read_text(encoding="utf-8"))
            except Exception:
                st = {}
        if st.get("last_morning_prefetch_date") == today:
            return
        if os.getenv("MORNING_INTEL_PREFETCH", "true").lower() not in ("1", "true", "yes"):
            return
        _log("morning_prefetch", f"trading day {today} ({reason})")
        py = os.getenv("PYTHON", str(ROOT / "venv/bin/python"))
        rc = _run([py, "-u", str(ROOT / "tools/morning_intel_prefetch.py")], timeout=300)
        if rc == 0:
            _set_autopilot_state(last_morning_prefetch_date=today)
        else:
            _log("morning_prefetch_fail", f"exit={rc}", ok=False)
    except Exception as e:
        _log("morning_prefetch_error", str(e), ok=False)


def _maybe_verify_trades() -> None:
    """Periodic full trade audit + auto-remediation (no manual ./run_all.sh verify-trades)."""
    if os.getenv("AUTO_VERIFY_TRADES", "true").lower() not in ("1", "true", "yes"):
        return
    if _autopilot_paused():
        return
    try:
        from analytics.market_session import orders_allowed

        interval = int(os.getenv("VERIFY_TRADES_INTERVAL_SEC", "180"))
        if not orders_allowed("any")[0]:
            interval = max(interval, int(os.getenv("VERIFY_TRADES_OFFHOURS_SEC", "600")))
    except Exception:
        interval = int(os.getenv("VERIFY_TRADES_INTERVAL_SEC", "180"))
    state_path = ROOT / "data" / "trade_verify_state.json"
    st: dict = {}
    if state_path.is_file():
        try:
            st = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            st = {}
    last = st.get("last_run_utc", "")
    if last:
        try:
            last_dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - last_dt).total_seconds() < interval:
                return
        except Exception:
            pass
    py = os.getenv("PYTHON", str(ROOT / "venv/bin/python"))
    _log("verify_trades", "start")
    rc = _run([py, "-u", str(ROOT / "tools/verify_trades.py"), "--quiet"], timeout=120)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "last_run_utc": datetime.now(timezone.utc).isoformat(),
                "exit_code": rc,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if rc != 0:
        _log("verify_trades_fail", f"exit={rc} — see data/last_trade_verification.json", ok=False)
    else:
        _log("verify_trades", "passed")


def _maybe_self_maintenance() -> None:
    if _paper_order_host():
        return
    if os.getenv("SELF_MAINTENANCE", "true").lower() not in ("1", "true", "yes"):
        return
    if _autopilot_paused():
        return
    try:
        py = os.getenv("PYTHON", str(ROOT / "venv/bin/python"))
        rc = _run([py, "-u", str(ROOT / "tools/self_maintenance.py")], timeout=900)
        if rc != 0:
            _log("self_maintenance_fail", f"exit={rc}", ok=False)
    except Exception as e:
        _log("self_maintenance_error", str(e), ok=False)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_pid(name: str) -> int | None:
    pf = PIDDIR / f"{name}.pid"
    if not pf.is_file():
        return None
    try:
        return int(pf.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def _pgrep(pattern: str) -> bool:
    try:
        r = subprocess.run(
            ["pgrep", "-f", pattern],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        return r.returncode == 0
    except Exception:
        return False


def _node_script_alive(script: str) -> bool:
    """True only if a Node process (not bash daemon_loop) has `script` in argv."""
    try:
        r = subprocess.run(
            ["ps", "-ax", "-o", "comm=,args="],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return False
    needle = script.lower()
    for line in r.stdout.splitlines():
        s = line.strip()
        if not s:
            continue
        comm = s.split(None, 1)[0].lower()
        if comm.startswith("node") and needle in s.lower():
            return True
    return False


def _daemon_alive(name: str) -> bool:
    if name == "subsecond-obi":
        return _node_script_alive("obi-tape/index.js")
    if name == "subsecond-earnings":
        return _node_script_alive("earnings/index.js")
    pid = _read_pid(name)
    if pid and _pid_alive(pid):
        return True
    # Process-pattern fallbacks (pid file can be stale or wrapper died).
    patterns = {
        "intraday": r"fortress_live\.py",
        "subsecond-obi": r"obi-tape/index\.js",
        "subsecond-earnings": r"earnings/index\.js",
        "stack-autotune": r"tools/stack_autotune\.py",
        "self-improve": r"tools/self_improve_loop\.py",
        "cortex-singularity": r"cortex_singularity_loop\.py",
        "stack-watchdog": r"tools/stack_watchdog\.py",
        "disk-cleanup": r"change_cleaner\.py.*disk_cleanup",
        "bottom-fisher-watch": r"bottom_fisher_watch\.py",
        "sheldon-hunt": r"sheldon_hunt\.py",
        "universe-lifecycle-watch": r"universe_lifecycle_watch\.py",
        "industry-ai-watch": r"industry_ai_watch\.py",
        "hft-rotator": r"hft_earnings_rotator\.sh",
        "paper-hygiene": r"paper_portfolio_hygiene\.py",
        "day-trade": r"day_trade_daemon\.py",
        "micro-scalp": r"micro_scalp_daemon\.py",
        "crypto-hft": r"crypto_hft_daemon\.py",
        "gainz-v2": r"gainz_v2_daemon\.py",
        "gainz-escape-watch": r"gainz_escape_watch\.py",
        "execution-monitor": r"monitor_execution\.py",
        "weekly": r"daemon_loop\.sh 3600.*paper_sim_today",
        "longterm": r"daemon_loop\.sh 7200.*paper_sim_today",
        "valuation-news-watch": r"valuation_news_watch\.py",
        "event-calendar-watch": r"event_calendar_watch\.py",
        "exec-delay": r"exec_delay",
        # Narrow patterns — avoid OR-globs that false-match unrelated lstm/train jobs.
        "train-lstm": r"tools/train_lstm|batch_train_lstm|train_lstm_meta",
        "retrain-weak-loop": r"retrain_weak_models\.py|finish_weak_top100|retrain_top100_strong",
        "paper-awake": r"fate.paper.awake|fate_paper_awake",
        "hft-news-watch": r"hft_news_watch\.py",
        "pattern-anomaly-watch": r"hidden_pattern_scan\.py",
        "cramer-cnbc-poll": r"cramer_cnbc_poll\.py",
        "free-agent": r"free_agent_loop\.py",
        "ule-watch": r"tools/ule_cycle\.py",
        "continuous-learn": r"tools/continuous_learn\.py",
        "algo-pipeline": r"tools/algo_pipeline\.py",
        "hist-cook": r"tools/hist_cook\.py",
        "event-learn-train": r"tools/event_learn_train\.py",
        "gen-learn-train": r"tools/gen_learn_train\.py",
    }
    pat = patterns.get(name)
    if pat and _pgrep(pat):
        return True
    return False


# Batch trainers exit when idle; don't thrash-restart them every poll (starves fortress ensures).
_TRAINER_COOLDOWN_SEC = {
    "train-lstm": int(os.getenv("WATCHDOG_TRAIN_LSTM_COOLDOWN_SEC", "600")),
    "retrain-weak-loop": int(os.getenv("WATCHDOG_RETRAIN_WEAK_COOLDOWN_SEC", "900")),
    "hist-cook": int(os.getenv("WATCHDOG_HIST_COOK_COOLDOWN_SEC", "1800")),
    "event-learn-train": int(os.getenv("WATCHDOG_EVENT_LEARN_COOLDOWN_SEC", "1800")),
    "gen-learn-train": int(os.getenv("WATCHDOG_GEN_LEARN_COOLDOWN_SEC", "1800")),
}
_LAST_TRAINER_START: dict[str, float] = {}


def _run(args: list[str], *, timeout: int = 120) -> int:
    try:
        return subprocess.run(
            args,
            cwd=ROOT,
            timeout=timeout,
            check=False,
        ).returncode
    except subprocess.TimeoutExpired:
        _log("run_timeout", " ".join(args[:4]), ok=False)
        return 124
    except Exception as e:
        _log("run_error", f"{args}: {e}", ok=False)
        return 1


def _ensure_industry_ai_watch() -> None:
    """Industry classification runs even when autopilot is paused (no trading impact)."""
    if _paper_order_host():
        return
    if os.getenv("USE_INDUSTRY_AI", "true").lower() not in ("1", "true", "yes"):
        return
    if os.getenv("AUTO_INDUSTRY_AI_WATCH", "true").lower() not in ("1", "true", "yes"):
        return
    if _daemon_alive("industry-ai-watch"):
        return
    _log("restart", "industry-ai-watch")
    rc = _run(["./run_all.sh", "industry-ai-watch"])
    if rc != 0:
        _log("restart_fail", f"industry-ai-watch exit={rc}", ok=False)


def _reload_env() -> None:
    """Pick up .env + deploy_scale.env without restarting the watchdog process."""
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=True)
        # deploy_scale wins for trading knobs (MICRO_SCALP, DAY_TRADE, fortress sizing)
        scale = ROOT / "data" / "deploy_scale.env"
        if scale.is_file():
            load_dotenv(scale, override=True)
    except ImportError:
        # Minimal fallback: export KEY=VAL lines
        for path in (ROOT / ".env", ROOT / "data" / "deploy_scale.env"):
            if not path.is_file():
                continue
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    s = line.strip()
                    if not s or s.startswith("#") or "=" not in s:
                        continue
                    k, _, v = s.partition("=")
                    k = k.strip()
                    if k:
                        os.environ[k] = v.strip().strip('"').strip("'")
            except OSError:
                pass


def _maybe_hft_news_refresh() -> None:
    if os.getenv("HFT_NEWS_GATE", "true").lower() not in ("1", "true", "yes"):
        return
    try:
        from analytics.market_session import intel_window_open

        if not intel_window_open()[0]:
            return
        py = str(ROOT / "venv" / "bin" / "python")
        rc = _run([py, "-u", str(ROOT / "tools/hft_news_refresh.py")], timeout=300)
        if rc != 0:
            _log("hft_news_refresh_fail", f"exit={rc}", ok=False)
    except Exception as e:
        _log("hft_news_refresh_error", str(e), ok=False)


def _maybe_kill_hung_fortress() -> None:
    """Kill fortress_live if heartbeat/log stalls (prevents flat-cash freezes).

    Prefer data/fortress_heartbeat.txt (touched every symbol) over log mtime —
    log-only idle kills were thrashing healthy long scans (false 'random stops').
    """
    if os.getenv("FORTRESS_HANG_WATCH", "true").lower() not in ("1", "true", "yes"):
        return
    idle_sec = int(os.getenv("FORTRESS_HANG_IDLE_SEC", "2400"))
    hb = ROOT / "data" / "fortress_heartbeat.txt"
    log = ROOT / "logs" / "intraday_latest.log"
    age = None
    for path in (hb, log):
        if not path.is_file():
            continue
        try:
            a = time.time() - path.stat().st_mtime
        except OSError:
            continue
        age = a if age is None else min(age, a)
    if age is None or age < idle_sec:
        return
    if not _daemon_alive("intraday"):
        return
    # Only act if a fortress python is actually present (pid may be the bash wrapper).
    if not _pgrep(r"fortress_live\.py"):
        return
    _log("hang_kill", f"fortress heartbeat/log idle {int(age)}s >= {idle_sec}s — restarting intraday")
    _run(["pkill", "-f", "fortress_live.py"], timeout=20)
    time.sleep(2)
    rc = _run(["./run_all.sh", "ensure-intraday"], timeout=90)
    if rc != 0:
        _log("hang_kill_fail", f"ensure-intraday exit={rc}", ok=False)


def ensure_stack(*, bootstrap: bool = False) -> None:
    _reload_env()
    try:
        from analytics.buying_power import refresh_and_persist

        refresh_and_persist()
    except Exception:
        pass
    _maybe_auto_unpause()
    # Trading engines FIRST — never block restarts behind Cramer/autorun (was 5–120min stalls
    # that looked like "random STOPPED" while watchdog was "RUNNING").
    if _autopilot_paused():
        _log("skip", "autopilot paused")
        # Still allow industry AI + unpause checks above; side jobs after return.
        _ensure_industry_ai_watch()
        return

    os.chdir(ROOT)
    if bootstrap:
        _run(["./run_all.sh", "prune-stale-pids"], timeout=30)

    # Daemons stay up always by default; order routing is gated inside each engine.
    always_online = os.getenv("KEEP_STACK_ALWAYS_ONLINE", "true").lower() in ("1", "true", "yes")

    # Trading engines FIRST so trainer thrash / slow ensures never starve fortress/HFT.
    checks: list[tuple[str, list[str]]] = [
        ("paper-awake", ["./run_all.sh", "ensure-paper-awake"]),
        ("intraday", ["./run_all.sh", "ensure-intraday"]),
        ("subsecond-obi", ["./run_all.sh", "ensure-subsecond"]),
        ("subsecond-earnings", ["./run_all.sh", "ensure-earnings"]),
        ("hft-rotator", ["./run_all.sh", "hft-rotator"]),
        ("valuation-news-watch", ["./run_all.sh", "valuation-news-watch"]),
        ("event-calendar-watch", ["./run_all.sh", "event-calendar-watch"]),
        ("exec-delay", ["./run_all.sh", "exec-delay-daemon"]),
    ]
    paper_host = _paper_order_host()
    if not paper_host:
        checks.append(("weekly", ["./run_all.sh", "ensure-weekly"]))
    if os.getenv("PAPER_USE_LONGTERM", "false").lower() in ("1", "true", "yes") and not paper_host:
        checks.append(("longterm", ["./run_all.sh", "ensure-longterm"]))
    if os.getenv("DAY_TRADE_MODE", "false").lower() in ("1", "true", "yes"):
        checks.append(("day-trade", ["./run_all.sh", "ensure-day-trade"]))
    # micro-scalp: only if explicitly enabled (paused during bleed — sleeve kept)
    if os.getenv("MICRO_SCALP_ENABLED", "false").lower() in ("1", "true", "yes"):
        checks.append(("micro-scalp", ["./run_all.sh", "ensure-micro-scalp"]))
    if os.getenv("CRYPTO_HFT_EXPERIMENTAL", "true").lower() in ("1", "true", "yes"):
        checks.append(("crypto-hft", ["./run_all.sh", "ensure-crypto-hft"]))
    if os.getenv("GAINZ_V2_ENABLED", "true").lower() in ("1", "true", "yes"):
        checks.append(("gainz-v2", ["./run_all.sh", "ensure-gainz-v2"]))
    if os.getenv("GAINZ_ESCAPE_WATCH", "true").lower() in ("1", "true", "yes"):
        checks.append(("gainz-escape-watch", ["./run_all.sh", "ensure-gainz-watch"]))
    checks.extend([
        ("execution-monitor", ["./run_all.sh", "ensure-execution-monitor"]),
        ("paper-hygiene", ["./run_all.sh", "ensure-paper-hygiene"]),
        ("hft-news-watch", ["./run_all.sh", "ensure-hft-news"]),
        ("bottom-fisher-watch", ["./run_all.sh", "bottom-fisher-watch"]),
        ("disk-cleanup", ["./run_all.sh", "ensure-disk-cleanup"]),
    ])
    if not paper_host:
        checks.extend([
            ("sheldon-hunt", ["./run_all.sh", "sheldon-hunt"]),
            ("universe-lifecycle-watch", ["./run_all.sh", "universe-lifecycle-watch"]),
            ("pattern-anomaly-watch", ["./run_all.sh", "pattern-anomaly-watch"]),
            ("stack-autotune", ["./run_all.sh", "ensure-autotune"]),
            ("self-improve", ["./run_all.sh", "ensure-self-improve"]),
            ("cortex-singularity", ["./run_all.sh", "ensure-cortex"]),
            ("free-agent", ["./run_all.sh", "ensure-free-agent"]),
        ])
    if os.getenv("USE_ALGO_PIPELINE", "true").lower() in ("1", "true", "yes") and not paper_host:
        checks.append(("algo-pipeline", ["./run_all.sh", "algo-pipeline"]))
    if os.getenv("CRAMER_CNBC_TOP10_ENABLED", "true").lower() in ("1", "true", "yes"):
        checks.append(("cramer-cnbc-poll", ["./run_all.sh", "ensure-cramer-cnbc"]))
    # Heavy cooks stay on fate-algobot-trainer. Paper 16GB must keep fortress/HFT alive.
    if not _paper_order_host():
        checks.append(("ule-watch", ["./run_all.sh", "ule-watch"]))
        checks.append(("continuous-learn", ["./run_all.sh", "ensure-continuous-learn"]))
        checks.append(("hist-cook", ["./run_all.sh", "hist-cook"]))
        checks.append(("event-learn-train", ["./run_all.sh", "event-learn-train"]))
        checks.append(("gen-learn-train", ["./run_all.sh", "gen-learn-train"]))
        if os.getenv("AUTOPILOT_AUTO_TRAIN", "true").lower() in ("1", "true", "yes") or os.getenv(
            "FOREVER_TRAIN", "true"
        ).lower() in ("1", "true", "yes"):
            checks.append(("retrain-weak-loop", ["./run_all.sh", "retrain-weak-until"]))
            checks.append(("train-lstm", ["./run_all.sh", "train-lstm"]))
    else:
        _log("paper_order_host", "skip heavy trainers — they run on fate-algobot-trainer")

    if _thermal_cool():
        keep = {
            "paper-awake",
            "intraday",
            "subsecond-obi",
            "subsecond-earnings",
            "hft-rotator",
            "weekly",
            "longterm",
            "paper-hygiene",
            "valuation-news-watch",
            "event-calendar-watch",
        }
        checks = [c for c in checks if c[0] in keep]
        _log("thermal_cool", f"skip trainers; keep {sorted(keep)}")

    hft_run_24x5 = os.getenv("HFT_RUN_24X5", "true").lower() in ("1", "true", "yes")
    weekday_24x5 = os.getenv("TRADE_WEEKDAY_24X5", "true").lower() in ("1", "true", "yes")
    hft_stopped = False
    for name, cmd in checks:
        trade_ok = True
        if always_online:
            trade_ok = True
        elif name in ("subsecond-obi", "subsecond-earnings", "hft-rotator"):
            try:
                from analytics.market_session import is_trading_day, orders_allowed

                # Keep HFT engines alive Mon–Fri; order routing is gated in Node (extended 04:00–20:00 ET).
                if hft_run_24x5 or weekday_24x5:
                    trade_ok = is_trading_day()
                else:
                    trade_ok = orders_allowed("any", for_hft=True)[0]
            except Exception:
                trade_ok = True
        elif name == "intraday":
            try:
                from analytics.market_session import intel_window_open, orders_allowed

                trade_ok = intel_window_open()[0] or orders_allowed("any")[0]
            except Exception:
                trade_ok = True
        if not trade_ok:
            if name == "subsecond-obi":
                # Only tear down on weekends — never kill pre-market HFT (fortress starts at 09:00).
                if (
                    not hft_stopped
                    and _daemon_alive("subsecond-obi")
                    and not (hft_run_24x5 or weekday_24x5)
                    and not always_online
                ):
                    _log("session_stop", "hft-outside-session")
                    _run(["./run_all.sh", "stop-hft-engines"], timeout=60)
                    hft_stopped = True
                continue
            if name != "hft-rotator":
                continue
        if _daemon_alive(name):
            continue
        cool = _TRAINER_COOLDOWN_SEC.get(name)
        if cool:
            last = _LAST_TRAINER_START.get(name, 0.0)
            if time.time() - last < cool:
                _log("cooldown", f"{name} wait {cool - (time.time() - last):.0f}s")
                continue
        _log("restart", name)
        rc = _run(cmd, timeout=180 if name in _TRAINER_COOLDOWN_SEC else 120)
        _LAST_TRAINER_START[name] = time.time()
        if rc != 0:
            _log("restart_fail", f"{name} exit={rc}", ok=False)

    # Side jobs AFTER cores are up (slow network sync must not block restarts).
    _maybe_kill_hung_fortress()
    if _thermal_cool():
        _log("thermal_cool_side", "skip prefetch/train/sim/news-refresh")
        return
    _ensure_industry_ai_watch()
    _maybe_cramer_sync()
    _maybe_morning_prefetch()
    _maybe_hft_news_refresh()
    _run_trading_day_autorun()
    _maybe_ensure_paper_sim()
    _maybe_verify_trades()
    _maybe_self_maintenance()


def main() -> int:
    once = "--once" in sys.argv or os.getenv("WATCHDOG_ONCE", "").lower() in ("1", "true", "yes")
    poll = int(os.getenv("WATCHDOG_POLL_SEC", os.getenv("DAEMON_SUPERVISOR_POLL_SEC", "45")))
    bootstrap = os.getenv("WATCHDOG_BOOTSTRAP", "true").lower() in ("1", "true", "yes")

    # Single-instance lock — multiple watchdogs thrash-restart cores ("random stops").
    lock_path = ROOT / "data" / "stack_watchdog.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = None
    try:
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
        if sys.platform == "darwin" or sys.platform.startswith("linux"):
            import fcntl

            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("[watchdog] another instance holds the lock — exit", flush=True)
                return 0
        os.write(lock_fd, f"{os.getpid()}\n".encode())
        os.ftruncate(lock_fd, 0)
        os.lseek(lock_fd, 0, os.SEEK_SET)
        os.write(lock_fd, f"{os.getpid()}\n".encode())
    except Exception as e:
        print(f"[watchdog] lock warn: {e}", flush=True)

    if once:
        ensure_stack(bootstrap=bootstrap)
        return 0

    _log("start", f"poll={poll}s pid={os.getpid()}")
    first = True
    while True:
        try:
            ensure_stack(bootstrap=bootstrap and first)
            first = False
        except Exception as e:
            _log("loop_error", str(e), ok=False)
        time.sleep(poll)


if __name__ == "__main__":
    raise SystemExit(main())
