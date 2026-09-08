#!/usr/bin/env bash
# Overnight local CharLSTM training toward 1e12 questions — NO Ollama/Qwen replies.
# Keep Mac awake; wake by ~05:30 PT.
#
# HONEST lid-close: closing the laptop STOPS this loop + caffeinate unless the Mac
# stays awake (AC power + clamshell/external display, or leave lid open). Checkpoints
# in data/talk_brain/massive_harness_checkpoint.json + trillion_progress.jsonl survive.
#
#   caffeinate -dims ./tools/overnight_talk_trillion.sh
#   # or: ./run_all.sh talk-overnight
# Morning resume:
#   ./tools/resume_massive_training.sh --continue
#   ./run_all.sh ensure-stack && ./run_all.sh status
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/venv/bin/python"
export PYTHONPATH="$ROOT"
export TALK_USE_OLLAMA_TEACHER=false
export TALK_OLLAMA_PULL_CHAT=false
export TALK_ALLOW_EDITS="${TALK_ALLOW_EDITS:-false}"
# Force trillion-scale unless TALK_TRILLION_OVERRIDE=1
if [ "${TALK_TRILLION_OVERRIDE:-0}" != "1" ]; then
  export TALK_TEACHER_PROBLEMS=1000000000000
  # Higher session throughput toward 1B edit gate (honest counters; no skipped checks)
  export TALK_TEACHER_SESSION_CAP="${TALK_TEACHER_SESSION_CAP:-2000000}"
  export TALK_TEACHER_TEMPLATES="${TALK_TEACHER_TEMPLATES:-250000}"
  export TALK_TEST_ITERS=10000000
  export TALK_TEST_SESSION_CAP=2000000
fi
export TALK_REWARD_IN_HARNESS="${TALK_REWARD_IN_HARNESS:-false}"
export TALK_CONFINEMENT=true
export TALK_GENERATE_OFFLINE=true
export TALK_SKIP_TEACHER_REWRITE="${TALK_SKIP_TEACHER_REWRITE:-true}"
export TALK_INCLUDE_INVESTING_GUIDE=true
# How many harness batches between CharLSTM train passes (maximize Q&A climb)
HARNESS_BURSTS="${TALK_OVERNIGHT_HARNESS_BURSTS:-4}"
TRAIN_STEPS="${TALK_OVERNIGHT_TRAIN_STEPS:-1000}"

LOGDIR="$ROOT/data/talk_brain"
mkdir -p "$LOGDIR" "$ROOT/logs" "$ROOT/.pids"
LOG="$LOGDIR/overnight_trillion.log"
echo $$ > "$ROOT/.pids/talk-overnight.pid"
echo "[overnight] pid=$$ target_problems=$TALK_TEACHER_PROBLEMS session_cap=$TALK_TEACHER_SESSION_CAP bursts=$HARNESS_BURSTS train_steps=$TRAIN_STEPS edits=OFF" | tee -a "$LOG"
echo "[overnight] local CharLSTM only — ollama teacher OFF; lid close kills unless caffeinate+awake" | tee -a "$LOG"
"$PY" -c "from intel.talk_edit_gate import persist_status; print('[overnight] edit_gate', persist_status())" >>"$LOG" 2>&1 || true
# Ensure investing-guide question bank is fully distilled before climbing
"$PY" -u "$ROOT/tools/train_talk_investing_guide.py" --no-train >>"$LOG" 2>&1 || true

# Foreground loop (caller should wrap with nohup/caffeinate)
while true; do
  for _burst in $(seq 1 "$HARNESS_BURSTS"); do
    echo "[overnight] $(date -u +%Y-%m-%dT%H:%M:%SZ) harness --continue burst=${_burst}/${HARNESS_BURSTS}" | tee -a "$LOG"
    "$PY" -u "$ROOT/tools/talk_massive_harness.py" --continue >>"$LOG" 2>&1 || true
    "$PY" -c "from intel.talk_edit_gate import persist_status; persist_status()" >>"$LOG" 2>&1 || true
  done
  echo "[overnight] $(date -u +%Y-%m-%dT%H:%M:%SZ) train-talk local steps=$TRAIN_STEPS" | tee -a "$LOG"
  TALK_FOCUS=dialogue TALK_DICT_WEIGHT=0 TALK_INCLUDE_DICT=false \
    "$PY" -u "$ROOT/tools/train_talk_brain.py" --steps "$TRAIN_STEPS" >>"$LOG" 2>&1 || true
  sleep 2
done
