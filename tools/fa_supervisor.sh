#!/usr/bin/env bash
# Free-agent supervisor: keep tools/free_agent_loop.py alive forever, log every
# exit (code 128+signal reveals an external kill), and restart with backoff.
# Tracked by the free-agent pidfile so the rest of run_all.sh sees the supervisor
# as "the daemon".
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

PY="${FATE_PYTHON:-$ROOT/venv/bin/python}"
[ -x "$PY" ] || PY="python3"

EXIT_LOG="$ROOT/logs/fa_supervisor_exits.log"
mkdir -p "$ROOT/logs"

backoff=2
while true; do
  echo "[fa-supervisor] $(date -u +%FT%TZ) starting free_agent_loop.py (py=$PY)"
  "$PY" -u "$ROOT/tools/free_agent_loop.py" </dev/null
  rc=$?
  # 128+N => terminated by signal N. 137=SIGKILL, 143=SIGTERM, 130=SIGINT.
  echo "$(date -u +%FT%TZ) free_agent_loop exited rc=$rc" >>"$EXIT_LOG"
  echo "[fa-supervisor] $(date -u +%FT%TZ) loop exited rc=$rc — restarting in ${backoff}s"
  # Clean shutdown via SIGINT/SIGTERM => stop supervising.
  if [ "$rc" = "130" ] || [ "$rc" = "143" ]; then
    echo "[fa-supervisor] clean stop signal (rc=$rc) — exiting supervisor"
    exit 0
  fi
  sleep "$backoff"
  backoff=$(( backoff < 30 ? backoff * 2 : 30 ))
done
