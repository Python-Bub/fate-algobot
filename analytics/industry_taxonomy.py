"""50-industry taxonomy, symbol classification, and factor sensitivities."""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TAXONOMY_PATH = ROOT / "data" / "industry" / "taxonomy.json"
OVERRIDES_PATH = ROOT / "data" / "industry" / "symbol_overrides.json"
MAP_PATH = ROOT / "data" / "industry" / "industry_map.json"

# Nasdaq / growth-heavy industries (move with QQQ)
NASDAQ_HEAVY = frozenset(
    {
        "biotech",
        "semiconductors",
        "semi_equipment",
        "application_software",
        "systems_software",
        "tech_hardware",
        "healthcare_technology",
        "interactive_media",
        "life_sciences_tools",
        "specialized_reits",
    }
)

# Rate-sensitive (inverse to 10y yield)
RATE_SENSITIVE = frozenset(
    {
        "residential_reits",
        "commercial_office_reits",
        "retail_reits",
        "industrial_logistics_reits",
        "specialized_reits",
        "electric_gas_utilities",
        "wireless_telecom",
        "renewable_energy",
        "life_health_insurance",
    }
)

# Early-cycle expansion beneficiaries (PMI > 52)
EXPANSION_CYCLICAL = frozenset(
    {
        "semiconductors",
        "semi_equipment",
        "railroads",
        "chemicals",
        "construction_machinery",
        "building_products",
        "metals_mining",
        "oil_gas_ep",
        "oil_gas_equipment",
        "air_freight_logistics",
        "industrial_logistics_reits",
    }
)

DEFAULT_INDUSTRY = "unclassified"


def _catalog() -> dict[str, dict[str, Any]]:
    """Built-in 50-industry definitions (etf proxy, Yahoo patterns, factor tags)."""
    rows: list[tuple[str, str, str, str, float, float, float]] = [
        ("biotech", "Biotechnology", "IBB", "biotech|biological", -0.1, 0.3, 1.1),
        ("big_pharma", "Big Pharma", "XPH", "drug manufacturer|pharmaceutical", 0.0, 0.2, 0.6),
        ("medical_devices", "Medical Devices", "IHI", "medical device|medical instruments", 0.0, 0.5, 0.8),
        ("life_sciences_tools", "Life Sciences Tools", "XLV", "diagnostics|research", 0.1, 0.8, 1.0),
        ("healthcare_providers", "Healthcare Providers", "XLV", "health care plans|hospitals|healthcare providers", -0.2, 0.2, 0.5),
        ("healthcare_technology", "Healthcare Technology", "XLV", "health information|healthcare technology", 0.2, 0.9, 1.2),
        ("residential_reits", "Residential REITs", "REZ", "residential reit|reit—residential", -0.7, 0.4, 0.4),
        ("commercial_office_reits", "Commercial Office REITs", "VNQ", "office reit|reit—office", -0.65, 0.5, 0.5),
        ("retail_reits", "Retail REITs", "VNQ", "retail reit|reit—retail", -0.6, 0.4, 0.5),
        ("industrial_logistics_reits", "Industrial & Logistics REITs", "IYR", "industrial reit|reit—industrial|warehouse", -0.55, 0.7, 0.6),
        ("specialized_reits", "Specialized REITs", "XLRE", "data center|cell tower|reit—specialty|reit—diversified", -0.5, 0.8, 1.0),
        ("semiconductors", "Semiconductors", "SMH", "semiconductor", 0.0, 1.2, 1.5),
        ("semi_equipment", "Semiconductor Equipment", "SMH", "semiconductor equipment|wafer", 0.0, 1.3, 1.4),
        ("application_software", "Application Software", "IGV", "software—application|software application", 0.2, 1.0, 1.3),
        ("systems_software", "Systems Software", "IGV", "software—infra|cyber|security software", 0.2, 0.9, 1.2),
        ("tech_hardware", "Technology Hardware", "XLK", "computer hardware|consumer electronics|electronic", 0.1, 0.9, 1.2),
        ("diversified_banks", "Diversified Banks", "KBE", "banks—diversified|diversified banks", 0.4, 0.8, 0.9),
        ("regional_banks", "Regional Banks", "KRE", "banks—regional|regional banks", 0.5, 0.7, 0.8),
        ("property_casualty_insurance", "Property & Casualty Insurance", "KIE", "insurance—property|property & casualty", 0.1, 0.3, 0.5),
        ("life_health_insurance", "Life & Health Insurance", "KIE", "insurance—life|insurance—diversified", -0.4, 0.2, 0.5),
        ("financial_data_exchanges", "Financial Data & Exchanges", "XLF", "financial data|capital markets|asset management", 0.3, 0.9, 1.0),
        ("consumer_finance", "Consumer Finance", "XLF", "credit services|consumer finance", 0.3, 0.8, 1.0),
        ("integrated_oil_gas", "Integrated Oil & Gas", "XLE", "oil & gas integrated|integrated oil", 0.2, 0.6, 0.7),
        ("oil_gas_ep", "Oil & Gas E&P", "XOP", "oil & gas e&p|exploration", 0.1, 0.9, 0.8),
        ("oil_gas_equipment", "Oil & Gas Equipment", "XES", "oil & gas equipment|oilfield", 0.0, 0.8, 0.8),
        ("renewable_energy", "Renewable Energy", "ICLN", "solar|renewable|clean energy", -0.5, 0.7, 1.0),
        ("electric_gas_utilities", "Electric & Gas Utilities", "XLU", "utilities—|electric utilities|gas utilities", -0.6, 0.2, 0.3),
        ("auto_manufacturers", "Auto Manufacturers", "CARZ", "auto manufacturers|automobile", 0.0, 0.9, 1.0),
        ("luxury_goods", "Luxury Goods", "XLY", "luxury|apparel—luxury", 0.0, 0.6, 1.0),
        ("hotels_resorts_cruise", "Hotels & Cruise", "XLY", "resorts|hotels| cruise|leisure", 0.0, 0.9, 1.0),
        ("restaurants_food", "Restaurants", "XLY", "restaurants|food service", 0.0, 0.5, 0.8),
        ("hypermarkets_discount", "Hypermarkets & Discount", "XRT", "discount stores|department stores|grocery", 0.0, 0.3, 0.6),
        ("household_personal_products", "Household Products", "XLP", "household|personal products|packaged soap", 0.0, 0.1, 0.4),
        ("packaged_foods", "Packaged Foods", "XLP", "packaged foods|food products|confectioners", 0.0, 0.1, 0.4),
        ("aerospace_defense", "Aerospace & Defense", "ITA", "aerospace|defense|aircraft", 0.0, 0.5, 0.7),
        ("air_freight_logistics", "Air Freight & Logistics", "IYT", "integrated freight|logistics|courier", 0.0, 0.9, 0.9),
        ("railroads", "Railroads", "IYT", "railroads", 0.1, 1.0, 0.8),
        ("construction_machinery", "Construction Machinery", "XLI", "farm & construction|construction machinery|heavy machinery", 0.0, 1.0, 0.9),
        ("building_products", "Building Products", "XLI", "building products|building materials| lumber", 0.0, 1.0, 0.9),
        ("chemicals", "Chemicals", "XLB", "chemicals|specialty chemicals|agricultural inputs", 0.0, 1.0, 0.8),
        ("metals_mining", "Metals & Mining", "XME", "gold|silver|copper|steel|aluminum|mining", 0.0, 1.1, 0.8),
        ("wireless_telecom", "Wireless Telecom", "XLC", "telecom services|wireless", -0.5, 0.3, 0.5),
        ("interactive_media", "Interactive Media", "XLC", "internet content|interactive media|search|social", 0.2, 1.0, 1.4),
        ("entertainment_streaming", "Entertainment & Streaming", "XLC", "entertainment|broadcasting|media—", 0.0, 0.7, 1.1),
        ("environmental_waste", "Environmental & Waste", "XLI", "waste management|environmental", 0.0, 0.3, 0.5),
        ("apparel_retail", "Apparel Retail", "XRT", "apparel retail|specialty retail|footwear", 0.0, 0.6, 0.9),
        ("marine_shipping", "Marine Shipping", "BDRY", "marine shipping|shipping", 0.0, 0.8, 0.6),
        ("independent_power_producers", "Independent Power Producers", "XLU", "independent power|power producers", 0.0, 0.7, 0.7),
        ("commercial_services", "Commercial Services", "XLI", "specialty business services|staffing|security", 0.0, 0.5, 0.7),
        ("distributors", "Distributors", "XLI", "distribution|wholesale|industrial distribution", 0.0, 0.6, 0.7),
    ]
    out: dict[str, dict[str, Any]] = {}
    for iid, name, etf, patterns, rate_s, exp_b, ndx_b in rows:
        out[iid] = {
            "id": iid,
            "name": name,
            "etf_proxy": etf,
            "yahoo_patterns": [p.strip() for p in patterns.split("|") if p.strip()],
            "rate_sensitivity": rate_s,
            "expansion_beta": exp_b,
            "nasdaq_beta": ndx_b,
            "intra_corr_prior": 0.85 if iid in ("biotech", "semiconductors", "metals_mining") else 0.75,
        }
    out[DEFAULT_INDUSTRY] = {
        "id": DEFAULT_INDUSTRY,
        "name": "Unclassified",
        "etf_proxy": "SPY",
        "yahoo_patterns": [],
        "rate_sensitivity": 0.0,
        "expansion_beta": 0.5,
        "nasdaq_beta": 1.0,
        "intra_corr_prior": 0.5,
    }
    return out


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, dict[str, Any]]:
    if TAXONOMY_PATH.is_file():
        try:
            doc = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
            items = doc.get("industries") or doc
            if isinstance(items, dict) and items:
                return items
        except Exception:
            pass
    return _catalog()


@lru_cache(maxsize=1)
def load_overrides() -> dict[str, str]:
    if not OVERRIDES_PATH.is_file():
        return {}
    try:
        doc = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        syms = doc.get("symbols") or doc
        return {str(k).upper(): str(v) for k, v in syms.items()}
    except Exception:
        return {}


def load_industry_map() -> dict[str, dict[str, Any]]:
    if not MAP_PATH.is_file():
        return {}
    try:
        doc = json.loads(MAP_PATH.read_text(encoding="utf-8"))
        return {str(k).upper(): v for k, v in (doc.get("symbols") or doc).items() if isinstance(v, dict)}
    except Exception:
        return {}


def _match_yahoo_industry(sector: str, industry: str) -> str:
    blob = f"{sector} {industry}".lower()
    catalog = load_catalog()
    best_id = DEFAULT_INDUSTRY
    best_len = 0
    for iid, meta in catalog.items():
        if iid == DEFAULT_INDUSTRY:
            continue
        for pat in meta.get("yahoo_patterns") or []:
            if pat in blob and len(pat) > best_len:
                best_len = len(pat)
                best_id = iid
    return best_id


def classify_symbol(
    symbol: str,
    *,
    sector: str = "",
    industry: str = "",
    use_yfinance: bool = True,
) -> dict[str, Any]:
    """Return industry metadata for a ticker."""
    sym = symbol.strip().upper()
    catalog = load_catalog()
    overrides = load_overrides()
    cached = load_industry_map().get(sym)

    iid = overrides.get(sym)
    sec = sector or (cached or {}).get("sector") or ""
    ind = industry or (cached or {}).get("yahoo_industry") or ""

    if not iid and cached:
        cached_iid = str((cached or {}).get("industry_id") or "")
        if cached_iid and cached_iid != DEFAULT_INDUSTRY:
            iid = cached_iid
            if not sec:
                sec = str((cached or {}).get("sector") or "")
            if not ind:
                ind = str((cached or {}).get("yahoo_industry") or "")

    if use_yfinance and (not sec and not ind) and not (sector or industry):
        try:
            import yfinance as yf

            info = yf.Ticker(sym).info or {}
            sec = str(info.get("sector") or sec or "")
            ind = str(info.get("industry") or ind or "")
        except Exception:
            pass

    if sector or industry:
        sec = sector or sec
        ind = industry or ind

    if not iid or iid == DEFAULT_INDUSTRY or (sector or industry):
        matched = _match_yahoo_industry(sec, ind)
        if matched != DEFAULT_INDUSTRY or not iid:
            iid = matched

    meta = dict(catalog.get(iid) or catalog[DEFAULT_INDUSTRY])
    meta["industry_id"] = iid
    meta["symbol"] = sym
    meta["sector"] = sec
    meta["yahoo_industry"] = ind
    meta["nasdaq_heavy"] = iid in NASDAQ_HEAVY
    meta["rate_sensitive"] = iid in RATE_SENSITIVE
    meta["expansion_cyclical"] = iid in EXPANSION_CYCLICAL
    return meta


def industry_etf(symbol: str) -> str:
    meta = classify_symbol(symbol, use_yfinance=False)
    return str(meta.get("etf_proxy") or "SPY")


def all_industry_ids() -> list[str]:
    return [k for k in load_catalog().keys() if k != DEFAULT_INDUSTRY]


def persist_taxonomy() -> None:
    """Write built-in catalog to data/industry/taxonomy.json."""
    TAXONOMY_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc = {"version": 1, "industries": _catalog()}
    TAXONOMY_PATH.write_text(json.dumps(doc, indent=2), encoding="utf-8")
