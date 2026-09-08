from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
UNIVERSE_DIR = DATA / "universe"

TOP100_PATH = DATA / "top100_market_cap.json"
TOP50_PATH = DATA / "top50pct_market_cap.json"
CAP_CACHE_PATH = UNIVERSE_DIR / "market_cap_cache.json"
CORPORATE_ACTIONS_PATH = UNIVERSE_DIR / "corporate_actions.json"
SNAPSHOT_PATH = UNIVERSE_DIR / "universe_snapshot.json"
STATE_PATH = DATA / "universe_lifecycle_state.json"
TRAIN_QUEUE_PATH = DATA / "universe_lifecycle_train_queue.json"
