"""Tests for cross-listing / regional market imbalance detection."""

from __future__ import annotations

import numpy as np

from analytics.market_imbalance import ImbalanceHit, imbalance_rank_boost, save_imbalances


def test_imbalance_rank_boost_cheap_side(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_MARKET_IMBALANCE", "true")
    monkeypatch.setenv("RANK_W_MARKET_IMBALANCE", "0.10")
    hits = [
        ImbalanceHit(
            symbol="BABA",
            peer="9988.HK",
            score=0.8,
            direction=1,
            gap_pct=-0.03,
            z=-2.5,
            fx="USDHKD=X",
            ratio=8.0,
            reasons=["parity_gap=-3.00% z=-2.50 vs 9988.HK"],
            primary_px=80.0,
            peer_px_local=620.0,
            peer_px_usd=82.5,
        )
    ]
    path = tmp_path / "imb.json"
    save_imbalances(hits, path=path)
    monkeypatch.setattr("analytics.market_imbalance.OUT_PATH", path)
    b, meta = imbalance_rank_boost("BABA")
    assert b > 0
    assert meta.get("hit") is True
    # Peer side inverted
    b2, meta2 = imbalance_rank_boost("9988.HK")
    assert meta2.get("as_peer") is True
    assert b2 < 0


def test_gap_math_direction():
    # primary cheap → negative gap → direction +1
    p = np.array([100.0] * 30 + [95.0])
    peer = np.array([100.0] * 31)
    mid = (p + peer) / 2
    gap = (p - peer) / mid
    assert gap[-1] < 0
