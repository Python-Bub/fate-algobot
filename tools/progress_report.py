#!/usr/bin/env python3
"""Accurate training progress: checkpoints + live [PROGRESS] lines from parallel_train logs."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HIST = ROOT / "data" / ".progress_rate_history.jsonl"
OVERALL_HIST = ROOT / "data" / ".progress_overall_history.jsonl"
PROGRESS_DONE_RE = re.compile(
    r"\[PROGRESS\]\s+done=(\d+)/(\d+)\s+failed=(\d+)\s+pending=(\d+)\s+"
    r"rate=([\d.]+)/min\s+ETA=([\d.]+)h"
)
PROGRESS_SESSION_RE = re.compile(
    r"\[PROGRESS\]\s+session\s+(\d+)/(\d+)\s+saved=(\d+)\s+failed=(\d+)\s+left=(\d+)\s+"
    r"rate=([\d.]+)/min\s+ETA=([\d.]+)h"
)
PARALLEL_QUEUE_RE = re.compile(
    r"\[PARALLEL\]\s+pipeline=\w+\s+workers=\d+\s+queue=(\d+)"
)


def universe_size() -> int:
    try:
        sys.path.insert(0, str(ROOT))
        from universe_provider import load_universe_with_cap

        return len(load_universe_with_cap(max_symbols=None))
    except Exception:
        return 11412


def _eta_minutes(left: int, rate_per_min: float) -> int:
    if left <= 0:
        return 0
    return max(1, int(round(left / max(rate_per_min, 1e-6))))


def load_ck(path: Path) -> tuple[int, int]:
    if not path.is_file():
        return 0, 0
    try:
        d = json.loads(path.read_text())
        return len(d.get("done", [])), len(d.get("failed", {}))
    except Exception:
        return 0, 0


def saved_count(pat: str) -> int:
    return sum(1 for _ in ROOT.glob(pat))


# Neutral backfill bundles are ~455 B joblib; real intraday GBDT bundles are ~900 KiB+.
INTRADAY_PLACEHOLDER_MAX_BYTES = 12_000


def intraday_pkl_disk_breakdown() -> tuple[int, int, int]:
    """Return (total_files, trained_guess, placeholder_guess) using file size only (fast)."""
    trained = 0
    ph = 0
    for p in ROOT.glob("models/intraday/*_intraday.pkl"):
        try:
            sz = p.stat().st_size
        except OSError:
            continue
        if sz <= INTRADAY_PLACEHOLDER_MAX_BYTES:
            ph += 1
        else:
            trained += 1
    return trained + ph, trained, ph


def _log_name_matches_trainer(name_prefix: str, path: Path) -> bool:
    n = path.name
    if name_prefix == "train":
        return n.startswith("train_") and not n.startswith("train-intraday")
    return n.startswith(f"{name_prefix}_")


def _stdout_trainer_log_via_pid(name_prefix: str) -> Path | None:
    """Resolve the log file the running ``parallel_train`` actually writes to (macOS/Linux ``lsof``).

    Symlinks and rotation make ``*_latest.log`` misleading for intraday; the pidfile + FD
    path is ground truth when the trainer process is alive.
    """
    pid_path = ROOT / ".pids" / f"{name_prefix}.pid"
    if not pid_path.is_file():
        return None
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    try:
        r = subprocess.run(
            ["lsof", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=6,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0 or not r.stdout:
        return None
    logs_dir = str(ROOT / "logs")
    hits: list[Path] = []
    for line in r.stdout.splitlines():
        if logs_dir not in line or ".log" not in line:
            continue
        parts = line.split()
        if len(parts) < 9:
            continue
        # stdout/stderr to a regular file: FD column like "1w" / "2w"
        fd = parts[3]
        if len(fd) < 2 or fd[-1] != "w":
            continue
        raw = parts[-1]
        if not raw.endswith(".log"):
            continue
        p = Path(raw)
        if not _log_name_matches_trainer(name_prefix, p):
            continue
        hits.append(p)
    seen: set[str] = set()
    uniq: list[Path] = []
    for p in hits:
        k = str(p.resolve())
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    for p in uniq:
        if p.is_file():
            return p
    return None


def resolve_trainer_log(name_prefix: str) -> Path:
    """Pick the log file that actually matches the current run.

    Prefer ``logs/<prefix>_latest.log`` when its target is as fresh as the newest
    rotated file (same second as a huge old log must not send us back to stale
    ``[PROGRESS]`` lines). If the symlink is stale, use the newest mtime among
    ``logs/<prefix>_*.log`` (excluding the symlink itself).

    When the pid in ``.pids/<prefix>.pid`` is alive, prefer the log path from ``lsof``
    (especially important for **intraday**).
    """
    via = _stdout_trainer_log_via_pid(name_prefix)
    if via is not None:
        return via
    log_dir = ROOT / "logs"
    latest = log_dir / f"{name_prefix}_latest.log"
    candidates: list[Path] = []
    resolved: Path | None = None
    if latest.is_file():
        r = latest.resolve()
        if r.is_file():
            resolved = r
            candidates.append(r)
    for p in log_dir.glob(f"{name_prefix}_*.log"):
        if p.is_file() and not p.name.endswith("_latest.log"):
            candidates.append(p)
    if not candidates:
        return latest.resolve() if latest.is_file() else latest
    uniq = list({p.resolve(): p for p in candidates}.values())
    max_mtime = max(p.stat().st_mtime for p in uniq)
    fresh = [p for p in uniq if p.stat().st_mtime >= max_mtime - 3.0]
    if resolved is not None and resolved in fresh:
        return resolved
    return max(fresh or uniq, key=lambda p: (p.stat().st_mtime, p.stat().st_size))


def _parallel_train_pids() -> list[int]:
    try:
        r = subprocess.run(
            ["pgrep", "-f", "parallel_train.py"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if r.returncode != 0 or not r.stdout.strip():
        return []
    out: list[int] = []
    for line in r.stdout.splitlines():
        try:
            out.append(int(line.strip()))
        except ValueError:
            continue
    return out


def resolve_parallel_train_log() -> Path | None:
    """Log file for any running parallel_train (retrain-weak, top100 daily, etc.)."""
    for pid in _parallel_train_pids():
        try:
            os.kill(pid, 0)
        except OSError:
            continue
        try:
            r = subprocess.run(
                ["lsof", "-p", str(pid)],
                capture_output=True,
                text=True,
                timeout=6,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if r.returncode != 0 or not r.stdout:
            continue
        logs_dir = str(ROOT / "logs")
        for line in r.stdout.splitlines():
            if logs_dir not in line or ".log" not in line:
                continue
            parts = line.split()
            if len(parts) < 9:
                continue
            fd = parts[3]
            if len(fd) < 2 or fd[-1] != "w":
                continue
            raw = parts[-1]
            if raw.endswith(".log"):
                p = Path(raw)
                if p.is_file():
                    return p
    for name in ("retrain_weak_latest.log", "train_latest.log"):
        p = ROOT / "logs" / name
        if p.is_file():
            try:
                target = p.resolve()
                if target.is_file() and _log_age_sec(target) is not None and _log_age_sec(target) < 3600:
                    return target
            except OSError:
                pass
    return None


def trainer_running(name_prefix: str) -> bool:
    pid_path = ROOT / ".pids" / f"{name_prefix}.pid"
    if not pid_path.is_file():
        return False
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _log_age_sec(log_path: Path) -> float | None:
    try:
        return max(0.0, time.time() - log_path.stat().st_mtime)
    except OSError:
        return None


def best_progress_line(
    log_path: Path,
    ck_done: int,
    *,
    trainer_alive: bool,
    ck_pending: int,
    max_bytes: int = 12_000_000,
) -> dict | None:
    """Pick the newest [PROGRESS] line from the current run (reject stale logs)."""
    if not log_path.is_file():
        return None
    age = _log_age_sec(log_path)
    if not trainer_alive:
        # Old completed runs leave 100%/left=0 lines — don't treat as live progress.
        if age is not None and age > 120:
            return None
    try:
        sz = log_path.stat().st_size
        with open(log_path, "rb") as f:
            if sz > max_bytes:
                f.seek(sz - max_bytes)
                f.readline()
            data = f.read().decode("utf-8", errors="ignore")
    except OSError:
        return None
    for line in reversed(data.splitlines()):
        m_done = PROGRESS_DONE_RE.search(line)
        if m_done:
            best = {
                "kind": "done",
                "done": int(m_done.group(1)),
                "total": int(m_done.group(2)),
                "failed": int(m_done.group(3)),
                "pending": int(m_done.group(4)),
                "rate_per_min": float(m_done.group(5)),
                "eta_hours": float(m_done.group(6)),
            }
            if best["rate_per_min"] >= 0.05 and (ck_done - 80) <= best["done"] <= (ck_done + 25):
                return best
            continue

        m_session = PROGRESS_SESSION_RE.search(line)
        if m_session:
            left = int(m_session.group(5))
            best = {
                "kind": "session",
                "session_done": int(m_session.group(1)),
                "session_total": int(m_session.group(2)),
                "saved": int(m_session.group(3)),
                "failed": int(m_session.group(4)),
                "pending": left,
                "rate_per_min": float(m_session.group(6)),
                "eta_hours": float(m_session.group(7)),
            }
            if best["rate_per_min"] < 0.05:
                continue
            # Stale tail: old run finished (left=0) but checkpoint still has backlog.
            if left == 0 and ck_pending > 50 and not trainer_alive:
                continue
            if left == 0 and ck_pending > 50 and age is not None and age > 120:
                continue
            return best
    return None


def bar(pct: float, w: int = 40) -> str:
    fill = int(round(w * min(max(pct, 0.0), 100.0) / 100.0))
    return "█" * fill + "░" * (w - fill)


# Full proper-finish queue — weights sum to 100 (time/work shaped, not ticker-count naive).
_FINISH_PHASE_WEIGHTS: list[tuple[str, float]] = [
    ("wait_intraday", 5.0),
    ("intraday_proper_gap", 10.0),
    ("wait_lstm_active", 5.0),
    ("daily_junk", 5.0),
    ("train_failed", 10.0),
    ("top100_perfect", 15.0),
    # lstm_all = final LSTM pass; scope from LSTM_FINISH_SCOPE (default active, not 3.8k universe).
    ("lstm_all", 5.0),
]


def _load_queue_phase() -> str:
    path = ROOT / "data" / "enhancement_queue_state.json"
    if not path.is_file():
        return "unknown"
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("phase", "unknown"))
    except Exception:
        return "unknown"


def _lstm_pending(scope: str) -> int:
    prev = os.environ.get("LSTM_TRAIN_SCOPE")
    os.environ["LSTM_TRAIN_SCOPE"] = scope
    try:
        sys.path.insert(0, str(ROOT))
        from tools.train_lstm_heads import _pending_symbols

        return len(_pending_symbols())
    except Exception:
        return 0
    finally:
        if prev is None:
            os.environ.pop("LSTM_TRAIN_SCOPE", None)
        else:
            os.environ["LSTM_TRAIN_SCOPE"] = prev


def _phase_sub_progress(phase: str, *, total: int) -> tuple[float, str]:
    """Return (0..1 fraction, short detail) for the active enhancement-queue phase."""
    if phase == "done":
        return 1.0, "queue finished"

    if phase == "wait_intraday":
        alive = trainer_running("train-intraday")
        i_done, i_fail = load_ck(ROOT / "data" / "intraday_train_checkpoint.json")
        if not alive and (i_done + i_fail) >= total * 0.95:
            return 1.0, "intraday trainer idle"
        return min(1.0, (i_done + i_fail) / max(1, total)), "waiting on intraday"

    if phase == "intraday_proper_gap":
        _tot, trained, _ph = intraday_pkl_disk_breakdown()
        return min(1.0, trained / max(1, total)), f"intraday trained ~{trained}/{total}"

    if phase == "wait_lstm_active":
        pending = _lstm_pending("active")
        if pending <= 0:
            return 1.0, "LSTM active complete"
        # Rough: active universe ≈ paper-active + top names (~800–1200); use pending decay.
        est = max(1, pending + 200)
        return min(1.0, 1.0 - pending / est), f"LSTM active left {pending}"

    if phase in ("daily_junk", "train_failed"):
        alive = trainer_running("train")
        live = best_progress_line(
            resolve_trainer_log("train"),
            load_ck(ROOT / "data" / "train_checkpoint.json")[0],
            trainer_alive=alive,
            ck_pending=max(0, total - load_ck(ROOT / "data" / "train_checkpoint.json")[0]),
        )
        if live and live.get("kind") == "session":
            st, tot = int(live["session_done"]), int(live["session_total"])
            return min(1.0, st / max(1, tot)), f"train session {st}/{tot}"
        if not alive:
            return 1.0, "train idle"
        return 0.5, "train running"

    if phase == "top100_perfect":
        qlog = ROOT / "logs" / "enhancement_queue_latest.log"
        head = ""
        tail = ""
        if qlog.is_file():
            try:
                raw = qlog.read_bytes()
                head = raw[:80_000].decode("utf-8", errors="ignore")
                tail = raw[-400_000:].decode("utf-8", errors="ignore")
                text = head + tail
            except OSError:
                text = ""
        else:
            text = ""
        if "[top100-perfect] done" in text:
            return 1.0, "top100 perfection done"
        steps = [
            "refresh top100 list",
            "daily multi-horizon rebuild",
            "intraday gap-fill top100",
            "LSTM heads top100",
        ]
        step_idx = 0
        for i, label in enumerate(steps):
            if f"[top100-perfect] === {label} ===" in text:
                step_idx = i + 1
        n_steps = len(steps)
        completed = max(0, step_idx - 1)
        cur_frac = 0.0
        if step_idx == 1 or (step_idx == 2 and "daily multi-horizon rebuild" in text):
            m = list(PROGRESS_SESSION_RE.finditer(tail or text))
            if m:
                last = m[-1]
                cur_frac = int(last.group(1)) / max(1, int(last.group(2)))
            elif step_idx >= 1:
                cur_frac = 0.05
        elif step_idx >= n_steps:
            cur_frac = 1.0
        else:
            cur_frac = 0.15
        frac = min(1.0, (completed + cur_frac) / n_steps)
        if step_idx == 2 and cur_frac:
            detail = f"top100 daily {int(cur_frac * 100)}% ({completed + 1}/{n_steps} steps)"
        else:
            detail = f"top100 step {min(step_idx, n_steps)}/{n_steps}"
        return frac, detail

    if phase == "lstm_all":
        scope = os.getenv("LSTM_FINISH_SCOPE", "active").strip().lower()
        pending = _lstm_pending(scope)
        est = max(1, pending + 10)
        return (
            min(1.0, 1.0 - pending / est),
            f"LSTM finish ({scope}) left {pending} — neural is top100/online, not this phase",
        )

    return 0.0, phase


def overall_finish_pct() -> tuple[float, str, str]:
    """Weighted proper-finish % across the enhancement queue (one number)."""
    phase = _load_queue_phase()
    if phase == "done":
        return 100.0, phase, "all phases complete"

    names = [p for p, _ in _FINISH_PHASE_WEIGHTS]
    weights = {p: w for p, w in _FINISH_PHASE_WEIGHTS}
    total_w = sum(weights.values())

    try:
        uni = universe_size()
    except Exception:
        uni = 11412

    if phase not in weights:
        # init / unknown — fall back to model coverage average
        d_saved = saved_count("models/*_model.pkl")
        _tot, i_tr, _ph = intraday_pkl_disk_breakdown()
        n_lstm = saved_count("models/lstm/*.pt")
        avg = (d_saved + i_tr + n_lstm) / (3.0 * max(1, uni))
        return min(99.0, 100.0 * avg), phase, "model coverage estimate"

    idx = names.index(phase)
    earned = sum(weights[n] for n in names[:idx])
    sub, detail = _phase_sub_progress(phase, total=uni)
    earned += weights[phase] * sub
    pct = 100.0 * earned / total_w
    return min(99.9, pct), phase, detail


def _fmt_gb(num_bytes: int | float) -> str:
    gb = float(num_bytes) / 1e9
    if gb >= 100:
        return f"{gb:.0f} GB"
    return f"{gb:.1f} GB"


def _fmt_duration(minutes: float) -> str:
    if minutes <= 0 or not (minutes < 1e8):
        return "—"
    m = int(round(minutes))
    if m < 90:
        return f"~{m} min"
    h, rem = divmod(m, 60)
    if h < 48:
        return f"~{h}h {rem}m" if rem else f"~{h}h"
    d, rh = divmod(h, 24)
    return f"~{d}d {rh}h" if rh else f"~{d}d"


def _fmt_eta_wall(minutes: float) -> str:
    if minutes <= 0 or not (minutes < 1e8):
        return "ETA —"
    finish = datetime.now() + timedelta(minutes=minutes)
    return f"ETA {finish.strftime('%a %b %d %I:%M %p')} ({_fmt_duration(minutes)})"


def _du_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        r = subprocess.run(
            ["du", "-sk", str(path)],
            capture_output=True,
            text=True,
            timeout=45,
        )
        if r.returncode == 0 and r.stdout.strip():
            return int(r.stdout.split()[0]) * 1024
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def disk_breakdown() -> dict[str, int]:
    """Byte sizes for models vs optional fetchable caches."""
    daily_b = sum(
        p.stat().st_size
        for p in (ROOT / "models").glob("*_model.pkl")
        if p.is_file()
    )
    return {
        "models_daily": daily_b,
        "models_intraday": _du_bytes(ROOT / "models/intraday"),
        "models_lstm": _du_bytes(ROOT / "models/lstm"),
        "models_meta": _du_bytes(ROOT / "models/meta"),
        "cache_intraday_bars": _du_bytes(ROOT / "data/intraday"),
        "cache_replay_features": _du_bytes(ROOT / "data/replay/features"),
        "cache_price_ohlcv": _du_bytes(ROOT / "data/cache"),
        "data_other": max(
            0,
            _du_bytes(ROOT / "data")
            - _du_bytes(ROOT / "data/intraday")
            - _du_bytes(ROOT / "data/replay")
            - _du_bytes(ROOT / "data/cache"),
        ),
    }


def optional_cache_bytes(bd: dict[str, int] | None = None) -> int:
    bd = bd or disk_breakdown()
    return (
        bd["cache_intraday_bars"]
        + bd["cache_replay_features"]
        + bd["cache_price_ohlcv"]
    )


def required_models_bytes(bd: dict[str, int] | None = None) -> int:
    bd = bd or disk_breakdown()
    return (
        bd["models_daily"]
        + bd["models_intraday"]
        + bd["models_lstm"]
        + bd["models_meta"]
    )


def realistic_finish_models_bytes(bd: dict[str, int] | None = None) -> int:
    """Models-only finish estimate (replaces bogus linear extrapolation)."""
    bd = bd or disk_breakdown()
    base = required_models_bytes(bd)
    lstm_pending = _lstm_pending("all")
    avg_lstm_b = 268_000
    if bd["models_lstm"] > 0:
        n_lstm = saved_count("models/lstm/*.pt")
        if n_lstm > 0:
            avg_lstm_b = bd["models_lstm"] // n_lstm
    _tot, trained, ph = intraday_pkl_disk_breakdown()
    avg_intra_b = 1_000_000
    if trained > 0:
        # trained portion of intraday dir ≈ real bundles
        avg_intra_b = max(900_000, (bd["models_intraday"] - ph * 500) // max(1, trained))
    intraday_add = ph * avg_intra_b
    lstm_add = lstm_pending * avg_lstm_b
    # Top-100 / failed retries rewrite files in place — no duplicate copies.
    est = base + lstm_add + intraday_add
    target_gb = os.getenv("MODEL_FINISH_TARGET_GB", "").strip()
    if target_gb:
        try:
            est = max(est, int(float(target_gb) * 1_000_000_000))
        except ValueError:
            pass
    return est


def disk_training_bytes() -> int:
    """Total on disk: required models + optional caches + small data/json."""
    bd = disk_breakdown()
    return required_models_bytes(bd) + optional_cache_bytes(bd) + bd["data_other"]


def _append_overall_hist(pct: float, disk_b: int) -> None:
    OVERALL_HIST.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": time.time(), "pct": round(pct, 3), "disk_b": disk_b}
    with open(OVERALL_HIST, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")
    try:
        lines = OVERALL_HIST.read_text(encoding="utf-8").splitlines()
        if len(lines) > 300:
            OVERALL_HIST.write_text("\n".join(lines[-300:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def _overall_hist_samples(min_gap_sec: float = 120.0) -> list[dict]:
    if not OVERALL_HIST.is_file():
        return []
    rows: list[dict] = []
    for ln in OVERALL_HIST.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    if len(rows) < 2:
        return rows
    # Prefer samples at least min_gap apart for rate stability.
    picked = [rows[0]]
    for r in rows[1:]:
        if float(r["ts"]) - float(picked[-1]["ts"]) >= min_gap_sec:
            picked.append(r)
    if picked[-1] is not rows[-1]:
        picked.append(rows[-1])
    return picked


def _overall_rate_from_hist(pct: float) -> tuple[float | None, float | None]:
    """Return (pct_points_per_min, gb_per_hour) from history."""
    samples = _overall_hist_samples()
    if len(samples) < 2:
        return None, None
    a, b = samples[-2], samples[-1]
    dt_min = (float(b["ts"]) - float(a["ts"])) / 60.0
    if dt_min < 2.0:
        return None, None
    dp = float(b["pct"]) - float(a["pct"])
    if dp <= 0.001:
        return None, None
    rpm = dp / dt_min
    dg_b = int(b.get("disk_b", 0)) - int(a.get("disk_b", 0))
    gbph = (dg_b / 1e9) / (dt_min / 60.0) if dg_b > 0 else None
    return rpm, gbph


def _queue_log_tail(max_bytes: int = 400_000) -> str:
    qlog = ROOT / "logs" / "enhancement_queue_latest.log"
    if not qlog.is_file():
        return ""
    try:
        raw = qlog.read_bytes()
        return raw[-max_bytes:].decode("utf-8", errors="ignore")
    except OSError:
        return ""


def _top100_eta_minutes() -> float:
    tail = _queue_log_tail()
    m = list(PROGRESS_SESSION_RE.finditer(tail))
    daily_left_min = 45.0
    if m:
        last = m[-1]
        left = int(last.group(5))
        rate = float(last.group(6))
        if rate >= 0.05 and left > 0:
            daily_left_min = left / rate
    # daily + intraday + LSTM + neural for top100 (after current daily step)
    return daily_left_min + 150.0


def _lstm_all_eta_minutes() -> float:
    scope = os.getenv("LSTM_FINISH_SCOPE", "active").strip().lower()
    pending = _lstm_pending(scope)
    if pending <= 0:
        return 0.0
    workers = max(1, int(os.getenv("ENHANCE_LSTM_WORKERS", "6")))
    min_per = float(os.getenv("PROGRESS_LSTM_MIN_PER_TICKER", "2.5"))
    return (pending / workers) * min_per


def estimate_overall_eta_minutes(pct: float, phase: str) -> tuple[float | None, str]:
    """Minutes until 100%; second value explains source."""
    if pct >= 99.95:
        return 0.0, "complete"
    rpm, _ = _overall_rate_from_hist(pct)
    if rpm and rpm > 0.001:
        return (100.0 - pct) / rpm, "measured overall rate"

    names = [p for p, _ in _FINISH_PHASE_WEIGHTS]
    if phase not in names:
        return None, "need 2+ progress samples ~2 min apart"

    idx = names.index(phase)
    sub, _ = _phase_sub_progress(phase, total=universe_size())
    remaining_min = 0.0

    phase_eta: dict[str, float] = {
        "top100_perfect": _top100_eta_minutes(),
        "lstm_all": _lstm_all_eta_minutes(),
        "train_failed": 180.0,
        "daily_junk": 30.0,
        "wait_lstm_active": 60.0,
        "intraday_proper_gap": 120.0,
        "wait_intraday": 60.0,
    }
    cur_total = phase_eta.get(phase, 90.0)
    remaining_min += cur_total * max(0.0, 1.0 - sub)
    for p in names[idx + 1 :]:
        remaining_min += phase_eta.get(p, 60.0)
    return remaining_min, "phase estimate"


def overall_disk_line(pct: float) -> tuple[str, str | None]:
    """Return (disk summary, optional GB/h write rate on models only)."""
    bd = disk_breakdown()
    models_now = required_models_bytes(bd)
    caches = optional_cache_bytes(bd)
    est_models = realistic_finish_models_bytes(bd)
    add_models = max(0, est_models - models_now)

    line = (
        f"disk models {_fmt_gb(models_now)} now · ~{_fmt_gb(est_models)} at finish "
        f"(+{_fmt_gb(add_models)})"
    )
    if caches >= 50_000_000:
        line += f"  ·  optional caches {_fmt_gb(caches)} (Yahoo/Alpaca — `./run_all.sh prune-disk`)"
    _, gbph = _overall_rate_from_hist(pct)
    if gbph and gbph >= 0.01:
        line += f"  ·  measured write ~{gbph:.2f} GB/h"
    return line, f"{gbph:.2f} GB/h" if gbph else None


def print_disk_audit() -> int:
    bd = disk_breakdown()
    models = required_models_bytes(bd)
    caches = optional_cache_bytes(bd)
    est = realistic_finish_models_bytes(bd)
    project_b = _du_bytes(ROOT)
    venv_b = _du_bytes(ROOT / "venv")
    print("DISK AUDIT (FATE_AlgoBot)")
    print(f"  project total (Finder):          {_fmt_gb(project_b)}  (~117k files incl. models + venv)")
    print(f"  required models (must stay local): {_fmt_gb(models)}")
    print(f"    daily *_model.pkl:              {_fmt_gb(bd['models_daily'])}  (~10k × ~4 MB — inference weights)")
    print(f"    intraday bundles:               {_fmt_gb(bd['models_intraday'])}")
    print(f"    LSTM heads:                     {_fmt_gb(bd['models_lstm'])}")
    print(f"  python venv (not refetchable):     {_fmt_gb(venv_b)}")
    print(f"  refetchable caches (delete OK):  {_fmt_gb(caches)}")
    print(f"    Alpaca minute bars:             {_fmt_gb(bd['cache_intraday_bars'])}  → Alpaca API")
    print(f"    replay feature parquet:         {_fmt_gb(bd['cache_replay_features'])}  → Yahoo on train")
    print(f"    Yahoo price cache:              {_fmt_gb(bd['cache_price_ohlcv'])}  → Yahoo on train")
    print(f"  est. models at queue finish:     ~{_fmt_gb(est)}  (not 140 GB — that was a bad guess)")
    print(f"  after slim-disk:                 ~{_fmt_gb(project_b - caches)}  (+ venv {_fmt_gb(venv_b)})")
    print("  network-first (.env): prices/bars/features fetched live; caches won't grow back")
    print("  run:  ./run_all.sh slim-disk")
    return 0


def _prev_hist_row() -> dict | None:
    if not HIST.is_file():
        return None
    lines = [ln for ln in HIST.read_text().splitlines() if ln.strip()]
    if len(lines) < 1:
        return None
    try:
        return json.loads(lines[-1])
    except Exception:
        return None


def _roll_rpm(prev_done: int, cur_done: int, prev_ts: float) -> tuple[float | None, float]:
    dt = time.time() - prev_ts
    if dt < 20.0:
        return None, dt
    dd = cur_done - prev_done
    if dd <= 0:
        return None, dt
    return dd / (dt / 60.0), dt


def print_overall_bar(*, compact: bool = False) -> tuple[float, str, str, float | None, str]:
    pct, phase, _detail = overall_finish_pct()
    bd = disk_breakdown()
    disk_b = required_models_bytes(bd)
    _append_overall_hist(pct, disk_b)
    overall_eta_min, eta_src = estimate_overall_eta_minutes(pct, phase)
    disk_line, _ = overall_disk_line(pct)

    print("OVERALL (proper-finish queue)")
    print(f"  [{bar(pct, 50)}]  {pct:5.1f}%")
    print(f"  phase: {phase}  ·  {_detail}")
    if overall_eta_min is not None:
        print(f"  {_fmt_eta_wall(overall_eta_min)}  ({eta_src})")
    else:
        print(f"  ETA —  ({eta_src}; run `./run_all.sh progress` again in ~2 min)")
    print(f"  {disk_line}")
    if not compact:
        print()

    queue_phase = _load_queue_phase()
    return pct, phase, _detail, overall_eta_min, queue_phase


def main() -> int:
    compact = os.environ.get("PROGRESS_COMPACT", "").lower() in ("1", "true", "yes")
    if os.environ.get("PROGRESS_OVERALL_ONLY", "").lower() in ("1", "true", "yes"):
        print_overall_bar(compact=True)
        return 0
    if os.environ.get("PROGRESS_DISK_AUDIT", "").lower() in ("1", "true", "yes"):
        return print_disk_audit()

    _pct, _phase, _detail, overall_eta_min, queue_phase = print_overall_bar(compact=compact)

    total = universe_size()
    d_done, d_fail = load_ck(ROOT / "data" / "train_checkpoint.json")
    i_done, i_fail = load_ck(ROOT / "data" / "intraday_train_checkpoint.json")
    d_saved = saved_count("models/*_model.pkl")
    i_saved = saved_count("models/intraday/*_intraday.pkl")

    train_log = resolve_trainer_log("train")
    intra_log = resolve_trainer_log("train-intraday")

    prev = _prev_hist_row()

    def block(
        title: str,
        done: int,
        fail: int,
        saved: int,
        log_path: Path,
        key: str,
        *,
        trainer_name: str,
        trainer_alive: bool | None = None,
        intraday_disk: tuple[int, int, int] | None = None,
        queue_phase: str = "",
        overall_eta_min: float | None = None,
    ):
        pending = max(0, total - done - fail)
        pct = 100.0 * (done + fail) / total if total else 0.0
        pct_saved = 100.0 * saved / total if total else 0.0
        alive = (
            trainer_alive
            if trainer_alive is not None
            else trainer_running(trainer_name)
        )
        log_age = _log_age_sec(log_path)
        print(f"\n{title}")
        if intraday_disk is not None:
            _tot, _tr, _ph = intraday_disk
            pct_trained = 100.0 * _tr / total if total else 0.0
            print(f"  [{bar(pct)}]  {pct:5.1f}% checkpoint processed  (lifetime universe queue)")
            print(
                f"  on-disk bundles: {_tot}  ·  ~{_tr} trained (~{pct_trained:.1f}% of universe)  ·  "
                f"~{_ph} neutral placeholder (file ≤ {INTRADAY_PLACEHOLDER_MAX_BYTES // 1000}kB)"
            )
        else:
            print(f"  [{bar(pct)}]  {pct:5.1f}% checkpoint processed  ({pct_saved:4.1f}% tickers with a saved model file)")
        print(f"  saved {saved}  ·  checkpoint done {done}  ·  failed {fail}  ·  pending {pending}  ·  universe {total}")
        print(f"  trainer: {'RUNNING' if alive else 'stopped'}  ·  log: {log_path.name}")

        live = best_progress_line(log_path, done, trainer_alive=alive, ck_pending=pending)
        if live:
            if live.get("kind") == "session":
                eta_min = _eta_minutes(int(live["pending"]), float(live["rate_per_min"]))
                pct_run = 100.0 * float(live["session_done"]) / max(1.0, float(live["session_total"]))
                print(
                    f"  THIS RUN: [{bar(pct_run, 30)}]  {pct_run:.1f}%  "
                    f"{live['session_done']}/{live['session_total']}  left={live['pending']}  "
                    f"@ {live['rate_per_min']:.1f}/min  ETA≈{eta_min} min"
                )
            else:
                eta_min = _eta_minutes(int(live["pending"]), float(live["rate_per_min"]))
                print(
                    f"  live (trainer log): {live['rate_per_min']:.1f} tickers/min  "
                    f"ETA≈{eta_min} min  (log done={live['done']}, trainer pending={live['pending']})"
                )
        elif not alive and pending > 0:
            age_s = int(log_age) if log_age is not None else -1
            age_h = age_s / 3600.0 if age_s >= 0 else -1.0
            age_txt = f"{age_s}s" if age_s < 7200 else f"{age_h:.1f}h"
            print(
                f"  live: trainer stopped — stale log ignored "
                f"(log age {age_txt}, checkpoint pending {pending})"
            )
            _gap_phases = {
                "wait_intraday",
                "intraday_proper_gap",
                "wait_lstm_active",
                "daily_junk",
                "train_failed",
            }
            if queue_phase in ("lstm_all", "top100_perfect", "done"):
                if overall_eta_min is not None:
                    print(
                        f"  finish-critical: {_fmt_eta_wall(overall_eta_min)}  "
                        f"(phase={queue_phase}; this section is optional gap-fill backlog)"
                    )
                else:
                    print(
                        f"  finish-critical: see OVERALL ETA above  "
                        f"(phase={queue_phase}; this section is optional gap-fill backlog)"
                    )
            elif queue_phase in _gap_phases and key == "d":
                print("  finish-critical: daily gap may be active — see OVERALL ETA above")
            elif queue_phase in _gap_phases and key == "i":
                print("  finish-critical: intraday gap may be active — see OVERALL ETA above")
            gap_eta: str | None = None
            if prev and isinstance(prev.get("ts"), (int, float)):
                pd = int(prev.get("daily_done" if key == "d" else "intraday_done", -1))
                if pd >= 0:
                    rpm, dt = _roll_rpm(pd, done, float(prev["ts"]))
                    if rpm is not None:
                        eta_h = pending / max(rpm, 1e-6) / 60.0
                        gap_eta = (
                            f"  gap-fill ETA≈{eta_h:.1f} h @ {rpm:.1f}/min "
                            f"(only if you resume `./run_all.sh train{'-intraday' if key == 'i' else ''}`)"
                        )
            if gap_eta:
                print(gap_eta)
            elif queue_phase not in ("lstm_all", "top100_perfect", "done"):
                print(
                    "  gap-fill ETA: run `./run_all.sh progress` twice ~30s apart "
                    "while the trainer is running"
                )
        elif prev and isinstance(prev.get("ts"), (int, float)):
            pd = int(prev.get("daily_done" if key == "d" else "intraday_done", -1))
            if pd >= 0:
                rpm, dt = _roll_rpm(pd, done, float(prev["ts"]))
                if rpm is not None:
                    eta_h = pending / max(rpm, 1e-6) / 60.0
                    print(f"  estimated: {rpm:.1f} tickers/min  (since last `./run_all.sh progress`, {dt/60:.1f} min)  ETA≈{eta_h:.1f} h")
                else:
                    print("  rate: run `./run_all.sh progress` again in ~30s (need more time between samples)")
            else:
                print("  rate: run `./run_all.sh progress` again in ~30s")
        else:
            print("  rate: run `./run_all.sh progress` again in ~30s (building history)")

    pt_log = resolve_parallel_train_log()
    pt_alive = bool(_parallel_train_pids())
    daily_log = pt_log if (pt_alive and pt_log) else train_log
    daily_alive = pt_alive or trainer_running("train")

    block(
        "Daily (1d + 5d + 20d + 60d heads)",
        d_done,
        d_fail,
        d_saved,
        daily_log,
        "d",
        trainer_name="train",
        trainer_alive=daily_alive,
        queue_phase=queue_phase,
        overall_eta_min=overall_eta_min,
    )
    if pt_alive and pt_log and pt_log != train_log:
        live = best_progress_line(
            pt_log, d_done, trainer_alive=True, ck_pending=max(0, total - d_done - d_fail)
        )
        if live and live.get("kind") == "session":
            eta_min = _eta_minutes(int(live["pending"]), float(live["rate_per_min"]))
            pct_run = 100.0 * float(live["session_done"]) / max(1.0, float(live["session_total"]))
            print(
                f"  AD-HOC parallel_train ({pt_log.name}): [{bar(pct_run, 30)}] {pct_run:.1f}%  "
                f"{live['session_done']}/{live['session_total']} left={live['pending']}  "
                f"@ {live['rate_per_min']:.1f}/min  ETA≈{eta_min} min"
            )
    i_disk = intraday_pkl_disk_breakdown()
    block(
        "Intraday (5-min + 60-min heads)",
        i_done,
        i_fail,
        i_saved,
        intra_log,
        "i",
        trainer_name="train-intraday",
        intraday_disk=i_disk,
        queue_phase=queue_phase,
        overall_eta_min=overall_eta_min,
    )

    now = time.time()
    HIST.parent.mkdir(parents=True, exist_ok=True)
    with open(HIST, "a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {"ts": now, "daily_done": d_done, "intraday_done": i_done},
                separators=(",", ":"),
            )
            + "\n"
        )
    # Trim history to last 200 lines
    try:
        lines = HIST.read_text(encoding="utf-8").splitlines()
        if len(lines) > 200:
            HIST.write_text("\n".join(lines[-200:]) + "\n", encoding="utf-8")
    except OSError:
        pass

    print()
    print("Notes:")
    print("  • checkpoint 'done' includes symbols that finished without writing a model (skipped).")
    print("  • THIS RUN = current parallel_train session (gap-fill queue). Checkpoint bar = lifetime universe.")
    print("  • Live ETA uses left/rate (not rounded-to-zero hours). Stale logs ignored when trainer is stopped.")
    print("  • Trainer log path uses the running pid + lsof when possible.")
    print("  • Intraday: bar = checkpoint progress; trained vs placeholder counts use on-disk file size (see line above).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
