"""User-facing 50 industry category slugs — matches the original taxonomy list."""

from __future__ import annotations

# (category_number, category_slug, display_name, internal_industry_id)
USER_CATEGORIES: tuple[tuple[int, str, str, str], ...] = (
    (1, "biotechnology", "Biotechnology", "biotech"),
    (2, "pharmaceuticals", "Pharmaceuticals", "big_pharma"),
    (3, "medical_devices_equipment", "Medical Devices & Equipment", "medical_devices"),
    (4, "life_sciences_tools_services", "Life Sciences Tools & Services", "life_sciences_tools"),
    (5, "healthcare_providers_services", "Healthcare Providers & Services", "healthcare_providers"),
    (6, "healthcare_technology", "Healthcare Technology", "healthcare_technology"),
    (7, "residential_reits", "Residential REITs", "residential_reits"),
    (8, "commercial_office_reits", "Commercial & Office REITs", "commercial_office_reits"),
    (9, "retail_reits", "Retail REITs", "retail_reits"),
    (10, "industrial_logistics_reits", "Industrial & Logistics REITs", "industrial_logistics_reits"),
    (11, "specialized_reits", "Specialized REITs", "specialized_reits"),
    (12, "semiconductors", "Semiconductors", "semiconductors"),
    (13, "semiconductor_equipment", "Semiconductor Equipment", "semi_equipment"),
    (14, "application_software", "Application Software", "application_software"),
    (15, "systems_software", "Systems Software", "systems_software"),
    (16, "technology_hardware_storage_peripherals", "Technology Hardware", "tech_hardware"),
    (17, "diversified_banks", "Diversified Banks", "diversified_banks"),
    (18, "regional_banks", "Regional Banks", "regional_banks"),
    (19, "property_casualty_insurance", "Property & Casualty Insurance", "property_casualty_insurance"),
    (20, "life_health_insurance", "Life & Health Insurance", "life_health_insurance"),
    (21, "financial_data_capital_markets", "Financial Data & Capital Markets", "financial_data_exchanges"),
    (22, "consumer_finance", "Consumer Finance", "consumer_finance"),
    (23, "integrated_oil_gas", "Integrated Oil & Gas", "integrated_oil_gas"),
    (24, "oil_gas_exploration_production", "Oil & Gas E&P", "oil_gas_ep"),
    (25, "oil_gas_equipment_services", "Oil & Gas Equipment & Services", "oil_gas_equipment"),
    (26, "renewable_electricity_clean_energy", "Renewable Electricity & Clean Energy", "renewable_energy"),
    (27, "electric_gas_utilities", "Electric & Gas Utilities", "electric_gas_utilities"),
    (28, "automobile_manufacturers", "Automobile Manufacturers", "auto_manufacturers"),
    (29, "luxury_goods_apparel_accessories", "Luxury Goods", "luxury_goods"),
    (30, "hotels_resorts_cruise_lines", "Hotels, Resorts & Cruise Lines", "hotels_resorts_cruise"),
    (31, "restaurants_food_services", "Restaurants & Food Services", "restaurants_food"),
    (32, "hypermarkets_supercenters", "Hypermarkets & Supercenters", "hypermarkets_discount"),
    (33, "household_personal_products", "Household & Personal Products", "household_personal_products"),
    (34, "food_products", "Food Products", "packaged_foods"),
    (35, "aerospace_defense", "Aerospace & Defense", "aerospace_defense"),
    (36, "air_freight_logistics", "Air Freight & Logistics", "air_freight_logistics"),
    (37, "railroads", "Railroads", "railroads"),
    (38, "construction_machinery_heavy_trucks", "Construction Machinery", "construction_machinery"),
    (39, "building_products_construction_materials", "Building Products", "building_products"),
    (40, "chemicals", "Chemicals", "chemicals"),
    (41, "metals_mining", "Metals & Mining", "metals_mining"),
    (42, "wireless_telecommunication_services", "Wireless Telecom", "wireless_telecom"),
    (43, "interactive_media_services", "Interactive Media & Services", "interactive_media"),
    (44, "entertainment_streaming", "Entertainment & Streaming", "entertainment_streaming"),
    (45, "environmental_waste_management", "Environmental & Waste Management", "environmental_waste"),
    (46, "apparel_retail", "Apparel Retail", "apparel_retail"),
    (47, "marine_transportation", "Marine Transportation", "marine_shipping"),
    (48, "independent_power_producers_energy_traders", "Independent Power Producers", "independent_power_producers"),
    (49, "commercial_services_supplies", "Commercial Services & Supplies", "commercial_services"),
    (50, "distributors", "Distributors", "distributors"),
)

SLUG_TO_INDUSTRY: dict[str, str] = {slug: iid for _, slug, _, iid in USER_CATEGORIES}
INDUSTRY_TO_SLUG: dict[str, str] = {iid: slug for _, slug, _, iid in USER_CATEGORIES}
SLUG_TO_NUMBER: dict[str, int] = {slug: num for num, slug, _, _ in USER_CATEGORIES}


def resolve_industry_id(key: str) -> str:
    """Accept category slug OR internal industry_id; return internal id."""
    k = str(key or "").strip().lower()
    if not k:
        return "unclassified"
    if k in SLUG_TO_INDUSTRY:
        return SLUG_TO_INDUSTRY[k]
    if k in INDUSTRY_TO_SLUG:
        return k
    return k


def category_slug_for_industry(industry_id: str) -> str:
    return INDUSTRY_TO_SLUG.get(str(industry_id or ""), str(industry_id or "unclassified"))
