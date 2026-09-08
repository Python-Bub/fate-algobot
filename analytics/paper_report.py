"""Shared helpers for valid paper_sim reports (skip empty/stale/unusable writes)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
LATEST_LINK = REPORTS / "paper_sim_latest.json"


def report_age_hours(path: Path) -> float:
    try:
        return (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) / 3600.0
    except OSError:
        return 9999.0


def report_generated_at(doc: dict) -> datetime | None:
    raw = doc.get("generated_at_utc")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def report_age_hours_from_doc(doc: dict, path: Path | None = None) -> float:
    gen = report_generated_at(doc)
    if gen is not None:
        if gen.tzinfo is None:
            gen = gen.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - gen.astimezone(timezone.utc)).total_seconds() / 3600.0
    if path is not None:
        return report_age_hours(path)
    return 9999.0


def is_valid_report(doc: dict, *, min_rows: int = 1) -> bool:
    if not doc:
        return False
    rows = doc.get("rows") or []
    if len(rows) >= min_rows:
        return True
    if int(doc.get("symbols_scored") or 0) >= min_rows:
        return True
    if doc.get("long_picks"):
        return True
    return False


def report_quality_metrics(doc: dict) -> dict[str, int | float]:
    """Coverage stats used to reject partial / junk paper sim runs."""
    rows = doc.get("rows") or []
    tradeable = [r for r in rows if not r.get("skipped") and "score" in r]
    try:
        from fortress_universe import load_top100_symbols

        top_set = frozenset(load_top100_symbols())
    except Exception:
        top_set = frozenset()

    top100 = sum(
        1
        for r in tradeable
        if r.get("top100") or str(r.get("ticker", "")).upper() in top_set
    )
    universe = int(doc.get("universe_size") or 0)
    scored_field = int(doc.get("symbols_scored") or len(tradeable))
    tradeable_n = len(tradeable) if tradeable else scored_field
    coverage = float(tradeable_n) / float(universe) if universe > 0 else 1.0
    return {
        "tradeable": tradeable_n,
        "top100": top100,
        "universe": universe,
        "coverage": round(coverage, 4),
    }


def is_usable_report(doc: dict, *, path: Path | None = None) -> tuple[bool, str]:
    """Family + autopilot need broad top-name coverage — not 50 obscure tickers."""
    if not is_valid_report(doc, min_rows=1):
        return False, "empty"

    m = report_quality_metrics(doc)
    min_tradeable = int(os.getenv("PAPER_REPORT_MIN_TRADEABLE", "100"))
    min_top100 = int(os.getenv("PAPER_REPORT_MIN_TOP100", "50"))
    min_coverage = float(os.getenv("PAPER_REPORT_MIN_COVERAGE", "0.20"))

    tradeable = int(m["tradeable"])
    top100 = int(m["top100"])
    coverage = float(m["coverage"])

    if tradeable < min_tradeable:
        return False, f"tradeable={tradeable}<{min_tradeable}"
    if top100 < min_top100:
        return False, f"top100={top100}<{min_top100}"
    if coverage < min_coverage:
        return False, f"coverage={coverage:.2f}<{min_coverage:.2f}"
    return True, "ok"


def _report_paths_newest_first() -> list[Path]:
    paths = [
        p
        for p in REPORTS.glob("paper_sim_*.json")
        if p.name != "paper_sim_latest.json"
    ]
    scored: list[tuple[float, Path]] = []
    for path in paths:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            scored.append((path.stat().st_mtime, path))
            continue
        gen = report_generated_at(doc)
        ts = gen.timestamp() if gen else path.stat().st_mtime
        scored.append((ts, path))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored]


def _archive_rejected_report(out: dict, reason: str) -> None:
    if os.getenv("PAPER_REPORT_ARCHIVE_REJECTED", "true").lower() not in ("1", "true", "yes"):
        return
    invalid = REPORTS / "invalid"
    invalid.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in reason)[:48]
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = invalid / f"paper_sim_{ts}_{safe}.json"
    payload = {**out, "_reject_reason": reason, "_rejected_at_utc": datetime.now(timezone.utc).isoformat()}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _link_latest_report(path: Path) -> None:
    try:
        if LATEST_LINK.is_symlink() or LATEST_LINK.exists():
            LATEST_LINK.unlink(missing_ok=True)
        LATEST_LINK.symlink_to(path.name)
    except OSError:
        pass


def prune_unusable_paper_reports(*, dry_run: bool = False) -> tuple[int, list[str]]:
    """Delete paper_sim JSON that fails quality gates (partial runs, junk scans)."""
    if not REPORTS.is_dir():
        return 0, []
    removed: list[str] = []
    freed = 0
    for path in _report_paths_newest_first():
        if path.name == "paper_sim_latest.json":
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            if not dry_run:
                try:
                    freed += path.stat().st_size
                    path.unlink(missing_ok=True)
                    removed.append(path.name)
                except OSError:
                    pass
            else:
                removed.append(path.name)
            continue
        ok, reason = is_usable_report(doc, path=path)
        if ok:
            continue
        removed.append(f"{path.name} ({reason})")
        if dry_run:
            continue
        try:
            freed += path.stat().st_size
            path.unlink(missing_ok=True)
        except OSError:
            pass
    return freed, removed


def latest_valid_report(
    *,
    min_rows: int = 1,
    max_age_hours: float | None = None,
    require_usable: bool | None = None,
) -> tuple[Path | None, dict | None]:
    """Newest usable paper_sim JSON with enough scored symbols for family forecast."""
    if not REPORTS.is_dir():
        return None, None
    if max_age_hours is None:
        max_age_hours = float(os.getenv("PAPER_REPORT_MAX_AGE_HOURS", "72"))
    if require_usable is None:
        require_usable = os.getenv("PAPER_REPORT_REQUIRE_USABLE", "true").lower() in (
            "1",
            "true",
            "yes",
        )

    prune_on_read = os.getenv("PAPER_REPORT_PRUNE_UNUSABLE", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    if prune_on_read:
        prune_unusable_paper_reports(dry_run=False)

    for path in _report_paths_newest_first():
        if path.name == "paper_sim_latest.json":
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        age = report_age_hours_from_doc(doc, path)
        if max_age_hours > 0 and age > max_age_hours:
            continue
        if not is_valid_report(doc, min_rows=min_rows):
            continue
        if require_usable:
            ok, _ = is_usable_report(doc, path=path)
            if not ok:
                continue
        return path, doc
    return None, None


def write_report_if_valid(out: dict, *, min_scored: int | None = None) -> Path | None:
    """Write daily report only when it has usable scores (never clobber with empty/partial)."""
    min_scored = int(min_scored if min_scored is not None else os.getenv("PAPER_SIM_MIN_SCORED", "5"))
    scored = int(out.get("symbols_scored") or 0)
    rows = len(out.get("rows") or [])
    metrics = report_quality_metrics(out)
    out["report_quality"] = metrics

    if scored < min_scored and rows < min_scored:
        prev_path, prev = latest_valid_report(min_rows=1, require_usable=False)
        _archive_rejected_report(out, f"too_few_scored_{scored}")
        if prev_path:
            from utils import log

            log.warning(
                "[PAPER_SIM] skip write — scored=%d rows=%d (keeping %s)",
                scored,
                rows,
                prev_path.name,
            )
        return None

    ok, reason = is_usable_report(out)
    if not ok:
        prev_path, _ = latest_valid_report(min_rows=1, require_usable=False)
        _archive_rejected_report(out, reason)
        from utils import log

        log.warning(
            "[PAPER_SIM] skip write — unusable report (%s) scored=%d top100=%d (keeping %s)",
            reason,
            scored,
            int(metrics.get("top100", 0)),
            prev_path.name if prev_path else "none",
        )
        return None

    REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fn = REPORTS / f"paper_sim_{ts}.json"
    tmp = fn.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, indent=2), encoding="utf-8")
    import os as _os

    _os.replace(tmp, fn)
    _link_latest_report(fn)
    _prune_old_reports_keep_n()
    return fn


def _prune_old_reports_keep_n() -> None:
    keep_n = int(os.getenv("PAPER_SIM_REPORTS_KEEP", "3"))
    if keep_n <= 0:
        return
    usable: list[tuple[float, Path]] = []
    for path in _report_paths_newest_first():
        if path.name == "paper_sim_latest.json":
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            ok, _ = is_usable_report(doc, path=path)
            if not ok:
                continue
            gen = report_generated_at(doc)
            ts = gen.timestamp() if gen else path.stat().st_mtime
            usable.append((ts, path))
        except Exception:
            continue
    usable.sort(key=lambda x: x[0], reverse=True)
    for _, path in usable[keep_n:]:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
