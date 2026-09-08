"""Macro event playbooks per industry — rate, PMI, commodity, regulatory shocks."""

from __future__ import annotations

from typing import Any

import numpy as np

from analytics.industries.macro_playbook_data import (
    GLOBAL_HEADLINE_RULES,
    HEADLINE_EVENT_RULES,
    INDUSTRY_PROFILES,
    PLAYBOOKS,
)


def apply_playbook(industry_id: str, event: str) -> dict[str, Any]:
    book = PLAYBOOKS.get(industry_id, {})
    hit = book.get(event)
    if not hit:
        return {"applied": False, "event": event, "industry_id": industry_id}
    rate_d, exp_d, ndx_d, note = hit
    return {
        "applied": True,
        "event": event,
        "industry_id": industry_id,
        "rate_delta": rate_d,
        "expansion_delta": exp_d,
        "nasdaq_delta": ndx_d,
        "note": note,
        "combined_delta": float(rate_d + exp_d * 0.5 + ndx_d * 0.35),
    }


def infer_events_from_headlines(headlines: list[str], industry_id: str | None = None) -> list[str]:
    text = " ".join(headlines).lower()
    events: list[str] = []
    rules = list(GLOBAL_HEADLINE_RULES)
    if industry_id:
        rules.extend(HEADLINE_EVENT_RULES.get(industry_id, []))
    for needle, ev in rules:
        if needle in text and ev not in events:
            events.append(ev)
    return events


def playbook_tilt(industry_id: str, headlines: list[str]) -> float:
    total = 0.0
    for ev in infer_events_from_headlines(headlines, industry_id):
        r = apply_playbook(industry_id, ev)
        if r.get("applied"):
            total += float(r.get("combined_delta") or 0.0)
    return float(np.tanh(total * 2.0))


def industry_profile(industry_id: str) -> dict[str, Any]:
    return dict(INDUSTRY_PROFILES.get(industry_id, {}))
