"""WMT 2026-08-20 counterfactual — no network."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from analytics.earnings_gap_guard import (
    block_stick_buy,
    decide,
    print_has_released,
    prioritize_print_window_holdings,
    session_gap_from_pos,
    should_kill_gap,
)

ET = ZoneInfo("America/New_York")

# WMT Q2 FY27 BMO 2026-08-20: prev close ~114.30, dump to ~104, 62 sh, ~9% of book.
WMT_PREV = 114.30
WMT_PX = 104.00
WMT_ENTRY = 114.93
WMT_QTY = 62.0
WMT_EQUITY = 71_100.0
WMT_GAP = WMT_PX / WMT_PREV - 1.0  # ≈ −9.0%
BMO_OPEN = datetime(2026, 8, 20, 10, 0, tzinfo=ET)
BMO_PRE = datetime(2026, 8, 20, 7, 0, tzinfo=ET)
AMC_RTH = datetime(2026, 8, 20, 14, 0, tzinfo=ET)
AMC_POST = datetime(2026, 8, 20, 16, 30, tzinfo=ET)
DTE1 = datetime(2026, 8, 19, 15, 0, tzinfo=ET)


@pytest.fixture
def gap_env(monkeypatch):
    monkeypatch.setenv("EARNINGS_GAP_GUARD", "true")
    monkeypatch.setenv("EARNINGS_GAP_KILL_PCT", "-0.035")
    monkeypatch.setenv("EARNINGS_EVENT_MAX_EQUITY_FRAC", "0.045")
    monkeypatch.setenv("FORTRESS_EARNINGS_SEVERE_ABORT_LOSS", "0.045")
    monkeypatch.setenv("EARNINGS_BUY_DAY_OF", "true")


def test_wmt_bmo_dump_kills(gap_env):
    mv = WMT_QTY * WMT_PX
    gain = (WMT_PX - WMT_ENTRY) / WMT_ENTRY
    dec = decide(
        dte=0,
        dse=None,
        hour="bmo",
        gap=WMT_GAP,
        gain_vs_entry=gain,
        mv=mv,
        equity=WMT_EQUITY,
        now_et=BMO_OPEN,
    )
    assert WMT_GAP <= -0.08
    assert dec.kill is True
    assert dec.block_add is True
    assert dec.trim_frac == 1.0
    assert should_kill_gap(dte=0, dse=None, hour="bmo", gap=WMT_GAP, now_et=BMO_PRE) is True


def test_wmt_premarket_also_kills(gap_env):
    assert should_kill_gap(dte=0, dse=None, hour="bmo", gap=WMT_GAP, now_et=BMO_PRE) is True


def test_amc_daytime_red_does_not_kill(gap_env):
    """SBUX-style AMC: a −4% RTH tape before the print is not the print gap."""
    assert should_kill_gap(dte=0, dse=None, hour="amc", gap=-0.04, now_et=AMC_RTH) is False
    dec = decide(dte=0, dse=None, hour="amc", gap=-0.04, mv=3000, equity=WMT_EQUITY, now_et=AMC_RTH)
    assert dec.kill is False


def test_amc_after_close_kills(gap_env):
    assert should_kill_gap(dte=0, dse=None, hour="amc", gap=-0.04, now_et=AMC_POST) is True


def test_unknown_hour_severe_dump_still_kills(gap_env):
    """Missing Finnhub hour must not recreate WMT (RTH, −9%, dte=0)."""
    assert should_kill_gap(dte=0, dse=None, hour=None, gap=WMT_GAP, now_et=BMO_OPEN) is True
    # Mild −3.6% with unknown hour in RTH is not assumed BMO.
    assert should_kill_gap(dte=0, dse=None, hour=None, gap=-0.036, now_et=BMO_OPEN) is False


def test_pre_print_trim_caps_not_flatten(gap_env):
    mv = 0.091 * WMT_EQUITY
    dec = decide(
        dte=1,
        dse=None,
        hour="bmo",
        gap=0.0,
        mv=mv,
        equity=WMT_EQUITY,
        now_et=DTE1,
    )
    assert dec.kill is False
    assert 0.45 <= dec.trim_frac <= 0.55
    leftover = mv * (1.0 - dec.trim_frac)
    assert leftover / WMT_EQUITY == pytest.approx(0.045, abs=0.002)


def test_quiet_name_no_kill(gap_env):
    dec = decide(
        dte=5,
        dse=None,
        hour="bmo",
        gap=-0.01,
        mv=0.03 * WMT_EQUITY,
        equity=WMT_EQUITY,
        now_et=BMO_OPEN,
    )
    assert dec.kill is False
    assert dec.trim_frac == 0.0
    assert dec.block_add is False


def test_stick_block_after_bmo_print(gap_env):
    assert print_has_released("bmo", 0, None, now_et=BMO_OPEN) is True
    assert block_stick_buy(dte=0, dse=None, hour="bmo", gap=0.0, now_et=BMO_OPEN) is True
    # Pre-print BMO with a flat tape: STICK still allowed (SBUX analog is AMC daytime).
    assert print_has_released("bmo", 0, None, now_et=BMO_PRE) is False
    assert block_stick_buy(dte=0, dse=None, hour="bmo", gap=0.0, now_et=BMO_PRE) is False
    # Red premarket gap blocks add even before 08:00.
    assert block_stick_buy(dte=0, dse=None, hour="bmo", gap=-0.02, now_et=BMO_PRE) is True


def test_amc_daytime_stick_still_on(gap_env):
    assert print_has_released("amc", 0, None, now_et=AMC_RTH) is False
    assert block_stick_buy(dte=0, dse=None, hour="amc", gap=0.0, now_et=AMC_RTH) is False
    assert print_has_released("amc", 0, None, now_et=AMC_POST) is True


def test_dte1_flat_does_not_block_stick(gap_env):
    assert block_stick_buy(dte=1, dse=None, hour="bmo", gap=0.0, now_et=DTE1) is False
    assert print_has_released("bmo", 1, None, now_et=DTE1) is False


def test_session_gap_prefers_intraday_not_entry():
    pos = {
        "avg_entry_price": WMT_ENTRY,
        "current_price": WMT_PX,
        "lastday_price": WMT_PREV,
        "unrealized_plpc": (WMT_PX - WMT_ENTRY) / WMT_ENTRY,
        "unrealized_intraday_plpc": WMT_GAP,
        "change_today": WMT_GAP,
    }
    g = session_gap_from_pos(pos)
    assert g == pytest.approx(WMT_GAP, abs=1e-6)
    g2 = session_gap_from_pos({"current_price": WMT_PX}, last=WMT_PX, prev_close=WMT_PREV)
    assert g2 == pytest.approx(WMT_GAP, abs=1e-6)


def test_holdings_tick_first_even_when_underdeploy():
    # Underdeploy recap puts fresh names first; guard must put WMT back at tick 1
    # without burying the fill list behind every other hold.
    ordered = prioritize_print_window_holdings(
        ["NVDA", "AAPL", "WMT", "MSFT"],
        ["WMT", "AAPL"],
        ["WMT"],
    )
    assert ordered[0] == "WMT"
    assert ordered[1] == "NVDA"
    assert "AAPL" in ordered


def test_thesis_death_gap_kill_one_vote(gap_env, monkeypatch):
    from analytics.conviction_exit import thesis_death_confirmed

    monkeypatch.setattr("analytics.conviction_exit._pressure_score", lambda _s: 0.0)

    def _plan(_sym, **_k):
        return {
            "days_to": 0,
            "days_since": None,
            "hour": "bmo",
            "report_session": "bmo",
            "fear_dump_watch": True,
            "trim_bias": 0.35,
        }

    monkeypatch.setattr("intel.historical_events.holdings_earnings_plan", _plan)
    dead, why = thesis_death_confirmed(
        "WMT",
        p_adj=0.65,
        gain=-0.094,
        pred=1,
        session_gap=WMT_GAP,
        now_et=BMO_OPEN,
    )
    assert dead is True
    assert "earnings_gap_kill" in why


def test_stick_plan_dte1_still_encourages(gap_env, monkeypatch):
    from intel import historical_events as he

    he._MEM.clear()

    def _ev(_sym, **_k):
        return {
            "days_to": 1,
            "days_since": None,
            "hour": "bmo",
            "session": "bmo",
            "avg_abs_move_1d": 0.02,
            "avg_abs_move_5d": 0.04,
            "next_date": "2026-08-21",
        }

    monkeypatch.setattr(he, "earnings_event", _ev)
    monkeypatch.setattr(he, "_apply_time_override", lambda plan, _s, **_k: plan)
    from datetime import date

    plan = he.holdings_earnings_plan("WMT", as_of=date(2026, 8, 20), is_holding=True, now_et=DTE1)
    assert plan["stick_to_prediction"] is True
    assert plan["encourage_pre_momentum"] is True
    assert plan["allow_overnight_hold"] is True


def test_stick_plan_off_after_bmo_print(gap_env, monkeypatch):
    from intel import historical_events as he

    he._MEM.clear()

    def _ev(_sym, **_k):
        return {
            "days_to": 0,
            "days_since": None,
            "hour": "bmo",
            "session": "bmo",
            "avg_abs_move_1d": 0.03,
            "avg_abs_move_5d": 0.05,
            "next_date": "2026-08-20",
        }

    monkeypatch.setattr(he, "earnings_event", _ev)
    monkeypatch.setattr(he, "_apply_time_override", lambda plan, _s, **_k: plan)
    from datetime import date

    plan = he.holdings_earnings_plan(
        "WMT", as_of=date(2026, 8, 20), is_holding=True, now_et=BMO_OPEN
    )
    assert plan["stick_to_prediction"] is False
    assert plan["encourage_pre_momentum"] is False
    assert plan["allow_overnight_hold"] is True
    assert plan["fear_dump_watch"] is True
    assert plan["print_released"] is True


def test_trail_locks_a_winner_that_gives_back(monkeypatch):
    from analytics.conviction_exit import decide_exit

    monkeypatch.setattr(
        "analytics.conviction_exit._trade_row",
        lambda _s: {"mfe": 0.025, "scaled": True},
    )
    d = decide_exit("AAPL", p_adj=0.62, gain=0.016, take_profit_pct=0.035, stop_loss_pct=0.028)
    assert d.action == "take_profit"
    assert "trail" in d.reason


def test_new_high_is_not_trailed_out(monkeypatch):
    from analytics.conviction_exit import decide_exit

    monkeypatch.setenv("FORTRESS_SCALE_OUT_PCT", "0.05")
    monkeypatch.setattr("analytics.conviction_exit._trade_row", lambda _s: {"mfe": 0.02})
    d = decide_exit("AAPL", p_adj=0.70, gain=0.024, take_profit_pct=0.035, stop_loss_pct=0.028)
    assert d.action == "hold"


def test_scale_out_happens_once(monkeypatch):
    from analytics.conviction_exit import decide_exit

    monkeypatch.setenv("FORTRESS_SCALE_OUT_PCT", "0.022")
    monkeypatch.setattr("analytics.conviction_exit._trade_row", lambda _s: {"scaled": True, "mfe": 0.024})
    d = decide_exit("AAPL", p_adj=0.66, gain=0.024, take_profit_pct=0.035, stop_loss_pct=0.028)
    assert d.action == "hold"


def test_early_cut_when_model_has_flipped(monkeypatch):
    from analytics.conviction_exit import decide_exit

    monkeypatch.setattr("analytics.conviction_exit._trade_row", lambda _s: {})
    d = decide_exit("AAPL", p_adj=0.40, gain=-0.013, take_profit_pct=0.035, stop_loss_pct=0.028)
    assert d.action == "stop_loss"
    assert "early_cut" in d.reason
