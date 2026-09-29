#!/usr/bin/env python3
"""Connect smoke: patterns + imbalances + rank + book + (optional) unit suite.

Read-only. Never places, cancels, or modifies orders. Safe on the Mac, the trainer VM,
and the paper orderer.

  ./venv/bin/python tools/smoke_connect.py              # offline checks + Alpaca GETs
  ./venv/bin/python tools/smoke_connect.py --offline    # no network at all
  ./venv/bin/python tools/smoke_connect.py --unit       # also run the core unit subset

Exit 0 when every hard check passes; 1 otherwise. Soft checks (network blips, missing
optional caches) are reported as WARN and do not fail the run.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# Orders must stay impossible from a smoke run regardless of host role.
os.environ.setdefault("FATE_ORDER_ROLE", "observe")
os.environ.pop("FATE_ALLOW_LOCAL_ORDERS", None)

_RESULTS: list[tuple[str, str, str]] = []  # (status, name, detail)


def _rec(status: str, name: str, detail: str = "") -> None:
    _RESULTS.append((status, name, detail))
    print(f"[smoke-connect] {status:<4} {name:<34} {detail}", flush=True)


def _ok(name: str, detail: str = "") -> None:
    _rec("OK", name, detail)


def _warn(name: str, detail: str = "") -> None:
    _rec("WARN", name, detail)


def _fail(name: str, detail: str = "") -> None:
    _rec("FAIL", name, detail)


def _synthetic_bars(n: int = 160, seed: int = 7):
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    closes = 100.0 + np.cumsum(rng.normal(0.0, 0.6, n))
    closes[-1] = closes[-2] * 1.06  # a pop the pattern detectors should notice
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    return pd.DataFrame(
        {
            "Open": closes,
            "High": closes * 1.01,
            "Low": closes * 0.99,
            "Close": closes,
            "Volume": rng.integers(800_000, 2_000_000, size=n).astype(float),
        },
        index=idx,
    )


def check_patterns() -> None:
    """Hidden-pattern anomaly + chart structure detectors run end-to-end on synthetic bars."""
    try:
        from analytics.hidden_pattern_anomaly import AnomalyHit, analyze_symbol, load_hits

        os.environ.setdefault("USE_GENERATED_PATTERNS", "false")  # no peer-bar fetches
        hit = analyze_symbol("SMOKE", df=_synthetic_bars(), market_rets=None)
        if hit is not None and not isinstance(hit, AnomalyHit):
            _fail("patterns.hidden_anomaly", f"unexpected return type {type(hit).__name__}")
        else:
            _ok("patterns.hidden_anomaly", "hit" if hit else "no-hit (ok on synthetic)")
        cache = load_hits()
        n = len((cache or {}).get("by_symbol") or {})
        _ok("patterns.anomaly_cache", f"{n} cached symbols")
    except Exception as e:  # noqa: BLE001
        _fail("patterns.hidden_anomaly", repr(e))
    try:
        from analytics.structure_patterns import structure_rank_boost

        boost, meta = structure_rank_boost(_synthetic_bars())
        _ok("patterns.structure", f"boost={float(boost):+.3f} keys={sorted(meta)[:4]}")
    except Exception as e:  # noqa: BLE001
        _fail("patterns.structure", repr(e))


def check_imbalances() -> None:
    """Cross-listing imbalance cache + pair table load (no network)."""
    try:
        from analytics.market_imbalance import imbalance_rank_boost, load_imbalances, load_pairs

        pairs = load_pairs()
        cache = load_imbalances()
        b, meta = imbalance_rank_boost("BABA")
        _ok(
            "imbalances.pairs+cache",
            f"pairs={len(pairs)} cached={len((cache or {}).get('by_symbol') or {})} "
            f"BABA boost={float(b):+.3f} hit={bool(meta.get('hit'))}",
        )
    except Exception as e:  # noqa: BLE001
        _fail("imbalances", repr(e))


def check_rank() -> None:
    """Unified rank pipeline + strategy registry + sleeve tables."""
    try:
        from analytics.rank_pipeline import RankInputs, build_buy_rank

        inp = RankInputs(ticker="AAPL", p_up=0.62, exec_conf=0.90, mom_5d=0.02, rs_spy=1.03)
        res = build_buy_rank(inp, runtime="fortress")
        if not isinstance(res.score, float) or res.score != res.score:
            _fail("rank.build_buy_rank", f"bad score {res.score!r}")
        else:
            _ok("rank.build_buy_rank", f"score={res.score:+.4f} components={len(res.components)}")
    except Exception as e:  # noqa: BLE001
        _fail("rank.build_buy_rank", repr(e))
    try:
        from analytics.sleeve_weights import SLEEVES, assert_tables_valid, pct_sum

        assert_tables_valid()
        bad = [s for s in SLEEVES if abs(pct_sum(s) - 100.0) > 0.01]
        if bad:
            _fail("rank.sleeve_tables", f"do not sum to 100: {bad}")
        else:
            _ok("rank.sleeve_tables", f"{len(SLEEVES)} sleeves sum to 100")
    except Exception as e:  # noqa: BLE001
        _fail("rank.sleeve_tables", repr(e))
    try:
        from analytics.strategy_registry import strategy_ids_for_runtime

        n = sum(len(strategy_ids_for_runtime(r)) for r in ("paper", "fortress", "subsecond"))
        _ok("rank.strategy_registry", f"{n} runtime→family mappings")
    except Exception as e:  # noqa: BLE001
        _fail("rank.strategy_registry", repr(e))
    try:
        from fortress_universe import load_top100_symbols

        top = load_top100_symbols()
        junk = [s for s in top if s.startswith("T") and s[1:].isdigit()]
        if len(top) < 50 or junk:
            _fail("rank.top100_cache", f"n={len(top)} junk={junk[:5]}")
        else:
            _ok("rank.top100_cache", f"n={len(top)} head={top[:4]}")
    except Exception as e:  # noqa: BLE001
        _fail("rank.top100_cache", repr(e))


def check_book(*, offline: bool) -> None:
    """Alpaca account/positions/clock via GET only (read-only)."""
    from order_role import orders_allowed_here

    if orders_allowed_here():
        _fail("book.order_role", "smoke must run in observe role — refusing")
        return
    _ok("book.order_role", "observe (orders impossible from this process)")
    if offline:
        _warn("book.alpaca", "skipped (--offline)")
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        from alpaca_broker import _keys, get_account, list_positions

        k, s = _keys()
        if not k or not s:
            _warn("book.alpaca", "no ALPACA_API_KEY/SECRET — skipped")
            return
        t0 = time.time()
        acct = get_account() or {}
        pos = list_positions() or []
        dt_ms = (time.time() - t0) * 1000
        eq = float(acct.get("equity") or 0)
        if eq <= 0:
            _warn("book.alpaca", f"GET /v2/account empty (429/blip?) {dt_ms:.0f}ms")
        else:
            _ok(
                "book.alpaca",
                f"equity=${eq:,.0f} cash=${float(acct.get('cash') or 0):,.0f} "
                f"positions={len(pos)} {dt_ms:.0f}ms",
            )
        from symbol_aliases import internal_symbol

        syms = sorted({internal_symbol(str(p.get('symbol') or '')) for p in pos})
        _ok("book.positions_internal", ",".join(syms)[:96] or "(flat)")
    except Exception as e:  # noqa: BLE001
        _warn("book.alpaca", repr(e))
    try:
        from analytics.market_session import exchange_is_open, orders_allowed

        eo, why = exchange_is_open()
        ok_buy, wb = orders_allowed("buy", symbol="AAPL")
        _ok("book.session", f"exchange_open={eo} ({why}) buy_allowed={ok_buy} ({wb})")
    except Exception as e:  # noqa: BLE001
        _warn("book.session", repr(e))


_UNIT_SUBSET = [
    "tests/test_repo_health.py",
    "tests/test_market_session.py",
    "tests/test_alpaca_order_pace.py",
    "tests/test_trade_math.py",
    "tests/test_sleeve_weights.py",
    "tests/test_market_imbalance.py",
    "tests/test_hidden_pattern_anomaly.py",
    "tests/integration/test_online_learning.py",
]


def run_unit_subset() -> None:
    py = ROOT / "venv" / "bin" / "python"
    exe = str(py if py.is_file() else sys.executable)
    files = [f for f in _UNIT_SUBSET if (ROOT / f).is_file()]
    cmd = [exe, "-m", "pytest", "-q", "-p", "no:cacheprovider", *files]
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=1800)
    tail = (proc.stdout.strip().splitlines() or [""])[-1]
    if proc.returncode == 0:
        _ok("unit.core_subset", f"{tail} ({time.time() - t0:.0f}s)")
    else:
        _fail("unit.core_subset", f"rc={proc.returncode} {tail}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="skip every network call")
    ap.add_argument("--unit", action="store_true", help="also run the core pytest subset")
    args = ap.parse_args()

    print(f"[smoke-connect] root={ROOT} python={sys.version.split()[0]} offline={args.offline}")
    check_patterns()
    check_imbalances()
    check_rank()
    check_book(offline=args.offline)
    if args.unit:
        run_unit_subset()

    fails = [r for r in _RESULTS if r[0] == "FAIL"]
    warns = [r for r in _RESULTS if r[0] == "WARN"]
    print(
        f"[smoke-connect] done: {len(_RESULTS) - len(fails) - len(warns)} ok, "
        f"{len(warns)} warn, {len(fails)} fail"
    )
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
