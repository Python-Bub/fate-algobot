"""Curriculum → sleeve routing for full investing guide + live factors.

Deep chapters live in investing.knowledge.* (catalog-complete).
Auto-merged from investing.catalog; overrides for HFT/day/passive.
"""

from __future__ import annotations

from typing import Literal

Sleeve = Literal["hft", "day_trade", "fortress", "weekly", "longterm", "knowledge"]

CURRICULUM_SLEEVE_MAP: dict[str, tuple[Sleeve, ...]] = {
    "lee_chin_five_laws": ("fortress", "weekly", "longterm", "knowledge"),
    "convertible_arb": ("longterm", "weekly", "fortress", "knowledge"),  # advanced
    "distressed_debt": ("longterm", "weekly", "fortress", "knowledge"),  # advanced
    "esg": ("longterm", "weekly", "fortress", "knowledge"),  # advanced
    "leveraged_investing": ("longterm", "weekly", "fortress", "knowledge"),  # advanced
    "merger_arb": ("longterm", "weekly", "fortress", "knowledge"),  # advanced
    "multi_asset": ("longterm", "weekly", "fortress", "knowledge"),  # advanced
    "portfolio_optimization": ("longterm", "weekly", "fortress", "knowledge"),  # advanced
    "sector_rotation": ("longterm", "weekly", "fortress", "knowledge"),  # advanced
    "strategic_aa": ("longterm", "weekly", "fortress", "knowledge"),  # advanced
    "tactical_aa": ("longterm", "weekly", "fortress", "knowledge"),  # advanced
    "tax_loss_harvesting": ("longterm", "weekly", "fortress", "knowledge"),  # advanced
    "thematic_investing": ("longterm", "weekly", "fortress", "knowledge"),  # advanced
    "volatility_trading": ("longterm", "weekly", "fortress", "knowledge"),  # advanced
    "angel_investing": ("knowledge",),  # alternative
    "collectibles": ("longterm", "knowledge"),  # alternative
    "crowdfunding": ("knowledge",),  # alternative
    "fine_art": ("longterm", "knowledge"),  # alternative
    "private_equity": ("longterm", "knowledge"),  # alternative
    "rare_coins": ("longterm", "knowledge"),  # alternative
    "seed_investing": ("longterm", "knowledge"),  # alternative
    "venture_capital": ("longterm", "knowledge"),  # alternative
    "watches": ("longterm", "knowledge"),  # alternative
    "wine": ("longterm", "knowledge"),  # alternative
    "alt_data": ("longterm", "weekly", "fortress", "knowledge"),  # analysis
    "competitive": ("longterm", "weekly", "fortress", "knowledge"),  # analysis
    "comps": ("longterm", "weekly", "fortress", "knowledge"),  # analysis
    "dcf": ("longterm", "weekly", "fortress", "knowledge"),  # analysis
    "economic_moat": ("longterm", "weekly", "fortress", "knowledge"),  # analysis
    "factor_analysis": ("longterm", "weekly", "fortress", "knowledge"),  # analysis
    "financial_statement": ("longterm", "weekly", "fortress", "knowledge"),  # analysis
    "fundamental": ("longterm", "weekly", "fortress", "knowledge"),  # analysis
    "industry": ("longterm", "weekly", "fortress", "knowledge"),  # analysis
    "macro_analysis": ("longterm", "weekly", "fortress", "knowledge"),  # analysis
    "management": ("longterm", "weekly", "fortress", "knowledge"),  # analysis
    "monte_carlo": ("longterm", "weekly", "fortress", "knowledge"),  # analysis
    "precedent_transactions": ("longterm", "weekly", "fortress", "knowledge"),  # analysis
    "qualitative": ("longterm", "weekly", "fortress", "knowledge"),  # analysis
    "quant_analysis": ("longterm", "weekly", "fortress", "knowledge"),  # analysis
    "risk": ("longterm", "weekly", "fortress", "knowledge"),  # analysis
    "scenario": ("longterm", "weekly", "fortress", "knowledge"),  # analysis
    "sentiment": ("longterm", "weekly", "fortress", "knowledge"),  # analysis
    "technical": ("longterm", "weekly", "fortress", "knowledge"),  # analysis
    "valuation": ("longterm", "weekly", "fortress", "knowledge"),  # analysis
    "wacc": ("longterm", "weekly", "fortress", "knowledge"),  # analysis
    "art": ("longterm", "weekly", "knowledge"),  # asset_class
    "bonds": ("longterm", "weekly", "knowledge"),  # asset_class
    "cash": ("longterm", "weekly", "knowledge"),  # asset_class
    "collectibles_asset": ("longterm", "weekly", "knowledge"),  # asset_class
    "commodities": ("longterm", "weekly", "knowledge"),  # asset_class
    "crypto": ("longterm", "weekly", "knowledge"),  # asset_class
    "etfs": ("longterm", "weekly", "knowledge"),  # asset_class
    "forwards": ("longterm", "weekly", "knowledge"),  # asset_class
    "futures": ("longterm", "weekly", "knowledge"),  # asset_class
    "gold": ("longterm", "weekly", "knowledge"),  # asset_class
    "hedge_funds": ("longterm", "weekly", "knowledge"),  # asset_class
    "index_funds": ("longterm", "weekly", "knowledge"),  # asset_class
    "mutual_funds": ("longterm", "weekly", "knowledge"),  # asset_class
    "natural_gas": ("longterm", "weekly", "knowledge"),  # asset_class
    "oil": ("longterm", "weekly", "knowledge"),  # asset_class
    "options_asset": ("longterm", "weekly", "knowledge"),  # asset_class
    "pe_asset": ("longterm", "weekly", "knowledge"),  # asset_class
    "platinum": ("longterm", "weekly", "knowledge"),  # asset_class
    "real_estate_asset": ("longterm", "weekly", "knowledge"),  # asset_class
    "reits": ("longterm", "weekly", "knowledge"),  # asset_class
    "silver": ("longterm", "weekly", "knowledge"),  # asset_class
    "stablecoins": ("longterm", "weekly", "knowledge"),  # asset_class
    "stocks": ("longterm", "weekly", "knowledge"),  # asset_class
    "swaps": ("longterm", "weekly", "knowledge"),  # asset_class
    "vc_asset": ("longterm", "weekly", "knowledge"),  # asset_class
    "butterfly": ("knowledge", "longterm"),  # derivatives
    "calendar_spreads": ("knowledge", "longterm"),  # derivatives
    "covered_calls": ("knowledge", "longterm"),  # derivatives
    "credit_spreads": ("knowledge", "longterm"),  # derivatives
    "debit_spreads": ("knowledge", "longterm"),  # derivatives
    "iron_condors": ("knowledge", "longterm"),  # derivatives
    "options": ("knowledge", "longterm"),  # derivatives
    "protective_puts": ("knowledge", "longterm"),  # derivatives
    "straddles": ("knowledge", "longterm"),  # derivatives
    "strangles": ("knowledge", "longterm"),  # derivatives
    "compounders": ("fortress", "weekly", "longterm"),  # growth
    "disruptor": ("fortress", "weekly", "longterm"),  # growth
    "early_stage": ("fortress", "weekly", "longterm"),  # growth
    "garp": ("fortress", "weekly", "longterm"),  # growth
    "growth": ("fortress", "weekly", "longterm"),  # growth
    "hypergrowth": ("fortress", "weekly", "longterm"),  # growth
    "innovation": ("fortress", "weekly", "longterm"),  # growth
    "momentum_growth": ("fortress", "weekly", "longterm"),  # growth
    "quality_growth": ("fortress", "weekly", "longterm"),  # growth
    "secular_growth": ("fortress", "weekly", "longterm"),  # growth
    "bond_laddering": ("longterm", "weekly", "knowledge"),  # income
    "covered_call_income": ("longterm", "weekly", "knowledge"),  # income
    "dividend": ("longterm", "weekly", "knowledge"),  # income
    "dividend_growth": ("longterm", "weekly", "knowledge"),  # income
    "high_yield": ("longterm", "weekly", "knowledge"),  # income
    "infrastructure_income": ("longterm", "weekly", "knowledge"),  # income
    "municipal_bonds": ("longterm", "weekly", "knowledge"),  # income
    "preferred_shares": ("longterm", "weekly", "knowledge"),  # income
    "preferred_stock": ("longterm", "weekly", "knowledge"),  # income
    "reit_income": ("longterm", "weekly", "knowledge"),  # income
    "bottom_up": ("longterm", "weekly", "fortress"),  # macro
    "business_cycle": ("longterm", "weekly", "fortress"),  # macro
    "commodity_macro": ("longterm", "weekly", "fortress"),  # macro
    "currency": ("longterm", "weekly", "fortress"),  # macro
    "deflation": ("longterm", "weekly", "fortress"),  # macro
    "global_macro": ("longterm", "weekly", "fortress"),  # macro
    "inflation": ("longterm", "weekly", "fortress"),  # macro
    "interest_rate": ("longterm", "weekly", "fortress"),  # macro
    "top_down": ("longterm", "weekly", "fortress"),  # macro
    "buy_and_hold": ("longterm", "weekly"),  # passive
    "core_satellite": ("longterm", "weekly", "fortress"),  # passive
    "dca": ("longterm", "weekly"),  # passive
    "etf_investing": ("longterm", "weekly", "fortress", "day_trade", "hft"),  # passive
    "index_investing": ("longterm", "weekly", "fortress"),  # passive
    "lazy_portfolios": ("longterm", "weekly", "fortress"),  # passive
    "target_date": ("longterm", "weekly", "fortress"),  # passive
    "ai_investing": ("fortress", "weekly", "longterm"),  # quant
    "algo_trading": ("hft", "day_trade", "fortress"),  # quant
    "automated_portfolio": ("fortress", "weekly", "longterm"),  # quant
    "factor": ("fortress", "weekly", "longterm"),  # quant
    "hft": ("hft",),  # quant
    "ml_investing": ("fortress", "weekly", "longterm"),  # quant
    "quant": ("fortress", "weekly", "longterm"),  # quant
    "risk_parity": ("fortress", "weekly", "longterm"),  # quant
    "smart_beta": ("fortress", "weekly", "longterm"),  # quant
    "stat_arb": ("fortress", "weekly", "hft"),  # quant
    "farmland": ("longterm", "knowledge"),  # real_assets
    "infrastructure_assets": ("longterm", "knowledge"),  # real_assets
    "precious_metals": ("longterm", "knowledge"),  # real_assets
    "real_estate": ("longterm", "knowledge"),  # real_assets
    "timberland": ("longterm", "knowledge"),  # real_assets
    "3d_printing": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "aerospace": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "ag_equipment": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "agriculture": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "ai": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "airlines": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "airports": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "aluminum": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "apparel": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "asset_management": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "auto_parts": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "automobiles": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "autonomous_vehicles": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "banks": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "battery_storage": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "beverage_companies": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "biotechnology": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "blockchain_infra": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "carbon_capture": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "cement": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "chemicals": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "clean_water": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "cloud": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "communication": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "construction": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "consumer_discretionary": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "consumer_electronics": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "consumer_staples": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "copper": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "credit_cards": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "cruise_lines": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "cybersecurity": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "data_centers": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "defense": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "diagnostics": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "digital_advertising": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "digital_payments": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "drone_technology": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "drug_manufacturing": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "ecommerce": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "electric_utilities": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "emerging_industries": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "energy": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "engineering": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "ev_manufacturers": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "exchanges": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "farming": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "fertilizers": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "financials": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "fintech": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "fisheries": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "food_distribution": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "food_manufacturers": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "freight_forwarding": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "fusion_energy": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "gaming": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "gas_utilities": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "gene_editing": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "glass": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "hardware": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "health_insurance": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "healthcare": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "healthcare_services": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "hospitals": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "hotels": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "household_products": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "hydrogen": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "industrials": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "insurance": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "internet_services": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "investment_banks": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "launch_providers": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "lithium": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "livestock": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "lng": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "logistics": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "luxury_goods": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "machinery": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "materials": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "medical_devices": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "mortgage_lenders": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "natural_gas": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "nuclear": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "oil_exploration": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "oil_refining": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "packaging": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "paper": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "personal_care": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "pharmaceuticals": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "pipelines": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "ports": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "public_transit": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "quantum": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "railroads": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "rare_earths": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "real_estate_sector": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "recycling": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "reit_cell_tower": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "reit_datacenter": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "reit_healthcare": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "reit_hotel": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "reit_industrial": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "reit_net_lease": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "reit_office": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "reit_residential": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "reit_retail": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "reit_self_storage": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "renewable_utilities": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "restaurants": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "retail": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "robotics": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "satellites": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "sector_private_equity": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "sector_venture_capital": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "seeds": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "semiconductors": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "shipping": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "social_media": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "software": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "solar": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "space": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "space_infrastructure": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "steel": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "streaming": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "synthetic_biology": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "technology": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "telecommunications": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "tobacco": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "transportation": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "travel": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "trucking": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "utilities": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "waste_management": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "water_utilities": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "wearable_technology": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "wind": ("fortress", "weekly", "longterm", "knowledge"),  # sector
    "bear_strategies": ("knowledge", "fortress", "weekly"),  # short
    "inverse_etfs": ("knowledge", "fortress", "weekly"),  # short
    "long_short": ("knowledge", "fortress", "weekly"),  # short
    "market_neutral": ("knowledge", "fortress", "weekly"),  # short
    "pair_trading": ("knowledge", "fortress", "weekly"),  # short
    "short_selling": ("knowledge", "fortress", "weekly"),  # short
    "breakout": ("day_trade", "fortress", "weekly"),  # trading
    "day_trading": ("day_trade",),  # trading
    "event_driven": ("day_trade", "fortress", "weekly"),  # trading
    "event_calendar": ("day_trade", "fortress", "weekly", "longterm"),
    "event_learn": ("day_trade", "fortress", "weekly", "longterm"),
    "event_ingenuity": ("day_trade", "fortress", "weekly", "longterm"),
    "proven_online": ("day_trade", "fortress", "weekly", "longterm"),
    "mean_reversion": ("day_trade", "fortress", "weekly"),  # trading
    "news_trading": ("day_trade", "fortress", "weekly"),  # trading
    "position_trading": ("weekly", "longterm"),  # trading
    "range_trading": ("day_trade", "fortress", "weekly"),  # trading
    "scalping": ("hft", "day_trade"),  # trading
    "swing_trading": ("fortress",),  # trading
    "trend_following": ("day_trade", "fortress", "weekly"),  # trading
    "asset_based": ("longterm", "weekly", "fortress"),  # value
    "buffett": ("longterm", "weekly", "fortress"),  # value
    "contrarian": ("longterm", "weekly", "fortress"),  # value
    "deep_value": ("longterm", "weekly", "fortress"),  # value
    "graham": ("longterm", "weekly", "fortress"),  # value
    "intrinsic_value": ("longterm", "weekly", "fortress"),  # value
    "net_net": ("longterm", "weekly", "fortress"),  # value
    "special_situations": ("longterm", "weekly", "fortress"),  # value
    "sum_of_the_parts": ("longterm", "weekly", "fortress"),  # value
    "turnaround": ("longterm", "weekly", "fortress"),  # value
}

HFT_FORBIDDEN_FAMILIES: frozenset[str] = frozenset({
    "value", "buffett", "graham", "dca", "buy_and_hold", "cramer",
    "alternative", "derivatives", "inflation", "deflation", "passive_essay",
})

def sleeves_for(topic_id: str) -> tuple[Sleeve, ...]:
    return CURRICULUM_SLEEVE_MAP.get(topic_id.strip().lower(), ("knowledge",))

def allowed_on_sleeve(topic_id: str, sleeve: Sleeve) -> bool:
    return sleeve in sleeves_for(topic_id)

def curriculum_topics() -> tuple[str, ...]:
    return tuple(sorted(CURRICULUM_SLEEVE_MAP))

