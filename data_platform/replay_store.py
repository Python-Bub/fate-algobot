"""Replay store contracts for deterministic offline retraining and audits."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

import pandas as pd

from utils import log

ROOT = Path(os.getenv("REPLAY_ROOT", "data/replay"))
RAW_DIR = ROOT / "raw"
FEAT_DIR = ROOT / "features"
NEWS_DIR = ROOT / "news"
TRANS_DIR = ROOT / "transcripts"
META_DIR = ROOT / "meta"


def _ensure_dirs() -> None:
    for d in (RAW_DIR, FEAT_DIR, NEWS_DIR, TRANS_DIR, META_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _safe_sym(symbol: str) -> str:
    return symbol.strip().upper().replace("/", "_")


def _write_df(df: pd.DataFrame, path_base: Path) -> Path:
    """Write dataframe as parquet when possible, else CSV fallback."""
    if df is None:
        raise ValueError("df is None")
    try:
        p = path_base.with_suffix(".parquet")
        df.to_parquet(p)
        return p
    except Exception:
        p = path_base.with_suffix(".csv")
        df.to_csv(p)
        return p


def _read_df(path_base: Path) -> pd.DataFrame:
    p_parq = path_base.with_suffix(".parquet")
    if p_parq.is_file():
        return pd.read_parquet(p_parq)
    p_csv = path_base.with_suffix(".csv")
    if p_csv.is_file():
        return pd.read_csv(p_csv, index_col=0, parse_dates=True)
    return pd.DataFrame()


def save_raw(symbol: str, df: pd.DataFrame) -> Path:
    _ensure_dirs()
    sym = _safe_sym(symbol)
    path = _write_df(df, RAW_DIR / sym)
    return path


def load_raw(symbol: str) -> pd.DataFrame:
    _ensure_dirs()
    return _read_df(RAW_DIR / _safe_sym(symbol))


def save_features(symbol: str, df: pd.DataFrame) -> Path:
    _ensure_dirs()
    return _write_df(df, FEAT_DIR / _safe_sym(symbol))


def load_features(symbol: str) -> pd.DataFrame:
    _ensure_dirs()
    return _read_df(FEAT_DIR / _safe_sym(symbol))


def save_news(symbol: str, records: Iterable[dict]) -> Path:
    _ensure_dirs()
    p = NEWS_DIR / f"{_safe_sym(symbol)}.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=True) + "\n")
    return p


def save_transcripts(symbol: str, records: Iterable[dict]) -> Path:
    _ensure_dirs()
    p = TRANS_DIR / f"{_safe_sym(symbol)}.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=True) + "\n")
    return p


def write_snapshot_meta(name: str, payload: dict) -> Path:
    _ensure_dirs()
    p = META_DIR / f"{name}.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    return p


def list_replay_symbols(kind: str = "raw") -> list[str]:
    _ensure_dirs()
    mp = {
        "raw": RAW_DIR,
        "features": FEAT_DIR,
        "news": NEWS_DIR,
        "transcripts": TRANS_DIR,
    }
    d = mp.get(kind, RAW_DIR)
    out: set[str] = set()
    for p in d.glob("*"):
        out.add(p.stem.upper().replace("_", "/"))
    return sorted(out)


def replay_health_report() -> dict:
    _ensure_dirs()
    rep = {
        "raw_symbols": len(list_replay_symbols("raw")),
        "feature_symbols": len(list_replay_symbols("features")),
        "news_symbols": len(list_replay_symbols("news")),
        "transcript_symbols": len(list_replay_symbols("transcripts")),
    }
    rep["ok"] = rep["raw_symbols"] > 0
    return rep


def prune_replay(max_age_days: int = 1800) -> int:
    """Simple retention: delete files older than max_age_days."""
    _ensure_dirs()
    import time

    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for d in (RAW_DIR, FEAT_DIR, NEWS_DIR, TRANS_DIR, META_DIR):
        for p in d.glob("*"):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink(missing_ok=True)
                    removed += 1
            except Exception as e:
                log.warning("[REPLAY] prune failed %s: %s", p, e)
    return removed

