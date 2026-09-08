"""Family horizon schedule tests."""

from analytics.family_horizon_schedule import horizon_schedules, schedule_for_label


def test_one_day_schedule():
    sch = schedule_for_label("one_day")
    assert sch is not None
    assert sch.hold_days == 1
    assert sch.buy_et == "09:00"
    assert sch.sell_et == "15:45"


def test_all_horizons_have_schedule():
    schedules = horizon_schedules()
    assert len(schedules) >= 7
    for label in (
        "one_day",
        "one_week",
        "one_month",
        "six_months",
        "one_year",
        "five_years",
        "ten_years",
    ):
        assert label in schedules


def test_legacy_label_alias():
    assert schedule_for_label("next_trading_day") is not None
    assert schedule_for_label("two_months") is not None
    assert schedule_for_label("two_months").hold_days == 126
