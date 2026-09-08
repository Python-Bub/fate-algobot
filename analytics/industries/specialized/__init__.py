"""Auto-generated specialized industry pipeline registry."""

from analytics.industries.specialized.biotech import LOGIC as _s_biotech
from analytics.industries.specialized.big_pharma import LOGIC as _s_big_pharma
from analytics.industries.specialized.medical_devices import LOGIC as _s_medical_devices
from analytics.industries.specialized.life_sciences_tools import LOGIC as _s_life_sciences_tools
from analytics.industries.specialized.healthcare_providers import LOGIC as _s_healthcare_providers
from analytics.industries.specialized.healthcare_technology import LOGIC as _s_healthcare_technology
from analytics.industries.specialized.residential_reits import LOGIC as _s_residential_reits
from analytics.industries.specialized.commercial_office_reits import LOGIC as _s_commercial_office_reits
from analytics.industries.specialized.retail_reits import LOGIC as _s_retail_reits
from analytics.industries.specialized.industrial_logistics_reits import LOGIC as _s_industrial_logistics_reits
from analytics.industries.specialized.specialized_reits import LOGIC as _s_specialized_reits
from analytics.industries.specialized.semiconductors import LOGIC as _s_semiconductors
from analytics.industries.specialized.semi_equipment import LOGIC as _s_semi_equipment
from analytics.industries.specialized.application_software import LOGIC as _s_application_software
from analytics.industries.specialized.systems_software import LOGIC as _s_systems_software
from analytics.industries.specialized.tech_hardware import LOGIC as _s_tech_hardware
from analytics.industries.specialized.diversified_banks import LOGIC as _s_diversified_banks
from analytics.industries.specialized.regional_banks import LOGIC as _s_regional_banks
from analytics.industries.specialized.property_casualty_insurance import LOGIC as _s_property_casualty_insurance
from analytics.industries.specialized.life_health_insurance import LOGIC as _s_life_health_insurance
from analytics.industries.specialized.financial_data_exchanges import LOGIC as _s_financial_data_exchanges
from analytics.industries.specialized.consumer_finance import LOGIC as _s_consumer_finance
from analytics.industries.specialized.integrated_oil_gas import LOGIC as _s_integrated_oil_gas
from analytics.industries.specialized.oil_gas_ep import LOGIC as _s_oil_gas_ep
from analytics.industries.specialized.oil_gas_equipment import LOGIC as _s_oil_gas_equipment
from analytics.industries.specialized.renewable_energy import LOGIC as _s_renewable_energy
from analytics.industries.specialized.electric_gas_utilities import LOGIC as _s_electric_gas_utilities
from analytics.industries.specialized.auto_manufacturers import LOGIC as _s_auto_manufacturers
from analytics.industries.specialized.luxury_goods import LOGIC as _s_luxury_goods
from analytics.industries.specialized.hotels_resorts_cruise import LOGIC as _s_hotels_resorts_cruise
from analytics.industries.specialized.restaurants_food import LOGIC as _s_restaurants_food
from analytics.industries.specialized.hypermarkets_discount import LOGIC as _s_hypermarkets_discount
from analytics.industries.specialized.household_personal_products import LOGIC as _s_household_personal_products
from analytics.industries.specialized.packaged_foods import LOGIC as _s_packaged_foods
from analytics.industries.specialized.aerospace_defense import LOGIC as _s_aerospace_defense
from analytics.industries.specialized.air_freight_logistics import LOGIC as _s_air_freight_logistics
from analytics.industries.specialized.railroads import LOGIC as _s_railroads
from analytics.industries.specialized.construction_machinery import LOGIC as _s_construction_machinery
from analytics.industries.specialized.building_products import LOGIC as _s_building_products
from analytics.industries.specialized.chemicals import LOGIC as _s_chemicals
from analytics.industries.specialized.metals_mining import LOGIC as _s_metals_mining
from analytics.industries.specialized.wireless_telecom import LOGIC as _s_wireless_telecom
from analytics.industries.specialized.interactive_media import LOGIC as _s_interactive_media
from analytics.industries.specialized.entertainment_streaming import LOGIC as _s_entertainment_streaming
from analytics.industries.specialized.environmental_waste import LOGIC as _s_environmental_waste
from analytics.industries.specialized.apparel_retail import LOGIC as _s_apparel_retail
from analytics.industries.specialized.marine_shipping import LOGIC as _s_marine_shipping
from analytics.industries.specialized.independent_power_producers import LOGIC as _s_independent_power_producers
from analytics.industries.specialized.commercial_services import LOGIC as _s_commercial_services
from analytics.industries.specialized.distributors import LOGIC as _s_distributors

from analytics.industries.specialized.unclassified import LOGIC as _s_unclassified


ALL_SPECIALIZED = {
    "biotech": _s_biotech,
    "big_pharma": _s_big_pharma,
    "medical_devices": _s_medical_devices,
    "life_sciences_tools": _s_life_sciences_tools,
    "healthcare_providers": _s_healthcare_providers,
    "healthcare_technology": _s_healthcare_technology,
    "residential_reits": _s_residential_reits,
    "commercial_office_reits": _s_commercial_office_reits,
    "retail_reits": _s_retail_reits,
    "industrial_logistics_reits": _s_industrial_logistics_reits,
    "specialized_reits": _s_specialized_reits,
    "semiconductors": _s_semiconductors,
    "semi_equipment": _s_semi_equipment,
    "application_software": _s_application_software,
    "systems_software": _s_systems_software,
    "tech_hardware": _s_tech_hardware,
    "diversified_banks": _s_diversified_banks,
    "regional_banks": _s_regional_banks,
    "property_casualty_insurance": _s_property_casualty_insurance,
    "life_health_insurance": _s_life_health_insurance,
    "financial_data_exchanges": _s_financial_data_exchanges,
    "consumer_finance": _s_consumer_finance,
    "integrated_oil_gas": _s_integrated_oil_gas,
    "oil_gas_ep": _s_oil_gas_ep,
    "oil_gas_equipment": _s_oil_gas_equipment,
    "renewable_energy": _s_renewable_energy,
    "electric_gas_utilities": _s_electric_gas_utilities,
    "auto_manufacturers": _s_auto_manufacturers,
    "luxury_goods": _s_luxury_goods,
    "hotels_resorts_cruise": _s_hotels_resorts_cruise,
    "restaurants_food": _s_restaurants_food,
    "hypermarkets_discount": _s_hypermarkets_discount,
    "household_personal_products": _s_household_personal_products,
    "packaged_foods": _s_packaged_foods,
    "aerospace_defense": _s_aerospace_defense,
    "air_freight_logistics": _s_air_freight_logistics,
    "railroads": _s_railroads,
    "construction_machinery": _s_construction_machinery,
    "building_products": _s_building_products,
    "chemicals": _s_chemicals,
    "metals_mining": _s_metals_mining,
    "wireless_telecom": _s_wireless_telecom,
    "interactive_media": _s_interactive_media,
    "entertainment_streaming": _s_entertainment_streaming,
    "environmental_waste": _s_environmental_waste,
    "apparel_retail": _s_apparel_retail,
    "marine_shipping": _s_marine_shipping,
    "independent_power_producers": _s_independent_power_producers,
    "commercial_services": _s_commercial_services,
    "distributors": _s_distributors,
    "unclassified": _s_unclassified,
}


def get_specialized(industry_id: str):
    return ALL_SPECIALIZED.get(str(industry_id or "unclassified"), _s_unclassified)
