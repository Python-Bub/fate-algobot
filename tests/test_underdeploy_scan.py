"""Underdeployed fortress must scan NEW names, not sit on holdings until PASS_MAX."""

from analytics.underdeploy_scan import order_scan_for_fill


def test_fresh_names_before_holds():
    held = ["AAPL", "AMZN", "NVDA"]
    universe = ["AAPL", "MSFT", "COST", "JPM", "AMZN", "KO", "NVDA", "XOM"]
    out = order_scan_for_fill(universe, held, fresh_cap=4)
    assert out[:4] == ["MSFT", "COST", "JPM", "KO"]
    assert out[-3:] == ["AAPL", "AMZN", "NVDA"]
    assert "NVDA" in out


def test_fresh_cap_does_not_drop_holds():
    held = ["AAPL", "SBUX"]
    universe = [f"T{i}" for i in range(80)] + held
    out = order_scan_for_fill(universe, held, fresh_cap=12)
    assert out[-2:] == ["AAPL", "SBUX"]
    assert len([s for s in out if s.startswith("T")]) == 12


def test_deprioritize_morning_club_when_fading():
    held = ["AAPL"]
    force = ["COST", "META", "MSFT"]
    universe = force + ["PFE", "T", "VZ", "MO", "KMB"]
    out = order_scan_for_fill(universe, held, fresh_cap=4, deprioritize=force)
    assert out[:4] == ["PFE", "T", "VZ", "MO"]
    assert "AAPL" in out
    assert "COST" not in out[:4]


def test_prefer_top100_ahead_of_microcaps():
    held = ["AAPL"]
    universe = ["ENGS", "FITBO", "JPM", "KO", "BUDA", "PEP"]
    out = order_scan_for_fill(
        universe, held, fresh_cap=4, prefer=["JPM", "KO", "PEP", "AAPL"]
    )
    assert out[:3] == ["JPM", "KO", "PEP"]
    assert "ENGS" not in out[:3]


def test_deploy_frac_fail_open_on_missing_equity():
    from analytics.underdeploy_scan import deploy_frac_from_snapshot

    assert deploy_frac_from_snapshot(0.0, 36_000.0) == 0.0
    assert deploy_frac_from_snapshot(1.0, 36_000.0) == 0.0
    assert abs(deploy_frac_from_snapshot(72_000.0, 36_000.0) - 0.5) < 1e-9


def test_dedupes_and_ignores_blank():
    out = order_scan_for_fill(["aapl", "AAPL", "", "MSFT"], ["AAPL"], fresh_cap=8)
    assert out == ["MSFT", "AAPL"]


def test_reserve_crypto_and_movers_beat_top100_cap():
    held = ["AAPL"]
    top = [f"T{i}" for i in range(80)]
    out = order_scan_for_fill(
        top + ["BTC-USD", "HOOD"],
        held,
        fresh_cap=8,
        prefer=top,
        reserve=["BTC-USD", "ETH-USD", "HOOD"],
    )
    assert out[:3] == ["BTC-USD", "ETH-USD", "HOOD"]
    assert "AAPL" in out
    assert "T0" in out
