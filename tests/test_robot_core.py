import numpy as np
import pandas as pd

from analytics.robot_core import catalog_coverage
from backtest import performance_stats


def test_johnston_buckets_all_present():
    cov = catalog_coverage()
    assert cov["missing_buckets"] == []
    assert cov["core_families_missing"] == []
    for sleeve in ("day_trade", "fortress", "hft", "gainz_1m_1h"):
        rules = cov["sleeves"][sleeve]
        assert rules["entry"]
        assert rules["exit"]
        assert rules["size"]


def test_backtest_sharpe_on_synthetic():
    rng = np.random.default_rng(1)
    r = pd.Series(rng.normal(0.001, 0.01, 252))
    st = performance_stats(r)
    assert st["n"] == 252
    assert st["max_dd"] >= 0
    assert np.isfinite(st["sharpe"])
