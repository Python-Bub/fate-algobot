#!/usr/bin/env python3
"""Download online foundation + sentiment nets into the Hugging Face cache.

Used by fortress (Chronos p_up blend) and FinBERT headline scores.
Does not place orders. Safe to re-run — HF cache is content-addressed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    load_dotenv(ROOT / "data" / "deploy_scale.env", override=True)
except Exception:
    pass


def _split_ids(raw: str) -> list[str]:
    return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]


def _models() -> list[tuple[str, str]]:
    chronos = os.getenv("FOUNDATION_CHRONOS_MODEL", "amazon/chronos-bolt-mini").strip()
    extra = os.getenv(
        "FOUNDATION_CHRONOS_EXTRA",
        "amazon/chronos-bolt-small,amazon/chronos-bolt-base",
    ).strip()
    finbert = os.getenv("FINBERT_MODEL", "ProsusAI/finbert").strip()
    more = os.getenv(
        "FOUNDATION_HF_EXTRA",
        "yiyanghkust/finbert-tone,mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis",
    ).strip()
    seen: set[str] = set()
    out: list[tuple[str, str]] = []

    def _add(kind: str, model_id: str) -> None:
        mid = (model_id or "").strip()
        if not mid or mid in seen:
            return
        seen.add(mid)
        out.append((kind, mid))

    _add("chronos", chronos)
    _add("finbert", finbert)
    for mid in _split_ids(extra):
        _add("chronos-extra", mid)
    for mid in _split_ids(more):
        _add("hf-extra", mid)
    return out


def prefetch() -> dict:
    report: dict = {"ok": True, "downloaded": [], "errors": []}
    try:
        from huggingface_hub import snapshot_download
    except Exception as e:
        report["ok"] = False
        report["errors"].append(f"huggingface_hub:{e}")
        return report

    for kind, model_id in _models():
        if not model_id:
            continue
        try:
            path = snapshot_download(repo_id=model_id)
            report["downloaded"].append({"kind": kind, "id": model_id, "path": path})
            print(f"[PREFETCH] {kind} {model_id} → {path}", flush=True)
        except Exception as e:
            report["ok"] = False
            report["errors"].append(f"{kind}:{model_id}:{e}")
            print(f"[PREFETCH] FAIL {kind} {model_id}: {e}", flush=True)

    # Touch the live Chronos loader so weights are in-process-ready.
    if os.getenv("PREFETCH_LOAD_CHRONOS", "true").lower() in ("1", "true", "yes"):
        try:
            from analytics.foundation_forecast import _load_chronos

            pipe = _load_chronos()
            report["chronos_loaded"] = pipe is not None
            print(f"[PREFETCH] chronos_loaded={pipe is not None}", flush=True)
        except Exception as e:
            report["errors"].append(f"chronos_load:{e}")
            print(f"[PREFETCH] chronos load skip: {e}", flush=True)
    return report


def main() -> int:
    os.chdir(ROOT)
    rep = prefetch()
    print(rep, flush=True)
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
