"""AI-maintained multi-industry registry — primary + secondary buckets per symbol."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
AI_REGISTRY_PATH = ROOT / "data" / "industry" / "ai_classifications.json"
AI_HISTORY_PATH = ROOT / "data" / "industry" / "ai_classification_history.jsonl"
AI_CODE_SNIPPETS_PATH = ROOT / "analytics" / "industries" / "ai_generated_overrides.py"

_MEM: dict[str, dict] | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_ai_registry(*, reload: bool = False) -> dict[str, dict[str, Any]]:
    global _MEM
    if _MEM is not None and not reload:
        return _MEM
    doc = _load_json(AI_REGISTRY_PATH, {"version": 1, "symbols": {}})
    syms = doc.get("symbols") or {}
    _MEM = {str(k).upper(): v for k, v in syms.items() if isinstance(v, dict)}
    return _MEM


def save_ai_registry(symbols: dict[str, dict[str, Any]], *, meta: dict | None = None) -> None:
    global _MEM
    doc = {
        "version": 2,
        "updated_at_utc": _now(),
        "symbol_count": len(symbols),
        "symbols": symbols,
    }
    if meta:
        doc["meta"] = meta
    _save_json(AI_REGISTRY_PATH, doc)
    _MEM = symbols


def append_history(entry: dict[str, Any]) -> None:
    AI_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = dict(entry)
    row["ts_utc"] = _now()
    with AI_HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def normalize_industries(raw: list[dict] | None) -> list[dict[str, Any]]:
    """Validate and sort industries by weight."""
    from analytics.industry_taxonomy import load_catalog

    catalog = load_catalog()
    out: list[dict[str, Any]] = []
    for item in raw or []:
        iid = str(item.get("industry_id") or item.get("id") or "").lower().strip()
        if not iid or iid not in catalog:
            continue
        w = float(item.get("weight") or item.get("w") or 0.0)
        if w <= 0:
            continue
        out.append(
            {
                "industry_id": iid,
                "weight": round(min(1.0, w), 4),
                "role": str(item.get("role") or ("primary" if len(out) == 0 else "secondary")),
                "rationale": str(item.get("rationale") or item.get("reason") or "")[:240],
            }
        )
    out.sort(key=lambda x: -x["weight"])
    if out and out[0]["role"] != "primary":
        out[0]["role"] = "primary"
    return out[:5]


def get_symbol_industries(symbol: str) -> list[dict[str, Any]]:
    sym = symbol.strip().upper()
    reg = load_ai_registry()
    row = reg.get(sym)
    if not row:
        return []
    return normalize_industries(row.get("industries"))


def primary_industry_id(symbol: str) -> str | None:
    inds = get_symbol_industries(symbol)
    if inds:
        return str(inds[0]["industry_id"])
    reg = load_ai_registry().get(symbol.strip().upper()) or {}
    pid = reg.get("primary_industry_id")
    return str(pid) if pid else None


def industry_blend_weights(symbol: str) -> dict[str, float]:
    inds = get_symbol_industries(symbol)
    if not inds:
        return {}
    return {str(i["industry_id"]): float(i["weight"]) for i in inds}


def upsert_ai_classification(
    symbol: str,
    *,
    industries: list[dict],
    source: str = "ai",
    confidence: float = 0.0,
    search_evidence: list[str] | None = None,
    model: str = "",
    persist: bool = True,
) -> dict[str, Any]:
    sym = symbol.strip().upper()
    norm = normalize_industries(industries)
    if not norm:
        return {}

    reg = load_ai_registry()
    prev = reg.get(sym) or {}
    row = {
        "symbol": sym,
        "primary_industry_id": norm[0]["industry_id"],
        "industries": norm,
        "confidence": round(float(confidence or norm[0].get("weight", 0.7)), 4),
        "source": source,
        "model": model,
        "search_evidence": (search_evidence or [])[:6],
        "previous_primary": prev.get("primary_industry_id"),
        "classified_at_utc": _now(),
        "version": int(prev.get("version") or 0) + 1,
    }
    reg[sym] = row
    if persist:
        save_ai_registry(reg, meta={"last_symbol": sym, "source": source})
        append_history({"symbol": sym, "row": row, "event": "upsert"})
    return row


def merge_ai_into_industry_row(symbol: str, base_row: dict[str, Any]) -> dict[str, Any]:
    """Attach multi-industry AI metadata to a classification row."""
    sym = symbol.strip().upper()
    ai = load_ai_registry().get(sym)
    if not ai:
        return base_row

    inds = normalize_industries(ai.get("industries"))
    if not inds:
        return base_row

    out = dict(base_row)
    primary = str(inds[0]["industry_id"])
    ai_conf = float(ai.get("confidence") or 0.0)
    base_conf = float(out.get("confidence") or 0.0)

    if ai_conf >= base_conf or out.get("industry_id") in ("unclassified", None, ""):
        out["industry_id"] = primary
        out["confidence"] = max(base_conf, ai_conf)
        out["reasons"] = list(out.get("reasons") or []) + ["ai_primary"]

    out["industries"] = inds
    out["primary_industry_id"] = primary
    out["secondary_industry_ids"] = [i["industry_id"] for i in inds[1:]]
    out["ai_source"] = ai.get("source")
    out["ai_classified_at_utc"] = ai.get("classified_at_utc")
    out["ai_confidence"] = ai_conf
    if ai.get("search_evidence"):
        out["ai_evidence"] = ai.get("search_evidence")
    return out


def emit_ai_override_module(*, min_confidence: float = 0.72) -> Path:
    """Generate Python snippet file with high-confidence AI primary mappings."""
    reg = load_ai_registry()
    lines = [
        '"""Auto-generated from AI weekly industry classifier — do not edit by hand."""',
        "",
        "from __future__ import annotations",
        "",
        "AI_PRIMARY_OVERRIDES: dict[str, str] = {",
    ]
    multi_lines = ["AI_MULTI_INDUSTRIES: dict[str, list[tuple[str, float]]] = {"]
    for sym in sorted(reg.keys()):
        row = reg[sym]
        conf = float(row.get("confidence") or 0.0)
        if conf < min_confidence:
            continue
        inds = normalize_industries(row.get("industries"))
        if not inds:
            continue
        lines.append(f'    "{sym}": "{inds[0]["industry_id"]}",')
        if len(inds) > 1:
            tpl = ", ".join(f'("{i["industry_id"]}", {i["weight"]})' for i in inds)
            multi_lines.append(f'    "{sym}": [{tpl}],')
    lines.append("}")
    multi_lines.append("}")
    AI_CODE_SNIPPETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    AI_CODE_SNIPPETS_PATH.write_text("\n".join(lines + [""] + multi_lines + ["\n"]), encoding="utf-8")
    return AI_CODE_SNIPPETS_PATH


@lru_cache(maxsize=1)
def ai_primary_overrides() -> dict[str, str]:
    try:
        from analytics.industries.ai_generated_overrides import AI_PRIMARY_OVERRIDES

        return {str(k).upper(): str(v) for k, v in AI_PRIMARY_OVERRIDES.items()}
    except Exception:
        reg = load_ai_registry()
        return {
            s: str(r.get("primary_industry_id"))
            for s, r in reg.items()
            if r.get("primary_industry_id") and float(r.get("confidence") or 0) >= 0.72
        }


def symbols_needing_ai_refresh(
    universe: list[str],
    *,
    max_age_days: int | None = None,
    include_unclassified: bool = True,
) -> list[str]:
    """Symbols due for AI re-classification (stale or missing)."""
    from analytics.industries.classifier import classify_ticker

    max_age = max_age_days if max_age_days is not None else int(os.getenv("INDUSTRY_AI_MAX_AGE_DAYS", "7"))
    reg = load_ai_registry()
    now = datetime.now(timezone.utc)
    out: list[str] = []

    for sym in universe:
        s = sym.strip().upper()
        if not s:
            continue
        row = reg.get(s)
        if not row:
            out.append(s)
            continue
        ts = str(row.get("classified_at_utc") or "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            age_days = (now - dt).total_seconds() / 86400.0
        except Exception:
            age_days = 9999.0
        if age_days >= max_age:
            out.append(s)
            continue
        if include_unclassified:
            base = classify_ticker(s, use_cache=True, use_yfinance=False)
            if base.get("industry_id") == "unclassified" and float(row.get("confidence") or 0) < 0.65:
                out.append(s)
    return sorted(set(out))
