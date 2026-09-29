#!/usr/bin/env bash

# 1️⃣ Navigate to project directory
cd "$(dirname "$0")"

# 2️⃣ Activate virtual environment
source venv/bin/activate

# 3️⃣ Ensure requirements are installed
pip install -r requirements.txt

# 4️⃣ Start the live realtime simulator (multi-symbol; the single-symbol
#     live_realtime.py was folded into live_realtime_multi.py)
python live_realtime_multi.py "$@"
