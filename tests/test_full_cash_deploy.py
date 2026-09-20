"""100% of equity in the book — leftover cash, not leftover 4× buying power."""

from fortress_portfolio import (
    allocate_idle_cash_to_holds,
    deploy_budget_usd,
    idle_cash_fill_active,
)


def test_idle_cash_fill_when_book_is_a_fraction(monkeypatch):
    monkeypatch.setenv("FORTRESS_FILL_IDLE_CASH", "true")
    monkeypatch.setenv("FORTRESS_TARGET_DEPLOY_FRAC", "1.0")
    monkeypatch.setenv("FORTRESS_MAX_GROSS_FRAC", "1.0")
    assert idle_cash_fill_active({"equity": 72_063.0, "gross_mv": 53_000.0}) is True
    assert idle_cash_fill_active({"equity": 72_063.0, "gross_mv": 71_500.0}) is False


def test_deploy_budget_is_the_equity_gap_not_margin(monkeypatch):
    monkeypatch.setenv("FORTRESS_TARGET_DEPLOY_USE_EQUITY", "true")
    monkeypatch.setenv("FORTRESS_TARGET_DEPLOY_FRAC", "1.0")
    monkeypatch.setenv("FORTRESS_MAX_GROSS_FRAC", "1.0")
    monkeypatch.setenv("FORTRESS_BP_USE_FRAC", "1.0")
    monkeypatch.setenv("FORTRESS_FILL_IDLE_CASH", "true")
    monkeypatch.setenv("USE_BUYING_POWER", "true")
    monkeypatch.setenv("FORTRESS_EXPOSURE_USE_BP", "false")
    bud = deploy_budget_usd(
        {
            "equity": 72_000.0,
            "buying_power": 224_000.0,
            "gross_mv": 53_000.0,
            "multiplier": 4.0,
        }
    )
    assert bud["use_eq_target"] is True
    assert abs(bud["target_usd"] - 72_000.0) < 1.0
    assert abs(bud["budget"] - 19_000.0) < 1.0
    assert bud["budget"] < 50_000.0  # never the leftover 4× BP


def test_allocate_idle_cash_fills_holds_up_to_single_cap():
    extra = allocate_idle_cash_to_holds(
        19_000.0,
        positions=[
            {"symbol": "AAPL", "qty": "10", "market_value": "4000"},
            {"symbol": "SPY", "qty": "5", "market_value": "3000"},
            {"symbol": "NVDA", "qty": "8", "market_value": "5000"},
        ],
        max_single_usd=7_200.0,
        min_n=200.0,
        banned={"SPY"},
    )
    assert "SPY" not in extra
    assert extra["AAPL"] == 3_200.0
    assert extra["NVDA"] == 2_200.0
    assert abs(sum(extra.values()) - 5_400.0) < 1e-6


def test_allocate_skips_losers_and_prefers_crypto():
    extra = allocate_idle_cash_to_holds(
        10_000.0,
        positions=[
            {"symbol": "LCID", "qty": "19", "market_value": "98", "unrealized_plpc": "-0.08"},
            {"symbol": "BTCUSD", "qty": "0.03", "market_value": "2600", "unrealized_plpc": "0.09"},
            {"symbol": "AAPL", "qty": "10", "market_value": "4000", "unrealized_plpc": "0.12"},
        ],
        max_single_usd=12_000.0,
        min_n=200.0,
    )
    assert "LCID" not in extra
    assert extra["BTCUSD"] == 9_400.0
    assert extra.get("AAPL", 0) == 600.0


def test_allocate_crypto_uses_18pct_cap_not_10pct():
    extra = allocate_idle_cash_to_holds(
        10_000.0,
        positions=[
            {
                "symbol": "BTCUSD",
                "qty": "0.1",
                "market_value": "8000",
                "unrealized_plpc": "0.02",
            }
        ],
        max_single_usd=7_100.0,
        min_n=200.0,
        equity=71_000.0,
    )
    # 18% of 71k ≈ $12,780; room above the $8k hold is not the 10% equity cap.
    assert extra["BTCUSD"] > 4_000
    assert extra["BTCUSD"] < 5_000


def test_idle_split_reserves_crypto_gap_before_stocks(monkeypatch):
    monkeypatch.setenv("FORTRESS_CRYPTO_OVERNIGHT_SCAN", "BTC-USD,ETH-USD,SOL-USD")
    monkeypatch.setenv("FORTRESS_CRYPTO_BOOK_FRAC", "0.50")
    monkeypatch.setenv("FORTRESS_NEW_CASH_CRYPTO_FRAC", "0.50")
    monkeypatch.setenv("FORTRESS_CRYPTO_MAX_SINGLE_FRAC", "0.18")
    from fortress_portfolio import allocate_idle_cash_split

    extra = allocate_idle_cash_split(
        21_598.0,
        positions=[
            {"symbol": "BTCUSD", "qty": "0.1", "market_value": "12755", "unrealized_plpc": "0.01"},
            {"symbol": "ETHUSD", "qty": "5", "market_value": "12673", "unrealized_plpc": "-0.001"},
            {"symbol": "AAPL", "qty": "10", "market_value": "5564", "unrealized_plpc": "1.4"},
            {"symbol": "MSFT", "qty": "10", "market_value": "6820", "unrealized_plpc": "1.7"},
            {"symbol": "GOOGL", "qty": "10", "market_value": "2530", "unrealized_plpc": "1.2"},
            {"symbol": "AMZN", "qty": "10", "market_value": "2518", "unrealized_plpc": "1.1"},
        ],
        equity=71_394.0,
        max_single_usd=7_139.0,
        min_n=150.0,
        hard_max=12_800.0,
        banned={"SPY"},
    )
    assert extra.get("SOL-USD", 0) > 9_000
    assert extra.get("AAPL", 0) + extra.get("GOOGL", 0) + extra.get("AMZN", 0) > 5_000
    assert "BTCUSD" not in extra  # already at 18% cap


def test_idle_addon_allows_winners_not_losers(monkeypatch):
    from types import SimpleNamespace

    from fortress_portfolio import can_add_position

    monkeypatch.setenv("FORTRESS_ALLOW_ADD_ON", "false")
    monkeypatch.setenv("FORTRESS_FILL_IDLE_CASH", "true")
    monkeypatch.setenv("FORTRESS_TARGET_DEPLOY_FRAC", "1.0")
    monkeypatch.setenv("FORTRESS_MAX_GROSS_FRAC", "1.0")
    monkeypatch.setenv("FORTRESS_MAX_SINGLE_FRAC", "0.10")
    monkeypatch.setenv("FORTRESS_CRYPTO_MAX_SINGLE_FRAC", "0.18")
    monkeypatch.setenv("FORTRESS_SINGLE_CAP_USE_EQUITY", "true")
    monkeypatch.setenv("USE_BUYING_POWER", "false")
    monkeypatch.setattr(
        "intel.downward_pressure.blocks_new_buy",
        lambda *_a, **_k: (False, ""),
    )

    def _pos(sym: str):
        s = str(sym).upper()
        if "LCID" in s:
            return {"unrealized_plpc": -0.08, "qty": 19, "avg_entry_price": 5.7}
        return {"unrealized_plpc": 0.09, "qty": 0.03, "avg_entry_price": 74000}

    monkeypatch.setattr("alpaca_broker.get_position", _pos)
    monkeypatch.setattr(
        "alpaca_broker.get_account",
        lambda: {"equity": 72_000.0, "buying_power": 42_000.0, "multiplier": 1.0},
    )
    monkeypatch.setattr("alpaca_broker.intraday_buying_power", lambda _a: 42_000.0)
    rm = SimpleNamespace(equity=72_000.0, total_gross_exposure=lambda: 29_000.0)
    rm.can_open = lambda *_a, **_k: True  # noqa: E731
    assert can_add_position(rm, "BTCUSD", 2_500.0, 80_000.0, 70_000.0, existing_mv=2_650.0) is True
    assert can_add_position(rm, "LCID", 200.0, 5.0, 4.0, existing_mv=98.0) is False


def test_addon_on_still_refuses_red_when_winners_only(monkeypatch):
    from types import SimpleNamespace

    from fortress_portfolio import can_add_position

    monkeypatch.setenv("FORTRESS_ALLOW_ADD_ON", "true")
    monkeypatch.setenv("FORTRESS_WINNERS_ONLY", "true")
    monkeypatch.setenv("FORTRESS_MIN_ADD_GAIN", "0")
    monkeypatch.setenv("FORTRESS_SINGLE_CAP_USE_EQUITY", "true")
    monkeypatch.setenv("USE_BUYING_POWER", "false")
    monkeypatch.setattr(
        "intel.downward_pressure.blocks_new_buy",
        lambda *_a, **_k: (False, ""),
    )

    def _pos(sym: str):
        s = str(sym).upper()
        if "LCID" in s:
            return {"unrealized_plpc": -0.08, "qty": 19, "avg_entry_price": 5.7}
        return {"unrealized_plpc": 0.09, "qty": 0.03, "avg_entry_price": 74000}

    monkeypatch.setattr("alpaca_broker.get_position", _pos)
    rm = SimpleNamespace(equity=72_000.0, total_gross_exposure=lambda: 29_000.0)
    rm.can_open = lambda *_a, **_k: True  # noqa: E731
    assert can_add_position(rm, "LCID", 200.0, 5.0, 4.0, existing_mv=98.0) is False


def test_fortress_keeps_held_idle_when_scan_scores_nothing():
    from pathlib import Path

    text = Path(__file__).resolve().parents[1].joinpath("fortress_live.py").read_text()
    assert "skip idle-cash fill — scan scored 0 ticks this pass" not in text
    assert "keep held idle fills" in text
    assert "FORTRESS_CRYPTO_TICK_TIMEOUT_SEC" in text
    assert 'os.environ["FORTRESS_LITE_INTEL"] = "true"' in text
    assert "weekend idle-cash" in text
    assert "weekend fill — keep cooldown holds" in text
    assert "lite tick" in text
    assert "overnight_cash_deploy can make buy_ok true" in text
