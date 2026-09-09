#!/bin/bash
# GCE startup-script: resume autonomous training after Spot STOP / reboot.
# Does not print secrets. Does not start paper/HFT (orders stay on the paper VM).
set -euo pipefail
TRAIN_USER="${TRAIN_USER:-demirgenc}"
ROOT="/home/${TRAIN_USER}/FATE_AlgoBot"
export PATH="/usr/local/bin:/usr/bin:/bin"

for _ in $(seq 1 40); do
  if ping -c1 -W2 8.8.8.8 >/dev/null 2>&1; then
    break
  fi
  sleep 3
done

if [ ! -d "$ROOT" ] || [ ! -f "$ROOT/run_all.sh" ]; then
  echo "[startup] $ROOT missing — skip train start" >&2
  exit 0
fi

mkdir -p "$ROOT/logs" "$ROOT/.pids" "$ROOT/models" "$ROOT/data"
chown -R "${TRAIN_USER}:${TRAIN_USER}" "$ROOT/logs" "$ROOT/.pids" 2>/dev/null || true

sudo -u "$TRAIN_USER" bash -lc "
set -e
cd '$ROOT'
export SKIP_PAPER_AUTO_TRAIN=true
export NETWORK_FIRST=true
export TRAIN_FORCE_YAHOO=true
export TRAIN_DATA_START=2010-01-01
export USE_LSTM_HEAD=true
export LSTM_TRAIN_SCOPE=all
./run_all.sh cloud-train >> logs/gcp_train.log 2>&1
"
echo "[startup] cloud-train launched"
