"""Category-aware buy decision layer using taxonomy specs, macro, and headlines."""

from __future__ import annotations

import os

import numpy as np

from analytics.industries.categories._spec_types import CategoryDecisionResult, CategorySpec
from analytics.industries.integration import get_industry_profile

try:
    from analytics.industries.categories.specs import get_spec_by_industry_id
except ImportError:
    get_spec_by_industry_id = None  # type: ignore[assignment]


def _f(d: dict | None, key: str, default: float = 0.0) -> float:
    if not d:
        return default
    v = d.get(key, default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _headline_text(headlines: list[str] | None) -> str:
    return " ".join(headlines or []).lower()


def _match_score(text: str, keywords: tuple[str, ...] | list[str]) -> float:
    if not text or not keywords:
        return 0.0
    hits = sum(1 for kw in keywords if kw and kw.lower() in text)
    return float(np.tanh(hits / max(2.0, len(keywords) * 0.35)))


def _compute_metric_proxy(spec: CategorySpec, row: dict | None, macro: dict | None) -> float:
    """Map category metric_type to a [-1, 1] proxy from row features + macro."""
    row = row or {}
    macro = macro or {}
    mt = spec.metric_type

    industry_z = _f(row, "industry_z_20") or _f(row, "industry_sympathy_score")
    residual = _f(row, "industry_residual_1d")
    mom = _f(row, "mom_20") or _f(row, "ret_20d")
    margin = _f(row, "gross_margin") or _f(row, "operating_margin")
    growth = _f(row, "revenue_growth") or _f(row, "arr_growth")
    pmi = _f(macro, "pmi_score")
    macro_score = _f(macro, "macro_score")
    rate_shock = _f(macro, "rate_shock_20d")
    ndx = _f(macro, "nasdaq_ret_5d")
    vix = _f(macro, "vix", 20.0)

    if mt == "burn_runway":
        cash = _f(row, "cash_runway_months") or _f(row, "runway_months")
        return float(np.tanh((cash - 18.0) / 12.0)) if cash else float(np.tanh(industry_z * 0.5))
    if mt == "patent_cliff":
        cliff = _f(row, "patent_years_remaining", 5.0)
        return float(np.tanh((cliff - 3.0) / 4.0))
    if mt == "gross_margin":
        base = margin if margin else 0.55 + industry_z * 0.05
        return float(np.tanh((base - 0.60) * 4.0))
    if mt == "backlog_growth":
        bl = _f(row, "backlog_growth") or growth
        return float(np.tanh(bl * 3.0 + industry_z * 0.25))
    if mt == "bed_occupancy":
        occ = _f(row, "bed_occupancy", 0.72 + industry_z * 0.03)
        return float(np.tanh((occ - 0.70) * 5.0))
    if mt == "ltv_cac":
        ratio = _f(row, "ltv_cac") or (2.5 + industry_z * 0.4)
        return float(np.tanh((ratio - 2.0) / 2.0))
    if mt == "net_effective_rent":
        rent = _f(row, "rent_growth") or (-rate_shock * 0.6 + industry_z * 0.2)
        return float(np.tanh(rent * 4.0))
    if mt == "wault":
        wault = _f(row, "wault_years", 4.0 + industry_z)
        return float(np.tanh((wault - 4.0) / 3.0))
    if mt == "tenant_occupancy_cost":
        toc = _f(row, "tenant_occupancy_cost", 0.12 - industry_z * 0.02)
        return float(np.tanh((0.14 - toc) * 8.0))
    if mt == "rent_reversion":
        rev = _f(row, "rent_reversion") or industry_z * 0.15
        return float(np.tanh(rev * 5.0))
    if mt == "pue_churn":
        pue = _f(row, "pue", 1.35 - industry_z * 0.05)
        return float(np.tanh((1.45 - pue) * 3.0 + ndx * 0.5))
    if mt == "book_to_bill":
        btb = _f(row, "book_to_bill", 1.0 + industry_z * 0.08)
        return float(np.tanh((btb - 1.0) * 6.0))
    if mt == "fab_capex":
        capex = _f(row, "fab_capex_growth") or (pmi * 0.4 + ndx * 0.3)
        return float(np.tanh(capex * 2.5))
    if mt == "nrr":
        nrr = _f(row, "nrr", 1.05 + industry_z * 0.03)
        return float(np.tanh((nrr - 1.10) * 8.0))
    if mt == "arr_growth":
        arr = _f(row, "arr_growth") or growth
        return float(np.tanh(arr * 2.5 + ndx * 0.4))
    if mt == "hardware_margin":
        hw = margin if margin else 0.28 + industry_z * 0.04
        return float(np.tanh((hw - 0.25) * 5.0))
    if mt == "nim":
        nim = _f(row, "nim") or (0.025 + rate_shock * 0.08 + industry_z * 0.01)
        return float(np.tanh((nim - 0.025) * 25.0))
    if mt == "deposit_beta":
        beta = _f(row, "deposit_beta", 0.45 - rate_shock * 0.2)
        return float(np.tanh((0.55 - beta) * 3.0))
    if mt == "combined_ratio":
        cr = _f(row, "combined_ratio", 0.96 - industry_z * 0.02)
        return float(np.tanh((0.98 - cr) * 8.0))
    if mt == "actuarial_loss":
        loss = _f(row, "actuarial_loss_ratio", 0.82 - industry_z * 0.02)
        return float(np.tanh((0.85 - loss) * 5.0 - rate_shock * 0.3))
    if mt == "aum_adv":
        vol = _f(row, "adv_growth") or (macro_score * 0.5 + _f(macro, "vix", 20.0) / 100.0)
        return float(np.tanh(vol * 2.0))
    if mt == "net_charge_off":
        nco = _f(row, "net_charge_off", 0.03 - macro_score * 0.01)
        return float(np.tanh((0.04 - nco) * 12.0))
    if mt == "fcf_breakeven":
        fcf = _f(row, "fcf_yield") or (industry_z * 0.05 + macro_score * 0.1)
        return float(np.tanh(fcf * 8.0))
    if mt == "rig_count":
        rig = _f(row, "rig_count_change") or (pmi * 0.35 + macro_score * 0.2)
        return float(np.tanh(rig * 2.0))
    if mt == "upstream_capex":
        cap = _f(row, "upstream_capex_growth") or (pmi * 0.3 + residual * 0.2)
        return float(np.tanh(cap * 2.5))
    if mt == "lcoe":
        lcoe = _f(row, "lcoe_decline") or (-rate_shock * 0.4 + pmi * 0.2)
        return float(np.tanh(lcoe * 2.0))
    if mt == "allowed_roe":
        roe = _f(row, "allowed_roe", 0.095 - rate_shock * 0.05)
        return float(np.tanh((roe - 0.09) * 15.0))
    if mt == "dealer_inventory":
        inv = _f(row, "dealer_inventory_days", 55.0 - industry_z * 5.0)
        return float(np.tanh((60.0 - inv) / 25.0))
    if mt == "pricing_power":
        pp = _f(row, "pricing_power") or industry_z * 0.2 + macro_score * 0.15
        return float(np.tanh(pp * 2.5))
    if mt == "revpar":
        rp = _f(row, "revpar_growth") or (macro_score * 0.35 + industry_z * 0.2)
        return float(np.tanh(rp * 3.0))
    if mt == "same_store_sales":
        sss = _f(row, "same_store_sales") or industry_z * 0.15
        return float(np.tanh(sss * 4.0))
    if mt == "inventory_turnover":
        turn = _f(row, "inventory_turnover") or (1.8 + industry_z * 0.2)
        return float(np.tanh((turn - 2.0) * 1.5))
    if mt == "margin_stability":
        stab = margin if margin else (0.22 + industry_z * 0.03)
        return float(np.tanh((stab - 0.20) * 6.0 - vix * 0.01))
    if mt == "volume_price_mix":
        mix = _f(row, "volume_price_mix") or industry_z * 0.18
        return float(np.tanh(mix * 3.0))
    if mt == "defense_backlog":
        bl = _f(row, "backlog_growth") or (0.05 + industry_z * 0.1)
        return float(np.tanh(bl * 4.0))
    if mt == "yield_ton_mile":
        ytm = _f(row, "yield_ton_mile") or industry_z * 0.2
        return float(np.tanh(ytm * 3.0 + pmi * 0.25))
    if mt == "operating_ratio":
        oratio = _f(row, "operating_ratio", 0.62 - industry_z * 0.03)
        return float(np.tanh((0.65 - oratio) * 6.0))
    if mt == "dealer_destocking":
        destock = _f(row, "dealer_destock_velocity") or industry_z * 0.25
        return float(np.tanh(destock * 2.5))
    if mt == "capacity_utilization":
        util = _f(row, "capacity_utilization", 0.78 + industry_z * 0.04)
        return float(np.tanh((util - 0.75) * 5.0))
    if mt == "gas_spread":
        spread = _f(row, "gas_spread") or (pmi * 0.3 + industry_z * 0.15)
        return float(np.tanh(spread * 2.5))
    if mt == "cash_cost":
        cost = _f(row, "cash_cost_margin") or industry_z * 0.2
        return float(np.tanh(cost * 2.5 + macro_score * 0.2))
    if mt == "postpaid_churn":
        churn = _f(row, "postpaid_churn", 0.018 - industry_z * 0.002)
        return float(np.tanh((0.02 - churn) * 30.0 - rate_shock * 0.2))
    if mt == "arpu_dau":
        arpu = _f(row, "arpu_growth") or (ndx * 0.6 + industry_z * 0.2)
        return float(np.tanh(arpu * 3.0))
    if mt == "content_roi":
        roi = _f(row, "content_roi") or industry_z * 0.2
        return float(np.tanh(roi * 2.5))
    if mt == "price_escalator":
        esc = _f(row, "price_escalator") or (0.03 + industry_z * 0.02)
        return float(np.tanh(esc * 8.0))
    if mt == "gmroii":
        gm = _f(row, "gmroii") or industry_z * 0.25
        return float(np.tanh(gm * 3.0))
    if mt == "spot_charter":
        spot = _f(row, "spot_charter_rate") or industry_z * 0.3
        return float(np.tanh(spot * 2.5))
    if mt == "spark_spread":
        spark = _f(row, "spark_spread") or industry_z * 0.25
        return float(np.tanh(spark * 3.0))
    if mt == "contract_retention":
        ret = _f(row, "contract_retention", 0.92 + industry_z * 0.02)
        return float(np.tanh((ret - 0.90) * 8.0))
    if mt == "working_capital":
        wc = _f(row, "working_capital_days", 45.0 - industry_z * 4.0)
        return float(np.tanh((50.0 - wc) / 20.0))

    return float(np.tanh(industry_z * 0.4 + mom * 0.2))


def _compute_macro_alignment(spec: CategorySpec, macro: dict | None) -> float:
    """[-1, 1] macro tailwind alignment for the category correlation_type."""
    macro = macro or {}
    ct = spec.correlation_type
    pmi = _f(macro, "pmi_score")
    macro_score = _f(macro, "macro_score")
    rate_shock = _f(macro, "rate_shock_20d")
    spread = _f(macro, "spread_10y2y")
    ndx = _f(macro, "nasdaq_ret_5d")
    vix = _f(macro, "vix", 20.0)

    if ct == "binary_event":
        return float(np.tanh(-abs(ndx) * 0.5 + (22.0 - vix) * 0.02))
    if ct == "defensive_low_beta":
        return float(np.tanh((vix - 20.0) * 0.04 + macro_score * -0.15))
    if ct == "inverse_rates":
        return float(np.tanh(-rate_shock * 1.2 - max(0.0, spread) * 0.15))
    if ct == "growth_high_beta":
        return float(np.tanh(ndx * 4.0 + pmi * 0.25 - rate_shock * 0.35))
    if ct in ("hyper_cyclical", "extreme_cyclical", "cyclical_indicator", "early_cyclical"):
        return float(np.tanh(pmi * 0.55 + macro_score * 0.35 + ndx * 0.25))
    if ct in ("commodity_inflation", "commodity_volatile", "commodity_decoupled", "energy_trading"):
        return float(np.tanh(pmi * 0.45 + macro_score * 0.25))
    if ct == "defensive_utility":
        return float(np.tanh(-rate_shock * 0.9 + (vix - 18.0) * 0.02))
    if ct == "defensive_yield":
        return float(np.tanh(-rate_shock * 0.85 + (vix - 19.0) * 0.025))
    if ct in ("defensive", "defensive_staple", "defensive_consumer", "defensive_industrial", "sovereign_defensive"):
        return float(np.tanh((vix - 18.0) * 0.03 - macro_score * 0.1))
    if ct == "rate_sensitive_growth":
        return float(np.tanh(ndx * 2.5 - rate_shock * 0.9 + pmi * 0.2))
    if ct == "market_levered":
        return float(np.tanh(macro_score * 0.5 + ndx * 2.0 + vix * 0.01))
    if ct == "systemic_sensitive":
        return float(np.tanh(macro_score * 0.35 - abs(rate_shock) * 0.4))
    if ct == "bond_correlated":
        return float(np.tanh(-rate_shock * 0.7 + spread * 0.1))
    if ct in ("consumer_cyclical", "high_beta_discretionary", "volatile_discretionary", "wealth_correlated"):
        return float(np.tanh(macro_score * 0.45 + ndx * 1.5))
    if ct in ("moderate_cyclical", "moderate_consumer", "cyclical_cre", "office_cyclical", "housing_cyclical"):
        return float(np.tanh(pmi * 0.35 + macro_score * 0.25 + ndx * 0.5))
    if ct in ("growth_hybrid", "tech_linked", "resilient_growth"):
        return float(np.tanh(ndx * 2.0 + pmi * 0.3 - rate_shock * 0.25))
    if ct in ("industrial_cyclical", "capex_cyclical", "volume_cyclical", "delayed_cyclical"):
        return float(np.tanh(pmi * 0.5 + macro_score * 0.2))
    if ct == "discretionary_media":
        return float(np.tanh(ndx * 1.8 + macro_score * 0.25))
    return float(np.tanh(macro_score * 0.3 + ndx * 0.8 + pmi * 0.2))


def _compute_group_signal(spec: CategorySpec, headlines: list[str] | None) -> float:
    text = _headline_text(headlines)
    if not text:
        return 0.0
    group_hit = _match_score(text, spec.group_keywords) > 0.15
    bull = _match_score(text, spec.bull_keywords)
    bear = _match_score(text, spec.bear_keywords)
    signal = bull - bear
    if group_hit:
        signal *= 1.15
    return float(np.clip(signal, -1.0, 1.0))


def _resolve_spec(symbol: str, row: dict | None) -> CategorySpec | None:
    if get_spec_by_industry_id is None:
        return None
    iid = None
    if row:
        iid = row.get("industry_id") or row.get("primary_industry_id")
    if not iid:
        prof = get_industry_profile(symbol.strip().upper())
        iid = prof.get("primary_industry_id") or prof.get("industry_id")
    if not iid or str(iid) == "unclassified":
        return None
    return get_spec_by_industry_id(str(iid))


def _evaluate_blended_category_decision(
    symbol: str,
    row: dict | None,
    macro: dict | None,
    headlines: list[str] | None,
    blend: dict[str, float],
) -> CategoryDecisionResult:
    """Weighted category decision across similar industry neighbors."""
    merged = CategoryDecisionResult()
    parts = 0
    for iid, w in sorted(blend.items(), key=lambda x: -x[1]):
        if float(w) < 0.05:
            continue
        rf = dict(row or {})
        rf.pop("blend_weights", None)
        rf.pop("industries", None)
        rf["industry_id"] = iid
        rf["primary_industry_id"] = iid
        part = evaluate_category_decision(symbol, rf, macro, headlines)
        wt = float(w)
        parts += 1
        merged.score_delta += wt * part.score_delta
        merged.p_up_delta += wt * part.p_up_delta
        merged.family_bias += wt * part.family_bias
        merged.metric_proxy += wt * part.metric_proxy
        merged.macro_alignment += wt * part.macro_alignment
        merged.group_signal += wt * part.group_signal
        merged.buy_quality += wt * part.buy_quality
        if part.block_buy:
            merged.block_buy = True
            merged.block_reason = part.block_reason or merged.block_reason
        if part.warn_buy:
            merged.warn_buy = True
        merged.notes.extend([f"{iid}:{n}" for n in part.notes[:2] if n != f"category={iid}"])

    if parts:
        merged.notes.append(f"blended_categories={parts}")
    merged.score_delta = float(np.clip(merged.score_delta, -0.25, 0.30))
    merged.p_up_delta = float(np.clip(merged.p_up_delta, 0.0, 0.12))
    merged.family_bias = float(np.clip(merged.family_bias, -0.20, 0.25))
    merged.buy_quality = float(np.clip(merged.buy_quality, 0.0, 1.0))
    return merged


def evaluate_category_decision(
    symbol: str,
    row: dict | None,
    macro: dict | None,
    headlines: list[str] | None,
) -> CategoryDecisionResult:
    """Enhancement-focused category decision with selective block/warn gates."""
    sym = symbol.strip().upper()
    blend: dict[str, float] = {}
    if row:
        blend = dict(row.get("blend_weights") or {})
    if not blend and row and row.get("industries"):
        for item in row.get("industries") or []:
            if isinstance(item, dict) and item.get("industry_id"):
                blend[str(item["industry_id"])] = float(item.get("weight") or 0.0)
    if len(blend) > 1 and os.getenv("USE_INDUSTRY_SIMILARITY_BLEND", "true").lower() in ("1", "true", "yes"):
        return _evaluate_blended_category_decision(sym, row, macro, headlines, blend)

    res = CategoryDecisionResult()
    spec = _resolve_spec(symbol, row)
    if spec is None:
        res.notes.append("no_category_spec")
        return res

    text = _headline_text(headlines)
    metric_proxy = _compute_metric_proxy(spec, row, macro)
    macro_alignment = _compute_macro_alignment(spec, macro)
    group_signal = _compute_group_signal(spec, headlines)

    res.metric_proxy = metric_proxy
    res.macro_alignment = macro_alignment
    res.group_signal = group_signal

    # Enhancement-first score composition
    score = metric_proxy * 0.10 + max(0.0, macro_alignment) * 0.08 + max(0.0, group_signal) * 0.09
    p_up = max(0.0, metric_proxy) * 0.03 + max(0.0, macro_alignment) * 0.025 + max(0.0, group_signal) * 0.02
    family = group_signal * 0.05 + macro_alignment * 0.03

    # Binary event: block on bear headlines
    if spec.correlation_type == "binary_event":
        for kw in spec.bear_keywords:
            if kw.lower() in text:
                res.block_buy = True
                res.block_reason = f"{spec.slug}: binary bear headline ({kw})"
                res.notes.append("binary_event_bear_block")
                break
        if macro_alignment > 0.05:
            score += macro_alignment * 0.04
            p_up += 0.01

    # Inverse rates: penalize rate shocks; severe misalignment blocks
    if spec.correlation_type in ("inverse_rates", "defensive_yield", "bond_correlated", "defensive_utility"):
        rate_shock = _f(macro, "rate_shock_20d")
        spread = _f(macro, "spread_10y2y")
        if rate_shock > 0.18 or (rate_shock > 0.12 and spread < -0.25):
            penalty = min(0.14, rate_shock * 0.35)
            score = max(0.0, score - penalty)
            p_up = max(0.0, p_up - penalty * 0.4)
            res.warn_buy = True
            res.notes.append("rate_headwind_warn")
            if spec.correlation_type == "inverse_rates" and rate_shock > 0.22:
                res.block_buy = True
                res.block_reason = f"{spec.slug}: severe rate shock headwind"
                res.notes.append("inverse_rates_block")
        elif rate_shock < -0.08:
            boost = abs(rate_shock) * 0.12
            score += boost
            p_up += boost * 0.35
            res.notes.append("rate_relief_boost")

    # Defensive low-beta: boost when VIX elevated
    if spec.correlation_type in ("defensive_low_beta", "defensive", "defensive_staple", "defensive_consumer", "defensive_industrial", "sovereign_defensive"):
        vix = _f(macro, "vix", 20.0)
        if vix > 22.0:
            boost = float(np.tanh((vix - 22.0) / 8.0)) * 0.10
            score += boost
            family += boost * 0.6
            p_up += boost * 0.25
            res.notes.append("defensive_vix_boost")

    # Growth high-beta: boost when Nasdaq up
    if spec.correlation_type in ("growth_high_beta", "tech_linked", "growth_hybrid", "hyper_cyclical"):
        ndx = _f(macro, "nasdaq_ret_5d")
        if ndx > 0.02:
            boost = ndx * 0.55
            score += boost
            p_up += boost * 0.35
            family += boost * 0.25
            res.notes.append("nasdaq_tailwind_boost")
        elif ndx < -0.035:
            res.warn_buy = True
            score = max(0.0, score + ndx * 0.25)
            res.notes.append("nasdaq_drawdown_warn")

    # Commodity-linked: respond to PMI / macro
    if spec.correlation_type in (
        "commodity_inflation", "commodity_volatile", "commodity_decoupled",
        "energy_trading", "cyclical_indicator", "industrial_cyclical", "capex_cyclical",
        "extreme_cyclical", "hyper_cyclical", "volume_cyclical", "delayed_cyclical",
    ):
        pmi = _f(macro, "pmi_score")
        macro_score = _f(macro, "macro_score")
        if pmi > 0.45:
            boost = pmi * 0.07
            score += boost
            p_up += boost * 0.3
            res.notes.append("commodity_pmi_boost")
        if macro_score < -0.4:
            res.warn_buy = True
            score = max(0.0, score - 0.05)
            res.notes.append("commodity_macro_warn")
            if macro_score < -0.55 and pmi < 0.0:
                res.block_buy = True
                res.block_reason = f"{spec.slug}: severe commodity-cycle macro misalignment"
                res.notes.append("commodity_macro_block")

    # Group headline tailwinds / headwinds (non-blocking unless binary)
    if group_signal > 0.12:
        score += group_signal * 0.06
        p_up += group_signal * 0.02
        family += group_signal * 0.04
        res.notes.append("group_bull_headlines")
    elif group_signal < -0.18 and spec.correlation_type != "binary_event":
        res.warn_buy = True
        score = max(0.0, score + group_signal * 0.04)
        family += group_signal * 0.05
        res.notes.append("group_bear_headlines")

    res.score_delta = float(np.clip(score, -0.25, 0.30))
    res.p_up_delta = float(np.clip(p_up, 0.0, 0.12))
    res.family_bias = float(np.clip(family, -0.20, 0.25))
    res.buy_quality = float(np.clip(0.5 + metric_proxy * 0.2 + macro_alignment * 0.15 + group_signal * 0.15, 0.0, 1.0))
    ai_conf = _f(row, "ai_confidence") if row else 0.0
    if ai_conf >= 0.85 and res.score_delta > 0:
        boost = (ai_conf - 0.85) * 0.12
        res.score_delta = float(np.clip(res.score_delta + boost, -0.25, 0.30))
        res.notes.append("ai_confidence_boost")
    res.notes.append(f"category={spec.slug}")
    return res
