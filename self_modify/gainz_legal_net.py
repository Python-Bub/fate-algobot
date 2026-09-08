"""Legal internet gate for the Gainz hour-think job.

Only public, published math. No invite-only V2, no unofficial dumps.
"""

from __future__ import annotations

from urllib.parse import urlparse

# Official open-source GainzAlgo publications on TradingView (MPL / TV open-source).
ALLOWED_EXACT = frozenset(
    {
        "https://www.tradingview.com/script/HKBMUhq3-Smart-Money-Structure-GainzAlgo/",
        "https://www.tradingview.com/script/uGCtOz0Y-Machine-Learning-Smart-Money-Concepts-GainzAlgo/",
        "https://en.wikipedia.org/wiki/Average_true_range",
        "https://en.wikipedia.org/wiki/Volume-weighted_average_price",
        "https://www.investopedia.com/terms/a/atr.asp",
        "https://www.investopedia.com/terms/v/vwap.asp",
    }
)

ALLOWED_HOSTS = frozenset(
    {
        "www.tradingview.com",
        "tradingview.com",
        "en.wikipedia.org",
        "www.investopedia.com",
        "investopedia.com",
    }
)

# Unofficial dumps / invite-only leaks — never fetch.
BLOCKED_HOSTS = frozenset(
    {
        "gist.github.com",
        "pastebin.com",
        "paste.ee",
        "t.me",
        "telegram.me",
        "discord.com",
        "discord.gg",
        "mediafire.com",
        "mega.nz",
        "anonfiles.com",
    }
)

_BLOCK_SUBSTR = (
    "invite-only",
    "inviteonly",
    "cracked",
    "leaked-pine",
    "nulled",
    "warez",
    "gainzalgo-v2",
    "gainzalgo_v2",
    "gainzalgo v2",
)


def url_allowed(url: str) -> tuple[bool, str]:
    raw = (url or "").strip()
    if not raw:
        return False, "empty"
    if raw in ALLOWED_EXACT:
        return True, "allowlist"
    low = raw.lower()
    try:
        p = urlparse(raw)
    except Exception:
        return False, "parse"
    if p.scheme != "https":
        return False, "https_only"
    host = (p.hostname or "").lower()
    if host in BLOCKED_HOSTS or host.endswith(".github.io"):
        return False, f"blocked_host:{host}"
    for s in _BLOCK_SUBSTR:
        if s in low:
            return False, f"blocked_term:{s}"
    if "gist" in host or "pastebin" in host:
        return False, f"blocked_host:{host}"
    if host not in ALLOWED_HOSTS:
        return False, f"host_not_allowlisted:{host}"
    # TradingView: only the two published open-source GainzAlgo script pages.
    if host.endswith("tradingview.com"):
        path = p.path or ""
        if path.startswith("/script/HKBMUhq3-") or path.startswith("/script/uGCtOz0Y-"):
            return True, "tv_oss"
        return False, "tv_not_oss_allowlisted"
    return True, "host_ok"


def filter_urls(urls: list[str]) -> tuple[list[str], list[dict]]:
    ok: list[str] = []
    blocked: list[dict] = []
    for u in urls:
        allowed, reason = url_allowed(u)
        if allowed:
            ok.append(u)
        else:
            blocked.append({"url": u[:180], "reason": reason})
    return ok, blocked
