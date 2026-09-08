"""Incremental paper sim row reuse."""

from pathlib import Path
from unittest.mock import patch

from analytics.paper_incremental import plan_incremental_rescore


def test_reuse_when_signal_date_matches():
    prev_rows = [
        {
            "ticker": "AAPL",
            "skipped": False,
            "score": 0.2,
            "signal_date": "2026-06-05",
            "p_daily_model_raw": 0.6,
        },
        {
            "ticker": "MSFT",
            "skipped": False,
            "score": 0.1,
            "signal_date": "2026-06-04",
            "p_daily_model_raw": 0.55,
        },
    ]
    prev = {"rows": prev_rows, "generated_at_utc": "2026-06-05T23:48:01+00:00"}

    with patch(
        "analytics.paper_report.latest_valid_report",
        return_value=(Path("paper_sim_test.json"), prev),
    ):
        reuse, rescore, meta = plan_incremental_rescore(
            ["AAPL", "MSFT", "NVDA"], signal_date="2026-06-05"
        )

    assert meta["reused"] == 1
    assert reuse[0]["ticker"] == "AAPL"
    assert set(rescore) == {"MSFT", "NVDA"}
