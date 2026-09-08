"""When the book is under target deploy, scan NEW names first.

Fortress was prepending holdings + playbook + sheldon until the list was 500+
tickers, then hitting FORTRESS_PASS_MAX_SEC after ~30 names — all already held.
Cash sat idle while those names bled.
"""

def deploy_frac_from_snapshot(equity: float, gross_mv: float) -> float:
    """0.0 (fail-open fill) when Alpaca 429s equity to 0/1."""
    eq = float(equity or 0.0)
    mv = abs(float(gross_mv or 0.0))
    if eq < 100.0:
        return 0.0
    return mv / eq


def order_scan_for_fill(
    syms: list[str],
    held: list[str],
    *,
    fresh_cap: int,
    prefer: list[str] | None = None,
    deprioritize: list[str] | None = None,
    reserve: list[str] | None = None,
) -> list[str]:
    """Non-held first (up to fresh_cap), then holdings for stop/TP.

    reserve: always scanned (crypto / today's liquid movers) even if prefer is huge.
    prefer: liquid / top100 names first so fade-fill does not buy microcaps.
    deprioritize: scored after prefer+other (optional).
    """
    held_u: list[str] = []
    seen_h: set[str] = set()
    for s in held:
        u = str(s or "").strip().upper()
        if u and u not in seen_h:
            seen_h.add(u)
            held_u.append(u)
    reserve_u: list[str] = []
    seen_r: set[str] = set()
    for s in reserve or []:
        u = str(s or "").strip().upper()
        if u and u not in seen_h and u not in seen_r:
            seen_r.add(u)
            reserve_u.append(u)
    prefer_set = {
        str(s or "").strip().upper()
        for s in (prefer or [])
        if str(s or "").strip()
    } - seen_h
    deprior = {
        str(s or "").strip().upper()
        for s in (deprioritize or [])
        if str(s or "").strip()
    } - seen_h
    pref: list[str] = []
    other: list[str] = []
    secondary: list[str] = []
    seen_f: set[str] = set()
    for s in syms:
        u = str(s or "").strip().upper()
        if not u or u in seen_h or u in seen_f or u in seen_r:
            continue
        seen_f.add(u)
        if u in deprior:
            secondary.append(u)
        elif u in prefer_set:
            pref.append(u)
        else:
            other.append(u)
    rest_cap = max(0, int(fresh_cap) - len(reserve_u))
    fresh = reserve_u + (pref + other + secondary)[:rest_cap]
    return list(dict.fromkeys(fresh + held_u))
