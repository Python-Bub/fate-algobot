"""Suite-wide isolation.

Why this exists
---------------
* Many modules call ``load_dotenv()`` / ``load_dotenv(deploy_scale.env, override=True)``
  at import time, and many tests poke ``os.environ`` directly. Without a baseline and a
  per-test restore, results depended on *which test imported what first* (e.g. the
  active-universe test saw ``PAPER_SIM_ACTIVE_MODE`` from deploy knobs instead of its own).
* One test refreshed the market-cap tiers with a synthetic pool and overwrote the
  production ``data/top100_market_cap.json`` that fortress/paper-sim read. The tests are
  sandboxed now, but the caches are guarded here too so a regression cannot silently
  corrupt the live bot's universe.
* Orders must be impossible from a test process regardless of host.
"""

from __future__ import annotations

import hashlib
import os
import sys
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_GUARDED_FILES = (
    ROOT / "data" / "top100_market_cap.json",
    ROOT / "data" / "top50pct_market_cap.json",
)


def _digest(p: Path) -> str | None:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return None


def pytest_configure(config: pytest.Config) -> None:
    # Deterministic baseline = what every daemon sees: .env, then deploy_scale.env last-wins.
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        deploy = ROOT / "data" / "deploy_scale.env"
        if deploy.is_file():
            load_dotenv(deploy, override=True)
    except Exception:  # pragma: no cover - dotenv missing
        pass
    # Never let a test process qualify as an order host.
    os.environ.pop("FATE_ALLOW_LOCAL_ORDERS", None)
    os.environ["FATE_ORDER_ROLE"] = "observe"
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


# Live family intel hits news-AI and can drop NVDA 1d after an earlier test.
# Tests that need it set the flag themselves.
_TEST_ISOLATION_ENV = {
    "FAMILY_UNIFIED_INTEL": "false",
    "FAMILY_LIVE_HEADWINDS": "false",
    "FAMILY_LIVE_RISK_CHECK": "false",
}


def _restore_env(snapshot: dict[str, str]) -> None:
    """Restore process env without deleting pytest's own PYTEST_* keys."""
    keep = {k: os.environ[k] for k in list(os.environ) if k.startswith("PYTEST_")}
    for key in list(os.environ):
        if key.startswith("PYTEST_"):
            continue
        if key not in snapshot:
            os.environ.pop(key, None)
    for key, val in snapshot.items():
        if key.startswith("PYTEST_"):
            continue
        os.environ[key] = val
    os.environ.update(keep)


def _reset_intel_caches() -> None:
    for mod_name, attr in (
        ("intel.unified_intel", "_CACHE"),
        ("intel.open_web_intel", "_CACHE"),
        ("intel.news_ai_agent", "_INTEL_CACHE"),
        ("intel.social_sentiment", "_CACHE"),
        ("intel.google_news_feed", "_CACHE_MEM"),
    ):
        try:
            mod = __import__(mod_name, fromlist=[attr])
            cache = getattr(mod, attr, None)
            if hasattr(cache, "clear"):
                cache.clear()
        except Exception:
            pass


@pytest.fixture(autouse=True)
def _isolate_environ():
    """Restore ``os.environ`` after each test so env pokes cannot leak across tests."""
    snapshot = dict(os.environ)
    os.environ.update(_TEST_ISOLATION_ENV)
    _reset_intel_caches()
    try:
        yield
    finally:
        _reset_intel_caches()
        _restore_env(snapshot)


@pytest.fixture(scope="session", autouse=True)
def _guard_production_caches():
    """Fail loudly (and restore) if a test rewrites the live top-100 / top-50% caches."""
    before = {p: (_digest(p), p.read_bytes() if p.is_file() else None) for p in _GUARDED_FILES}
    yield
    for p, (h0, raw0) in before.items():
        h1 = _digest(p)
        if h0 is None or h1 == h0:
            continue
        if raw0 is not None:
            p.write_bytes(raw0)
        msg = (
            f"{p.relative_to(ROOT)} was modified during the test session and has been restored. "
            "A test is writing production universe caches — sandbox it (patch TOP100_PATH/TOP50_PATH)."
        )
        warnings.warn(msg, RuntimeWarning, stacklevel=1)
        print(f"\n[conftest] WARNING: {msg}", file=sys.stderr)
