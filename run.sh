#!/bin/bash

echo "💻 FATE_AlgoBot: Runtime Launcher"

MODE=$1
ARG=$2

if [ "$MODE" == "all" ]; then
    echo "🚀 Running full pipeline for all tickers..."
    python3 FATE_AlgoBot.py train
    for t in AAPL TSLA NVDA AMZN MSFT COIN AMD META GOOGL; do
        python3 FATE_AlgoBot.py optimize $t
        python3 FATE_AlgoBot.py backtest $t
    done

elif [ "$MODE" == "live" ] && [ "$ARG" == "all" ]; then
    echo "📡 Launching parallel live tickers..."
    python3 dispatcher.py

elif [ "$MODE" == "live" ]; then
    echo "📡 Starting single live ticker: $ARG"
    python3 live_listener.py "$ARG"

elif [ "$MODE" == "meta" ]; then
    echo "🧪 Feature analysis..."
    python3 FATE_AlgoBot.py meta

else
    echo "❌ Unknown mode: $MODE"
    echo "Usage:"
    echo "  ./run.sh all"
    echo "  ./run.sh live all"
    echo "  ./run.sh live TICKER"
    echo "  ./run.sh meta"
fi
