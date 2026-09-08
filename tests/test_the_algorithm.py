from analytics.order_fingerprint import recently_cancelled, recently_submitted, record_cancel, record_submit
from analytics.the_algorithm import refine_live
from alpaca_broker import fortress_buy_should_cancel


def test_cancel_fingerprint_blocks_repeat(tmp_path, monkeypatch):
    monkeypatch.setenv("CANCEL_FINGERPRINT_FILE", str(tmp_path / "fp.json"))
    monkeypatch.setenv("REBUY_AFTER_CANCEL_SEC", "600")
    assert not recently_cancelled("INTU")
    record_cancel("INTU", side="buy", reason="ioc_miss")
    assert recently_cancelled("INTU")
    assert not recently_cancelled("MSFT")


def test_submit_fingerprint_blocks_repeat_buy(tmp_path, monkeypatch):
    monkeypatch.setenv("CANCEL_FINGERPRINT_FILE", str(tmp_path / "fp.json"))
    monkeypatch.setenv("REBUY_AFTER_SUBMIT_SEC", "90")
    assert not recently_submitted("AAPL")
    record_submit("AAPL", side="buy")
    assert recently_submitted("AAPL", side="buy")
    assert not recently_submitted("MSFT")


def test_algorithm_skips_recent_cancel(tmp_path, monkeypatch):
    monkeypatch.setenv("CANCEL_FINGERPRINT_FILE", str(tmp_path / "fp.json"))
    monkeypatch.setenv("USE_THE_ALGORITHM", "true")
    monkeypatch.setenv("USE_VALUE_INVESTING", "false")
    record_cancel("NOW", side="buy")
    p, meta = refine_live("NOW", 0.81)
    assert p == 0.5
    assert meta.get("skip_buy") is True


def test_algorithm_keeps_high_p_without_cancel(tmp_path, monkeypatch):
    monkeypatch.setenv("CANCEL_FINGERPRINT_FILE", str(tmp_path / "fp.json"))
    monkeypatch.setenv("USE_THE_ALGORITHM", "true")
    monkeypatch.setenv("USE_VALUE_INVESTING", "false")
    p, meta = refine_live("AAPL", 0.70)
    assert 0.4 <= p <= 0.99
    assert meta.get("algorithm") is True
    assert not meta.get("skip_buy")


def test_offlist_cancel_default_off(monkeypatch):
    monkeypatch.setenv("FORTRESS_CANCEL_OFFLIST", "false")
    keep = {"AAPL"}
    assert not fortress_buy_should_cancel(
        {"side": "buy", "symbol": "MSFT", "client_order_id": "ft-1"}, keep
    )


def test_offlist_cancel_opt_in(monkeypatch):
    monkeypatch.setenv("FORTRESS_CANCEL_OFFLIST", "true")
    keep = {"AAPL"}
    assert fortress_buy_should_cancel(
        {"side": "buy", "symbol": "MSFT", "client_order_id": "ft-1"}, keep
    )
    assert not fortress_buy_should_cancel(
        {"side": "buy", "symbol": "MSFT", "client_order_id": "obi-abc"}, keep
    )
