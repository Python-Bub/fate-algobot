#!/usr/bin/env python3
"""Periodic bottom-fisher rescan + news discovery (daemon_loop target)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from bottom_fisher.integrate import maybe_force_investigate
from bottom_fisher.news_radar import discover_news_mentions
from bottom_fisher.scanner import run_bottom_fisher_scan
from utils import log


def main() -> int:
    log.info("[BOTTOM_FISHER] watch cycle start")
    discovered = discover_news_mentions()
    for sym in discovered[:8]:
        maybe_force_investigate(sym)
    try:
        from tools.ai_ipo_autopilot import bootstrap as ai_ipo_bootstrap
        from tools.train_coordination import should_defer_secondary_training

        if should_defer_secondary_training():
            log.info("[BOTTOM_FISHER] skip ai_ipo train — heavy trainer active")
        else:
            ai_ipo_bootstrap(train=os.getenv("IPO_TRAIN_ON_WATCH", "true").lower() in ("1", "true", "yes"))
    except Exception as e:
        log.debug("[BOTTOM_FISHER] ai_ipo_autopilot: %s", e)
    run_bottom_fisher_scan(skip_ai=False)
    # Periodically train promoted bottom→top50 overlay (strong multi-head stack).
    if os.getenv("BOTTOM_FISHER_PROMOTE_TRAIN_ON_WATCH", "true").lower() in ("1", "true", "yes"):
        try:
            from tools.train_coordination import should_defer_secondary_training

            if should_defer_secondary_training():
                log.info("[BOTTOM_FISHER] skip promote train — heavy trainer active")
            else:
                from bottom_fisher.promote import PROMOTED_PATH, record_and_train
                import json

                if PROMOTED_PATH.is_file():
                    doc = json.loads(PROMOTED_PATH.read_text(encoding="utf-8"))
                    syms = list(doc.get("symbols") or [])[: int(os.getenv("BOTTOM_FISHER_PROMOTE_TRAIN_CAP", "25"))]
                    if syms:
                        record_and_train(syms, train=True)
        except Exception as e:
            log.debug("[BOTTOM_FISHER] promote train: %s", e)
    if os.getenv("PRUNE_BOTTOM_JUNK_ON_WATCH", "false").lower() in ("1", "true", "yes"):
        try:
            import subprocess
            from pathlib import Path

            root = Path(__file__).resolve().parents[1]
            # Opt-in only — deleting bottom-half models fights survey→new-head promotion.
            subprocess.call(
                [str(root / "venv/bin/python"), "-u", str(root / "tools/prune_bottom_junk_models.py"), "--run"],
                cwd=root,
            )
        except Exception as e:
            log.debug("[BOTTOM_FISHER] prune junk: %s", e)
    log.info("[BOTTOM_FISHER] watch cycle done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
