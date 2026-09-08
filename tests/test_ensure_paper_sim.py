"""Auto paper sim scheduling."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def fresh_report(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    reports.mkdir()
    doc = {
        "rows": [{"ticker": "AAPL", "skipped": False, "score": 0.2, "top100": True}] * 120,
        "universe_size": 480,
        "symbols_scored": 120,
        "generated_at_utc": "2026-06-07T14:00:00+00:00",
    }
    path = reports / "paper_sim_test.json"
    import json

    path.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setenv("PAPER_REPORT_MIN_TRADEABLE", "100")
    monkeypatch.setenv("PAPER_REPORT_MIN_TOP100", "50")
    monkeypatch.setenv("PAPER_REPORT_MIN_COVERAGE", "0.20")
    monkeypatch.setenv("AUTO_PAPER_SIM_MAX_AGE_HOURS", "20")
    with patch("analytics.paper_report.REPORTS", reports):
        with patch("analytics.paper_report.latest_valid_report") as lv:
            lv.return_value = (path, doc)
            yield path, doc


def test_needs_paper_sim_when_fresh(fresh_report):
    from tools.ensure_paper_sim import needs_paper_sim

    with patch("analytics.paper_report.report_age_hours", return_value=1.0):
        need, reason = needs_paper_sim()
    assert need is False
    assert reason == "fresh"


def test_needs_paper_sim_when_stale(fresh_report):
    from tools.ensure_paper_sim import needs_paper_sim

    with patch("analytics.paper_report.report_age_hours", return_value=30.0):
        need, reason = needs_paper_sim()
    assert need is True
    assert reason.startswith("stale:")


def test_start_skips_when_in_progress(monkeypatch):
    from tools.ensure_paper_sim import start_paper_sim_background

    monkeypatch.setenv("AUTO_PAPER_SIM_COOLDOWN_SEC", "0")
    with patch("tools.ensure_paper_sim.paper_sim_in_progress", return_value=True):
        assert start_paper_sim_background(reason="test") is False
