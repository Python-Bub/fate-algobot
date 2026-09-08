#!/bin/bash
# GCE startup-script: start 24/7 paper after every reboot.
# Does not print secrets. Idempotent if fortress is already up.
set -euo pipefail
PAPER_USER="${PAPER_USER:-demirgenc}"
ROOT="/home/${PAPER_USER}/FATE_AlgoBot"
export PATH="/usr/local/bin:/usr/bin:/bin"

for _ in $(seq 1 40); do
  if ping -c1 -W2 8.8.8.8 >/dev/null 2>&1; then
    break
  fi
  sleep 3
done

if [ ! -d "$ROOT" ] || [ ! -f "$ROOT/run_all.sh" ]; then
  echo "[startup] $ROOT missing — skip paper start" >&2
  exit 0
fi
if [ ! -f "$ROOT/.env" ]; then
  echo "[startup] $ROOT/.env missing — skip (Alpaca keys live only on this VM)" >&2
  exit 0
fi

if pgrep -u "$PAPER_USER" -f "fortress_live.py" >/dev/null 2>&1; then
  echo "[startup] fortress already running"
  exit 0
fi

mkdir -p "$ROOT/logs"
chown -R "${PAPER_USER}:${PAPER_USER}" "$ROOT/logs" "$ROOT/.pids" 2>/dev/null || true

sudo -u "$PAPER_USER" bash -lc "
set -e
cd '$ROOT'
export PAPER_USE_FORTRESS=true
export PAPER_USE_LONGTERM=true
export SKIP_PAPER_AUTO_TRAIN=true
export NETWORK_FIRST=true
./run_all.sh paper >> logs/gcp_paper.log 2>&1
"
echo "[startup] paper launched"
