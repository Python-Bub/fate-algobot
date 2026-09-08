#!/usr/bin/env bash
# Runs on the GCP VM: 24/7 paper stack (not SPOT training).
set -euo pipefail
cd ~/FATE_AlgoBot

PY="python3"
if command -v python3.12 >/dev/null 2>&1; then PY="python3.12"; fi

"$PY" -m venv venv
./venv/bin/pip install -q --upgrade pip wheel
./venv/bin/pip install -q -r requirements.txt
(cd hft && npm install --no-audit --no-fund && npm run build)
mkdir -p logs .pids data models/intraday
chmod +x run_all.sh run_hft.sh 2>/dev/null || true

if [ ! -f .env ]; then
  echo "[REMOTE] ERROR: copy .env from your Mac before paper:" >&2
  echo "  ./cloud/gcp_bootstrap.sh sync-env" >&2
  exit 1
fi

# Inline exports in the tmux command: an already-running tmux server
# (e.g. bootstrap session) does not inherit this shell's environment.
PAPER_USE_FORTRESS="${PAPER_USE_FORTRESS:-true}"
PAPER_USE_LONGTERM="${PAPER_USE_LONGTERM:-true}"
SKIP_PAPER_AUTO_TRAIN="${SKIP_PAPER_AUTO_TRAIN:-true}"

tmux kill-session -t paper 2>/dev/null || true
tmux new-session -d -s paper "cd ~/FATE_AlgoBot && export PAPER_USE_FORTRESS=${PAPER_USE_FORTRESS} PAPER_USE_LONGTERM=${PAPER_USE_LONGTERM} SKIP_PAPER_AUTO_TRAIN=${SKIP_PAPER_AUTO_TRAIN} && ./run_all.sh paper 2>&1 | tee -a logs/gcp_paper.log; exec bash"
echo "[REMOTE] tmux session 'paper' started. Attach: tmux attach -t paper"
