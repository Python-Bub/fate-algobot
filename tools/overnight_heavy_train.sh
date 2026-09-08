#!/usr/bin/env bash
# Overnight heavy batch: talk reward + massive harness continue + trading gap-fill.
# Does NOT shrink universe or skip phases. Leave Mac awake (caffeinate / paper-awake).
#
#   ./tools/overnight_heavy_train.sh
#   TALK_REWARD_STEPS=8000 ./tools/overnight_heavy_train.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/venv/bin/python"
LOGDIR="${ROOT}/logs"
mkdir -p "$LOGDIR" "$ROOT/.pids" "$ROOT/data/talk_brain"

export PYTHONPATH="$ROOT"
export TALK_ALLOW_EDITS="${TALK_ALLOW_EDITS:-false}"
export TRAIN_PRIORITIZE="${TRAIN_PRIORITIZE:-letter_rr}"
export TALK_REWARD_STEPS="${TALK_REWARD_STEPS:-6000}"
export TALK_REWARD_LR="${TALK_REWARD_LR:-8e-4}"
export TALK_REWARD_PAIRS="${TALK_REWARD_PAIRS:-1200}"
export TALK_TEACHER_PROBLEMS="${TALK_TEACHER_PROBLEMS:-1000000000}"
export TALK_TEST_ITERS="${TALK_TEST_ITERS:-5000000}"
export TALK_TEACHER_SESSION_CAP="${TALK_TEACHER_SESSION_CAP:-250000}"
export TALK_TEST_SESSION_CAP="${TALK_TEST_SESSION_CAP:-1000000}"

# Ensure caffeinate / paper-awake
if ! pgrep -x caffeinate >/dev/null 2>&1; then
  ./run_all.sh ensure-paper-awake || true
fi

ts="$(date +%Y%m%d_%H%M%S)"
log="$LOGDIR/overnight_heavy_${ts}.log"
ln -sf "$log" "$LOGDIR/overnight_heavy_latest.log"

{
  echo "[overnight] start $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "[overnight] reward steps=$TALK_REWARD_STEPS teacher=$TALK_TEACHER_PROBLEMS"

  # 1) Preference / reward train (hold-out gated)
  "$PY" -u "$ROOT/tools/train_talk_reward.py" || echo "[overnight] reward train rc=$?"

  # 2) Massive teacher + tests continue
  "$PY" -u "$ROOT/tools/talk_massive_harness.py" --continue || echo "[overnight] harness rc=$?"

  # 3) Another reward pass after more teacher data
  "$PY" -u "$ROOT/tools/train_talk_reward.py" || true

  echo "[overnight] done $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "[overnight] resume: ./tools/overnight_heavy_train.sh"
  echo "[overnight] or: ./tools/resume_massive_training.sh"
} >>"$log" 2>&1 &
echo $! >"$ROOT/.pids/overnight-heavy.pid"
echo "[overnight] background pid=$(cat "$ROOT/.pids/overnight-heavy.pid") log=$log"
echo "  tail -f $LOGDIR/overnight_heavy_latest.log"
