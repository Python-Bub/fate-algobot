"""Family manual trading schedule — buy ~9 AM ET, sell at horizon end (EOD rules)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from analytics.family_horizons import FAMILY_HORIZON_DEFS, normalize_label


@dataclass(frozen=True)
class FamilyHorizonSchedule:
    label: str
    title: str
    hold_days: int
    buy_et: str
    sell_et: str
    sell_rule: str
    instructions: str


def _sell_rule(hold_days: int) -> str:
    if hold_days <= 1:
        return "same_day_eod"
    if hold_days <= 5:
        return "week_eod"
    if hold_days <= 21:
        return "month_eod"
    if hold_days <= 126:
        return "hold_days_eod"
    if hold_days <= 252:
        return "year_eod"
    return "long_term_hold"


def _instructions(title: str, hold_days: int, buy: str, sell: str) -> str:
    buy_s = _fmt_et(buy)
    sell_s = _fmt_et(sell)
    if hold_days <= 1:
        return f"Buy at/after {buy_s} → sell same day before close ({sell_s})."
    if hold_days <= 5:
        return f"Buy at/after {buy_s} → hold through the week, sell Friday at close ({sell_s})."
    if hold_days <= 21:
        return f"Buy at/after {buy_s} → hold ~1 month (~{hold_days} trading days), sell at close on exit day ({sell_s})."
    if hold_days <= 126:
        return f"Buy at/after {buy_s} → hold ~6 months (~{hold_days} trading days), sell at close on exit day ({sell_s})."
    if hold_days <= 252:
        return f"Buy at/after {buy_s} → hold ~1 year (~{hold_days} trading days), sell at close on exit day ({sell_s})."
    if hold_days <= 1260:
        return f"Buy at/after {buy_s} → hold ~5 years (investment horizon), review quarterly; exit at close ({sell_s}) when target met."
    return f"Buy at/after {buy_s} → hold ~10 years (investment horizon), review quarterly; exit at close ({sell_s}) when target met."


def family_buy_et() -> str:
    return os.getenv("FAMILY_BUY_ET", "09:00").strip() or "09:00"


def family_sell_et() -> str:
    return os.getenv("FAMILY_SELL_ET", "15:45").strip() or "15:45"


def horizon_schedules() -> dict[str, FamilyHorizonSchedule]:
    buy = family_buy_et()
    sell = family_sell_et()
    out: dict[str, FamilyHorizonSchedule] = {}
    for d in FAMILY_HORIZON_DEFS:
        out[d.label] = FamilyHorizonSchedule(
            label=d.label,
            title=d.title,
            hold_days=d.hold_days,
            buy_et=buy,
            sell_et=sell,
            sell_rule=_sell_rule(d.hold_days),
            instructions=_instructions(d.title, d.hold_days, buy, sell),
        )
    # Legacy keys → same schedule as new labels
    legacy = {
        "next_trading_day": "one_day",
        "this_week": "one_week",
        "this_month": "one_month",
        "two_months": "six_months",
    }
    for old, new in legacy.items():
        if new in out:
            out[old] = out[new]
    return out


def schedule_for_label(label: str) -> FamilyHorizonSchedule | None:
    key = normalize_label(label)
    return horizon_schedules().get(key) or horizon_schedules().get(label)


def _fmt_et(hhmm: str) -> str:
    parts = hhmm.split(":")
    if len(parts) < 2:
        return hhmm
    h, m = int(parts[0]), int(parts[1])
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix} ET"


def schedule_dict(sch: FamilyHorizonSchedule) -> dict:
    return {
        "buy_et": sch.buy_et,
        "sell_et": sch.sell_et,
        "sell_rule": sch.sell_rule,
        "hold_days": sch.hold_days,
        "instructions": sch.instructions,
        "buy_display": _fmt_et(sch.buy_et),
        "sell_display": _fmt_et(sch.sell_et),
    }
