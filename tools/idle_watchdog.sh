#!/usr/bin/env bash
# Kill idle trading/training processes and restart cores. Run every few minutes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOG="$ROOT/logs/idle_watchdog_latest.log"
stamp() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(stamp)] $*" | tee -a "$LOG"; }

age_sec() {
  local f="$1"
  [ -e "$f" ] || { echo 999999; return; }
  echo $(( $(date +%s) - $(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f" 2>/dev/null || echo 0) ))
}

cpu_of() {
  local pat="$1"
  local pid
  pid=$(pgrep -f "$pat" | head -1 || true)
  [ -n "$pid" ] || { echo 0; return; }
  ps -p "$pid" -o pcpu= 2>/dev/null | tr -d ' ' || echo 0
}

# --- trading cores: log must be fresh OR process gets replaced ---
ensure_trade() {
  local name="$1" logpat="$2" pat="$3" start_cmd="$4" max_age="${5:-180}"
  local age cpu
  age=$(age_sec "logs/${logpat}_latest.log")
  if ! pgrep -f "$pat" >/dev/null 2>&1; then
    log "DEAD $name — starting"
    bash -c "cd '$ROOT' && set -a; source .env; source data/deploy_scale.env; set +a; $start_cmd" >>"$LOG" 2>&1 || true
    return
  fi
  cpu=$(cpu_of "$pat")
  # Idle = stale log AND near-zero CPU for a real stall (feature builds can
  # pause logging for minutes while still using CPU intermittently).
  if [ "$age" -gt "$max_age" ]; then
    # awk compare float
    idle=$(python3 -c "print(1 if float('${cpu:-0}') < 0.2 else 0)")
    if [ "$idle" = "1" ]; then
      log "IDLE $name age=${age}s cpu=${cpu} — kill+restart"
      pkill -9 -f "$pat" 2>/dev/null || true
      sleep 1
      bash -c "cd '$ROOT' && set -a; source .env; source data/deploy_scale.env; set +a; $start_cmd" >>"$LOG" 2>&1 || true
    else
      log "SLOW $name age=${age}s but cpu=${cpu} — leave"
    fi
  else
    log "OK $name age=${age}s cpu=${cpu}"
  fi
}

# --- trainers: if 0% CPU and log >10m, kill (don't restart empty gap-fill) ---
kill_idle_train() {
  local name="$1" pat="$2" logpat="$3" max_age="${4:-600}"
  pgrep -f "$pat" >/dev/null 2>&1 || return 0
  local age cpu
  age=$(age_sec "logs/${logpat}_latest.log")
  cpu=$(cpu_of "$pat")
  idle=$(python3 -c "print(1 if float('${cpu:-0}') < 0.3 else 0)")
  if [ "$age" -gt "$max_age" ] && [ "$idle" = "1" ]; then
    log "KILL_IDLE_TRAIN $name age=${age}s cpu=${cpu}"
    pkill -9 -f "$pat" 2>/dev/null || true
  else
    log "TRAIN $name age=${age}s cpu=${cpu}"
  fi
}

mkdir -p logs
log "==== idle watchdog tick ===="
set -a
# shellcheck disable=SC1091
source "$ROOT/.env" 2>/dev/null || true
# shellcheck disable=SC1091
source "$ROOT/data/deploy_scale.env" 2>/dev/null || true
set +a
export DAY_TRADE_MODE=true HFT_DRY_RUN=false

ensure_trade fortress intraday "fortress_live.py" "./run_all.sh start intraday" 900
ensure_trade hft subsecond-obi "dist/obi-tape/index.js" "./run_all.sh hft-live" 600
# Day-trade is quiet on weekends / outside RTH — don't thrash on stale logs.
ensure_trade daytrade day_trade "day_trade_daemon.py" "./run_all.sh day-trade" 1200
# Micro-scalp / noise-harvest — high attempt-rate paper sidecar (additive to OBI).
if [ "${MICRO_SCALP_ENABLED:-false}" = "true" ] || [ "${MICRO_SCALP_ENABLED:-false}" = "1" ]; then
  ensure_trade microscalp micro_scalp "micro_scalp_daemon.py" "./run_all.sh micro-scalp" 300
fi
# stack_watchdog does not maintain a dedicated `stack_watchdog_latest.log`.
# Check process liveness only; treating a missing log as stale caused a restart loop.
if ! pgrep -f "stack_watchdog.py" >/dev/null 2>&1; then
  log "DEAD watchdog — starting"
  ./run_all.sh stack-watchdog >>"$LOG" 2>&1 || true
else
  log "OK watchdog process alive"
fi

# Kill zombie trainers only
kill_idle_train top100 "train_top100_perfect.py" train-top100 480
kill_idle_train daily_gap "parallel_train.py --pipeline daily --missing-only" train 600
kill_idle_train daily_rebuild "parallel_train.py --pipeline daily --workers" train-top100 480
kill_idle_train enhancement "enhancement_queue.py" enhancement_queue 900

# If top100 dead after kill, restart heavy path
if ! pgrep -f "train_top100_perfect.py" >/dev/null 2>&1; then
  log "RESTART train-top100"
  nohup ./run_all.sh train-top100 >>"$LOG" 2>&1 &
fi

# Pattern / regional-imbalance finder must stay alive
if ! pgrep -f "hidden_pattern_scan.py" >/dev/null 2>&1; then
  log "DEAD pattern-anomaly — starting"
  ./run_all.sh pattern-anomaly-watch >>"$LOG" 2>&1 || true
else
  log "OK pattern-anomaly process alive"
fi

# Operator Doc chat (Google Doc or local mirror) — honest math-first operator
if ! pgrep -f "operator_doc_chat.py" >/dev/null 2>&1; then
  log "DEAD operator-doc — starting"
  ./run_all.sh doc-chat >>"$LOG" 2>&1 || true
else
  log "OK operator-doc process alive"
fi

# Enhancement queue keepalive (historical finish path) — skip if already done
if ! pgrep -f "enhancement_queue.py" >/dev/null 2>&1; then
  done_phase=0
  if [ -f "$ROOT/data/enhancement_queue_state.json" ]; then
    done_phase=$(python3 -c "
import json
from pathlib import Path
p=Path('$ROOT/data/enhancement_queue_state.json')
try:
    d=json.loads(p.read_text())
    print(1 if d.get('phase')=='done' else 0)
except Exception:
    print(0)
" 2>/dev/null || echo 0)
  fi
  if [ "$done_phase" = "1" ]; then
    log "SKIP enhancement-queue (phase=done) — top100/retrain own historical path"
  else
    log "RESTART enhancement-queue"
    nohup ./run_all.sh enhancement-queue >>"$LOG" 2>&1 &
  fi
fi

log "==== tick done ===="
