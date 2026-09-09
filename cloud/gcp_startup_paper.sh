#!/bin/bash
# GCE startup-script: start 24/7 paper after every reboot, including HFT.
# Does not print secrets. Always re-ensures the stack (fortress-up is not "done").
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

mkdir -p "$ROOT/logs" "$ROOT/.pids"
chown -R "${PAPER_USER}:${PAPER_USER}" "$ROOT/logs" "$ROOT/.pids" 2>/dev/null || true

sudo -u "$PAPER_USER" bash -lc "
set -e
cd '$ROOT'
export PAPER_USE_FORTRESS=true
export PAPER_USE_LONGTERM=true
export SKIP_PAPER_AUTO_TRAIN=true
export NETWORK_FIRST=true
export FATE_ORDER_ROLE=gcp-paper
export KEEP_STACK_ALWAYS_ONLINE=true
export DAY_TRADE_MODE=true
export MICRO_SCALP_ENABLED=true
./run_all.sh paper >> logs/gcp_paper.log 2>&1
./run_all.sh ensure-subsecond >> logs/gcp_paper.log 2>&1 || true
./run_all.sh ensure-earnings >> logs/gcp_paper.log 2>&1 || true
./run_all.sh ensure-weekly >> logs/gcp_paper.log 2>&1 || true
./run_all.sh ensure-longterm >> logs/gcp_paper.log 2>&1 || true
./run_all.sh valuation-news-watch >> logs/gcp_paper.log 2>&1 || true
./run_all.sh event-calendar-watch >> logs/gcp_paper.log 2>&1 || true
./run_all.sh watchdog >> logs/gcp_paper.log 2>&1 || true
"
echo "[startup] paper + HFT + watchdog launched"
