#!/usr/bin/env bash
# Restart a command forever (for nohup paper / sim daemons).
# Usage: daemon_loop.sh <pause_seconds> -- <command> [args...]
#
# Optional hang/idle kill:
#   DAEMON_MAX_RUNTIME_SEC  hard wall-clock limit per run (0=off)
#   DAEMON_IDLE_LOG_SEC     kill if process stdout/stderr log stops growing (0=off)
#   DAEMON_LOG_PATH         log file to watch for idle growth (required for idle kill)
set -uo pipefail
pause="${1:?pause seconds required}"
shift
[[ "${1:-}" == "--" ]] && shift
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"
max_runtime="${DAEMON_MAX_RUNTIME_SEC:-0}"
idle_sec="${DAEMON_IDLE_LOG_SEC:-0}"
log_path="${DAEMON_LOG_PATH:-}"

_run_idle_aware() {
  if [[ ! "$max_runtime" =~ ^[0-9]+$ ]]; then max_runtime=0; fi
  if [[ ! "$idle_sec" =~ ^[0-9]+$ ]]; then idle_sec=0; fi
  if [[ "$max_runtime" -le 0 && "$idle_sec" -le 0 ]]; then
    "$@"
    return $?
  fi
  local child_pid size0 last_grow=0 elapsed=0
  "$@" &
  child_pid=$!
  size0=0
  [[ -n "$log_path" && -f "$log_path" ]] && size0=$(wc -c <"$log_path" 2>/dev/null | tr -d ' ' || echo 0)
  while kill -0 "$child_pid" 2>/dev/null; do
    sleep 20
    elapsed=$((elapsed + 20))
    last_grow=$((last_grow + 20))
    if [[ -n "$log_path" && -f "$log_path" ]]; then
      local size1
      size1=$(wc -c <"$log_path" 2>/dev/null | tr -d ' ' || echo 0)
      if [[ "$size1" -gt "$size0" ]]; then
        size0=$size1
        last_grow=0
      fi
    fi
    if [[ "$idle_sec" -gt 0 && "$last_grow" -ge "$idle_sec" ]]; then
      echo "[daemon_loop] IDLE ${idle_sec}s (log stalled: ${log_path:-none}) — killing pid $child_pid"
      kill -TERM "$child_pid" 2>/dev/null || true
      sleep 3
      kill -KILL "$child_pid" 2>/dev/null || true
      wait "$child_pid" 2>/dev/null || true
      return 124
    fi
    if [[ "$max_runtime" -gt 0 && "$elapsed" -ge "$max_runtime" ]]; then
      echo "[daemon_loop] HARD TIMEOUT ${max_runtime}s — killing pid $child_pid"
      kill -TERM "$child_pid" 2>/dev/null || true
      sleep 3
      kill -KILL "$child_pid" 2>/dev/null || true
      wait "$child_pid" 2>/dev/null || true
      return 124
    fi
  done
  wait "$child_pid"
  return $?
}

while true; do
  echo "[daemon_loop] $(date -u +%Y-%m-%dT%H:%M:%SZ) starting: $*"
  if _run_idle_aware "$@"; then
    :
  else
    echo "[daemon_loop] exit=$? — retry in ${pause}s"
  fi
  sleep "$pause"
done
