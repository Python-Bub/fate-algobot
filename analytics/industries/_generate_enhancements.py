#!/usr/bin/env python3
"""Generate 50 comprehensive industry enhancement modules + high-level tests."""

from __future__ import annotations

from pathlib import Path

from analytics.industries._generate_industry_handlers import MASTER
from analytics.industries.enhancements._base import ENHANCEMENT_FEATURES

ROOT = Path(__file__).resolve().parents[2]
ENH_DIR = ROOT / "analytics" / "industries" / "enhancements"
TEST_DIR = ROOT / "tests" / "industry_enhancements"


def _cls(iid: str) -> str:
    return "".join(p.capitalize() for p in iid.split("_")) + "Enhancement"


def _feature_doc() -> str:
    return "\n".join(f"    {i+1:2d}. {f}" for i, f in enumerate(ENHANCEMENT_FEATURES))


def _mode_macro_regime(spec: dict) -> str:
    mode = spec["mode"]
    rate = spec["rate"]
    exp = spec["exp"]
    ndx = spec["ndx"]
    defense = spec["def"]
    if mode == "inverse_rates":
        return (
            f'shock = self._macro(ctx, handler, "rate_shock_20d")\n'
            f"spread = self._macro(ctx, handler, \"spread_10y2y\")\n"
            f"if shock < -0.04 or spread > 0.2:\n"
            f"    self._boost(res, {abs(rate):.2f} * 0.12, \"enh:rate_regime_tailwind\")\n"
            f"    self._boost_p_up(res, 0.03)\n"
            f"    res.macro_gates.append(\"enh_rate_favorable\")"
        )
    if mode == "follow_nasdaq":
        return (
            f'ndx = self._macro(ctx, handler, "nasdaq_ret_5d")\n'
            f"pmi = self._macro(ctx, handler, \"pmi_score\")\n"
            f"if ndx > 0.015:\n"
            f"    self._boost(res, ndx * {ndx:.2f} * 0.15, \"enh:nasdaq_regime\")\n"
            f"if pmi > 0.45:\n"
            f"    self._boost(res, pmi * {exp:.2f} * 0.06, \"enh:pmi_regime\")"
        )
    if mode == "defensive":
        return (
            f'vix = self._macro(ctx, handler, "vix", 20.0)\n'
            f"if vix > 20:\n"
            f"    self._boost(res, {defense:.2f} * float(__import__(\"numpy\").tanh((vix-18)/8)) * 0.10, \"enh:defensive_regime\")\n"
            f"    res.family_bias += {defense:.2f} * 0.05"
        )
    if mode == "commodity":
        return (
            f'pmi = self._macro(ctx, handler, "pmi_score")\n'
            f"macro = self._macro(ctx, handler, \"macro_score\")\n"
            f"if pmi > 0.35:\n"
            f"    self._boost(res, pmi * {exp:.2f} * 0.08, \"enh:commodity_demand_regime\")\n"
            f"if macro > 0.2:\n"
            f"    self._boost(res, macro * 0.05, \"enh:commodity_macro\")"
        )
    if mode == "event_driven":
        return (
            "if ctx.news_headlines:\n"
            "    ns = handler.score_news(ctx.news_headlines)\n"
            "    if ns.bullish_score > 0.1:\n"
            "        self._boost(res, ns.bullish_score * 0.15, \"enh:event_regime_bull\")\n"
            "        self._boost_p_up(res, ns.bullish_score * 0.04)"
        )
    return (
        f'pmi = self._macro(ctx, handler, "pmi_score")\n'
        f"macro = self._macro(ctx, handler, \"macro_score\")\n"
        f"if pmi > 0.4:\n"
        f"    self._boost(res, pmi * {exp:.2f} * 0.06, \"enh:hybrid_pmi\")\n"
        f"if macro > 0.2:\n"
        f"    self._boost(res, macro * 0.04, \"enh:hybrid_macro\")"
    )


def _mode_macro_tailwind(spec: dict) -> str:
    mode = spec["mode"]
    if mode == "inverse_rates":
        return (
            f'shock = self._macro(ctx, handler, "rate_shock_20d")\n'
            f"if shock < 0:\n"
            f"    self._boost(res, abs(shock) * {abs(spec['rate']):.2f} * 0.20, \"enh:rate_tailwind\")"
        )
    if mode == "follow_nasdaq":
        return (
            f'ndx = self._macro(ctx, handler, "nasdaq_ret_5d")\n'
            f"if ndx > 0:\n"
            f"    self._boost(res, ndx * {spec['ndx']:.2f} * 0.18, \"enh:ndx_tailwind\")"
        )
    if mode == "defensive":
        return (
            f'vix = self._macro(ctx, handler, "vix", 20.0)\n'
            f"if vix > 21:\n"
            f"    self._boost(res, {spec['def']:.2f} * 0.08, \"enh:defensive_tailwind\")"
        )
    if mode == "commodity":
        return (
            f'pmi = self._macro(ctx, handler, "pmi_score")\n'
            f"if pmi > 0.3:\n"
            f"    self._boost(res, pmi * {spec['exp']:.2f} * 0.10, \"enh:commodity_tailwind\")"
        )
    return (
        f'macro = self._macro(ctx, handler, "macro_score")\n'
        f"if macro > 0:\n"
        f"    self._boost(res, macro * {spec['exp']:.2f} * 0.08, \"enh:macro_tailwind\")"
    )


def _news_bull(spec: dict) -> str:
    phrases = spec["bull"][:6]
    checks = " or ".join(f'"{p}" in text' for p in phrases) or "False"
    return (
        "if not ctx.news_headlines:\n"
        "    return None\n"
        "text = \" \".join(ctx.news_headlines).lower()\n"
        "ns = handler.score_news(ctx.news_headlines)\n"
        f"if ns.bullish_score >= 0.08 or ({checks}):\n"
        "    boost = max(ns.bullish_score, 0.15) * 0.12\n"
        f"    self._boost(res, boost, \"enh:{spec['id']}_bull_lexicon\")\n"
        "    self._boost_p_up(res, boost * 0.3)\n"
        "    res.family_bias += 0.03"
    )


def _news_event(spec: dict) -> str:
    ebull = spec["events_bull"][:4]
    checks = " or ".join(f'"{p}" in text' for p in ebull) or "False"
    return (
        "if not ctx.news_headlines:\n"
        "    return None\n"
        "text = \" \".join(ctx.news_headlines).lower()\n"
        f"if {checks}:\n"
        "    self._boost(res, 0.16, \"enh:sector_event_bull\")\n"
        "    self._boost_p_up(res, 0.05)\n"
        "    self._expand_risk(res, hold=1.12, cap=1.06)"
    )


def _family_bias(spec: dict) -> str:
    mode = spec["mode"]
    if mode == "defensive":
        return (
            f'vix = self._macro(ctx, handler, "vix", 20.0)\n'
            f"res.family_bias += 0.03\n"
            f"if vix > 22:\n"
            f"    res.family_bias += {spec['def']:.2f} * 0.10"
        )
    if mode == "follow_nasdaq":
        return (
            f'ndx = self._macro(ctx, handler, "nasdaq_ret_5d")\n'
            f"res.family_bias += 0.03\n"
            f"res.family_bias += float(__import__(\"numpy\").tanh(ndx * 6)) * {spec['exp']:.2f} * 0.06"
        )
    return (
        "res.family_bias += 0.04\n"
        "tilts = handler.compute_factor_tilts(ctx)\n"
        "if tilts.combined > 0:\n"
        "    res.family_bias += float(__import__('numpy').tanh(tilts.combined)) * 0.04"
    )


def _ml_matrix(spec: dict) -> str:
    mode = spec["mode"]
    corr = spec["corr"]
    lines = [
        f'super().ml_feature_weight_matrix(res, ctx, handler)',
        f'self._add_fpw(res, "fpw_{spec["id"]}_alpha", 1.12)',
        f'self._add_fpw(res, "fpw_intra_corr", {corr:.2f})',
    ]
    if mode == "event_driven":
        lines.append('self._add_fpw(res, "fpw_news_sent", 1.45)')
        lines.append('self._add_fpw(res, "fpw_trial_catalyst", 1.30)')
    elif mode == "inverse_rates":
        lines.append(f'self._add_fpw(res, "fpw_factor_rate", 1.0 + {abs(spec["rate"]):.2f} * 0.4)')
        lines.append('self._add_fpw(res, "fpw_duration", 1.25)')
    elif mode == "follow_nasdaq":
        lines.append(f'self._add_fpw(res, "fpw_nasdaq_beta", 1.0 + {spec["ndx"]:.2f} * 0.15)')
        lines.append('self._add_fpw(res, "fpw_industry_leader_momentum", 1.35)')
    elif mode == "commodity":
        lines.append('self._add_fpw(res, "fpw_commodity_proxy", 1.50)')
        lines.append('self._add_fpw(res, "fpw_factor_expansion", 1.25)')
    elif mode == "defensive":
        lines.append('self._add_fpw(res, "fpw_vix_sensitivity", 1.40)')
        lines.append('self._add_fpw(res, "fpw_dividend_quality", 1.15)')
    else:
        lines.append(f'self._add_fpw(res, "fpw_factor_expansion", 1.0 + {spec["exp"]:.2f} * 0.12)')
    return "\n".join(lines)


def _playbook_amp(spec: dict) -> str:
    events = list(spec.get("events_bull", ()))[:3]
    ev_checks = []
    for ev in events:
        ev_checks.append(f'if "{ev}" in text or ev == "{ev.replace(" ", "_")}":')
    body = (
        "from analytics.industries.macro_playbooks import apply_playbook, infer_events_from_headlines\n"
        "events = infer_events_from_headlines(ctx.news_headlines or [], self.INDUSTRY_ID)\n"
        "for ev in events:\n"
        "    hit = apply_playbook(self.INDUSTRY_ID, ev)\n"
        "    if hit.get('applied') and float(hit.get('combined_delta') or 0) > 0:\n"
        "        self._boost(res, float(hit['combined_delta']) * 0.15, f\"enh:playbook:{ev}\")\n"
        "super().playbook_amplification(res, ctx, handler)"
    )
    return body


def _comovement_bonus(spec: dict) -> str:
    mode = spec["mode"]
    return (
        f"super().comovement_mode_bonus(res, ctx, handler)\n"
        f"if self.COMOVEMENT_MODE == {mode!r}:\n"
        f"    self._boost(res, 0.025, \"enh:mode_identity:{spec['id']}\")"
    )


def _industry_alpha_suite(spec: dict) -> str:
    """Large industry-specific alpha block — unique logic per bucket."""
    iid = spec["id"]
    mode = spec["mode"]
    bull = spec["bull"]
    comm = spec["commodities"]
    leaders = spec["leaders"]
    lines = [
        f'"""Apply {spec["name"]}-specific alpha signals from notes: {spec["notes"][:60]}."""',
        "sym = ctx.symbol.upper()",
        f"leaders = {leaders!r}",
        f"bull_phrases = {bull!r}",
        f"commodity_keys = {comm!r}",
        "tilts = handler.compute_factor_tilts(ctx)",
        "if tilts.combined > 0:",
        '    self._boost(res, float(__import__("numpy").tanh(tilts.combined)) * 0.06, "enh:combined_tilt")',
        "if sym in leaders:",
        '    self._boost(res, 0.04, "enh:sector_leader")',
        '    self._add_fpw(res, "fpw_leader_alpha", 1.20)',
        "if ctx.news_headlines:",
        "    text = ' '.join(ctx.news_headlines).lower()",
        "    bull_hits = sum(1 for p in bull_phrases if p in text)",
        "    if bull_hits:",
        f'        self._boost(res, min(0.20, bull_hits * 0.05), "enh:{iid}_phrase_hits")',
        "    comm_hits = sum(1 for k in commodity_keys if k in text)",
        "    if comm_hits:",
        f'        self._boost(res, min(0.12, comm_hits * 0.04), "enh:{iid}_commodity_news")',
    ]
    if mode == "inverse_rates":
        lines.extend([
            'shock = self._macro(ctx, handler, "rate_shock_20d")',
            "if shock < -0.03:",
            f'    self._boost(res, abs(shock) * {abs(spec["rate"]):.2f} * 0.25, "enh:{iid}_rate_alpha")',
            '    self._add_fpw(res, "fpw_duration_alpha", 1.18)',
        ])
    elif mode == "follow_nasdaq":
        lines.extend([
            'ndx = self._macro(ctx, handler, "nasdaq_ret_5d")',
            "if ndx > 0.01:",
            f'    self._boost(res, ndx * {spec["ndx"]:.2f} * 0.20, "enh:{iid}_ndx_alpha")',
            '    self._add_fpw(res, "fpw_growth_beta", 1.22)',
        ])
    elif mode == "defensive":
        lines.extend([
            'vix = self._macro(ctx, handler, "vix", 20.0)',
            "if vix > 20:",
            f'    self._boost(res, {spec["def"]:.2f} * 0.10, "enh:{iid}_defensive_alpha")',
            '    self._add_fpw(res, "fpw_quality_defensive", 1.16)',
        ])
    elif mode == "commodity":
        lines.extend([
            'pmi = self._macro(ctx, handler, "pmi_score")',
            "if pmi > 0.35:",
            f'    self._boost(res, pmi * {spec["exp"]:.2f} * 0.12, "enh:{iid}_commodity_cycle")',
            '    self._add_fpw(res, "fpw_cycle_beta", 1.24)',
        ])
    elif mode == "event_driven":
        lines.extend([
            "if ctx.news_headlines:",
            "    ns = handler.score_news(ctx.news_headlines)",
            "    if ns.bullish_score > 0.08:",
            f'        self._boost(res, ns.bullish_score * 0.18, "enh:{iid}_event_alpha")',
            '        self._add_fpw(res, "fpw_catalyst", 1.35)',
        ])
    else:
        lines.extend([
            'pmi = self._macro(ctx, handler, "pmi_score")',
            "if pmi > 0.4:",
            f'    self._boost(res, pmi * {spec["exp"]:.2f} * 0.08, "enh:{iid}_hybrid_alpha")',
        ])
    lines.extend([
        'ret1 = float(ctx.row_features.get("industry_ret_1d", 0.0))',
        "if ret1 > 0.005:",
        '    self._boost(res, float(__import__("numpy").tanh(ret1 * 30)) * 0.04, "enh:industry_momentum_1d")',
        'z = float(ctx.row_features.get("industry_z_20", 0.0))',
        "if 0.3 < z < 2.5:",
        '    self._boost(res, z * 0.02, "enh:industry_z_sweet")',
        "if res.score_delta > 0.06:",
        "    self._expand_risk(res, hold=1.05, cap=1.04)",
    ])
    return "\n".join(f"        {ln}" for ln in lines)


def _sympathy_override(spec: dict) -> str:
    return (
        "comove = handler.compute_comovement(\n"
        "    ctx,\n"
        '    industry_z=float(ctx.row_features.get("industry_z_20", 0.0)),\n'
        '    residual=float(ctx.row_features.get("industry_residual_1d", 0.0)),\n'
        ")\n"
        "if comove.sympathy_score > 0:\n"
        f"    self._boost(res, comove.sympathy_score * {spec['corr']:.2f} * 0.12, \"enh:sympathy_follow\")\n"
        "if comove.leader_momentum > 0.01:\n"
        f"    self._boost(res, comove.leader_momentum * {spec['exp']:.2f} * 0.15, \"enh:leader_momentum\")"
    )


def _residual_override(spec: dict) -> str:
    return (
        'residual = float(ctx.row_features.get("industry_residual_1d", 0.0))\n'
        "if residual < -0.01:\n"
        f"    self._boost(res, float(__import__('numpy').tanh(-residual * 35)) * {spec['corr']:.2f} * 0.05, \"enh:mean_revert\")"
    )


def _factor_overrides(spec: dict) -> list[tuple[str, str]]:
    mode = spec["mode"]
    out = []
    if mode in ("inverse_rates", "hybrid") and abs(spec["rate"]) > 0.2:
        out.append(("factor_rate_emphasis", (
            "tilts = handler.compute_factor_tilts(ctx)\n"
            "if tilts.rate_tilt > 0:\n"
            f"    self._boost(res, tilts.rate_tilt * {abs(spec['rate']):.2f} * 0.08, \"enh:rate_factor\")\n"
            f"    self._add_fpw(res, \"fpw_factor_rate\", 1.0 + {abs(spec['rate']):.2f} * 0.25)"
        )))
    if spec["exp"] > 0.5:
        out.append(("factor_expansion_emphasis", (
            "tilts = handler.compute_factor_tilts(ctx)\n"
            "if tilts.expansion_tilt > 0:\n"
            f"    self._boost(res, tilts.expansion_tilt * {spec['exp']:.2f} * 0.07, \"enh:expansion_factor\")\n"
            f"    self._add_fpw(res, \"fpw_factor_expansion\", 1.0 + {spec['exp']:.2f} * 0.18)"
        )))
    if mode == "follow_nasdaq" or spec["ndx"] > 1.0:
        out.append(("factor_nasdaq_emphasis", (
            "tilts = handler.compute_factor_tilts(ctx)\n"
            "if tilts.nasdaq_tilt > 0:\n"
            f"    self._boost(res, tilts.nasdaq_tilt * {spec['ndx']:.2f} * 0.06, \"enh:nasdaq_factor\")"
        )))
    if spec["def"] > 0.4:
        out.append(("factor_defensive_emphasis", (
            "tilts = handler.compute_factor_tilts(ctx)\n"
            "if tilts.defensive_tilt > 0:\n"
            f"    self._boost(res, tilts.defensive_tilt * {spec['def']:.2f} * 0.08, \"enh:defensive_factor\")"
        )))
    if mode == "commodity":
        out.append(("factor_commodity_emphasis", (
            "tilts = handler.compute_factor_tilts(ctx)\n"
            "if tilts.commodity_tilt > 0:\n"
            f"    self._boost(res, tilts.commodity_tilt * {spec['exp']:.2f} * 0.10, \"enh:commodity_factor\")"
        )))
    return out


def _enhancement_source(spec: dict) -> str:
    iid = spec["id"]
    cls = _cls(iid)
    bull = ",\n        ".join(repr(x) for x in spec["bull"])
    ebull = ",\n        ".join(repr(x) for x in spec["events_bull"])
    comm = ",\n        ".join(repr(x) for x in spec["commodities"])
    leaders = ",\n        ".join(repr(x) for x in spec["leaders"])

    methods = []
    core_feats = [
        ("macro_tailwind_score", _mode_macro_tailwind(spec)),
        ("macro_regime_alignment", _mode_macro_regime(spec)),
        ("news_bull_accelerator", _news_bull(spec)),
        ("news_event_catalyst", _news_event(spec)),
        ("sympathy_leader_follow", _sympathy_override(spec)),
        ("residual_reversion_edge", _residual_override(spec)),
        ("family_horizon_bias", _family_bias(spec)),
        ("ml_feature_weight_matrix", _ml_matrix(spec)),
        ("playbook_amplification", _playbook_amp(spec)),
        ("comovement_mode_bonus", _comovement_bonus(spec)),
    ]
    core_feats.extend(_factor_overrides(spec))
    for feat, body in core_feats:
        methods.append(
            f"    def {feat}(self, res, ctx, handler):\n"
            + "\n".join(f"        {line}" if line.strip() else "" for line in body.splitlines())
            + "\n"
        )
    methods.append(f"    def industry_alpha_suite(self, res, ctx, handler):\n{_industry_alpha_suite(spec)}\n")
    methods.append(
        "    def enhance(self, res, ctx, handler):\n"
        "        out = super().enhance(res, ctx, handler)\n"
        "        before = out.score_delta\n"
        "        self.industry_alpha_suite(out, ctx, handler)\n"
        "        if out.score_delta < before:\n"
        "            out.score_delta = before\n"
        "        return out\n"
    )

    return (
        f'"""\n{spec["name"]} — comprehensive industry enhancement module.\n\n'
        f"Industry notes: {spec['notes']}\n\n"
        f"ALL SPECIALIZED FEATURES IMPLEMENTED ({len(ENHANCEMENT_FEATURES)}):\n"
        f"{_feature_doc()}\n\n"
        f"Philosophy: enhancement-only — boosts scores, p_up, family bias, ML weights;\n"
        f"expands risk capacity on strength. Never reduces score except via super() guard.\n"
        f'"""\n\n'
        f"from __future__ import annotations\n\n"
        f"import numpy as np\n\n"
        f"from analytics.industries.enhancements._base import IndustryEnhancement, ENHANCEMENT_FEATURES\n\n\n"
        f"class {cls}(IndustryEnhancement):\n"
        f"    INDUSTRY_ID = {iid!r}\n"
        f"    INDUSTRY_NAME = {spec['name']!r}\n"
        f"    ETF_PROXY = {spec['etf']!r}\n"
        f"    COMOVEMENT_MODE = {spec['mode']!r}\n"
        f"    RATE_SENSITIVITY = {spec['rate']}\n"
        f"    EXPANSION_BETA = {spec['exp']}\n"
        f"    NASDAQ_BETA = {spec['ndx']}\n"
        f"    DEFENSIVE_SCORE = {spec['def']}\n"
        f"    INTRA_CORR = {spec['corr']}\n"
        f"    INDUSTRY_NOTES = {spec['notes']!r}\n\n"
        f"    LEADER_TICKERS = (\n        {leaders}\n    )\n"
        f"    NEWS_BULL = (\n        {bull}\n    )\n"
        f"    NEWS_EVENT_BULL = (\n        {ebull}\n    )\n"
        f"    COMMODITY_KEYS = (\n        {comm}\n    )\n\n"
        f"    IMPLEMENTED_FEATURES = ENHANCEMENT_FEATURES\n\n"
        + "".join(methods)
        + "\n\n"
        f"ENHANCEMENT = {cls}()\n"
    )


def _test_source(spec: dict) -> str:
    iid = spec["id"]
    cls = _cls(iid)
    leader = spec["leaders"][0]
    bull_headline = spec["bull"][0]
    return (
        f'"""High-level tests for {spec["name"]} enhancement module."""\n\n'
        f"from __future__ import annotations\n\n"
        f"import unittest\n\n"
        f"from analytics.industries.enhancements.{iid} import ENHANCEMENT\n"
        f"from analytics.industries.enhancements._base import ENHANCEMENT_FEATURES\n"
        f"from analytics.industries.base import IndustryContext\n"
        f"from analytics.industries.pipeline_models import IndustryPipelineResult\n"
        f"from analytics.industries.registry import get_handler\n\n\n"
        f"class Test{cls}(unittest.TestCase):\n"
        f"    INDUSTRY_ID = {iid!r}\n\n"
        f"    def test_all_features_callable(self):\n"
        f"        for feat in ENHANCEMENT_FEATURES:\n"
        f"            self.assertTrue(callable(getattr(ENHANCEMENT, feat)), feat)\n\n"
        f"    def test_high_level_self_test(self):\n"
        f"        report = ENHANCEMENT.high_level_test()\n"
        f"        self.assertEqual(report['industry_id'], self.INDUSTRY_ID)\n"
        f"        self.assertEqual(report['features_implemented'], len(ENHANCEMENT_FEATURES))\n"
        f"        self.assertTrue(report['net_positive'], report)\n"
        f"        self.assertGreater(report['score_delta'], 0, report)\n"
        f"        self.assertGreaterEqual(report['feature_weight_count'], 3, report)\n\n"
        f"    def test_bullish_macro_enhances(self):\n"
        f"        handler = get_handler(self.INDUSTRY_ID)\n"
        f"        ctx = IndustryContext(\n"
        f"            symbol={leader!r},\n"
        f"            market_cap=80e9,\n"
        f"            macro={{'macro_score': 0.5, 'pmi_score': 0.7, 'nasdaq_ret_5d': 0.04, 'rate_shock_20d': -0.06, 'vix': 18, 'spread_10y2y': 0.2}},\n"
        f"            row_features={{'industry_z_20': 1.0, 'industry_ret_5d': 0.03, 'industry_beta_60': 1.05}},\n"
        f"        )\n"
        f"        res = IndustryPipelineResult()\n"
        f"        ENHANCEMENT.enhance(res, ctx, handler)\n"
        f"        self.assertGreater(res.score_delta, 0.05)\n\n"
        f"    def test_bull_news_enhances(self):\n"
        f"        handler = get_handler(self.INDUSTRY_ID)\n"
        f"        ctx = IndustryContext(\n"
        f"            symbol={leader!r},\n"
        f"            news_headlines=[{bull_headline!r}, 'beats estimates raises guidance'],\n"
        f"            macro={{'macro_score': 0.3, 'pmi_score': 0.5, 'vix': 18, 'nasdaq_ret_5d': 0.01, 'rate_shock_20d': 0}},\n"
        f"        )\n"
        f"        res = IndustryPipelineResult()\n"
        f"        ENHANCEMENT.enhance(res, ctx, handler)\n"
        f"        self.assertGreater(res.score_delta, 0.03)\n"
        f"        self.assertGreater(res.p_up_delta, 0)\n\n"
        f"    def test_leader_premium(self):\n"
        f"        handler = get_handler(self.INDUSTRY_ID)\n"
        f"        ctx = IndustryContext(symbol={leader!r}, market_cap=200e9, macro={{'macro_score': 0.2}})\n"
        f"        res = IndustryPipelineResult()\n"
        f"        ENHANCEMENT.leader_ticker_premium(res, ctx, handler)\n"
        f"        self.assertGreater(res.score_delta, 0)\n\n"
        f"    def test_never_reduces_on_enhance_guard(self):\n"
        f"        handler = get_handler(self.INDUSTRY_ID)\n"
        f"        ctx = IndustryContext(symbol='ZZZZ', macro={{'macro_score': -0.5, 'vix': 35}})\n"
        f"        base = IndustryPipelineResult(score_delta=0.10)\n"
        f"        out = ENHANCEMENT.enhance(base, ctx, handler)\n"
        f"        self.assertGreaterEqual(out.score_delta, 0.10)\n\n\n"
        f"if __name__ == '__main__':\n"
        f"    unittest.main()\n"
    )


def generate_all() -> tuple[int, int]:
    ENH_DIR.mkdir(parents=True, exist_ok=True)
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    init_lines = ['"""Auto-generated industry enhancement registry."""\n']
    n = 0
    for spec in MASTER:
        iid = spec["id"]
        (ENH_DIR / f"{iid}.py").write_text(_enhancement_source(spec), encoding="utf-8")
        (TEST_DIR / f"test_{iid}.py").write_text(_test_source(spec), encoding="utf-8")
        init_lines.append(f"from analytics.industries.enhancements.{iid} import ENHANCEMENT as _e_{iid}")
        n += 1
    init_lines.append("\nfrom analytics.industries.enhancements._unclassified import ENHANCEMENT as _e_unclassified\n")
    init_lines.append("\nALL_ENHANCEMENTS = {")
    for spec in MASTER:
        init_lines.append(f'    "{spec["id"]}": _e_{spec["id"]},')
    init_lines.append('    "unclassified": _e_unclassified,')
    init_lines.append("}\n")
    init_lines.append(
        "\ndef get_enhancement(industry_id: str):\n"
        '    return ALL_ENHANCEMENTS.get(str(industry_id or "unclassified"), _e_unclassified)\n'
    )
    (ENH_DIR / "__init__.py").write_text("\n".join(init_lines), encoding="utf-8")
    (TEST_DIR / "__init__.py").write_text('"""Per-industry high-level enhancement tests (50 modules)."""\n')
    return n, n


if __name__ == "__main__":
    modules, tests = generate_all()
    print(f"Generated {modules} enhancement modules + {tests} test files")
