"""Transcript-to-factor conversion for videos/podcasts/recommendation media."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import json
import re

from news_reader import analyze_sentiment
from intel.repetition_weighting import phrase_repetition_score
from intel.llm_signal_agent import score_documents_with_llm


ACTION_RE = re.compile(r"\b(buy|sell|short|accumulate|avoid|hold)\b", re.I)
URGENCY_RE = re.compile(r"\b(now|immediately|urgent|must|critical|asap)\b", re.I)
HORIZON_RE = re.compile(r"\b(week|month|quarter|year|long-term|short-term)\b", re.I)


@dataclass
class TranscriptFactors:
    sentiment: float
    action_density: float
    urgency_density: float
    horizon_density: float
    repetition_persistence: float
    recommendation_strength: float
    final_factor: float
    sample_count: int
    generated_at_utc: str


def _dens(rx: re.Pattern, text: str) -> float:
    toks = max(1, len(text.split()))
    return len(rx.findall(text)) / toks


def score_transcript_texts(texts: list[str]) -> dict:
    if not texts:
        return asdict(
            TranscriptFactors(
                sentiment=0.0,
                action_density=0.0,
                urgency_density=0.0,
                horizon_density=0.0,
                repetition_persistence=0.0,
                recommendation_strength=0.0,
                final_factor=0.0,
                sample_count=0,
                generated_at_utc=datetime.now(timezone.utc).isoformat(),
            )
        )

    sent_vals = [float(analyze_sentiment(t)) for t in texts]
    sentiment = sum(sent_vals) / max(1, len(sent_vals))
    action_density = sum(_dens(ACTION_RE, t) for t in texts) / len(texts)
    urgency_density = sum(_dens(URGENCY_RE, t) for t in texts) / len(texts)
    horizon_density = sum(_dens(HORIZON_RE, t) for t in texts) / len(texts)
    rep = phrase_repetition_score(texts, ngram=4)
    llm = score_documents_with_llm("TRANSCRIPT", texts)
    llm_sent = float(llm.get("sentiment", 0.0))
    llm_conf = float(llm.get("confidence", 0.0))
    llm_action = float(llm.get("action_bias", 0.0))
    rec_strength = 0.6 * action_density + 0.25 * urgency_density + 0.15 * horizon_density
    base = 0.55 * sentiment + 0.45 * rec_strength
    base = 0.75 * base + 0.15 * llm_sent + 0.10 * llm_action
    final = base * (1.0 + rep.persistence_score) * (0.85 + 0.15 * max(0.0, llm_conf))

    event_windows: list = []
    try:
        from analytics.event_calendar import extract_guidance_windows
        from datetime import date as _date

        joined = "\n".join(texts)
        event_windows = extract_guidance_windows(joined, as_of=_date.today())
    except Exception:
        event_windows = []

    out = TranscriptFactors(
        sentiment=float(sentiment),
        action_density=float(action_density),
        urgency_density=float(urgency_density),
        horizon_density=float(horizon_density),
        repetition_persistence=float(rep.persistence_score),
        recommendation_strength=float(rec_strength),
        final_factor=float(final),
        sample_count=len(texts),
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    ret = asdict(out)
    ret["llm_sentiment"] = llm_sent
    ret["llm_confidence"] = llm_conf
    ret["llm_action_bias"] = llm_action
    ret["llm_key_thesis"] = str(llm.get("key_thesis", ""))
    ret["event_windows"] = event_windows
    return ret


def score_symbol_transcripts(symbol: str, replay_transcript_path: str | None = None) -> dict:
    texts: list[str] = []
    if replay_transcript_path:
        p = Path(replay_transcript_path)
    else:
        p = Path("data/replay/transcripts") / f"{symbol.upper().replace('/', '_')}.jsonl"
    if p.is_file():
        with open(p, encoding="utf-8") as f:
            for ln in f:
                try:
                    obj = json.loads(ln)
                    txt = str(obj.get("text", "")).strip()
                    if txt:
                        texts.append(txt)
                except Exception:
                    continue
    return score_transcript_texts(texts)

