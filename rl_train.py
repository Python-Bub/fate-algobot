"""Train PPO on StockTradingEnv (optional stable-baselines3)."""

from __future__ import annotations

import os

from feature_engineering import build_features
from rl_trading_env import get_stock_trading_env_class
from utils import log


def train_rl(ticker: str = "AAPL", start: str = "2018-01-01", timesteps: int = 50_000) -> str | None:
    try:
        from stable_baselines3 import PPO
    except ImportError:
        log.error("[RL] pip install stable-baselines3 gymnasium shimmy")
        return None

    df = build_features(ticker, start, None)
    if df.empty:
        return None
    try:
        Env = get_stock_trading_env_class()
    except ImportError:
        log.error("[RL] pip install gymnasium stable-baselines3")
        return None
    env = Env(df)
    model = PPO("MlpPolicy", env, verbose=0)
    model.learn(total_timesteps=int(os.getenv("RL_TIMESTEPS", str(timesteps))))
    path = os.path.join("models", f"{ticker}_ppo.zip")
    model.save(path)
    log.info("[RL] Saved %s", path)
    return path


if __name__ == "__main__":
    train_rl()
