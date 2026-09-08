#!/usr/bin/env python3
"""Generate expanded macro playbooks for all 50 industries."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "macro_playbook_data.py"

# Load MASTER from handler generator without executing side effects
_spec_path = Path(__file__).resolve().parent / "_generate_industry_handlers.py"
_spec = importlib.util.spec_from_file_location("ind_gen", _spec_path)
_mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)
MASTER = _mod.MASTER

MODE_EVENTS: dict[str, list[tuple[str, tuple[float, float, float, str]]]] = {
    "inverse_rates": [
        ("rate_hike", (-0.18, -0.04, -0.04, "bond_yield_competition")),
        ("rate_cut", (0.16, 0.04, 0.04, "yield_proxy_bid")),
        ("yield_spike", (-0.12, -0.03, -0.03, "duration_pain")),
        ("fed_pivot_dovish", (0.14, 0.05, 0.03, "duration_relief")),
    ],
    "follow_nasdaq": [
        ("rate_hike", (-0.04, -0.06, -0.14, "growth_multiple_compress")),
        ("nasdaq_rally", (0.0, 0.06, 0.22, "beta_rally")),
        ("nasdaq_selloff", (0.0, -0.08, -0.2, "beta_drawdown")),
        ("ai_capex_up", (0.0, 0.12, 0.25, "tech_spend_cycle")),
    ],
    "event_driven": [
        ("fda_approval", (0.0, 0.0, 0.12, "binary_positive")),
        ("trial_failure", (0.0, 0.0, -0.18, "binary_negative")),
        ("offering_dilution", (-0.02, -0.04, -0.08, "capital_raise")),
        ("partnership_deal", (0.0, 0.05, 0.08, "collaboration_premium")),
    ],
    "defensive": [
        ("recession_fear", (0.04, -0.08, -0.06, "flight_to_quality")),
        ("risk_on_rally", (-0.02, 0.06, 0.04, "cyclical_rotation_out")),
        ("vix_spike", (0.06, -0.04, -0.08, "defensive_bid")),
        ("consumer_weakness", (0.03, -0.06, -0.02, "staples_relative")),
    ],
    "commodity": [
        ("commodity_spike", (0.04, 0.12, 0.02, "input_or_output_beta")),
        ("commodity_crash", (-0.03, -0.1, -0.02, "margin_relief_or_pain")),
        ("dollar_spike", (-0.04, -0.08, 0.0, "usd_inverse_commodity")),
        ("supply_disruption", (0.05, 0.1, 0.0, "scarcity_premium")),
    ],
    "hybrid": [
        ("rate_hike", (-0.06, -0.04, -0.08, "mixed_duration_growth")),
        ("pmi_up", (0.04, 0.1, 0.06, "cycle_and_beta")),
        ("pmi_down", (-0.03, -0.08, -0.05, "demand_softness")),
        ("guidance_raise", (0.02, 0.08, 0.05, "operating_leverage")),
    ],
    "follow_market": [
        ("risk_on", (0.02, 0.08, 0.06, "beta_risk_on")),
        ("risk_off", (-0.02, -0.06, -0.05, "beta_risk_off")),
        ("earnings_beat_sector", (0.0, 0.06, 0.04, "peer_sympathy")),
        ("earnings_miss_sector", (0.0, -0.06, -0.04, "peer_sympathy_neg")),
    ],
}

COMMODITY_EVENT_MAP: dict[str, list[tuple[str, tuple[float, float, float, str]]]] = {
    "restaurants_food": [
        ("beef_spike", (-0.08, 0.0, 0.0, "protein_cost_margin")),
        ("wheat_spike", (-0.06, 0.0, 0.0, "grain_input")),
        ("wage_hike", (-0.1, 0.0, 0.0, "labor_margin")),
        ("traffic_up", (0.08, 0.05, 0.0, "same_store_strength")),
    ],
    "packaged_foods": [
        ("corn_spike", (-0.06, 0.0, 0.0, "ag_input")),
        ("glp1_headwind", (-0.1, 0.0, 0.0, "snacking_fear")),
        ("pricing_power", (0.08, 0.02, 0.0, "brand_pricing")),
    ],
    "integrated_oil_gas": [
        ("opec_cut", (0.05, 0.1, 0.05, "crude_rally")),
        ("wti_spike", (0.08, 0.12, 0.06, "commodity_beta")),
        ("demand_fear", (-0.05, -0.15, -0.08, "recession_oil")),
    ],
    "metals_mining": [
        ("china_stimulus", (0.05, 0.2, 0.05, "copper_demand")),
        ("lme_draw", (0.08, 0.12, 0.0, "supply_tight")),
        ("dollar_spike", (-0.05, -0.1, 0.0, "commodity_inverse_usd")),
    ],
    "semiconductors": [
        ("export_ban", (-0.05, -0.15, -0.25, "trade_war")),
        ("inventory_glut", (0.0, -0.2, -0.15, "cycle_down")),
        ("ai_capex_up", (0.0, 0.2, 0.3, "hyperscaler_spend")),
    ],
    "diversified_banks": [
        ("fed_hike", (0.12, 0.05, 0.0, "nim_expand")),
        ("credit_fear", (-0.15, -0.1, -0.05, "cecl_fear")),
        ("steepening", (0.08, 0.03, 0.0, "curve_steepen")),
    ],
    "regional_banks": [
        ("deposit_run", (-0.25, -0.15, -0.1, "systemic_fear")),
        ("cre_stress", (-0.15, -0.1, 0.0, "cre_exposure")),
    ],
    "biotech": [
        ("fda_approval", (0.0, 0.0, 0.15, "binary_positive")),
        ("trial_failure", (0.0, 0.0, -0.2, "binary_negative")),
    ],
}


def _custom_events(spec: dict) -> list[tuple[str, tuple[float, float, float, str]]]:
    iid = spec["id"]
    mode = spec["mode"]
    base = list(MODE_EVENTS.get(mode, MODE_EVENTS["follow_market"]))
    extra = list(COMMODITY_EVENT_MAP.get(iid, []))
    # Industry-specific from bull/bear keywords
    for phrase in (spec.get("events_bull") or [])[:2]:
        key = phrase.replace(" ", "_")[:28]
        extra.append((key, (0.0, 0.05, 0.04, f"bull_event:{phrase[:20]}")))
    for phrase in (spec.get("events_bear") or [])[:2]:
        key = phrase.replace(" ", "_")[:28]
        extra.append((key, (0.0, -0.05, -0.04, f"bear_event:{phrase[:20]}")))
    merged: dict[str, tuple[float, float, float, str]] = {}
    for ev, tpl in base + extra:
        merged[ev] = tpl
    return list(merged.items())


def _headline_rules(spec: dict) -> list[tuple[str, str]]:
    rules: list[tuple[str, str]] = []
    for phrase in spec.get("bull") or []:
        rules.append((phrase[:40], phrase.replace(" ", "_")[:28]))
    for phrase in spec.get("bear") or []:
        rules.append((phrase[:40], phrase.replace(" ", "_")[:28]))
    for phrase in spec.get("commodities") or []:
        rules.append((phrase[:40], f"{phrase}_move"))
    for phrase in spec.get("events_bull") or []:
        rules.append((phrase[:40], phrase.replace(" ", "_")[:28]))
    for phrase in spec.get("events_bear") or []:
        rules.append((phrase[:40], phrase.replace(" ", "_")[:28]))
    return rules[:24]


def generate() -> None:
    lines: list[str] = [
        '"""Auto-generated macro playbooks — one profile per industry bucket."""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Any",
        "",
        "# event -> (rate_delta, expansion_delta, nasdaq_delta, note)",
        "PLAYBOOKS: dict[str, dict[str, tuple[float, float, float, str]]] = {",
    ]
    profile_lines: list[str] = ["INDUSTRY_PROFILES: dict[str, dict[str, Any]] = {"]
    rule_lines: list[str] = ["HEADLINE_EVENT_RULES: dict[str, list[tuple[str, str]]] = {"]

    for spec in MASTER:
        iid = spec["id"]
        events = _custom_events(spec)
        lines.append(f'    "{iid}": {{')
        profile_lines.append(f'    "{iid}": {{')
        profile_lines.append(f'        "name": {spec["name"]!r},')
        profile_lines.append(f'        "mode": {spec["mode"]!r},')
        profile_lines.append(f'        "etf": {spec["etf"]!r},')
        profile_lines.append(f'        "leaders": {list(spec.get("leaders") or ())!r},')
        profile_lines.append(f'        "notes": {spec.get("notes", "")!r},')
        profile_lines.append(f'        "event_count": {len(events)},')
        profile_lines.append("    },")
        for ev, tpl in events:
            lines.append(f'        "{ev}": {tpl!r},')
        lines.append("    },")
        rules = _headline_rules(spec)
        rule_lines.append(f'    "{iid}": {rules!r},')

    lines.append("}")
    profile_lines.append("}")
    rule_lines.append("}")

    global_rules = [
        ("fda approv", "fda_approval"),
        ("trial fail", "trial_failure"),
        ("rate hike", "rate_hike"),
        ("rate cut", "rate_cut"),
        ("fed pivot", "fed_pivot_dovish"),
        ("opec", "opec_cut"),
        ("export ban", "export_ban"),
        ("beef", "beef_spike"),
        ("wheat", "wheat_spike"),
        ("deposit run", "deposit_run"),
        ("antitrust", "antitrust"),
        ("heat wave", "heat_wave"),
        ("china stimulus", "china_stimulus"),
        ("inventory glut", "inventory_glut"),
        ("ai capex", "ai_capex_up"),
        ("yield spike", "yield_spike"),
        ("vix spike", "vix_spike"),
        ("recession", "recession_fear"),
        ("guidance raise", "guidance_raise"),
        ("earnings beat", "earnings_beat_sector"),
    ]
    lines.extend(
        [
            "",
            f"GLOBAL_HEADLINE_RULES: list[tuple[str, str]] = {global_rules!r}",
            "",
            *profile_lines,
            "",
            *rule_lines,
        ]
    )
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(lines)} lines, {len(MASTER)} industries)")


if __name__ == "__main__":
    generate()
