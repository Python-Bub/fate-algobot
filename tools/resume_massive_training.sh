#!/usr/bin/env bash
# Resume trillion-scale talk teacher + tests — LOCAL templates only (no Qwen disguise).
#
# HONEST: closing the Mac lid WILL stop local caffeinate / train / daemons unless
# you leave the machine awake (AC + caffeinate) or run remote. Progress is
# checkpointed — resume at wake (~05:30 PT):
#
#   ./tools/resume_massive_training.sh --continue
#   # or overnight loop:
#   caffeinate -dims ./tools/overnight_talk_trillion.sh
#   ./run_all.sh talk-overnight
#   ./run_all.sh ensure-stack   # restart trading daemons
#   ./run_all.sh status
#
# 1B edit gate: intel/talk_edit_gate.py reads teacher_done / problems_done from
# data/talk_brain/massive_harness_checkpoint.json + trillion_progress.jsonl
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/venv/bin/python"
export PYTHONPATH="$ROOT"
export TALK_USE_OLLAMA_TEACHER=false
export TALK_OLLAMA_PULL_CHAT=false
export TALK_ALLOW_EDITS="${TALK_ALLOW_EDITS:-false}"
export TALK_TEACHER_PROBLEMS="${TALK_TEACHER_PROBLEMS:-1000000000000}"
export TALK_TEST_ITERS="${TALK_TEST_ITERS:-10000000}"
export TALK_TEACHER_SESSION_CAP="${TALK_TEACHER_SESSION_CAP:-2000000}"
export TALK_TEST_SESSION_CAP="${TALK_TEST_SESSION_CAP:-2000000}"
export TALK_TEACHER_TEMPLATES="${TALK_TEACHER_TEMPLATES:-250000}"
export TALK_SKIP_TEACHER_REWRITE="${TALK_SKIP_TEACHER_REWRITE:-true}"
export TALK_INCLUDE_INVESTING_GUIDE=true
echo "[resume] teacher_target=$TALK_TEACHER_PROBLEMS test_target=$TALK_TEST_ITERS session_cap=$TALK_TEACHER_SESSION_CAP local_only=1 edits=OFF"
# Ensure guide Q&A bank exists
"$PY" -u "$ROOT/tools/train_talk_investing_guide.py" --no-train || true
# Persist gate status before continue
"$PY" -c "from intel.talk_edit_gate import persist_status; import json; print(json.dumps(persist_status(), indent=2))" || true
exec "$PY" -u "$ROOT/tools/talk_massive_harness.py" --continue
