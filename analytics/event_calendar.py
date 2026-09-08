"""Public clocks for *when* a company is allowed to speak — not unpublished results.

Earnings calendars miss biologics: Merck+Moderna INTerpath-001 (NCT05933577) printed
an interim RFS readout on 2026-08-19 while ClinicalTrials.gov still listed primary
completion ESTIMATED 2029-10-26 (OS follow-up) and earnings sat on 2026-11-04.

What we *can* score from public data:
  1. Live binary — Phase 2/3, enrollment done (ACTIVE_NOT_RECRUITING / COMPLETED),
     no results posted. Interim analyses can fire years before primaryCompletionDate.
  2. Collaborator graph — lead sponsor Merck, collaborator ModernaTX → both tickers.
  3. Guidance language — 10-Q / 8-K / transcript: "topline", "interim", "2H 2026".
  4. Conference windows — AACR / ASCO / ESMO / ASH abstract drops.
  5. 8-K clustering + lastUpdatePostDate (status changed recently).
  6. Post-print exhaustion — do not chase a +25–40% gap on a live Phase 3.

This module never claims to know the *sign* of a trial. Rank boost is "the clock
is armed"; exhaustion is "the print already happened". Long-only sleeves just
rank down after a rip — shorts / live options stay off unless the operator asks.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT / "data" / "intel" / "event_calendar.json"

# Longest alias first so "merck sharp" wins over a later generic.
SPONSOR_ALIASES: tuple[tuple[str, str], ...] = (
    ("merck sharp", "MRK"),
    ("merck and co", "MRK"),
    ("merck & co", "MRK"),
    ("modernatx", "MRNA"),
    ("moderna", "MRNA"),
    ("bristol-myers", "BMY"),
    ("bristol myers", "BMY"),
    ("johnson & johnson", "JNJ"),
    ("johnson and johnson", "JNJ"),
    ("eli lilly", "LLY"),
    ("astrazeneca", "AZN"),
    ("glaxosmithkline", "GSK"),
    ("crispr therapeutics", "CRSP"),
    ("legend biotech", "LEGN"),
    ("blueprint medicines", "BPMC"),
    ("revolution medicines", "RVMD"),
    ("beam therapeutics", "BEAM"),
    ("intra-cellular", "ITCI"),
    ("regeneron", "REGN"),
    ("biontech", "BNTX"),
    ("novavax", "NVAX"),
    ("vertex", "VRTX"),
    ("gilead", "GILD"),
    ("biogen", "BIIB"),
    ("alnylam", "ALNY"),
    ("sarepta", "SRPT"),
    ("biomarin", "BMRN"),
    ("ultragenyx", "RARE"),
    ("bridgebio", "BBIO"),
    ("apellis", "APLS"),
    ("argenx", "ARGX"),
    ("immunocore", "IMCR"),
    ("exelixis", "EXEL"),
    ("intellia", "NTLA"),
    ("editas", "EDIT"),
    ("janssen", "JNJ"),
    ("genentech", "RHHBY"),
    ("novartis", "NVS"),
    ("sanofi", "SNY"),
    ("abbvie", "ABBV"),
    ("amgen", "AMGN"),
    ("pfizer", "PFE"),
    ("incyte", "INCY"),
    ("ions", "IONS"),
    ("denali", "DNLI"),
    ("neurocrine", "NBIX"),
    ("karuna", "BMY"),
    ("seagen", "PFE"),
    ("lilly", "LLY"),
    ("roche", "RHHBY"),
    ("merck", "MRK"),
    ("gsk", "GSK"),
)

# query.spons values (lead + collaborator). Keep short — 6h watch paces CT.gov.
CTGOV_SPONSOR_QUERIES: tuple[str, ...] = (
    "ModernaTX",
    "Merck Sharp",
    "Pfizer",
    "BioNTech",
    "Novavax",
    "Eli Lilly",
    "Amgen",
    "Gilead",
    "Regeneron",
    "Vertex",
    "Bristol-Myers",
    "Janssen",
    "AbbVie",
    "AstraZeneca",
    "Biogen",
    "Alnylam",
    "CRISPR",
    "Sarepta",
    "Legend Biotech",
    "argenx",
)

ONCO_RE = re.compile(
    r"\b(oncol|cancer|tumor|tumour|melanoma|carcinoma|lymphoma|leukemia|"
    r"myeloma|sarcoma|nsclc|sclc|pembrolizumab|keytruda|checkpoint|"
    r"pd-?1|ctla-?4|car-?t|kras|egfr|her2|adc\b|intismeran|v940)\b",
    re.I,
)
EVENT_KW_RE = re.compile(
    r"\b(topline|interim(?:\s+analysis)?|readout|pdufa|adcom(?:m)?|"
    r"primary\s+endpoint|data\s+(?:in|expected|anticipated)|"
    r"expected\s+(?:in|during)|results\s+expected)\b",
    re.I,
)
_MONTH = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
_HALF_RE = re.compile(
    r"\b(?:(?P<h>h\s*[12]|[12]\s*h)|(?P<fh>first\s+half)|(?P<sh>second\s+half))\s*(?:of\s*)?(?P<y>20\d{2})\b",
    re.I,
)
_Q_RE = re.compile(r"\b(?P<q>q[1-4])\s*(?P<y>20\d{2})\b", re.I)
_MON_RE = re.compile(
    r"\b(?P<m>january|february|march|april|may|june|july|august|september|"
    r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
    r"\s+(?P<y>20\d{2})\b",
    re.I,
)
_YEAR_RE = re.compile(r"\b(?:in|during|by|for)\s+(?P<y>20\d{2})\b", re.I)
_THIS_YEAR_RE = re.compile(r"\b(?:later\s+)?this\s+year\b", re.I)
_INTERIM_RE = re.compile(r"\binterim(?:\s+analysis)?\b", re.I)
_TOPLINE_RE = re.compile(r"\btopline\b", re.I)
_PDUFA_RE = re.compile(r"\bpdufa\b", re.I)

# Medical-meeting windows. Abstract drop is when abstracts leak — often the real print.
CONFERENCES: tuple[dict[str, Any], ...] = (
    {
        "id": "aacr26",
        "name": "AACR",
        "start": "2026-04-17",
        "end": "2026-04-22",
        "abstract": "2026-03-11",
        "tags": ("oncology",),
    },
    {
        "id": "asco26",
        "name": "ASCO",
        "start": "2026-05-29",
        "end": "2026-06-02",
        "abstract": "2026-04-23",
        "tags": ("oncology",),
    },
    {
        "id": "esmo26",
        "name": "ESMO",
        "start": "2026-10-09",
        "end": "2026-10-13",
        "abstract": "2026-09-14",
        "tags": ("oncology",),
    },
    {
        "id": "ash26",
        "name": "ASH",
        "start": "2026-12-05",
        "end": "2026-12-08",
        "abstract": "2026-11-04",
        "tags": ("oncology", "heme"),
    },
    {
        "id": "jpm27",
        "name": "JPM Healthcare",
        "start": "2027-01-11",
        "end": "2027-01-14",
        "abstract": None,
        "tags": ("biotech",),
    },
    {
        "id": "aacr27",
        "name": "AACR",
        "start": "2027-04-16",
        "end": "2027-04-21",
        "abstract": "2027-03-10",
        "tags": ("oncology",),
    },
    {
        "id": "asco27",
        "name": "ASCO",
        "start": "2027-06-04",
        "end": "2027-06-08",
        "abstract": "2027-04-22",
        "tags": ("oncology",),
    },
)

LIVE_STATUSES = frozenset(
    {
        "ACTIVE_NOT_RECRUITING",
        "ENROLLING_BY_INVITATION",
        "COMPLETED",
        "RECRUITING",
    }
)
P3 = frozenset({"PHASE3", "PHASE2/PHASE3", "PHASE 3", "PHASE2_PHASE3"})
P2 = frozenset({"PHASE2", "PHASE 2", "PHASE1/PHASE2", "PHASE2/PHASE3"})
LEAD_W = 1.0
COLLAB_W = 0.72  # Moderna on Merck-led INTerpath still moved ~double

_MEM_CACHE: dict[str, Any] | None = None
_MEM_MTIME: float = 0.0


def _today(as_of: date | None = None) -> date:
    if as_of is not None:
        return as_of
    return datetime.now(timezone.utc).date()


def _parse_date(raw: Any) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    s = str(raw).strip()[:10]
    if len(s) < 7:
        return None
    try:
        if len(s) == 7:
            return date.fromisoformat(s + "-01")
        return date.fromisoformat(s)
    except ValueError:
        return None


def _days(a: date | None, b: date | None) -> int | None:
    if a is None or b is None:
        return None
    return (a - b).days


def _norm_org(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def map_org_to_ticker(name: str) -> str | None:
    n = _norm_org(name)
    if not n:
        return None
    for alias, ticker in SPONSOR_ALIASES:
        if re.search(rf"\b{re.escape(alias)}\b", n):
            return ticker
    return None


def _phase_set(raw: Any) -> set[str]:
    if raw is None:
        return set()
    if isinstance(raw, str):
        return {raw.replace(" ", "").upper()}
    out: set[str] = set()
    for p in raw:
        out.add(str(p).replace(" ", "").upper())
    return out


def flatten_study(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Accept nested CT.gov v2 JSON or a test fixture dict."""
    if not isinstance(raw, dict):
        return None
    ps = raw.get("protocolSection") if isinstance(raw.get("protocolSection"), dict) else None
    if ps:
        ident = ps.get("identificationModule") or {}
        status_m = ps.get("statusModule") or {}
        spons = ps.get("sponsorCollaboratorsModule") or {}
        design = ps.get("designModule") or {}
        pc = (status_m.get("primaryCompletionDateStruct") or {}).get("date")
        lu = (status_m.get("lastUpdatePostDateStruct") or {}).get("date") or status_m.get(
            "lastUpdatePostDate"
        )
        collabs = [
            str(c.get("name") or "")
            for c in (spons.get("collaborators") or [])
            if isinstance(c, dict)
        ]
        nct = str(ident.get("nctId") or ident.get("nct_id") or "").upper()
        has_res = bool(raw.get("hasResults") or raw.get("has_results"))
        phases = design.get("phases") or []
        title = str(ident.get("briefTitle") or ident.get("officialTitle") or "")
        lead = str((spons.get("leadSponsor") or {}).get("name") or "")
        status = str(status_m.get("overallStatus") or "")
    else:
        nct = str(raw.get("nct_id") or raw.get("nctId") or "").upper()
        title = str(raw.get("title") or raw.get("briefTitle") or "")
        lead = str(raw.get("lead_sponsor") or raw.get("leadSponsor") or "")
        collabs = [str(c) for c in (raw.get("collaborators") or [])]
        phases = raw.get("phases") or raw.get("phase") or []
        status = str(raw.get("status") or raw.get("overallStatus") or "")
        pc = raw.get("primary_completion") or raw.get("primaryCompletionDate")
        lu = raw.get("last_update") or raw.get("lastUpdatePostDate")
        has_res = bool(raw.get("has_results") or raw.get("hasResults"))
    if not nct:
        return None
    phase_s = _phase_set(phases)
    tickers: dict[str, str] = {}
    lt = map_org_to_ticker(lead)
    if lt:
        tickers[lt] = "lead"
    for c in collabs:
        ct = map_org_to_ticker(c)
        if ct and ct not in tickers:
            tickers[ct] = "collaborator"
    return {
        "nct_id": nct,
        "title": title,
        "lead_sponsor": lead,
        "collaborators": collabs,
        "phases": sorted(phase_s),
        "status": status.replace(" ", "_").upper(),
        "primary_completion": str(pc)[:10] if pc else None,
        "last_update": str(lu)[:10] if lu else None,
        "has_results": has_res,
        "oncology": bool(ONCO_RE.search(title or "")),
        "tickers": tickers,
    }


def window_heat(today: date, start: date, end: date) -> float:
    """0–1 heat for a guidance / conference window. Peaks in the last ~40 days."""
    if today > end + timedelta(days=14):
        return 0.0
    if today < start - timedelta(days=30):
        return 0.08
    if today < start:
        d = (start - today).days
        return 0.25 * max(0.0, 1.0 - d / 30.0)
    span = max(1, (end - start).days)
    left = (end - today).days
    elapsed = (today - start).days
    if left <= 40:
        return 0.72 + 0.28 * (1.0 - left / 40.0)
    return 0.40 + 0.20 * min(1.0, elapsed / max(1, span - 40))


def extract_guidance_windows(text: str, *, as_of: date | None = None) -> list[dict[str, Any]]:
    """Pull H1/H2/Qn/month/year windows that sit next to readout language."""
    today = _today(as_of)
    blob = text or ""
    if not blob.strip():
        return []
    tags: list[str] = []
    if _INTERIM_RE.search(blob):
        tags.append("interim")
    if _TOPLINE_RE.search(blob):
        tags.append("topline")
    if _PDUFA_RE.search(blob):
        tags.append("pdufa")
    has_kw = bool(EVENT_KW_RE.search(blob))
    windows: list[dict[str, Any]] = []

    def _add(kind: str, y: int, m0: int, d0: int, m1: int, d1: int, span: str) -> None:
        try:
            start = date(y, m0, d0)
            if m1 == 12:
                end = date(y, 12, 31)
            else:
                end = date(y, m1, d1)
        except ValueError:
            return
        if y < today.year - 1 or y > today.year + 2:
            return
        windows.append(
            {
                "kind": kind,
                "span": span,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "heat": round(window_heat(today, start, end), 4),
                "tags": list(tags),
            }
        )

    for m in _HALF_RE.finditer(blob):
        y = int(m.group("y"))
        token = (m.group("h") or m.group("fh") or m.group("sh") or "").lower().replace(" ", "")
        first = token in ("h1", "1h", "firsthalf") or "first" in token
        if first:
            _add("half", y, 1, 1, 6, 30, f"H1 {y}")
        else:
            _add("half", y, 7, 1, 12, 31, f"H2 {y}")
    for m in _Q_RE.finditer(blob):
        y = int(m.group("y"))
        q = int(m.group("q")[1])
        m0 = 1 + (q - 1) * 3
        m1 = m0 + 2
        _add("quarter", y, m0, 1, m1, 28 if m1 == 2 else 30, f"Q{q} {y}")
    for m in _MON_RE.finditer(blob):
        y = int(m.group("y"))
        mo = _MONTH[m.group("m").lower()]
        _add("month", y, mo, 1, mo, 28 if mo == 2 else 30, f"{m.group('m')} {y}")
    if has_kw:
        for m in _YEAR_RE.finditer(blob):
            y = int(m.group("y"))
            _add("year", y, 1, 1, 12, 31, f"{y}")
        if _THIS_YEAR_RE.search(blob):
            _add("year", today.year, 1, 1, 12, 31, f"{today.year}")

    # Dedup identical spans; keep max heat. Drop year buckets when H1/Qn/month exists.
    by_span: dict[str, dict[str, Any]] = {}
    for w in windows:
        prev = by_span.get(w["span"])
        if prev is None or float(w["heat"]) > float(prev["heat"]):
            by_span[w["span"]] = w
    out = list(by_span.values())
    specific_years = {
        str(w.get("start") or "")[:4]
        for w in out
        if w.get("kind") in ("half", "quarter", "month")
    }
    out = [
        w
        for w in out
        if not (w.get("kind") == "year" and str(w.get("start") or "")[:4] in specific_years)
    ]
    if tags and not out and has_kw:
        out.append(
            {
                "kind": "tag_only",
                "span": "+".join(tags),
                "start": today.isoformat(),
                "end": (today + timedelta(days=90)).isoformat(),
                "heat": 0.35,
                "tags": tags,
            }
        )
    return sorted(out, key=lambda w: -float(w["heat"]))


def conference_heat(today: date, *, oncology: bool, biotech: bool = True) -> dict[str, Any]:
    best = 0.0
    hit: dict[str, Any] | None = None
    for c in CONFERENCES:
        tags = tuple(c.get("tags") or ())
        if "oncology" in tags and not oncology:
            continue
        if "biotech" in tags and not biotech:
            continue
        start = _parse_date(c["start"])
        end = _parse_date(c["end"])
        absd = _parse_date(c.get("abstract"))
        if start is None or end is None:
            continue
        heat = window_heat(today, start, end)
        if absd is not None:
            # Abstract drop is often the leak. Ramp 21d before drop through meeting end.
            drop_heat = window_heat(today, absd - timedelta(days=7), absd + timedelta(days=3))
            heat = max(heat, min(1.0, drop_heat * 1.15), window_heat(today, absd, end))
        if heat > best:
            best = heat
            hit = {
                "id": c["id"],
                "name": c["name"],
                "start": c["start"],
                "abstract": c.get("abstract"),
                "heat": round(heat, 4),
            }
    return hit or {"heat": 0.0}


def study_pre_score(study: dict[str, Any], *, as_of: date | None = None) -> dict[str, Any]:
    """Score one flattened study. Far primary completion does **not** zero this out."""
    today = _today(as_of)
    st = study if "nct_id" in study and "tickers" in study else (flatten_study(study) or {})
    phases = set(st.get("phases") or [])
    status = str(st.get("status") or "")
    has_res = bool(st.get("has_results"))
    onco = bool(st.get("oncology"))
    pc = _parse_date(st.get("primary_completion"))
    lu = _parse_date(st.get("last_update"))
    dte_pc = _days(pc, today) if pc else None
    days_since_upd = _days(today, lu) if lu else None

    live = 0.0
    if not has_res and status in LIVE_STATUSES:
        is_p3 = bool(phases & P3) or any("PHASE3" in p for p in phases)
        is_p2 = bool(phases & P2) or any("PHASE2" in p for p in phases)
        if is_p3 and status == "ACTIVE_NOT_RECRUITING":
            live = 0.55  # enrollment done; interim can print any time
        elif is_p3 and status == "COMPLETED":
            # Recently finished, results not posted. Ancient COMPLETED+empty is a graveyard.
            # Milder than ANR — leftover completed COVID/device studies must not outrank live binaries.
            recent_pc = dte_pc is not None and -120 <= int(dte_pc) <= 30
            recent_upd = days_since_upd is not None and int(days_since_upd) <= 45
            if recent_pc or recent_upd:
                live = 0.32 if onco else 0.16
            else:
                live = 0.0
        elif is_p3 and status == "ENROLLING_BY_INVITATION":
            live = 0.48
        elif is_p3 and status == "RECRUITING":
            live = 0.28
            if days_since_upd is not None and days_since_upd > 300:
                live *= 0.35
        elif is_p2 and status == "ACTIVE_NOT_RECRUITING":
            live = 0.40
        elif is_p2 and status == "COMPLETED":
            recent_pc = dte_pc is not None and -240 <= int(dte_pc) <= 60
            recent_upd = days_since_upd is not None and int(days_since_upd) <= 60
            live = 0.40 if recent_pc else (0.28 if recent_upd else 0.0)
        elif is_p2:
            live = 0.22
        if onco and live > 0:
            live = min(0.85, live * 1.15)

    proximity = 0.0
    if dte_pc is not None and not has_res:
        if -14 <= dte_pc <= 90:
            proximity = 0.90 * (1.0 - min(abs(dte_pc), 90) / 120.0)
        elif dte_pc < -14:
            stale_completed = status == "COMPLETED" and (
                days_since_upd is None or int(days_since_upd) > 180
            )
            if stale_completed or dte_pc < -180 or status == "COMPLETED":
                # Post-completion without results is usually a graveyard, not an imminent print.
                proximity = 0.0
            else:
                overdue = min(180, abs(dte_pc))
                proximity = 0.40 + 0.20 * min(1.0, overdue / 120.0)

    last_upd = 0.0
    if days_since_upd is not None and days_since_upd <= 45 and live > 0.2:
        last_upd = 0.18 * (1.0 - days_since_upd / 45.0)

    pre = min(1.0, max(live, proximity) + 0.25 * min(live, proximity) + last_upd)
    return {
        "nct_id": st.get("nct_id"),
        "title": st.get("title"),
        "live_binary": round(live, 4),
        "proximity": round(proximity, 4),
        "last_update_heat": round(last_upd, 4),
        "pre": round(pre, 4),
        "days_to_primary": dte_pc,
        "days_since_update": days_since_upd,
        "oncology": onco,
        "status": status,
        "has_results": has_res,
        "tickers": dict(st.get("tickers") or {}),
        "primary_completion": st.get("primary_completion"),
    }


def exhaustion(ret_1d: float | None, mom_5d: float | None, *, live: float) -> float:
    """1.0 = already printed / do not chase. Needs a live binary so mega-caps don't fade on any rip."""
    if live < 0.18:
        return 0.0
    e = 0.0
    if ret_1d is not None and ret_1d >= 0.25:
        e = max(e, min(1.0, (float(ret_1d) - 0.15) / 0.70))
    if mom_5d is not None and mom_5d >= 0.40:
        e = max(e, min(1.0, (float(mom_5d) - 0.25) / 0.90))
    return round(e, 4)


def _effective_dte(
    *,
    live: float,
    days_to_primary: int | None,
    guidance: list[dict[str, Any]],
    today: date,
) -> int | None:
    """Sleeve horizon. Armed binaries use a near clock — not 2029 OS follow-up."""
    if guidance:
        top = guidance[0]
        start = _parse_date(top.get("start"))
        end = _parse_date(top.get("end"))
        if start and end:
            if start <= today <= end:
                left = (end - today).days
                return 7 if left <= 45 else 14
            if today < start:
                return max(1, (start - today).days)
            return -(today - end).days
    if days_to_primary is not None and abs(int(days_to_primary)) <= 90:
        return int(days_to_primary)
    if live >= 0.35:
        return 14  # could print this month; fortress still cares
    if live >= 0.18:
        return 21
    return days_to_primary


def score_ticker(
    ticker: str,
    studies: list[dict[str, Any]],
    *,
    guidance_text: str = "",
    as_of: date | None = None,
    eightk_recent: int = 0,
    industry_id: str | None = None,
) -> dict[str, Any]:
    today = _today(as_of)
    sym = ticker.strip().upper()
    scored = [study_pre_score(s, as_of=today) for s in studies]
    role_w = {"lead": LEAD_W, "collaborator": COLLAB_W}
    weighted: list[tuple[float, dict[str, Any]]] = []
    for sc in scored:
        role = (sc.get("tickers") or {}).get(sym)
        if not role:
            continue
        weighted.append((float(sc["pre"]) * float(role_w.get(role, COLLAB_W)), sc))
    weighted.sort(key=lambda kv: -kv[0])
    anr = [
        w
        for w in weighted
        if w[1].get("status") == "ACTIVE_NOT_RECRUITING" and float(w[1].get("live_binary") or 0) >= 0.35
    ]
    pool = anr if anr else weighted
    trial = 0.0
    if pool:
        trial = pool[0][0]
        if len(pool) > 1:
            second = pool[1][1]
            hot = float(second.get("proximity") or 0) > 0.15 or float(
                second.get("last_update_heat") or 0
            ) > 0.04
            if hot:
                trial = min(1.0, trial + 0.25 * pool[1][0])
    live = max((float(sc["live_binary"]) for _, sc in pool), default=0.0) if pool else 0.0
    onco = any(bool(sc.get("oncology")) for _, sc in weighted)
    bio = (industry_id or "").lower() in ("biotech", "pharma", "pharmaceuticals") or onco
    guides = extract_guidance_windows(guidance_text, as_of=today)
    g_heat = float(guides[0]["heat"]) if guides else 0.0
    if guides and guides[0].get("tags"):
        tags = set(guides[0]["tags"])
        if "interim" in tags:
            g_heat = min(1.0, g_heat + 0.20)
        if "topline" in tags:
            g_heat = min(1.0, g_heat + 0.22)
        if "pdufa" in tags:
            g_heat = min(1.0, g_heat + 0.25)
    conf = conference_heat(today, oncology=onco or bio, biotech=bio)
    c_heat = float(conf.get("heat") or 0.0)
    filing = 0.35 if int(eightk_recent or 0) >= 1 else 0.0
    pre = min(1.0, 0.70 * trial + 0.45 * g_heat + 0.25 * c_heat + 0.20 * filing)
    dte_pc = None
    if pool:
        dte_pc = pool[0][1].get("days_to_primary")
    dte = _effective_dte(live=live, days_to_primary=dte_pc, guidance=guides, today=today)
    shown = list(pool) + [w for w in weighted if w not in pool]
    return {
        "ticker": sym,
        "trial": round(trial, 4),
        "live_binary": round(live, 4),
        "guidance": round(g_heat, 4),
        "conference": round(c_heat, 4),
        "filing": round(filing, 4),
        "pre": round(pre, 4),
        "effective_dte": dte,
        "days_to_primary": dte_pc,
        "oncology": onco,
        "guidance_windows": guides[:4],
        "conference_hit": conf if c_heat > 0 else {},
        "studies": [
            {
                "nct_id": sc.get("nct_id"),
                "pre": sc.get("pre"),
                "live_binary": sc.get("live_binary"),
                "proximity": sc.get("proximity"),
                "days_to_primary": sc.get("days_to_primary"),
                "role": (sc.get("tickers") or {}).get(sym),
                "title": (sc.get("title") or "")[:160],
                "primary_completion": sc.get("primary_completion"),
                "status": sc.get("status"),
            }
            for _, sc in shown[:6]
        ],
        "as_of": today.isoformat(),
    }


def event_rank_boost(
    ticker: str,
    *,
    mom_5d: float = 0.0,
    ret_1d: float | None = None,
    sleeve: str | None = None,
    row: dict[str, Any] | None = None,
    as_of: date | None = None,
) -> tuple[float, dict[str, Any]]:
    """Additive rank in roughly [-1, 1]. Exhaustion turns a rip into a *downrank*."""
    meta: dict[str, Any] = {"applied": 0.0, "pre": 0.0, "exhaust": 0.0, "fit": 1.0}
    if os.getenv("USE_EVENT_CALENDAR", "true").strip().lower() in ("0", "false", "no"):
        meta["skipped"] = "disabled"
        return 0.0, meta
    rec = row if isinstance(row, dict) else ticker_row(ticker)
    if not rec or float(rec.get("pre") or 0) <= 0 and float(rec.get("live_binary") or 0) <= 0:
        return 0.0, meta
    live = float(rec.get("live_binary") or 0.0)
    pre = float(rec.get("pre") or 0.0)
    ex = exhaustion(ret_1d, mom_5d, live=live)
    dte = rec.get("effective_dte")
    try:
        from analytics.catalyst_horizon import catalyst_horizon_fit

        fit = float(catalyst_horizon_fit(dte, sleeve))
    except Exception:
        fit = 1.0
    if ex >= 0.45:
        boost = -0.55 * ex
    else:
        boost = pre * fit - 0.35 * ex
    boost = max(-1.0, min(1.0, float(boost)))
    meta.update(
        {
            "applied": round(boost, 4),
            "pre": round(pre, 4),
            "exhaust": ex,
            "fit": round(fit, 4),
            "effective_dte": dte,
            "live_binary": live,
            "nct": [s.get("nct_id") for s in (rec.get("studies") or [])[:3]],
        }
    )
    return boost, meta


def load_cache(*, force: bool = False) -> dict[str, Any]:
    global _MEM_CACHE, _MEM_MTIME
    if not CACHE_PATH.is_file():
        return {"tickers": {}, "studies": [], "updated_at": None}
    try:
        mtime = CACHE_PATH.stat().st_mtime
    except OSError:
        mtime = 0.0
    if not force and _MEM_CACHE is not None and mtime == _MEM_MTIME:
        return _MEM_CACHE
    try:
        doc = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"tickers": {}, "studies": [], "updated_at": None}
    if not isinstance(doc, dict):
        return {"tickers": {}, "studies": [], "updated_at": None}
    _MEM_CACHE = doc
    _MEM_MTIME = mtime
    return doc


def ticker_row(ticker: str) -> dict[str, Any]:
    doc = load_cache()
    rows = doc.get("tickers") if isinstance(doc.get("tickers"), dict) else {}
    rec = rows.get(ticker.strip().upper())
    return rec if isinstance(rec, dict) else {}


def write_cache(doc: dict[str, Any]) -> Path:
    global _MEM_CACHE, _MEM_MTIME
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, CACHE_PATH)
    _MEM_CACHE = doc
    try:
        _MEM_MTIME = CACHE_PATH.stat().st_mtime
    except OSError:
        _MEM_MTIME = 0.0
    return CACHE_PATH


def _ctgov_get(params: dict[str, Any], *, cache_key: str) -> dict[str, Any]:
    try:
        from intel.http_scheduler import get_json
    except Exception:
        return {}
    url = "https://clinicaltrials.gov/api/v2/studies"
    doc = get_json(
        url,
        params=params,
        ttl_sec=6 * 3600,
        timeout=22.0,
        cache_key=cache_key,
        allow_cache_on_error=True,
    )
    return doc if isinstance(doc, dict) else {}


def fetch_study_nct(nct: str) -> dict[str, Any] | None:
    nct_id = str(nct or "").strip().upper()
    if not nct_id.startswith("NCT"):
        return None
    doc = _ctgov_get({"query.term": nct_id, "pageSize": 1}, cache_key=f"ctgov:nct:{nct_id}")
    studies = doc.get("studies") or []
    if not studies or not isinstance(studies[0], dict):
        return None
    return flatten_study(studies[0])


def fetch_studies_for_sponsor(spons: str, *, page_size: int = 80) -> list[dict[str, Any]]:
    """CT.gov v2. Empty list on network/cache miss — never raises into rank.

    Live API rejects `filter.phase`. Phase is `filter.advanced=AREA[Phase]…`.
    """
    params: dict[str, Any] = {
        "query.spons": spons,
        "filter.advanced": "(AREA[Phase]PHASE2 OR AREA[Phase]PHASE3)",
        "filter.overallStatus": "RECRUITING,ACTIVE_NOT_RECRUITING,COMPLETED,ENROLLING_BY_INVITATION",
        "pageSize": int(min(1000, max(10, page_size))),
        "countTotal": "false",
    }
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    token = None
    for page in range(2):
        p = dict(params)
        if token:
            p["pageToken"] = token
        doc = _ctgov_get(p, cache_key=f"ctgov:v2:{spons}:p{page}")
        for raw in doc.get("studies") or []:
            flat = flatten_study(raw if isinstance(raw, dict) else {})
            if not flat:
                continue
            nct = str(flat.get("nct_id") or "")
            if nct and nct not in seen:
                seen.add(nct)
                out.append(flat)
        token = doc.get("nextPageToken")
        if not token:
            break
    return out


def eightk_recent_count(symbol: str, *, as_of: date | None = None, days: int = 2) -> tuple[int, str]:
    """How many 8-Ks in the last `days`, plus concatenated descriptions for guidance."""
    today = _today(as_of)
    try:
        from intel.open_web_intel import fetch_sec_filings
    except Exception:
        return 0, ""
    sec = fetch_sec_filings(symbol, limit=12)
    n = 0
    bits: list[str] = []
    for item in sec.get("filings") or []:
        form = str(item.get("form") or "").upper().replace(" ", "")
        if form not in ("8-K", "8K"):
            continue
        fd = _parse_date(item.get("date"))
        desc = str(item.get("description") or "")
        if desc:
            bits.append(desc)
        if fd is not None and 0 <= (today - fd).days <= days:
            n += 1
    return n, " | ".join(bits)


def _industry(ticker: str) -> str:
    try:
        from analytics.industries.peer_ticker_map import lookup

        return str(lookup(ticker) or "")
    except Exception:
        return ""


def refresh_event_calendar(
    *,
    sponsors: list[str] | None = None,
    extra_text: dict[str, str] | None = None,
    as_of: date | None = None,
    fetch_sec: bool = True,
    page_size: int = 40,
) -> dict[str, Any]:
    """Pull CT.gov (and light 8-K titles), score, write data/intel/event_calendar.json."""
    today = _today(as_of)
    prev_block = os.getenv("HTTP_BLOCK_ON_COOLDOWN")
    os.environ["HTTP_BLOCK_ON_COOLDOWN"] = "true"
    try:
        return _refresh_event_calendar_inner(
            sponsors=sponsors,
            extra_text=extra_text,
            as_of=today,
            fetch_sec=fetch_sec,
            page_size=page_size,
        )
    finally:
        if prev_block is None:
            os.environ.pop("HTTP_BLOCK_ON_COOLDOWN", None)
        else:
            os.environ["HTTP_BLOCK_ON_COOLDOWN"] = prev_block


def _refresh_event_calendar_inner(
    *,
    sponsors: list[str] | None,
    extra_text: dict[str, str] | None,
    as_of: date,
    fetch_sec: bool,
    page_size: int,
) -> dict[str, Any]:
    today = as_of
    queries = list(sponsors or CTGOV_SPONSOR_QUERIES)
    studies: dict[str, dict[str, Any]] = {}
    seed_raw = os.getenv("EVENT_CALENDAR_SEED_NCTS", "NCT05933577")
    for nct in [s.strip() for s in seed_raw.split(",") if s.strip()]:
        st = fetch_study_nct(nct)
        if st and st.get("nct_id"):
            studies[str(st["nct_id"])] = st
    for q in queries:
        for st in fetch_studies_for_sponsor(q, page_size=page_size):
            nct = st.get("nct_id")
            if nct:
                studies[str(nct)] = st
    study_list = list(studies.values())
    tickers: set[str] = set()
    for st in study_list:
        tickers.update((st.get("tickers") or {}).keys())
    extra = extra_text or {}
    rows: dict[str, Any] = {}
    for sym in sorted(tickers):
        n8, desc = (0, "")
        if fetch_sec:
            try:
                n8, desc = eightk_recent_count(sym, as_of=today)
            except Exception:
                n8, desc = 0, ""
        text = " ".join(x for x in (extra.get(sym, ""), desc) if x)
        rows[sym] = score_ticker(
            sym,
            study_list,
            guidance_text=text,
            as_of=today,
            eightk_recent=n8,
            industry_id=_industry(sym),
        )
        rows[sym]["eightk_recent"] = n8
    ranked = sorted(rows.values(), key=lambda r: -float(r.get("pre") or 0))
    doc = {
        "version": 2,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": today.isoformat(),
        "n_studies": len(study_list),
        "n_tickers": len(rows),
        "disclaimer": (
            "Public clocks only — does not predict unpublished trial results. "
            "Primary completion can be OS follow-up years after an interim print."
        ),
        "tickers": rows,
        "top": [
            {
                "ticker": r["ticker"],
                "pre": r["pre"],
                "live_binary": r["live_binary"],
                "guidance": r["guidance"],
                "effective_dte": r["effective_dte"],
                "nct": [s.get("nct_id") for s in (r.get("studies") or [])[:2]],
            }
            for r in ranked[:15]
        ],
        "studies": [
            {
                "nct_id": s.get("nct_id"),
                "title": (s.get("title") or "")[:160],
                "status": s.get("status"),
                "phases": s.get("phases"),
                "primary_completion": s.get("primary_completion"),
                "last_update": s.get("last_update"),
                "has_results": s.get("has_results"),
                "lead_sponsor": s.get("lead_sponsor"),
                "collaborators": s.get("collaborators"),
                "tickers": s.get("tickers"),
                "oncology": s.get("oncology"),
            }
            for s in study_list[:200]
        ],
    }
    write_cache(doc)
    return doc


# Fixture used by tests + canvas (Merck-led, Moderna collaborator, OS primary 2029).
INTERPATH_001: dict[str, Any] = {
    "nct_id": "NCT05933577",
    "title": (
        "A Clinical Study of Intismeran Autogene (V940) Plus Pembrolizumab "
        "in People With High-Risk Melanoma (INTerpath-001)"
    ),
    "lead_sponsor": "Merck Sharp & Dohme LLC",
    "collaborators": ["ModernaTX, Inc."],
    "phase": "PHASE3",
    "status": "ACTIVE_NOT_RECRUITING",
    "primary_completion": "2029-10-26",
    "last_update": "2025-09-24",
    "has_results": False,
}


__all__ = [
    "INTERPATH_001",
    "conference_heat",
    "event_rank_boost",
    "exhaustion",
    "extract_guidance_windows",
    "fetch_studies_for_sponsor",
    "fetch_study_nct",
    "flatten_study",
    "load_cache",
    "map_org_to_ticker",
    "refresh_event_calendar",
    "score_ticker",
    "study_pre_score",
    "ticker_row",
    "window_heat",
    "write_cache",
]
