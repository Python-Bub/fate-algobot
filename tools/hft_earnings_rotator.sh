#!/usr/bin/env bash
# HFT engine supervisor: OBI + earnings.
# Default HFT_COEXIST=true — both run; earnings uses REST news/quotes (no Alpaca WS).
# Legacy multiplex: HFT_COEXIST=false → time-swap in earnings window.
set -u
# Do not use pipefail/-e — a failed pgrep or python probe must not kill the supervisor.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOGDIR="$ROOT/logs"
mkdir -p "$LOGDIR"
# shellcheck disable=SC1091
[ -f .env ] && set -a && . ./.env && set +a
[ -f data/deploy_scale.env ] && set -a && . ./data/deploy_scale.env && set +a

export TZ="${HFT_ROTATOR_TZ:-America/New_York}"
POLL="${HFT_ROTATOR_POLL_SEC:-120}"
START_H="${EARNINGS_WINDOW_START_HOUR:-6}"
END_H="${EARNINGS_WINDOW_END_HOUR:-10}"
MODE="${HFT_ROTATOR_MODE:-auto}"  # auto | earnings | obi | both
COEXIST="${HFT_COEXIST:-true}"

log() { echo "[hft-rotator $(date '+%Y-%m-%d %H:%M:%S %Z')] $*"; }
trap 'log "exiting status=$? line=$LINENO"' EXIT

is_weekday() {
  local dow
  dow="$(date +%u)"
  [ "$dow" -le 5 ]
}

in_earnings_window() {
  local dow h
  dow="$(date +%u)"
  h="$(date +%H | sed 's/^0//')"
  [ -z "$h" ] && h=0
  [ "$dow" -ge 6 ] && return 1
  [ "$h" -ge "$START_H" ] && [ "$h" -lt "$END_H" ]
}

want_earnings() {
  case "$MODE" in
    earnings|both) return 0 ;;
    obi) return 1 ;;
    *) in_earnings_window ;;
  esac
}

coexist_on() {
  case "${COEXIST}" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

hft_orders_open() {
  "$ROOT/venv/bin/python" -c "from analytics.market_session import orders_allowed; import sys; sys.exit(0 if orders_allowed('any', for_hft=True)[0] else 1)" 2>/dev/null
}

run_24x5() {
  case "${HFT_RUN_24X5:-true}" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

ensure_both() {
  # Fast path: both Node processes alive — do not shell out to run_all.sh
  # (old pgrep used hft/dist/earnings which never matched cwd-relative argv,
  # so this loop spawned a new earnings every POLL and looked like crashes).
  if pgrep -f "obi-tape/index.js" >/dev/null 2>&1 \
     && pgrep -f "earnings/index.js" >/dev/null 2>&1; then
    return 0
  fi
  "$ROOT/run_all.sh" swap-hft both >>"$LOGDIR/hft-rotator_latest.log" 2>&1 || true
}

log "rotator started  MODE=$MODE  COEXIST=$COEXIST  earnings ${START_H}:00–${END_H}:00 ET  HFT_RUN_24X5=${HFT_RUN_24X5:-true}"

while true; do
  if ! is_weekday; then
    log "weekend — stopping HFT engines"
    "$ROOT/run_all.sh" stop-hft-engines >>"$LOGDIR/hft-rotator_latest.log" 2>&1 || true
    sleep "$POLL"
    continue
  fi

  if run_24x5; then
    if ! hft_orders_open; then
      log "weekday scan-only until ${HFT_TRADE_START_ET:-04:00} ET (engines stay up 24/5 Mon–Fri)"
    fi
  elif ! hft_orders_open; then
    log "outside HFT order window — engines idle"
    "$ROOT/run_all.sh" stop-hft-engines >>"$LOGDIR/hft-rotator_latest.log" 2>&1 || true
    sleep "$POLL"
    continue
  fi

  if coexist_on || [ "$MODE" = "both" ]; then
    ensure_both
  elif want_earnings; then
    "$ROOT/run_all.sh" swap-hft earnings >>"$LOGDIR/hft-rotator_latest.log" 2>&1 || true
  else
    "$ROOT/run_all.sh" swap-hft obi >>"$LOGDIR/hft-rotator_latest.log" 2>&1 || true
  fi
  sleep "$POLL"
done
