"""Big Brain orchestrator — unifies talk + codebase observe + browser allowlist
+ events + Cramer/investor signals into one pipeline manager.

Does not remove capability; coordinates existing modules and writes a durable
status snapshot for daemons / talk / training resume.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "data" / "ops" / "big_brain_status.json"
PIPELINE_PATH = ROOT / "data" / "ops" / "big_brain_pipeline.json"


def _step(name: str, fn: Callable[[], Any], *, optional: bool = False) -> dict[str, Any]:
    t0 = time.time()
    try:
        out = fn()
        return {
            "name": name,
            "ok": True,
            "optional": optional,
            "elapsed_ms": int((time.time() - t0) * 1000),
            "result": out if isinstance(out, (dict, list, str, int, float, bool)) or out is None else str(out)[:200],
        }
    except Exception as e:
        return {
            "name": name,
            "ok": False,
            "optional": optional,
            "elapsed_ms": int((time.time() - t0) * 1000),
            "error": str(e)[:240],
        }


class PipelineManager:
    """Ordered, resumable pipeline of named stages."""

    def __init__(self, name: str = "big_brain") -> None:
        self.name = name
        self.stages: list[tuple[str, Callable[[], Any], bool]] = []

    def add(self, name: str, fn: Callable[[], Any], *, optional: bool = False) -> "PipelineManager":
        self.stages.append((name, fn, optional))
        return self

    def run(self, *, stop_on_hard_fail: bool = False) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for name, fn, optional in self.stages:
            row = _step(name, fn, optional=optional)
            results.append(row)
            if not row["ok"] and not optional and stop_on_hard_fail:
                break
        ok = all(r["ok"] or r.get("optional") for r in results)
        doc = {
            "pipeline": self.name,
            "ok": ok,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "stages": results,
        }
        PIPELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PIPELINE_PATH.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        return doc


class BigBrain:
    """One orchestrator for talk + intel + succession + knowledge + tests."""

    def __init__(self) -> None:
        self.pipeline = PipelineManager("big_brain")

    def build_default_pipeline(self) -> PipelineManager:
        pm = PipelineManager("big_brain")

        def _hot():
            from intel.cramer_hot_picks import ensure_hot_file, ingest_hot_into_transcript

            doc = ensure_hot_file()
            n = ingest_hot_into_transcript()
            return {"hot_buys": list((doc.get("buys") or {}).keys()), "jsonl_lines": n}

        def _post_market():
            from intel.cramer_post_market import sync_post_market_cramer

            return sync_post_market_cramer(force=False)

        def _succession():
            from intel.investor_succession import refresh_succession

            return refresh_succession()

        def _safe_knowledge():
            from intel.safe_knowledge import expand_teacher_from_knowledge

            return expand_teacher_from_knowledge(
                n_wiki=int(os.getenv("BIG_BRAIN_WIKI_N", "40")),
                n_arxiv=int(os.getenv("BIG_BRAIN_ARXIV_N", "20")),
            )

        def _talk_ready():
            from intel import talk_brain
            from intel.talk_confine import checkpoint_provenance

            prov = checkpoint_provenance()
            return {
                "ready": talk_brain.is_ready(),
                "codebase": talk_brain.connect_codebase_enabled(),
                "edits": talk_brain.edits_allowed(),
                "backend": "local_char_lstm",
                "sha256_16": prov["sha256"][:16],
                "path": prov["path"],
                "not_qwen": True,
                "edit_gate": __import__("intel.talk_edit_gate", fromlist=["progress_snapshot"]).progress_snapshot(),
            }

        def _browser():
            from intel.talk_browser import ALLOWLIST_SUFFIXES, browser_allowed, lookup_allowed

            return {
                "browser": browser_allowed(),
                "lookup": lookup_allowed(),
                "allowlist_n": len(ALLOWLIST_SUFFIXES),
                "has_wiki": "wikipedia.org" in ALLOWLIST_SUFFIXES,
                "has_arxiv": "arxiv.org" in ALLOWLIST_SUFFIXES,
            }

        def _letter_coverage():
            p = ROOT / "data" / "ops" / "letter_training_coverage.json"
            if not p.is_file():
                return {"missing": True}
            doc = json.loads(p.read_text(encoding="utf-8"))
            letters = doc.get("letters") or []
            weak = []
            if isinstance(letters, list):
                weak = [
                    r
                    for r in letters
                    if isinstance(r, dict) and float(r.get("daily_pct") or 0) < 1.0
                ]
            return {
                "models_gb": doc.get("models_gb"),
                "target_gb": doc.get("target_gb"),
                "weak_letters": [r.get("letter") for r in weak[:12]],
                "train_prioritize": (doc.get("bias") or {}).get("train_prioritize"),
            }

        def _events():
            # Lightweight event pulse from existing intel files
            events = []
            for rel in (
                "data/intel/cramer_hot_picks.json",
                "data/intel/cramer_post_market_latest.json",
                "data/intel/investor_succession.json",
            ):
                p = ROOT / rel
                if p.is_file():
                    events.append({"path": rel, "mtime": p.stat().st_mtime})
            return {"n": len(events), "events": events}

        pm.add("cramer_hot_picks", _hot)
        pm.add("cramer_post_market", _post_market, optional=True)
        pm.add("investor_succession", _succession)
        pm.add("safe_knowledge", _safe_knowledge, optional=True)
        pm.add("talk_brain", _talk_ready)
        pm.add("browser_allowlist", _browser)
        pm.add("letter_coverage", _letter_coverage)
        pm.add("events", _events)
        self.pipeline = pm
        return pm

    def run(self) -> dict[str, Any]:
        if not self.pipeline.stages:
            self.build_default_pipeline()
        pipe = self.pipeline.run()
        status = {
            "ok": pipe.get("ok"),
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "pipeline": pipe,
            "config": {
                "TALK_TEACHER_PROBLEMS": os.getenv("TALK_TEACHER_PROBLEMS", "500000"),
                "TALK_TEST_ITERS": os.getenv("TALK_TEST_ITERS", "1000000"),
                "USE_CRAMER_HOT_PICKS": os.getenv("USE_CRAMER_HOT_PICKS", "true"),
                "USE_INVESTOR_SUCCESSION": os.getenv("USE_INVESTOR_SUCCESSION", "true"),
                "TRAIN_PRIORITIZE": os.getenv("TRAIN_PRIORITIZE", "letter_rr"),
            },
        }
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATUS_PATH.write_text(json.dumps(status, indent=2), encoding="utf-8")
        return status


def run_big_brain() -> dict[str, Any]:
    return BigBrain().run()


if __name__ == "__main__":
    print(json.dumps(run_big_brain(), indent=2))
