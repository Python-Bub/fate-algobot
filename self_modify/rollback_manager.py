"""Rollback manager for guarded live self-modify."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from self_modify.audit_trail import log_audit


SNAPSHOT_ROOT = Path("data/policy/snapshots")


def _prune_old_snapshots(keep: int = 40) -> None:
    """Cap snapshot dirs so self-modify cannot fill the disk with 10k+ folders."""
    if not SNAPSHOT_ROOT.is_dir():
        return
    dirs = sorted(
        [p for p in SNAPSHOT_ROOT.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in dirs[max(5, keep) :]:
        shutil.rmtree(old, ignore_errors=True)


def snapshot_files(file_paths: list[str], tag: str | None = None) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"{tag or 'snapshot'}_{ts}"
    d = SNAPSHOT_ROOT / name
    d.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"created_at_utc": ts, "files": []}
    for p in file_paths:
        src = Path(p)
        if not src.is_file():
            continue
        dst = d / src.name
        shutil.copy2(src, dst)
        manifest["files"].append({"src": str(src), "dst": str(dst)})
    with open(d / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    log_audit("snapshot_created", {"snapshot": str(d), "count": len(manifest["files"])})
    _prune_old_snapshots(int(os.getenv("POLICY_SNAPSHOT_KEEP", "40")))
    return d


def rollback_snapshot(snapshot_path: str) -> int:
    d = Path(snapshot_path)
    man = d / "manifest.json"
    if not man.is_file():
        raise FileNotFoundError(man)
    obj = json.loads(man.read_text(encoding="utf-8"))
    restored = 0
    for rec in obj.get("files", []):
        src = Path(rec["dst"])
        dst = Path(rec["src"])
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            restored += 1
    log_audit("rollback_executed", {"snapshot": snapshot_path, "restored": restored})
    return restored

