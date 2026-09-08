"""Downward-pressure must not buy falling names, then stop them out."""

from __future__ import annotations

from intel.downward_pressure import blocks_new_buy


def _assess(**over):
    base = {
        "block_new_buy": False,
        "tighten_exit": False,
        "counter_signal": False,
        "reasons": [],
        "pressure_score": 0.0,
        "stop_mult": 1.0,
    }
    base.update(over)
    return base


def test_hard_dump_blocks_buy(monkeypatch):
    monkeypatch.setattr(
        "intel.downward_pressure.assess_downward_pressure",
        lambda *_a, **_k: _assess(
            block_new_buy=True,
            tighten_exit=True,
            pressure_score=0.85,
            reasons=["hard 5d dump -8.8%"],
        ),
    )
    blocked, why = blocks_new_buy("AVGO")
    assert blocked
    assert "dump" in why


def test_soft_20d_weakness_blocks_buy(monkeypatch):
    monkeypatch.setenv("DOWNPRESS_BLOCK_ON_TIGHTEN", "true")
    monkeypatch.delenv("DOWNPRESS_SOFT_OK_WHEN_UNDERDEPLOY", raising=False)
    monkeypatch.delenv("FORTRESS_FADE_SKIP_SOFT_DOWNPRESS", raising=False)
    monkeypatch.setattr(
        "intel.downward_pressure.assess_downward_pressure",
        lambda *_a, **_k: _assess(
            tighten_exit=True,
            pressure_score=0.55,
            reasons=["soft 20d weakness -8.2%"],
        ),
    )
    blocked, why = blocks_new_buy("AAPL")
    assert blocked
    assert "20d" in why


def test_soft_weakness_allowed_when_underdeployed(monkeypatch):
    monkeypatch.setenv("DOWNPRESS_BLOCK_ON_TIGHTEN", "true")
    monkeypatch.setenv("DOWNPRESS_SOFT_OK_WHEN_UNDERDEPLOY", "true")
    monkeypatch.setattr(
        "intel.downward_pressure.assess_downward_pressure",
        lambda *_a, **_k: _assess(
            tighten_exit=True,
            pressure_score=0.55,
            reasons=["soft 20d weakness -8.2%"],
        ),
    )
    blocked, _why = blocks_new_buy("KO")
    assert not blocked


def test_hard_dump_still_blocks_when_underdeployed(monkeypatch):
    monkeypatch.setenv("DOWNPRESS_SOFT_OK_WHEN_UNDERDEPLOY", "true")
    monkeypatch.setattr(
        "intel.downward_pressure.assess_downward_pressure",
        lambda *_a, **_k: _assess(
            block_new_buy=True,
            tighten_exit=True,
            pressure_score=0.85,
            reasons=["hard 5d dump -8.8%"],
        ),
    )
    blocked, why = blocks_new_buy("AVGO")
    assert blocked
    assert "dump" in why


def test_counter_signal_allows_soft_weakness(monkeypatch):
    monkeypatch.setenv("DOWNPRESS_BLOCK_ON_TIGHTEN", "true")
    monkeypatch.setattr(
        "intel.downward_pressure.assess_downward_pressure",
        lambda *_a, **_k: _assess(
            tighten_exit=True,
            counter_signal=True,
            pressure_score=0.45,
            reasons=["soft 5d weakness -4.1%", "counter-signal: strong 5d bounce"],
        ),
    )
    blocked, _why = blocks_new_buy("MSFT")
    assert not blocked


def test_no_pressure_allows_buy(monkeypatch):
    monkeypatch.setattr(
        "intel.downward_pressure.assess_downward_pressure",
        lambda *_a, **_k: _assess(),
    )
    blocked, _why = blocks_new_buy("COST")
    assert not blocked


def test_addon_refuses_soft_pressure(monkeypatch):
    from types import SimpleNamespace

    from fortress_portfolio import can_add_position

    monkeypatch.setenv("FORTRESS_ALLOW_ADD_ON", "true")
    monkeypatch.setenv("DOWNPRESS_BLOCK_ON_TIGHTEN", "true")
    monkeypatch.delenv("DOWNPRESS_SOFT_OK_WHEN_UNDERDEPLOY", raising=False)
    monkeypatch.delenv("FORTRESS_FADE_SKIP_SOFT_DOWNPRESS", raising=False)
    monkeypatch.setattr(
        "intel.downward_pressure.assess_downward_pressure",
        lambda *_a, **_k: _assess(
            tighten_exit=True,
            pressure_score=0.55,
            reasons=["soft 20d weakness -8.2%"],
        ),
    )
    rm = SimpleNamespace(equity=72_000.0, total_gross_exposure=lambda: 20_000.0)
    rm.can_open = lambda *a, **k: True  # noqa: E731
    assert can_add_position(rm, "AAPL", 2500.0, 300.0, 280.0, existing_mv=4900.0) is False
