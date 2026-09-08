from analytics.trade_rotation import select_diversified_buys
from symbol_aliases import issuer_group, issuer_siblings, same_issuer


def test_goog_googl_same_issuer():
    assert issuer_group("GOOG") == issuer_group("GOOGL") == "GOOGL"
    assert same_issuer("GOOG", "GOOGL")
    assert "GOOG" in issuer_siblings("GOOGL")
    assert not same_issuer("GOOG", "MSFT")


def test_diversify_will_not_pick_both_google_classes():
    held = {"GOOGL"}
    cands = [
        {"ticker": "GOOG", "score": 0.9},
        {"ticker": "MSFT", "score": 0.8},
        {"ticker": "NVDA", "score": 0.7},
    ]
    out = select_diversified_buys(cands, 5, held=held)
    tickers = {str(c["ticker"]).upper() for c in out}
    assert "GOOG" not in tickers
    assert "MSFT" in tickers


def test_force_cannot_double_google():
    cands = [
        {"ticker": "GOOG", "score": 0.99, "force_priority": True},
        {"ticker": "GOOGL", "score": 0.98, "force_priority": True},
        {"ticker": "AAPL", "score": 0.5},
    ]
    out = select_diversified_buys(cands, 5, held=set())
    googlish = [c["ticker"] for c in out if str(c["ticker"]).upper() in ("GOOG", "GOOGL")]
    assert len(googlish) == 1
