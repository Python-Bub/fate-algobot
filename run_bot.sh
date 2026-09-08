#!/bin/bash
echo "📦 Activating virtual environment..."
source venv/bin/activate

echo "🚀 Launching DemirBot Multi-Ticker Edition..."
python live_realtime_multi.py
