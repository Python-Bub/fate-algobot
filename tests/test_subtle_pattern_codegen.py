"""Tests for subtle-tie discover + generated pattern codegen."""

from __future__ import annotations

import numpy as np

from analytics.pattern_code_evolver import _render_detector, _validate_source, write_detector_module
from analytics.subtle_tie_discover import SubtleTie, _is_banned, _score_pair


def test_bans_well_known_pairs():
    assert _is_banned("KO", "PEP")
    assert _is_banned("V", "MA")
    assert not _is_banned("CAT", "NKE")


def test_render_and_validate_detector(tmp_path, monkeypatch):
    tie = SubtleTie(
        a="CAT",
        b="NKE",
        kind="resid_leadlag",
        lag=2,
        score=0.55,
        direction_a=1,
        direction_b=1,
        stats={"lead_corr": 0.41},
        rationale="subtle idio lead: CAT leads NKE by 2d",
    )
    src = _render_detector(tie)
    _validate_source(src)
    assert "DETECTOR_ID" in src
    assert "def detect(ctx)" in src
    assert "gen:resid_leadlag" in src or "KIND" in src

    # Write into temp generated_patterns dir
    import analytics.generated_patterns as gp
    import analytics.pattern_code_evolver as pce

    monkeypatch.setattr(pce, "GEN_DIR", tmp_path)
    monkeypatch.setattr(pce, "ARCHIVE", tmp_path / "archive")
    monkeypatch.setattr(gp, "DIR", tmp_path)
    monkeypatch.setattr(gp, "REGISTRY", tmp_path / "_registry.json")
    monkeypatch.setattr(gp, "ARCHIVE", tmp_path / "archive")

    path = write_detector_module(tie)
    assert path is not None and path.is_file()
    mods = gp.load_generated_detectors(force=True)
    assert any(getattr(m, "DETECTOR_ID", "").startswith("gen_") for m in mods)


def test_score_pair_finds_synthetic_lead():
    rng = np.random.default_rng(0)
    n = 200
    mkt = rng.normal(0, 0.01, n)
    # B follows A's idiosyncratic move by 2 days
    idio_a = rng.normal(0, 0.015, n)
    idio_b = np.zeros(n)
    idio_b[2:] = 0.7 * idio_a[:-2] + rng.normal(0, 0.005, n - 2)
    ra = mkt + idio_a
    rb = mkt + idio_b
    va = rng.normal(0, 0.2, n)
    vb = rng.normal(0, 0.2, n)
    ties = _score_pair("AAA", "BBB", ra, rb, va, vb, mkt)
    kinds = {t.kind for t in ties}
    # Should surface some residual lead or shared structure
    assert ties, "expected at least one subtle tie on synthetic lead-lag"
    assert "resid_leadlag" in kinds or "shared_resid" in kinds or "delayed_echo" in kinds
