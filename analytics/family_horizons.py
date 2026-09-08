"""Family forecast horizon definitions — model mapping + ultra-long proxies."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class FamilyHorizonDef:
    label: str
    title: str
    model_prefix: str  # p_daily | p_short | p_long | p_xlong | p_ultra
    hold_days: int
    head_label: str


# Trading-day approximations for calendar labels.
FAMILY_HORIZON_DEFS: list[FamilyHorizonDef] = [
    FamilyHorizonDef("one_day", "1 day", "p_daily", 1, "model_daily"),
    FamilyHorizonDef("one_week", "1 week", "p_short", 5, "model_short"),
    FamilyHorizonDef("one_month", "1 month", "p_long", 21, "model_long"),
    FamilyHorizonDef("six_months", "6 months", "p_xlong", 126, "model_xlong"),
    FamilyHorizonDef("one_year", "1 year", "p_xlong", 252, "model_xlong"),
    FamilyHorizonDef("five_years", "5 years", "p_ultra", 1260, "fundamental_proxy"),
    FamilyHorizonDef("ten_years", "10 years", "p_ultra", 2520, "fundamental_proxy"),
]

# Back-compat aliases (old report / headwind keys)
LABEL_ALIASES: dict[str, str] = {
    "next_trading_day": "one_day",
    "this_week": "one_week",
    "this_month": "one_month",
    "two_months": "six_months",
}


def normalize_label(label: str) -> str:
    key = (label or "").strip().lower()
    return LABEL_ALIASES.get(key, key)


def horizon_defs(*, edition: str | None = None) -> list[FamilyHorizonDef]:
    if not edition:
        return list(FAMILY_HORIZON_DEFS)
    key = normalize_label(edition)
    for d in FAMILY_HORIZON_DEFS:
        if d.label == key:
            return [d]
    raise ValueError(f"Unknown family edition: {edition}")


def horizon_fields(*, edition: str | None = None) -> list[tuple[str, str, str, int]]:
    """(label, title, model_prefix, hold_days) for family_forecast."""
    return [(d.label, d.title, d.model_prefix, d.hold_days) for d in horizon_defs(edition=edition)]


def resolve_model_probability(row: dict, prefix: str) -> tuple[float | None, str]:
    """Return (raw probability, head name) for a horizon model prefix."""
    if prefix == "p_ultra":
        return _ultra_long_probability(row)

    raw_key = f"{prefix}_model_raw"
    legacy = {
        "p_short": "p_short_model",
        "p_long": "p_long_model",
        "p_daily": "p_daily_model",
        "p_xlong": "p_xlong_model",
    }
    head_key = f"{prefix}_head"
    head = str(row.get(head_key) or legacy.get(prefix, prefix))

    raw = row.get(raw_key)
    if raw is None:
        raw = row.get(legacy.get(prefix))
    if raw is None:
        raw = row.get(f"{prefix}_model")
    if raw is None:
        return None, head
    return float(raw), head


def _ultra_long_probability(row: dict) -> tuple[float | None, str]:
    """Multi-year view: xlong model + quality/fundamentals (no 10y ML head yet)."""
    xlong, _ = resolve_model_probability(row, "p_xlong")
    if xlong is None:
        xlong, _ = resolve_model_probability(row, "p_long")
    if xlong is None:
        return None, "fundamental_proxy"

    fund = float(row.get("fund_score") or 0.0)
    quality = float(row.get("quality_score") or 0.0)
    top100 = 1.0 if row.get("top100") else 0.0
    ur = float(row.get("ur_score") or 0.0)
    dip = float(row.get("dip_signal") or 0.0)

    blend = (
        0.55 * float(xlong)
        + 0.15 * max(fund, quality)
        + 0.10 * top100
        + 0.10 * min(1.0, ur * 1.2)
        + 0.10 * dip
    )
    floor = float(os.getenv("FAMILY_ULTRA_LONG_FLOOR", "0.35"))
    cap = float(os.getenv("FAMILY_ULTRA_LONG_CAP", "0.88"))
    return max(floor, min(cap, blend)), "fundamental_proxy"


def _xlong_daily_gap(row: dict) -> float | None:
    daily, _ = resolve_model_probability(row, "p_daily")
    xlong, _ = resolve_model_probability(row, "p_xlong")
    if daily is None or xlong is None:
        return None
    return float(xlong) - float(daily)


def is_bounce_back_candidate(row: dict) -> bool:
    """Full bounce-back thesis: strong xlong vs near-term heads + recovery structure."""
    gap = _xlong_daily_gap(row)
    if gap is None:
        return False
    min_gap = float(os.getenv("FAMILY_BOUNCE_XLONG_GAP", "0.15"))
    if gap < min_gap:
        return False
    if row.get("ur_detected") or str(row.get("ur_rationale") or "") == "undercut_and_rally":
        return True
    if float(row.get("dip_signal") or 0.0) >= float(os.getenv("FAMILY_BOUNCE_MIN_DIP", "0.12")):
        return True
    return gap >= float(os.getenv("FAMILY_BOUNCE_GAP_ONLY", "0.22"))


def short_horizon_blocked(row: dict, *, hold_days: int) -> bool:
    """Bounce names belong on 1–2 month+ holds, not 1 day / 1 week editions.

    When HORIZON_INDEPENDENT, each timeframe is allowed to be right on its own —
    a strong 6-month head does not veto a 1-day trade.
    """
    try:
        from analytics.horizon_picks import horizon_independent

        if horizon_independent():
            return False
    except Exception:
        pass
    if hold_days > 5:
        return False
    if not is_bounce_back_candidate(row):
        return False
    gap = _xlong_daily_gap(row)
    if gap is None:
        return False
    if hold_days <= 1:
        return gap > float(os.getenv("FAMILY_SHORT_AVOID_XLONG_GAP", "0.10"))
    short_p, _ = resolve_model_probability(row, "p_short")
    daily, _ = resolve_model_probability(row, "p_daily")
    xlong, _ = resolve_model_probability(row, "p_xlong")
    short_gap = float(xlong) - float(short_p or daily)
    return short_gap > float(os.getenv("FAMILY_WEEK_AVOID_XLONG_GAP", "0.08"))


def horizon_effective_probability(
    row: dict, prefix: str, *, hold_days: int
) -> tuple[float | None, str]:
    """Family-facing probability — bounce names use xlong-weighted view on 1-month holds."""
    raw, head = resolve_model_probability(row, prefix)
    if raw is None and prefix == "p_xlong":
        fallback, fhead = resolve_model_probability(row, "p_long")
        if fallback is not None:
            return float(fallback), str(fhead or "model_long_fallback")
    try:
        from analytics.horizon_picks import horizon_independent

        if horizon_independent():
            return raw, head
    except Exception:
        pass
    if not is_bounce_back_candidate(row):
        return raw, head

    xlong, xhead = resolve_model_probability(row, "p_xlong")
    if xlong is None:
        return raw, head

    if prefix == "p_long" and hold_days <= 21:
        long_p = float(raw or 0.0)
        w_xlong = float(os.getenv("FAMILY_BOUNCE_MONTH_XLONG_W", "0.65"))
        blend = (1.0 - w_xlong) * long_p + w_xlong * float(xlong)
        return blend, "model_bounce_blend"

    return raw, head


def horizon_timeframe_fit(row: dict, *, hold_days: int) -> float:
    """Boost names that fit the hold window (e.g. ISRG bounce = longer, not 1-day)."""
    try:
        from analytics.horizon_picks import horizon_independent

        if horizon_independent():
            return 0.0
    except Exception:
        pass
    daily, _ = resolve_model_probability(row, "p_daily")
    short_p, _ = resolve_model_probability(row, "p_short")
    xlong, _ = resolve_model_probability(row, "p_xlong")
    if daily is None or xlong is None:
        return 0.0

    gap = float(xlong) - float(daily)
    short_gap = float(xlong) - float(short_p or daily)
    bounce = is_bounce_back_candidate(row)

    if hold_days <= 1 and gap > float(os.getenv("FAMILY_SHORT_AVOID_XLONG_GAP", "0.10")):
        return -0.8
    if hold_days <= 5 and short_gap > float(os.getenv("FAMILY_WEEK_AVOID_XLONG_GAP", "0.08")):
        return -0.5
    if hold_days >= 252:
        return 0.5 if bounce else 0.4
    if hold_days >= 126 and float(xlong) >= float(os.getenv("FAMILY_LONG_MIN_XLONG", "0.58")):
        return 0.85 if bounce else 0.8
    if hold_days >= 21 and gap > 0.08:
        return 0.75 if bounce else 0.6
    return 0.0
