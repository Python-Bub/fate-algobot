#!/usr/bin/env python3
"""Generate company-name / sector lexicon for industry classification fallback."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "name_lexicon.py"

_spec_path = Path(__file__).resolve().parent / "_generate_industry_handlers.py"
_spec = importlib.util.spec_from_file_location("ind_gen", _spec_path)
_mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)
MASTER = _mod.MASTER

SECTOR_DEFAULTS: dict[str, str] = {
    "technology": "application_software",
    "healthcare": "healthcare_providers",
    "financial services": "diversified_banks",
    "financial": "diversified_banks",
    "energy": "oil_gas_ep",
    "utilities": "electric_gas_utilities",
    "consumer cyclical": "apparel_retail",
    "consumer defensive": "packaged_foods",
    "industrials": "commercial_services",
    "basic materials": "metals_mining",
    "communication services": "interactive_media",
    "real estate": "specialized_reits",
}

SYMBOL_SUFFIX: dict[str, str] = {
    "BIO": "biotech",
    "PHM": "big_pharma",
    "RX": "big_pharma",
    "BANK": "regional_banks",
    "REIT": "specialized_reits",
    "OIL": "oil_gas_ep",
    "GAS": "oil_gas_ep",
    "TECH": "application_software",
    "SOFT": "application_software",
    "CHIP": "semiconductors",
    "SEMI": "semiconductors",
    "AIR": "aerospace_defense",
    "SHIP": "marine_shipping",
    "RAIL": "railroads",
    "MIN": "metals_mining",
    "GOLD": "metals_mining",
    "SILV": "metals_mining",
    "COAL": "metals_mining",
    "SOLAR": "renewable_energy",
    "WIND": "renewable_energy",
    "HOTEL": "hotels_resorts_cruise",
    "FOOD": "packaged_foods",
    "REST": "restaurants_food",
    "INS": "life_health_insurance",
    "INSU": "property_casualty_insurance",
    "MED": "medical_devices",
    "HOSP": "healthcare_providers",
    "LAB": "life_sciences_tools",
    "DRUG": "big_pharma",
    "PHAR": "big_pharma",
    "GENE": "biotech",
    "CELL": "biotech",
    "DATA": "financial_data_exchanges",
    "PAY": "consumer_finance",
    "FIN": "consumer_finance",
    "MORT": "residential_reits",
    "APT": "residential_reits",
    "LOG": "air_freight_logistics",
    "TRUK": "air_freight_logistics",
    "AUTO": "auto_manufacturers",
    "EV": "auto_manufacturers",
    "UTIL": "electric_gas_utilities",
    "PWR": "independent_power_producers",
    "WASTE": "environmental_waste",
    "WAST": "environmental_waste",
    "CHEM": "chemicals",
    "STEEL": "metals_mining",
    "COPPER": "metals_mining",
    "LITH": "metals_mining",
    "LITHIUM": "metals_mining",
    "URAN": "metals_mining",
    "NUCL": "independent_power_producers",
    "GAME": "interactive_media",
    "MEDIA": "entertainment_streaming",
    "STREAM": "entertainment_streaming",
    "TELE": "wireless_telecom",
    "TEL": "wireless_telecom",
    "FIBER": "wireless_telecom",
    "5G": "wireless_telecom",
    "CLOUD": "application_software",
    "SAAS": "application_software",
    "AI": "application_software",
    "ML": "application_software",
    "CYBR": "systems_software",
    "SEC": "systems_software",
    "DEF": "aerospace_defense",
    "ARM": "aerospace_defense",
    "SPACE": "aerospace_defense",
    "SAT": "wireless_telecom",
    "CRUISE": "hotels_resorts_cruise",
    "RESORT": "hotels_resorts_cruise",
    "LUX": "luxury_goods",
    "JEWEL": "luxury_goods",
    "APP": "apparel_retail",
    "WEAR": "apparel_retail",
    "SHOE": "apparel_retail",
    "FOOT": "apparel_retail",
    "MALL": "retail_reits",
    "SHOP": "retail_reits",
    "WARE": "industrial_logistics_reits",
    "STOR": "industrial_logistics_reits",
    "DIST": "distributors",
    "WHOLE": "distributors",
    "PACK": "packaged_foods",
    "SNACK": "packaged_foods",
    "BEV": "packaged_foods",
    "BREW": "packaged_foods",
    "COFF": "restaurants_food",
    "PIZZ": "restaurants_food",
    "BURG": "restaurants_food",
    "CAFE": "restaurants_food",
    "DINE": "restaurants_food",
    "EDU": "commercial_services",
    "STAFF": "commercial_services",
    "SERV": "commercial_services",
    "CONS": "commercial_services",
    "AD": "interactive_media",
    "ADS": "interactive_media",
    "NET": "interactive_media",
    "WEB": "interactive_media",
    "SOCIAL": "interactive_media",
    "META": "interactive_media",
    "VID": "entertainment_streaming",
    "FILM": "entertainment_streaming",
    "STUDIO": "entertainment_streaming",
    "MUSIC": "entertainment_streaming",
    "EQUIP": "construction_machinery",
    "MACH": "construction_machinery",
    "CAT": "construction_machinery",
    "DOZ": "construction_machinery",
    "BLDG": "building_products",
    "ROOF": "building_products",
    "HVAC": "building_products",
    "PIPE": "building_products",
    "PLUMB": "building_products",
    "LUMBER": "building_products",
    "TIMBER": "building_products",
    "FARM": "packaged_foods",
    "AGRI": "packaged_foods",
    "CROP": "packaged_foods",
    "SEED": "packaged_foods",
    "FERT": "chemicals",
    "PEST": "chemicals",
    "POLY": "chemicals",
    "PLAST": "chemicals",
    "RESIN": "chemicals",
    "PAINT": "chemicals",
    "COAT": "chemicals",
    "ADH": "chemicals",
    "REFIN": "integrated_oil_gas",
    "PIPELINE": "integrated_oil_gas",
    "MIDSTREAM": "integrated_oil_gas",
    "DRILL": "oil_gas_equipment",
    "RIG": "oil_gas_equipment",
    "FRAC": "oil_gas_equipment",
    "SHALE": "oil_gas_ep",
    "LNG": "integrated_oil_gas",
    "PROP": "oil_gas_ep",
    "EXPL": "oil_gas_ep",
    "EXCHANGE": "financial_data_exchanges",
    "BROKER": "financial_data_exchanges",
    "TRADE": "financial_data_exchanges",
    "CLEAR": "financial_data_exchanges",
    "CARD": "consumer_finance",
    "LEND": "consumer_finance",
    "LOAN": "consumer_finance",
    "CRED": "consumer_finance",
    "MORTG": "consumer_finance",
    "LEASE": "consumer_finance",
    "RENT": "residential_reits",
    "APTMT": "residential_reits",
    "MULTI": "residential_reits",
    "OFFICE": "commercial_office_reits",
    "TOWER": "commercial_office_reits",
    "INDUSTRIAL": "industrial_logistics_reits",
    "DC": "specialized_reits",
    "DATAC": "specialized_reits",
    "HEALTH": "healthcare_providers",
    "CLINIC": "healthcare_providers",
    "NURS": "healthcare_providers",
    "DIAL": "healthcare_providers",
    "THERA": "biotech",
    "ONCO": "biotech",
    "IMMUN": "biotech",
    "VACC": "biotech",
    "MRNA": "biotech",
    "RNA": "biotech",
    "DNA": "biotech",
    "GENOM": "biotech",
    "PROTE": "biotech",
    "ANTIB": "big_pharma",
    "VAX": "big_pharma",
    "DIAG": "life_sciences_tools",
    "ASSAY": "life_sciences_tools",
    "REAG": "life_sciences_tools",
    "SCOPE": "medical_devices",
    "IMPL": "medical_devices",
    "ORTHO": "medical_devices",
    "CARDIO": "medical_devices",
    "DIAB": "medical_devices",
    "PUMP": "medical_devices",
    "ROBOT": "medical_devices",
    "SURG": "medical_devices",
    "EHR": "healthcare_technology",
    "TELEHEALTH": "healthcare_technology",
    "PHARM": "big_pharma",
    "RXCO": "big_pharma",
    "GENERIC": "big_pharma",
    "BIOSIM": "big_pharma",
}


def _name_rules(spec: dict) -> list[tuple[str, float]]:
    rules: list[tuple[str, float]] = []
    for pat in spec.get("patterns") or []:
        rules.append((pat, 0.72))
    for pat in spec.get("commodities") or []:
        rules.append((pat, 0.65))
    for pat in (spec.get("bull") or [])[:6]:
        rules.append((pat, 0.58))
    for pat in (spec.get("bear") or [])[:4]:
        rules.append((pat, 0.55))
    name_bits = spec["name"].lower().split()
    for w in name_bits:
        if len(w) > 4:
            rules.append((w, 0.6))
    return rules


def generate() -> None:
    lines: list[str] = [
        '"""Auto-generated name/sector/suffix lexicon for industry classification."""',
        "",
        "from __future__ import annotations",
        "",
        "from analytics.industries.base import ClassificationResult",
        "from analytics.industries.registry import get_handler",
        "",
        "SECTOR_DEFAULTS: dict[str, str] = {",
    ]
    for k, v in SECTOR_DEFAULTS.items():
        lines.append(f"    {k!r}: {v!r},")
    lines.append("}")
    lines.append("")
    lines.append("SYMBOL_SUFFIX: dict[str, str] = {")
    for k, v in SYMBOL_SUFFIX.items():
        lines.append(f"    {k!r}: {v!r},")
    lines.append("}")
    lines.append("")
    lines.append("NAME_RULES: dict[str, list[tuple[str, float]]] = {")
    for spec in MASTER:
        rules = _name_rules(spec)
        lines.append(f'    "{spec["id"]}": [')
        for pat, conf in rules:
            lines.append(f"        ({pat!r}, {conf}),")
        lines.append("    ],")
    lines.append("}")
    lines.extend(
        [
            "",
            "",
            "def _result(iid: str, confidence: float, reason: str) -> ClassificationResult:",
            "    handler = get_handler(iid)",
            "    return ClassificationResult(",
            "        industry_id=iid,",
            "        industry_name=handler.INDUSTRY_NAME,",
            "        confidence=confidence,",
            "        etf_proxy=handler.ETF_PROXY,",
            "        comovement_mode=handler.COMOVEMENT_MODE.value,",
            "        reasons=[reason],",
            "    )",
            "",
            "",
            "def match_name_lexicon(",
            "    company_name: str,",
            "    sector: str = \"\",",
            "    yahoo_industry: str = \"\",",
            ") -> ClassificationResult | None:",
            "    blob = f\"{company_name} {sector} {yahoo_industry}\".lower()",
            "    if not blob.strip():",
            "        return None",
            "    best: ClassificationResult | None = None",
            "    for iid, rules in NAME_RULES.items():",
            "        for pat, conf in rules:",
            "            if pat in blob:",
            "                hit = _result(iid, conf, f\"name_lex:{pat[:24]}\")",
            "                if best is None or hit.confidence > best.confidence:",
            "                    best = hit",
            "    sec = sector.lower().strip()",
            "    if best is None and sec in SECTOR_DEFAULTS:",
            "        return _result(SECTOR_DEFAULTS[sec], 0.52, f\"sector_default:{sec}\")",
            "    return best",
            "",
            "",
            "def suffix_industry(symbol: str) -> str | None:",
            "    sym = symbol.strip().upper()",
            "    for suffix, iid in sorted(SYMBOL_SUFFIX.items(), key=lambda x: -len(x[0])):",
            "        if sym.endswith(suffix):",
            "            return iid",
            "    return None",
            "",
        ]
    )
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(lines)} lines)")


if __name__ == "__main__":
    generate()
