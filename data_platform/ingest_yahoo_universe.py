"""Yahoo full-universe ingestion with checkpoints and quality quarantine."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from data_platform.data_quality import audit_ohlcv
from data_platform.replay_store import save_raw, write_snapshot_meta
from data_platform.symbol_registry import build_registry, save_registry, filter_tradable
from data_store import merge_and_save
from universe_provider import load_universe_symbols
from utils import log

CHECKPOINT_PATH = Path(os.getenv("DATA_SYNC_CHECKPOINT", "data/universe/data_sync_checkpoint.json"))
REPORT_PATH = Path(os.getenv("DATA_SYNC_REPORT", "data/universe/data_sync_report.json"))
QUARANTINE_PATH = Path(os.getenv("DATA_SYNC_QUARANTINE", "data/universe/quarantine_symbols.json"))


@dataclass
class SyncStats:
    universe_size: int = 0
    pending: int = 0
    fetched_ok: int = 0
    quarantined: int = 0
    failed: int = 0
    skipped_done: int = 0
    started_at: str = ""
    ended_at: str = ""


def _load_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def _fetch_yahoo_symbol(symbol: str, start: str, end: str) -> pd.DataFrame:
    from data_platform.market_prices import fetch_daily

    df = fetch_daily(symbol, start, end)
    if df is not None and not df.empty:
        return df
    from multi_source_data import fetch_yahoo

    return fetch_yahoo(symbol, start, end)
    return pd.DataFrame()


def _incremental_start(df_old: pd.DataFrame | None, default_start: str) -> str:
    if df_old is None or df_old.empty:
        return default_start
    idx = pd.to_datetime(df_old.index)
    if len(idx) == 0:
        return default_start
    last = idx.max()
    return (last - pd.Timedelta(days=14)).strftime("%Y-%m-%d")


def sync_universe(
    mode: str = "incremental",
    max_symbols: int | None = None,
    rebuild_registry: bool = True,
) -> dict:
    full = mode.lower() == "full"
    syms = load_universe_symbols(refresh=False)
    if max_symbols is not None:
        syms = syms[: int(max_symbols)]

    if rebuild_registry:
        reg = build_registry(syms)
        save_registry(reg)
        syms = filter_tradable(syms, reg)
        log.info("[DATA_SYNC] Tradable symbols after registry filter: %d", len(syms))

    ck = _load_json(CHECKPOINT_PATH, {"done": {}, "failed": {}, "quarantine": {}})
    done = dict(ck.get("done", {}))
    failed = dict(ck.get("failed", {}))
    quarantine = dict(ck.get("quarantine", {}))
    if os.getenv("DATA_SYNC_RESET_FAILED", "false").lower() in ("1", "true", "yes"):
        failed = {}
    if os.getenv("DATA_SYNC_RESET_DONE", "false").lower() in ("1", "true", "yes"):
        done = {}

    stats = SyncStats(
        universe_size=len(syms),
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    end = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d")
    default_start = os.getenv("DATA_SYNC_START", "2000-01-01")
    pending = [s for s in syms if full or s not in done]
    stats.pending = len(pending)

    for i, s in enumerate(pending, 1):
        try:
            cached = None if full else _load_cached_for_sync(s)
            start = default_start if full else _incremental_start(cached, default_start)
            df = _fetch_yahoo_symbol(s, start, end)
            if df is None or df.empty:
                failed[s] = "empty_data"
                stats.failed += 1
                _persist_checkpoint(done, failed, quarantine)
                continue

            qa = audit_ohlcv(df)
            if not qa["ok"]:
                quarantine[s] = qa
                stats.quarantined += 1
                _persist_checkpoint(done, failed, quarantine)
                continue

            merge_and_save(s, df)
            try:
                from data_platform.network_data import save_replay_raw

                if save_replay_raw():
                    save_raw(s, df)
            except ImportError:
                pass
            done[s] = datetime.now(timezone.utc).isoformat()
            failed.pop(s, None)
            quarantine.pop(s, None)
            stats.fetched_ok += 1
            if i % 100 == 0:
                log.info(
                    "[DATA_SYNC] %d/%d ok=%d failed=%d quarantine=%d",
                    i, len(pending), stats.fetched_ok, stats.failed, stats.quarantined
                )
            _persist_checkpoint(done, failed, quarantine)
        except Exception as e:
            failed[s] = f"{type(e).__name__}: {str(e)[:160]}"
            stats.failed += 1
            _persist_checkpoint(done, failed, quarantine)

    stats.skipped_done = max(0, len(syms) - len(pending))
    stats.ended_at = datetime.now(timezone.utc).isoformat()
    rep = asdict(stats)
    rep["checkpoint"] = str(CHECKPOINT_PATH)
    rep["quarantine_path"] = str(QUARANTINE_PATH)
    rep["quarantine_count"] = len(quarantine)
    rep["failed_count"] = len(failed)
    rep["done_count"] = len(done)

    _save_json(REPORT_PATH, rep)
    _save_json(QUARANTINE_PATH, quarantine)
    write_snapshot_meta("data_sync_latest", rep)
    return rep


def _load_cached_for_sync(symbol: str) -> pd.DataFrame | None:
    try:
        from data_store import load_cached_ohlcv

        return load_cached_ohlcv(symbol)
    except Exception:
        return None


def _persist_checkpoint(done: dict, failed: dict, quarantine: dict) -> None:
    _save_json(CHECKPOINT_PATH, {"done": done, "failed": failed, "quarantine": quarantine})


def audit_existing_cache(max_symbols: int | None = None) -> dict:
    from data_store import load_cached_ohlcv

    syms = load_universe_symbols(refresh=False)
    if max_symbols is not None:
        syms = syms[: int(max_symbols)]
    issues: dict[str, dict] = {}
    ok = 0
    for s in syms:
        try:
            d = load_cached_ohlcv(s)
            if d is None or d.empty:
                issues[s] = {"ok": False, "reason": "no_cache"}
                continue
            qa = audit_ohlcv(d)
            if qa["ok"]:
                ok += 1
            else:
                issues[s] = qa
        except Exception as e:
            issues[s] = {"ok": False, "reason": f"{type(e).__name__}: {e}"}
    rep = {
        "symbols_checked": len(syms),
        "ok": ok,
        "issues": issues,
        "issue_count": len(issues),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    _save_json(REPORT_PATH, rep)
    return rep

