#!/usr/bin/env python3
"""Show Matrix state — universe laws, neuron firings, what is actually affecting trades."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
    except Exception:
        pass

    from cortex.matrix_engine import MANIFEST_PATH, RUNTIME_PATH, collect_matrix_context, matrix_tick
    from cortex.universe_laws import LAWS_PATH, ENFORCE_LOG, load_laws

    print("=" * 60)
    print("  FATE MATRIX — universe laws + neuron engine")
    print("=" * 60)

    laws = load_laws()
    print(f"\n── Written laws ({LAWS_PATH}) ──")
    for law in laws:
        print(f"  [{law.get('id')}] {law.get('name')}")
        print(f"      {law.get('axiom')}")
        print(f"      when: {law.get('when')}")

    ctx = collect_matrix_context()
    print(f"\n── Universe state ──")
    print(f"  alpha:          {ctx.get('alpha')}")
    print(f"  deployed_frac:  {ctx.get('deployed_frac', 0):.2%}")
    print(f"  hit_rate:       {ctx.get('hit_rate', 0.5):.2%}")
    print(f"  losing_to_mkt:  {ctx.get('losing_to_market')}")

    print("\n── Matrix tick (neurons fire now) ──")
    out = matrix_tick(ctx, learn=False)
    motor = out.get("motor") or {}
    print(f"  tick:           {out.get('tick')}")
    print(f"  buy_bias:       {motor.get('buy_bias', 0):+.4f}  → eases buy gates")
    print(f"  rank_tilt:      {motor.get('rank_tilt', 0):+.4f}  → shifts p_up")
    print(f"  paper_boost:    {motor.get('paper_boost', 0):+.4f}  → paper sim scores")
    print(f"  hft_conf_delta: {motor.get('hft_conf_delta', 0):+.4f}  → HFT confidence floor")
    print(f"  size_mult:      {motor.get('size_mult', 1):.4f}  → position sizing")

    fired = out.get("laws_fired") or []
    print(f"\n── Laws enforced this tick ({len(fired)}) ──")
    for ev in fired:
        print(f"  ✓ {ev.get('law_id')}: {ev.get('law_name')}")
        applied = ev.get("applied") or {}
        if applied:
            print(f"      applied: {applied}")

    firings = out.get("firings") or {}
    print("\n── Neuron firings (top association) ──")
    for nid, act in (firings.get("association_top") or {}).items():
        bar = "█" * int(abs(act) * 20)
        print(f"  {nid:12s} {act:+.3f} {bar}")

    print("\n── Motor neurons ──")
    for nid, act in (firings.get("motor") or {}).items():
        print(f"  {nid:16s} {act:+.4f}")

    if MANIFEST_PATH.is_file():
        print(f"\n  manifest → {MANIFEST_PATH}")
    if RUNTIME_PATH.is_file():
        print(f"  runtime  → {RUNTIME_PATH} (trading stack reads this)")

    activity = Path("data/cortex/matrix_activity.jsonl")
    if activity.is_file():
        lines = activity.read_text(encoding="utf-8").strip().splitlines()
        print(f"\n── Recent matrix actions ({min(5, len(lines))} of {len(lines)}) ──")
        for line in lines[-5:]:
            try:
                rec = json.loads(line)
                sym = rec.get("symbol") or "—"
                laws = ",".join(rec.get("laws") or []) or "none"
                print(
                    f"  tick {rec.get('tick')} {sym:6s} "
                    f"buy_bias={rec.get('motor', {}).get('buy_bias', 0):+.3f} "
                    f"laws=[{laws}]"
                )
            except Exception:
                pass

    if ENFORCE_LOG.is_file():
        print(f"\n  law log  → {ENFORCE_LOG}")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
