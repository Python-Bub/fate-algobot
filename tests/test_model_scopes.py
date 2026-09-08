"""Model universes must not all share one ticker list."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv(
        "OBI_TICKER_WHITELIST",
        "SPY,QQQ,IWM,NVDA,AMD,TSLA,MSFT,NFLX,AMZN",
    )
    monkeypatch.setenv(
        "HFT_REST_TICKERS",
        "TJX,DELL,CVCO,PANW,GS,WELL",
    )
    monkeypatch.setenv("PAPER_HYGIENE_OBI_SCOPE", "false")


def test_hft_and_fortress_scopes_differ():
    from analytics.model_scopes import (
        fortress_playbook_tickers,
        hft_all_tickers,
        hft_ws_tickers,
    )

    hft = set(hft_all_tickers())
    ws = set(hft_ws_tickers())
    assert "SPY" in ws
    assert "TJX" not in ws
    assert "TJX" in hft

    playbook = set(fortress_playbook_tickers())
    if playbook:
        assert playbook - hft, "fortress should have names outside HFT WS basket"


def test_hygiene_obi_scope_off_by_default():
    from fortress_portfolio import liquidate_outside_obi_scope

    assert os.getenv("PAPER_HYGIENE_OBI_SCOPE", "false").lower() not in ("1", "true", "yes")
    assert liquidate_outside_obi_scope() == 0
