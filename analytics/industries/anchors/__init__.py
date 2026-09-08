"""Auto-generated industry anchor registry (50 buckets)."""

from analytics.industries.anchors.biotech import ANCHOR as _a_biotech
from analytics.industries.anchors.big_pharma import ANCHOR as _a_big_pharma
from analytics.industries.anchors.medical_devices import ANCHOR as _a_medical_devices
from analytics.industries.anchors.life_sciences_tools import ANCHOR as _a_life_sciences_tools
from analytics.industries.anchors.healthcare_providers import ANCHOR as _a_healthcare_providers
from analytics.industries.anchors.healthcare_technology import ANCHOR as _a_healthcare_technology
from analytics.industries.anchors.residential_reits import ANCHOR as _a_residential_reits
from analytics.industries.anchors.commercial_office_reits import ANCHOR as _a_commercial_office_reits
from analytics.industries.anchors.retail_reits import ANCHOR as _a_retail_reits
from analytics.industries.anchors.industrial_logistics_reits import ANCHOR as _a_industrial_logistics_reits
from analytics.industries.anchors.specialized_reits import ANCHOR as _a_specialized_reits
from analytics.industries.anchors.semiconductors import ANCHOR as _a_semiconductors
from analytics.industries.anchors.semi_equipment import ANCHOR as _a_semi_equipment
from analytics.industries.anchors.application_software import ANCHOR as _a_application_software
from analytics.industries.anchors.systems_software import ANCHOR as _a_systems_software
from analytics.industries.anchors.tech_hardware import ANCHOR as _a_tech_hardware
from analytics.industries.anchors.diversified_banks import ANCHOR as _a_diversified_banks
from analytics.industries.anchors.regional_banks import ANCHOR as _a_regional_banks
from analytics.industries.anchors.property_casualty_insurance import ANCHOR as _a_property_casualty_insurance
from analytics.industries.anchors.life_health_insurance import ANCHOR as _a_life_health_insurance
from analytics.industries.anchors.financial_data_exchanges import ANCHOR as _a_financial_data_exchanges
from analytics.industries.anchors.consumer_finance import ANCHOR as _a_consumer_finance
from analytics.industries.anchors.integrated_oil_gas import ANCHOR as _a_integrated_oil_gas
from analytics.industries.anchors.oil_gas_ep import ANCHOR as _a_oil_gas_ep
from analytics.industries.anchors.oil_gas_equipment import ANCHOR as _a_oil_gas_equipment
from analytics.industries.anchors.renewable_energy import ANCHOR as _a_renewable_energy
from analytics.industries.anchors.electric_gas_utilities import ANCHOR as _a_electric_gas_utilities
from analytics.industries.anchors.auto_manufacturers import ANCHOR as _a_auto_manufacturers
from analytics.industries.anchors.luxury_goods import ANCHOR as _a_luxury_goods
from analytics.industries.anchors.hotels_resorts_cruise import ANCHOR as _a_hotels_resorts_cruise
from analytics.industries.anchors.restaurants_food import ANCHOR as _a_restaurants_food
from analytics.industries.anchors.hypermarkets_discount import ANCHOR as _a_hypermarkets_discount
from analytics.industries.anchors.household_personal_products import ANCHOR as _a_household_personal_products
from analytics.industries.anchors.packaged_foods import ANCHOR as _a_packaged_foods
from analytics.industries.anchors.aerospace_defense import ANCHOR as _a_aerospace_defense
from analytics.industries.anchors.air_freight_logistics import ANCHOR as _a_air_freight_logistics
from analytics.industries.anchors.railroads import ANCHOR as _a_railroads
from analytics.industries.anchors.construction_machinery import ANCHOR as _a_construction_machinery
from analytics.industries.anchors.building_products import ANCHOR as _a_building_products
from analytics.industries.anchors.chemicals import ANCHOR as _a_chemicals
from analytics.industries.anchors.metals_mining import ANCHOR as _a_metals_mining
from analytics.industries.anchors.wireless_telecom import ANCHOR as _a_wireless_telecom
from analytics.industries.anchors.interactive_media import ANCHOR as _a_interactive_media
from analytics.industries.anchors.entertainment_streaming import ANCHOR as _a_entertainment_streaming
from analytics.industries.anchors.environmental_waste import ANCHOR as _a_environmental_waste
from analytics.industries.anchors.apparel_retail import ANCHOR as _a_apparel_retail
from analytics.industries.anchors.marine_shipping import ANCHOR as _a_marine_shipping
from analytics.industries.anchors.independent_power_producers import ANCHOR as _a_independent_power_producers
from analytics.industries.anchors.commercial_services import ANCHOR as _a_commercial_services
from analytics.industries.anchors.distributors import ANCHOR as _a_distributors

from analytics.industries.anchors._unclassified import ANCHOR as _a_unclassified


ALL_ANCHORS = {
    "biotech": _a_biotech,
    "big_pharma": _a_big_pharma,
    "medical_devices": _a_medical_devices,
    "life_sciences_tools": _a_life_sciences_tools,
    "healthcare_providers": _a_healthcare_providers,
    "healthcare_technology": _a_healthcare_technology,
    "residential_reits": _a_residential_reits,
    "commercial_office_reits": _a_commercial_office_reits,
    "retail_reits": _a_retail_reits,
    "industrial_logistics_reits": _a_industrial_logistics_reits,
    "specialized_reits": _a_specialized_reits,
    "semiconductors": _a_semiconductors,
    "semi_equipment": _a_semi_equipment,
    "application_software": _a_application_software,
    "systems_software": _a_systems_software,
    "tech_hardware": _a_tech_hardware,
    "diversified_banks": _a_diversified_banks,
    "regional_banks": _a_regional_banks,
    "property_casualty_insurance": _a_property_casualty_insurance,
    "life_health_insurance": _a_life_health_insurance,
    "financial_data_exchanges": _a_financial_data_exchanges,
    "consumer_finance": _a_consumer_finance,
    "integrated_oil_gas": _a_integrated_oil_gas,
    "oil_gas_ep": _a_oil_gas_ep,
    "oil_gas_equipment": _a_oil_gas_equipment,
    "renewable_energy": _a_renewable_energy,
    "electric_gas_utilities": _a_electric_gas_utilities,
    "auto_manufacturers": _a_auto_manufacturers,
    "luxury_goods": _a_luxury_goods,
    "hotels_resorts_cruise": _a_hotels_resorts_cruise,
    "restaurants_food": _a_restaurants_food,
    "hypermarkets_discount": _a_hypermarkets_discount,
    "household_personal_products": _a_household_personal_products,
    "packaged_foods": _a_packaged_foods,
    "aerospace_defense": _a_aerospace_defense,
    "air_freight_logistics": _a_air_freight_logistics,
    "railroads": _a_railroads,
    "construction_machinery": _a_construction_machinery,
    "building_products": _a_building_products,
    "chemicals": _a_chemicals,
    "metals_mining": _a_metals_mining,
    "wireless_telecom": _a_wireless_telecom,
    "interactive_media": _a_interactive_media,
    "entertainment_streaming": _a_entertainment_streaming,
    "environmental_waste": _a_environmental_waste,
    "apparel_retail": _a_apparel_retail,
    "marine_shipping": _a_marine_shipping,
    "independent_power_producers": _a_independent_power_producers,
    "commercial_services": _a_commercial_services,
    "distributors": _a_distributors,
    "unclassified": _a_unclassified,
}


def get_anchor(industry_id: str):
    return ALL_ANCHORS.get(str(industry_id or "unclassified"), _a_unclassified)


def anchor_for_symbol(symbol: str):
    from analytics.industries.integration import get_industry_profile
    prof = get_industry_profile(symbol.strip().upper())
    return get_anchor(prof.get("primary_industry_id") or "unclassified")
