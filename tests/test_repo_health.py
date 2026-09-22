"""Repo-wide syntax, data, and tooling smoke tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_tools_python_files_compile():
    from tools.data_health_scan import scan_syntax

    rep = scan_syntax(roots=("tools",))
    assert rep["ok"], rep["errors"]


def test_full_stack_historical_eval_imports():
    import tools.full_stack_historical_eval as mod

    assert callable(mod.eval_symbol)
    assert callable(mod.run_eval)


def test_price_fallback_symbols_goog():
    from symbol_aliases import price_data_fallback_symbols

    syms = price_data_fallback_symbols("GOOG")
    assert "GOOG" in syms
    assert "GOOGL" in syms


def test_price_fallback_symbols_brk_prefers_feed_symbol():
    from symbol_aliases import price_data_fallback_symbols

    syms = price_data_fallback_symbols("BRK-B")
    assert syms[0] == "BRK-B"
    assert "BRK.B" in syms


def test_resolve_model_ticker_msft():
    from symbol_aliases import resolve_model_ticker

    assert resolve_model_ticker("MSFT") == "MSFT"


def test_data_health_scan_smoke():
    from tools.data_health_scan import scan_hft, scan_syntax

    assert scan_syntax(roots=("tools",))["ok"]
    hft = scan_hft()
    assert "built" in hft


def test_full_stack_eval_cli_no_syntax_error():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "full_stack_historical_eval.py"), "--symbol", "MSFT", "--hold-days", "5"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert "SyntaxError" not in proc.stderr
    assert "unmatched" not in proc.stderr
    assert proc.returncode in (0, 1)
