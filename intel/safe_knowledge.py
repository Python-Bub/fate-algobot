"""Allowlisted Wikipedia + arXiv lookups for teacher corpus expansion.

Safe only: Wikipedia REST/API, arXiv API. No arbitrary downloads, no executables.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_CORPUS = ROOT / "data" / "talk_brain" / "knowledge_teacher.txt"
OUT_META = ROOT / "data" / "talk_brain" / "knowledge_fetch.json"

_UA = "FATE-AlgoBot/1.0 (safe-knowledge; allowlisted-read-only)"

WIKI_TOPICS = [
    "Costco",
    "Walmart",
    "ServiceNow",
    "Salesforce",
    "Johnson_%26_Johnson",
    "Stock_market",
    "Technical_analysis",
    "Fundamental_analysis",
    "Jim_Cramer",
    "Mad_Money",
    "Efficient-market_hypothesis",
    "Modern_portfolio_theory",
    "Value_investing",
    "Growth_investing",
    "Dividend",
    "Earnings",
    "Price%E2%80%93earnings_ratio",
    "Moving_average",
    "Relative_strength_index",
    "Arbitrage",
]

ARXIV_QUERIES = [
    "all:stock+prediction",
    "all:portfolio+optimization",
    "all:market+microstructure",
    "all:reinforcement+learning+trading",
    "all:natural+language+finance",
]


def _get(url: str, *, timeout: float = 12.0) -> bytes | None:
    # Hard allowlist
    host = urllib.parse.urlparse(url).hostname or ""
    if not any(host.endswith(s) for s in ("wikipedia.org", "wikimedia.org", "arxiv.org", "export.arxiv.org")):
        return None
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


def wiki_summary(title: str) -> dict[str, str] | None:
    enc = urllib.parse.quote(title.replace(" ", "_"))
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{enc}"
    raw = _get(url)
    if not raw:
        return None
    try:
        doc = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return None
    extract = (doc.get("extract") or "").strip()
    if len(extract) < 40:
        return None
    return {
        "title": str(doc.get("title") or title),
        "extract": extract[:900],
        "url": str(doc.get("content_urls", {}).get("desktop", {}).get("page") or ""),
    }


def arxiv_search(query: str, *, n: int = 5) -> list[dict[str, str]]:
    url = (
        f"http://export.arxiv.org/api/query?search_query={query}"
        f"&start=0&max_results={max(1, min(n, 20))}"
    )
    # Prefer https if available
    https = url.replace("http://", "https://", 1)
    raw = _get(https) or _get(url)
    if not raw:
        return []
    try:
        root = ET.fromstring(raw)
    except Exception:
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out: list[dict[str, str]] = []
    for entry in root.findall("a:entry", ns):
        title = re.sub(r"\s+", " ", (entry.findtext("a:title", default="", namespaces=ns) or "").strip())
        summary = re.sub(r"\s+", " ", (entry.findtext("a:summary", default="", namespaces=ns) or "").strip())
        link = ""
        for ln in entry.findall("a:link", ns):
            if ln.attrib.get("type") == "text/html" or ln.attrib.get("rel") == "alternate":
                link = ln.attrib.get("href") or ""
                break
        if title and summary:
            out.append({"title": title[:160], "summary": summary[:700], "url": link})
    return out


def _pairs_from_wiki(n: int) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    topics = list(WIKI_TOPICS)
    # Rotate with env seed so resume covers more
    offset = int(os.getenv("SAFE_KNOWLEDGE_OFFSET", "0") or "0")
    topics = topics[offset % len(topics) :] + topics[: offset % len(topics)]
    for title in topics:
        if len(pairs) >= n:
            break
        s = wiki_summary(title)
        if not s:
            continue
        short = s["extract"].split(". ")
        one = (short[0] + ".").strip() if short else s["extract"][:200]
        pairs.append((f"what is {s['title']}", one[:220]))
        pairs.append(
            (
                f"summarize {s['title']}",
                s["extract"][:280],
            )
        )
    return pairs


def _pairs_from_arxiv(n: int) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    per = max(1, n // max(1, len(ARXIV_QUERIES)))
    for q in ARXIV_QUERIES:
        if len(pairs) >= n:
            break
        for paper in arxiv_search(q, n=per):
            pairs.append(
                (
                    f"arxiv: {paper['title'][:80]}",
                    f"{paper['summary'][:240]} (allowlisted arXiv abstract only).",
                )
            )
            if len(pairs) >= n:
                break
    return pairs


def expand_teacher_from_knowledge(*, n_wiki: int = 40, n_arxiv: int = 20) -> dict[str, Any]:
    if os.getenv("USE_SAFE_KNOWLEDGE", "true").lower() not in ("1", "true", "yes"):
        return {"ok": False, "reason": "disabled"}
    pairs = _pairs_from_wiki(n_wiki) + _pairs_from_arxiv(n_arxiv)
    OUT_CORPUS.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(f"you: {u}\nai: {a}\n" for u, a in pairs)
    if OUT_CORPUS.is_file():
        # Append unique-ish lines
        prev = OUT_CORPUS.read_text(encoding="utf-8")
        if text and text not in prev:
            OUT_CORPUS.write_text(prev + "\n" + text, encoding="utf-8")
        else:
            OUT_CORPUS.write_text(prev or text, encoding="utf-8")
    else:
        OUT_CORPUS.write_text(text, encoding="utf-8")
    meta = {
        "ok": True,
        "pairs": len(pairs),
        "n_wiki": n_wiki,
        "n_arxiv": n_arxiv,
        "path": str(OUT_CORPUS),
        "chars": OUT_CORPUS.stat().st_size if OUT_CORPUS.is_file() else 0,
    }
    OUT_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta
