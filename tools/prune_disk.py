#!/usr/bin/env python3
"""Free disk space: old logs, caches, Cursor terminal dumps. Never deletes models/."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
LOGDIR = ROOT / "logs"
CURSOR_TERMINALS = Path.home() / ".cursor/projects/Users-demirgenc-FATE-AlgoBot/terminals"


def _bytes(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _rm(path: Path, dry: bool) -> int:
    if not path.exists():
        return 0
    n = _bytes(path)
    if dry:
        return n
    if path.is_file() or path.is_symlink():
        path.unlink(missing_ok=True)
    else:
        shutil.rmtree(path, ignore_errors=True)
    return n


def _open_log_paths() -> set[Path]:
    """Log files still held open by running daemons (unlink-safe skip)."""
    open_paths: set[Path] = set()
    try:
        out = subprocess.check_output(
            ["lsof", "+D", str(LOGDIR)],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=8,
        )
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return open_paths
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 9:
            continue
        name = parts[-1]
        if name.endswith(".log"):
            try:
                open_paths.add(Path(name).resolve())
            except OSError:
                pass
    return open_paths


def prune_hft_jsonl(dry: bool) -> int:
    """Drop old HFT day jsonl under logs/ and hft/logs/ (refetchable telemetry)."""
    from datetime import date, datetime, timedelta

    keep_days = max(1, int(os.getenv("HFT_JSONL_KEEP_DAYS", "2")))
    cutoff = date.today() - timedelta(days=keep_days - 1)
    freed = 0
    for logdir in (LOGDIR, ROOT / "hft" / "logs"):
        if not logdir.is_dir():
            continue
        for p in logdir.glob("hft-*.jsonl"):
            # hft-YYYY-MM-DD.jsonl
            try:
                day = datetime.strptime(p.stem.removeprefix("hft-"), "%Y-%m-%d").date()
            except ValueError:
                continue
            if day < cutoff:
                freed += _rm(p, dry)
    return freed


def prune_logs(dry: bool) -> int:
    freed = 0
    if not LOGDIR.is_dir():
        return 0
    keep: set[Path] = set()
    keep.update(_open_log_paths())
    for latest in LOGDIR.glob("*_latest.log"):
        if latest.is_symlink():
            try:
                target = latest.resolve()
                if target.is_file():
                    keep.add(target)
            except OSError:
                pass
        elif latest.is_file():
            keep.add(latest.resolve())
    for p in LOGDIR.glob("*.log"):
        if p.name.endswith("_latest.log"):
            continue
        if p.resolve() in keep:
            continue
        freed += _rm(p, dry)
    for p in LOGDIR.glob("*.log.*"):
        freed += _rm(p, dry)
    freed += prune_hft_jsonl(dry)
    return freed


def prune_legacy_root_csv(dry: bool) -> int:
    """Old ``data/TICKER.csv`` samples — training uses Yahoo/Alpaca via feature_engineering."""
    freed = 0
    data = ROOT / "data"
    if not data.is_dir():
        return 0
    for p in data.glob("*.csv"):
        if p.name.lower() in ("trades.csv",):
            continue
        freed += _rm(p, dry)
    return freed


def prune_replay_all(dry: bool) -> int:
    """Replay parquet/raw duplicates — refetch via Yahoo + SAVE_REPLAY_FEATURES=false."""
    freed = 0
    replay = ROOT / "data" / "replay"
    if not replay.is_dir():
        return 0
    for sub in ("features", "raw", "news", "meta"):
        d = replay / sub
        if d.is_dir():
            for child in d.iterdir():
                freed += _rm(child, dry)
    return freed


def prune_bak_and_ds_store(dry: bool) -> int:
    freed = 0
    for p in ROOT.rglob("*.bak"):
        if "venv" in p.parts or "models" in p.parts:
            continue
        freed += _rm(p, dry)
    for p in ROOT.rglob(".DS_Store"):
        if "venv" in p.parts:
            continue
        freed += _rm(p, dry)
    return freed


def trim_jsonl_tail(path: Path, max_lines: int, dry: bool) -> int:
    if not path.is_file() or max_lines <= 0:
        return 0
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return 0
    if len(lines) <= max_lines:
        return 0
    drop = len(lines) - max_lines
    if dry:
        return drop * 80  # rough
    path.write_text("\n".join(lines[-max_lines:]) + "\n", encoding="utf-8")
    return drop * 80


def prune_stale_pids(dry: bool) -> int:
    freed = 0
    pdir = ROOT / ".pids"
    if not pdir.is_dir():
        return 0
    for pf in pdir.glob("*.pid"):
        try:
            pid = int(pf.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
        except (OSError, ValueError):
            freed += _rm(pf, dry)
    return freed


def prune_old_progress_hist(dry: bool) -> int:
    freed = 0
    for name in (".progress_rate_history.jsonl", ".progress_overall_history.jsonl"):
        p = ROOT / "data" / name
        freed += trim_jsonl_tail(p, int(os.getenv("PROGRESS_HIST_MAX_LINES", "500")), dry)
    return freed


def prune_self_improve_archive(dry: bool) -> int:
    """Keep newest N evolver gens — 20k+ copies are refetchable local snapshots."""
    root = ROOT / "data" / "self_improve" / "archive"
    if not root.is_dir():
        return 0
    keep = max(8, int(os.getenv("SELF_IMPROVE_ARCHIVE_KEEP", "24")))
    gens = sorted(root.glob("gen_*.py"), key=lambda p: p.stat().st_mtime, reverse=True)
    freed = 0
    for p in gens[keep:]:
        freed += _rm(p, dry)
    return freed


def prune_policy_snapshots(dry: bool) -> int:
    """Keep newest N rollback snapshots — 10k+ dirs waste inodes/space."""
    root = ROOT / "data" / "policy" / "snapshots"
    if not root.is_dir():
        return 0
    keep = max(5, int(os.getenv("POLICY_SNAPSHOT_KEEP", "40")))
    dirs = sorted(
        [p for p in root.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    freed = 0
    for d in dirs[keep:]:
        freed += _rm(d, dry)
    audit = ROOT / "data" / "policy" / "audit_trail.jsonl"
    freed += trim_jsonl_tail(audit, int(os.getenv("POLICY_AUDIT_MAX_LINES", "5000")), dry)
    return freed


def prune_intraday_placeholders(dry: bool) -> int:
    """Remove tiny neutral intraday bundles — inference uses p=0.5 when file missing."""
    freed = 0
    root = ROOT / "models/intraday"
    thresh = int(os.getenv("INTRADAY_TRAINED_MIN_BYTES", "12000"))
    if not root.is_dir():
        return 0
    for p in root.glob("*_intraday.pkl"):
        try:
            if p.stat().st_size > thresh:
                continue
        except OSError:
            continue
        freed += _rm(p, dry)
    return freed


def prune_replay_cache(dry: bool) -> int:
    freed = prune_replay_all(dry)
    cache = ROOT / "data/cache"
    if cache.is_dir():
        for child in cache.iterdir():
            freed += _rm(child, dry)
    intra = ROOT / "data/intraday"
    if intra.is_dir() and os.getenv("PRUNE_INTRADAY_BARS", "true").lower() in ("1", "true", "yes"):
        for child in intra.rglob("*"):
            if child.is_file():
                freed += _rm(child, dry)
    return freed


def prune_old_paper_reports(dry: bool) -> int:
    """Drop unusable + excess paper_sim JSON (family-forecast reads newest usable)."""
    from analytics.paper_report import _prune_old_reports_keep_n, prune_unusable_paper_reports

    freed = 0
    n_bytes, removed = prune_unusable_paper_reports(dry_run=dry)
    freed += n_bytes
    if removed:
        print(f"    removed unusable: {', '.join(removed[:5])}" + ("…" if len(removed) > 5 else ""))
    if not dry:
        _prune_old_reports_keep_n()
    return freed


def prune_cursor_debug(dry: bool) -> int:
    freed = 0
    cursor = ROOT / ".cursor"
    if not cursor.is_dir():
        return 0
    for p in cursor.glob("debug-*.log"):
        freed += _rm(p, dry)
    return freed


def prune_junk_data_files(dry: bool) -> int:
    """Stale one-shot listing batch files only — never delete the IPO train queue."""
    freed = 0
    batch = ROOT / "data/new_listing_batch.json"
    if batch.is_file():
        try:
            text = batch.read_text(encoding="utf-8", errors="ignore")
            doc = json.loads(text)
            stale = (
                not doc
                or (isinstance(doc, list) and len(doc) == 0)
                or "OPENAI" in text.upper()
            )
        except Exception:
            stale = True
        if stale:
            freed += _rm(batch, dry)
    for p in ROOT.glob("data/universe_protocol_*.json"):
        freed += _rm(p, dry)
    return freed


def prune_cursor_terminals(dry: bool) -> int:
    freed = 0
    if not CURSOR_TERMINALS.is_dir():
        return 0
    for p in CURSOR_TERMINALS.glob("*.txt"):
        freed += _rm(p, dry)
    return freed


def prune_pycache(dry: bool) -> int:
    freed = 0
    skip = {"venv", ".git", "node_modules", "hft/node_modules"}
    for dirpath, dirnames, _ in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in skip]
        if "__pycache__" in dirnames:
            p = Path(dirpath) / "__pycache__"
            freed += _rm(p, dry)
            dirnames.remove("__pycache__")
    return freed


def trim_checkpoint_failed(dry: bool) -> tuple[int, int]:
    """Drop failed[] entries for non-priority symbols (keeps top100 + well-known)."""
    sys_path = str(ROOT)
    if sys_path not in __import__("sys").path:
        __import__("sys").path.insert(0, sys_path)
    from fortress_universe import load_top100_symbols

    keep = set(load_top100_symbols())
    freed = 0
    trimmed = 0
    for name in ("train_checkpoint.json", "intraday_train_checkpoint.json", "lstm_train_checkpoint.json"):
        path = ROOT / "data" / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        failed = data.get("failed") or {}
        if not isinstance(failed, dict):
            continue
        before = len(failed)
        new_failed = {k: v for k, v in failed.items() if k.upper() in keep}
        dropped = before - len(new_failed)
        if dropped <= 0:
            continue
        trimmed += dropped
        if not dry:
            data["failed"] = new_failed
            path.write_text(json.dumps(data, indent=0), encoding="utf-8")
        freed += path.stat().st_size  # nominal; json is small
    return freed, trimmed


def main() -> int:
    ap = argparse.ArgumentParser(description="Prune safe disk clutter (not models/)")
    ap.add_argument("--dry-run", action="store_true", help="report only")
    ap.add_argument("--no-checkpoints", action="store_true", help="do not trim failed[] in checkpoints")
    ap.add_argument("--no-stats-trim", action="store_true", help="do not trim train stats jsonl tails")
    args = ap.parse_args()
    dry = args.dry_run

    total = 0
    for label, fn in (
        ("logs (keep *_latest targets)", lambda: prune_logs(dry)),
        ("data/replay + cache + intraday bars", lambda: prune_replay_cache(dry)),
        ("legacy data/*.csv (7 tickers)", lambda: prune_legacy_root_csv(dry)),
        ("old paper_sim reports", lambda: prune_old_paper_reports(dry)),
        ("junk listing batch files", lambda: prune_junk_data_files(dry)),
        ("intraday placeholder bundles (≤12kB)", lambda: prune_intraday_placeholders(dry)),
        (".bak + .DS_Store", lambda: prune_bak_and_ds_store(dry)),
        ("stale .pids", lambda: prune_stale_pids(dry)),
        ("progress history tails", lambda: prune_old_progress_hist(dry)),
        ("policy snapshots + audit tail", lambda: prune_policy_snapshots(dry)),
        ("self-improve archive gens", lambda: prune_self_improve_archive(dry)),
        (".cursor debug logs", lambda: prune_cursor_debug(dry)),
        ("Cursor terminal history", lambda: prune_cursor_terminals(dry)),
        ("__pycache__", lambda: prune_pycache(dry)),
    ):
        n = fn()
        total += n
        print(f"  {label}: {_human(n)}")

    if not args.no_stats_trim:
        max_lines = int(os.getenv("TRAIN_STATS_MAX_LINES", "4000"))
        for label, rel in (
            ("train_run_stats.jsonl tail", "data/train_run_stats.jsonl"),
            ("intraday_train_stats.jsonl tail", "data/intraday_train_stats.jsonl"),
        ):
            n = trim_jsonl_tail(ROOT / rel, max_lines, dry)
            total += n
            if n:
                print(f"  {label}: {_human(n)}")

    if not args.no_checkpoints:
        _, dropped = trim_checkpoint_failed(dry)
        if dropped:
            print(f"  checkpoint failed[] trimmed: {dropped} non-priority symbols")

    print(f"{'Would free' if dry else 'Freed'} ~{_human(total)} (models/ untouched)")
    return 0


def _human(n: int) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.1f} {u}" if u != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} GB"


if __name__ == "__main__":
    raise SystemExit(main())
