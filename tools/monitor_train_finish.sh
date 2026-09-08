#!/usr/bin/env bash
# Keep trainers alive and prove they are writing logs (not zombie / instant-exit).
# Usage: nohup ./tools/monitor_train_finish.sh >/tmp/train_monitor.log 2>&1 &
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/venv/bin/python"
LOGDIR="${ROOT}/logs"
mkdir -p "$LOGDIR" "$ROOT/data"
STATE="$ROOT/data/train_monitor_state.json"
REPORT="$LOGDIR/train_monitor_latest.log"

stamp() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "[$(stamp)] $*" | tee -a "$REPORT"; }

alive_pat() {
  pgrep -f "$1" >/dev/null 2>&1
}

log_fresh() {
  # true if latest log for prefix mtime within $2 seconds
  local prefix="$1" max_age="${2:-900}"
  local f
  f="$(ls -t "$LOGDIR"/${prefix}*.log 2>/dev/null | head -1 || true)"
  [[ -n "$f" ]] || return 1
  local age
  age=$(( $(date +%s) - $(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f" 2>/dev/null || echo 0) ))
  [[ "$age" -le "$max_age" ]]
}

kick_if_needed() {
  local name="$1" cmd="$2" pat="$3" prefix="$4"
  if alive_pat "$pat"; then
    if log_fresh "$prefix" 1800; then
      log "OK $name running + log fresh"
      return 0
    fi
    log "WARN $name process alive but log stale >30m — restarting"
    pkill -f "$pat" 2>/dev/null || true
    sleep 2
  else
    log "RESTART $name (not running)"
  fi
  # shellcheck disable=SC2086
  nohup bash -c "cd '$ROOT' && $cmd" >>"$LOGDIR/train_monitor_kicks.log" 2>&1 &
  sleep 8
  if alive_pat "$pat"; then
    log "STARTED $name"
  else
    # Instant exit often means "nothing pending" — probe log
    local f
    f="$(ls -t "$LOGDIR"/${prefix}*.log 2>/dev/null | head -1 || true)"
    if [[ -n "$f" ]] && grep -qiE 'nothing to do|nothing pending|checkpoint complete|already finished' "$f"; then
      log "DONE $name (queue empty / finished — not a bail)"
    else
      log "FAIL $name did not stay up — check $f"
    fi
  fi
}

log "==== train monitor start ===="
# Max path: gaps + lstm + enhancement + weak retrain (never shrink)
kick_if_needed "train-gaps-daily" "./run_all.sh train-missing-fast" "parallel_train.py --pipeline daily" "train_"
kick_if_needed "train-intraday-gap" "./run_all.sh train-intraday-gap" "parallel_train.py --pipeline intraday" "train-intraday_"
kick_if_needed "train-lstm" "./run_all.sh train-lstm" "train_lstm_heads.py|LSTM-BATCH|train-lstm" "train-lstm_"
kick_if_needed "enhancement-queue" "./run_all.sh enhancement-queue" "enhancement_queue.py" "enhancement_queue_"
kick_if_needed "retrain-weak" "./run_all.sh retrain-weak-until" "retrain_top100_strong.py|retrain_weak" "retrain"

# Loop: re-check every 10 minutes for a few hours
for i in $(seq 1 36); do
  sleep 600
  log "---- heartbeat $i/36 ----"
  kick_if_needed "train-gaps-daily" "./run_all.sh train-missing-fast" "parallel_train.py --pipeline daily" "train_"
  kick_if_needed "train-intraday-gap" "./run_all.sh train-intraday-gap" "parallel_train.py --pipeline intraday" "train-intraday_"
  kick_if_needed "train-lstm" "./run_all.sh train-lstm" "train_lstm_heads.py" "train-lstm_"
  kick_if_needed "enhancement-queue" "./run_all.sh enhancement-queue" "enhancement_queue.py" "enhancement_queue_"
  kick_if_needed "retrain-weak" "./run_all.sh retrain-weak-until" "retrain_top100_strong.py" "retrain"
  # Progress snapshot
  "$PY" - <<'PY' >>"$REPORT" 2>&1 || true
import json
from pathlib import Path
root = Path(".")
def done(p):
    try:
        d=json.loads(Path(p).read_text())
        return len(d.get("done",[])), len(d.get("failed",[]))
    except Exception:
        return None, None
for label, path in [
    ("daily", "data/train_checkpoint.json"),
    ("intraday", "data/intraday_train_checkpoint.json"),
]:
    d,f = done(path)
    print(f"checkpoint {label}: done={d} failed={f}")
lstm = list(Path("models/lstm").glob("*.pkl")) if Path("models/lstm").exists() else []
print(f"lstm_heads_files≈{len(lstm)}")
PY
done

log "==== train monitor finished window ===="
