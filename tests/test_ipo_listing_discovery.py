"""Tests for IPO / listing discovery filters and queue hygiene."""

from __future__ import annotations

from intel.ipo_news_discovery import _normalize_ticker, is_denied_ticker
from tools.listing_watch import is_queueable_listing_ticker


def test_deny_regulators_and_private_brands():
    for junk in ("OPENAI", "SEBI", "DRHP", "IFSCA", "SEC", "IPO", "SPAC"):
        assert is_denied_ticker(junk)
        assert _normalize_ticker(junk) is None


def test_normalize_accepts_real_tickers():
    assert _normalize_ticker("QMLS") == "QMLS"
    assert _normalize_ticker("STDN") == "STDN"
    assert _normalize_ticker("$CSQR") is None  # dollar handled by extractors, not normalize
    assert _normalize_ticker("aapl") == "AAPL"


def test_normalize_rejects_units_by_default():
    assert _normalize_ticker("PHAXU") is None  # unit stub
    assert _normalize_ticker("XIIIU") is None


def test_megacap_proxies_not_queueable_as_listings():
    for prox in ("MSFT", "NVDA", "GOOGL", "AMZN", "META", "AMD", "AVGO", "ORCL"):
        assert not is_queueable_listing_ticker(prox)


def test_junk_not_queueable():
    for junk in ("OPENAI", "SEBI", "DRHP", "THISX", "SPACEX"):
        assert not is_queueable_listing_ticker(junk)


def test_spacex_still_private_probe():
    from tools.listing_watch import probe_private_company_listings

    rows = probe_private_company_listings(
        {"tickers": ["QMLS", "STDN"], "company_names": [], "sources": {}}
    )
    by = {r["name"]: r for r in rows}
    assert by["SPACEX"]["status"] == "still_private"
    assert by["SPACEX"]["ticker"] is None
    assert by["OPENAI"]["status"] == "still_private"
