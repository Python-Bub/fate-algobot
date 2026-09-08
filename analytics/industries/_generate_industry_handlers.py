#!/usr/bin/env python3
"""Generate 50 specialized industry handler modules from master specifications."""

from __future__ import annotations

import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HANDLERS_DIR = ROOT / "analytics" / "industries" / "handlers"

# fmt: off
MASTER: list[dict] = [
    {"id": "biotech", "name": "Biotechnology", "etf": "IBB", "mode": "event_driven", "rate": -0.1, "exp": 0.3, "ndx": 1.1, "def": 0.0, "corr": 0.88,
     "leaders": ("AMGN", "GILD", "VRTX", "REGN", "BIIB", "MRNA"),
     "patterns": ("biotechnology", "biotech", "genomic", "gene editing", "cell therapy", "immuno-oncology"),
     "hints": ("AMGN", "GILD", "VRTX", "REGN", "BIIB", "MRNA", "BNTX", "SGEN", "ILMN", "CRSP", "NTLA", "BEAM", "SRPT", "BMRN", "ALNY", "EXAS", "IONS", "NBIX", "RARE", "FOLD"),
     "bull": ("phase 3 success", "fda approval", "breakthrough therapy", "trial met primary", "orphan drug", "positive data", "complete response"),
     "bear": ("clinical hold", "trial failure", "fda rejection", "safety concern", "offering", "dilution", "phase 2 miss", "complete response letter"),
     "events_bull": ("fda approves", "topline positive", "accelerated approval"),
     "events_bear": ("clinical hold", "trial halted", "failed endpoint"),
     "commodities": ("trial", "fda", "phase", "biomarker"),
     "notes": "R&D burn vs cash runway; binary trial outcomes; low SPY correlation."},
    {"id": "big_pharma", "name": "Big Pharma", "etf": "XPH", "mode": "defensive", "rate": 0.0, "exp": 0.2, "ndx": 0.6, "def": 0.55, "corr": 0.72,
     "leaders": ("LLY", "JNJ", "MRK", "PFE", "ABBV", "NVS", "AZN", "BMY"),
     "patterns": ("drug manufacturers", "pharmaceutical", "big pharma"),
     "hints": ("LLY", "JNJ", "MRK", "PFE", "ABBV", "NVS", "AZN", "BMY", "GSK", "SNY", "TAK"),
     "bull": ("beats estimates", "raises guidance", "patent win", "formulary inclusion", "blockbuster"),
     "bear": ("patent cliff", "generic entry", "medicare negotiation", "fda warning letter", "recall"),
     "events_bull": ("fda approval", "label expansion"),
     "events_bear": ("patent expiry", "price cap", "generic launch"),
     "commodities": ("prescription", "formulary", "patent"),
     "notes": "Patent cliff timeline; Medicare pricing; low-beta defensive."},
    {"id": "medical_devices", "name": "Medical Devices", "etf": "IHI", "mode": "hybrid", "rate": 0.0, "exp": 0.5, "ndx": 0.8, "def": 0.35, "corr": 0.78,
     "leaders": ("MDT", "ABT", "ISRG", "SYK", "BSX", "EW", "ZBH"),
     "patterns": ("medical devices", "medical instruments", "surgical", "orthopedic", "pacemaker"),
     "hints": ("MDT", "ABT", "ISRG", "SYK", "BSX", "EW", "ZBH", "DXCM", "PODD", "HOLX", "ALGN"),
     "bull": ("procedure volume", "hospital capex", "robotics adoption", "guidance raise"),
     "bear": ("hospital budget cut", "recall", "reimbursement cut", "elective delay"),
     "events_bull": ("fda clearance", "510k"),
     "events_bear": ("class 1 recall", "warning letter"),
     "commodities": ("surgery", "hospital", "implant"),
     "notes": "Gross margin >60%; elective surgery volume driver."},
    {"id": "life_sciences_tools", "name": "Life Sciences Tools", "etf": "XLV", "mode": "follow_nasdaq", "rate": 0.1, "exp": 0.8, "ndx": 1.0, "def": 0.1, "corr": 0.82,
     "leaders": ("TMO", "DHR", "A", "IQV", "CRL", "WAT", "TECH"),
     "patterns": ("diagnostics", "life sciences", "research", "laboratory", "contract research", "cro"),
     "hints": ("TMO", "DHR", "A", "IQV", "CRL", "WAT", "TECH", "BIO", "MTD", "RVTY"),
     "bull": ("backlog growth", "biotech funding", "instrument demand", "academic grants"),
     "bear": ("biotech funding winter", "capex pause", "china weakness"),
     "events_bull": ("record orders", "backlog up"),
     "events_bear": ("guidance cut", "funding drought"),
     "commodities": ("instrument", "sequencing", "lab"),
     "notes": "Backlog growth; VC funding into biotech drives instrument demand."},
    {"id": "healthcare_providers", "name": "Healthcare Providers", "etf": "XLV", "mode": "defensive", "rate": -0.2, "exp": 0.2, "ndx": 0.5, "def": 0.65, "corr": 0.7,
     "leaders": ("UNH", "ELV", "CI", "HUM", "CVS", "HCA", "UHS"),
     "patterns": ("health care plans", "hospitals", "healthcare providers", "managed care", "health services"),
     "hints": ("UNH", "ELV", "CI", "HUM", "CVS", "HCA", "UHS", "DVA", "THC", "MOH", "CNC"),
     "bull": ("membership growth", "medical loss ratio beat", "rate increase", "utilization stable"),
     "bear": ("mlr miss", "medicare cut", "nurse wage inflation", "utilization spike"),
     "events_bull": ("cms rate", "star rating"),
     "events_bear": ("reimbursement cut", "mlr pressure"),
     "commodities": ("medicare", "medicaid", "mlr", "bed"),
     "notes": "Bed occupancy; payer mix; CMS reimbursement updates."},
    {"id": "healthcare_technology", "name": "Healthcare Technology", "etf": "XLV", "mode": "follow_nasdaq", "rate": 0.2, "exp": 0.9, "ndx": 1.2, "def": 0.05, "corr": 0.8,
     "leaders": ("VEEV", "TDOC", "HIMS", "DOCS", "CERN", "MDRX"),
     "patterns": ("health information", "healthcare technology", "health tech", "telehealth", "ehr"),
     "hints": ("VEEV", "TDOC", "HIMS", "DOCS", "ONEM", "PHR"),
     "bull": ("contract win", "hospital go-live", "saas growth", "ARR beat"),
     "bear": ("security breach", "privacy fine", "churn", "telehealth cut"),
     "events_bull": ("enterprise deal", "platform migration"),
     "events_bear": ("hipaa", "data breach", " outage"),
     "commodities": ("telehealth", "ehr", "hipaa"),
     "notes": "LTV/CAC; privacy regulation hits entire group."},
    {"id": "residential_reits", "name": "Residential REITs", "etf": "REZ", "mode": "inverse_rates", "rate": -0.75, "exp": 0.4, "ndx": 0.4, "def": 0.2, "corr": 0.9,
     "leaders": ("EQR", "AVB", "ESS", "MAA", "UDR", "CPT", "AIV"),
     "patterns": ("residential reit", "reit—residential", "apartment reit", "multifamily"),
     "hints": ("EQR", "AVB", "ESS", "MAA", "UDR", "CPT", "AIV", "INVH", "AMH"),
     "bull": ("rent growth", "occupancy up", "concession down", "rate cut"),
     "bear": ("rent decline", "supply surge", "rate hike", "concession increase"),
     "events_bull": ("rent reacceleration", "fed pivot"),
     "events_bear": ("yield spike", "housing starts surge"),
     "commodities": ("rent", "multifamily", "apartment", "mortgage"),
     "notes": "Net effective rent; inverse to 10y Treasury."},
    {"id": "commercial_office_reits", "name": "Commercial Office REITs", "etf": "VNQ", "mode": "inverse_rates", "rate": -0.65, "exp": 0.5, "ndx": 0.5, "def": 0.1, "corr": 0.88,
     "leaders": ("BXP", "VNO", "SLG", "KRC", "DEI", "OFC"),
     "patterns": ("office reit", "reit—office", "commercial office"),
     "hints": ("BXP", "VNO", "SLG", "KRC", "DEI", "HIW"),
     "bull": ("return to office", "lease signed", "occupancy stabil", "wault extended"),
     "bear": ("default", "vacancy rise", "cre stress", "remote work"),
     "events_bull": ("anchor lease", "occupancy beat"),
     "events_bear": ("tenant bankruptcy", "cre loan"),
     "commodities": ("office", "wault", "occupancy"),
     "notes": "WAULT; transit ridership; CRE lending standards."},
    {"id": "retail_reits", "name": "Retail REITs", "etf": "VNQ", "mode": "inverse_rates", "rate": -0.6, "exp": 0.4, "ndx": 0.5, "def": 0.15, "corr": 0.86,
     "leaders": ("SPG", "O", "REG", "FRT", "KIM", "BRX"),
     "patterns": ("retail reit", "reit—retail", "shopping center", "mall reit"),
     "hints": ("SPG", "REG", "FRT", "KIM", "BRX", "MAC", "SKT"),
     "bull": ("foot traffic", "tenant sales", "re-leasing spread", "occupancy cost ratio ok"),
     "bear": ("anchor closure", "bankruptcy", "retail apocalypse", "rent cut"),
     "events_bull": ("tenant sales beat", "re-leasing positive"),
     "events_bear": ("chapter 11", "store closure wave"),
     "commodities": ("mall", "foot traffic", "tenant"),
     "notes": "Tenant occupancy cost ratio; anchor tenant risk."},
    {"id": "industrial_logistics_reits", "name": "Industrial & Logistics REITs", "etf": "IYR", "mode": "hybrid", "rate": -0.55, "exp": 0.7, "ndx": 0.6, "def": 0.1, "corr": 0.87,
     "leaders": ("PLD", "EXR", "PSA", "REXR", "FR", "STAG", "EGP"),
     "patterns": ("industrial reit", "reit—industrial", "warehouse", "logistics reit", "self storage"),
     "hints": ("PLD", "EXR", "PSA", "REXR", "FR", "STAG", "EGP", "TRNO", "COLD"),
     "bull": ("rent reversion", "e-commerce demand", "supply chain", "development yield"),
     "bear": ("amazon slowdown", "oversupply", "cap rate expansion"),
     "events_bull": ("record leasing", "rent spread"),
     "events_bear": ("warehouse glut", "demand softening"),
     "commodities": ("warehouse", "fulfillment", "storage"),
     "notes": "Rent reversion; e-commerce % of retail."},
    {"id": "specialized_reits", "name": "Specialized REITs", "etf": "XLRE", "mode": "hybrid", "rate": -0.55, "exp": 0.8, "ndx": 1.0, "def": 0.1, "corr": 0.85,
     "leaders": ("EQIX", "AMT", "CCI", "DLR", "WELL", "PSA", "SBAC"),
     "patterns": ("data center", "cell tower", "reit—specialty", "reit—diversified", "healthcare reit", "tower reit"),
     "hints": ("EQIX", "AMT", "CCI", "DLR", "WELL", "SBAC", "IRM", "CONE"),
     "bull": ("ai demand", "cloud capex", "tower lease", "power capacity"),
     "bear": ("rate spike", "hyperscaler pause", "interest expense"),
     "events_bull": ("hyperscaler deal", "ai server demand"),
     "events_bear": ("capex cut", "yield jump"),
     "commodities": ("data center", "tower", "ai server"),
     "notes": "PUE/churn; cloud capex from MSFT/AMZN/GOOG."},
    {"id": "semiconductors", "name": "Semiconductors", "etf": "SMH", "mode": "follow_nasdaq", "rate": 0.0, "exp": 1.2, "ndx": 1.5, "def": 0.0, "corr": 0.9,
     "leaders": ("NVDA", "TSM", "AVGO", "AMD", "INTC", "QCOM", "MU", "ASML"),
     "patterns": ("semiconductor", "semiconductors", "chip", "gpu", "foundry"),
     "hints": ("NVDA", "TSM", "AVGO", "AMD", "INTC", "QCOM", "MU", "ASML", "MRVL", "ON", "NXPI", "TXN", "ADI", "LRCX", "KLAC", "AMAT"),
     "bull": ("ai demand", "book-to-bill", "supply tight", "export license", "data center"),
     "bear": ("inventory glut", "export ban", "cycle downturn", "book-to-bill below 1"),
     "events_bull": ("beat on ai", "guidance raise", "tsmc capacity"),
     "events_bear": ("export restriction", "inventory days high"),
     "commodities": ("wafer", "chip", "foundry", "hbm"),
     "notes": "Book-to-bill; inventory days; trade war headline risk."},
    {"id": "semi_equipment", "name": "Semiconductor Equipment", "etf": "SMH", "mode": "follow_nasdaq", "rate": 0.0, "exp": 1.3, "ndx": 1.4, "def": 0.0, "corr": 0.92,
     "leaders": ("ASML", "LRCX", "AMAT", "KLAC", "TER", "ONTO"),
     "patterns": ("semiconductor equipment", "wafer fab", "lithography"),
     "hints": ("ASML", "LRCX", "AMAT", "KLAC", "TER", "ONTO", "NVMI", "ACLS"),
     "bull": ("fab build", "capex raise", "chips act", "order backlog"),
     "bear": ("fab pause", "capex cut", "order cancel"),
     "events_bull": ("tsmc capex", "intel fab"),
     "events_bear": ("push out", "order push"),
     "commodities": ("lithography", "fab", "capex"),
     "notes": "Multi-year boom/bust; moves on fab capex headlines."},
    {"id": "application_software", "name": "Application Software", "etf": "IGV", "mode": "follow_nasdaq", "rate": 0.2, "exp": 1.0, "ndx": 1.3, "def": 0.0, "corr": 0.84,
     "leaders": ("CRM", "NOW", "ADBE", "INTU", "WDAY", "SNOW", "DDOG"),
     "patterns": ("software—application", "software application", "saas", "enterprise software"),
     "hints": ("CRM", "NOW", "ADBE", "INTU", "WDAY", "SNOW", "DDOG", "TEAM", "HUBS", "ZM", "DOCU"),
     "bull": ("nrr above 110", "billings beat", "seat expansion", "ai copilot"),
     "bear": ("nrr decline", "churn", "budget freeze", "multiple compression"),
     "events_bull": ("raise nrr", "large deal"),
     "events_bear": ("layoffs", "capex cut it"),
     "commodities": ("saas", "subscription", "seat"),
     "notes": "NRR >110%; IT budget surveys; rate-sensitive multiples."},
    {"id": "systems_software", "name": "Systems Software", "etf": "IGV", "mode": "follow_nasdaq", "rate": 0.15, "exp": 0.9, "ndx": 1.2, "def": 0.15, "corr": 0.83,
     "leaders": ("MSFT", "ORCL", "PANW", "CRWD", "FTNT", "ZS", "NET"),
     "patterns": ("software—infra", "systems software", "cybersecurity", "security software", "database"),
     "hints": ("MSFT", "ORCL", "PANW", "CRWD", "FTNT", "ZS", "NET", "OKTA", "S", "IBM"),
     "bull": ("arr growth", "ransomware spike", "cloud migration", "platform stickiness"),
     "bear": ("breach at peer", "budget defer", "open source threat"),
     "events_bull": ("major breach industry", "fed mandate"),
     "events_bear": ("zero day", "outage"),
     "commodities": ("cyber", "cloud", "database"),
     "notes": "Mission-critical; ransomware waves lift group."},
    {"id": "tech_hardware", "name": "Technology Hardware", "etf": "XLK", "mode": "hybrid", "rate": 0.1, "exp": 0.9, "ndx": 1.2, "def": 0.05, "corr": 0.81,
     "leaders": ("AAPL", "DELL", "HPQ", "HPE", "STX", "WDC", "LOGI"),
     "patterns": ("computer hardware", "consumer electronics", "technology hardware", "storage device"),
     "hints": ("AAPL", "DELL", "HPQ", "HPE", "STX", "WDC", "LOGI", "SONO"),
     "bull": ("upgrade cycle", "iphone demand", "pc recovery", "holiday strong"),
     "bear": ("inventory channel", "demand miss", "component cost", "china weak"),
     "events_bull": ("product launch", "sell through beat"),
     "events_bear": ("cut production", "demand warning"),
     "commodities": ("iphone", "pc", "smartphone", "foxconn"),
     "notes": "Consumer upgrade cycles; Foxconn/assembly signals."},
    {"id": "diversified_banks", "name": "Diversified Banks", "etf": "KBE", "mode": "hybrid", "rate": 0.4, "exp": 0.8, "ndx": 0.9, "def": 0.2, "corr": 0.87,
     "leaders": ("JPM", "BAC", "WFC", "C", "MS", "GS", "USB", "PNC"),
     "patterns": ("banks—diversified", "diversified banks", "money center"),
     "hints": ("JPM", "BAC", "WFC", "C", "MS", "GS", "USB", "PNC", "TFC", "BK"),
     "bull": ("nim expansion", "net interest income", "stress test pass", "loan growth"),
     "bear": ("credit loss", "deposit flight", "regulatory fine", "inversion"),
     "events_bull": ("fed hike", "stress test clear"),
     "events_bear": ("svb", "deposit outflow", "cecl spike"),
     "commodities": ("nim", "deposit", "loan"),
     "notes": "NIM vs Fed path; stress tests move group."},
    {"id": "regional_banks", "name": "Regional Banks", "etf": "KRE", "mode": "hybrid", "rate": 0.5, "exp": 0.7, "ndx": 0.8, "def": 0.1, "corr": 0.91,
     "leaders": ("PNC", "USB", "TFC", "FITB", "RF", "KEY", "ZION"),
     "patterns": ("banks—regional", "regional banks"),
     "hints": ("PNC", "USB", "TFC", "FITB", "RF", "KEY", "ZION", "CFG", "HBAN", "MTB"),
     "bull": ("deposit stable", "cre manageable", "buyback"),
     "bear": ("cre exposure", "unrealized losses", "deposit beta spike", "run risk"),
     "events_bull": ("deposit inflows", "fdic calm"),
     "events_bear": ("regional bank", "deposit run", "cre default"),
     "commodities": ("cre", "deposit beta", "unrealized"),
     "notes": "Systemic cluster risk on one failure."},
    {"id": "property_casualty_insurance", "name": "Property & Casualty Insurance", "etf": "KIE", "mode": "defensive", "rate": 0.1, "exp": 0.3, "ndx": 0.5, "def": 0.7, "corr": 0.8,
     "leaders": ("PGR", "TRV", "ALL", "CB", "AIG", "HIG", "WRB"),
     "patterns": ("insurance—property", "property & casualty", "pc insurance"),
     "hints": ("PGR", "TRV", "ALL", "CB", "AIG", "HIG", "WRB", "CINF", "L"),
     "bull": ("combined ratio beat", "rate increase approved", "pricing firm"),
     "bear": ("cat loss", "hurricane", "wildfire", "combined ratio miss"),
     "events_bull": ("rate approval", "pricing hard"),
     "events_bear": ("cat event", "storm landfall"),
     "commodities": ("hurricane", "wildfire", "combined ratio"),
     "notes": "Combined ratio; NOAA hurricane season."},
    {"id": "life_health_insurance", "name": "Life & Health Insurance", "etf": "KIE", "mode": "inverse_rates", "rate": -0.45, "exp": 0.2, "ndx": 0.5, "def": 0.6, "corr": 0.79,
     "leaders": ("MET", "PRU", "AFL", "UNM", "LNC", "GL"),
     "patterns": ("insurance—life", "life insurance", "insurance—diversified"),
     "hints": ("MET", "PRU", "AFL", "UNM", "LNC", "GL", "VOYA"),
     "bull": ("investment income", "long bond yield", "mortality stable"),
     "bear": ("longevity", "rate cut", "alternative asset markdown"),
     "events_bull": ("yield curve steepen"),
     "events_bear": ("rate cut cycle", "crediting rate"),
     "commodities": ("annuity", "mortality", "long bond"),
     "notes": "Bond book yield; demographic aging."},
    {"id": "financial_data_exchanges", "name": "Financial Data & Exchanges", "etf": "XLF", "mode": "follow_market", "rate": 0.3, "exp": 0.9, "ndx": 1.0, "def": 0.15, "corr": 0.86,
     "leaders": ("SPGI", "ICE", "CME", "MCO", "MSCI", "NDAQ", "COIN"),
     "patterns": ("financial data", "capital markets", "exchange", "asset management", "rating agency"),
     "hints": ("SPGI", "ICE", "CME", "MCO", "MSCI", "NDAQ", "MKTX", "FDS"),
     "bull": ("trading volume", "vix elevated", "aum growth", "data subscription"),
     "bear": ("volume drought", "fee pressure", "crypto winter"),
     "events_bull": ("vol spike", "record volume"),
     "events_bear": ("trading slowdown", "fee cut"),
     "commodities": ("volume", "vix", "aum"),
     "notes": "ADV and VIX drive exchange revenues."},
    {"id": "consumer_finance", "name": "Consumer Finance", "etf": "XLF", "mode": "hybrid", "rate": 0.35, "exp": 0.8, "ndx": 0.95, "def": 0.05, "corr": 0.84,
     "leaders": ("V", "MA", "AXP", "COF", "SYF", "ALLY", "SOFI"),
     "patterns": ("credit services", "consumer finance", "credit card", "payment"),
     "hints": ("V", "MA", "AXP", "COF", "SYF", "ALLY", "SOFI", "AFRM", "UPST"),
     "bull": ("spend growth", "delinquency stable", "loan growth"),
     "bear": ("charge-off rise", "delinquency spike", "rate cap", "recession fear"),
     "events_bull": ("spend data strong", "naco stable"),
     "events_bear": ("delinquency", "charge-off", "bnpl stress"),
     "commodities": ("delinquency", "charge-off", "revolving"),
     "notes": "NCO rate; consumer credit delinquency."},
    {"id": "integrated_oil_gas", "name": "Integrated Oil & Gas", "etf": "XLE", "mode": "commodity", "rate": 0.2, "exp": 0.6, "ndx": 0.7, "def": 0.1, "corr": 0.93,
     "leaders": ("XOM", "CVX", "SHEL", "TTE", "BP", "COP"),
     "patterns": ("oil & gas integrated", "integrated oil", "supermajor"),
     "hints": ("XOM", "CVX", "SHEL", "TTE", "BP", "COP", "OXY"),
     "bull": ("opec cut", "crude rally", "refining margin", "buyback"),
     "bear": ("demand destruction", "opec increase", "windfall tax"),
     "events_bull": ("opec+", "supply cut"),
     "events_bear": ("demand concern", "inventory build"),
     "commodities": ("wti", "brent", "crude", "opec"),
     "notes": "Lockstep with WTI/Brent futures."},
    {"id": "oil_gas_ep", "name": "Oil & Gas E&P", "etf": "XOP", "mode": "commodity", "rate": 0.1, "exp": 0.9, "ndx": 0.75, "def": 0.0, "corr": 0.94,
     "leaders": ("EOG", "PXD", "DVN", "FANG", "MRO", "OVV", "APA"),
     "patterns": ("oil & gas e&p", "exploration", "upstream"),
     "hints": ("EOG", "PXD", "DVN", "FANG", "MRO", "OVV", "APA", "CTRA", "CHK"),
     "bull": ("production beat", "hedge gain", "rig count", "permit"),
     "bear": ("gas glut", "basis blowout", "decline curve"),
     "events_bull": ("eia draw", "rig up"),
     "events_bear": ("eia build", "gas price collapse"),
     "commodities": ("natural gas", "wti", "rig", "eia"),
     "notes": "Amplified oil beta; EIA inventory weekly."},
    {"id": "oil_gas_equipment", "name": "Oil & Gas Equipment", "etf": "XES", "mode": "commodity", "rate": 0.0, "exp": 0.8, "ndx": 0.7, "def": 0.0, "corr": 0.9,
     "leaders": ("SLB", "HAL", "BKR", "NOV", "CHX", "FTI"),
     "patterns": ("oil & gas equipment", "oilfield services", "drilling"),
     "hints": ("SLB", "HAL", "BKR", "NOV", "CHX", "FTI", "WFRD"),
     "bull": ("rig count", "international capex", "dayrate"),
     "bear": ("capex cut", "utilization fall", "frac spread narrow"),
     "events_bull": ("rig count up", "dayrate hike"),
     "events_bear": ("capex guide down", "stacked frac"),
     "commodities": ("rig", "dayrate", "frac"),
     "notes": "Lags crude 3-6 months."},
    {"id": "renewable_energy", "name": "Renewable Energy", "etf": "ICLN", "mode": "inverse_rates", "rate": -0.5, "exp": 0.7, "ndx": 1.0, "def": 0.05, "corr": 0.85,
     "leaders": ("ENPH", "SEDG", "FSLR", "NEE", "RUN", "PLUG"),
     "patterns": ("solar", "renewable", "clean energy", "wind energy"),
     "hints": ("ENPH", "SEDG", "FSLR", "RUN", "PLUG", "BE", "NOVA"),
     "bull": ("ira credit", "solar demand", "lcoe decline", "policy support"),
     "bear": ("rate hike", "subsidy cut", "module glut", "interconnection delay"),
     "events_bull": ("tax credit extend", "solar install beat"),
     "events_bear": ("subsidy rollback", "module oversupply"),
     "commodities": ("solar", "wind", "lcoe", "ira"),
     "notes": "Rate-sensitive upfront capex; policy driven."},
    {"id": "electric_gas_utilities", "name": "Electric & Gas Utilities", "etf": "XLU", "mode": "inverse_rates", "rate": -0.65, "exp": 0.2, "ndx": 0.3, "def": 0.75, "corr": 0.88,
     "leaders": ("NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE"),
     "patterns": ("utilities—", "electric utilities", "gas utilities", "regulated utility"),
     "hints": ("NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "XEL", "PEG", "ED"),
     "bull": ("allowed roe", "rate case win", "load growth", "data center power"),
     "bear": ("rate case loss", "wildfire liability", "yield competition"),
     "events_bull": ("rate case approved", "load forecast up"),
     "events_bear": ("wildfire", "rate denial"),
     "commodities": ("utility", "grid", "allowed roe"),
     "notes": "Bond proxy; drops when yields rise."},
    {"id": "auto_manufacturers", "name": "Auto Manufacturers", "etf": "CARZ", "mode": "hybrid", "rate": 0.0, "exp": 0.9, "ndx": 0.85, "def": 0.05, "corr": 0.86,
     "leaders": ("TSLA", "TM", "GM", "F", "RIVN", "LCID", "STLA"),
     "patterns": ("auto manufacturers", "automobile", "motor vehicles"),
     "hints": ("TSLA", "TM", "GM", "F", "RIVN", "LCID", "STLA", "HMC", "NIO"),
     "bull": ("delivery beat", "ev demand", "inventory days low", "incentive cut"),
     "bear": ("strike", "inventory glut", "price war", "recall"),
     "events_bull": ("delivery record", "ev subsidy"),
     "events_bear": ("uaw strike", "recall", "price cut"),
     "commodities": ("steel", "lithium", "battery", "auto loan"),
     "notes": "Dealer days supply; union negotiations."},
    {"id": "luxury_goods", "name": "Luxury Goods", "etf": "XLY", "mode": "hybrid", "rate": 0.0, "exp": 0.6, "ndx": 1.0, "def": 0.1, "corr": 0.82,
     "leaders": ("LVMUY", "TPR", "RL", "CPRI", "RACE", "BIRK"),
     "patterns": ("luxury", "apparel—luxury", "designer", "premium fashion"),
     "hints": ("TPR", "RL", "CPRI", "RACE", "BIRK", "DECK", "MONC"),
     "bull": ("china reopen", "pricing power", "tourist spend", "hnw growth"),
     "bear": ("china slowdown", "asp reduction", "counterfeit", "wealth shock"),
     "events_bull": ("china sales beat", "pricing increase"),
     "events_bear": ("china weak", "discounting"),
     "commodities": ("luxury", "tourist", "yuan"),
     "notes": "HNW wealth; travel retail flows."},
    {"id": "hotels_resorts_cruise", "name": "Hotels & Cruise", "etf": "XLY", "mode": "hybrid", "rate": 0.0, "exp": 0.9, "ndx": 0.95, "def": 0.0, "corr": 0.89,
     "leaders": ("MAR", "HLT", "H", "CCL", "RCL", "NCLH", "BKNG"),
     "patterns": ("hotels", "resorts", "cruise", "lodging", "casino resort"),
     "hints": ("MAR", "HLT", "H", "CCL", "RCL", "NCLH", "WH", "EXPE"),
     "bull": ("revpar up", "booking strong", "load factor", "business travel"),
     "bear": ("outbreak", "fuel surcharge", "geopolitical travel", "revpar miss"),
     "events_bull": ("revpar beat", "booking record"),
     "events_bear": ("travel warning", "outbreak", "port closure"),
     "commodities": ("revpar", "occupancy", "cruise", "jet fuel"),
     "notes": "RevPAR; airline passenger volumes."},
    {"id": "restaurants_food", "name": "Restaurants", "etf": "XLY", "mode": "hybrid", "rate": 0.0, "exp": 0.5, "ndx": 0.75, "def": 0.15, "corr": 0.83,
     "leaders": ("MCD", "SBUX", "YUM", "CMG", "QSR", "DRI", "TXRH"),
     "patterns": ("restaurants", "food service", "fast food", "casual dining"),
     "hints": ("MCD", "SBUX", "YUM", "CMG", "QSR", "DRI", "TXRH", "WING", "SHAK", "DPZ"),
     "bull": ("same store sales", "digital mix", "menu price", "traffic up"),
     "bear": ("food cost inflation", "wage inflation", "traffic down", "e.coli"),
     "events_bull": ("sss beat", "menu innovation"),
     "events_bear": ("food safety", "minimum wage", "beef price"),
     "commodities": ("beef", "wheat", "dairy", "coffee", "corn", "food cost"),
     "notes": "SSS vs commodity food inputs; minimum wage."},
    {"id": "hypermarkets_discount", "name": "Hypermarkets & Discount", "etf": "XRT", "mode": "defensive", "rate": 0.0, "exp": 0.3, "ndx": 0.6, "def": 0.55, "corr": 0.8,
     "leaders": ("WMT", "COST", "TGT", "DG", "DLTR", "BJ"),
     "patterns": ("discount stores", "department stores", "hypermarket", "supercenter"),
     "hints": ("WMT", "COST", "TGT", "DG", "DLTR", "BJ", "BIG"),
     "bull": ("traffic up", "market share gain", "inventory turn", "gas savings"),
     "bear": ("shrink", "theft", "margin pressure", "inventory glut"),
     "events_bull": ("holiday beat", "traffic surge"),
     "events_bear": ("guidance cut", "inventory markdown"),
     "commodities": ("gasoline", "consumer", "shrink"),
     "notes": "Counter-cyclical; gas prices affect wallet share."},
    {"id": "household_personal_products", "name": "Household Products", "etf": "XLP", "mode": "defensive", "rate": 0.0, "exp": 0.1, "ndx": 0.4, "def": 0.85, "corr": 0.76,
     "leaders": ("PG", "CL", "KMB", "CHD", "CLX", "EL", "KVUE"),
     "patterns": ("household", "personal products", "soap", "cosmetics", "cleaning"),
     "hints": ("PG", "CL", "KMB", "CHD", "CLX", "EL", "KVUE", "COTY"),
     "bull": ("pricing power", "volume stable", "premium mix"),
     "bear": ("private label share", "input cost", "china weak"),
     "events_bull": ("price increase stick"),
     "events_bear": ("volume decline", "promotional intensity"),
     "commodities": ("pulp", "chemical", "soap"),
     "notes": "Volume vs price mix; recession resilient."},
    {"id": "packaged_foods", "name": "Packaged Foods", "etf": "XLP", "mode": "defensive", "rate": 0.0, "exp": 0.1, "ndx": 0.35, "def": 0.8, "corr": 0.77,
     "leaders": ("KO", "PEP", "GIS", "K", "HSY", "MDLZ", "KHC"),
     "patterns": ("packaged foods", "food products", "confectioners", "beverages—non-alcoholic"),
     "hints": ("KO", "PEP", "GIS", "K", "HSY", "MDLZ", "KHC", "CPB", "SJM", "CAG"),
     "bull": ("pricing", "volume return", "snacking trend", "distribution gain"),
     "bear": ("glut", "grain cost", "trade down private label", "obesity drug"),
     "events_bull": ("pricing hold", "volume positive"),
     "events_bear": ("corn spike", "glucagon", "weight loss headwind"),
     "commodities": ("corn", "wheat", "cocoa", "sugar", "beef", "grain"),
     "notes": "Food commodity inputs; GLP-1 headwind theme."},
    {"id": "aerospace_defense", "name": "Aerospace & Defense", "etf": "ITA", "mode": "defensive", "rate": 0.0, "exp": 0.5, "ndx": 0.65, "def": 0.5, "corr": 0.81,
     "leaders": ("RTX", "LMT", "NOC", "GD", "BA", "LHX", "TDG"),
     "patterns": ("aerospace", "defense", "aircraft", "military", "space"),
     "hints": ("RTX", "LMT", "NOC", "GD", "BA", "LHX", "TDG", "HWM", "TXT"),
     "bull": ("defense budget", "backlog record", "flight hours", "contract award"),
     "bear": ("program delay", "grounding", "budget cut", "strike"),
     "events_bull": ("ndaa", "contract win", "geopolitical"),
     "events_bear": ("grounding", "quality issue"),
     "commodities": ("defense", "backlog", "faa"),
     "notes": "Government backlog; geopolitical escalations."},
    {"id": "air_freight_logistics", "name": "Air Freight & Logistics", "etf": "IYT", "mode": "hybrid", "rate": 0.0, "exp": 0.9, "ndx": 0.85, "def": 0.05, "corr": 0.87,
     "leaders": ("UPS", "FDX", "EXPD", "CHRW", "XPO", "JBHT"),
     "patterns": ("integrated freight", "logistics", "courier", "air freight"),
     "hints": ("UPS", "FDX", "EXPD", "CHRW", "XPO", "JBHT", "ODFL", "SAIA"),
     "bull": ("parcel volume", "yield up", "e-commerce ship", "tender reject"),
     "bear": ("volume miss", "jet fuel", "trade tariff", "capacity add"),
     "events_bull": ("peak season strong", "yield beat"),
     "events_bear": ("trade war", "fuel surcharge", "volume guide down"),
     "commodities": ("jet fuel", "diesel", "parcel", "freight"),
     "notes": "Early GDP indicator; fuel and tariffs hit all."},
    {"id": "railroads", "name": "Railroads", "etf": "IYT", "mode": "hybrid", "rate": 0.1, "exp": 1.0, "ndx": 0.75, "def": 0.15, "corr": 0.88,
     "leaders": ("UNP", "CSX", "NSC", "CP", "CNI"),
     "patterns": ("railroads", "rail freight", "class i rail"),
     "hints": ("UNP", "CSX", "NSC", "CP", "CNI", "WAB"),
     "bull": ("carload up", "operating ratio improve", "pricing", "intermodal"),
     "bear": ("coal decline", "strike", "weather", "regulatory"),
     "events_bull": ("carload beat", "precision scheduled railroading"),
     "events_bear": ("derailment", "strike vote"),
     "commodities": ("coal", "grain", "intermodal", "carload"),
     "notes": "Operating ratio; weekly carload data."},
    {"id": "construction_machinery", "name": "Construction Machinery", "etf": "XLI", "mode": "hybrid", "rate": 0.0, "exp": 1.0, "ndx": 0.85, "def": 0.05, "corr": 0.87,
     "leaders": ("CAT", "DE", "CNH", "PCAR", "OSK", "URI"),
     "patterns": ("farm & construction", "construction machinery", "heavy machinery", "agricultural machinery"),
     "hints": ("CAT", "DE", "CNH", "PCAR", "OSK", "URI", "ALG"),
     "bull": ("dealer inventory down", "infrastructure bill", "mining capex", "backlog"),
     "bear": ("dealer destock", "china weak", "farm income down"),
     "events_bull": ("infrastructure", "dealer survey up"),
     "events_bear": ("dealer inventory high", "china demand"),
     "commodities": ("steel", "copper", "infrastructure"),
     "notes": "Dealer destocking velocity; housing starts."},
    {"id": "building_products", "name": "Building Products", "etf": "XLI", "mode": "hybrid", "rate": -0.2, "exp": 1.0, "ndx": 0.8, "def": 0.05, "corr": 0.86,
     "leaders": ("SHW", "MLM", "VMC", "BLDR", "OC", "TREX"),
     "patterns": ("building products", "building materials", " lumber", "cement", "roofing"),
     "hints": ("SHW", "MLM", "VMC", "BLDR", "OC", "TREX", "AWI", "FBIN"),
     "bull": ("housing starts", "repair remodel", "pricing", "capacity util"),
     "bear": ("mortgage rate spike", "housing slowdown", "input cost"),
     "events_bull": ("permits up", "housing starts beat"),
     "events_bear": ("mortgage rate", "housing miss"),
     "commodities": ("lumber", "cement", "housing starts", "mortgage"),
     "notes": "Housing starts and mortgage rates."},
    {"id": "chemicals", "name": "Chemicals", "etf": "XLB", "mode": "hybrid", "rate": 0.0, "exp": 1.0, "ndx": 0.75, "def": 0.05, "corr": 0.85,
     "leaders": ("LIN", "APD", "ECL", "DD", "DOW", "LYB", "CE"),
     "patterns": ("chemicals", "specialty chemicals", "agricultural inputs", "fertilizer"),
     "hints": ("LIN", "APD", "ECL", "DD", "DOW", "LYB", "CE", "FMC", "CF"),
     "bull": ("spread widen", "volume up", "auto build", "crop acreage"),
     "bear": ("gas feedstock spike", "destock", "china demand"),
     "events_bull": ("spread expansion", "volume beat"),
     "events_bear": ("destocking", "natural gas feed"),
     "commodities": ("natural gas", "ethylene", "fertilizer", "potash"),
     "notes": "Spread over nat gas; early cycle."},
    {"id": "metals_mining", "name": "Metals & Mining", "etf": "XME", "mode": "commodity", "rate": 0.0, "exp": 1.1, "ndx": 0.7, "def": 0.0, "corr": 0.92,
     "leaders": ("FCX", "NEM", "GOLD", "RIO", "BHP", "VALE", "AA"),
     "patterns": ("gold", "silver", "copper", "steel", "aluminum", "mining", "metals"),
     "hints": ("FCX", "NEM", "GOLD", "RIO", "BHP", "VALE", "AA", "X", "CLF", "STLD"),
     "bull": ("copper squeeze", "china stimulus", "gold safe haven", "lme draw"),
     "bear": ("china property", "dollar strong", "inventory build"),
     "events_bull": ("china stimulus", "lme cancel"),
     "events_bear": ("china weak", "inventory surge"),
     "commodities": ("copper", "gold", "iron ore", "lme", "steel"),
     "notes": "Daily metal price moves dominate."},
    {"id": "wireless_telecom", "name": "Wireless Telecom", "etf": "XLC", "mode": "inverse_rates", "rate": -0.55, "exp": 0.3, "ndx": 0.5, "def": 0.55, "corr": 0.84,
     "leaders": ("TMUS", "VZ", "T", "LUMN", "USM"),
     "patterns": ("telecom services", "wireless", "communication services"),
     "hints": ("TMUS", "VZ", "T", "LUMN", "USM", "SATS"),
     "bull": ("churn low", "arpu up", "fiber build", "dividend safe"),
     "bear": ("price war", "churn spike", "capex overhang", "yield competition"),
     "events_bull": ("postpaid net add", "dividend raise"),
     "events_bear": ("price cut", "churn warning"),
     "commodities": ("spectrum", "churn", "arpu"),
     "notes": "Bond-proxy dividend; postpaid churn."},
    {"id": "interactive_media", "name": "Interactive Media", "etf": "XLC", "mode": "follow_nasdaq", "rate": 0.15, "exp": 1.0, "ndx": 1.4, "def": 0.0, "corr": 0.86,
     "leaders": ("META", "GOOGL", "GOOG", "SNAP", "PINS", "RDDT"),
     "patterns": ("internet content", "interactive media", "search", "social media", "online advertising"),
     "hints": ("META", "GOOGL", "GOOG", "SNAP", "PINS", "RDDT", "TTD", "APP"),
     "bull": ("ad spend", "dau growth", "reels monetization", "ai search"),
     "bear": ("ad recession", "att opt out", "antitrust", "tiktok competition"),
     "events_bull": ("ad beat", "engagement record"),
     "events_bear": ("antitrust", "ad slowdown", "privacy"),
     "commodities": ("advertising", "pixel", "dau"),
     "notes": "ARPU/DAU; digital ad budget cycle."},
    {"id": "entertainment_streaming", "name": "Entertainment & Streaming", "etf": "XLC", "mode": "hybrid", "rate": 0.1, "exp": 0.7, "ndx": 1.1, "def": 0.05, "corr": 0.84,
     "leaders": ("NFLX", "DIS", "WBD", "PARA", "SPOT", "LYV"),
     "patterns": ("entertainment", "broadcasting", "streaming", "media—", "movie"),
     "hints": ("NFLX", "DIS", "WBD", "PARA", "SPOT", "LYV", "CMCSA", "FOXA"),
     "bull": ("subscriber add", "content hit", "pricing tier", "box office"),
     "bear": ("churn", "content flop", "strike", "cord cutting margin"),
     "events_bull": ("subscriber beat", "box office record"),
     "events_bear": ("writers strike", "sub miss", "content write down"),
     "commodities": ("streaming", "box office", "subscriber"),
     "notes": "Content ROI; subscriber net adds."},
    {"id": "environmental_waste", "name": "Environmental & Waste", "etf": "XLI", "mode": "defensive", "rate": 0.0, "exp": 0.3, "ndx": 0.45, "def": 0.7, "corr": 0.78,
     "leaders": ("WM", "RSG", "WCN", "CWST", "CLH"),
     "patterns": ("waste management", "environmental", "pollution", "recycling"),
     "hints": ("WM", "RSG", "WCN", "CWST", "CLH", "SRCL"),
     "bull": ("pricing escalator", "volume tonnage", "municipal contract"),
     "bear": ("diesel cost", "volume soft", "recycling price"),
     "events_bull": ("price increase", "contract win"),
     "events_bear": ("fuel surcharge lag", "volume miss"),
     "commodities": ("diesel", "landfill", "tonnage"),
     "notes": "Pricing escalators pass diesel inflation."},
    {"id": "apparel_retail", "name": "Apparel Retail", "etf": "XRT", "mode": "hybrid", "rate": 0.0, "exp": 0.6, "ndx": 0.9, "def": 0.05, "corr": 0.85,
     "leaders": ("TJX", "ROST", "LULU", "NKE", "UAA", "GAP", "ANF"),
     "patterns": ("apparel retail", "specialty retail", "footwear", "clothing store"),
     "hints": ("TJX", "ROST", "LULU", "NKE", "UAA", "GAP", "ANF", "URBN", "AEO"),
     "bull": ("comp beat", "inventory clean", "brand heat", "china reopen"),
     "bear": ("warm winter", "inventory glut", "promotional", "supply delay"),
     "events_bull": ("comp positive", "margin beat"),
     "events_bear": ("inventory up", "weather miss"),
     "commodities": ("cotton", "freight", "apparel"),
     "notes": "GMROII; weather affects seasonal coats."},
    {"id": "marine_shipping", "name": "Marine Shipping", "etf": "BDRY", "mode": "commodity", "rate": 0.0, "exp": 0.8, "ndx": 0.4, "def": 0.0, "corr": 0.91,
     "leaders": ("ZIM", "MATX", "DAC", "GSL", "SBLK", "GOGL"),
     "patterns": ("marine shipping", "shipping", "tanker", "bulk carrier", "container ship"),
     "hints": ("ZIM", "MATX", "DAC", "GSL", "SBLK", "GOGL", "CMRE", "Eagle Bulk"),
     "bull": ("baltic dry up", "spot rate spike", "canal congestion", "tanker tight"),
     "bear": ("rate collapse", "new supply", "trade slowdown"),
     "events_bull": ("bdi surge", "canal delay"),
     "events_bear": ("rate crash", "demurrage"),
     "commodities": ("baltic", "freight rate", "tanker", "container"),
     "notes": "Spot charter rates; canal bottlenecks."},
    {"id": "independent_power_producers", "name": "Independent Power Producers", "etf": "XLU", "mode": "commodity", "rate": 0.0, "exp": 0.7, "ndx": 0.6, "def": 0.05, "corr": 0.87,
     "leaders": ("VST", "NRG", "CEG", "AES", "CWEN"),
     "patterns": ("independent power", "power producers", "merchant power", "ipp"),
     "hints": ("VST", "NRG", "CEG", "AES", "CWEN", "ORA"),
     "bull": ("spark spread widen", "heat wave", "capacity tight", "data center power"),
     "bear": ("power price collapse", "renewable cannibalization", "regulatory"),
     "events_bull": ("heat dome", "power price spike"),
     "events_bear": ("power price negative", "regulatory cap"),
     "commodities": ("power price", "spark spread", "heat"),
     "notes": "Spark/dark spread; grid constraints."},
    {"id": "commercial_services", "name": "Commercial Services", "etf": "XLI", "mode": "hybrid", "rate": 0.0, "exp": 0.5, "ndx": 0.7, "def": 0.2, "corr": 0.79,
     "leaders": ("ADP", "PayX", "CTAS", "UNF", "ABM", "BCO"),
     "patterns": ("specialty business services", "staffing", "security guard", "uniform", "facility"),
     "hints": ("ADP", "PAYX", "CTAS", "UNF", "ABM", "BCO", "MAN", "RHI"),
     "bull": ("white collar hiring", "contract renewal", "cross sell"),
     "bear": ("hiring freeze", "office vacancy", "wage inflation"),
     "events_bull": ("jobs report strong", "contract win"),
     "events_bear": ("layoffs", "office empty"),
     "commodities": ("employment", "office", "staffing"),
     "notes": "White-collar employment linkage."},
    {"id": "distributors", "name": "Distributors", "etf": "XLI", "mode": "hybrid", "rate": 0.0, "exp": 0.6, "ndx": 0.65, "def": 0.1, "corr": 0.8,
     "leaders": ("GWW", "FAST", "WSO", "POOL", "AIT", "CNM"),
     "patterns": ("distribution", "wholesale", "industrial distribution", "distributor"),
     "hints": ("GWW", "FAST", "WSO", "POOL", "AIT", "CNM", "WCC", "MSM"),
     "bull": ("volume growth", "pricing pass", "inventory turn", "digital share"),
     "bear": ("destock", "freight cost", "customer inventory cut"),
     "events_bull": ("daily sales up", "share gain"),
     "events_bear": ("customer destock", "margin squeeze"),
     "commodities": ("freight", "inventory", "working capital"),
     "notes": "Working capital cycle; supplier lead times."},
]
# fmt: on


def _expand_patterns(base: tuple[str, ...], name: str, industry_id: str) -> tuple[str, ...]:
    extras = [
        industry_id.replace("_", " "),
        industry_id.replace("_", "-"),
        name.lower(),
        f"{name.lower()} industry",
    ]
    return tuple(dict.fromkeys(list(base) + extras))


def _handler_source(spec: dict) -> str:
    iid = spec["id"]
    cls = "".join(p.capitalize() for p in iid.split("_")) + "Handler"
    patterns = _expand_patterns(tuple(spec["patterns"]), spec["name"], iid)
    hints = spec["hints"]
    bull = spec["bull"]
    bear = spec["bear"]
    ebull = spec["events_bull"]
    ebear = spec["events_bear"]
    comm = spec["commodities"]
    leaders = spec["leaders"]
    mode = spec["mode"]

    def q(items: tuple[str, ...] | list[str]) -> str:
        return ",\n        ".join(repr(x) for x in items)

    return textwrap.dedent(
        f'''\
        """{spec["name"]} — {spec["notes"]}"""

        from __future__ import annotations

        import numpy as np

        from analytics.industries.base import (
            BaseIndustryHandler,
            ComovementMode,
            FactorTiltResult,
            IndustryContext,
            ClassificationResult,
        )


        class {cls}(BaseIndustryHandler):
            INDUSTRY_ID = {iid!r}
            INDUSTRY_NAME = {spec["name"]!r}
            ETF_PROXY = {spec["etf"]!r}
            COMOVEMENT_MODE = ComovementMode.{mode.upper()}
            RATE_SENSITIVITY = {spec["rate"]}
            EXPANSION_BETA = {spec["exp"]}
            NASDAQ_BETA = {spec["ndx"]}
            DEFENSIVE_SCORE = {spec["def"]}
            INTRA_CORR_PRIOR = {spec["corr"]}

            YAHOO_PATTERNS = (
                {q(patterns)}
            )
            TICKER_HINTS = frozenset({{
                {", ".join(repr(h) for h in hints)}
            }})
            LEADER_TICKERS = (
                {q(leaders)}
            )

            NEWS_BULL = (
                {q(bull)}
            )
            NEWS_BEAR = (
                {q(bear)}
            )
            NEWS_EVENT_BULL = (
                {q(ebull)}
            )
            NEWS_EVENT_BEAR = (
                {q(ebear)}
            )
            COMMODITY_KEYS = (
                {q(comm)}
            )

            def refine_classification(self, ctx: IndustryContext) -> ClassificationResult | None:
                blob = f"{{ctx.sector}} {{ctx.yahoo_industry}}".lower()
                sym = ctx.symbol.upper()
                if sym in self.TICKER_HINTS:
                    return ClassificationResult(
                        industry_id=self.INDUSTRY_ID,
                        industry_name=self.INDUSTRY_NAME,
                        confidence=0.96,
                        etf_proxy=self.ETF_PROXY,
                        comovement_mode=self.COMOVEMENT_MODE.value,
                        reasons=["ticker_hint_refine"],
                    )
                for pat in self.YAHOO_PATTERNS:
                    if pat in blob:
                        return ClassificationResult(
                            industry_id=self.INDUSTRY_ID,
                            industry_name=self.INDUSTRY_NAME,
                            confidence=0.72,
                            etf_proxy=self.ETF_PROXY,
                            comovement_mode=self.COMOVEMENT_MODE.value,
                            reasons=[f"refine:{{pat[:32]}}"],
                        )
                return None

            def compute_factor_tilts(self, ctx: IndustryContext) -> FactorTiltResult:
                rate = self._base_rate_tilt(ctx)
                exp = self._base_expansion_tilt(ctx)
                ndx = self._base_nasdaq_tilt(ctx)
                defensive = self._base_defensive_tilt(ctx)
                news = self.news_factor_tilt(ctx)
                commodity = self._commodity_tilt(ctx)
                notes: list[str] = []

                if self.COMOVEMENT_MODE == ComovementMode.INVERSE_RATES:
                    shock = self._macro(ctx, "rate_shock_20d")
                    if shock > 0.15:
                        rate -= 0.08
                        notes.append("rates_up_headwind")
                    elif shock < -0.1:
                        rate += 0.06
                        notes.append("rates_down_tailwind")

                if self.COMOVEMENT_MODE == ComovementMode.EVENT_DRIVEN:
                    ndx *= 0.35
                    exp *= 0.4
                    notes.append("event_driven_low_beta")

                if self.COMOVEMENT_MODE == ComovementMode.DEFENSIVE:
                    vix = self._macro(ctx, "vix", 20.0)
                    if vix > 24:
                        defensive += 0.12
                        notes.append("flight_to_defensive")

                if self.COMOVEMENT_MODE == ComovementMode.COMMODITY:
                    commodity += self._commodity_tilt(ctx)
                    notes.append("commodity_linked")

                combined = rate + exp * 0.55 + ndx * 0.35 + defensive + news * 0.45 + commodity * 0.35
                return FactorTiltResult(
                    rate_tilt=float(rate),
                    expansion_tilt=float(exp),
                    nasdaq_tilt=float(ndx),
                    defensive_tilt=float(defensive),
                    commodity_tilt=float(commodity),
                    news_tilt=float(news),
                    combined=float(combined),
                    notes=notes,
                )

            def _commodity_tilt(self, ctx: IndustryContext) -> float:
                if not ctx.news_headlines:
                    return 0.0
                ns = self.score_news(ctx.news_headlines)
                tagged = [t for t in ns.event_tags if t.startswith("commodity:")]
                if not tagged:
                    return 0.0
                direction = ns.net
                return float(np.tanh(direction * 1.8))

            def feature_overrides(self, ctx: IndustryContext) -> dict[str, float]:
                tilts = self.compute_factor_tilts(ctx)
                return {{
                    "factor_rate_tilt": tilts.rate_tilt,
                    "factor_expansion_tilt": tilts.expansion_tilt,
                    "industry_sympathy_score": tilts.combined * 0.25,
                }}


        HANDLER = {cls}()
        '''
    )


def generate_all() -> int:
    HANDLERS_DIR.mkdir(parents=True, exist_ok=True)
    init_lines = ['"""Auto-generated industry handler registry."""\n']
    count = 0
    for spec in MASTER:
        iid = spec["id"]
        path = HANDLERS_DIR / f"{iid}.py"
        path.write_text(_handler_source(spec), encoding="utf-8")
        cls = "".join(p.capitalize() for p in iid.split("_")) + "Handler"
        init_lines.append(f"from analytics.industries.handlers.{iid} import HANDLER as _h_{iid}")
        count += 1
    init_lines.append("\nALL_HANDLERS = {")
    for spec in MASTER:
        iid = spec["id"]
        init_lines.append(f'    "{iid}": _h_{iid},')
    init_lines.append("}\n")
    init_lines.append("from analytics.industries.handlers.unclassified import HANDLER as _h_unclassified\n")
    init_lines.append("ALL_HANDLERS['unclassified'] = _h_unclassified\n")
    (HANDLERS_DIR / "__init__.py").write_text("\n".join(init_lines), encoding="utf-8")
    return count


if __name__ == "__main__":
    n = generate_all()
    print(f"Generated {n} industry handlers in {HANDLERS_DIR}")
