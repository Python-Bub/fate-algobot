"""Known multi-industry conglomerates — seed blends before similarity/RL refine them."""

from __future__ import annotations

# Symbols that legitimately span multiple of the 50 buckets (not exact single fit).
HYBRID_BLEND: dict[str, dict[str, float]] = {
    "AMZN": {"hypermarkets_discount": 0.42, "application_software": 0.33, "industrial_logistics_reits": 0.15, "interactive_media": 0.10},
    "TSLA": {"auto_manufacturers": 0.52, "application_software": 0.22, "renewable_energy": 0.16, "semiconductors": 0.10},
    "BRK-B": {"diversified_banks": 0.28, "property_casualty_insurance": 0.22, "railroads": 0.18, "hypermarkets_discount": 0.16, "application_software": 0.16},
    "BRK.B": {"diversified_banks": 0.28, "property_casualty_insurance": 0.22, "railroads": 0.18, "hypermarkets_discount": 0.16, "application_software": 0.16},
    "JNJ": {"big_pharma": 0.55, "medical_devices": 0.30, "healthcare_providers": 0.15},
    "GE": {"aerospace_defense": 0.35, "renewable_energy": 0.30, "construction_machinery": 0.20, "diversified_banks": 0.15},
    "DIS": {"entertainment_streaming": 0.45, "interactive_media": 0.30, "hotels_resorts_cruise": 0.25},
    "GOOGL": {"interactive_media": 0.55, "application_software": 0.30, "semiconductors": 0.15},
    "GOOG": {"interactive_media": 0.55, "application_software": 0.30, "semiconductors": 0.15},
}


def hybrid_blend(symbol: str) -> dict[str, float] | None:
    sym = symbol.strip().upper().replace(".", "-")
    return dict(HYBRID_BLEND.get(sym) or {})
