"""Ticker identity, algorithm memory, calibrated power-people, Lee-Chin tilt."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pandas as pd
import pytest


def test_rename_history_and_spinoff_does_not_alias_parent():
    from symbol_aliases import canonical_symbol, price_feed_symbol
    from universe_lifecycle.corporate_actions import (
        alias_map,
        former_tickers,
        history_symbols,
        is_dead_money,
        lineage,
        related_symbols,
        spinoff_children,
    )

    assert canonical_symbol("FB") == "META"
    assert price_feed_symbol("SQ") == "XYZ"
    assert "FB" in former_tickers("META")
    assert "FB" in history_symbols("META")
    m = alias_map()
    assert m.get("EBAY") is None
    assert spinoff_children("EBAY") == ["PYPL"]
    assert "PYPL" in related_symbols("EBAY")
    assert "EBAY" in related_symbols("PYPL")
    assert is_dead_money("TMHC") is True
    assert is_dead_money("TWTR") is True
    assert is_dead_money("AAPL") is False
    ident = lineage("FB")
    assert ident["canonical"] == "META"
    assert ident["dead_money"] is False


def test_register_spinoff_does_not_alias(tmp_path, monkeypatch):
    from universe_lifecycle import corporate_actions as ca

    p = tmp_path / "corp.json"
    monkeypatch.setattr(ca, "CORPORATE_ACTIONS_PATH", p)
    ca.save_registry({"version": 1, "aliases": {}, "events": [], "delisted": [], "pending_migrations": []})
    ca.register_event(kind="spinoff", old="PARENT", new="CHILD", source="test", note="unit")
    reg = ca.load_registry()
    assert reg["aliases"].get("PARENT") is None
    assert ca.canonical_symbol("PARENT") == "PARENT"
    pending = reg["pending_migrations"]
    assert any(x.get("kind") == "spinoff" and x.get("new") == "CHILD" for x in pending)


def test_stitch_former_ticker_fills_older_dates():
    from feature_engineering import _stitch_price_history

    meta = pd.DataFrame({"Close": [10.0, 11.0]}, index=pd.to_datetime(["2022-01-03", "2022-01-04"]))
    fb = pd.DataFrame({"Close": [8.0, 9.0, 10.0]}, index=pd.to_datetime(["2021-12-30", "2021-12-31", "2022-01-03"]))
    out = _stitch_price_history([meta, fb])
    assert list(out.index.strftime("%Y-%m-%d")) == ["2021-12-30", "2021-12-31", "2022-01-03", "2022-01-04"]
    assert float(out.loc["2022-01-03", "Close"]) == 10.0  # current listing wins overlap


def test_algo_memory_summary_and_dead_money(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_ALGO_MEMORY", "true")
    monkeypatch.setenv("ALGO_MEMORY_FILE", str(tmp_path / "mem.jsonl"))
    monkeypatch.setenv("ALGO_MEMORY_SUMMARY_FILE", str(tmp_path / "sum.json"))
    from intel import algo_memory as am

    am.remember("rename", "META", "FB renamed to META", related=["FB"], source="test")
    doc = am.summary_for("META")
    assert doc["ticker"] == "META"
    assert any("FB" in b or "META" in b for b in doc.get("bullets") or [])
    # TMHC is cash takeout in the live registry
    assert am.memory_boost_for("TMHC") == -1.0


def test_power_people_requires_speaker_ticker_and_direction(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_POWER_PEOPLE", "true")
    monkeypatch.setenv("POWER_PEOPLE_HITS_FILE", str(tmp_path / "hits.jsonl"))
    monkeypatch.setenv("POWER_PEOPLE_CAL_FILE", str(tmp_path / "cal.json"))
    from intel.power_people import extract_mentions, power_people_boost_for, append_hits

    assert extract_mentions("The president talked about chips and cars and energy.") == []
    assert extract_mentions("Trump mentioned Tesla in passing.") == []  # no direction
    hits = extract_mentions(
        "President Trump said wanna get rich? Buy this Tesla.",
        ts=date.today().isoformat(),
    )
    assert len(hits) == 1
    assert hits[0]["ticker"] == "TSLA"
    assert hits[0]["speaker"] == "trump"
    assert hits[0]["direction"] > 0
    assert hits[0]["strong"] is True

    # RSS bucket filter: Powell text in a Trump query must not invent Trump
    assert extract_mentions("Powell said buy Apple.", speaker_hint="trump") == []

    two = extract_mentions("Elon Musk said buy the Cybertruck now.")
    assert any(h["ticker"] == "TSLA" and h["speaker"] == "musk" for h in two)

    append_hits(hits, source="test")
    boost = power_people_boost_for("TSLA")
    assert boost > 0


def test_lee_chin_tilt_and_chapter():
    from investing.knowledge import get_chapter
    from investing.knowledge.lee_chin import lee_chin_tilt

    ch = get_chapter("lee_chin_five_laws")
    assert ch is not None
    assert "high-quality" in ch.philosophy.lower() or "few" in ch.philosophy.lower()
    good = lee_chin_tilt({"returnOnEquity": 0.22, "debtToEquity": 40.0, "profitMargins": 0.18})
    bad = lee_chin_tilt({"returnOnEquity": -0.05, "debtToEquity": 400.0, "profitMargins": -0.1})
    assert good > 0
    assert bad < 0


def test_beginner_guide_covers_operator_book_and_lee_chin():
    from investing.beginner_guide import coverage_check, GUIDE_SECTIONS

    ids = {s["id"] for s in GUIDE_SECTIONS}
    for need in ("value", "growth", "derivatives", "shorts", "macro", "passive", "advanced", "lee_chin", "identity_memory"):
        assert need in ids
    cov = coverage_check()
    assert cov["missing"] == []


def test_sleeve_still_sums_100_with_power_people():
    from analytics.sleeve_weights import HFT_PCT, pct_sum, SLEEVES, assert_tables_valid

    assert_tables_valid()
    for s in SLEEVES:
        assert pct_sum(s) == pytest.approx(100.0, abs=0.01)
    assert HFT_PCT.get("power_people", 0.0) == 0.0
