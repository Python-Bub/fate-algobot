from alpaca_broker import _floor_qty, _qty_str


def test_yahoo_crypto_symbol_not_btcusd():
    from analytics.hidden_pattern_anomaly import _bars_symbol

    assert _bars_symbol("$BTCUSD") == "BTC-USD"
    assert _bars_symbol("ETHUSD") == "ETH-USD"


def test_crypto_qty_never_rounds_above_available():
    avail = 0.097004357
    requested = 0.09700436  # naive 8-decimal round-up
    assert _floor_qty(min(requested, avail)) <= avail
    assert float(_qty_str(requested, avail=avail)) <= avail
    assert float(_qty_str(5.12703304, avail=5.127033035)) <= 5.127033035
