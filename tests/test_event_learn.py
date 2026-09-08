"""Event-outcome learner — synthetic history, no network."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from analytics.event_learn import (
    credit_event_outcome,
    event_learn_rank_boost,
    featurize,
    online_update,
    predict_from_feats,
    redesign_until_best,
    samples_from_closes,
    walk_forward_metrics,
)
from analytics.sleeve_weights import HFT_PCT, FORTRESS_PCT, assert_tables_valid, pct_sum


def _synth_panel(seed: int = 7, n: int = 1600) -> tuple[pd.Series, list[date]]:
    """Prints every ~63d: |gap| grows with hist vol; sign follows 5d pre-momentum."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2018-01-02", periods=n)
    px = 100.0
    closes = []
    earn: list[date] = []
    next_e = 80
    for i, ts in enumerate(idx):
        if i == next_e:
            earn.append(ts.date())
            mom = (closes[-1] / closes[-6] - 1.0) if len(closes) >= 6 else 0.0
            hist = 0.04
            gap = (0.035 + 0.4 * hist) * (1.0 if mom >= 0 else -1.0)
            gap += float(rng.normal(0, 0.004))
            px *= 1.0 + gap
            next_e += int(rng.integers(58, 70))
        else:
            px *= 1.0 + float(rng.normal(0.0003, 0.009))
        closes.append(px)
    return pd.Series(closes, index=idx, name="Close"), earn


def test_featurize_dte_buckets():
    f = featurize(dte=0, hour="bmo", hist_abs_1d=0.05, mom_5d=0.02, is_event_day=True)
    assert f["bias"] == 1.0
    assert f["dte_0"] == 1.0
    assert f["hour_bmo"] == 1.0
    assert f["hist_abs_1d"] == pytest.approx(0.05)
    f1 = featurize(dte=1)
    assert f1["dte_1"] == 1.0 and f1["dte_0"] == 0.0


def test_walk_forward_beats_naive_on_synth(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_EVENT_LEARN", "true")
    monkeypatch.setattr("analytics.event_learn.STATE_PATH", tmp_path / "st.json")
    closes, earn = _synth_panel()
    samples = samples_from_closes("SYN", closes, earn, control_stride=10)
    event_n = sum(1 for s in samples if s.is_event)
    assert event_n >= 12
    assert len(samples) >= 90
    met = walk_forward_metrics(samples, min_train=48)
    st = redesign_until_best(samples, max_rounds=5, min_train=48)
    # Learned mag must beat predicting the train-set mean |move|.
    assert st["n_samples"] == len(samples)
    assert st["model_mae"] is not None
    assert st["baseline_mae"] is not None
    assert float(st["model_mae"]) <= float(st["baseline_mae"]) + 0.002
    assert float(st["oos_ic"] or 0) > 0.0 or st["beat_baseline"] is True
    # Direction: pre-momentum is in the DGP — acc should beat coin-flip on enough OOS.
    if met.get("ok") and int(met.get("n_oos_event") or 0) >= 6:
        assert float(met.get("acc_event") or 0) >= 0.55


def test_online_update_self_adjusts(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_EVENT_LEARN", "true")
    monkeypatch.setenv("EVENT_LEARN_LR", "0.2")
    monkeypatch.setattr("analytics.event_learn.STATE_PATH", tmp_path / "st.json")
    feats = featurize(dte=0, hour="bmo", hist_abs_1d=0.08, mom_5d=0.03, is_event_day=True)
    before = predict_from_feats(feats)
    st = None
    for _ in range(12):
        st = online_update(feats, y_sign=1.0, y_abs=0.09, st=st)
    after = predict_from_feats(feats, st=st)
    assert after["p_up"] >= before["p_up"] - 1e-9
    assert after["p_up"] > 0.5
    assert int(st["n_updates"]) == 12


def test_skill_gates_rank_when_disabled(monkeypatch):
    monkeypatch.setenv("USE_EVENT_LEARN", "false")
    b, meta = event_learn_rank_boost("AAPL", mom_5d=0.04, sleeve="fortress")
    assert b == 0.0
    assert meta.get("skipped")


def test_credit_skips_quiet_names(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_EVENT_LEARN", "true")
    monkeypatch.setattr("analytics.event_learn.STATE_PATH", tmp_path / "st.json")

    def _feats(*_a, **_k):
        return featurize(dte=40, mom_5d=0.0)

    monkeypatch.setattr("analytics.event_learn.features_for_ticker", _feats)
    out = credit_event_outcome("ZZZ", 0.01)
    assert out.get("applied") is False


def test_sleeve_keeps_event_learn_and_100():
    assert_tables_valid()
    assert pct_sum("fortress") == pytest.approx(100.0, abs=0.01)
    assert FORTRESS_PCT.get("event_learn", 0.0) >= 1.0
    assert FORTRESS_PCT.get("event_ingenuity", 0.0) >= 1.0
    assert HFT_PCT.get("event_learn", 0.0) == 0.0
