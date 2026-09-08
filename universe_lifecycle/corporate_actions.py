"""Corporate actions: ticker renames, mergers, delistings, splits — registry + migration."""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from universe_lifecycle.paths import CORPORATE_ACTIONS_PATH, ROOT

# Seed known renames / mergers (auto-detected events append here).
_DEFAULT_REGISTRY: dict[str, Any] = {
    "version": 1,
    "updated_at_utc": None,
    "aliases": {
        "SQ": "XYZ",
        "FB": "META",
        "FISV": "FI",
        "DWAC": "DJT",
    },
    "events": [
        {
            "kind": "rename",
            "old": "SQ",
            "new": "XYZ",
            "note": "Block Inc (formerly Square)",
            "source": "seed",
        },
        {
            "kind": "rename",
            "old": "FB",
            "new": "META",
            "note": "Meta Platforms rebrand",
            "source": "seed",
        },
    ],
    "delisted": [],
    "pending_migrations": [],
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_registry(path: Path | None = None) -> dict:
    p = path or CORPORATE_ACTIONS_PATH
    if not p.is_file():
        return json.loads(json.dumps(_DEFAULT_REGISTRY))
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return json.loads(json.dumps(_DEFAULT_REGISTRY))
    if not doc.get("aliases"):
        doc["aliases"] = {}
    if not doc.get("events"):
        doc["events"] = []
    if not doc.get("delisted"):
        doc["delisted"] = []
    if not doc.get("pending_migrations"):
        doc["pending_migrations"] = []
    return doc


def save_registry(doc: dict, path: Path | None = None) -> None:
    p = path or CORPORATE_ACTIONS_PATH
    doc = dict(doc)
    doc["updated_at_utc"] = _now()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def alias_map(registry: dict | None = None) -> dict[str, str]:
    """old listing → current listing. Spinoffs do *not* consume the parent ticker."""
    reg = registry or load_registry()
    out = {str(k).upper(): str(v).upper() for k, v in (reg.get("aliases") or {}).items()}
    for ev in reg.get("events") or []:
        kind = str(ev.get("kind") or "")
        old = str(ev.get("old") or "").upper()
        new = str(ev.get("new") or "").upper()
        if not old:
            continue
        if kind == "rename" and new:
            out[old] = new
        # Mergers and spinoffs never consume the surviving listing's ticker.
    return out


def canonical_symbol(ticker: str, registry: dict | None = None) -> str:
    t = ticker.strip().upper()
    mapping = alias_map(registry)
    seen: set[str] = set()
    while t in mapping and t not in seen:
        seen.add(t)
        t = mapping[t]
    return t


def reverse_alias_map(registry: dict | None = None) -> dict[str, list[str]]:
    """Current listing → former tickers (FB under META, SQ under XYZ)."""
    reg = registry or load_registry()
    rev: dict[str, list[str]] = {}
    for old, new in alias_map(reg).items():
        if not old or not new or old == new:
            continue
        canon = canonical_symbol(new, reg)
        bucket = rev.setdefault(canon, [])
        if old not in bucket and old != canon:
            bucket.append(old)
    return rev


def former_tickers(ticker: str, registry: dict | None = None) -> list[str]:
    reg = registry or load_registry()
    return list(reverse_alias_map(reg).get(canonical_symbol(ticker, reg), []))


def spinoff_children(ticker: str, registry: dict | None = None) -> list[str]:
    reg = registry or load_registry()
    t = canonical_symbol(ticker, reg)
    out: list[str] = []
    for ev in reg.get("events") or []:
        if str(ev.get("kind") or "") != "spinoff":
            continue
        if str(ev.get("old") or "").upper() != t:
            continue
        child = str(ev.get("new") or "").upper()
        if child and child not in out:
            out.append(child)
    return out


def spinoff_parent(ticker: str, registry: dict | None = None) -> str | None:
    reg = registry or load_registry()
    t = str(ticker or "").strip().upper()
    if not t:
        return None
    for ev in reg.get("events") or []:
        if str(ev.get("kind") or "") != "spinoff":
            continue
        if str(ev.get("new") or "").upper() == t:
            parent = str(ev.get("old") or "").upper()
            return parent or None
    return None


def acquired_into(ticker: str, registry: dict | None = None) -> str | None:
    """Stock-deal acquirer ticker, if recorded. Cash deals have no surviving listing."""
    reg = registry or load_registry()
    t = str(ticker or "").strip().upper()
    for ev in reg.get("events") or []:
        if str(ev.get("kind") or "") != "merge":
            continue
        if str(ev.get("old") or "").upper() != t:
            continue
        new = str(ev.get("new") or "").upper()
        return new or None
    return None


def is_dead_money(ticker: str, registry: dict | None = None) -> bool:
    """True when the listing is gone (cash takeout, delist) and should not be bought."""
    reg = registry or load_registry()
    t = str(ticker or "").strip().upper()
    if not t:
        return False
    for row in reg.get("delisted") or []:
        if isinstance(row, dict) and str(row.get("symbol") or "").upper() == t:
            return True
        if isinstance(row, str) and row.strip().upper() == t:
            return True
    for ev in reg.get("events") or []:
        if str(ev.get("old") or "").upper() != t:
            continue
        kind = str(ev.get("kind") or "")
        new = str(ev.get("new") or "").strip()
        if kind == "delist":
            return True
        if kind == "merge" and not new:
            return True
    return False


def history_symbols(ticker: str, registry: dict | None = None) -> list[str]:
    """Same economic price series: current listing + former names + dual-class siblings."""
    from symbol_aliases import issuer_siblings, price_feed_symbol

    reg = registry or load_registry()
    logical = str(ticker or "").strip().upper()
    if not logical:
        return []
    canon = canonical_symbol(logical, reg)
    out: list[str] = []
    for raw in (logical, canon, price_feed_symbol(logical), *former_tickers(logical, reg)):
        s = str(raw or "").strip().upper()
        if s and s not in out:
            out.append(s)
    try:
        for sib in issuer_siblings(logical):
            s = str(sib or "").strip().upper()
            if s and s not in out:
                out.append(s)
    except Exception:
        pass
    return out


def related_symbols(ticker: str, registry: dict | None = None) -> list[str]:
    """News/memory graph: history plus spinoff parent/child and acquirer (not price-stitched)."""
    reg = registry or load_registry()
    out = list(history_symbols(ticker, reg))
    for child in spinoff_children(ticker, reg):
        if child not in out:
            out.append(child)
    parent = spinoff_parent(ticker, reg)
    if parent and parent not in out:
        out.append(parent)
    acq = acquired_into(ticker, reg)
    if acq and acq not in out:
        out.append(acq)
    return out


def lineage(ticker: str, registry: dict | None = None) -> dict[str, Any]:
    """Operator-readable identity card: old names, spinoffs, takeouts."""
    reg = registry or load_registry()
    t = str(ticker or "").strip().upper()
    canon = canonical_symbol(t, reg) if t else ""
    former = former_tickers(t, reg) if t else []
    children = spinoff_children(t, reg) if t else []
    parent = spinoff_parent(t, reg) if t else None
    acq = acquired_into(t, reg) if t else None
    dead = is_dead_money(t, reg) if t else False
    notes: list[str] = []
    for ev in reg.get("events") or []:
        old = str(ev.get("old") or "").upper()
        new = str(ev.get("new") or "").upper()
        if t not in {old, new, canon} and canon not in {old, new}:
            continue
        kind = str(ev.get("kind") or "")
        note = str(ev.get("note") or "").strip()
        if kind == "rename" and old and new:
            notes.append(f"{old} renamed to {new}" + (f" — {note}" if note else ""))
        elif kind == "spinoff" and old and new:
            notes.append(f"{new} spun off from {old}" + (f" — {note}" if note else ""))
        elif kind == "merge":
            if new:
                notes.append(f"{old} acquired into {new}" + (f" — {note}" if note else ""))
            else:
                notes.append(f"{old} cash takeout / listing ended" + (f" — {note}" if note else ""))
        elif kind == "share_class" and old and new:
            notes.append(f"{old}/{new} dual class" + (f" — {note}" if note else ""))
        elif kind == "delist":
            notes.append(f"{old} delisted" + (f" — {note}" if note else ""))
        elif kind == "split" and old:
            notes.append(f"{old} split {note}".strip())
    # unique preserve order
    seen_n: set[str] = set()
    uniq_notes: list[str] = []
    for n in notes:
        if n not in seen_n:
            seen_n.add(n)
            uniq_notes.append(n)
    summary = "; ".join(uniq_notes[:8]) if uniq_notes else (
        f"{canon} current listing" if canon else ""
    )
    return {
        "input": t,
        "canonical": canon,
        "former_tickers": former,
        "history_symbols": history_symbols(t, reg) if t else [],
        "related_symbols": related_symbols(t, reg) if t else [],
        "spinoff_children": children,
        "spinoff_parent": parent,
        "acquired_into": acq,
        "dead_money": dead,
        "summary": summary,
        "notes": uniq_notes[:12],
    }


def register_event(
    *,
    kind: str,
    old: str | None = None,
    new: str | None = None,
    note: str = "",
    source: str = "auto",
    retrain: bool = True,
) -> dict:
    reg = load_registry()
    ev = {
        "kind": kind,
        "old": (old or "").upper() or None,
        "new": (new or "").upper() or None,
        "note": note,
        "source": source,
        "detected_at_utc": _now(),
        "retrain": retrain,
    }
    reg.setdefault("events", []).append(ev)
    reg["events"] = reg["events"][-500:]

    if kind == "rename" and old and new:
        # Same company, new ticker — stitch history and move artifacts.
        reg.setdefault("aliases", {})[old.upper()] = new.upper()
        pending = {m.get("old") for m in reg.get("pending_migrations", [])}
        if old.upper() not in pending:
            reg.setdefault("pending_migrations", []).append(
                {"old": old.upper(), "new": new.upper(), "kind": kind, "retrain": retrain}
            )
    elif kind == "merge" and old and new:
        # Stock deal: target ticker dies. Do *not* alias prices onto the acquirer
        # (ATVI bars are not MSFT). Memory + news related_symbols still link them.
        pending = {(m.get("old"), m.get("kind")) for m in reg.get("pending_migrations", [])}
        if (old.upper(), "merge") not in pending:
            reg.setdefault("pending_migrations", []).append(
                {
                    "old": old.upper(),
                    "new": new.upper(),
                    "kind": "merge",
                    "retrain": bool(retrain),
                    "archive": True,
                }
            )
    elif kind == "spinoff" and old and new:
        # Parent keeps trading. Child is a new listing — never alias the parent away.
        pending = {m.get("new") for m in reg.get("pending_migrations", []) if m.get("kind") == "spinoff"}
        if new.upper() not in pending:
            reg.setdefault("pending_migrations", []).append(
                {"old": old.upper(), "new": new.upper(), "kind": "spinoff", "retrain": retrain}
            )
    elif old and (kind == "delist" or (kind == "merge" and not new)):
        reg.setdefault("delisted", []).append(
            {"symbol": old.upper(), "note": note, "detected_at_utc": _now()}
        )
        reg["delisted"] = reg["delisted"][-500:]
        pending = {m.get("old") for m in reg.get("pending_migrations", [])}
        if old.upper() not in pending:
            reg.setdefault("pending_migrations", []).append(
                {"old": old.upper(), "new": "", "kind": "delist", "retrain": False, "archive": True}
            )

    save_registry(reg)
    if source != "test":
        try:
            from intel.algo_memory import remember_corporate_event

            remember_corporate_event(ev)
        except Exception:
            pass
    return ev


def _model_artifacts(sym: str) -> list[Path]:
    model_dir = Path(os.getenv("MODEL_DIR", "models"))
    intra_dir = Path(os.getenv("INTRADAY_MODEL_DIR", "models/intraday"))
    lstm_dir = Path(os.getenv("LSTM_MODEL_DIR", "models/lstm"))
    cache_dir = Path(os.getenv("PRICE_CACHE_DIR", "data/cache/prices"))
    sym = sym.upper()
    paths: list[Path] = [
        model_dir / f"{sym}_model.pkl",
        model_dir / "meta" / f"{sym}_meta.pkl",
        intra_dir / f"{sym}_intraday.pkl",
        lstm_dir / f"{sym}_lstm.pt",
        cache_dir / f"{sym}.parquet",
        cache_dir / f"{sym}.csv",
        ROOT / "data" / "cache" / "prices" / f"{sym}.parquet",
        ROOT / "data" / "cache" / "prices" / f"{sym}.csv",
    ]
    return [p for p in paths if p.is_file()]


def _rename_artifact(src: Path, dst: Path) -> bool:
    if not src.is_file() or dst.is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return True


def migrate_symbol_artifacts(old: str, new: str, *, archive_delisted: bool = False) -> dict:
    """Move model/cache files old→new, or archive when delisted (old with no new)."""
    old_u, new_u = old.upper(), new.upper()
    moved: list[str] = []
    archived: list[str] = []
    artifacts = _model_artifacts(old_u)

    if new_u and old_u != new_u:
        for src in artifacts:
            name = src.name.replace(old_u, new_u, 1)
            dst = src.parent / name
            if _rename_artifact(src, dst):
                moved.append(str(dst))
        _patch_checkpoints(old_u, new_u)
    elif archive_delisted:
        archive_dir = ROOT / "data" / "archive" / "delisted"
        archive_dir.mkdir(parents=True, exist_ok=True)
        for src in artifacts:
            dst = archive_dir / src.name
            if src.is_file() and not dst.is_file():
                shutil.move(str(src), str(dst))
                archived.append(str(dst))
        _patch_checkpoints(old_u, old_u)

    return {"old": old_u, "new": new_u, "moved": moved, "archived": archived}


def _patch_checkpoints(old: str, new: str) -> None:
    for rel in (
        "data/train_checkpoint.json",
        "data/intraday_train_checkpoint.json",
        "data/lstm_train_checkpoint.json",
    ):
        p = ROOT / rel
        if not p.is_file():
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        done = doc.get("done") or []
        doc["done"] = sorted({new if x.upper() == old else x for x in done})
        failed = dict(doc.get("failed") or {})
        if old in failed or old.upper() in {k.upper() for k in failed}:
            val = failed.pop(old, failed.pop(old.upper(), None))
            if val is not None:
                failed[new] = val
        doc["failed"] = failed
        p.write_text(json.dumps(doc, indent=0), encoding="utf-8")


def apply_pending_migrations(registry: dict | None = None) -> list[dict]:
    reg = registry or load_registry()
    results: list[dict] = []
    remaining: list[dict] = []
    for item in reg.get("pending_migrations") or []:
        old = str(item.get("old", "")).upper()
        new = str(item.get("new", "")).upper()
        kind = str(item.get("kind", "rename"))
        if not old:
            continue
        try:
            if kind == "spinoff":
                # Keep parent models; queue the child for training via retrain=True.
                res = {
                    "old": old,
                    "new": new,
                    "moved": [],
                    "archived": [],
                    "retrain": bool(item.get("retrain", True)),
                    "kind": kind,
                }
            elif kind == "merge" and new:
                # Archive the target listing; do not overwrite acquirer artifacts.
                res = migrate_symbol_artifacts(old, "", archive_delisted=True)
                res["retrain"] = bool(item.get("retrain", True))
                res["kind"] = kind
                res["acquired_into"] = new
            elif kind == "delist" or not new:
                res = migrate_symbol_artifacts(old, "", archive_delisted=True)
                res["retrain"] = bool(item.get("retrain", True))
                res["kind"] = kind
            elif old == new:
                continue
            else:
                res = migrate_symbol_artifacts(old, new)
                res["retrain"] = bool(item.get("retrain", True))
                res["kind"] = kind
            results.append(res)
        except Exception as e:
            remaining.append({**item, "error": str(e)[:200]})
    reg["pending_migrations"] = remaining
    save_registry(reg)
    _sync_symbol_aliases_file()
    if results and os.getenv("CLEANER_ON_CORPORATE", "true").lower() in ("1", "true", "yes"):
        try:
            import sys
            from pathlib import Path

            root = Path(__file__).resolve().parents[1]
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            from tools.change_cleaner import run_builtin_cleaner

            orphans = [r.get("old") for r in results if r.get("old")]
            run_builtin_cleaner(reason="corporate_migration", extra_orphans=orphans)
        except Exception:
            pass
    return results


def _sync_symbol_aliases_file() -> None:
    """Push alias map into symbol_aliases module at runtime."""
    try:
        from symbol_aliases import reload_aliases_from_registry

        reload_aliases_from_registry()
    except Exception:
        pass


def _yf_ticker_alive(sym: str) -> tuple[bool, dict]:
    try:
        import yfinance as yf

        tk = yf.Ticker(sym)
        info = tk.info or {}
        hist = tk.history(period="5d", auto_adjust=True)
        if hist is not None and not hist.empty:
            return True, info
        q = str(info.get("quoteType") or "").lower()
        if q in ("equity", "etf") and info.get("regularMarketPrice"):
            return True, info
        return False, info
    except Exception:
        return False, {}


def _detect_rename_candidate(old: str, info: dict) -> str | None:
    for key in ("symbol", "previousSymbol", "underlyingSymbol"):
        cand = str(info.get(key) or "").upper()
        if cand and cand != old and 1 < len(cand) <= 6:
            return cand
    return None


def _recent_splits(symbols: list[str], lookback_days: int = 35) -> list[dict]:
    out: list[dict] = []
    if not symbols:
        return out
    try:
        import yfinance as yf
    except ImportError:
        return out

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    batch = 25
    for i in range(0, len(symbols), batch):
        chunk = symbols[i : i + batch]
        for sym in chunk:
            try:
                splits = yf.Ticker(sym).splits
                if splits is None or splits.empty:
                    continue
                idx = splits.index
                if getattr(idx, "tz", None) is not None:
                    idx = idx.tz_convert("UTC").tz_localize(None)
                recent = splits[idx >= cutoff.replace(tzinfo=None)]
                if recent.empty:
                    continue
                out.append(
                    {
                        "symbol": sym.upper(),
                        "kind": "split",
                        "splits": {str(k.date()): float(v) for k, v in recent.items()},
                        "retrain": True,
                    }
                )
            except Exception:
                continue
    return out


def detect_corporate_events(
    *,
    removed_symbols: list[str] | None = None,
    model_symbols: list[str] | None = None,
    split_scan_symbols: list[str] | None = None,
    split_lookback_days: int = 35,
) -> dict[str, Any]:
    """Scan delisted/renamed symbols and recent splits; update registry."""
    reg = load_registry()
    detected: dict[str, Any] = {
        "renames": [],
        "delistings": [],
        "splits": [],
        "migrations_applied": [],
    }

    removed = [s.upper() for s in (removed_symbols or []) if s]
    models = [s.upper() for s in (model_symbols or []) if s]
    removed_cap = int(os.getenv("CORPORATE_REMOVED_SCAN_CAP", "40"))
    if removed_cap > 0:
        removed = removed[:removed_cap]

    fast = os.getenv("UNIVERSE_CORPORATE_FAST", "false").lower() in ("1", "true", "yes")
    if fast:
        detected["migrations_applied"] = apply_pending_migrations(reg)
        return detected

    for old in removed:
        alive, info = _yf_ticker_alive(old)
        if alive:
            new = _detect_rename_candidate(old, info)
            if new and new != old:
                ev = register_event(kind="rename", old=old, new=new, note="auto: still tradable under new ticker", source="auto")
                detected["renames"].append(ev)
                continue
        if old in models or _model_artifacts(old):
            ev = register_event(kind="delist", old=old, note="auto: removed from exchange universe", source="auto", retrain=False)
            detected["delistings"].append(ev)

    split_syms = list(split_scan_symbols or models[:200])
    cap = int(os.getenv("CORPORATE_SPLIT_SCAN_CAP", "200"))
    if cap > 0:
        split_syms = split_syms[:cap]
    for item in _recent_splits(split_syms, split_lookback_days):
        sym = item["symbol"]
        already = any(
            e.get("kind") == "split" and e.get("old") == sym
            and (datetime.now(timezone.utc) - datetime.fromisoformat(e.get("detected_at_utc", "1970-01-01").replace("Z", "+00:00"))).days < 7
            for e in reg.get("events", [])
        )
        if not already:
            register_event(kind="split", old=sym, note=json.dumps(item.get("splits", {})), source="auto", retrain=True)
        detected["splits"].append(item)

    detected["migrations_applied"] = apply_pending_migrations(reg)

    try:
        from analytics.industries.classifier import apply_corporate_events_to_industry_map

        lifecycle_rows = apply_corporate_events_to_industry_map()
        if lifecycle_rows:
            detected["industry_lifecycle"] = lifecycle_rows
    except Exception:
        pass

    return detected
