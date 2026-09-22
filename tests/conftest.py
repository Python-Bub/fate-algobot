"""Test isolation: snapshot os.environ, never mutate live top100/top50 caches.

Do not weaken these guards. Production ranking files and deploy knobs must not leak
across tests (FAMILY_UNIFIED_INTEL live NVDA blocks, FORCE_YAHOO_PRICES, etc.).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

# Snapshot BEFORE collection imports paper_sim_today (which load_dotenv override=True
# on data/deploy_scale.env). Restore this snapshot at the start/end of every test.
_ENV_SNAPSHOT = os.environ.copy()
_ROOT = Path(__file__).resolve().parents[1]
_ORIG_TOP100 = _ROOT / "data" / "top100_market_cap.json"
_ORIG_TOP50 = _ROOT / "data" / "top50pct_market_cap.json"
_ORIG_CAPS = _ROOT / "data" / "universe" / "market_cap_cache.json"

os.environ.setdefault("FATE_ORDER_ROLE", "observe")
_ENV_SNAPSHOT.setdefault("FATE_ORDER_ROLE", "observe")


_PYTEST_ENV_PREFIX = "PYTEST_"


def _restore_env() -> None:
    """Restore the collection-time snapshot without clobbering pytest internals."""
    keep = {k: v for k, v in os.environ.items() if k.startswith(_PYTEST_ENV_PREFIX)}
    extra = [k for k in os.environ if k not in _ENV_SNAPSHOT and k not in keep]
    for k in extra:
        os.environ.pop(k, None)
    for k, v in _ENV_SNAPSHOT.items():
        os.environ[k] = v
    os.environ.update(keep)
    os.environ["FATE_ORDER_ROLE"] = "observe"


def _clear_module_caches() -> None:
    try:
        import fortress_universe as fu

        fu._TOP100_SET = None
        fu._TOP100_RANK = None
        fu._TOP50_SET = None
    except Exception:
        pass
    try:
        import analytics.industries.engine as eng

        eng._SNAP_CACHE = None
    except Exception:
        pass
    try:
        from intel.unified_intel import clear_unified_intel_cache

        clear_unified_intel_cache()
    except Exception:
        pass
    try:
        import intel.unified_intel as ui

        ui._CACHE.clear()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _isolate_env_and_caches(tmp_path, monkeypatch):
    """Per-test env snapshot + sandbox top100/top50 writes."""
    _restore_env()
    _clear_module_caches()

    sandbox = tmp_path / "universe_cache"
    sandbox.mkdir()
    top100 = sandbox / "top100_market_cap.json"
    top50 = sandbox / "top50pct_market_cap.json"
    caps = sandbox / "market_cap_cache.json"
    if _ORIG_TOP100.is_file():
        shutil.copy2(_ORIG_TOP100, top100)
    if _ORIG_TOP50.is_file():
        shutil.copy2(_ORIG_TOP50, top50)
    if _ORIG_CAPS.is_file():
        shutil.copy2(_ORIG_CAPS, caps)

    monkeypatch.setattr("universe_lifecycle.paths.TOP100_PATH", top100, raising=False)
    monkeypatch.setattr("universe_lifecycle.paths.TOP50_PATH", top50, raising=False)
    monkeypatch.setattr("universe_lifecycle.paths.CAP_CACHE_PATH", caps, raising=False)
    try:
        import universe_lifecycle.rankings as rk

        monkeypatch.setattr(rk, "TOP100_PATH", top100)
        monkeypatch.setattr(rk, "TOP50_PATH", top50)
        monkeypatch.setattr(rk, "CAP_CACHE_PATH", caps)
    except Exception:
        pass
    try:
        import fortress_universe as fu

        monkeypatch.setattr(fu, "TOP100_CACHE", top100)
        monkeypatch.setattr(fu, "TOP50_CACHE", top50)
    except Exception:
        pass

    yield

    _clear_module_caches()
    _restore_env()
