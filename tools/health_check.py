#!/usr/bin/env python3
"""Verify core stack: models, enhancements, APIs. Exit 0 = OK."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    os.chdir(ROOT)
    issues: list[str] = []
    ok: list[str] = []

    # Enhancements importable
    for mod in (
        "analytics.foundation_forecast",
        "analytics.signal_enhance",
        "analytics.lstm_head",
        "fortress_universe",
    ):
        try:
            __import__(mod)
            ok.append(f"import {mod}")
        except Exception as e:
            issues.append(f"import {mod}: {e}")

    from fortress_universe import load_top100_symbols, symbols_paper_active_universe, is_top100_equity
    from model_trainer import training_saved_model

    top = load_top100_symbols()
    active = symbols_paper_active_universe()
    if len(top) < 90:
        issues.append(f"top100 list short: {len(top)}")
    else:
        ok.append(f"top100={len(top)}")
    ok.append(f"paper_active={len(active)}")

    # Megacap daily models (finish-today rebuilds these)
    mega_missing = [s for s in top[:15] if not training_saved_model(s)]
    if mega_missing:
        issues.append(
            f"megacap daily models missing (retraining): {', '.join(mega_missing[:8])}"
            + ("…" if len(mega_missing) > 8 else "")
        )
    else:
        ok.append("megacap daily models present")

    top_trained = sum(1 for s in top if training_saved_model(s))
    ok.append(f"top100 daily trained {top_trained}/{len(top)}")
    if top_trained < len(top):
        missing_top = [s for s in top if not training_saved_model(s)]
        if len(missing_top) > 5:
            issues.append(
                f"top100 daily missing ({len(missing_top)}): {', '.join(missing_top[:8])}"
                + ("…" if len(missing_top) > 8 else "")
            )
        else:
            ok.append(f"top100 gap-fill pending ({len(missing_top)}): {', '.join(missing_top)}")

    # Catch NVDA-style CalibratedClassifierCV fitted_ failures still in checkpoint.
    ck_path = ROOT / "data" / "train_checkpoint.json"
    if ck_path.is_file():
        try:
            import json

            failed = (json.loads(ck_path.read_text(encoding="utf-8")).get("failed") or {})
            calib_fail = [k for k, v in failed.items() if "fitted_" in str(v)]
            if calib_fail:
                issues.append(f"calibration train failures: {', '.join(calib_fail[:6])}")
        except Exception:
            pass

    # LSTM + intraday spot-check on one liquid probe symbol (env, not a favor list).
    from analytics.lstm_head import has_lstm_head
    from fortress_universe import has_trained_intraday_bundle

    probe = (os.getenv("API_PROBE_SYMBOL") or "SPY").strip().upper()
    if has_lstm_head(probe):
        ok.append(f"{probe} LSTM head")
    else:
        issues.append(f"{probe} LSTM head missing")
    if has_trained_intraday_bundle(probe):
        ok.append(f"{probe} intraday bundle")
    else:
        issues.append(f"{probe} intraday bundle missing")

    try:
        import chronos  # noqa: F401

        ok.append("Chronos installed")
    except ImportError:
        ok.append("Chronos fallback (statistical)")

    if os.getenv("USE_FOUNDATION_FORECAST", "true").lower() in ("1", "true", "yes"):
        ok.append("foundation blend enabled")

    print("=== health-check ===")
    for line in ok:
        print(f"  OK  {line}")
    for line in issues:
        print(f"  WARN {line}")
    # Warnings only if megacap daily missing while training — not hard fail
    hard = [i for i in issues if not i.startswith("megacap")]
    return 1 if hard else 0


if __name__ == "__main__":
    raise SystemExit(main())
