"""Tests for institutional stake headline detection."""

from intel.institutional_flow_signals import _scan_documents, assess_institutional_flow


def test_pershing_square_msft_stake_detected():
    headline = (
        "Bill Ackman's Pershing Square disclosing a large new stake in Microsoft "
        "signals strong long-term confidence in its fundamentals and valuation."
    )
    scan = _scan_documents("MSFT", [headline])
    assert scan["bullish_count"] >= 1
    assert scan["high_conviction"]
    assert any("pershing" in m.lower() for m in scan["managers"])


def test_exit_headline_bearish():
    headline = "Tiger Global cuts its stake in NVDA after weak quarter"
    scan = _scan_documents("NVDA", [headline])
    assert scan["bearish_count"] >= 1


def test_assess_returns_boost_for_stake():
    headline = "Pershing Square disclosed stake in MSFT as largest position in portfolio"
    meta = assess_institutional_flow("MSFT", documents=[headline])
    assert meta.get("boost_long") is True
    assert float(meta.get("p_up_delta") or 0) > 0
