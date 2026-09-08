"""Crypto/commodity driver math + experimental crypto HFT gates."""

from __future__ import annotations

import pandas as pd
import pytest

from analytics.commodity_math import classify_commodity, score_commodity
from analytics.crypto_hft import decide_entry, qty_for_clip, skip_held, spread_bps
from analytics.crypto_math import CryptoScore, score_crypto, should_fire_hft
from analytics.alt_drivers import alt_rank_boost
from analytics.sleeve_weights import HFT_PCT, pct_sum


def _idx(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2024-01-02", periods=n)


def _path(start: float, rets: list[float]) -> pd.Series:
    px = [float(start)]
    for r in rets:
        px.append(px[-1] * (1.0 + float(r)))
    return pd.Series(px, index=_idx(len(px)))


def _flat(start: float, n: int, last_bump: float = 0.0) -> pd.Series:
    rets = [0.0002] * (n - 1)
    if last_bump:
        rets[-1] = last_bump
    return _path(start, rets)


def _fetch(store: dict[str, pd.Series]):
    def fn(sym: str, days: int):
        return store.get(str(sym).strip().upper(), pd.Series(dtype=float))

    return fn


def _bull_btc_store() -> dict[str, pd.Series]:
    n = 80
    # Dollar and yields falling; BTC grinding then breaking out; IBIT leads.
    dxy = _path(30.0, [0.0005] * (n - 6) + [-0.006] * 5)
    tnx = _path(4.2, [0.001] * (n - 6) + [-0.02] * 5)
    btc = _path(90_000.0, [0.001] * (n - 6) + [0.012] * 4 + [0.045])
    ibit = _path(40.0, [0.001] * (n - 6) + [0.016] * 4 + [0.055])
    eth = _path(3_200.0, [0.001] * (n - 6) + [0.01] * 4 + [0.03])
    return {
        "UUP": dxy,
        "DX-Y.NYB": dxy,
        "^TNX": tnx,
        "BTC-USD": btc,
        "ETH-USD": eth,
        "IBIT": ibit,
        "BITO": ibit,
    }


def test_btc_bull_math_is_positive_and_explosive():
    cs = score_crypto("BTC-USD", fetch=_fetch(_bull_btc_store()), news_tilt=0.4)
    assert cs.score > 0.15
    assert cs.p_up > 0.55
    assert cs.breakout
    assert cs.explosive > 0.35
    assert cs.drivers["dollar_inv"] > 0.2
    assert "explosive_up" in cs.notes


def test_strong_dollar_hurts_btc():
    store = _bull_btc_store()
    n = len(store["UUP"]) - 1
    store["UUP"] = _path(30.0, [-0.0002] * (n - 5) + [0.01] * 5)
    cs = score_crypto("BTC-USD", fetch=_fetch(store), news_tilt=0.0)
    bull = score_crypto("BTC-USD", fetch=_fetch(_bull_btc_store()), news_tilt=0.0)
    assert cs.drivers["dollar_inv"] < bull.drivers["dollar_inv"]
    assert cs.score < bull.score


def test_silver_owns_gsr_and_copper_gold_does_not_use_copper():
    n = 90
    # Elevated gold/silver ratio (gold up, silver flat historically then silver catch-up setup)
    gold = _path(2000.0, [0.002] * (n - 1))
    silver = _path(22.0, [0.0003] * (n - 6) + [0.004] * 5)  # still cheap vs gold
    copper = _path(4.0, [0.0002] * (n - 6) + [0.02] * 5)
    dxy = _path(30.0, [0.0002] * (n - 6) + [-0.008] * 5)
    tnx = _path(4.2, [0.0] * (n - 6) + [-0.03] * 5)
    store = {
        "GC=F": gold,
        "GLD": gold,
        "SI=F": silver,
        "SLV": silver,
        "HG=F": copper,
        "CPER": copper,
        "UUP": dxy,
        "^TNX": tnx,
        "^VIX": _path(15.0, [0.0] * (n - 1)),
        "SPY": _path(500.0, [0.001] * (n - 1)),
        "CL=F": _path(70.0, [0.001] * (n - 1)),
        "XLE": _path(80.0, [0.001] * (n - 1)),
    }
    slv = score_commodity("SLV", fetch=_fetch(store))
    gld = score_commodity("GLD", fetch=_fetch(store))
    assert slv.family == "silver"
    assert gld.family == "gold"
    assert slv.score > 0.05
    assert "copper_5d" in slv.drivers
    assert "copper_5d" not in gld.drivers
    miner = score_commodity("AG", fetch=_fetch(store))
    assert miner.family == "silver_miner"
    assert abs(miner.score) <= abs(slv.score) + 1e-9
    assert miner.score == pytest.approx(slv.score * 0.45, abs=0.02)


def test_classify_and_equity_zero_boost(monkeypatch):
    monkeypatch.setenv("ALT_DRIVERS_NEWS", "false")
    assert classify_commodity("SLV") == "silver"
    assert classify_commodity("NEM") == "gold_miner"
    assert classify_commodity("AAPL") == ""
    b, meta = alt_rank_boost("AAPL")
    assert b == 0.0
    assert meta.get("reason") == "not_alt"


def test_alt_boost_btc_with_injected_feed(monkeypatch):
    monkeypatch.setenv("ALT_DRIVERS_NEWS", "false")
    b, meta = alt_rank_boost("BTC-USD", fetch=_fetch(_bull_btc_store()))
    assert b > 0.15
    assert meta["family"] == "crypto"
    assert meta["breakout"] is True


def test_crypto_hft_gates():
    cs = CryptoScore(
        ticker="BTC-USD",
        score=0.4,
        p_up=0.7,
        explosive=0.6,
        breakout=True,
        drivers={},
    )
    ok, why = should_fire_hft(cs, spread_bps=4.0, mid_slope=0.0002)
    assert ok and why == "crypto_math"
    bad, why2 = should_fire_hft(cs, spread_bps=40.0, mid_slope=0.0002)
    assert not bad and why2 == "spread"
    fade, why3 = should_fire_hft(cs, spread_bps=4.0, mid_slope=-0.002)
    assert not fade and why3 == "mid_fade"


def test_skip_fortress_inventory_and_tiny_qty():
    assert skip_held("BTC/USD", live_qty=0.01, our_qty=0.0) is True
    assert skip_held("BTC/USD", live_qty=0.0008, our_qty=0.0008) is False
    q = qty_for_clip(100_000.0, 80.0)
    assert 0.0007 < q < 0.0009
    assert spread_bps(100.0, 100.05) < 8.0


def test_decide_entry_skips_fortress(monkeypatch):
    monkeypatch.setenv("CRYPTO_HFT_MAX_OPEN", "1")
    cs = CryptoScore("BTC-USD", 0.5, 0.75, 0.7, True, {})
    d = decide_entry(
        cs,
        bid=100_000.0,
        ask=100_008.0,
        mids=[99_900, 99_950, 100_004],
        held_fortress=True,
        open_count=0,
        gross_usd=0.0,
    )
    assert d["ok"] is False
    assert d["why"] == "fortress_held"
    d2 = decide_entry(
        cs,
        bid=100_000.0,
        ask=100_008.0,
        mids=[99_900, 99_950, 100_004],
        held_fortress=False,
        open_count=0,
        gross_usd=0.0,
    )
    assert d2["ok"] is True
    assert d2["qty"] > 0


def test_hft_sleeve_still_one_hundred_and_no_alt_bleed():
    assert pct_sum("hft") == pytest.approx(100.0, abs=0.01)
    assert HFT_PCT.get("alt_drivers", 0.0) == 0.0
    assert HFT_PCT.get("proven_online", 0.0) == 0.0


def test_crypto_quote_uses_crypto_endpoint(monkeypatch):
    import alpaca_broker as ab

    class _R:
        status_code = 200
        content = b"x"

        def json(self):
            return {"quotes": {"BTC/USD": {"bp": 101_000.0, "ap": 101_012.0}}}

        def raise_for_status(self):
            return None

    monkeypatch.setattr(ab, "_keys", lambda: ("k", "s"))
    monkeypatch.setattr(ab, "_data_headers", lambda: {"Authorization": "x"})
    monkeypatch.setattr(ab.requests, "get", lambda *a, **k: _R())
    monkeypatch.setattr(
        "analytics.alpaca_limits.quote_cache_get",
        lambda *_a, **_k: None,
    )
    q = ab.get_quote_bid_ask("BTC-USD")
    assert q == (101_000.0, 101_012.0)
