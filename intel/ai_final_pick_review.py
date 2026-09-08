"""Final-list AI review: Tavily/DuckDuckGo snippets + batched LLM grades blended into picks.

Env (highlights):
  USE_AI_FINAL_PICK_REVIEW   true|false
  AI_PICK_LLM_MODEL          model for this step only (default gpt-4o; does not change global LLM_MODEL)
  AI_PICK_REVIEW_WEIGHT      0..1 blend on AI vs normalized model score (default 0.58)
  AI_PICK_REJECT_CONF        min confidence to honor verdict=reject
  AI_PICK_MIN_GRADE_FOR_LONG minimum letter grade to keep (A–F; default C). Below + conf → drop.
  AI_PICK_GRADE_DROP_CONF    min LLM confidence to enforce grade floor (default 0.40)
  AI_PICK_ALWAYS_DROP_F      drop F regardless of confidence (default true)
  AI_PICK_LLM_RETRIES        parse/call retries (default 2)
  AI_PICK_TAVILY_DEPTH       basic|advanced (default advanced)
  AI_PICK_TAVILY_MAX_RESULTS default 8
  TAVILY_API_KEY, LLM_API_KEY / OPENAI_API_KEY
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
from typing import Any

import requests

from utils import log

try:
    from intel.llm_signal_agent import _extract_json, _post_chat
except Exception:  # pragma: no cover
    _extract_json = None  # type: ignore[misc, assignment]
    _post_chat = None  # type: ignore[misc, assignment]


_GRADE_VAL = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}


def _b(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes")


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _grade_rank(letter: str) -> int:
    g = (letter or "C").strip().upper()[:1]
    return _GRADE_VAL.get(g, 2)


def _grade_meets_minimum(grade: str, min_letter: str) -> bool:
    return _grade_rank(grade) >= _grade_rank(min_letter)


def fetch_tavily_snippet(query: str, max_chars: int | None = None) -> str:
    key = (os.getenv("TAVILY_API_KEY") or "").strip()
    if not key:
        return ""
    depth = (os.getenv("AI_PICK_TAVILY_DEPTH", "advanced") or "advanced").strip().lower()
    if depth not in ("basic", "advanced"):
        depth = "advanced"
    max_results = _i("AI_PICK_TAVILY_MAX_RESULTS", 8)
    cap = max_chars if max_chars is not None else _i("AI_PICK_TAVILY_MAX_CHARS", 2600)
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": key,
                "query": query,
                "search_depth": depth,
                "max_results": max(3, min(max_results, 15)),
                "include_answer": True,
            },
            timeout=min(25.0, float(os.getenv("TAVILY_TIMEOUT_SEC", "18"))),
        )
        r.raise_for_status()
        js = r.json()
        parts: list[str] = []
        if js.get("answer"):
            parts.append(str(js["answer"]))
        for it in (js.get("results") or [])[:max_results]:
            if isinstance(it, dict):
                t = (it.get("title") or "").strip()
                c = (it.get("content") or "").strip()
                u = (it.get("url") or "").strip()
                line = f"{t}: {c}".strip()
                if u:
                    line = f"{line} ({u})"
                if line:
                    parts.append(line)
        out = "\n".join(parts)[:cap]
        return out
    except Exception as e:
        log.debug("[AI-PICK] Tavily failed: %s", e)
        return ""


def fetch_ddg_instant_answer(query: str, max_chars: int = 1400) -> str:
    try:
        q = urllib.parse.quote(query[:220])
        r = requests.get(
            f"https://api.duckduckgo.com/?q={q}&format=json&no_html=1&skip_disambig=1",
            headers={"User-Agent": "FATE_AlgoBot/1.4"},
            timeout=10.0,
        )
        r.raise_for_status()
        js = r.json()
        parts: list[str] = []
        if js.get("Abstract"):
            parts.append(str(js["Abstract"]))
        for t in (js.get("RelatedTopics") or [])[:8]:
            if isinstance(t, dict) and t.get("Text"):
                parts.append(str(t["Text"])[:450])
        return "\n".join(parts)[:max_chars]
    except Exception as e:
        log.debug("[AI-PICK] DDG failed: %s", e)
        return ""


def build_web_context(ticker: str) -> str:
    t = ticker.upper().strip()
    half = max(800, _i("AI_PICK_TAVILY_MAX_CHARS", 2600) // 2)
    q1 = f"{t} stock earnings revenue guidance analyst upgrades downgrades"
    q2 = f"{t} company SEC investigation lawsuit bankruptcy dilution risk"
    blob = fetch_tavily_snippet(q1, max_chars=half)
    blob2 = fetch_tavily_snippet(q2, max_chars=half)
    merged = "\n---\n".join(x for x in (blob, blob2) if x.strip())
    if not merged.strip():
        merged = fetch_ddg_instant_answer(f"{t} stock news earnings")
    return merged or "(no web snippet — lean neutral; do not invent facts.)"


def _llm_key_ok() -> bool:
    return bool((os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip())


def _normalize_review_item(it: dict) -> dict | None:
    if not isinstance(it, dict):
        return None
    tk = str(it.get("ticker", "")).upper().strip()
    if not tk:
        return None
    verdict = str(it.get("verdict", "hold")).lower().strip()[:12]
    if verdict not in ("approve", "reject", "hold"):
        verdict = "hold"
    grade = str(it.get("grade", "C")).upper().strip()[:1]
    if grade not in _GRADE_VAL:
        grade = "C"
    try:
        conf = float(it.get("confidence", 0.0) or 0.0)
    except Exception:
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    try:
        pfs = float(it.get("profit_focus_score", 0.5) or 0.5)
    except Exception:
        pfs = 0.5
    pfs = max(0.0, min(1.0, pfs))
    rf = it.get("red_flags")
    if not isinstance(rf, list):
        rf = []
    rf = [str(x)[:120] for x in rf[:8]]
    return {
        "ticker": tk,
        "verdict": verdict,
        "grade": grade,
        "confidence": conf,
        "profit_focus_score": pfs,
        "red_flags": rf,
        "one_line": str(it.get("one_line", ""))[:220],
    }


def _fill_missing_reviews(expected: list[str], reviews: list[dict]) -> list[dict]:
    by_t = {str(x["ticker"]).upper(): x for x in reviews if x.get("ticker")}
    out: list[dict] = []
    for t in expected:
        if t in by_t:
            out.append(by_t[t])
            continue
        log.warning("[AI-PICK] LLM omitted %s — injecting conservative hold", t)
        out.append(
            {
                "ticker": t,
                "verdict": "hold",
                "grade": "C",
                "confidence": 0.35,
                "profit_focus_score": 0.48,
                "red_flags": ["llm_omitted_ticker"],
                "one_line": "No model output for this ticker; conservative hold.",
            }
        )
    return out


def _run_llm_once(slim: list[dict], regime_name: str, vix: float | None) -> dict[str, Any]:
    blocks: list[str] = []
    for r in slim:
        t = str(r.get("ticker", "")).upper()
        web = build_web_context(t)
        earn_ctx = ""
        try:
            from intel.earnings_calendar import earnings_context_text, earnings_snapshot

            earn_ctx = earnings_context_text(t)
            es = earnings_snapshot(t)
        except Exception:
            es = {}
        news_ai = r.get("news_ai") or {}
        blocks.append(
            f"=== {t} ===\n"
            f"model_p_up={float(r.get('p_up', 0.5)):.3f}  score={float(r.get('score', 0)):.4f}  "
            f"exec_conf={float(r.get('execution_confidence', 0)):.3f}  asym={r.get('asym_action','?')}  "
            f"sent={float(r.get('sentiment', 0)):.2f}  mom5d={float(r.get('momentum_5d', 0))*100:.2f}%  "
            f"rs_spy={float(r.get('rs_spy', 1)):.3f}  dip_signal={float(r.get('dip_signal', 0)):.3f}\n"
            f"EARNINGS: {earn_ctx or 'unknown'}  days_to_earnings={es.get('days_to_earnings', r.get('days_to_earnings', '?'))}\n"
            f"NEWS_AI: narrative={news_ai.get('narrative','?')} good={float(news_ai.get('good_news_score',0)):.2f} "
            f"bad={float(news_ai.get('bad_news_score',0)):.2f} thesis={str(news_ai.get('llm_thesis',''))[:160]}\n"
            f"WEB_SNIPPET:\n{web}\n"
        )
    joined = "\n".join(blocks)
    system = (
        "You are a senior long-biased equity PM optimizing risk-adjusted profit over days to a few weeks. "
        "Not financial advice. Be skeptical: prefer passing on marginal names over chasing hype.\n"
        "Rules:\n"
        "- Use WEB_SNIPPET + EARNINGS + NEWS_AI as primary external evidence. If snippets are thin, verdict should be hold or weak approve, "
        "never strong approve, and never fabricate events.\n"
        "- Penalize names with bad_news narrative, high bad_news_score, or imminent earnings binary risk unless reward/risk is exceptional.\n"
        "- Reward good_news narrative with strong good_news_score when earnings window is clear.\n"
        "- profit_focus_score: 0=poor expected reward / high risk of loss, 1=strong asymmetric long setup given evidence.\n"
        "- grade: A exceptional, B good, C acceptable only if reward/risk ok, D weak, F structurally bad or broken story.\n"
        "- verdict=reject only for clear deal-breakers (e.g. fraud, bankruptcy, hopeless dilution, delisting spiral) "
        "when snippet or uncontroversial public facts support it. If unsure, hold — do not reject.\n"
        "- Large drawdowns can create *mean-reversion* or oversold-bounce setups — mildly raise profit_focus_score when "
        "dip_signal is high AND snippets show no structural impairment (still penalize broken fundamentals / dilution).\n"
        "- Do NOT assume 'fell a lot so must rip'; many names keep sliding. Snippets + fundamentals discipline the bounce thesis.\n"
        "- VIX elevated: be more selective (lower profit_focus_score unless defensive quality).\n"
        "Return ONE JSON object only with key \"reviews\" array. Each element must include all keys below.\n"
        'Schema: {"reviews":[{"ticker":"SYM","verdict":"approve|reject|hold","grade":"A|B|C|D|F",'
        '"confidence":0-1,"profit_focus_score":0-1,"red_flags":[],"one_line":"..."}]}\n'
        "You MUST include one review object per ticker block shown by the user, same tickers, no extras."
    )
    user = (
        f"MARKET_REGIME={regime_name!r}  VIX={vix if vix is not None else 'unknown'}\n"
        f"VIX_ELEVATED={'yes' if (vix is not None and float(vix) > 22) else 'no'}\n\n"
        f"CANDIDATE_LONG_PICKS ({len(slim)} names):\n\n{joined[:28000]}"
    )
    raw = _post_chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
    obj = _extract_json(raw)
    revs = obj.get("reviews")
    if not isinstance(revs, list):
        raise ValueError("reviews not a list")
    parsed: list[dict] = []
    for it in revs:
        n = _normalize_review_item(it)
        if n:
            parsed.append(n)
    tickers = [str(r.get("ticker", "")).upper() for r in slim]
    filled = _fill_missing_reviews(tickers, parsed)
    return {
        "enabled": True,
        "model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
        "reviews": filled,
    }


def review_final_picks(
    picks: list[dict],
    *,
    regime_name: str = "",
    vix: float | None = None,
) -> dict[str, Any]:
    if not picks:
        return {"enabled": False, "reason": "empty_picks", "reviews": []}
    if not _b("USE_AI_FINAL_PICK_REVIEW", True):
        return {"enabled": False, "reason": "disabled", "reviews": []}
    if _post_chat is None or _extract_json is None:
        return {"enabled": False, "reason": "llm_import_failed", "reviews": []}
    if not _llm_key_ok():
        log.warning("[AI-PICK] No LLM_API_KEY / OPENAI_API_KEY — skipping final AI review")
        return {"enabled": False, "reason": "no_api_key", "reviews": []}

    max_n = _i("AI_PICK_MAX_SYMBOLS", 24)
    slim = picks[:max_n]
    retries = max(1, _i("AI_PICK_LLM_RETRIES", 2))

    timeout_prev = os.environ.get("LLM_TIMEOUT_SEC")
    model_prev = os.environ.get("LLM_MODEL")
    os.environ["LLM_TIMEOUT_SEC"] = str(float(os.getenv("AI_PICK_LLM_TIMEOUT_SEC", "55")))
    pick_model = (os.getenv("AI_PICK_LLM_MODEL") or "gpt-4o").strip()
    if pick_model:
        os.environ["LLM_MODEL"] = pick_model

    last_err: Exception | None = None
    try:
        for attempt in range(retries):
            try:
                meta = _run_llm_once(slim, regime_name, vix)
                meta["tavily_depth"] = os.getenv("AI_PICK_TAVILY_DEPTH", "advanced")
                meta["attempt"] = attempt + 1
                return meta
            except Exception as e:
                last_err = e
                log.warning("[AI-PICK] attempt %s/%s failed: %s", attempt + 1, retries, e)
                if attempt + 1 < retries:
                    time.sleep(0.8 * (attempt + 1))
        log.warning("[AI-PICK] batch review failed after retries: %s", last_err)
        return {"enabled": False, "reason": str(last_err)[:200] if last_err else "unknown", "reviews": []}
    finally:
        if timeout_prev is None:
            os.environ.pop("LLM_TIMEOUT_SEC", None)
        else:
            os.environ["LLM_TIMEOUT_SEC"] = timeout_prev
        if model_prev is None:
            os.environ.pop("LLM_MODEL", None)
        else:
            os.environ["LLM_MODEL"] = model_prev


def apply_ai_review_to_long_picks(
    picks: list[dict],
    *,
    regime_name: str = "",
    vix: float | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    meta = review_final_picks(picks, regime_name=regime_name, vix=vix)
    if not meta.get("enabled"):
        return picks, meta

    w = _f("AI_PICK_REVIEW_WEIGHT", 0.58)
    w = max(0.0, min(1.0, w))
    rej_min_conf = _f("AI_PICK_REJECT_CONF", 0.52)
    min_grade = (os.getenv("AI_PICK_MIN_GRADE_FOR_LONG", "C") or "C").strip().upper()[:1]
    if min_grade not in _GRADE_VAL:
        min_grade = "C"
    grade_drop_conf = _f("AI_PICK_GRADE_DROP_CONF", 0.40)

    reviews = {str(x["ticker"]).upper(): x for x in meta.get("reviews", []) if x.get("ticker")}

    scores_model = [float(r.get("score", 0.0)) for r in picks]
    lo, hi = min(scores_model), max(scores_model)
    span = hi - lo + 1e-9

    def model_norm(r: dict) -> float:
        return (float(r.get("score", 0.0)) - lo) / span

    kept: list[dict] = []
    for r in picks:
        t = str(r["ticker"]).upper()
        rv = reviews.get(t)
        if not rv:
            kept.append({**r, "ai_pick_review": None, "ai_blend_rank": float(r.get("score", 0.0))})
            continue

        verdict = str(rv.get("verdict", "hold"))
        conf = float(rv.get("confidence", 0.0) or 0.0)
        grade = str(rv.get("grade", "C")).upper()[:1]

        if verdict == "reject" and conf >= rej_min_conf:
            log.warning("[AI-PICK] rejected %s (conf=%.2f): %s", t, conf, rv.get("one_line", ""))
            continue

        if _b("AI_PICK_ALWAYS_DROP_F", True) and grade == "F":
            log.warning("[AI-PICK] dropped %s grade=F", t)
            continue

        if not _grade_meets_minimum(grade, min_grade) and conf >= grade_drop_conf:
            log.warning("[AI-PICK] dropped %s grade=%s below min=%s (conf=%.2f)", t, grade, min_grade, conf)
            continue

        ai_s = max(0.0, min(1.0, float(rv.get("profit_focus_score", 0.5))))
        # Slightly penalize weak grades in the scalar used for ranking (not a second gate).
        grade_adj = {"A": 1.0, "B": 0.97, "C": 0.90, "D": 0.78, "F": 0.55}.get(grade, 0.88)
        ai_eff = max(0.0, min(1.0, ai_s * grade_adj))

        blend = (1.0 - w) * model_norm(r) + w * ai_eff
        nr = {
            **r,
            "ai_pick_review": rv,
            "ai_blend_rank": blend,
            "ai_grade": grade,
            "ai_profit_focus_score": ai_s,
        }
        kept.append(nr)

    kept.sort(key=lambda x: -float(x.get("ai_blend_rank", x.get("score", 0.0))))
    meta["picks_before"] = len(picks)
    meta["picks_after"] = len(kept)
    meta["blend_weight"] = w
    meta["min_grade"] = min_grade
    return kept, meta
