"""Yahoo GICS-ish sector/industry → FATE industry_id when handlers miss.

Ticker hints catch mega-caps. Everything else often lands on `unclassified`
because Yahoo's sector string is 'Technology' not 'semiconductor'. This map
is a math-free but deterministic prior (confidence ~0.62) so blend weights
are never zero.
"""

from __future__ import annotations

from analytics.industries.base import ClassificationResult
from analytics.industries.registry import get_handler

# Longer keys first. Matched against `"{sector} {yahoo_industry} {name}".lower()`.
_INDUSTRY_SUBSTR: tuple[tuple[str, str], ...] = (
    ("semiconductor equipment", "semi_equipment"),
    ("semiconductor", "semiconductors"),
    ("consumer electronics", "tech_hardware"),
    ("computer hardware", "tech_hardware"),
    ("application software", "application_software"),
    ("software—infrastructure", "systems_software"),
    ("software - infrastructure", "systems_software"),
    ("information technology services", "systems_software"),
    ("internet content", "interactive_media"),
    ("internet retail", "apparel_retail"),
    ("entertainment", "entertainment_streaming"),
    ("telecom", "wireless_telecom"),
    ("oil & gas e&p", "oil_gas_ep"),
    ("oil & gas integrated", "integrated_oil_gas"),
    ("oil & gas equipment", "oil_gas_equipment"),
    ("oil & gas midstream", "oil_gas_equipment"),
    ("oil & gas refining", "integrated_oil_gas"),
    ("uranium", "metals_mining"),
    ("gold", "metals_mining"),
    ("copper", "metals_mining"),
    ("steel", "metals_mining"),
    ("chemical", "chemicals"),
    ("banks—diversified", "diversified_banks"),
    ("banks - diversified", "diversified_banks"),
    ("banks—regional", "regional_banks"),
    ("banks - regional", "regional_banks"),
    ("credit services", "consumer_finance"),
    ("capital markets", "financial_data_exchanges"),
    ("asset management", "financial_data_exchanges"),
    ("insurance—life", "life_health_insurance"),
    ("insurance - life", "life_health_insurance"),
    ("insurance—property", "property_casualty_insurance"),
    ("insurance - property", "property_casualty_insurance"),
    ("biotechnology", "biotech"),
    ("drug manufacturers", "big_pharma"),
    ("medical devices", "medical_devices"),
    ("diagnostics & research", "life_sciences_tools"),
    ("medical instruments", "medical_devices"),
    ("health information", "healthcare_technology"),
    ("medical care facilities", "healthcare_providers"),
    ("healthcare plans", "healthcare_providers"),
    ("reit—residential", "residential_reits"),
    ("reit - residential", "residential_reits"),
    ("reit—office", "commercial_office_reits"),
    ("reit - office", "commercial_office_reits"),
    ("reit—retail", "retail_reits"),
    ("reit - retail", "retail_reits"),
    ("reit—industrial", "industrial_logistics_reits"),
    ("reit - industrial", "industrial_logistics_reits"),
    ("reit—specialty", "specialized_reits"),
    ("reit - specialty", "specialized_reits"),
    ("auto manufacturers", "auto_manufacturers"),
    ("auto & truck", "auto_manufacturers"),
    ("luxury goods", "luxury_goods"),
    ("apparel retail", "apparel_retail"),
    ("apparel manufacturing", "apparel_retail"),
    ("restaurants", "restaurants_food"),
    ("packaged foods", "packaged_foods"),
    ("household & personal", "household_personal_products"),
    ("discount stores", "hypermarkets_discount"),
    ("grocery stores", "hypermarkets_discount"),
    ("aerospace", "aerospace_defense"),
    ("defense", "aerospace_defense"),
    ("airlines", "air_freight_logistics"),
    ("integrated freight", "air_freight_logistics"),
    ("railroads", "railroads"),
    ("farm & heavy construction", "construction_machinery"),
    ("building products", "building_products"),
    ("utilities—regulated", "electric_gas_utilities"),
    ("utilities - regulated", "electric_gas_utilities"),
    ("utilities—renewable", "renewable_energy"),
    ("solar", "renewable_energy"),
    ("lodging", "hotels_resorts_cruise"),
    ("resorts & casinos", "hotels_resorts_cruise"),
    ("waste management", "environmental_waste"),
    ("marine shipping", "marine_shipping"),
    ("specialty business services", "commercial_services"),
    ("conglomerates", "commercial_services"),
)

_SECTOR_DEFAULT: dict[str, str] = {
    "technology": "application_software",
    "communication services": "interactive_media",
    "consumer cyclical": "apparel_retail",
    "consumer defensive": "packaged_foods",
    "healthcare": "big_pharma",
    "financial services": "diversified_banks",
    "financials": "diversified_banks",
    "energy": "integrated_oil_gas",
    "industrials": "commercial_services",
    "basic materials": "chemicals",
    "real estate": "specialized_reits",
    "utilities": "electric_gas_utilities",
}


def match_sector_fallback(
    sector: str,
    yahoo_industry: str = "",
    company_name: str = "",
) -> ClassificationResult | None:
    blob = f"{sector} {yahoo_industry} {company_name}".lower()
    if not blob.strip():
        return None
    iid = None
    reason = ""
    for needle, hid in _INDUSTRY_SUBSTR:
        if needle in blob:
            iid = hid
            reason = f"yahoo_industry:{needle}"
            break
    if iid is None:
        sec = (sector or "").strip().lower()
        iid = _SECTOR_DEFAULT.get(sec)
        if iid:
            reason = f"yahoo_sector:{sec}"
    if not iid:
        return None
    h = get_handler(iid)
    conf = 0.72 if reason.startswith("yahoo_industry") else 0.58
    return ClassificationResult(
        industry_id=h.INDUSTRY_ID,
        industry_name=h.INDUSTRY_NAME,
        confidence=conf,
        etf_proxy=h.ETF_PROXY,
        comovement_mode=h.COMOVEMENT_MODE.value,
        reasons=["sector_fallback", reason],
    )
