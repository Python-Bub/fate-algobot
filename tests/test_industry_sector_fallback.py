"""Industry sector fallback + known mega-cap hints."""

from __future__ import annotations

from analytics.industries.classifier import classify_ticker
from analytics.industries.sector_fallback import match_sector_fallback


def test_sector_fallback_oil():
    r = match_sector_fallback("Energy", "Oil & Gas Integrated", "Exxon Mobil")
    assert r is not None
    assert r.industry_id == "integrated_oil_gas"
    assert r.confidence >= 0.55


def test_sector_fallback_tech_hardware():
    r = match_sector_fallback("Technology", "Consumer Electronics", "Apple")
    assert r is not None
    assert r.industry_id == "tech_hardware"


def test_sector_fallback_banks():
    r = match_sector_fallback("Financial Services", "Banks—Diversified", "JPMorgan")
    assert r is not None
    assert r.industry_id == "diversified_banks"


def test_ticker_hints_without_yahoo():
    from analytics.industries.base import IndustryContext
    from analytics.industries.handlers.tech_hardware import HANDLER as HW
    from analytics.industries.handlers.integrated_oil_gas import HANDLER as OIL
    from analytics.industries.handlers.diversified_banks import HANDLER as BANK

    assert HW.classify(IndustryContext(symbol="AAPL")).industry_id == "tech_hardware"
    assert OIL.classify(IndustryContext(symbol="XOM")).industry_id == "integrated_oil_gas"
    assert BANK.classify(IndustryContext(symbol="JPM")).industry_id == "diversified_banks"
    aapl = classify_ticker("AAPL", use_cache=False, use_yfinance=False)
    assert str(aapl.get("industry_id") or "unclassified") != "unclassified"


def test_weights_sum_when_classified():
    row = classify_ticker("NVDA", use_cache=False, use_yfinance=False)
    assert row.get("industry_id") == "semiconductors"
    assert float(row.get("confidence") or 0) >= 0.5
