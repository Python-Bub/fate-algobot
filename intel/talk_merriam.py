"""Fetch Merriam-Webster Word of the Day (official RSS) into talk-brain corpus.

Site HTML is Cloudflare-blocked; the public WOTD RSS is the honest MW source we can use.
Also opens https://www.merriam-webster.com/ in the browser for you.
"""

from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "talk_brain" / "merriam_corpus.txt"
META = ROOT / "data" / "talk_brain" / "merriam_fetch.json"
RSS_URL = "https://www.merriam-webster.com/wotd/feed/rss2"
SITE = "https://www.merriam-webster.com/"


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def fetch_wotd_rss(*, timeout: float = 25.0) -> list[dict[str, str]]:
    req = urllib.request.Request(
        RSS_URL,
        headers={"User-Agent": "FATE_AlgoBot-talk-brain/1.0 (local training; WOTD RSS)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    root = ET.fromstring(raw)
    items: list[dict[str, str]] = []
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        desc = _strip_html(it.findtext("description") or "")
        if title and desc:
            items.append({"word": title, "link": link, "text": desc})
    return items


def to_dialogue(items: list[dict[str, str]]) -> str:
    """Turn definitions into you:/ai: chat the tiny brain can learn."""
    blocks: list[str] = []
    for it in items:
        w = it["word"]
        t = it["text"]
        # keep ASCII-ish for char LSTM
        t = t.encode("ascii", "ignore").decode("ascii")
        w = w.encode("ascii", "ignore").decode("ascii")
        if not w or not t:
            continue
        blocks.append(
            f"you: what does {w} mean\n"
            f"ai: {t[:500]}\n"
            f"you: define {w}\n"
            f"ai: {w}: {t[:350]}\n"
            f"you: teach me a word\n"
            f"ai: today's merriam-webster word is {w}. {t[:280]}\n"
        )
    return "\n".join(blocks)


def save_corpus(dialogue: str, items: list[dict[str, str]]) -> Path:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # append-merge with previous so we keep learning
    prev = ""
    if OUT.is_file():
        prev = OUT.read_text(encoding="utf-8", errors="replace")
    merged = (prev + "\n" + dialogue).strip() + "\n"
    # de-dupe exact blocks lightly by line set size cap
    if len(merged) > 400_000:
        merged = merged[-400_000:]
    OUT.write_text(merged, encoding="utf-8")
    META.write_text(
        json.dumps(
            {
                "ts": time.time(),
                "source": RSS_URL,
                "site": SITE,
                "n_items": len(items),
                "words": [i["word"] for i in items],
                "corpus_path": str(OUT),
                "corpus_chars": len(merged),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return OUT


def open_merriam_site() -> str:
    try:
        from intel.talk_browser import open_url

        ok, msg = open_url(SITE)
        return msg if ok else f"browser: {msg}"
    except Exception as e:
        return f"browser skip: {e}"


def ingest_and_train(
    *,
    steps: int | None = None,
    open_browser: bool = True,
) -> dict[str, Any]:
    items = fetch_wotd_rss()
    dialogue = to_dialogue(items)
    path = save_corpus(dialogue, items)
    browser_msg = open_merriam_site() if open_browser else "browser skipped"
    from intel.talk_brain import train

    # WOTD RSS only (not full MW scrape). Include merriam + modest WordNet sample.
    os.environ["TALK_FOCUS"] = "merriam"
    os.environ["TALK_INCLUDE_DICT"] = "true"
    os.environ.setdefault("TALK_DICT_WEIGHT", "500")
    n_steps = steps or int(os.getenv("TALK_MERRIAM_TRAIN_STEPS", os.getenv("TALK_TRAIN_STEPS", "1500")))
    meta = train(steps=n_steps, extra_paths=[path])
    return {
        "words": [i["word"] for i in items],
        "corpus": str(path),
        "browser": browser_msg,
        "train": meta,
    }
