"""Public event clocks — trials / guidance / conferences / exhaustion.

Does not hit the network. INTerpath-001 fixture matches the 2026-08-19 MRNA print:
Phase 3 ACTIVE_NOT_RECRUITING, primary completion 2029-10-26, Moderna collaborator.
"""

from __future__ import annotations

from datetime import date

import pytest

from analytics.event_calendar import (
    INTERPATH_001,
    event_rank_boost,
    exhaustion,
    extract_guidance_windows,
    flatten_study,
    map_org_to_ticker,
    score_ticker,
    study_pre_score,
)
from analytics.sleeve_weights import assert_tables_valid, FORTRESS_PCT, HFT_PCT, pct_sum


AS_OF = date(2026, 8, 18)  # day before the INTerpath-001 RFS print


def test_sponsor_map_hits_collaborator_and_lead():
    assert map_org_to_ticker("Merck Sharp & Dohme LLC") == "MRK"
    assert map_org_to_ticker("ModernaTX, Inc.") == "MRNA"
    assert map_org_to_ticker("Pfizer Inc") == "PFE"


def test_nested_v2_flatten_maps_both_tickers():
    raw = {
        "hasResults": False,
        "protocolSection": {
            "identificationModule": {
                "nctId": "NCT05933577",
                "briefTitle": INTERPATH_001["title"],
            },
            "statusModule": {
                "overallStatus": "ACTIVE_NOT_RECRUITING",
                "primaryCompletionDateStruct": {"date": "2029-10-26", "type": "ESTIMATED"},
                "lastUpdatePostDateStruct": {"date": "2025-09-24"},
            },
            "sponsorCollaboratorsModule": {
                "leadSponsor": {"name": "Merck Sharp & Dohme LLC", "class": "INDUSTRY"},
                "collaborators": [{"name": "ModernaTX, Inc.", "class": "INDUSTRY"}],
            },
            "designModule": {"phases": ["PHASE3"]},
        },
    }
    flat = flatten_study(raw)
    assert flat is not None
    assert flat["tickers"]["MRK"] == "lead"
    assert flat["tickers"]["MRNA"] == "collaborator"
    assert flat["oncology"] is True


def test_primary_completion_2029_still_live_binary():
    sc = study_pre_score(INTERPATH_001, as_of=AS_OF)
    assert sc["days_to_primary"] is not None and sc["days_to_primary"] > 1000
    assert sc["proximity"] == pytest.approx(0.0, abs=0.02)
    assert sc["live_binary"] >= 0.55
    assert sc["pre"] >= 0.55


def test_mrna_collaborator_scores_without_guidance():
    row = score_ticker("MRNA", [INTERPATH_001], as_of=AS_OF)
    assert row["live_binary"] >= 0.55
    assert row["trial"] >= 0.35
    assert row["days_to_primary"] > 1000
    # Armed binary uses a near clock, not the 2029 OS date.
    assert row["effective_dte"] is not None and abs(int(row["effective_dte"])) <= 21


def test_guidance_interim_2026_beats_year_bucket_when_half_present():
    text = "We expect an interim analysis and topline data in 2H 2026."
    wins = extract_guidance_windows(text, as_of=AS_OF)
    spans = {w["span"] for w in wins}
    assert any("H2" in s for s in spans)
    assert "2026" not in spans  # year dropped when half exists
    assert wins[0]["heat"] >= 0.35
    assert "interim" in wins[0]["tags"] or "topline" in wins[0]["tags"]


def test_guidance_lifts_mrna_pre_print():
    bare = score_ticker("MRNA", [INTERPATH_001], as_of=AS_OF)
    guided = score_ticker(
        "MRNA",
        [INTERPATH_001],
        guidance_text="interim analysis expected in 2026",
        as_of=AS_OF,
    )
    assert guided["guidance"] > bare["guidance"]
    assert guided["pre"] > bare["pre"]
    boost, meta = event_rank_boost(
        "MRNA", sleeve="fortress", row=guided, mom_5d=0.02, ret_1d=0.01
    )
    assert boost > 0.08
    assert meta["exhaust"] == 0.0


def test_gap_exhaustion_downranks_after_print():
    guided = score_ticker(
        "MRNA",
        [INTERPATH_001],
        guidance_text="interim analysis expected in 2026",
        as_of=date(2026, 8, 19),
    )
    assert exhaustion(0.80, 1.10, live=guided["live_binary"]) >= 0.70
    boost, meta = event_rank_boost(
        "MRNA",
        sleeve="fortress",
        row=guided,
        mom_5d=1.10,
        ret_1d=0.80,
    )
    assert boost < 0
    assert meta["exhaust"] >= 0.45


def test_stale_completed_does_not_look_armed():
    grave = {
        "nct_id": "NCT00000001",
        "title": "An Old Oncology Study",
        "lead_sponsor": "Pfizer Inc",
        "collaborators": [],
        "phase": "PHASE3",
        "status": "COMPLETED",
        "primary_completion": "2012-06-01",
        "last_update": "2013-01-15",
        "has_results": False,
    }
    sc = study_pre_score(grave, as_of=AS_OF)
    assert sc["live_binary"] == 0.0
    assert sc["proximity"] == 0.0
    assert sc["pre"] < 0.05


def test_earnings_style_far_primary_would_miss():
    """A 'days to primary completion' calendar is exactly what missed MRNA."""
    sc = study_pre_score(INTERPATH_001, as_of=AS_OF)
    assert sc["proximity"] < 0.05
    assert sc["live_binary"] > 0.5


def test_sleeve_tables_keep_event_calendar_and_sum_100():
    assert_tables_valid()
    assert FORTRESS_PCT["event_calendar"] >= 1.0
    assert HFT_PCT.get("event_calendar", 0.0) == 0.0
    assert pct_sum("fortress") == pytest.approx(100.0, abs=0.01)
    assert pct_sum("hft") == pytest.approx(100.0, abs=0.01)
    assert pct_sum("day_trade") == pytest.approx(100.0, abs=0.01)
    assert pct_sum("weekly") == pytest.approx(100.0, abs=0.01)
    assert pct_sum("longterm") == pytest.approx(100.0, abs=0.01)
