#!/usr/bin/env bash
#
# Paper simulation (no real orders). Uses config.TRAIN_TICKERS, lower min_conf,
# shorts + ETFs enabled to produce lots of picks.
#
#   ./run_paper_sim.sh                # default
#   ./run_paper_sim.sh --max-symbols 30
#
set -euo pipefail
cd "$(dirname "$0")"

export PAPER_SIM_CONFIG_TICKERS_ONLY=${PAPER_SIM_CONFIG_TICKERS_ONLY:-true}
export PAPER_SIM_MODE=${PAPER_SIM_MODE:-top_k}
export PAPER_SIM_TOP_K=${PAPER_SIM_TOP_K:-20}
export PAPER_SIM_MIN_CONF=${PAPER_SIM_MIN_CONF:-0.55}
export PAPER_SIM_ALLOW_SHORTS=${PAPER_SIM_ALLOW_SHORTS:-true}
export PAPER_SIM_SHORT_TOP_K=${PAPER_SIM_SHORT_TOP_K:-10}
export PAPER_SIM_USE_NOTIONAL=${PAPER_SIM_USE_NOTIONAL:-true}
export ORDER_NOTIONAL=${ORDER_NOTIONAL:-500}
export HEAVY_NEWS_INTEL=${HEAVY_NEWS_INTEL:-true}
export USE_CRAMER_SIGNAL=${USE_CRAMER_SIGNAL:-true}
export USE_SOCIAL_SENTIMENT=${USE_SOCIAL_SENTIMENT:-true}

mkdir -p logs reports
LOG="logs/paper_sim_$(date +%Y%m%d_%H%M%S).log"

./venv/bin/python -m paper_sim_today 2>&1 | tee "$LOG"
echo "Log: $LOG"
