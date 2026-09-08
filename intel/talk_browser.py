"""Safe allowlisted web browse + lookup for the homemade talk brain.

- Opens http/https only (no downloads / executables).
- Lookup fetches readable text summaries from allowlisted domains
  (Wikipedia, Merriam-Webster, Yahoo Finance, TradingView, GitHub docs, etc.).
- Sketchy hosts and file extensions are blocked.
"""

from __future__ import annotations

import html
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from urllib.parse import urlparse

# Safe defaults / shortcuts
SHORTCUTS = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "tradingview": "https://www.tradingview.com",
    "alpaca": "https://app.alpaca.markets/paper/dashboard/overview",
    "yahoo": "https://finance.yahoo.com",
    "github": "https://github.com",
    "wikipedia": "https://en.wikipedia.org",
    "wiki": "https://en.wikipedia.org",
    "arxiv": "https://arxiv.org",
    "merriam": "https://www.merriam-webster.com",
    "dict": "https://www.merriam-webster.com",
    "doc": "https://docs.google.com/document/d/1fEuErs8mTMzSoJm4WMesxmhsfqvnlhzzFINycbRCIeU/edit",
}

# Host suffixes we will open or fetch from (leading '.' = suffix match).
ALLOWLIST_SUFFIXES = (
    "wikipedia.org",
    "wikimedia.org",
    "merriam-webster.com",
    "dictionary.com",
    "britannica.com",
    "investopedia.com",
    "finance.yahoo.com",
    "yahoo.com",
    "tradingview.com",
    "github.com",
    "githubusercontent.com",
    "docs.github.com",
    "readthedocs.io",
    "python.org",
    "pytorch.org",
    "numpy.org",
    "pandas.pydata.org",
    "alpaca.markets",
    "polygon.io",
    "finnhub.io",
    "sec.gov",
    "federalreserve.gov",
    "bls.gov",
    "arxiv.org",
    "openai.com",
    "google.com",
    "youtube.com",
    "youtu.be",
    "duckduckgo.com",
    "cnbc.com",
    "reuters.com",
    "bloomberg.com",
    "marketwatch.com",
    "seekingalpha.com",
    "wsj.com",
    "npr.org",
    "bbc.co.uk",
    "bbc.com",
    "podcasts.apple.com",
    "open.spotify.com",
    "spotify.com",
    "sec.gov",
)

BLOCK_SUFFIXES = (
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "goo.gl",
    "raw.githubusercontent.com",  # raw blobs — prefer docs pages
)

BLOCK_EXT = (
    ".exe",
    ".dmg",
    ".pkg",
    ".msi",
    ".bat",
    ".cmd",
    ".ps1",
    ".sh",
    ".app",
    ".apk",
    ".ipa",
    ".dll",
    ".so",
    ".dylib",
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".bz2",
    ".iso",
    ".img",
    ".bin",
    ".run",
    ".deb",
    ".rpm",
    ".js",  # direct script downloads
    ".vbs",
    ".scr",
)

_UA = "FATE-AlgoBot-TalkBrain/1.0 (+local; allowlisted-read-only)"


def browser_allowed() -> bool:
    return os.getenv("TALK_ALLOW_BROWSER", "true").lower() in ("1", "true", "yes")


def lookup_allowed() -> bool:
    return os.getenv("TALK_ALLOW_WEB_LOOKUP", "true").lower() in ("1", "true", "yes")


def _host_allowed(host: str) -> bool:
    h = (host or "").lower().strip().rstrip(".")
    if not h:
        return False
    if h.startswith("www."):
        h = h[4:]
    for bad in BLOCK_SUFFIXES:
        if h == bad or h.endswith("." + bad):
            return False
    for ok in ALLOWLIST_SUFFIXES:
        if h == ok or h.endswith("." + ok):
            return True
    return False


def _path_safe(path: str) -> bool:
    p = (path or "").lower()
    for ext in BLOCK_EXT:
        if p.endswith(ext):
            return False
    if "/releases/download/" in p or "/download/" in p:
        return False
    return True


def _normalize_url(raw: str) -> str | None:
    s = (raw or "").strip().strip("\"'")
    if not s:
        return None
    key = s.lower().rstrip("/")
    if key in SHORTCUTS:
        return SHORTCUTS[key]
    if "://" not in s:
        if re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/\S*)?$", s):
            s = "https://" + s
        else:
            return None
    parsed = urlparse(s)
    if parsed.scheme not in ("http", "https"):
        return None
    if not parsed.netloc:
        return None
    if not _host_allowed(parsed.hostname or ""):
        return None
    if not _path_safe(parsed.path or ""):
        return None
    return s


_OPEN_RE = re.compile(
    r"(?i)^\s*(?:/open|open(?:\s+browser)?|browse|go\s+to|launch)\s+(.+?)\s*$"
)
_URL_IN_TEXT = re.compile(r"https?://[^\s]+", re.I)
_LOOKUP_RE = re.compile(
    r"(?i)^\s*(?:/lookup|/search|look\s*up|search\s+(?:for\s+)?|wiki(?:pedia)?\s+"
    r"|google\s+|find\s+(?:out\s+)?(?:about\s+)?|web\s+search\s+)\s*(.+?)\s*$"
)


def parse_open_request(user: str) -> str | None:
    """Return a URL to open, or None."""
    if not user:
        return None
    m = _OPEN_RE.match(user.strip())
    if m:
        return _normalize_url(m.group(1))
    if re.match(r"(?i)^\s*(?:/browser|open\s+browser|browser)\s*$", user.strip()):
        home = os.getenv("TALK_BROWSER_HOME", "https://www.wikipedia.org")
        return _normalize_url(home)
    if re.search(r"(?i)\bopen\b", user):
        for name, url in SHORTCUTS.items():
            if re.search(rf"(?i)\b{re.escape(name)}\b", user):
                if _host_allowed(urlparse(url).hostname or ""):
                    return url
        found = _URL_IN_TEXT.search(user)
        if found:
            return _normalize_url(found.group(0).rstrip(".,)"))
    return None


def open_url(url: str) -> tuple[bool, str]:
    if not browser_allowed():
        return False, "browser open is disabled (TALK_ALLOW_BROWSER=false)"
    target = _normalize_url(url)
    if not target:
        return False, f"won't open that ({url!r}) — allowlisted http/https only"
    try:
        ok = webbrowser.open(target, new=2)
        if ok:
            return True, f"opened {target}"
        import subprocess

        subprocess.run(["open", target], check=False, timeout=10)
        return True, f"opened {target}"
    except Exception as e:
        return False, f"failed to open browser: {e}"


def maybe_open(user: str) -> str | None:
    """If user asked to open something, do it and return a reply string."""
    url = parse_open_request(user)
    if not url:
        return None
    ok, msg = open_url(url)
    return msg if ok else f"couldn't open: {msg}"


def _strip_html(raw: str) -> str:
    t = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw)
    t = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", t)
    t = re.sub(r"(?is)<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _http_get(url: str, timeout: float = 8.0) -> str | None:
    target = _normalize_url(url)
    if not target:
        return None
    req = urllib.request.Request(
        target,
        headers={"User-Agent": _UA, "Accept": "text/html,application/json,text/plain"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "octet-stream" in ctype or "application/zip" in ctype:
                return None
            data = resp.read(400_000)
            charset = "utf-8"
            m = re.search(r"charset=([\w-]+)", ctype)
            if m:
                charset = m.group(1)
            return data.decode(charset, errors="replace")
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def _wiki_summary(query: str) -> tuple[str, str] | None:
    q = urllib.parse.quote(query.replace(" ", "_"))
    api = (
        "https://en.wikipedia.org/api/rest_v1/page/summary/"
        + q
    )
    raw = _http_get(api)
    if not raw:
        # search then summary
        search = (
            "https://en.wikipedia.org/w/api.php?action=opensearch&limit=1&namespace=0&format=json&search="
            + urllib.parse.quote(query)
        )
        sraw = _http_get(search)
        if not sraw:
            return None
        try:
            import json

            data = json.loads(sraw)
            titles = data[1] if isinstance(data, list) and len(data) > 1 else []
            if not titles:
                return None
            return _wiki_summary(titles[0])
        except Exception:
            return None
    try:
        import json

        doc = json.loads(raw)
        if doc.get("type") == "disambiguation":
            extract = (doc.get("extract") or "")[:240]
            title = doc.get("title") or query
            return title, extract or f"Wikipedia has several pages for {title}."
        extract = (doc.get("extract") or "").strip()
        title = doc.get("title") or query
        url = (doc.get("content_urls") or {}).get("desktop", {}).get("page") or (
            f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
        )
        if not extract:
            return None
        return title, f"{extract[:700]} (source: {url})"
    except Exception:
        return None


def _yahoo_quote_blurb(symbol: str) -> str | None:
    sym = re.sub(r"[^A-Za-z0-9.-]", "", symbol).upper()
    if not sym or len(sym) > 12:
        return None
    url = f"https://finance.yahoo.com/quote/{urllib.parse.quote(sym)}"
    raw = _http_get(url)
    if not raw:
        return None
    text = _strip_html(raw)
    # Keep a short readable slice; Yahoo pages are huge
    m = re.search(
        rf"(?i){re.escape(sym)}.{{0,80}}?(?:\$\s*)?(\d+\.\d+).{{0,40}}?",
        text[:8000],
    )
    if m:
        return f"{sym} on Yahoo Finance — recent price context around {m.group(0)[:80]}. More: {url}"
    return f"Opened allowlisted Yahoo Finance page for {sym}: {url}"


def lookup_summary(query: str, *, max_chars: int = 750) -> str:
    """Fetch a readable summary from allowlisted sources only."""
    q = (query or "").strip().strip("\"'")
    if not q:
        return "Nothing to look up."
    # Ticker-ish short query → Yahoo
    if re.fullmatch(r"[A-Za-z]{1,5}(?:\.[A-Za-z]{1,2})?", q):
        y = _yahoo_quote_blurb(q)
        if y:
            return y[:max_chars]
    wiki = _wiki_summary(q)
    if wiki:
        title, body = wiki
        out = f"{title}: {body}"
        return out[:max_chars]
    # Last resort: point at Wikipedia search (allowlisted) without scraping random web
    search_url = "https://en.wikipedia.org/wiki/Special:Search?search=" + urllib.parse.quote(q)
    return f"No clean summary fetched. Try Wikipedia (allowlisted): {search_url}"[:max_chars]


def parse_lookup_request(user: str) -> str | None:
    if not user:
        return None
    # Never steal local codebase/error intents (find errors, review codebase, …)
    try:
        from intel.talk_codebase import wants_factual

        if wants_factual(user):
            return None
    except Exception:
        pass
    # "find errors" / "find bugs" are repo scans, not web search
    if re.match(r"(?i)^\s*find\s+(errors?|bugs?|issues?|problems?)\s*$", user.strip()):
        return None
    m = _LOOKUP_RE.match(user.strip())
    if m:
        return m.group(1).strip()
    # "look this up: X" / "can you look up X"
    m2 = re.search(
        r"(?i)\b(?:look\s*up|search\s+for|wiki(?:pedia)?)\s+(.+)$",
        user.strip(),
    )
    if m2:
        return m2.group(1).strip().rstrip("?.!")
    return None


def maybe_lookup(user: str) -> str | None:
    """If user asked to look something up, fetch an allowlisted summary."""
    if not lookup_allowed():
        return None
    q = parse_lookup_request(user)
    if not q:
        return None
    # Don't treat open-url as lookup
    if parse_open_request(user):
        return None
    try:
        return lookup_summary(q)
    except Exception as e:
        return f"lookup failed safely: {e}"
