"""
Minimal Gymnasium env: discrete position {-1,0,1}, reward ~ position * return.
Requires: pip install gymnasium (import is deferred until env is constructed).

Optional RL_USE_ASYM_REWARD=true wires analytics.asymmetric_loss for the same
reward shape used in paper-sim online learning (5x long loss, 10x short loss).
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

_StockTradingEnvCls: type | None = None


def _use_asym_reward() -> bool:
    return os.getenv("RL_USE_ASYM_REWARD", "false").strip().lower() in ("1", "true", "yes")


def get_stock_trading_env_class() -> type:
    global _StockTradingEnvCls
    if _StockTradingEnvCls is not None:
        return _StockTradingEnvCls
    from gymnasium import Env, spaces

    class StockTradingEnv(Env):
        metadata = {"render_modes": []}

        def __init__(self, features: pd.DataFrame, ret_col: str = "returns", window: int = 1):
            super().__init__()
            self.df = features.reset_index(drop=True)
            self.ret = self.df[ret_col].values.astype(np.float64)
            drop = {"target", "target_long", "returns"}
            num = self.df.select_dtypes(include=[np.number])
            feat_cols = [c for c in num.columns if c not in drop][:20]
            if not feat_cols:
                raise ValueError("No numeric feature columns for RL env")
            self.X = self.df[feat_cols].replace([np.inf, -np.inf], 0).fillna(0).values
            self.window = window
            self.t = window
            self.pos = 0
            obs_dim = self.X.shape[1] * window + 1
            self.observation_space = spaces.Box(
                low=-np.inf, high=np.inf, shape=(obs_dim,), dtype=np.float32
            )
            self.action_space = spaces.Discrete(3)

        def _obs(self):
            w = self.X[self.t - self.window : self.t].reshape(-1)
            return np.concatenate([w, [float(self.pos)]]).astype(np.float32)

        def reset(self, *, seed=None, options=None):
            super().reset(seed=seed)
            self.t = self.window
            self.pos = 0
            return self._obs(), {}

        def step(self, action):
            prev_pos = int(self.pos)
            new_pos = int(action) - 1
            bar_ret = float(self.ret[self.t])
            # PnL over this bar if we held *prev* position into the return
            linear = bar_ret * float(prev_pos)

            if _use_asym_reward():
                if prev_pos == 0:
                    switch = 1 if new_pos != prev_pos else 0
                    r = -float(os.getenv("RL_ACTION_SWITCH_FRICTION", "0.0001")) * switch
                else:
                    from analytics.asymmetric_loss import asymmetric_reward

                    side = "LONG" if prev_pos > 0 else "SHORT"
                    realized = linear  # long: +ret; short: -ret when price drops is +linear
                    rw = asymmetric_reward(side, realized, bars_held=1)
                    r = float(rw.reward)
                    if new_pos != prev_pos:
                        r -= float(os.getenv("RL_ACTION_SWITCH_FRICTION", "0.0001"))
            else:
                # Legacy: reward uses *new* position (preserved for backward compatibility)
                self.pos = new_pos
                r = float(bar_ret * float(self.pos))
                self.t += 1
                terminated = self.t >= len(self.ret) - 1
                return self._obs(), r, terminated, False, {}

            self.pos = new_pos
            self.t += 1
            terminated = self.t >= len(self.ret) - 1
            return self._obs(), float(r), terminated, False, {}

    _StockTradingEnvCls = StockTradingEnv
    return StockTradingEnv
