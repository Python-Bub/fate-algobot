#!/usr/bin/env bash
#
# REAL paper-trade route: connects to Alpaca paper account and sends actual orders.
# Requires `.env` to contain:
#   BROKER=alpaca
#   ALPACA_API_KEY=...
#   ALPACA_SECRET_KEY=...
#   ALPACA_BASE_URL=https://paper-api.alpaca.markets
#
# This forces USE_REAL_MONEY=true (paper API only — no real cash). Trades route via
# fortress_live, with Cramer + StockTwits boosts and heavy intel weighting.
#
#   ./run_alpaca_paper_live.sh                 # default 50 symbols
#   MAX_LIVE_SYMBOLS=120 ./run_alpaca_paper_live.sh
#
set -euo pipefail
cd "$(dirname "$0")"

export BROKER=alpaca
export USE_REAL_MONEY=true
export ALPACA_BASE_URL=${ALPACA_BASE_URL:-https://paper-api.alpaca.markets}
# Lower the confidence floor so trades actually happen (still ranks by score).
export MIN_MODEL_CONFIDENCE=${MIN_MODEL_CONFIDENCE:-0.55}
export HEAVY_NEWS_INTEL=${HEAVY_NEWS_INTEL:-true}
export USE_CRAMER_SIGNAL=${USE_CRAMER_SIGNAL:-true}
export USE_SOCIAL_SENTIMENT=${USE_SOCIAL_SENTIMENT:-true}
# Use config.TRAIN_TICKERS instead of full 11k US universe; comma-list overrides everything.
export LIVE_SYMBOL_LIST=${LIVE_SYMBOL_LIST:-"AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AMD,COIN,AVGO,SPY,QQQ,IWM,SOXL,SQQQ,TQQQ,XOM,JPM,BAC,WMT,COST,SHOP,UBER,CRWD,PLTR,SNOW"}
export MAX_LIVE_SYMBOLS=${MAX_LIVE_SYMBOLS:-50}
export ORDER_NOTIONAL=${ORDER_NOTIONAL:-500}

mkdir -p logs
LOG="logs/alpaca_paper_$(date +%Y%m%d_%H%M%S).log"

./venv/bin/python -u fortress_live.py --max-symbols "$MAX_LIVE_SYMBOLS" --shuffle 2>&1 | tee "$LOG"
echo "Log: $LOG"
