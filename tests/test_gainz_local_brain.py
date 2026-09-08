def test_gainz_brain_trains_and_predicts(tmp_path, monkeypatch):
    import analytics.gainz_local_brain as b
    from self_modify.gainz_evolver import _sample_bars

    monkeypatch.setattr(b, "CKPT", tmp_path / "gainz_brain.pt")
    monkeypatch.setattr(b, "META", tmp_path / "gainz_brain.json")
    out = b.train_steps(6)
    assert out.get("ok") is True
    assert out.get("steps", 0) >= 6
    df = _sample_bars(seed=3, drift=0.12)
    assert b.features(df).shape[0] == 12
    pred = b.predict(df)
    assert pred.get("side") in ("none", "buy", "sell")
    assert pred.get("ok") is True
