#!/usr/bin/env bash
# Runs on the GCP VM after rsync. Do not run locally.
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
  echo "[REMOTE] WARNING: no .env on VM — copy yours:  rsync -e \"gcloud compute ssh --zone=ZONE INSTANCE --\" .env INSTANCE:~/FATE_AlgoBot/.env"
fi

# 8 vCPU / 64 GB — can afford more workers than a 16 GB laptop.
export TRAIN_WORKERS="${TRAIN_WORKERS:-8}"
export INTRADAY_WORKERS="${INTRADAY_WORKERS:-4}"

tmux kill-session -t train 2>/dev/null || true
tmux new-session -d -s train "cd ~/FATE_AlgoBot && ./run_all.sh train-everything 2>&1 | tee -a logs/gcp_train.log; exec bash"
echo "[REMOTE] tmux session 'train' started. Attach: tmux attach -t train"
