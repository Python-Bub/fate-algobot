from alt_assets import (
    COMMODITY_ETFS,
    is_alt_symbol,
    is_commodity_etf,
    is_tradeable_instrument,
    alt_scan_symbols,
)


def test_silver_and_gold_are_commodity_sleeve():
    assert is_commodity_etf("SLV")
    assert is_commodity_etf("gld")
    assert "SLV" in COMMODITY_ETFS
    assert is_alt_symbol("SLV")
    assert is_alt_symbol("BTC-USD")
    assert is_alt_symbol("BTCUSD")
    from crypto_universe import is_crypto_symbol, same_crypto, alpaca_symbol, yahoo_symbol

    assert is_crypto_symbol("BTCUSD")
    assert alpaca_symbol("BTCUSD") == "BTC/USD"
    assert yahoo_symbol("BTCUSD") == "BTC-USD"
    assert same_crypto("BTCUSD", "BTC/USD")
    assert same_crypto("BTCUSD", "BTC-USD")


def test_get_position_matches_compact_btcusd(monkeypatch):
    import alpaca_broker as ab

    monkeypatch.setattr(
        ab,
        "list_positions",
        lambda: [{"symbol": "BTCUSD", "qty": "0.03", "market_value": "2600"}],
    )
    pos = ab.get_position("BTC-USD")
    assert pos is not None
    assert pos["symbol"] == "BTCUSD"


def test_alt_scan_includes_silver_and_btc(monkeypatch):
    monkeypatch.setenv("TRADE_ALTS", "true")
    monkeypatch.setenv("TRADE_CRYPTO", "true")
    monkeypatch.setenv("TRADE_COMMODITIES", "true")
    syms = alt_scan_symbols()
    assert "SLV" in syms
    assert "BTC-USD" in syms
    assert "POL-USD" in syms


def test_tradeable_instrument_crypto_gate(monkeypatch):
    monkeypatch.setenv("TRADE_ALTS", "true")
    monkeypatch.setenv("TRADE_CRYPTO", "false")
    assert is_tradeable_instrument("BTC-USD") is False
    monkeypatch.setenv("TRADE_CRYPTO", "true")
    assert is_tradeable_instrument("BTC-USD") is True
