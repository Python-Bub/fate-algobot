#!/usr/bin/env bash
#
# Walk-forward validation: rolling chronological train/test splits.
# Validates that the model generalises through time, not just on the static holdout.
#
#   ./run_walk_forward.sh                           # AAPL default
#   ./run_walk_forward.sh AAPL,NVDA,SPY,QQQ,AMD     # comma list
#
set -euo pipefail
cd "$(dirname "$0")"

TICKERS="${1:-AAPL,NVDA,SPY,QQQ}"
START="${WF_START:-2019-01-01}"
SPLITS="${WF_SPLITS:-6}"

IFS=',' read -r -a syms <<< "$TICKERS"
for t in "${syms[@]}"; do
    echo "=== walk-forward $t ==="
    ./venv/bin/python walk_forward.py --ticker "$t" --start "$START" --splits "$SPLITS"
done
