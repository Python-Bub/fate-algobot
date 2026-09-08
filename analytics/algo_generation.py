"""Algorithm factory: models teach, the student learns, and both keep minting forever.

Per-ticker daily/LSTM heads stay as teachers. There is no cap on how many ticker
models or algorithm generations may exist — clips chain the whole universe, and
each loop can mint the next gen_N pickle. Live rank still only flips when OOS
strictly beats the teacher.

Phases (100): 9 waves × 11 core steps + complete.
  Core: scan → cover → harvest → distill → pipeline → quality → fuse → deploy → batch → advance → finalize
  Wave 1 uses those names; waves 2–9 are wN_<core>; phase 100 is complete.
  Live rank still only flips when OOS strictly beats the teacher. Ticker trainers never stop.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from utils import log

def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _path(env_name: str, *parts: str) -> Path:
    raw = os.getenv(env_name, "").strip()
    if raw:
        return Path(raw)
    return _root().joinpath(*parts)


def state_path() -> Path:
    return _path("ALGO_PIPELINE_STATE", "data", "intel", "algo_pipeline_state.json")


def board_path() -> Path:
    return _path("ALGO_BOARD_PATH", "data", "intel", "algo_board.json")


def candidate_board_path() -> Path:
    return _path("ALGO_CANDIDATE_BOARD", "data", "intel", "algo_board_candidate.json")


def pipeline_phase_path() -> Path:
    return _path("ALGO_PIPELINE_PHASE", "data", "intel", "algo_pipeline.json")


def overlay_path() -> Path:
    return _path("ALGO_OVERLAY_PATH", "data", "self_improve", "algo_overlay.json")


def overlay_candidate_path() -> Path:
    return _path("ALGO_OVERLAY_CANDIDATE", "data", "self_improve", "algo_overlay_candidate.json")


def fuse_state_path() -> Path:
    return _path("ALGO_FUSE_STATE", "data", "intel", "algo_fuse.json")


def deploy_state_path() -> Path:
    return _path("ALGO_DEPLOY_STATE", "data", "intel", "algo_deploy.json")


def batch_path() -> Path:
    return _path("ALGO_BATCH_FILE", "data", "train", "algo_next_batch.txt")


def batch_state_path() -> Path:
    return _path("ALGO_BATCH_STATE", "data", "intel", "algo_batch.json")


def advance_state_path() -> Path:
    return _path("ALGO_ADVANCE_STATE", "data", "intel", "algo_advance.json")


def finalize_state_path() -> Path:
    return _path("ALGO_FINALIZE_STATE", "data", "intel", "algo_finalize.json")


def complete_state_path() -> Path:
    return _path("ALGO_COMPLETE_STATE", "data", "intel", "algo_complete.json")


def ledger_path() -> Path:
    return _path("ALGO_LEDGER", "data", "intel", "algo_ledger.json")


def harvest_rows_path() -> Path:
    return _path("ALGO_HARVEST_ROWS", "data", "intel", "algo_harvest_rows.json")


def scan_state_path() -> Path:
    return _path("ALGO_SCAN_STATE", "data", "intel", "algo_scan.json")


def cover_state_path() -> Path:
    return _path("ALGO_COVER_STATE", "data", "intel", "algo_cover.json")


def pipeline_lock_path() -> Path:
    return _path("ALGO_PIPELINE_LOCK", "data", "intel", "algo_pipeline.lock")


def algo_dir() -> Path:
    return _path("ALGO_MODEL_DIR", "models", "algorithm")


def current_ptr() -> Path:
    return algo_dir() / "current.json"


def distill_recipe() -> str:
    return os.getenv("ALGO_DISTILL_RECIPE", DISTILL_RECIPE_DEFAULT).strip() or DISTILL_RECIPE_DEFAULT


def _unbounded_cap(env_name: str, default: str = "0") -> int:
    raw = os.getenv(env_name, default).strip().lower()
    if raw in ("", "0", "inf", "all", "unlimited"):
        return 10_000_000
    try:
        n = int(raw)
    except ValueError:
        return 10_000_000
    return n if n > 0 else 10_000_000


def _skip_unchanged() -> bool:
    return os.getenv("ALGO_SKIP_UNCHANGED", "false").lower() in ("1", "true", "yes")


ROOT = _root()
CORE_PHASES: tuple[str, ...] = (
    "scan",
    "cover",
    "harvest",
    "distill",
    "pipeline",
    "quality",
    "fuse",
    "deploy",
    "batch",
    "advance",
    "finalize",
)
N_WAVES = 9
WAVE_FOCUS: tuple[str, ...] = (
    "bootstrap",
    "intraday_cover",
    "daily_gaps",
    "teacher_harvest",
    "student_distill",
    "weak_quality",
    "fuse_overlay",
    "strict_deploy",
    "batch_advance",
)


def _build_phases() -> tuple[str, ...]:
    names: list[str] = []
    for w in range(1, N_WAVES + 1):
        for c in CORE_PHASES:
            names.append(c if w == 1 else f"w{w}_{c}")
    names.append("complete")
    return tuple(names)


PHASES: tuple[str, ...] = _build_phases()
FEATURE_COLS: tuple[str, ...] = (
    "p_up",
    "p_up_raw",
    "p_short_model",
    "p_long_model",
    "execution_confidence",
    "score",
    "momentum_5d",
    "rs_spy",
    "volume_ratio",
    "sentiment",
    "dip_signal",
    "news_factor",
    "lstm_p_up",
    "neural_p_up",
    "daily_top20",
    "meta_auc",
    "minute_top20",
    "hour_top20",
    "lstm_test_acc",
    "teacher_margin",
    "teacher_extreme",
    "long_short_gap",
    "lstm_gap",
    "conf_x_margin",
)

DISTILL_RECIPE_DEFAULT = "teacher_blend_v1"


_BUNDLE_CACHE: tuple[float, dict[str, Any]] | None = None


@dataclass
class PhaseResult:
    phase: str
    ok: bool
    detail: dict[str, Any] = field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _json_ready(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _json_ready(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_ready(v) for v in obj]
    if isinstance(obj, np.generic):
        return _json_ready(obj.item())
    if isinstance(obj, float):
        if obj != obj or obj in (float("inf"), float("-inf")):
            return None
        return obj
    return obj


def _save_json(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(_json_ready(doc), indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


def load_state() -> dict[str, Any]:
    st = _load_json(state_path(), {})
    if not isinstance(st, dict):
        st = {}
    st.setdefault("generation", 0)
    st.setdefault("phase", "scan")
    st.setdefault("history", [])
    return st


def save_state(st: dict[str, Any]) -> None:
    st["updated_utc"] = _now()
    _save_json(state_path(), st)


def _count_glob(folder: Path, pattern: str, *, min_bytes: int = 1000) -> int:
    if not folder.is_dir():
        return 0
    n = 0
    for p in folder.glob(pattern):
        try:
            if p.is_file() and p.stat().st_size >= min_bytes:
                n += 1
        except OSError:
            continue
    return n


def _pid_running(name: str) -> bool:
    pf = ROOT / ".pids" / f"{name}.pid"
    if not pf.is_file():
        return False
    try:
        pid = int(pf.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, OSError):
        return False


def trainers_busy() -> list[str]:
    busy = []
    for name in ("train", "train-intraday", "train-lstm", "enhancement-queue", "retrain-weak-loop"):
        if _pid_running(name):
            busy.append(name)
    return busy


def scan_upgrades() -> dict[str, Any]:
    """Whole-stack catalog: coverage gaps + weak heads + overlay gen. Never deletes."""
    ttl = float(os.getenv("ALGO_SCAN_TTL_SEC", "900"))
    if ttl > 0:
        prev = _load_json(scan_state_path(), {})
        ts = str(prev.get("scanned_utc") or "")
        if ts and prev.get("daily_models"):
            try:
                age = (
                    datetime.now(timezone.utc) - datetime.fromisoformat(ts.replace("Z", "+00:00"))
                ).total_seconds()
            except ValueError:
                age = ttl + 1
            if age < ttl:
                prev["cached"] = True
                prev["trainers_busy"] = trainers_busy()
                prev["cache_age_sec"] = round(age, 1)
                return prev
    models = ROOT / "models"
    daily = _count_glob(models, "*_model.pkl")
    intra = _count_glob(models / "intraday", "*_intraday.pkl")
    lstm = _count_glob(models / "lstm", "*_lstm.pt", min_bytes=100)
    neural = _count_glob(models / "neural_ensemble", "*", min_bytes=100)
    missing_intra: list[str] = []
    missing_lstm: list[str] = []
    if models.is_dir():
        for p in models.glob("*_model.pkl"):
            if p.stat().st_size < 1000:
                continue
            sym = p.name[: -len("_model.pkl")].upper()
            ip = models / "intraday" / f"{sym}_intraday.pkl"
            lp = models / "lstm" / f"{sym}_lstm.pt"
            if not ip.is_file() or ip.stat().st_size < 1000:
                missing_intra.append(sym)
            if not lp.is_file() or lp.stat().st_size < 100:
                missing_lstm.append(sym)
    weak: dict[str, list[str]] = {}
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "retrain_weak_models",
            ROOT / "tools" / "retrain_weak_models.py",
        )
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            prev = os.environ.get("RETRAIN_SCAN_NULL_HEADS")
            os.environ["RETRAIN_SCAN_NULL_HEADS"] = "false"
            try:
                weak = mod.find_weak_symbols(
                    min_top20=float(os.getenv("RETRAIN_MIN_TOP20", "0.6")),
                    min_meta=float(os.getenv("MIN_META_AUC", "0.52")),
                    top100_only=os.getenv("ALGO_WEAK_TOP100_ONLY", "true").lower()
                    in ("1", "true", "yes"),
                )
            finally:
                if prev is None:
                    os.environ.pop("RETRAIN_SCAN_NULL_HEADS", None)
                else:
                    os.environ["RETRAIN_SCAN_NULL_HEADS"] = prev
    except Exception as e:
        log.debug("[ALGO] weak scan skipped: %s", e)
    overlay_gen = 0
    try:
        ov = ROOT / "data" / "self_improve" / "strategy_overlay.py"
        if ov.is_file():
            for ln in ov.read_text(encoding="utf-8", errors="ignore").splitlines()[:40]:
                if "GENERATION" in ln and "=" in ln:
                    digits = "".join(ch for ch in ln.split("=", 1)[-1] if ch.isdigit())
                    if digits:
                        overlay_gen = int(digits)
                        break
    except Exception:
        pass
    cover_file = ROOT / "data" / "train" / "algo_cover_intraday.txt"
    cover_file.parent.mkdir(parents=True, exist_ok=True)
    cover_file.write_text("\n".join(missing_intra) + ("\n" if missing_intra else ""), encoding="utf-8")
    eq = _load_json(ROOT / "data" / "enhancement_queue_state.json", {})

    def _ck(rel: str) -> dict[str, Any]:
        doc = _load_json(ROOT / rel, {})
        failed = doc.get("failed") or {}
        n_fail = len(failed) if isinstance(failed, dict) else len(failed or [])
        return {"done": len(doc.get("done") or []), "failed": n_fail}

    daily_ck = _ck("data/train_checkpoint.json")
    intra_ck = _ck("data/intraday_train_checkpoint.json")
    lstm_ck = _ck("data/lstm_train_checkpoint.json")
    paper = _load_json(ROOT / "reports" / "paper_sim_latest.json", {})
    paper_meta = {
        "generated_at_utc": paper.get("generated_at_utc"),
        "symbols_scored": int(paper.get("symbols_scored") or 0),
        "universe_size": int(paper.get("universe_size") or 0),
        "skipped_no_model_or_history": int(paper.get("skipped_no_model_or_history") or 0),
        "sum_hypothetical_pnl_usd": paper.get("sum_hypothetical_pnl_usd"),
    }
    ptr = _load_json(current_ptr(), {})
    upgrades: list[dict[str, Any]] = []
    if missing_intra:
        upgrades.append(
            {
                "id": "fill_intraday",
                "priority": 1,
                "n": len(missing_intra),
                "why": "daily pickle exists, no trained 5m/60m head",
                "next": "phase 2 cover → train-intraday missing clip",
            }
        )
    if daily_ck["failed"] > 0:
        upgrades.append(
            {
                "id": "retry_daily_failed",
                "priority": 2,
                "n": daily_ck["failed"],
                "why": "train_checkpoint failed (often skipped_no_model)",
                "next": "phase 9 batch + existing train-failed path",
            }
        )
    skip_n = paper_meta["skipped_no_model_or_history"]
    if skip_n > 0:
        upgrades.append(
            {
                "id": "paper_unscored",
                "priority": 3,
                "n": skip_n,
                "why": "paper_sim skipped names (no model or history)",
                "next": "phase 3 harvest uses scored rows; cover fills the rest",
            }
        )
    if missing_lstm:
        upgrades.append(
            {
                "id": "fill_lstm",
                "priority": 4,
                "n": len(missing_lstm),
                "why": "daily pickle exists, no LSTM .pt",
                "next": "existing train-lstm / enhancement lstm_all",
            }
        )
    catalog = {
        "daily_models": daily,
        "intraday_models": intra,
        "lstm_models": lstm,
        "neural_models": neural,
        "missing_intraday": len(missing_intra),
        "missing_lstm": len(missing_lstm),
        "weak_heads": len(weak),
        "overlay_generation": overlay_gen,
        "enhancement_phase": eq.get("phase"),
        "trainers_busy": trainers_busy(),
        "missing_intraday_sample": missing_intra[:80],
        "missing_lstm_sample": missing_lstm[:80],
        "weak_sample": sorted(weak)[:80],
        "cover_intraday_file": str(cover_file),
        "daily_checkpoint": daily_ck,
        "intraday_checkpoint": intra_ck,
        "lstm_checkpoint": lstm_ck,
        "paper_sim": paper_meta,
        "algo_generation": int(ptr.get("generation") or 0),
        "algo_auc": ptr.get("auc"),
        "upgrades": upgrades,
        "phase": "scan",
        "scanned_utc": _now(),
    }
    _save_json(scan_state_path(), catalog)
    log.info(
        "[ALGO] scan daily=%d intra=%d lstm=%d weak=%d miss_i=%d miss_l=%d upgrades=%d",
        daily,
        intra,
        lstm,
        len(weak),
        len(missing_intra),
        len(missing_lstm),
        len(upgrades),
    )
    return catalog


def _write_batch(symbols: list[str]) -> Path:
    path = batch_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    uniq = []
    seen: set[str] = set()
    for s in symbols:
        u = str(s).strip().upper()
        if not u or u in seen:
            continue
        seen.add(u)
        uniq.append(u)
    path.write_text("\n".join(uniq) + ("\n" if uniq else ""), encoding="utf-8")
    return path


def _kick_daily_batch(symbols: list[str]) -> str:
    """Queue next clip. Does not wipe checkpoints or start a second full-universe train."""
    if not symbols:
        return "empty"
    path = _write_batch(symbols)
    if os.getenv("ALGO_KICK_TRAIN", "true").lower() not in ("1", "true", "yes"):
        return f"queued_file:{len(symbols)}"
    if os.getenv("ALGO_KICK_DAILY_BATCH", "true").lower() not in ("1", "true", "yes"):
        return f"queued_learn:{len(symbols)}"
    busy = trainers_busy()
    if busy:
        return f"queued_busy:{','.join(busy)}"
    py = ROOT / "venv" / "bin" / "python"
    if not py.is_file():
        py = Path(os.environ.get("PYTHON", "python3"))
    env = os.environ.copy()
    env["TRAIN_SYMBOLS_FILE"] = str(path)
    env["FRESH_MODEL_REBUILD"] = "false"
    logf = ROOT / "logs" / "algo_batch_train.log"
    logf.parent.mkdir(parents=True, exist_ok=True)
    try:
        with logf.open("a", encoding="utf-8") as out:
            subprocess.Popen(
                [str(py), "-u", str(ROOT / "parallel_train.py"), "--pipeline", "daily"],
                cwd=str(ROOT),
                env=env,
                stdout=out,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        return f"spawned:{len(symbols)}"
    except Exception as e:
        log.warning("[ALGO] batch spawn failed: %s", e)
        return f"spawn_failed:{e}"


def advance(
    symbols: list[str] | None = None,
    *,
    generation: int | None = None,
    ensure_loop: bool | None = None,
) -> dict[str, Any]:
    """Phase 10: kick the daily clip if idle, keep the factory loop. Never flips live rank."""
    if symbols is None:
        bp = batch_path()
        if bp.is_file():
            symbols = [ln.strip().upper() for ln in bp.read_text(encoding="utf-8").splitlines() if ln.strip()]
        else:
            symbols = []
    busy = trainers_busy()
    kick = _kick_daily_batch(symbols) if symbols else "no_batch"
    do_loop = ensure_loop
    if do_loop is None:
        do_loop = os.getenv("ALGO_ENSURE_LOOP", "true").lower() in ("1", "true", "yes")
        if os.getenv("ALGO_KICK_TRAIN", "true").lower() not in ("1", "true", "yes"):
            do_loop = False
    loop_note = "skipped"
    if do_loop:
        if _pid_running("algo-pipeline"):
            loop_note = "already_running"
        else:
            run = ROOT / "run_all.sh"
            logf = ROOT / "logs" / "algo_advance_loop.log"
            logf.parent.mkdir(parents=True, exist_ok=True)
            try:
                with logf.open("a", encoding="utf-8") as fh:
                    subprocess.Popen(
                        ["bash", str(run), "ensure-algo-pipeline"],
                        cwd=str(ROOT),
                        stdout=fh,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                loop_note = "ensured"
            except Exception as e:
                loop_note = f"ensure_failed:{e}"
    ptr = _load_json(current_ptr(), {})
    st = load_state()
    gen = int(generation if generation is not None else (st.get("generation") or 0))
    st["generation"] = max(int(st.get("generation") or 0), gen)
    st["phase"] = "scan"
    st["last"] = {
        "generation": st["generation"],
        "kick": kick,
        "loop": loop_note,
        "utc": _now(),
    }
    save_state(st)
    out = {
        "ok": True,
        "phase": "advance",
        "utc": _now(),
        "generation": st["generation"],
        "kick": kick,
        "trainers_busy": busy,
        "batch_n": len(symbols or []),
        "batch_file": str(batch_path()),
        "loop": loop_note,
        "live_generation": ptr.get("generation"),
        "deployed": False,
        "note": (
            "daily clip waits while cover/quality run; loop continues. "
            "FRESH_MODEL_REBUILD false. current.json unchanged."
        ),
    }
    _save_json(advance_state_path(), out)
    log.info("[ALGO] advance kick=%s loop=%s busy=%s", kick, loop_note, busy)
    return out


def cover_gaps(catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    """Phase 2: fill missing intraday (and LSTM) without shrinking the universe.

    Starts the existing ``train-intraday-proper`` engine (365d lookback, retry
    placeholders). Does not delete models or skip names.
    """
    catalog = catalog or scan_upgrades()
    n_i = int(catalog.get("missing_intraday") or 0)
    n_l = int(catalog.get("missing_lstm") or 0)
    out: dict[str, Any] = {
        "missing_intraday": n_i,
        "missing_lstm": n_l,
        "cover_file": catalog.get("cover_intraday_file"),
        "utc": _now(),
        "phase": "cover",
    }
    if n_i <= 0 and n_l <= 0:
        out["note"] = "coverage_complete"
        out["algorithm_independent"] = True
        out["status"] = "teachers_complete"
        _save_json(cover_state_path(), out)
        return out
    out["algorithm_independent"] = True
    out["status"] = "teacher_backlog"
    out["algorithm_note"] = (
        f"missing_intraday={n_i} is a teacher-pickle backlog (checkpoint resume). "
        "The live algorithm already scores every ticker from features and does not wait on these heads."
    )
    if _pid_running("train-intraday"):
        out["note"] = "already_running"
        _save_json(cover_state_path(), out)
        return out
    if os.getenv("ALGO_KICK_TRAIN", "true").lower() not in ("1", "true", "yes"):
        out["note"] = "queued_file"
        _save_json(cover_state_path(), out)
        return out
    run = ROOT / "run_all.sh"
    logf = ROOT / "logs" / "algo_cover_intraday.log"
    logf.parent.mkdir(parents=True, exist_ok=True)
    try:
        with logf.open("a", encoding="utf-8") as fh:
            subprocess.Popen(
                ["bash", str(run), "train-intraday-proper"],
                cwd=str(ROOT),
                stdout=fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env={**os.environ, "FRESH_MODEL_REBUILD": "false"},
            )
        out["note"] = "spawned_train_intraday_proper"
        log.info("[ALGO] cover spawned train-intraday-proper missing_intraday=%d", n_i)
    except Exception as e:
        out["note"] = f"spawn_failed:{e}"
        log.warning("[ALGO] cover spawn failed: %s", e)
    _save_json(cover_state_path(), out)
    return out


def _fget(row: dict, key: str, default: float) -> float:
    try:
        v = row.get(key)
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _feat_default(col: str) -> float:
    c = str(col)
    if (
        c.startswith("p_")
        or c.endswith("_p_up")
        or c.endswith("_auc")
        or c.endswith("_acc")
        or c.endswith("_top20")
        or c == "execution_confidence"
    ):
        return 0.5
    return 0.0


def _enrich_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Derived teacher geometry — the student learns *when* models are wrong."""
    for r in rows:
        p = _fget(r, "p_up", 0.5)
        r["teacher_margin"] = p - 0.5
        r["teacher_extreme"] = 1.0 if p >= 0.60 or p < 0.45 else 0.0
        r["long_short_gap"] = _fget(r, "p_long_model", 0.5) - _fget(r, "p_short_model", 0.5)
        r["lstm_gap"] = _fget(r, "lstm_p_up", 0.5) - p
        r["conf_x_margin"] = _fget(r, "execution_confidence", 0.5) * (p - 0.5)
    return rows


def harvest_state_path() -> Path:
    return _path("ALGO_HARVEST_STATE", "data", "intel", "algo_harvest.json")


def _paper_fingerprint() -> str:
    parts: list[str] = []
    for p in _paper_sim_paths(harvest_reports_dir()):
        try:
            st = p.stat()
            parts.append(f"{p.name}:{int(st.st_mtime)}:{st.st_size}")
        except OSError:
            continue
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _rows_fingerprint(rows: list[dict[str, Any]], *, paper_fp: str = "") -> str:
    dates = sorted({str(r.get("signal_date") or "") for r in rows if r.get("signal_date")})
    n_intra = sum(1 for r in rows if r.get("joined_intraday"))
    payload = (
        f"{len(rows)}|{len({str(r.get('ticker')) for r in rows})}|"
        f"{','.join(dates)}|{n_intra}|{paper_fp}|{','.join(FEATURE_COLS)}"
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _fingerprint_from_harvest_summary(h: dict[str, Any], paper_fp: str = "") -> str:
    dates = sorted(str(d) for d in (h.get("dates") or []) if d)
    payload = (
        f"{int(h.get('n_rows') or 0)}|{int(h.get('n_tickers') or 0)}|"
        f"{','.join(dates)}|{int(h.get('joined_intraday_stats') or 0)}|{paper_fp}|{','.join(FEATURE_COLS)}"
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _load_harvest_cache(paper_fp: str) -> list[dict[str, Any]] | None:
    doc = _load_json(harvest_rows_path(), {})
    if not isinstance(doc, dict) or not doc.get("rows"):
        return None
    if str(doc.get("paper_fp") or "") != paper_fp:
        return None
    if list(doc.get("features") or []) != list(FEATURE_COLS):
        return None
    rows = doc.get("rows") or []
    return rows if isinstance(rows, list) and len(rows) >= 40 else None


def harvest_moments(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Running totals — keep 0.25, not 0.1+0.2+0.05."""
    if not rows:
        return {"n": 0, "n_tickers": 0, "hit": 0.0, "mean_fwd": 0.0, "mean_p": 0.5}
    n = len(rows)
    return {
        "n": n,
        "n_tickers": len({str(r.get("ticker") or "").upper() for r in rows}),
        "hit": float(np.mean([int(r.get("y") or 0) for r in rows])),
        "mean_fwd": float(np.mean([_fget(r, "fwd", 0.0) for r in rows])),
        "mean_p": float(np.mean([_fget(r, "p_up", 0.5) for r in rows])),
    }


def compact_labeled_rows(rows: list[dict[str, Any]], *, keep_dates: int | None = None) -> list[dict[str, Any]]:
    """Drop stale date copies; keep last N dates + latest-per-ticker. Moments live in harvest.json."""
    if not rows:
        return []
    k = keep_dates if keep_dates is not None else int(os.getenv("ALGO_HARVEST_KEEP_DATES", "8"))
    k = max(2, k)
    dates = sorted({str(r.get("signal_date") or "") for r in rows if r.get("signal_date")})
    keep = set(dates[-k:]) if dates else set()
    recent = [r for r in rows if not keep or str(r.get("signal_date") or "") in keep]
    seen = {(str(r.get("ticker") or "").upper(), str(r.get("signal_date") or "")) for r in recent}
    for r in _latest_per_ticker(rows):
        key = (str(r.get("ticker") or "").upper(), str(r.get("signal_date") or ""))
        if key not in seen:
            recent.append(r)
            seen.add(key)
    return recent


def _save_harvest_cache(rows: list[dict[str, Any]], paper_fp: str) -> None:
    compact = compact_labeled_rows(rows)
    _save_json(
        harvest_rows_path(),
        {
            "paper_fp": paper_fp,
            "harvest_fp": _rows_fingerprint(compact, paper_fp=paper_fp),
            "features": list(FEATURE_COLS),
            "n_rows": len(compact),
            "moments": harvest_moments(rows),
            "utc": _now(),
            "rows": compact,
        },
    )


def distill_state_path() -> Path:
    return _path("ALGO_DISTILL_STATE", "data", "intel", "algo_distill.json")


def harvest_reports_dir() -> Path:
    return _path("ALGO_HARVEST_REPORTS", "reports")


def _latest_jsonl_by_ticker(
    path: Path, *, prefer_keys: tuple[str, ...] = ()
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not path.is_file():
        return out
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if not isinstance(r, dict):
            continue
        t = str(r.get("ticker") or "").upper()
        if not t:
            continue
        prev = out.get(t)
        if prev is not None and prefer_keys:
            prev_rich = any(prev.get(k) is not None for k in prefer_keys)
            new_rich = any(r.get(k) is not None for k in prefer_keys)
            if prev_rich and not new_rich:
                continue
        out[t] = r
    return out


def _paper_sim_paths(reports_dir: Path) -> list[Path]:
    max_n = _unbounded_cap("ALGO_HARVEST_MAX_REPORTS", "0")
    latest = reports_dir / "paper_sim_latest.json"
    dated = sorted(
        (p for p in reports_dir.glob("paper_sim_*.json") if p.name != "paper_sim_latest.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    paths: list[Path] = []
    seen: set[Path] = set()
    if latest.is_file():
        paths.append(latest)
        try:
            seen.add(latest.resolve())
        except OSError:
            pass
    for p in dated:
        try:
            rp = p.resolve()
        except OSError:
            rp = p
        if rp in seen:
            continue
        seen.add(rp)
        paths.append(p)
        if len(paths) >= max_n:
            break
    return paths


def _p_up_buckets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges = (0.0, 0.45, 0.50, 0.55, 0.60, 1.01)
    out: list[dict[str, Any]] = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        subset = [r for r in rows if lo <= float(r.get("p_up") or 0) < hi]
        if not subset:
            continue
        y = [int(r["y"]) for r in subset]
        out.append(
            {
                "bucket": f"{lo:.2f}–{hi:.2f}",
                "n": len(subset),
                "hit": float(np.mean(y)),
                "mean_fwd": float(np.mean([float(r["fwd"]) for r in subset])),
            }
        )
    return out


def _intraday_pickle_stats(tickers: set[str]) -> dict[str, dict[str, Any]]:
    """Read stats from existing intraday pickles for teacher names only. Never deletes."""
    out: dict[str, dict[str, Any]] = {}
    if os.getenv("ALGO_HARVEST_PKL_JOIN", "false").lower() not in ("1", "true", "yes"):
        return out
    intra_dir = ROOT / "models" / "intraday"
    if not intra_dir.is_dir():
        return out
    for t in tickers:
        p = intra_dir / f"{t}_intraday.pkl"
        try:
            if not p.is_file() or p.stat().st_size < 1000:
                continue
            bundle = joblib.load(p)
        except Exception:
            continue
        if not isinstance(bundle, dict) or bundle.get("placeholder"):
            continue
        st = bundle.get("stats") or {}
        if not isinstance(st, dict):
            continue
        if st.get("minute_top20") is None and st.get("minute_acc") is None:
            continue
        out[t] = st
    return out


def harvest_teachers(*, max_rows: int | None = None) -> list[dict[str, Any]]:
    """Teacher dataset = paper_sim predictions vs next-bar, joined to pickle train stats."""
    paper_fp = _paper_fingerprint()
    busy = trainers_busy()
    cached = _load_harvest_cache(paper_fp)
    if cached:
        n_full = len(cached)
        cached = compact_labeled_rows(cached)
        _enrich_rows(cached)
        summary = _load_json(harvest_state_path(), {}) or {}
        summary["cached"] = True
        summary["paper_fp"] = paper_fp
        summary["n_rows"] = len(cached)
        summary["harvest_fp"] = _rows_fingerprint(cached, paper_fp=paper_fp)
        summary["moments"] = harvest_moments(cached)
        summary["utc"] = _now()
        summary["note"] = "harvest cache hit; compact rows (running totals, not stale date copies)"
        _save_json(harvest_state_path(), summary)
        if len(cached) < n_full:
            try:
                _save_harvest_cache(cached, paper_fp)
            except Exception:
                pass
        log.info("[ALGO] harvest cache n=%d (was %d) fp=%s", len(cached), n_full, paper_fp)
        return cached
    cap = max_rows if max_rows is not None else _unbounded_cap("ALGO_HARVEST_MAX_ROWS", "0")
    reports_dir = harvest_reports_dir()
    paths = _paper_sim_paths(reports_dir)
    daily_stats = _latest_jsonl_by_ticker(
        _path("TRAIN_STATS_PATH", "data", "train_run_stats.jsonl"),
        prefer_keys=("daily_top20", "meta_auc"),
    )
    intra_stats = _latest_jsonl_by_ticker(
        ROOT / "data" / "intraday_train_stats.jsonl",
        prefer_keys=("minute_top20", "minute_acc"),
    )
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    sources: list[dict[str, Any]] = []
    skipped_latest = 0
    for path in paths:
        doc = _load_json(path, {})
        if not isinstance(doc, dict):
            continue
        n_before = len(rows)
        if path.name == "paper_sim_latest.json":
            skipped_latest = int(doc.get("skipped_no_model_or_history") or 0)
        n_scored = 0
        for r in doc.get("rows") or []:
            if not isinstance(r, dict) or r.get("skipped"):
                continue
            t = str(r.get("ticker") or "").upper()
            if not t:
                continue
            key = (t, str(r.get("signal_date") or ""))
            if key in seen:
                continue
            seen.add(key)
            fwd = _fget(r, "fwd_1d_return", float("nan"))
            if fwd != fwd:
                continue
            n_scored += 1
            feat = {c: _fget(r, c, _feat_default(c)) for c in FEATURE_COLS}
            ds = daily_stats.get(t) or {}
            ins = intra_stats.get(t) or {}
            feat["daily_top20"] = _fget(ds, "daily_top20", feat.get("daily_top20") or 0.5)
            feat["meta_auc"] = _fget(ds, "meta_auc", feat.get("meta_auc") or 0.5)
            feat["lstm_test_acc"] = _fget(ds, "lstm_test_acc", feat.get("lstm_test_acc") or 0.5)
            feat["minute_top20"] = _fget(ins, "minute_top20", feat.get("minute_top20") or 0.5)
            feat["hour_top20"] = _fget(ins, "hour_top20", feat.get("hour_top20") or 0.5)
            if feat["p_up"] <= 0:
                feat["p_up"] = 0.5
            feat["ticker"] = t
            feat["signal_date"] = str(r.get("signal_date") or "")
            feat["y"] = 1 if fwd > 0 else 0
            feat["fwd"] = float(fwd)
            feat["joined_daily"] = bool(ds)
            feat["joined_intraday"] = bool(ins.get("minute_acc") is not None or ins.get("minute_top20") is not None)
            rows.append(feat)
            if len(rows) >= cap:
                break
        sources.append(
            {
                "file": path.name,
                "generated_at_utc": doc.get("generated_at_utc"),
                "symbols_scored": int(doc.get("symbols_scored") or n_scored),
                "harvested": len(rows) - n_before,
            }
        )
        if len(rows) >= cap:
            break
    need_intra = {str(r["ticker"]) for r in rows if not r.get("joined_intraday")}
    pkl_intra = {} if busy else _intraday_pickle_stats(need_intra)
    for r in rows:
        if r.get("joined_intraday"):
            continue
        st = pkl_intra.get(str(r["ticker"])) or {}
        if not st:
            continue
        r["minute_top20"] = _fget(st, "minute_top20", r.get("minute_top20") or 0.5)
        r["hour_top20"] = _fget(st, "hour_top20", r.get("hour_top20") or 0.5)
        r["joined_intraday"] = True
        r["joined_intraday_pkl"] = True
    _enrich_rows(rows)
    rows = compact_labeled_rows(rows)
    n_daily = sum(1 for r in rows if r.get("joined_daily"))
    n_intra = sum(1 for r in rows if r.get("joined_intraday"))
    tickers = {str(r["ticker"]) for r in rows}
    dates = sorted({str(r.get("signal_date") or "") for r in rows if r.get("signal_date")})
    hit = float(np.mean([int(r["y"]) for r in rows])) if rows else 0.0
    mean_fwd = float(np.mean([float(r["fwd"]) for r in rows])) if rows else 0.0
    mean_p = float(np.mean([float(r["p_up"]) for r in rows])) if rows else 0.5
    hot = sorted(rows, key=lambda r: -abs(float(r["fwd"])))[:12]
    summary = {
        "phase": "harvest",
        "utc": _now(),
        "n_rows": len(rows),
        "n_tickers": len(tickers),
        "n_dates": len(dates),
        "dates": dates,
        "hit_rate": hit,
        "mean_fwd": mean_fwd,
        "mean_p_up": mean_p,
        "joined_daily_stats": n_daily,
        "joined_intraday_stats": n_intra,
        "joined_intraday_from_pickle": sum(1 for r in rows if r.get("joined_intraday_pkl")),
        "daily_stats_universe": len(daily_stats),
        "intraday_stats_universe": len(intra_stats),
        "skipped_no_model_or_history": skipped_latest,
        "sources": sources,
        "p_up_buckets": _p_up_buckets(rows),
        "extreme_fwd": [
            {"ticker": r["ticker"], "fwd": r["fwd"], "p_up": r["p_up"], "y": r["y"], "signal_date": r.get("signal_date")}
            for r in hot
        ],
        "paper_fp": paper_fp,
        "harvest_fp": _rows_fingerprint(rows, paper_fp=paper_fp),
        "moments": harvest_moments(rows),
        "cached": False,
        "note": "compact teacher rows (last dates + latest-per-ticker); moments are running totals",
    }
    _save_json(harvest_state_path(), summary)
    try:
        _save_harvest_cache(rows, paper_fp)
    except Exception as e:
        log.debug("[ALGO] harvest cache write skipped: %s", e)
    log.info(
        "[ALGO] harvest n=%d tickers=%d dates=%d hit=%.3f daily_join=%d intra_join=%d",
        len(rows),
        len(tickers),
        len(dates),
        hit,
        n_daily,
        n_intra,
    )
    return rows


def _matrix(rows: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    X = np.asarray(
        [[float(r.get(c) if r.get(c) is not None else _feat_default(c)) for c in FEATURE_COLS] for r in rows],
        dtype=float,
    )
    y = np.asarray([int(r["y"]) for r in rows], dtype=int)
    return X, y


def _auc_score(y: np.ndarray, p: np.ndarray) -> float:
    if len(y) < 8 or len(set(y.tolist())) < 2:
        return float("nan")
    try:
        from sklearn.metrics import roc_auc_score

        return float(roc_auc_score(y, p))
    except Exception:
        return float("nan")


def _split_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    dates = sorted({str(r.get("signal_date") or "") for r in rows if r.get("signal_date")})
    if len(dates) >= 3:
        n_hold = max(1, len(dates) // 5)
        hold = set(dates[-n_hold:])
        train = [r for r in rows if str(r.get("signal_date") or "") not in hold]
        test = [r for r in rows if str(r.get("signal_date") or "") in hold]
        if len(train) >= 40 and len(test) >= 20 and len({int(r["y"]) for r in train}) >= 2:
            return train, test, {"mode": "time", "hold_dates": sorted(hold), "train_dates": [d for d in dates if d not in hold]}
    rng = np.random.default_rng(42)
    idx = rng.permutation(len(rows))
    n_te = max(20, int(len(rows) * 0.2))
    te_i, tr_i = idx[:n_te], idx[n_te:]
    train = [rows[int(i)] for i in tr_i]
    test = [rows[int(i)] for i in te_i]
    return train, test, {"mode": "random", "seed": 42, "test_frac": 0.2}


def _new_hgb(n_train: int = 200):
    from sklearn.ensemble import HistGradientBoostingClassifier

    leaf = max(10, min(40, max(int(n_train), 1) // 10))
    return HistGradientBoostingClassifier(
        max_depth=3,
        learning_rate=0.05,
        max_iter=200,
        l2_regularization=1.0,
        min_samples_leaf=leaf,
        early_stopping=True,
        validation_fraction=0.15,
        n_iter_no_change=12,
        random_state=42,
    )


def _new_logit():
    from sklearn.linear_model import LogisticRegression

    return LogisticRegression(max_iter=400, C=0.5)


def _importances(clf: Any) -> list[dict[str, Any]]:
    vals = getattr(clf, "feature_importances_", None)
    if vals is None and hasattr(clf, "coef_"):
        vals = np.abs(np.asarray(clf.coef_, dtype=float).ravel())
    if vals is None:
        return []
    pairs = sorted(zip(FEATURE_COLS, [float(v) for v in vals]), key=lambda kv: -kv[1])
    return [{"feature": n, "importance": v} for n, v in pairs]


def _perm_importances(clf: Any, X: np.ndarray, y: np.ndarray) -> list[dict[str, Any]]:
    try:
        from sklearn.inspection import permutation_importance

        r = permutation_importance(clf, X, y, n_repeats=6, random_state=42, scoring="roc_auc")
        pairs = sorted(zip(FEATURE_COLS, [float(v) for v in r.importances_mean]), key=lambda kv: -kv[1])
        return [{"feature": n, "importance": v} for n, v in pairs]
    except Exception:
        return _importances(clf)


def _student_buckets(rows: list[dict[str, Any]], proba: np.ndarray) -> list[dict[str, Any]]:
    tagged = []
    for r, p in zip(rows, proba):
        tagged.append({**r, "p_up": float(p)})
    return _p_up_buckets(tagged)


def _fit_one(kind: str, train: list[dict[str, Any]], test: list[dict[str, Any]]) -> dict[str, Any] | None:
    Xtr, ytr = _matrix(train)
    Xte, yte = _matrix(test)
    if len(set(ytr.tolist())) < 2:
        return None
    try:
        clf = _new_hgb(len(train)) if kind == "hgb" else _new_logit()
        clf.fit(Xtr, ytr)
    except Exception:
        return None
    p_tr = clf.predict_proba(Xtr)[:, 1]
    p_te = clf.predict_proba(Xte)[:, 1]
    return {
        "clf": clf,
        "kind": kind,
        "auc_train": _auc_score(ytr, p_tr),
        "auc_oos": _auc_score(yte, p_te),
        "importances": _perm_importances(clf, Xte, yte),
        "student_oos_buckets": _student_buckets(test, p_te),
        "teacher_oos_buckets": _p_up_buckets(test),
    }


def _teacher_vec(rows: list[dict[str, Any]]) -> np.ndarray:
    return np.asarray([_fget(r, "p_up", 0.5) for r in rows], dtype=float)


def _fit_calibrator(train: list[dict[str, Any]]):
    try:
        from sklearn.isotonic import IsotonicRegression

        p = _teacher_vec(train)
        y = np.asarray([int(r["y"]) for r in train], dtype=int)
        if len(set(y.tolist())) < 2 or float(np.std(p)) < 1e-9:
            return None
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.01, y_max=0.99)
        iso.fit(p, y)
        return iso
    except Exception:
        return None


def _best_blend_w(p_student: np.ndarray, p_teacher: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    best_w = 0.0
    best_a = _auc_score(y, p_teacher)
    if best_a != best_a:
        best_a = -1.0
    for w in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        p = w * p_student + (1.0 - w) * p_teacher
        a = _auc_score(y, p)
        if a == a and a >= best_a:
            best_a = a
            best_w = float(w)
    return best_w, best_a


def _fit_student(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if len(rows) < 40:
        return None
    rows = _enrich_rows(rows)
    y_all = [int(r["y"]) for r in rows]
    if len(set(y_all)) < 2:
        return None
    train, test, split = _split_rows(rows)
    yte = np.asarray([int(r["y"]) for r in test], dtype=int)
    ytr = np.asarray([int(r["y"]) for r in train], dtype=int)
    p_teacher_te = _teacher_vec(test)
    p_teacher_tr = _teacher_vec(train)
    teacher_oos = _auc_score(yte, p_teacher_te)
    recipes: list[dict[str, Any]] = [
        {
            "clf": None,
            "calibrator": None,
            "blend_w": 0.0,
            "kind": "teacher",
            "auc_train": _auc_score(ytr, p_teacher_tr),
            "auc_oos": teacher_oos,
            "p_te": p_teacher_te,
        }
    ]
    ptr = _load_json(current_ptr(), {}) or {}
    live_path = Path(str(ptr.get("path") or ""))
    if live_path.is_file():
        try:
            live_bundle = joblib.load(live_path)
            p_live_te = _apply_bundle(test, live_bundle)
            p_live_tr = _apply_bundle(train, live_bundle)
            recipes.append(
                {
                    "clf": live_bundle.get("clf"),
                    "calibrator": live_bundle.get("calibrator"),
                    "blend_w": live_bundle.get("blend_w"),
                    "kind": "live_prior",
                    "auc_train": _auc_score(ytr, p_live_tr),
                    "auc_oos": _auc_score(yte, p_live_te),
                    "p_te": p_live_te,
                }
            )
        except Exception:
            pass
    iso = _fit_calibrator(train)
    if iso is not None:
        try:
            p_cal_tr = np.clip(iso.predict(p_teacher_tr), 0.01, 0.99)
            p_cal_te = np.clip(iso.predict(p_teacher_te), 0.01, 0.99)
            recipes.append(
                {
                    "clf": None,
                    "calibrator": iso,
                    "blend_w": 0.0,
                    "kind": "calibrated",
                    "auc_train": _auc_score(ytr, p_cal_tr),
                    "auc_oos": _auc_score(yte, p_cal_te),
                    "p_te": p_cal_te,
                    "p_tr": p_cal_tr,
                }
            )
        except Exception:
            iso = None
    teacher_for_blend_tr = p_teacher_tr
    teacher_for_blend_te = p_teacher_te
    cal_for_blend = None
    if iso is not None and recipes[-1].get("kind") == "calibrated":
        cal_oos = recipes[-1].get("auc_oos")
        if cal_oos == cal_oos and (teacher_oos != teacher_oos or float(cal_oos) >= float(teacher_oos)):
            teacher_for_blend_tr = recipes[-1]["p_tr"]
            teacher_for_blend_te = recipes[-1]["p_te"]
            cal_for_blend = iso
    for kind in ("hgb", "logit"):
        fitted = _fit_one(kind, train, test)
        if not fitted:
            continue
        recipes.append(fitted)
        w, _ = _best_blend_w(fitted["clf"].predict_proba(_matrix(train)[0])[:, 1], teacher_for_blend_tr, ytr)
        p_s_te = fitted["clf"].predict_proba(_matrix(test)[0])[:, 1]
        p_blend = w * p_s_te + (1.0 - w) * teacher_for_blend_te
        recipes.append(
            {
                "clf": fitted["clf"],
                "calibrator": cal_for_blend,
                "blend_w": w,
                "kind": f"blend_{kind}",
                "auc_train": _best_blend_w(
                    fitted["clf"].predict_proba(_matrix(train)[0])[:, 1], teacher_for_blend_tr, ytr
                )[1],
                "auc_oos": _auc_score(yte, p_blend),
                "p_te": p_blend,
                "importances": fitted.get("importances"),
            }
        )
    scored = [d for d in recipes if d.get("auc_oos") == d.get("auc_oos")]
    if not scored:
        return None
    best = max(scored, key=lambda d: float(d.get("auc_oos") or -1.0))
    freeze = best.get("clf")
    X, y = _matrix(rows)
    full = freeze
    auc_in_sample = float(best.get("auc_train") or 0)
    if freeze is not None:
        try:
            k = "hgb" if "hgb" in str(best.get("kind") or "") else "logit"
            full = _new_hgb(len(rows)) if k == "hgb" else _new_logit()
            full.fit(X, y)
            auc_in_sample = _auc_score(y, full.predict_proba(X)[:, 1])
        except Exception:
            full = freeze
    p_te = np.asarray(best.get("p_te") if best.get("p_te") is not None else p_teacher_te, dtype=float)
    return {
        "clf": freeze,
        "clf_full": full,
        "calibrator": best.get("calibrator"),
        "blend_w": float(best.get("blend_w") if best.get("blend_w") is not None else 1.0),
        "kind": best["kind"],
        "features": list(FEATURE_COLS),
        "recipe": distill_recipe(),
        "auc": float(best["auc_oos"]),
        "auc_oos": best["auc_oos"],
        "auc_train": best.get("auc_train"),
        "auc_in_sample": auc_in_sample,
        "auc_teacher_oos": teacher_oos,
        "n_rows": int(len(rows)),
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "split": split,
        "mean_fwd": float(np.mean([r["fwd"] for r in rows])),
        "hit": float(np.mean(y_all)),
        "importances": best.get("importances") or (_importances(freeze) if freeze is not None else []),
        "candidates": [
            {"kind": c["kind"], "auc_oos": c.get("auc_oos"), "auc_train": c.get("auc_train"), "blend_w": c.get("blend_w")}
            for c in recipes
        ],
        "student_oos_buckets": _student_buckets(test, p_te),
        "teacher_oos_buckets": _p_up_buckets(test),
    }


def distill(rows: list[dict[str, Any]], *, generation: int) -> dict[str, Any]:
    d = algo_dir()
    d.mkdir(parents=True, exist_ok=True)
    paper_fp = str((_load_json(harvest_state_path(), {}) or {}).get("paper_fp") or "")
    harvest_fp = _rows_fingerprint(rows, paper_fp=paper_fp) if rows else ""
    recipe = distill_recipe()
    prev = _load_json(distill_state_path(), {}) or {}
    prev_path = Path(str(prev.get("path") or ""))
    ptr_early = _load_json(current_ptr(), {}) or {}
    live_ok = Path(str(ptr_early.get("path") or "")).is_file()
    if (
        _skip_unchanged()
        and rows
        and harvest_fp
        and str(prev.get("harvest_fp") or "") == harvest_fp
        and str(prev.get("recipe") or "") == recipe
        and prev.get("ok")
        and (prev_path.is_file() or (prev.get("skipped_not_better") and live_ok))
    ):
        prev["skipped_unchanged"] = True
        prev["utc"] = _now()
        prev["note"] = "same teacher fingerprint; kept prior pickle (did not mint a new gen)"
        _save_json(distill_state_path(), prev)
        log.info("[ALGO] distill skip unchanged fp=%s gen=%s", harvest_fp, prev.get("generation"))
        return prev
    fitted = _fit_student(rows)
    if not fitted:
        out = {"ok": False, "reason": "too_few_teacher_rows", "n_rows": len(rows), "phase": "distill", "utc": _now()}
        _save_json(distill_state_path(), out)
        return out
    ptr = _load_json(current_ptr(), {}) or {}
    if not _should_mint_student(fitted, ptr):
        live_path = str(ptr.get("path") or "")
        keep_path = str(prev.get("path") or live_path or "")
        if keep_path and not Path(keep_path).is_file():
            keep_path = live_path if Path(live_path).is_file() else ""
        keep_gen = int(ptr.get("generation") or prev.get("generation") or 0)
        if str(fitted.get("kind") or "") == "live_prior" and Path(live_path).is_file():
            try:
                oos = float(fitted.get("auc_oos"))
            except (TypeError, ValueError):
                oos = float("nan")
            if oos == oos:
                live_doc = dict(ptr)
                live_doc["auc_oos"] = oos
                live_doc["auc_in_sample"] = live_doc.get("auc_in_sample") or live_doc.get("auc")
                live_doc["auc_teacher_oos"] = fitted.get("auc_teacher_oos")
                live_doc["note"] = (
                    "auc_oos from freeze-train live_prior on harvest holdout; "
                    "auc is in-sample and is never the deploy floor"
                )
                _save_json(current_ptr(), live_doc)
        summary = {
            "ok": True,
            "phase": "distill",
            "utc": _now(),
            "generation": keep_gen or int(generation),
            "path": keep_path or None,
            "kind": fitted["kind"],
            "recipe": fitted.get("recipe") or recipe,
            "blend_w": fitted.get("blend_w"),
            "auc": fitted["auc"],
            "auc_oos": fitted.get("auc_oos"),
            "auc_train": fitted.get("auc_train"),
            "auc_in_sample": fitted.get("auc_in_sample"),
            "auc_teacher_oos": fitted.get("auc_teacher_oos"),
            "n_rows": fitted["n_rows"],
            "n_train": fitted.get("n_train"),
            "n_test": fitted.get("n_test"),
            "split": fitted.get("split"),
            "candidates": fitted.get("candidates"),
            "deploy_ready": False,
            "harvest_fp": harvest_fp,
            "paper_fp": paper_fp,
            "skipped_not_better": True,
            "skipped_unchanged": False,
            "note": (
                "did not mint a new pickle — OOS did not beat live auc_oos and teacher "
                "(in-sample auc is never the floor)"
            ),
        }
        _save_json(distill_state_path(), summary)
        log.info(
            "[ALGO] distill skip mint kind=%s oos=%s teacher=%s live_floor=%s",
            fitted.get("kind"),
            fitted.get("auc_oos"),
            fitted.get("auc_teacher_oos"),
            _live_oos_floor(ptr),
        )
        return summary
    bundle = {
        "clf": fitted["clf"],
        "calibrator": fitted.get("calibrator"),
        "blend_w": fitted.get("blend_w"),
        "kind": fitted["kind"],
        "features": fitted["features"],
        "recipe": fitted.get("recipe") or recipe,
        "auc": fitted["auc"],
        "auc_oos": fitted.get("auc_oos"),
        "auc_in_sample": fitted.get("auc_in_sample"),
        "generation": int(generation),
        "trained_utc": _now(),
        "source": "old_models_paper_sim",
        "n_rows": fitted["n_rows"],
        "deploy_ready": _should_mint_student(fitted, ptr),
        "freeze_train": True,
    }
    out_path = d / f"gen_{int(generation):05d}_algo.pkl"
    joblib.dump(bundle, out_path)
    summary = {
        "ok": True,
        "phase": "distill",
        "utc": _now(),
        "generation": int(generation),
        "path": str(out_path),
        "kind": fitted["kind"],
        "recipe": fitted.get("recipe") or recipe,
        "blend_w": fitted.get("blend_w"),
        "auc": fitted["auc"],
        "auc_oos": fitted.get("auc_oos"),
        "auc_train": fitted.get("auc_train"),
        "auc_in_sample": fitted.get("auc_in_sample"),
        "auc_teacher_oos": fitted.get("auc_teacher_oos"),
        "n_rows": fitted["n_rows"],
        "n_train": fitted.get("n_train"),
        "n_test": fitted.get("n_test"),
        "split": fitted.get("split"),
        "mean_fwd": fitted.get("mean_fwd"),
        "hit": fitted.get("hit"),
        "importances": (fitted.get("importances") or [])[:12],
        "candidates": fitted.get("candidates"),
        "student_oos_buckets": fitted.get("student_oos_buckets"),
        "teacher_oos_buckets": fitted.get("teacher_oos_buckets"),
        "deploy_ready": bool(bundle.get("deploy_ready")),
        "harvest_fp": harvest_fp,
        "paper_fp": paper_fp,
        "skipped_unchanged": False,
        "freeze_train": True,
        "note": "algorithm learns from teachers (calibrate/blend). OOS is freeze-train. current.json unchanged until phase 8.",
    }
    _save_json(distill_state_path(), summary)
    log.info(
        "[ALGO] distill gen=%d kind=%s oos=%.3f teacher_oos=%.3f n=%d → %s",
        generation,
        fitted["kind"],
        float(fitted.get("auc_oos") or 0),
        float(fitted.get("auc_teacher_oos") or 0),
        fitted["n_rows"],
        out_path.name,
    )
    return summary


def _load_current_bundle() -> dict[str, Any] | None:
    global _BUNDLE_CACHE
    ptr = _load_json(current_ptr(), {})
    path = Path(str(ptr.get("path") or ""))
    d = algo_dir()
    if not path.is_file():
        gens = sorted(d.glob("gen_*_algo.pkl")) if d.is_dir() else []
        if not gens:
            return None
        path = gens[-1]
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    if _BUNDLE_CACHE and _BUNDLE_CACHE[0] == mtime:
        return _BUNDLE_CACHE[1]
    try:
        bundle = joblib.load(path)
    except Exception:
        return None
    _BUNDLE_CACHE = (mtime, bundle)
    return bundle


def _load_bundle_at(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    try:
        return joblib.load(path)
    except Exception:
        return None


def _latest_per_ticker(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for r in rows:
        t = str(r.get("ticker") or "").upper()
        if not t:
            continue
        d = str(r.get("signal_date") or "")
        prev = best.get(t)
        if prev is None or d >= str(prev.get("signal_date") or ""):
            best[t] = r
    return list(best.values())


def _apply_bundle(rows: list[dict[str, Any]], bundle: dict[str, Any]) -> np.ndarray:
    rows = _enrich_rows(list(rows))
    teacher = _teacher_vec(rows)
    cal = bundle.get("calibrator")
    if cal is not None:
        try:
            teacher = np.clip(np.asarray(cal.predict(teacher), dtype=float), 0.01, 0.99)
        except Exception:
            pass
    kind = str(bundle.get("kind") or "")
    if kind in ("teacher", "calibrated") or bundle.get("clf") is None:
        return np.clip(teacher, 0.01, 0.99)
    feats = bundle.get("features") or FEATURE_COLS
    X = np.asarray(
        [[float(r.get(c) if r.get(c) is not None else _feat_default(str(c))) for c in feats] for r in rows],
        dtype=float,
    )
    student = np.clip(np.asarray(bundle["clf"].predict_proba(X)[:, 1], dtype=float), 0.01, 0.99)
    w = bundle.get("blend_w")
    w_f = 1.0 if w is None else max(0.0, min(1.0, float(w)))
    if kind.startswith("blend_") or w is not None:
        return np.clip(w_f * student + (1.0 - w_f) * teacher, 0.01, 0.99)
    return student


def _batch_p_up(rows: list[dict[str, Any]], bundle: dict[str, Any]) -> np.ndarray:
    return _apply_bundle(rows, bundle)


def student_p_up(row: dict[str, Any], bundle: dict[str, Any] | None = None) -> float | None:
    bundle = bundle if bundle is not None else _load_current_bundle()
    if not bundle:
        return None
    try:
        return float(_apply_bundle([row], bundle)[0])
    except Exception:
        return None


def _rank_corr(a: list[float], b: list[float]) -> float:
    if len(a) < 8:
        return float("nan")
    xa = np.asarray(a, dtype=float)
    xb = np.asarray(b, dtype=float)
    ra = np.argsort(np.argsort(xa))
    rb = np.argsort(np.argsort(xb))
    if np.std(ra) == 0 or np.std(rb) == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def pipeline_score(
    rows: list[dict[str, Any]],
    *,
    bundle_path: str | Path | None = None,
) -> dict[str, Any]:
    """Score latest-per-ticker teachers through the student. Live board only if deploy-ready."""
    uniq = _latest_per_ticker(rows)
    bpath = Path(bundle_path) if bundle_path else None
    bundle = _load_bundle_at(bpath) or _load_current_bundle()
    board: dict[str, dict[str, Any]] = {}
    if bundle and uniq:
        try:
            probs = _batch_p_up(uniq, bundle)
        except Exception:
            probs = np.array([student_p_up(r, bundle) or _fget(r, "p_up", 0.5) for r in uniq], dtype=float)
        for r, p in zip(uniq, probs):
            t = str(r.get("ticker") or "").upper()
            teacher = _fget(r, "p_up", 0.5)
            board[t] = {
                "p_up": float(p),
                "teacher_p_up": teacher,
                "fwd": _fget(r, "fwd", 0.0),
                "y": int(r.get("y") or 0),
                "signal_date": str(r.get("signal_date") or ""),
                "score": (float(p) - 0.5) * 2.0,
                "delta": float(p) - teacher,
            }
    else:
        for r in uniq:
            t = str(r.get("ticker") or "").upper()
            teacher = _fget(r, "p_up", 0.5)
            board[t] = {
                "p_up": teacher,
                "teacher_p_up": teacher,
                "fwd": _fget(r, "fwd", 0.0),
                "y": int(r.get("y") or 0),
                "signal_date": str(r.get("signal_date") or ""),
                "score": (teacher - 0.5) * 2.0,
                "delta": 0.0,
            }
    hot_n = int(os.getenv("ALGO_HOT_N", "40"))
    hot = sorted(board.items(), key=lambda kv: -float(kv[1]["p_up"]))[:hot_n]
    teacher_hot = sorted(board.items(), key=lambda kv: -float(kv[1]["teacher_p_up"]))[:hot_n]
    cold = sorted(board.items(), key=lambda kv: float(kv[1]["p_up"]))[:12]
    disagree = sorted(board.items(), key=lambda kv: -abs(float(kv[1].get("delta") or 0)))[:12]
    hot_names = [t for t, _ in hot]
    teacher_names = [t for t, _ in teacher_hot]
    overlap = [t for t in hot_names if t in set(teacher_names)]
    student_ps = [float(v["p_up"]) for v in board.values()]
    teacher_ps = [float(v["teacher_p_up"]) for v in board.values()]
    fwds = [float(v["fwd"]) for v in board.values()]
    ys = [int(v.get("y") or 0) for v in board.values()]
    gen = int((bundle or {}).get("generation") or 0)
    deploy_ready = bool((bundle or {}).get("deploy_ready"))
    ptr = _load_json(current_ptr(), {})
    live = (
        bool(deploy_ready)
        and Path(str(ptr.get("path") or "")).is_file()
        and int(ptr.get("generation") or 0) == gen
    )
    moments = {
        "n": len(board),
        "mean_student": float(np.mean(student_ps)) if student_ps else None,
        "mean_teacher": float(np.mean(teacher_ps)) if teacher_ps else None,
        "mean_fwd": float(np.mean(fwds)) if fwds else None,
        "hit": float(np.mean(ys)) if ys else None,
    }
    hot_board = {t: board[t] for t, _ in hot}
    payload = {
        "updated_utc": _now(),
        "phase": "pipeline",
        "generation": gen,
        "bundle_path": str(bpath) if bpath else None,
        "deploy_ready": deploy_ready,
        "live": live,
        "n": len(board),
        "hot": hot_names,
        "teacher_hot": teacher_names,
        "hot_overlap": overlap,
        "board": hot_board,
        "board_n": len(board),
        "moments": moments,
    }
    _save_json(candidate_board_path(), payload)
    if live:
        live_doc = dict(payload)
        live_doc["live"] = True
        _save_json(board_path(), live_doc)
    summary = {
        "ok": True,
        "phase": "pipeline",
        "utc": _now(),
        "generation": gen,
        "live": live,
        "deploy_ready": deploy_ready,
        "n": len(board),
        "hot": hot_names[:12],
        "teacher_hot": teacher_names[:12],
        "hot_overlap_n": len(overlap),
        "hot_overlap": overlap[:12],
        "cold": [t for t, _ in cold],
        "disagree": [
            {
                "ticker": t,
                "student": round(float(v["p_up"]), 4),
                "teacher": round(float(v["teacher_p_up"]), 4),
                "delta": round(float(v.get("delta") or 0), 4),
            }
            for t, v in disagree[:8]
        ],
        "mean_student_p_up": float(np.mean(student_ps)) if student_ps else None,
        "mean_teacher_p_up": float(np.mean(teacher_ps)) if teacher_ps else None,
        "moments": moments,
        "spearman_student_teacher": _rank_corr(student_ps, teacher_ps),
        "hot_hit": float(np.mean([int(board[t].get("y") or 0) for t in hot_names])) if hot_names else None,
        "teacher_hot_hit": float(np.mean([int(board[t].get("y") or 0) for t in teacher_names])) if teacher_names else None,
        "hot_mean_fwd": float(np.mean([float(board[t]["fwd"]) for t in hot_names])) if hot_names else None,
        "teacher_hot_mean_fwd": float(np.mean([float(board[t]["fwd"]) for t in teacher_names])) if teacher_names else None,
        "all_hit": float(np.mean(ys)) if ys else None,
        "all_mean_fwd": float(np.mean(fwds)) if fwds else None,
        "candidate": str(candidate_board_path()),
        "live_board": str(board_path()) if live else None,
        "note": "candidate board only unless deploy_ready and current.json matches this generation",
    }
    hold = set(((_load_json(distill_state_path(), {}) or {}).get("split") or {}).get("hold_dates") or [])
    if hold:
        held = {t: v for t, v in board.items() if str(v.get("signal_date") or "") in hold}
        if held:
            h_hot = [t for t, _ in sorted(held.items(), key=lambda kv: -float(kv[1]["p_up"]))[:hot_n]]
            t_hot = [t for t, _ in sorted(held.items(), key=lambda kv: -float(kv[1]["teacher_p_up"]))[:hot_n]]
            summary["holdout_dates"] = sorted(hold)
            summary["holdout_n"] = len(held)
            summary["holdout_hot"] = h_hot[:12]
            summary["holdout_hot_hit"] = float(np.mean([int(held[t].get("y") or 0) for t in h_hot]))
            summary["holdout_hot_mean_fwd"] = float(np.mean([float(held[t]["fwd"]) for t in h_hot]))
            summary["holdout_teacher_hot_hit"] = float(np.mean([int(held[t].get("y") or 0) for t in t_hot]))
            summary["holdout_teacher_hot_mean_fwd"] = float(np.mean([float(held[t]["fwd"]) for t in t_hot]))
            summary["note"] = (
                "candidate only; holdout hot uses the saved full-data pickle "
                "(seen those dates). Live board unchanged. OOS AUC stays the phase-4 freeze-train number."
            )
    _save_json(pipeline_phase_path(), summary)
    log.info(
        "[ALGO] pipeline gen=%d n=%d live=%s overlap=%d/%d hot_hit=%.3f teacher_hot_hit=%.3f",
        gen,
        len(board),
        live,
        len(overlap),
        hot_n,
        float(summary.get("hot_hit") or 0),
        float(summary.get("teacher_hot_hit") or 0),
    )
    return summary


def algo_rank_boost(ticker: str, features: dict[str, Any] | None = None) -> tuple[float, dict[str, Any]]:
    """Live rank additive from the one global student. Scores any stock with features."""
    from analytics.algo_universe import live_rank_boost

    return live_rank_boost(ticker, features)


def algo_overlay_boost(ticker: str) -> tuple[float, dict[str, Any]]:
    """Live overlay tilt only. Staged candidate (live is not True) is a no-op."""
    if os.getenv("USE_ALGO_PIPELINE", "true").lower() not in ("1", "true", "yes"):
        return 0.0, {"head": "algo_overlay", "off": True}
    doc = _load_json(overlay_path(), {})
    if doc.get("live") is not True:
        return 0.0, {"head": "algo_overlay", "staged": True}
    tilt = float((doc.get("tilts") or {}).get(str(ticker).upper()) or 0.0)
    if abs(tilt) < 1e-12:
        return 0.0, {"head": "algo_overlay", "miss": True}
    return float(tilt), {"head": "algo_overlay", "tilt": tilt}


def quality_state_path() -> Path:
    return _path("ALGO_QUALITY_STATE", "data", "intel", "algo_quality.json")


def quality_queue_path() -> Path:
    return _path("ALGO_QUALITY_FILE", "data", "train", "algo_quality_weak.txt")


def _quality_queue(catalog: dict[str, Any]) -> list[str]:
    """Weak heads only. Missing intraday is phase 2 cover, not quality."""
    names = list(catalog.get("weak_sample") or [])
    return list(dict.fromkeys(str(s).upper() for s in names if str(s).strip()))


def _backup_pickles(symbols: list[str]) -> list[str]:
    bak = ROOT / "data" / "train" / "algo_quality_bak"
    bak.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for t in symbols:
        for rel in (f"models/{t}_model.pkl", f"models/meta/{t}_meta.pkl"):
            src = ROOT / rel
            if not src.is_file():
                continue
            dest = bak / src.name
            try:
                import shutil

                shutil.copy2(src, dest)
                saved.append(str(dest))
            except OSError:
                continue
    return saved


def quality_retrain(catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    """Phase 6: enqueue weak top100 heads on the existing strong-retrain path.

    Does not shrink the universe or delete live pickles (copies first). Missing
    intraday stays on the cover trainer.
    """
    catalog = catalog or {}
    min_top20 = float(os.getenv("RETRAIN_MIN_TOP20", "0.6"))
    min_meta = float(os.getenv("MIN_META_AUC", "0.52"))
    weak: dict[str, list[str]] = {}
    if os.getenv("ALGO_QUALITY_SCAN", "true").lower() in ("1", "true", "yes"):
        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "retrain_weak_models",
                ROOT / "tools" / "retrain_weak_models.py",
            )
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                prev = os.environ.get("RETRAIN_SCAN_NULL_HEADS")
                os.environ["RETRAIN_SCAN_NULL_HEADS"] = "false"
                try:
                    weak = mod.find_weak_symbols(
                        min_top20=min_top20,
                        min_meta=min_meta,
                        top100_only=os.getenv("ALGO_WEAK_TOP100_ONLY", "true").lower()
                        in ("1", "true", "yes"),
                    )
                finally:
                    if prev is None:
                        os.environ.pop("RETRAIN_SCAN_NULL_HEADS", None)
                    else:
                        os.environ["RETRAIN_SCAN_NULL_HEADS"] = prev
        except Exception as e:
            log.debug("[ALGO] quality weak scan skipped: %s", e)
    for s in _quality_queue(catalog):
        weak.setdefault(s, list(weak.get(s) or ["catalog"]))
    names = sorted(weak)
    qpath = quality_queue_path()
    qpath.parent.mkdir(parents=True, exist_ok=True)
    qpath.write_text("\n".join(names) + ("\n" if names else ""), encoding="utf-8")
    backups = _backup_pickles(names) if names else []
    out: dict[str, Any] = {
        "phase": "quality",
        "utc": _now(),
        "n": len(names),
        "symbols": names,
        "reasons": {t: weak[t] for t in names},
        "queue_file": str(qpath),
        "backups": len(backups),
        "min_top20": min_top20,
        "min_meta": min_meta,
    }
    if not names:
        out["note"] = "no_weak_heads"
        _save_json(quality_state_path(), out)
        return out
    if _pid_running("retrain-weak-loop"):
        out["note"] = "already_running"
        _save_json(quality_state_path(), out)
        return out
    if os.getenv("ALGO_KICK_TRAIN", "true").lower() not in ("1", "true", "yes"):
        out["note"] = "queued_file"
        _save_json(quality_state_path(), out)
        return out
    run = ROOT / "run_all.sh"
    logf = ROOT / "logs" / "algo_quality_retrain.log"
    logf.parent.mkdir(parents=True, exist_ok=True)
    try:
        with logf.open("a", encoding="utf-8") as fh:
            subprocess.Popen(
                ["bash", str(run), "retrain-weak-until"],
                cwd=str(ROOT),
                stdout=fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env={
                    **os.environ,
                    "FRESH_MODEL_REBUILD": "false",
                    "TRAIN_PURGE_ARTIFACTS": "false",
                    "KEEP_EXISTING_PICKLE": "true",
                },
            )
        out["note"] = "spawned_retrain_weak_until"
        log.info("[ALGO] quality spawned retrain-weak-until n=%d", len(names))
    except Exception as e:
        out["note"] = f"spawn_failed:{e}"
        log.warning("[ALGO] quality spawn failed: %s", e)
    _save_json(quality_state_path(), out)
    return out


def fuse(
    generation: int,
    distill_meta: dict[str, Any],
    pipeline_meta: dict[str, Any],
    quality_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Phase 7: ULE-friendly overlay snapshot. Live tilts apply only after phase 8."""
    quality_meta = quality_meta or {}
    deploy_ready = bool(distill_meta.get("deploy_ready") or pipeline_meta.get("deploy_ready"))
    ptr = _load_json(current_ptr(), {})
    live = bool(deploy_ready) and Path(str(ptr.get("path") or "")).is_file() and (
        int(ptr.get("generation") or 0) == int(generation)
    )
    ule = _load_json(ROOT / "data" / "intel" / "ule_state.json", {})
    skill = ule.get("skill") if isinstance(ule.get("skill"), dict) else {}
    board = (_load_json(candidate_board_path(), {}) or {}).get("board") or {}
    cap = float(os.getenv("RANK_W_ALGO", "0.12"))
    tilts: dict[str, float] = {}
    for t, rec in board.items():
        if not isinstance(rec, dict):
            continue
        d = float(rec.get("delta") or 0.0)
        if abs(d) < 0.02:
            continue
        tilts[str(t).upper()] = float(max(-cap, min(cap, d * 0.5)))
    top_tilts = sorted(tilts.items(), key=lambda kv: -abs(kv[1]))[:16]
    overlay_gen = 0
    try:
        ov = ROOT / "data" / "self_improve" / "strategy_overlay.py"
        if ov.is_file():
            for ln in ov.read_text(encoding="utf-8", errors="ignore").splitlines()[:20]:
                if ln.startswith("GENERATION"):
                    digits = "".join(ch for ch in ln.split("=", 1)[-1] if ch.isdigit())
                    if digits:
                        overlay_gen = int(digits)
                    break
    except Exception:
        pass
    payload = {
        "generation": int(generation),
        "live": live,
        "deploy_ready": deploy_ready,
        "auc": distill_meta.get("auc_oos") or distill_meta.get("auc"),
        "auc_oos": distill_meta.get("auc_oos"),
        "auc_teacher_oos": distill_meta.get("auc_teacher_oos"),
        "kind": distill_meta.get("kind"),
        "hot": list(pipeline_meta.get("hot") or [])[:40],
        "teacher_hot": list(pipeline_meta.get("teacher_hot") or [])[:40],
        "cold": list(pipeline_meta.get("cold") or [])[:16],
        "quality_weak": list(quality_meta.get("symbols") or [])[:16],
        "strategy_overlay_generation": overlay_gen,
        "ule": {
            "channel": "algo_student_staged",
            "math": "LEA",
            "skill_snapshot": {
                k: float(v) for k, v in skill.items() if isinstance(v, (int, float))
            },
            "n_updates": ule.get("n_updates"),
            "n_cycles": ule.get("n_cycles"),
        },
        "tilt_n": len(tilts),
        "tilts": tilts,
        "updated_utc": _now(),
        "source": "algo_generation",
        "note": "staged ULE overlay; not applied to rank_tilt / live ULE until phase 8",
    }
    _save_json(overlay_candidate_path(), payload)
    if live:
        live_doc = dict(payload)
        live_doc["live"] = True
        _save_json(overlay_path(), live_doc)
    summary = {
        "ok": True,
        "phase": "fuse",
        "utc": _now(),
        "generation": int(generation),
        "live": live,
        "deploy_ready": deploy_ready,
        "auc_oos": payload.get("auc_oos"),
        "auc_teacher_oos": payload.get("auc_teacher_oos"),
        "hot": payload["hot"][:12],
        "quality_weak": payload["quality_weak"],
        "strategy_overlay_generation": overlay_gen,
        "ule_skill": payload["ule"]["skill_snapshot"],
        "tilt_n": len(tilts),
        "tilts_top": [{"ticker": t, "tilt": round(v, 4)} for t, v in top_tilts[:8]],
        "candidate": str(overlay_candidate_path()),
        "live_overlay": str(overlay_path()) if live else None,
        "note": payload["note"],
    }
    _save_json(fuse_state_path(), summary)
    log.info(
        "[ALGO] fuse gen=%d live=%s tilts=%d overlay_py=%d",
        generation,
        live,
        len(tilts),
        overlay_gen,
    )
    return summary


def _fuse(
    generation: int,
    distill_meta: dict[str, Any],
    pipeline_meta: dict[str, Any],
    quality_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return fuse(generation, distill_meta, pipeline_meta, quality_meta)


def _live_oos_floor(prev: dict[str, Any] | None = None) -> float:
    """Live deploy floor is freeze-train auc_oos. Never use in-sample `auc` (gen2 0.905)."""
    prev = prev if prev is not None else (_load_json(current_ptr(), {}) or {})
    for key in ("auc_oos", "auc_teacher_oos"):
        v = prev.get(key)
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f == f:
            return f
    return float("nan")


def _oos_beats_priors(distill_meta: dict[str, Any], prev: dict[str, Any] | None = None) -> bool:
    """Newer gens promote only if freeze-train OOS beats teacher AND live auc_oos."""
    kind = str(distill_meta.get("kind") or "")
    if kind in ("teacher", "live_prior", ""):
        return False
    oos = distill_meta.get("auc_oos", distill_meta.get("auc"))
    try:
        oos_f = float(oos)
    except (TypeError, ValueError):
        return False
    if oos_f != oos_f:
        return False
    floors: list[float] = []
    teacher = distill_meta.get("auc_teacher_oos")
    try:
        tea_f = float(teacher)
        if tea_f == tea_f:
            floors.append(tea_f)
    except (TypeError, ValueError):
        pass
    live = _live_oos_floor(prev)
    if live == live:
        floors.append(live)
    if not floors:
        return False
    return oos_f > max(floors) + 1e-6


def _should_mint_student(fitted: dict[str, Any], prev: dict[str, Any] | None = None) -> bool:
    """Do not write a gen pickle unless it is strictly better than live + teacher."""
    return _oos_beats_priors(fitted, prev)


def _oos_beats_teacher(distill_meta: dict[str, Any]) -> bool:
    """True only if a *new* recipe strictly beats teacher and live OOS. Passthrough is not a deploy."""
    return _oos_beats_priors(distill_meta)


def deploy(
    generation: int,
    distill_meta: dict[str, Any],
    pipeline_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Phase 8: promote current.json only if freeze-train OOS beats teacher and live auc_oos."""
    pipeline_meta = pipeline_meta or {}
    prev = _load_json(current_ptr(), {})
    path = str(distill_meta.get("path") or "")
    oos = distill_meta.get("auc_oos", distill_meta.get("auc"))
    teacher = distill_meta.get("auc_teacher_oos")
    live_floor = _live_oos_floor(prev)
    ready = _oos_beats_priors(distill_meta, prev)
    out: dict[str, Any] = {
        "ok": False,
        "phase": "deploy",
        "utc": _now(),
        "generation": int(generation),
        "deployed": False,
        "auc_oos": oos,
        "auc_teacher_oos": teacher,
        "auc_live_oos": live_floor if live_floor == live_floor else None,
        "path": path or None,
        "previous": {
            "generation": prev.get("generation"),
            "path": prev.get("path"),
            "auc": prev.get("auc"),
            "auc_oos": prev.get("auc_oos"),
        },
    }
    p = Path(path) if path else None
    if not p or not p.is_file():
        out["note"] = "no_model"
        out["reason"] = "no_model"
        _save_json(deploy_state_path(), out)
        return out
    kind = str(distill_meta.get("kind") or "")
    if kind in ("teacher", "live_prior"):
        out["note"] = "refused_teacher_passthrough" if kind == "teacher" else "refused_live_prior"
        out["reason"] = "passthrough is not a new algorithm"
        _save_json(deploy_state_path(), out)
        log.info("[ALGO] deploy REFUSED gen=%d kind=%s — current stays gen=%s", generation, kind, prev.get("generation"))
        return out
    if not ready:
        try:
            oos_f = float(oos)
            tea_f = float(teacher)
        except (TypeError, ValueError):
            oos_f, tea_f = float("nan"), float("nan")
        if live_floor == live_floor and oos_f == oos_f and oos_f > tea_f + 1e-6 and oos_f <= live_floor + 1e-6:
            out["note"] = "refused_oos_below_live"
            out["reason"] = "student_oos <= live_auc_oos"
        else:
            out["note"] = "refused_oos_below_teacher"
            out["reason"] = "student_oos < teacher_oos"
        _save_json(deploy_state_path(), out)
        log.info(
            "[ALGO] deploy REFUSED gen=%d oos=%s teacher=%s live=%s — current stays gen=%s",
            generation,
            oos,
            teacher,
            live_floor if live_floor == live_floor else None,
            prev.get("generation"),
        )
        return out

    _save_json(
        current_ptr(),
        {
            "generation": int(generation),
            "path": str(p),
            "auc": oos,
            "auc_oos": oos,
            "auc_in_sample": distill_meta.get("auc_in_sample"),
            "auc_teacher_oos": teacher,
            "kind": distill_meta.get("kind"),
            "deployed_utc": _now(),
            "note": "auc and auc_oos are freeze-train OOS; never compare against in-sample",
        },
    )
    cand = _load_json(candidate_board_path(), {})
    if isinstance(cand, dict) and cand.get("board"):
        cand["live"] = True
        cand["deployed_utc"] = _now()
        _save_json(board_path(), cand)
        out["live_board"] = str(board_path())
    ov = _load_json(overlay_candidate_path(), {})
    if isinstance(ov, dict) and ov:
        ov["live"] = True
        ov["deployed_utc"] = _now()
        _save_json(overlay_path(), ov)
        out["live_overlay"] = str(overlay_path())
    out["ok"] = True
    out["deployed"] = True
    out["note"] = "promoted_current_board_overlay"
    _save_json(deploy_state_path(), out)
    log.info("[ALGO] deploy gen=%d oos=%s → %s", generation, oos, p.name)
    return out


def _deploy(
    generation: int,
    distill_meta: dict[str, Any],
    pipeline_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return deploy(generation, distill_meta, pipeline_meta)


def _failed_no_pickle(limit: int) -> list[str]:
    ck = _load_json(_path("ALGO_TRAIN_CHECKPOINT", "data", "train_checkpoint.json"), {})
    failed = ck.get("failed") or {}
    out: list[str] = []
    models = ROOT / "models"
    if isinstance(failed, dict):
        for t in sorted(str(x).upper() for x in failed):
            if not t:
                continue
            p = models / f"{t}_model.pkl"
            try:
                if p.is_file() and p.stat().st_size >= 1000:
                    continue
            except OSError:
                pass
            out.append(t)
            if len(out) >= limit:
                return out
    if len(out) >= limit:
        return out
    if os.getenv("ALGO_UNIVERSE_GAPS", "true").lower() not in ("1", "true", "yes"):
        return out
    try:
        from universe_provider import load_universe_with_cap

        universe = load_universe_with_cap(max_symbols=None, refresh=False)
    except Exception as e:
        log.debug("[ALGO] universe gaps skipped: %s", e)
        return out
    have = set(out)
    for t in sorted(str(s).upper() for s in (universe or []) if str(s).strip()):
        if t in have:
            continue
        p = models / f"{t}_model.pkl"
        try:
            if p.is_file() and p.stat().st_size >= 1000:
                continue
        except OSError:
            pass
        out.append(t)
        have.add(t)
        if len(out) >= limit:
            break
    return out


def make_batch(
    catalog: dict[str, Any] | None = None,
    pipeline_meta: dict[str, Any] | None = None,
    quality_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Phase 9: next daily clip. Weak heads first, then checkpoint gaps. No live-rank flip."""
    catalog = catalog or {}
    quality_meta = quality_meta or {}
    n = _unbounded_cap("ALGO_BATCH_SIZE", "0")
    weak = [
        str(s).upper()
        for s in (quality_meta.get("symbols") or catalog.get("weak_sample") or [])
        if str(s).strip()
    ]
    gaps = _failed_no_pickle(max(n, 1))
    ordered: list[str] = []
    roles: dict[str, str] = {}
    for u in weak:
        if u not in ordered:
            ordered.append(u)
            roles[u] = "quality_weak"
        if len(ordered) >= n:
            break
    if len(ordered) < n:
        for u in gaps:
            if u in ordered:
                continue
            ordered.append(u)
            roles[u] = "daily_gap"
            if len(ordered) >= n:
                break
    busy = trainers_busy()
    prev_file = batch_path()
    if busy and prev_file.is_file():
        prev_syms = [
            ln.strip().upper()
            for ln in prev_file.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        for u in prev_syms:
            if len(ordered) >= n:
                break
            if u in ordered:
                continue
            ordered.append(u)
            roles.setdefault(u, "queued_keep")
    path = _write_batch(ordered)
    n_weak = sum(1 for s in ordered if roles.get(s) == "quality_weak")
    n_gap = sum(1 for s in ordered if roles.get(s) == "daily_gap")
    out = {
        "ok": True,
        "phase": "batch",
        "utc": _now(),
        "n": len(ordered),
        "n_quality_weak": n_weak,
        "n_daily_gap": n_gap,
        "symbols": ordered,
        "roles": roles,
        "file": str(path),
        "trainers_busy": busy,
        "daily_failed_no_pickle": len(gaps),
        "note": (
            "unbounded remaining daily gaps — no 40-name ceiling. "
            "phase 10 kicks if trainers idle. FRESH_MODEL_REBUILD false. live rank unchanged."
        ),
    }
    _save_json(batch_state_path(), out)
    log.info("[ALGO] batch n=%d weak=%d gap=%d file=%s", len(ordered), n_weak, n_gap, path.name)
    return out


def _next_batch(
    catalog: dict[str, Any],
    pipeline_meta: dict[str, Any],
    quality_meta: dict[str, Any] | None = None,
) -> list[str]:
    return list(make_batch(catalog, pipeline_meta, quality_meta).get("symbols") or [])


def _append_ledger(entry: dict[str, Any]) -> None:
    doc = _load_json(ledger_path(), {"entries": []})
    if not isinstance(doc, dict):
        doc = {"entries": []}
    entries = list(doc.get("entries") or [])
    entries.append(entry)
    doc["entries"] = entries[-80:]
    doc["updated_utc"] = _now()
    _save_json(ledger_path(), doc)


def finalize(
    *,
    generation: int | None = None,
    distill_meta: dict[str, Any] | None = None,
    pipeline_meta: dict[str, Any] | None = None,
    kick: str | None = None,
) -> dict[str, Any]:
    """Phase 11: health + ledger. Never flips live rank, never deletes models."""
    distill_meta = distill_meta or _load_json(distill_state_path(), {}) or {}
    pipeline_meta = pipeline_meta or _load_json(pipeline_phase_path(), {}) or {}
    ptr = _load_json(current_ptr(), {})
    st = load_state()
    gen = int(generation if generation is not None else (st.get("generation") or distill_meta.get("generation") or 0))
    busy = trainers_busy()
    loop = _pid_running("algo-pipeline")
    batch_syms: list[str] = []
    bp = batch_path()
    if bp.is_file():
        batch_syms = [ln.strip().upper() for ln in bp.read_text(encoding="utf-8").splitlines() if ln.strip()]
    pickles = sorted(algo_dir().glob("gen_*_algo.pkl")) if algo_dir().is_dir() else []
    harvest = _load_json(harvest_state_path(), {}) or {}
    deploy_doc = _load_json(deploy_state_path(), {}) or {}
    paper_fp = str(harvest.get("paper_fp") or _paper_fingerprint())
    if harvest and not harvest.get("paper_fp"):
        harvest["paper_fp"] = paper_fp
        harvest["harvest_fp"] = harvest.get("harvest_fp") or _fingerprint_from_harvest_summary(harvest, paper_fp)
        _save_json(harvest_state_path(), harvest)
    if distill_meta.get("ok") and not distill_meta.get("harvest_fp"):
        distill_meta["harvest_fp"] = _fingerprint_from_harvest_summary(harvest, paper_fp)
        distill_meta["paper_fp"] = paper_fp
        _save_json(distill_state_path(), distill_meta)
    oos = distill_meta.get("auc_oos")
    teacher = distill_meta.get("auc_teacher_oos")
    skipped = bool(distill_meta.get("skipped_unchanged") or harvest.get("cached") or harvest.get("deferred_busy"))
    extras = [
        "harvest_cache",
        "skip_unchanged_teachers",
        "freeze_train_pickle",
        "universe_daily_gaps",
        "keep_queued_clip",
        "scan_ttl",
        "cycle_lock",
        "overlay_boost_live_only",
    ]
    out = {
        "ok": True,
        "phase": "finalize",
        "utc": _now(),
        "generation": gen,
        "live_generation": ptr.get("generation"),
        "staged_generation": distill_meta.get("generation"),
        "deployed": False,
        "auc_oos": oos,
        "auc_teacher_oos": teacher,
        "deploy_ready": bool(distill_meta.get("deploy_ready")),
        "last_deploy_note": deploy_doc.get("note"),
        "kick": kick or (st.get("last") or {}).get("kick"),
        "trainers_busy": busy,
        "loop_running": loop,
        "batch_n": len(batch_syms),
        "batch_head": batch_syms[:8],
        "harvest_n": harvest.get("n_rows"),
        "harvest_cached": bool(harvest.get("cached") or harvest.get("deferred_busy")),
        "skipped_unchanged": skipped,
        "student_pickles": [p.name for p in pickles],
        "current_path": ptr.get("path"),
        "extras": extras,
        "note": (
            "factory looping; live rank stays on current.json. "
            "new gens mint only when paper_sim teachers change. "
            "FRESH_MODEL_REBUILD false. models/ not touched."
        ),
    }
    _append_ledger(
        {
            "generation": gen,
            "live_generation": ptr.get("generation"),
            "auc_oos": oos,
            "auc_teacher_oos": teacher,
            "deployed": False,
            "skipped_unchanged": skipped,
            "kick": out["kick"],
            "batch_n": len(batch_syms),
            "utc": _now(),
        }
    )
    _save_json(finalize_state_path(), out)
    log.info(
        "[ALGO] finalize gen=%s live=%s skip=%s batch=%d loop=%s busy=%s",
        gen,
        ptr.get("generation"),
        skipped,
        len(batch_syms),
        loop,
        busy,
    )
    return out


def _core_name(phase: str) -> str:
    if phase == "complete":
        return "complete"
    if phase.startswith("w") and "_" in phase:
        return phase.split("_", 1)[1]
    return phase


def _wave_of(phase: str) -> int:
    if phase == "complete":
        return N_WAVES + 1
    if phase.startswith("w") and len(phase) > 1 and phase[1].isdigit():
        return int(phase[1])
    return 1


def complete(
    *,
    generation: int,
    distill_meta: dict[str, Any],
    catalog: dict[str, Any],
    pipeline_meta: dict[str, Any],
    kick: str,
    n_phases: int,
) -> dict[str, Any]:
    """Phase 100: seal the 100-phase catalog. Never flips live rank. Trainers keep running."""
    ptr = _load_json(current_ptr(), {}) or {}
    busy = trainers_busy()
    batch_syms: list[str] = []
    bp = batch_path()
    if bp.is_file():
        batch_syms = [ln.strip().upper() for ln in bp.read_text(encoding="utf-8").splitlines() if ln.strip()]
    out = {
        "ok": True,
        "phase": "complete",
        "phase_index": 100,
        "waves": N_WAVES,
        "n_phases": n_phases,
        "utc": _now(),
        "generation": generation,
        "live_generation": ptr.get("generation"),
        "staged_generation": generation,
        "deployed": False,
        "auc_oos": distill_meta.get("auc_oos") or distill_meta.get("auc"),
        "auc_teacher_oos": distill_meta.get("auc_teacher_oos"),
        "deploy_ready": bool(distill_meta.get("deploy_ready")),
        "kick": kick,
        "trainers_busy": busy,
        "batch_n": len(batch_syms),
        "missing_intraday": int(catalog.get("missing_intraday") or 0),
        "missing_lstm": int(catalog.get("missing_lstm") or 0),
        "daily_models": int(catalog.get("daily_models") or 0),
        "intraday_models": int(catalog.get("intraday_models") or 0),
        "lstm_models": int(catalog.get("lstm_models") or 0),
        "cover_is_teachers_not_algorithm": True,
        "algorithm_live_for_all_stocks": True,
        "hot": (pipeline_meta.get("hot") or [])[:8],
        "current_path": ptr.get("path"),
        "note": (
            "100-phase catalog finished this pass. missing_intraday is a teacher-pickle "
            "backlog (checkpoint resume); the live algorithm already scores every ticker "
            "from features and does not wait on those heads. Newer gens promote only if "
            "freeze-train OOS beats teacher AND live auc_oos (never in-sample auc). "
            "FRESH_MODEL_REBUILD false. models/ not touched."
        ),
    }
    _save_json(complete_state_path(), out)
    log.info(
        "[ALGO] complete phase=100 gen=%s live=%s miss_i=%s batch=%d busy=%s",
        generation,
        ptr.get("generation"),
        out["missing_intraday"],
        len(batch_syms),
        busy,
    )
    return out


def _refresh_wave(
    wave: int,
    core: str,
    ctx: dict[str, Any],
) -> dict[str, Any]:
    """Waves 2–9 re-kick coverage without a second full-universe daily train."""
    focus = WAVE_FOCUS[wave - 1] if 1 <= wave <= len(WAVE_FOCUS) else f"wave_{wave}"
    catalog = ctx.get("catalog") or {}
    distill_meta = ctx.get("distill_meta") or {}
    pipeline_meta = ctx.get("pipeline_meta") or {}
    q = ctx.get("q") or {}
    gen = int(ctx.get("gen") or 0)
    batch = list(ctx.get("batch") or [])
    base: dict[str, Any] = {"wave": wave, "focus": focus, "core": core}

    if core == "scan" and wave == 9:
        catalog = scan_upgrades()
        ctx["catalog"] = catalog
        base.update(
            {
                "daily": catalog.get("daily_models"),
                "missing_intraday": catalog.get("missing_intraday"),
                "missing_lstm": catalog.get("missing_lstm"),
                "weak": catalog.get("weak_heads"),
            }
        )
        return base
    if core == "cover":
        cover = cover_gaps(catalog)
        ctx["cover"] = cover
        base.update({"note": cover.get("note"), "n": cover.get("missing_intraday")})
        return base
    if core == "harvest" and wave == 4:
        rows = harvest_teachers()
        if rows:
            ctx["rows"] = rows
        base.update({"n_rows": len(ctx.get("rows") or []), "refreshed": bool(rows)})
        return base
    if core == "distill" and wave == 5:
        rows = list(ctx.get("rows") or [])
        if rows and not _skip_unchanged():
            meta = distill(rows, generation=gen)
            ctx["distill_meta"] = meta
            base.update(meta)
        else:
            base.update({"reused": True, "generation": gen, "auc_oos": distill_meta.get("auc_oos")})
        return base
    if core == "quality":
        q2 = quality_retrain(catalog)
        ctx["q"] = q2
        base.update({"n": q2.get("n"), "note": q2.get("note")})
        return base
    if core == "fuse":
        fused = fuse(gen, distill_meta, pipeline_meta, q)
        ctx["fused"] = fused
        base.update({"ok": fused.get("ok"), "live": fused.get("live")})
        return base
    if core == "deploy":
        dep = deploy(gen, distill_meta, pipeline_meta) if distill_meta.get("ok") else {"ok": False, "reason": "skip"}
        ctx["dep"] = dep
        base.update({"ok": dep.get("ok"), "reason": dep.get("reason") or dep.get("note")})
        return base
    if core == "batch":
        bmeta = make_batch(catalog, pipeline_meta, q)
        ctx["bmeta"] = bmeta
        ctx["batch"] = list(bmeta.get("symbols") or [])
        base.update({"n": bmeta.get("n") or len(ctx["batch"]), "note": bmeta.get("note")})
        return base
    if core == "advance":
        adv = advance(list(ctx.get("batch") or batch), generation=gen, ensure_loop=False)
        ctx["adv"] = adv
        ctx["kick"] = str(adv.get("kick") or ctx.get("kick") or "no_batch")
        base.update({"kick": ctx["kick"], "trainers_busy": adv.get("trainers_busy")})
        return base
    if core == "pipeline":
        base.update({"n": pipeline_meta.get("n"), "hot": (pipeline_meta.get("hot") or [])[:8]})
        return base
    if core == "harvest":
        base.update({"n_rows": len(ctx.get("rows") or [])})
        return base
    if core == "distill":
        base.update(
            {
                "reused": True,
                "generation": gen,
                "auc_oos": distill_meta.get("auc_oos") or distill_meta.get("auc"),
                "deploy_ready": distill_meta.get("deploy_ready"),
            }
        )
        return base
    if core == "scan":
        base.update(
            {
                "daily": catalog.get("daily_models"),
                "missing_intraday": catalog.get("missing_intraday"),
                "weak": catalog.get("weak_heads"),
            }
        )
        return base
    if core == "finalize":
        ptr = _load_json(current_ptr(), {}) or {}
        base.update(
            {
                "live_generation": ptr.get("generation"),
                "deployed": False,
                "note": "wave seal; live rank unchanged",
            }
        )
        return base
    return base


def run_generation() -> dict[str, Any]:
    """Run all 100 phases once, persist state, return summary."""
    st = load_state()
    results: list[PhaseResult] = []
    catalog = scan_upgrades()
    results.append(PhaseResult("scan", True, {"daily": catalog.get("daily_models"), "weak": catalog.get("weak_heads")}))

    cover = cover_gaps(catalog)
    results.append(
        PhaseResult(
            "cover",
            True,
            {
                "note": cover.get("note"),
                "n": cover.get("missing_intraday"),
                "lstm": cover.get("missing_lstm"),
                "status": cover.get("status"),
                "algorithm_independent": cover.get("algorithm_independent"),
            },
        )
    )

    rows = harvest_teachers()
    results.append(
        PhaseResult(
            "harvest",
            bool(rows) or bool((_load_json(harvest_state_path(), {}) or {}).get("n_rows")),
            {"n_rows": len(rows), "cached": bool((_load_json(harvest_state_path(), {}) or {}).get("cached")), "state": str(harvest_state_path())},
        )
    )

    prev_distill = _load_json(distill_state_path(), {}) or {}
    paper_fp = str((_load_json(harvest_state_path(), {}) or {}).get("paper_fp") or "")
    harvest_fp = _rows_fingerprint(rows, paper_fp=paper_fp) if rows else str(prev_distill.get("harvest_fp") or "")
    same_teachers = bool(
        _skip_unchanged()
        and harvest_fp
        and str(prev_distill.get("harvest_fp") or "") == harvest_fp
        and str(prev_distill.get("recipe") or "") == distill_recipe()
        and prev_distill.get("ok")
        and (
            Path(str(prev_distill.get("path") or "")).is_file()
            or prev_distill.get("skipped_not_better")
            or prev_distill.get("skipped_unchanged")
        )
    )
    if not rows and prev_distill.get("ok"):
        gen = int(st.get("generation") or prev_distill.get("generation") or 0)
        distill_meta = dict(prev_distill)
        distill_meta["skipped_unchanged"] = True
        distill_meta["note"] = "harvest deferred; kept prior student"
    elif same_teachers:
        gen = int(st.get("generation") or prev_distill.get("generation") or 1)
        distill_meta = distill(rows, generation=gen)
        gen = int(distill_meta.get("generation") or gen)
    else:
        next_gen = int(st.get("generation") or 0) + 1
        distill_meta = distill(rows, generation=next_gen)
        if distill_meta.get("skipped_not_better") or distill_meta.get("skipped_unchanged"):
            gen = int(distill_meta.get("generation") or st.get("generation") or next_gen)
        else:
            gen = int(distill_meta.get("generation") or next_gen)
    results.append(PhaseResult("distill", bool(distill_meta.get("ok")), distill_meta))

    if rows:
        pipeline_meta = pipeline_score(rows, bundle_path=distill_meta.get("path"))
    else:
        pipeline_meta = _load_json(pipeline_phase_path(), {}) or {"n": 0, "hot": []}
    results.append(PhaseResult("pipeline", True, pipeline_meta))

    q = quality_retrain(catalog)
    results.append(PhaseResult("quality", True, {"n": q.get("n"), "note": q.get("note"), "sample": (q.get("symbols") or [])[:12]}))

    fused = fuse(gen, distill_meta, pipeline_meta, q)
    results.append(PhaseResult("fuse", True, fused))

    dep = deploy(gen, distill_meta, pipeline_meta) if distill_meta.get("ok") else {"ok": False, "reason": "skip"}
    results.append(PhaseResult("deploy", bool(dep.get("ok")), dep))

    bmeta = make_batch(catalog, pipeline_meta, q)
    batch = list(bmeta.get("symbols") or [])
    results.append(PhaseResult("batch", True, bmeta))

    adv = advance(batch, generation=gen, ensure_loop=False)
    results.append(PhaseResult("advance", True, adv))
    kick = str(adv.get("kick") or "no_batch")

    fin = finalize(generation=gen, distill_meta=distill_meta, pipeline_meta=pipeline_meta, kick=kick)
    results.append(PhaseResult("finalize", True, fin))

    for i, r in enumerate(results):
        r.detail = {
            **(r.detail or {}),
            "wave": 1,
            "focus": WAVE_FOCUS[0],
            "core": r.phase,
            "phase_index": i + 1,
        }

    ctx: dict[str, Any] = {
        "catalog": catalog,
        "cover": cover,
        "rows": rows,
        "distill_meta": distill_meta,
        "pipeline_meta": pipeline_meta,
        "q": q,
        "fused": fused,
        "dep": dep,
        "bmeta": bmeta,
        "batch": batch,
        "adv": adv,
        "gen": gen,
        "kick": kick,
    }
    for w in range(2, N_WAVES + 1):
        for core in CORE_PHASES:
            name = f"w{w}_{core}"
            detail = _refresh_wave(w, core, ctx)
            detail["phase_index"] = len(results) + 1
            results.append(PhaseResult(name, True, detail))
            if core == "advance":
                kick = str(ctx.get("kick") or kick)
            if core == "distill" and ctx.get("distill_meta"):
                distill_meta = ctx["distill_meta"]
            if core == "scan" and ctx.get("catalog"):
                catalog = ctx["catalog"]
            if core == "batch" and ctx.get("batch") is not None:
                batch = list(ctx["batch"])

    fin100 = complete(
        generation=gen,
        distill_meta=distill_meta,
        catalog=catalog,
        pipeline_meta=pipeline_meta,
        kick=kick,
        n_phases=len(results) + 1,
    )
    results.append(PhaseResult("complete", True, fin100))

    harvest_doc = _load_json(harvest_state_path(), {}) or {}
    st["generation"] = gen
    st["phase"] = "complete"
    st["phase_index"] = 100
    st["waves"] = N_WAVES
    st["harvest_fp"] = harvest_fp
    st["paper_fp"] = paper_fp
    st["last"] = {
        "generation": gen,
        "auc": distill_meta.get("auc_oos") or distill_meta.get("auc"),
        "n_rows": len(rows) or harvest_doc.get("n_rows") or 0,
        "hot": (pipeline_meta.get("hot") or [])[:8],
        "kick": kick,
        "skipped_unchanged": bool(distill_meta.get("skipped_unchanged")),
        "phase_index": 100,
        "utc": _now(),
    }
    hist = list(st.get("history") or [])
    hist.append(st["last"])
    st["history"] = hist[-50:]
    st["catalog"] = {k: catalog[k] for k in catalog if not str(k).endswith("_sample")}
    save_state(st)
    log.info(
        "[ALGO] generation %d phase=100/100 auc=%s batch=%d kick=%s skip=%s",
        gen,
        distill_meta.get("auc_oos") or distill_meta.get("auc"),
        len(batch),
        kick,
        distill_meta.get("skipped_unchanged"),
    )
    return {
        "generation": gen,
        "phase_index": 100,
        "n_phases": len(results),
        "phases": [asdict(r) for r in results],
        "auc": distill_meta.get("auc_oos") or distill_meta.get("auc"),
        "n_rows": len(rows),
        "batch": batch[:12],
        "kick": kick,
        "skipped_unchanged": bool(distill_meta.get("skipped_unchanged")),
        "complete": fin100,
    }
