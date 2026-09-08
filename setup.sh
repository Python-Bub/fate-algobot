#!/usr/bin/env bash
set -eux

# 1) Create & activate virtualenv
if [ ! -d venv ]; then
  python3 -m venv venv
fi
source venv/bin/activate

# 2) Upgrade pip & install dependencies
pip install --upgrade pip
pip install \
  alpaca-trade-api \
  pandas \
  numpy \
  scikit-learn \
  xgboost \
  lightgbm \
  python-dotenv \
  ta \
  tqdm \
  optuna \
  joblib

# 3) Copy .env if missing
if [ ! -f .env ] && [ -f .env.template ]; then
  cp .env.template .env
  echo "🔑 Created .env – fill in your Alpaca keys."
fi

# 4) Ensure models directory exists
mkdir -p models

echo "✅ Setup complete. Use ./run.sh to train, optimize, backtest, or trade live."
