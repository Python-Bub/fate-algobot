#!/usr/bin/env python3
"""Preference / reward training for talk brain — only keep if hold-out improves.

Heavy params (harder than casual manual):
  TALK_REWARD_STEPS   default 4000
  TALK_REWARD_LR      default 8e-4 (lower than plain train)
  TALK_REWARD_PATIENCE default 3 eval windows without hold-out gain → stop
  TALK_REWARD_PAIRS   preference pairs injected (not scorer-keyword bait)

  ./venv/bin/python -u tools/train_talk_reward.py
  TALK_REWARD_STEPS=8000 ./venv/bin/python -u tools/train_talk_reward.py --force
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

BRAIN = ROOT / "data" / "talk_brain"
CKPT = BRAIN / "brain.pt"
CKPT_BAK = BRAIN / "brain.pt.prereward"
PREF_CORPUS = BRAIN / "preference_corpus.txt"


def _i(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, str(default))))
    except ValueError:
        return default


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _write_pref_corpus(n: int) -> int:
    from intel.talk_reward import preference_pairs

    pairs = preference_pairs(n)
    PREF_CORPUS.parent.mkdir(parents=True, exist_ok=True)
    with PREF_CORPUS.open("w", encoding="utf-8") as fh:
        for u, a in pairs:
            fh.write(f"you: {u}\nai: {a}\n")
    return len(pairs)


def _eval_brain() -> dict:
    from intel.talk_brain import TalkBrain
    from intel.talk_reward import evaluate_holdout, ensure_holdout_file

    ensure_holdout_file()
    brain = TalkBrain()

    def gen(prompt: str) -> str:
        return brain.generate(prompt, max_new=48, temperature=0.7, top_k=40)

    return evaluate_holdout(gen)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=_i("TALK_REWARD_STEPS", 4000))
    ap.add_argument("--pairs", type=int, default=_i("TALK_REWARD_PAIRS", 800))
    ap.add_argument("--lr", type=float, default=_f("TALK_REWARD_LR", 8e-4))
    ap.add_argument("--seq", type=int, default=_i("TALK_REWARD_SEQ", 96))
    ap.add_argument("--batch", type=int, default=_i("TALK_REWARD_BATCH", 32))
    ap.add_argument(
        "--force",
        action="store_true",
        help="Keep new ckpt even if hold-out does not improve (debug only)",
    )
    args = ap.parse_args()

    os.environ.setdefault("TALK_ALLOW_EDITS", "false")

    from intel.talk_brain import train
    from intel.talk_reward import load_reward_meta, save_reward_meta, should_keep_checkpoint

    print("[talk-reward] baseline hold-out eval…", flush=True)
    try:
        baseline = _eval_brain()
        base_mean = float(baseline["mean_reward"])
    except Exception as e:
        print(f"[talk-reward] baseline failed ({e}) — training from corpus only", flush=True)
        baseline = {"mean_reward": None, "error": str(e)}
        base_mean = None

    n_pairs = _write_pref_corpus(args.pairs)
    print(
        f"[talk-reward] preference pairs={n_pairs} steps={args.steps} "
        f"lr={args.lr} (hold-out gate ON unless --force)",
        flush=True,
    )

    if CKPT.is_file():
        shutil.copy2(CKPT, CKPT_BAK)

    t0 = time.time()
    meta = train(
        steps=args.steps,
        seq=args.seq,
        batch=args.batch,
        lr=args.lr,
        extra_paths=[PREF_CORPUS],
    )
    elapsed = time.time() - t0

    print("[talk-reward] post hold-out eval…", flush=True)
    try:
        after = _eval_brain()
        after_mean = float(after["mean_reward"])
    except Exception as e:
        print(f"[talk-reward] post eval failed: {e}", flush=True)
        after = {"mean_reward": None, "error": str(e)}
        after_mean = None

    prev_meta = load_reward_meta()
    prev_hold = prev_meta.get("best_holdout_mean")
    if prev_hold is None and base_mean is not None:
        prev_hold = base_mean

    keep = args.force or should_keep_checkpoint(
        new_holdout=after_mean if after_mean is not None else -1.0,
        prev_holdout=float(prev_hold) if prev_hold is not None else None,
        new_loss=meta.get("final_loss"),
        prev_loss=prev_meta.get("final_loss"),
    )

    if not keep and CKPT_BAK.is_file():
        shutil.copy2(CKPT_BAK, CKPT)
        print(
            f"[talk-reward] REVERTED — hold-out {after_mean} <= best {prev_hold} "
            f"(anti reward-hack / no improvement)",
            flush=True,
        )
        kept = False
    else:
        kept = True
        print(
            f"[talk-reward] KEPT — hold-out {after_mean} (prev best {prev_hold})",
            flush=True,
        )

    doc = {
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kept": kept,
        "forced": bool(args.force),
        "baseline_holdout_mean": base_mean,
        "after_holdout_mean": after_mean,
        "best_holdout_mean": (
            max(x for x in (prev_hold, after_mean) if x is not None)
            if kept and after_mean is not None
            else prev_hold
        ),
        "final_loss": meta.get("final_loss"),
        "steps": args.steps,
        "lr": args.lr,
        "pairs": n_pairs,
        "elapsed_sec": round(elapsed, 1),
        "honest_note": (
            "Literal billions of CharLSTM steps overnight on one Mac is usually "
            "not feasible as wall-clock; this run uses heavy steps + low LR + "
            "hold-out gate. Resume with higher TALK_REWARD_STEPS."
        ),
        "baseline_detail_n": (baseline or {}).get("n"),
        "after_min": (after or {}).get("min_reward"),
        "resume": (
            f"TALK_REWARD_STEPS={max(args.steps, 8000)} TALK_REWARD_LR={args.lr} "
            f"./venv/bin/python -u tools/train_talk_reward.py"
        ),
    }
    if kept and after_mean is not None:
        doc["best_holdout_mean"] = (
            after_mean
            if prev_hold is None
            else max(float(prev_hold), after_mean)
        )
    save_reward_meta(doc)
    print(json.dumps({k: doc[k] for k in ("kept", "after_holdout_mean", "best_holdout_mean", "resume", "honest_note")}, indent=2), flush=True)
    return 0 if kept or after_mean is None else 0


if __name__ == "__main__":
    raise SystemExit(main())
