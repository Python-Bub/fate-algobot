"""Gainz-style 1m–1h signals, reconstruction sandbox, escape-then-return."""

from __future__ import annotations

import pandas as pd


def _bars(n: int = 120, drift: float = 0.03):
    import numpy as np

    rng = np.random.default_rng(3)
    idx = pd.date_range("2026-08-17 09:30", periods=n, freq="1min", tz="America/New_York")
    px = 50 + np.cumsum(rng.normal(drift, 0.08, n))
    return pd.DataFrame(
        {
            "Open": px,
            "High": px + 0.12,
            "Low": px - 0.12,
            "Close": px,
            "Volume": rng.integers(80_000, 250_000, n),
        },
        index=idx,
    )


def test_momentum_formulas():
    from analytics.gainz_v2 import momentum_threshold, pre_momentum_factor

    thr = momentum_threshold(100.0, 2.0, base=0.004)
    pre = pre_momentum_factor(100.0, 2.0, base=0.004)
    # MomentumThreshold = Base × (1 + (ATR/Price)×2) = 0.004 × (1 + 0.04)
    # PreMomentum      = Base × (1 − (ATR/Price)×0.5) = 0.004 × (1 − 0.01)
    assert abs(thr - 0.004 * (1 + 0.04)) < 1e-9
    assert abs(pre - 0.004 * (1 - 0.01)) < 1e-9
    assert thr > pre


def test_buy_has_entry_stop_target():
    from analytics.gainz_v2 import assess

    g = assess(_bars(drift=0.08), symbol="TEST")
    assert g.trend_strength == g.trend_strength  # finite
    if g.side == "buy":
        assert 0 < g.stop < g.entry < g.target
        assert g.layers_passed >= 4
        assert g.label == "BUY"
    if g.side == "sell":
        assert g.target < g.entry < g.stop


def test_setup_bias_label():
    from analytics.gainz_v2 import setup_bias

    bias, label = setup_bias(_bars(), symbol="MSFT")
    assert -1.0 <= bias <= 1.0
    assert isinstance(label, str)


def test_student_stays_in_sandbox():
    from pathlib import Path

    from self_modify.gainz_evolver import detect_escape

    src = Path("data/self_improve/gainz_student.py").read_text(encoding="utf-8")
    hits = detect_escape(src)
    assert not any(h.startswith(("import:os", "call:exec", "from:subprocess")) for h in hits)


def test_os_import_is_escape():
    from self_modify.gainz_evolver import detect_escape

    hits = detect_escape("import os\ndef student_signal(df, symbol=''):\n    return os.getcwd()\n")
    assert any("import:os" in h for h in hits)


def test_future_import_is_not_escape():
    from self_modify.gainz_evolver import detect_escape

    hits = detect_escape("from __future__ import annotations\ndef student_signal(df, symbol=''):\n    return {'side': 'none'}\n")
    assert not hits


def test_teacher_import_is_cheat_not_escape():
    from self_modify.gainz_evolver import detect_escape

    hits = detect_escape("from analytics.gainz_v2 import assess\ndef student_signal(df, symbol=''):\n    return assess(df)\n")
    assert any(h.startswith("cheat:") for h in hits)
    assert not any(h.startswith(("import:", "from:", "call:")) for h in hits if not h.startswith("cheat:"))


def test_reconstruction_score_teacher_self():
    from analytics.gainz_v2 import assess
    from self_modify.gainz_teacher import reconstruction_score

    df = _bars()

    def fn(df, symbol=""):
        g = assess(df, symbol=symbol)
        return {"side": g.side, "confidence": g.confidence}

    out = reconstruction_score(fn, df, symbol="SELF")
    assert out["score"] == 1.0


def test_evolve_once_runs(tmp_path, monkeypatch):
    from pathlib import Path
    import shutil

    import self_modify.gainz_evolver as ge

    src = Path("data/self_improve/gainz_student.py")
    student = tmp_path / "gainz_student.py"
    shutil.copy2(src, student)
    monkeypatch.setattr(ge, "STUDENT", student)
    monkeypatch.setattr(ge, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(ge, "LOG", tmp_path / "esc.jsonl")
    monkeypatch.setattr(ge, "ARCHIVE", tmp_path / "arch")
    monkeypatch.setattr(ge, "ESCAPE", tmp_path / "esc")
    out = ge.evolve_once()
    assert out.get("ok") is True
    assert "escaped" in out
    assert out.get("escaped") is False
