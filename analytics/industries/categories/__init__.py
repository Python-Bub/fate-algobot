"""50 user-facing industry category modules."""

from analytics.industries.categories._registry import (

    INDUSTRY_TO_SLUG,
    SLUG_TO_INDUSTRY,
    USER_CATEGORIES,

    category_slug_for_industry,
    resolve_industry_id,
)

from analytics.industries.categories.biotechnology import CATEGORY as _c_biotechnology
from analytics.industries.categories.pharmaceuticals import CATEGORY as _c_pharmaceuticals
from analytics.industries.categories.medical_devices_equipment import CATEGORY as _c_medical_devices_equipment
from analytics.industries.categories.life_sciences_tools_services import CATEGORY as _c_life_sciences_tools_services
from analytics.industries.categories.healthcare_providers_services import CATEGORY as _c_healthcare_providers_services
from analytics.industries.categories.healthcare_technology import CATEGORY as _c_healthcare_technology
from analytics.industries.categories.residential_reits import CATEGORY as _c_residential_reits
from analytics.industries.categories.commercial_office_reits import CATEGORY as _c_commercial_office_reits
from analytics.industries.categories.retail_reits import CATEGORY as _c_retail_reits
from analytics.industries.categories.industrial_logistics_reits import CATEGORY as _c_industrial_logistics_reits
from analytics.industries.categories.specialized_reits import CATEGORY as _c_specialized_reits
from analytics.industries.categories.semiconductors import CATEGORY as _c_semiconductors
from analytics.industries.categories.semiconductor_equipment import CATEGORY as _c_semiconductor_equipment
from analytics.industries.categories.application_software import CATEGORY as _c_application_software
from analytics.industries.categories.systems_software import CATEGORY as _c_systems_software
from analytics.industries.categories.technology_hardware_storage_peripherals import CATEGORY as _c_technology_hardware_storage_peripherals
from analytics.industries.categories.diversified_banks import CATEGORY as _c_diversified_banks
from analytics.industries.categories.regional_banks import CATEGORY as _c_regional_banks
from analytics.industries.categories.property_casualty_insurance import CATEGORY as _c_property_casualty_insurance
from analytics.industries.categories.life_health_insurance import CATEGORY as _c_life_health_insurance
from analytics.industries.categories.financial_data_capital_markets import CATEGORY as _c_financial_data_capital_markets
from analytics.industries.categories.consumer_finance import CATEGORY as _c_consumer_finance
from analytics.industries.categories.integrated_oil_gas import CATEGORY as _c_integrated_oil_gas
from analytics.industries.categories.oil_gas_exploration_production import CATEGORY as _c_oil_gas_exploration_production
from analytics.industries.categories.oil_gas_equipment_services import CATEGORY as _c_oil_gas_equipment_services
from analytics.industries.categories.renewable_electricity_clean_energy import CATEGORY as _c_renewable_electricity_clean_energy
from analytics.industries.categories.electric_gas_utilities import CATEGORY as _c_electric_gas_utilities
from analytics.industries.categories.automobile_manufacturers import CATEGORY as _c_automobile_manufacturers
from analytics.industries.categories.luxury_goods_apparel_accessories import CATEGORY as _c_luxury_goods_apparel_accessories
from analytics.industries.categories.hotels_resorts_cruise_lines import CATEGORY as _c_hotels_resorts_cruise_lines
from analytics.industries.categories.restaurants_food_services import CATEGORY as _c_restaurants_food_services
from analytics.industries.categories.hypermarkets_supercenters import CATEGORY as _c_hypermarkets_supercenters
from analytics.industries.categories.household_personal_products import CATEGORY as _c_household_personal_products
from analytics.industries.categories.food_products import CATEGORY as _c_food_products
from analytics.industries.categories.aerospace_defense import CATEGORY as _c_aerospace_defense
from analytics.industries.categories.air_freight_logistics import CATEGORY as _c_air_freight_logistics
from analytics.industries.categories.railroads import CATEGORY as _c_railroads
from analytics.industries.categories.construction_machinery_heavy_trucks import CATEGORY as _c_construction_machinery_heavy_trucks
from analytics.industries.categories.building_products_construction_materials import CATEGORY as _c_building_products_construction_materials
from analytics.industries.categories.chemicals import CATEGORY as _c_chemicals
from analytics.industries.categories.metals_mining import CATEGORY as _c_metals_mining
from analytics.industries.categories.wireless_telecommunication_services import CATEGORY as _c_wireless_telecommunication_services
from analytics.industries.categories.interactive_media_services import CATEGORY as _c_interactive_media_services
from analytics.industries.categories.entertainment_streaming import CATEGORY as _c_entertainment_streaming
from analytics.industries.categories.environmental_waste_management import CATEGORY as _c_environmental_waste_management
from analytics.industries.categories.apparel_retail import CATEGORY as _c_apparel_retail
from analytics.industries.categories.marine_transportation import CATEGORY as _c_marine_transportation
from analytics.industries.categories.independent_power_producers_energy_traders import CATEGORY as _c_independent_power_producers_energy_traders
from analytics.industries.categories.commercial_services_supplies import CATEGORY as _c_commercial_services_supplies
from analytics.industries.categories.distributors import CATEGORY as _c_distributors

ALL_CATEGORIES = {

    "biotechnology": _c_biotechnology,
    "biotech": _c_biotechnology,  # alias
    "pharmaceuticals": _c_pharmaceuticals,
    "big_pharma": _c_pharmaceuticals,  # alias
    "medical_devices_equipment": _c_medical_devices_equipment,
    "medical_devices": _c_medical_devices_equipment,  # alias
    "life_sciences_tools_services": _c_life_sciences_tools_services,
    "life_sciences_tools": _c_life_sciences_tools_services,  # alias
    "healthcare_providers_services": _c_healthcare_providers_services,
    "healthcare_providers": _c_healthcare_providers_services,  # alias
    "healthcare_technology": _c_healthcare_technology,
    "healthcare_technology": _c_healthcare_technology,  # alias
    "residential_reits": _c_residential_reits,
    "residential_reits": _c_residential_reits,  # alias
    "commercial_office_reits": _c_commercial_office_reits,
    "commercial_office_reits": _c_commercial_office_reits,  # alias
    "retail_reits": _c_retail_reits,
    "retail_reits": _c_retail_reits,  # alias
    "industrial_logistics_reits": _c_industrial_logistics_reits,
    "industrial_logistics_reits": _c_industrial_logistics_reits,  # alias
    "specialized_reits": _c_specialized_reits,
    "specialized_reits": _c_specialized_reits,  # alias
    "semiconductors": _c_semiconductors,
    "semiconductors": _c_semiconductors,  # alias
    "semiconductor_equipment": _c_semiconductor_equipment,
    "semi_equipment": _c_semiconductor_equipment,  # alias
    "application_software": _c_application_software,
    "application_software": _c_application_software,  # alias
    "systems_software": _c_systems_software,
    "systems_software": _c_systems_software,  # alias
    "technology_hardware_storage_peripherals": _c_technology_hardware_storage_peripherals,
    "tech_hardware": _c_technology_hardware_storage_peripherals,  # alias
    "diversified_banks": _c_diversified_banks,
    "diversified_banks": _c_diversified_banks,  # alias
    "regional_banks": _c_regional_banks,
    "regional_banks": _c_regional_banks,  # alias
    "property_casualty_insurance": _c_property_casualty_insurance,
    "property_casualty_insurance": _c_property_casualty_insurance,  # alias
    "life_health_insurance": _c_life_health_insurance,
    "life_health_insurance": _c_life_health_insurance,  # alias
    "financial_data_capital_markets": _c_financial_data_capital_markets,
    "financial_data_exchanges": _c_financial_data_capital_markets,  # alias
    "consumer_finance": _c_consumer_finance,
    "consumer_finance": _c_consumer_finance,  # alias
    "integrated_oil_gas": _c_integrated_oil_gas,
    "integrated_oil_gas": _c_integrated_oil_gas,  # alias
    "oil_gas_exploration_production": _c_oil_gas_exploration_production,
    "oil_gas_ep": _c_oil_gas_exploration_production,  # alias
    "oil_gas_equipment_services": _c_oil_gas_equipment_services,
    "oil_gas_equipment": _c_oil_gas_equipment_services,  # alias
    "renewable_electricity_clean_energy": _c_renewable_electricity_clean_energy,
    "renewable_energy": _c_renewable_electricity_clean_energy,  # alias
    "electric_gas_utilities": _c_electric_gas_utilities,
    "electric_gas_utilities": _c_electric_gas_utilities,  # alias
    "automobile_manufacturers": _c_automobile_manufacturers,
    "auto_manufacturers": _c_automobile_manufacturers,  # alias
    "luxury_goods_apparel_accessories": _c_luxury_goods_apparel_accessories,
    "luxury_goods": _c_luxury_goods_apparel_accessories,  # alias
    "hotels_resorts_cruise_lines": _c_hotels_resorts_cruise_lines,
    "hotels_resorts_cruise": _c_hotels_resorts_cruise_lines,  # alias
    "restaurants_food_services": _c_restaurants_food_services,
    "restaurants_food": _c_restaurants_food_services,  # alias
    "hypermarkets_supercenters": _c_hypermarkets_supercenters,
    "hypermarkets_discount": _c_hypermarkets_supercenters,  # alias
    "household_personal_products": _c_household_personal_products,
    "household_personal_products": _c_household_personal_products,  # alias
    "food_products": _c_food_products,
    "packaged_foods": _c_food_products,  # alias
    "aerospace_defense": _c_aerospace_defense,
    "aerospace_defense": _c_aerospace_defense,  # alias
    "air_freight_logistics": _c_air_freight_logistics,
    "air_freight_logistics": _c_air_freight_logistics,  # alias
    "railroads": _c_railroads,
    "railroads": _c_railroads,  # alias
    "construction_machinery_heavy_trucks": _c_construction_machinery_heavy_trucks,
    "construction_machinery": _c_construction_machinery_heavy_trucks,  # alias
    "building_products_construction_materials": _c_building_products_construction_materials,
    "building_products": _c_building_products_construction_materials,  # alias
    "chemicals": _c_chemicals,
    "chemicals": _c_chemicals,  # alias
    "metals_mining": _c_metals_mining,
    "metals_mining": _c_metals_mining,  # alias
    "wireless_telecommunication_services": _c_wireless_telecommunication_services,
    "wireless_telecom": _c_wireless_telecommunication_services,  # alias
    "interactive_media_services": _c_interactive_media_services,
    "interactive_media": _c_interactive_media_services,  # alias
    "entertainment_streaming": _c_entertainment_streaming,
    "entertainment_streaming": _c_entertainment_streaming,  # alias
    "environmental_waste_management": _c_environmental_waste_management,
    "environmental_waste": _c_environmental_waste_management,  # alias
    "apparel_retail": _c_apparel_retail,
    "apparel_retail": _c_apparel_retail,  # alias
    "marine_transportation": _c_marine_transportation,
    "marine_shipping": _c_marine_transportation,  # alias
    "independent_power_producers_energy_traders": _c_independent_power_producers_energy_traders,
    "independent_power_producers": _c_independent_power_producers_energy_traders,  # alias
    "commercial_services_supplies": _c_commercial_services_supplies,
    "commercial_services": _c_commercial_services_supplies,  # alias
    "distributors": _c_distributors,
    "distributors": _c_distributors,  # alias
}



def get_category(key: str):
    """Lookup by slug (marine_transportation) or internal id (marine_shipping)."""
    from analytics.industries.categories._registry import resolve_industry_id
    k = str(key or '').strip().lower()
    if k in ALL_CATEGORIES:
        return ALL_CATEGORIES[k]
    iid = resolve_industry_id(k)
    from analytics.industries.categories._unclassified import CATEGORY as _unclassified
    return ALL_CATEGORIES.get(iid) or _unclassified


def list_category_slugs() -> list[str]:
    from analytics.industries.categories._registry import USER_CATEGORIES
    return [slug for _, slug, _, _ in USER_CATEGORIES]
