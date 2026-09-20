"""Environment bundle for maximum-quality training (no FAST_MODE / no placeholder skips)."""
from __future__ import annotations

import os


def proper_finish_enabled() -> bool:
    return os.getenv("TRAIN_PROPER_FINISH", "false").lower() in ("1", "true", "yes")


def max_quality_env(extra: dict | None = None) -> dict[str, str]:
    """Merge into subprocess env for trainers and enhancement queue phases."""
    e = {
        "TRAIN_PROPER_FINISH": "true",
        "ENHANCE_FINISH_MODE": "full",
        "FAST_MODE": "false",
        "FAST_UNIVERSE_TRAIN": "false",
        "USE_TRAIN_NEWS_HISTORY": "true",
        "HEAVY_NEWS_INTEL": "true",
        "USE_AI_TRAINING_GRADER": "true",
        "USE_CLASSIC_QUANT_FEATURES": "true",
        "MULTI_HORIZON_TRAIN": "true",
        "TRAIN_TIME_ORDER_SPLIT": "true",
        "TRAIN_FORCE_YAHOO": "true",
        "INTRADAY_GAP_SKIP_CACHED_PLACEHOLDER": "false",
        "INTRADAY_LOOKBACK_DAYS": os.getenv("PROPER_INTRADAY_LOOKBACK", "365"),
        "INTRADAY_GAP_WORKERS": os.getenv("PROPER_INTRADAY_WORKERS", "6"),
        "ENHANCE_DAILY_WORKERS": os.getenv("PROPER_DAILY_WORKERS", "6"),
        "ENHANCE_LSTM_WORKERS": os.getenv("PROPER_LSTM_WORKERS", "6"),
        "ENHANCE_LSTM_EPOCHS": os.getenv("PROPER_LSTM_EPOCHS", "24"),
        "LSTM_EPOCHS": os.getenv("PROPER_LSTM_EPOCHS", "24"),
        "LSTM_HIDDEN": os.getenv("LSTM_HIDDEN", "256"),
        "LSTM_LAYERS": os.getenv("LSTM_LAYERS", "4"),
        "LSTM_SEQ_LEN": os.getenv("LSTM_SEQ_LEN", "80"),
        "LSTM_EARLY_STOP_PATIENCE": os.getenv("LSTM_EARLY_STOP_PATIENCE", "6"),
        "TRAIN_DATA_START": os.getenv("TRAIN_DATA_START", "2010-01-01"),
        "STRONG_TRAIN_DATA_START": os.getenv("STRONG_TRAIN_DATA_START", "2010-01-01"),
        "TOP100_LSTM_EPOCHS": os.getenv("PROPER_TOP100_LSTM_EPOCHS", "28"),
        "TOP100_NEURAL_EPOCHS": os.getenv("PROPER_TOP100_NEURAL_EPOCHS", "24"),
        "NEURAL_EPOCHS": os.getenv("NEURAL_EPOCHS", "24"),
        "NEURAL_SEQ_LEN": os.getenv("NEURAL_SEQ_LEN", "64"),
        "TOP100_INTRADAY_LOOKBACK": os.getenv("PROPER_INTRADAY_LOOKBACK", "365"),
        "USE_FOUNDATION_FORECAST": "true",
        "USE_LSTM_HEAD": "true",
        "BLEND_LSTM_INTO_META": "true",
        "SAVE_REPLAY_FEATURES": "false",
        "INTRADAY_USE_CACHE": "false",
        "USE_PRICE_CACHE": os.getenv("USE_PRICE_CACHE", "true"),
        "USE_REPLAY_RAW_FIRST": "false",
        "DATA_SYNC_SAVE_RAW": "false",
        "INTRADAY_SKIP_PLACEHOLDER_DISK": "true",
        "NETWORK_FIRST": "true",
        # Keep multi-TF heads filled; quality loops can still raise them later.
        "KEEP_WEAK_HEADS": os.getenv("KEEP_WEAK_HEADS", "true"),
        "FILL_NULL_HEADS": os.getenv("FILL_NULL_HEADS", "true"),
        "COALESCE_EXISTING_HEADS": "true",
        "USE_MULTI_TF_META": "true",
        "USE_MULTI_TF_BLEND": "true",
        "PRICE_CACHE_MAX_START_GAP_DAYS": os.getenv("PRICE_CACHE_MAX_START_GAP_DAYS", "400"),
        "PRICE_CACHE_MIN_MULTI_HORIZON": os.getenv("PRICE_CACHE_MIN_MULTI_HORIZON", "400"),
        # Drop weak horizon heads + meta that hurt ranking at inference.
        "MIN_HEAD_TOP20": os.getenv("MIN_HEAD_TOP20", "0.48"),
        "RETRAIN_MIN_TOP20": os.getenv("RETRAIN_MIN_TOP20", "0.6"),
        "AUTO_RETRAIN_LOW_TOP20": os.getenv("AUTO_RETRAIN_LOW_TOP20", "true"),
        "MIN_META_AUC": os.getenv("MIN_META_AUC", "0.52"),
        "HORIZON_USE_ENSEMBLE": "true",
        "LONG_OVERFIT_TRAIN_TEST_GAP": os.getenv("LONG_OVERFIT_TRAIN_TEST_GAP", "0.30"),
        # 0 = no per-ticker kill (quality passes for top100/retrain can take many minutes).
        "TRAIN_TICKER_TIMEOUT_SEC": os.getenv("PROPER_TRAIN_TIMEOUT_SEC", "0"),
        "PRICE_FETCH_BLOCK": os.getenv("PRICE_FETCH_BLOCK", "true"),
        "TOP100_DAILY_WORKERS": os.getenv("PROPER_TOP100_DAILY_WORKERS", "2"),
    }
    if extra:
        e.update({k: str(v) for k, v in extra.items()})
    return e
