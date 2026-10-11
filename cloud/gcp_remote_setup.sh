#!/usr/bin/env bash
# Runs on the GCP trainer VM after rsync. Do not run locally.
# Starts autonomous historical + LSTM-all training. Does not start paper/HFT.
set -euo pipefail
cd ~/FATE_AlgoBot

PY="python3"
if command -v python3.12 >/dev/null 2>&1; then PY="python3.12"; fi

"$PY" -m venv venv
./venv/bin/pip install -q --upgrade pip wheel
./venv/bin/pip install -q -r requirements.txt
(cd hft && npm install --no-audit --no-fund && npm run build)
mkdir -p logs .pids data models/intraday models/lstm models/neural_ensemble
chmod +x run_all.sh run_hft.sh cloud/gcp_startup_train.sh cloud/install_train_systemd.sh 2>/dev/null || true

if [ ! -f .env ]; then
  echo "[REMOTE] WARNING: no .env on VM — copy yours:  ./cloud/gcp_bootstrap.sh sync-env"
fi

# 8 vCPU / 64 GB — more workers than a 16 GB laptop. Do not cap the universe.
export TRAIN_WORKERS="${TRAIN_WORKERS:-8}"
export INTRADAY_WORKERS="${INTRADAY_WORKERS:-4}"
export LSTM_WORKERS="${LSTM_WORKERS:-6}"
export SKIP_PAPER_AUTO_TRAIN=true
export NETWORK_FIRST="${NETWORK_FIRST:-true}"
export TRAIN_FORCE_YAHOO="${TRAIN_FORCE_YAHOO:-true}"
export TRAIN_DATA_START="${TRAIN_DATA_START:-2010-01-01}"
export STRONG_TRAIN_DATA_START="${STRONG_TRAIN_DATA_START:-2010-01-01}"
export USE_LSTM_HEAD=true
export BLEND_LSTM_INTO_META=true
export LSTM_TRAIN_SCOPE=all
export LSTM_HIDDEN="${LSTM_HIDDEN:-256}"
export LSTM_LAYERS="${LSTM_LAYERS:-4}"
export LSTM_SEQ_LEN="${LSTM_SEQ_LEN:-80}"
export LSTM_EPOCHS="${LSTM_EPOCHS:-24}"
export NEURAL_EPOCHS="${NEURAL_EPOCHS:-24}"
export HIST_COOK_YEARS="${HIST_COOK_YEARS:-16}"
export HIST_COOK_MAX_SYMBOLS="${HIST_COOK_MAX_SYMBOLS:-1200}"
export HIST_COOK_TRAIN_LSTM=true
export FAST_MODE=false
export FAST_UNIVERSE_TRAIN=false
export TRAIN_TOP50_ONLY=false
export TRAIN_TOP100_ONLY=false

tmux kill-session -t train 2>/dev/null || true
tmux new-session -d -s train "cd ~/FATE_AlgoBot && ./run_all.sh cloud-train 2>&1 | tee -a logs/gcp_train.log; exec bash"
echo "[REMOTE] tmux session 'train' started (cloud-train). Attach: tmux attach -t train"

if command -v sudo >/dev/null 2>&1; then
  bash ~/FATE_AlgoBot/cloud/install_train_systemd.sh || echo "[REMOTE] systemd train unit skipped"
fi
