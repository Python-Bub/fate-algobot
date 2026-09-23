"""Tests for hidden pattern anomaly detection."""

from __future__ import annotations

import numpy as np

from analytics.hidden_pattern_anomaly import (
    AnomalyHit,
    analyze_symbol,
    hidden_anomaly_rank_boost,
    save_hits,
)


def test_analyze_synthetic_spike(tmp_path, monkeypatch):
    # Synthetic scenario: neutralize the live bot's learned per-family multipliers
    # (data/intel/hidden_pattern_weights.json) and the auto-generated cross-symbol
    # detectors (which fetch peer bars) so this checks the detectors, not live state.
    monkeypatch.setattr("analytics.hidden_pattern_learn.load_detector_weights", lambda: {})
    monkeypatch.setenv("USE_GENERATED_PATTERNS", "false")
    monkeypatch.setenv("HIDDEN_ANOMALY_MIN_SCORE", "0.42")
    # Quiet series then a huge idiosyncratic jump → residual / iforest should fire
    rng = np.random.default_rng(0)
    closes = 100 + np.cumsum(rng.normal(0, 0.3, 120))
    closes[-1] = closes[-2] * 1.08  # 8% pop
    import pandas as pd

    df = pd.DataFrame(
        {
            "Open": closes,
            "High": closes * 1.01,
            "Low": closes * 0.99,
            "Close": closes,
            "Volume": rng.integers(1_000_000, 2_000_000, size=len(closes)),
        }
    )
    mkt = np.diff(closes[:-1]) / np.maximum(closes[:-2], 1e-12)
    # pad market to match rets length after analyze uses closes
    hit = analyze_symbol("TEST", df=df, market_rets=None)
    assert hit is None or isinstance(hit, AnomalyHit)
    # Force volume divergence path with quiet volume + big move
    df2 = df.copy()
    df2["Volume"] = 1000.0
    df2.loc[df2.index[-1], "Volume"] = 1000.0
    hit2 = analyze_symbol("TEST2", df=df2, market_rets=None)
    assert hit2 is not None
    assert hit2.score >= 0.35


def test_rank_boost_from_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_HIDDEN_PATTERN_ANOMALY", "true")
    monkeypatch.setenv("RANK_W_HIDDEN_ANOMALY", "0.10")
    hits = [
        AnomalyHit("AAA", 0.8, 1, ["idio_z=3.1"], {"last_ret": 0.02}),
        AnomalyHit("BBB", 0.7, -1, ["vol_regime"], {}),
    ]
    path = tmp_path / "anoms.json"
    save_hits(hits, path=path)
    monkeypatch.setattr(
        "analytics.hidden_pattern_anomaly.OUT_PATH",
        path,
    )
    b, meta = hidden_anomaly_rank_boost("AAA")
    assert b > 0
    assert meta.get("hit") is True
    b2, meta2 = hidden_anomaly_rank_boost("BBB")
    assert b2 < 0
    assert meta2.get("direction") == -1


def test_p_blend_and_learn(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_HIDDEN_PATTERN_ANOMALY", "true")
    monkeypatch.setenv("HIDDEN_ANOMALY_P_BLEND", "0.10")
    monkeypatch.setenv("HIDDEN_ANOMALY_LEARN", "true")
    monkeypatch.setenv("HIDDEN_ANOMALY_MAX_AGE_SEC", "99999")
    hits = [AnomalyHit("ZZZ", 0.9, 1, ["idio_z=3.0", "motif sim=0.9"], {"det_0_idio": 1.0, "det_1_motif": 1.0})]
    path = tmp_path / "anoms.json"
    save_hits(hits, path=path)
    monkeypatch.setattr("analytics.hidden_pattern_anomaly.OUT_PATH", path)
    from analytics.hidden_pattern_learn import (
        WEIGHTS_PATH,
        ENTRY_SNAP_PATH,
        hidden_pattern_p_blend,
        learn_from_trade_outcome,
        snapshot_entry_pattern,
    )

    wpath = tmp_path / "weights.json"
    spath = tmp_path / "snaps.json"
    monkeypatch.setattr("analytics.hidden_pattern_learn.WEIGHTS_PATH", wpath)
    monkeypatch.setattr("analytics.hidden_pattern_learn.ENTRY_SNAP_PATH", spath)

    p_new, meta = hidden_pattern_p_blend("ZZZ", 0.55)
    assert meta.get("applied") is True
    assert p_new > 0.55  # bullish pattern should lift p_up

    snapshot_entry_pattern("ZZZ", side="LONG")
    res = learn_from_trade_outcome("ZZZ", "LONG", 0.02)
    assert res.get("applied") is True
    assert res.get("success") is True
    assert "idio" in (res.get("families") or []) or "motif" in (res.get("families") or [])
