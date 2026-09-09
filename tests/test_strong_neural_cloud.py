"""Stronger neural defaults + autonomous cloud historical train (no coverage cuts)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_lstm_defaults_are_stronger_and_legacy_arch_still_loads():
    src = (ROOT / "analytics/lstm_head.py").read_text(encoding="utf-8")
    assert 'LSTM_HIDDEN", "128"' in src
    assert 'LSTM_LAYERS", "3"' in src
    assert 'LSTM_SEQ_LEN", "60"' in src
    assert 'LSTM_EPOCHS", "20"' in src
    assert "LSTM_EARLY_STOP_PATIENCE" in src
    assert "best_state" in src
    assert 'bundle.get("hidden") or 64' in src
    assert 'bundle.get("num_layers") or 2' in src


def test_daily_train_default_history_is_2010():
    src = (ROOT / "model_trainer.py").read_text(encoding="utf-8")
    assert 'TRAIN_DATA_START", "2010-01-01"' in src
    assert 'TRAIN_DATA_START", "2023-01-01"' not in src


def test_neural_ensemble_trains_more_and_stores_arch():
    src = (ROOT / "online_learning/neural_ensemble.py").read_text(encoding="utf-8")
    assert 'NEURAL_EPOCHS", 12' in src
    assert 'NEURAL_SEQ_LEN", 48' in src
    assert "def _train_arch" in src
    assert 'NEURAL_LSTM_HIDDEN", 128' in src
    assert "def _make_head" in src


def test_hist_cook_expands_years_and_trains_lstm():
    src = (ROOT / "tools/hist_cook.py").read_text(encoding="utf-8")
    assert 'HIST_COOK_YEARS", "16"' in src
    assert 'HIST_COOK_MAX_SYMBOLS", "400"' in src
    assert "def _cook_symbols" in src
    assert "def _train_hist_lstm" in src
    assert "load_universe_symbols" in src


def test_cloud_train_is_autonomous_and_does_not_order():
    run = (ROOT / "run_all.sh").read_text(encoding="utf-8")
    cloud = run.split("cmd_cloud_train()")[1].split("ensure_hft_built()")[0]
    assert "cmd_train_everything" in cloud
    assert "cmd_train_lstm" in cloud
    assert "cmd_launch_hist_cook" in cloud
    assert "cmd_launch_enhancement_queue" in cloud
    assert "launch_subsecond" not in cloud
    assert "cmd_refresh_paper" not in cloud
    assert "fortress_live" not in cloud
    assert "SKIP_PAPER_AUTO_TRAIN=true" in cloud
    assert "LSTM_TRAIN_SCOPE" in cloud and "all" in cloud
    setup = (ROOT / "cloud/gcp_remote_setup.sh").read_text(encoding="utf-8")
    assert "cloud-train" in setup
    after_tmux = setup.split("tmux new-session", 1)[-1]
    assert "cloud-train" in after_tmux
    assert "train-everything" not in after_tmux
    boot = (ROOT / "cloud/gcp_bootstrap.sh").read_text(encoding="utf-8")
    assert "push-train" in boot
    assert "400" in boot
    svc = (ROOT / "cloud/fate-algobot-train.service").read_text(encoding="utf-8")
    assert "cloud-train" in svc
    assert "run_all.sh paper" not in svc


def test_last_wins_strong_neural():
    text = (ROOT / "data/deploy_scale.env").read_text(encoding="utf-8")
    last = text.rsplit("stronger neural + historical cloud train", 1)[-1]
    assert "TRAIN_DATA_START=2010-01-01" in last
    assert "LSTM_HIDDEN=128" in last
    assert "LSTM_LAYERS=3" in last
    assert "NEURAL_EPOCHS=12" in last
    assert "HIST_COOK_YEARS=16" in last
    assert "HIST_COOK_TRAIN_LSTM=true" in last


def test_lstm_roundtrip_saves_best_and_arch(tmp_path, monkeypatch):
    import numpy as np
    import pandas as pd

    monkeypatch.setenv("USE_LSTM_HEAD", "true")
    monkeypatch.setenv("LSTM_HIDDEN", "32")
    monkeypatch.setenv("LSTM_LAYERS", "2")
    monkeypatch.setenv("LSTM_SEQ_LEN", "8")
    monkeypatch.setenv("LSTM_EPOCHS", "3")
    monkeypatch.setenv("LSTM_EARLY_STOP_PATIENCE", "5")
    monkeypatch.setenv("LSTM_MIN_ROWS_OVER_SEQ", "5")
    monkeypatch.setenv("LSTM_MIN_SEQUENCES", "8")
    monkeypatch.setenv("LSTM_BATCH", "16")
    monkeypatch.setenv("LSTM_CUDA", "false")

    from analytics import lstm_head as lh

    if not lh._TORCH_OK:
        return
    monkeypatch.setattr(lh, "MODEL_DIR", tmp_path)
    rng = np.random.RandomState(0)
    n = 80
    cols = ["f1", "f2", "f3", "f4"]
    df = pd.DataFrame({c: rng.normal(size=n) for c in cols})
    df["target_long"] = (df["f1"] + rng.normal(scale=0.2, size=n) > 0).astype(np.float32)
    out = lh.train_lstm_head("ZZZTEST", df, cols, force=True)
    assert "saved" in out
    assert out.get("hidden") == 32
    assert out.get("num_layers") == 2
    p = lh.lstm_proba_up("ZZZTEST", df)
    assert p is not None
    assert 0.0 <= float(p) <= 1.0
    bundle = lh._load_bundle("ZZZTEST")
    assert int(bundle["hidden"]) == 32
    assert "test_acc" in bundle
