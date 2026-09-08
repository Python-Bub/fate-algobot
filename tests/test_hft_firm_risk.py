"""Lag / inventory haircuts — sit out before the book is eaten."""

from __future__ import annotations

import math

from analytics.hft_firm_risk import (
    clip_notional,
    combined_haircut,
    inventory_haircut,
    lag_haircut,
)


def test_lag_haircut_half_life():
    assert abs(lag_haircut(0, 0, 250) - 1.0) < 1e-12
    assert abs(lag_haircut(250, 0, 250) - 0.5) < 1e-12
    assert lag_haircut(2000, 250, 250) < 0.05


def test_inventory_haircut_full_book_is_zero():
    assert inventory_haircut(0, 72_000, 0.08) == 1.0
    assert inventory_haircut(5_760, 72_000, 0.08) == 0.0
    assert 0.4 < inventory_haircut(2_880, 72_000, 0.08) < 0.6


def test_sit_out_when_lag_eats_edge():
    fresh = combined_haircut(0, 0, 72_000, 0.0, half_life_ms=250, min_haircut=0.12)
    assert fresh["sit_out"] is False
    stale = combined_haircut(2000, 0, 72_000, 250.0, half_life_ms=250, min_haircut=0.12)
    assert stale["sit_out"] is True
    full = combined_haircut(0, 5_760, 72_000, 0.0)
    assert full["sit_out"] is True


def test_clip_never_rounds_thin_haircut_up():
    assert clip_notional(180, 0.5) == 90
    assert clip_notional(180, 0.1) == 0
    assert clip_notional(6400, 1.0) == 350
    assert math.isclose(clip_notional(200, 1.0), 200)
