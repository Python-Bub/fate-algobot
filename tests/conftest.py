"""Session isolation for pytest.

Import-time dotenv and unittest ``os.environ`` leaks used to bleed into later tests.
Baseline = original process env plus layered file env (``.env`` then
``data/deploy_scale.env``, files last-win, process pins win). Each test starts
from that baseline so Mac observe / GCP paper knobs remain, then monkeypatch can
still pin ``FORCE_YAHOO_PRICES=false``.

Also restore git-tracked universe caches and clear in-memory intel/forecast state.
Live family intel is off unless a test opts in — otherwise ``blocks_long`` hits
news-AI and can drop NVDA 1d from independent-horizon math.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Capture BEFORE other test modules import loaders that dump deploy_scale.env.
_ENV_SNAPSHOT = dict(os.environ)

_BASELINE = dict(_ENV_SNAPSHOT)
try:
    from data_platform.runtime_env import layered_dotenv_values

    for _k, _v in layered_dotenv_values().items():
        if _k not in _BASELINE:
            _BASELINE[_k] = _v
except Exception:
    pass

_PROTECTED_FILES = (
    ROOT / "data" / "top100_market_cap.json",
    ROOT / "data" / "top50pct_market_cap.json",
    ROOT / "data" / "intel" / "morning_club_latest.json",
)

_FILE_SNAPSHOT: dict[Path, bytes | None] = {
    p: (p.read_bytes() if p.is_file() else None) for p in _PROTECTED_FILES
}

# Family forecast unit tests must not call live news/intel unless they opt in.
_TEST_ISOLATION_ENV = {
    "FAMILY_UNIFIED_INTEL": "false",
    "FAMILY_LIVE_HEADWINDS": "false",
    "FAMILY_LIVE_RISK_CHECK": "false",
}


def _restore_env(snap: dict[str, str]) -> None:
    """Restore process env without deleting pytest's own PYTEST_* keys."""
    keep = {k: os.environ[k] for k in list(os.environ) if k.startswith("PYTEST_")}
    for key in list(os.environ):
        if key.startswith("PYTEST_"):
            continue
        if key not in snap:
            os.environ.pop(key, None)
    for key, val in snap.items():
        if key.startswith("PYTEST_"):
            continue
        os.environ[key] = val
    os.environ.update(keep)


def _restore_protected_files() -> None:
    for path, blob in _FILE_SNAPSHOT.items():
        if blob is None:
            if path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.read_bytes() != blob:
            path.write_bytes(blob)


def _reset_process_caches() -> None:
    try:
        import fortress_universe as fu

        fu._TOP100_SET = None
        fu._TOP100_RANK = None
        fu._TOP50_SET = None
        fu._HFT_QUALITY_SET = None
    except Exception:
        pass
    for mod_name, attr in (
        ("intel.unified_intel", "_CACHE"),
        ("intel.open_web_intel", "_CACHE"),
        ("intel.news_ai_agent", "_INTEL_CACHE"),
        ("intel.social_sentiment", "_CACHE"),
        ("intel.google_news_feed", "_CACHE_MEM"),
        ("intel.insider_signals", "_TX_CACHE"),
        ("intel.institutional_flow_signals", "_TX_CACHE"),
    ):
        try:
            mod = __import__(mod_name, fromlist=[attr])
            cache = getattr(mod, attr, None)
            if hasattr(cache, "clear"):
                cache.clear()
        except Exception:
            pass


def _ensure_runtime_seeds() -> None:
    student = ROOT / "data" / "self_improve" / "gainz_student.py"
    if student.is_file():
        return
    student.parent.mkdir(parents=True, exist_ok=True)
    student.write_text(
        "from __future__ import annotations\n"
        "GENERATION = 0\n\n"
        "def student_signal(df, symbol=''):\n"
        "    return {'side': 'none', 'confidence': 0.0}\n",
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def _isolate_env_and_caches():
    """Start (and end) every test from file+process baseline + on-disk caches."""
    _restore_env(_BASELINE)
    os.environ.update(_TEST_ISOLATION_ENV)
    _restore_protected_files()
    _ensure_runtime_seeds()
    _reset_process_caches()
    yield
    _restore_protected_files()
    _reset_process_caches()
    _restore_env(_BASELINE)
