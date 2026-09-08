"""Public event tells — peer cascade / filings / rank. No network."""

from __future__ import annotations

import pytest

from analytics.event_ingenuity import (
    HARD_PEERS,
    block_add_on_peer_dump,
    contagion_decision,
    contagion_for_book,
    peer_universe,
    rank_boost_from_features,
    score_filings,
    score_peer_cascade,
    straddle_proxy,
)
from analytics.event_learn import FEATURE_NAMES, featurize
from analytics.sleeve_weights import FORTRESS_PCT, HFT_PCT, assert_tables_valid, pct_sum


def test_wmt_cost_are_hard_peers():
    assert "COST" in HARD_PEERS["WMT"]
    assert "WMT" in peer_universe("COST")


def test_wmt_dump_trims_red_cost_does_not_flatten_green():
    # WMT −9%, COST −2% → trim, not flatten.
    trim = contagion_decision(-0.02, [-0.09])
    assert trim["kill"] is False
    assert trim["trim_frac"] == pytest.approx(0.40)
    assert trim["block_add"] is True
    assert trim["watch"] is True

    # COST also dumping hard → kill that name only.
    kill = contagion_decision(-0.04, [-0.09])
    assert kill["kill"] is True
    assert kill["trim_frac"] == pytest.approx(1.0)

    # COST green → keep the long, still block adds.
    green = contagion_decision(0.012, [-0.09])
    assert green["kill"] is False
    assert green["trim_frac"] == pytest.approx(0.0)
    assert green["block_add"] is True

    # Unrelated mild red with no peer dump.
    quiet = contagion_decision(-0.02, [-0.01])
    assert quiet["kill"] is False
    assert quiet["trim_frac"] == pytest.approx(0.0)
    assert quiet["block_add"] is False


def test_book_contagion_cost_not_aapl(monkeypatch):
    monkeypatch.setenv("USE_EVENT_INGENUITY", "true")
    positions = [
        {"symbol": "WMT", "qty": 62, "change_today": -0.089},
        {"symbol": "COST", "qty": 10, "change_today": -0.021},
        {"symbol": "AAPL", "qty": 20, "change_today": -0.008},
    ]
    acts = {a["symbol"]: a for a in contagion_for_book(positions)}
    assert acts["COST"]["trim_frac"] > 0
    assert acts["COST"]["kill"] is False
    # AAPL is not a WMT retail peer — no trim.
    assert "AAPL" not in acts or float(acts.get("AAPL", {}).get("trim_frac") or 0) == 0


def test_rank_fades_peer_dump():
    feats = score_peer_cascade([-0.09])
    boost = rank_boost_from_features(feats, dte=2)
    assert feats["peer_printed"] == 1.0
    assert boost < -0.05


def test_silence_and_eightk_and_straddle():
    dark = score_filings(eightk_2d=0, eightk_14d=0, form4_sell=0.8)
    assert dark["silence"] == 1.0
    assert dark["form4_sell"] == pytest.approx(0.8)
    burst = score_filings(eightk_2d=3, eightk_14d=3)
    assert burst["eightk_burst"] == pytest.approx(1.0)
    assert burst["silence"] == 0.0
    assert 0.02 < straddle_proxy(0.05, 0) <= 0.20
    assert straddle_proxy(0.05, 20) < straddle_proxy(0.05, 0)


def test_event_learn_merges_ingenuity_keys():
    for k in (
        "peer_gap_signed",
        "crowding",
        "eightk_burst",
        "form4_sell",
        "straddle_proxy",
    ):
        assert k in FEATURE_NAMES
    f = featurize(dte=0, extra={"peer_gap_signed": -0.08, "crowding": 0.5})
    assert f["peer_gap_signed"] == pytest.approx(-0.08)
    assert f["crowding"] == pytest.approx(0.5)
    assert f["dte_0"] == 1.0


def test_block_add_reads_sticky_book(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_EVENT_INGENUITY", "true")
    monkeypatch.setattr("analytics.event_ingenuity.GAPS_PATH", tmp_path / "gaps.json")
    from analytics.event_ingenuity import save_book_gaps

    save_book_gaps({"WMT": -0.09, "AAPL": -0.004})
    assert block_add_on_peer_dump("COST", 0.0) is True
    assert block_add_on_peer_dump("AAPL", 0.0) is False


def test_sleeve_keeps_ingenuity_and_100():
    assert_tables_valid()
    assert pct_sum("fortress") == pytest.approx(100.0, abs=0.01)
    assert FORTRESS_PCT.get("event_ingenuity", 0.0) >= 1.0
    assert HFT_PCT.get("event_ingenuity", 0.0) == 0.0
