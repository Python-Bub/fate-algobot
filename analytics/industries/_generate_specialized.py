#!/usr/bin/env python3
"""Generate 50 specialized industry pipeline modules from master specifications."""

from __future__ import annotations

import textwrap
from pathlib import Path

from analytics.industries._generate_industry_handlers import MASTER

ROOT = Path(__file__).resolve().parents[2]
SPECIALIZED_DIR = ROOT / "analytics" / "industries" / "specialized"


def _cls_name(iid: str) -> str:
    return "".join(p.capitalize() for p in iid.split("_")) + "Specialized"


def _indent_block(code: str, spaces: int = 8) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line.strip() else line for line in code.strip().splitlines())


def _macro_gates_body(spec: dict) -> str:
    mode = spec["mode"]
    rate = spec["rate"]
    exp = spec["exp"]
    ndx = spec["ndx"]
    defense = spec["def"]
    iid = spec["id"]

    if mode == "inverse_rates":
        thr = 0.10 + abs(rate) * 0.10
        return (
            f'shock = self._macro(ctx, handler, "rate_shock_20d")\n'
            f'spread = self._macro(ctx, handler, "spread_10y2y")\n'
            f'vix = self._macro(ctx, handler, "vix", 20.0)\n'
            f"rate_thr = {thr:.3f}\n"
            f"if shock > rate_thr or spread < -0.35:\n"
            f'    res.block_long = True\n'
            f'    res.block_reason = "{iid}: rising rates / inverted curve headwind"\n'
            f'    res.macro_gates.append("rate_headwind_block")\n'
            f'    res.pipeline_notes.append(f"rate_shock={{shock:.2f}}")\n'
            f"elif shock < -0.08:\n"
            f"    boost = {abs(rate):.2f} * 0.09\n"
            f"    res.score_delta += boost\n"
            f"    res.p_up_delta += boost * 0.35\n"
            f'    res.macro_gates.append("rate_relief")\n'
            f"if vix > 28 and shock > 0.05:\n"
            f"    res.warn_long = True\n"
            f"    res.score_delta -= 0.03"
        )

    if mode == "event_driven":
        return (
            f'vix = self._macro(ctx, handler, "vix", 20.0)\n'
            f'ndx = self._macro(ctx, handler, "nasdaq_ret_5d")\n'
            f"if vix > 30:\n"
            f"    res.score_delta -= 0.02\n"
            f'    res.pipeline_notes.append("event_vix_elevated")\n'
            f"if ndx < -0.04:\n"
            f"    res.warn_long = True\n"
            f"    res.score_delta -= 0.04 * {ndx:.2f}"
        )

    if mode == "defensive":
        return (
            f'vix = self._macro(ctx, handler, "vix", 20.0)\n'
            f'macro = self._macro(ctx, handler, "macro_score")\n'
            f'pmi = self._macro(ctx, handler, "pmi_score")\n'
            f"if vix > 22:\n"
            f"    boost = {defense:.2f} * float(np.tanh((vix - 22) / 10))\n"
            f"    res.score_delta += boost * 0.08\n"
            f"    res.family_bias += boost * 0.06\n"
            f'    res.macro_gates.append("defensive_vix_bid")\n'
            f"if pmi > 0.6 and vix < 18:\n"
            f"    res.score_delta -= 0.03 * {defense:.2f}\n"
            f'    res.pipeline_notes.append("defensive_late_cycle_penalty")\n'
            f"if macro < -0.35:\n"
            f"    res.score_delta += 0.04 * {defense:.2f}"
        )

    if mode == "commodity":
        comm_keys = spec["commodities"][:3]
        keys_repr = ", ".join(repr(k) for k in comm_keys)
        return (
            f'pmi = self._macro(ctx, handler, "pmi_score")\n'
            f'macro = self._macro(ctx, handler, "macro_score")\n'
            f"if pmi > 0.45:\n"
            f"    res.score_delta += {exp:.2f} * pmi * 0.05\n"
            f'    res.macro_gates.append("commodity_demand")\n'
            f"if macro < -0.4:\n"
            f"    res.warn_long = True\n"
            f"    res.score_delta -= 0.05\n"
            f'text = " ".join(ctx.news_headlines).lower()\n'
            f"for key in ({keys_repr},):\n"
            f"    if key in text:\n"
            f'        res.pipeline_notes.append(f"commodity_tag:{{key}}")'
        )

    if mode == "follow_nasdaq":
        return (
            f'ndx = self._macro(ctx, handler, "nasdaq_ret_5d")\n'
            f'pmi = self._macro(ctx, handler, "pmi_score")\n'
            f"if ndx < -0.035:\n"
            f"    res.warn_long = True\n"
            f"    res.score_delta -= 0.06 * {ndx:.2f}\n"
            f'    res.macro_gates.append("ndx_drawdown")\n'
            f"elif ndx > 0.025:\n"
            f"    res.score_delta += 0.05 * {ndx:.2f}\n"
            f"    res.p_up_delta += 0.02 * {ndx:.2f}\n"
            f"if pmi > 0.5:\n"
            f"    res.score_delta += {exp:.2f} * pmi * 0.04"
        )

    if mode == "follow_market":
        return (
            f'macro = self._macro(ctx, handler, "macro_score")\n'
            f'spread = self._macro(ctx, handler, "spread_10y2y")\n'
            f"if macro > 0.25:\n"
            f"    res.score_delta += macro * 0.06 * {exp:.2f}\n"
            f"if spread < -0.3:\n"
            f"    res.warn_long = True\n"
            f"    res.score_delta -= 0.04"
        )

    return (
        f'shock = self._macro(ctx, handler, "rate_shock_20d")\n'
        f'pmi = self._macro(ctx, handler, "pmi_score")\n'
        f'ndx = self._macro(ctx, handler, "nasdaq_ret_5d")\n'
        f"if abs({rate:.2f}) > 0.25 and shock > 0.15:\n"
        f"    res.score_delta += shock * {rate:.2f} * -0.12\n"
        f"    if shock > 0.22:\n"
        f"        res.warn_long = True\n"
        f"if pmi > 0.4:\n"
        f"    res.score_delta += pmi * {exp:.2f} * 0.05\n"
        f"if ndx < -0.03:\n"
        f"    res.score_delta += ndx * {ndx:.2f} * 0.08"
    )


def _news_gates_body(spec: dict) -> str:
    mode = spec["mode"]
    bear_block = spec["bear"][:4]
    bull_boost = spec["bull"][:4]
    ebear = spec["events_bear"][:3]
    ebull = spec["events_bull"][:3]

    bear_checks = " or ".join(f'"{p}" in text' for p in bear_block) or "False"
    bull_checks = " or ".join(f'"{p}" in text' for p in bull_boost) or "False"
    ebear_checks = " or ".join(f'"{p}" in text' for p in ebear) or "False"
    ebull_checks = " or ".join(f'"{p}" in text' for p in ebull) or "False"

    lines = [
        "if not ctx.news_headlines:",
        "    return None",
        "ns = handler.score_news(ctx.news_headlines)",
        'text = " ".join(ctx.news_headlines).lower()',
    ]
    if mode == "event_driven":
        lines.extend(
            [
                f"if ns.bearish_score >= 0.20 and ({ebear_checks} or {bear_checks}):",
                "    res.block_long = True",
                f'    res.block_reason = "{spec["id"]}: adverse event headline"',
                '    res.pipeline_notes.append("event_bear_block")',
                f"if ns.bullish_score >= 0.18 and ({ebull_checks} or {bull_checks}):",
                "    res.score_delta += 0.14",
                "    res.p_up_delta += 0.05",
                '    res.pipeline_notes.append("event_bull_boost")',
            ]
        )
    elif mode in ("inverse_rates", "commodity"):
        lines.extend(
            [
                f"if ns.bearish_score >= 0.35 and ({bear_checks}):",
                "    res.warn_long = True",
                "    res.score_delta -= 0.06",
                '    res.pipeline_notes.append("sector_bear_warn")',
                f"if ns.bullish_score >= 0.28 and ({bull_checks}):",
                "    res.score_delta += 0.07",
                "    res.p_up_delta += 0.02",
            ]
        )
    else:
        lines.extend(
            [
                f"if ns.bearish_score >= 0.32 and ({bear_checks}):",
                "    res.warn_long = True",
                "    res.score_delta -= 0.05",
                f"if ns.bullish_score >= 0.25 and ({bull_checks}):",
                "    res.score_delta += 0.06",
                "    res.p_up_delta += 0.015",
            ]
        )
    lines.extend(
        [
            "if ns.net > 0.15:",
            "    res.family_bias += 0.04",
            "elif ns.net < -0.15:",
            "    res.family_bias -= 0.06",
            "return None",
        ]
    )
    return "\n".join(lines)


def _feature_weights_body(spec: dict) -> str:
    mode = spec["mode"]
    rate = abs(spec["rate"])
    exp = spec["exp"]
    ndx = spec["ndx"]
    corr = spec["corr"]
    if mode == "event_driven":
        extra = '"fpw_news_sent": 1.35, "fpw_industry_sympathy": 0.65,'
    elif mode == "inverse_rates":
        extra = f'"fpw_factor_rate": 1.0 + {rate:.2f} * 0.35, "fpw_industry_beta": 1.15,'
    elif mode == "follow_nasdaq":
        extra = f'"fpw_nasdaq_beta": 1.0 + {ndx:.2f} * 0.12, "fpw_industry_leader_momentum": 1.25,'
    elif mode == "commodity":
        extra = '"fpw_factor_expansion": 1.20, "fpw_commodity_proxy": 1.40,'
    elif mode == "defensive":
        extra = '"fpw_vix_sensitivity": 1.30, "fpw_industry_sympathy": 0.80,'
    else:
        extra = f'"fpw_factor_expansion": 1.0 + {exp:.2f} * 0.10,'

    return (
        "base = super().feature_weights(ctx, handler)\n"
        "base.update({\n"
        f"    {extra}\n"
        f'    "fpw_intra_corr": {corr:.2f},\n'
        "})\n"
        "tilts = handler.compute_factor_tilts(ctx)\n"
        'base["fpw_combined_tilt"] = 1.0 + abs(tilts.combined) * 0.08\n'
        "return base"
    )


def _family_bias_body(spec: dict) -> str:
    mode = spec["mode"]
    defense = spec["def"]
    exp = spec["exp"]
    if mode == "defensive":
        return (
            f'vix = self._macro(ctx, handler, "vix", 20.0)\n'
            f"bias = super().family_bias(ctx, handler)\n"
            f"if vix > 24:\n"
            f"    bias += {defense:.2f} * 0.12\n"
            f"return float(np.clip(bias, -0.25, 0.25))"
        )
    if mode == "follow_nasdaq":
        return (
            f'ndx = self._macro(ctx, handler, "nasdaq_ret_5d")\n'
            f"bias = super().family_bias(ctx, handler)\n"
            f"bias += float(np.tanh(ndx * 8.0)) * {exp:.2f} * 0.08\n"
            f"return float(np.clip(bias, -0.25, 0.25))"
        )
    return (
        "bias = super().family_bias(ctx, handler)\n"
        "tilts = handler.compute_factor_tilts(ctx)\n"
        "bias += float(np.tanh(tilts.combined)) * 0.05\n"
        "return float(np.clip(bias, -0.25, 0.25))"
    )


def _risk_adjust_body(spec: dict) -> str:
    mode = spec["mode"]
    if mode == "event_driven":
        return (
            "super().risk_adjust(ctx, handler, res)\n"
            "if res.block_long:\n"
            "    res.max_hold_mult = min(res.max_hold_mult, 0.5)\n"
            "    res.position_cap_mult = min(res.position_cap_mult, 0.6)\n"
            "elif res.warn_long:\n"
            "    res.max_hold_mult = min(res.max_hold_mult, 0.65)"
        )
    if mode == "inverse_rates":
        return (
            "super().risk_adjust(ctx, handler, res)\n"
            f'shock = self._macro(ctx, handler, "rate_shock_20d")\n'
            "if shock > 0.18:\n"
            "    res.max_hold_mult = min(res.max_hold_mult, 0.7)"
        )
    return "super().risk_adjust(ctx, handler, res)"


def _pipeline_score_body(spec: dict) -> str:
    leaders = spec["leaders"][:3]
    leaders_repr = ", ".join(repr(x) for x in leaders)
    return (
        "score = super().pipeline_score(ctx, handler)\n"
        "comove = handler.compute_comovement(\n"
        "    ctx,\n"
        '    industry_z=float(ctx.row_features.get("industry_z_20", 0.0)),\n'
        '    residual=float(ctx.row_features.get("industry_residual_1d", 0.0)),\n'
        ")\n"
        "score += comove.sympathy_score * 0.08\n"
        "sym = ctx.symbol.upper()\n"
        f"leaders = ({leaders_repr},)\n"
        "if sym in leaders:\n"
        "    score += 0.025\n"
        "if comove.short_sympathy:\n"
        "    score -= 0.04\n"
        "return float(score)"
    )


def _specialized_source(spec: dict) -> str:
    iid = spec["id"]
    cls = _cls_name(iid)
    notes = spec["notes"].replace('"', "'")
    leaders = ", ".join(repr(x) for x in spec["leaders"])
    macro = _indent_block(_macro_gates_body(spec), 8)
    news = _indent_block(_news_gates_body(spec), 8)
    score = _indent_block(_pipeline_score_body(spec), 8)
    feats = _indent_block(_feature_weights_body(spec), 8)
    family = _indent_block(_family_bias_body(spec), 8)
    risk = _indent_block(_risk_adjust_body(spec), 8)

    return (
        f'"""{spec["name"]} specialized pipeline — {notes}"""\n\n'
        "from __future__ import annotations\n\n"
        "import numpy as np\n\n"
        "from analytics.industries.specialized.base import SpecializedLogic\n\n\n"
        f"class {cls}(SpecializedLogic):\n"
        f"    INDUSTRY_ID = {iid!r}\n"
        f"    INDUSTRY_NAME = {spec['name']!r}\n"
        f"    ETF_PROXY = {spec['etf']!r}\n"
        f"    COMOVEMENT_MODE = {spec['mode']!r}\n"
        f"    RATE_SENSITIVITY = {spec['rate']}\n"
        f"    EXPANSION_BETA = {spec['exp']}\n"
        f"    NASDAQ_BETA = {spec['ndx']}\n"
        f"    DEFENSIVE_SCORE = {spec['def']}\n"
        f"    INTRA_CORR = {spec['corr']}\n\n"
        f"    LEADER_TICKERS = (\n"
        f"        {leaders}\n"
        f"    )\n\n"
        f"    def apply_macro_gates(self, ctx, handler, res):\n{macro}\n"
        f"        return None\n\n"
        f"    def apply_news_gates(self, ctx, handler, res):\n{news}\n\n"
        f"    def pipeline_score(self, ctx, handler):\n{score}\n\n"
        f"    def feature_weights(self, ctx, handler):\n{feats}\n\n"
        f"    def family_bias(self, ctx, handler):\n{family}\n\n"
        f"    def risk_adjust(self, ctx, handler, res):\n{risk}\n"
        f"        return None\n\n\n"
        f"LOGIC = {cls}()\n"
    )


def generate_all() -> int:
    SPECIALIZED_DIR.mkdir(parents=True, exist_ok=True)
    init_lines = ['"""Auto-generated specialized industry pipeline registry."""\n']
    count = 0
    for spec in MASTER:
        iid = spec["id"]
        path = SPECIALIZED_DIR / f"{iid}.py"
        path.write_text(_specialized_source(spec), encoding="utf-8")
        init_lines.append(f"from analytics.industries.specialized.{iid} import LOGIC as _s_{iid}")
        count += 1
    init_lines.append("\nfrom analytics.industries.specialized.unclassified import LOGIC as _s_unclassified\n")
    init_lines.append("\nALL_SPECIALIZED = {")
    for spec in MASTER:
        iid = spec["id"]
        init_lines.append(f'    "{iid}": _s_{iid},')
    init_lines.append('    "unclassified": _s_unclassified,')
    init_lines.append("}\n")
    init_lines.append(
        "\ndef get_specialized(industry_id: str):\n"
        '    return ALL_SPECIALIZED.get(str(industry_id or "unclassified"), _s_unclassified)\n'
    )
    (SPECIALIZED_DIR / "__init__.py").write_text("\n".join(init_lines), encoding="utf-8")
    return count


if __name__ == "__main__":
    n = generate_all()
    print(f"Generated {n} specialized pipeline modules in {SPECIALIZED_DIR}")
