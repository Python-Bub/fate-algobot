"""Financial headline lexicon + per-headline good/bad/neutral classification."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Strong bearish / bullish phrases (checked before single-word hits).
_PHRASE_NEG = re.compile(
    r"\b("
    r"misses?\s+estimates|missed\s+estimates|guidance\s+cut|cuts?\s+guidance|"
    r"profit\s+warning|earnings\s+miss|revenue\s+miss|"
    r"stock\s+(crash|crashes|crashing|plunge|plunges|plunging|tumble|tumbles|tumbling|"
    r"selloff|sell-off|slump|slumps|tank|tanks|tanking|drop|drops|dropping|dip|dips|dipping)|"
    r"stock\s+is\s+(down|dropping|falling|sliding|tumbling)|"
    r"shares?\s+(crash|crashes|crashing|plunge|plunges|tumble|tumbles|sink|sinks|fall|falls)|"
    r"downgrade[ds]?|price\s+target\s+cut|cuts?\s+price\s+target|"
    r"underperform|sell\s+rating|bearish\s+(call|outlook|view)|"
    r"layoffs?|job\s+cuts?|restructur(ing|e)\s+.*\s+cut|"
    r"sec\s+(probe|investigation)|class\s+action|accounting\s+(irregular|probe)|"
    r"going\s+concern|chapter\s+11|bankruptcy|"
    r"disappointing\s+(results|earnings|revenue)|"
    r"warns?\s+of\s+(weak|lower|slower)|"
    r"ai\s+spending\s+(slow|slowdown|concern)|"
    r"regulatory\s+(risk|scrutiny|pressure)|"
    r"insiders?\s+sold|insider\s+sale|insider\s+sell|"
    r"(?:ceo|cfo|coo|chief|president|chairman|director|officer).{0,50}sell|"
    r"sold\s+\$[\d.,]+\s*(?:m|million|b|billion)\s*(?:of\s+)?(?:stock|shares)?|"
    r"sells?\s+\$[\d.,]+\s*(?:m|million|b|billion)|"
    r"sells?\s+[\d,]+\s+shares|10b5-?1|form\s+4|officer\s+sold|executive\s+sold|"
    r"chief\s+\w+\s+officer.{0,40}sell"
    r")\b",
    re.I,
)

_PHRASE_POS = re.compile(
    r"\b("
    r"beats?\s+estimates|beat\s+estimates|topped\s+estimates|"
    r"guidance\s+raise|raises?\s+guidance|raised\s+guidance|"
    r"earnings\s+beat|revenue\s+beat|record\s+(revenue|profit|earnings)|"
    r"upgrade[ds]?|price\s+target\s+raise|raises?\s+price\s+target|"
    r"outperform|overweight|buy\s+rating|bullish\s+(call|outlook|view)|"
    r"stock\s+(surge|surges|soar|soars|rally|rallies|jump|jumps|rebound|rebounds)|"
    r"shares?\s+(surge|soar|rally|jump|rebound|rise|rise\s+on)|"
    r"buyback|repurchase|dividend\s+raise|"
    r"strong\s+(demand|growth|quarter|results|earnings)|"
    r"ai\s+(boom|tailwind|growth|momentum)|"
    r"disclos(?:es|ed|ing)\s+(?:a\s+)?(?:large\s+|new\s+|major\s+)?stake|"
    r"new\s+stake|builds?\s+(?:a\s+)?stake|13f\s+filing|"
    r"pershing\s+square|bill\s+ackman|activist\s+stake|"
    r"initiated\s+(?:a\s+)?position|largest\s+(?:position|holding)|"
    r"undervalued|under\s*valued|below\s+fair\s+value|trading\s+below\s+(fair|intrinsic)|"
    r"\d{1,2}\s*%\s*(undervalued|upside|discount)|"
    r"margin\s+of\s+safety|cheap\s+vs\s+(fair|intrinsic)|bargain\s+(buy|valuation)|"
    r"price\s+target\s+(implies|suggests)|intrinsic\s+value\s+(above|higher)|"
    r"worth\s+more\s+than|trading\s+at\s+a\s+discount"
    r")\b",
    re.I,
)

_WORD_NEG = re.compile(
    r"\b("
    r"crash|crashing|plunge|plunging|tumble|tumbling|selloff|slump|sink|tank|"
    r"miss|missed|downgrade|weak|loss|losses|fraud|lawsuit|probe|bankrupt|"
    r"bearish|underperform|cut|cuts|warning|disappoint|disappointing|"
    r"concern|concerns|fear|fears|worry|worries|overhang|risk|risks|"
    r"layoff|layoffs|dilution|recall|investigation|scandal|"
    r"decline|declines|declining|fall|falls|falling|drop|drops|dropping|dipping|dip|"
    r"slide|slides|sliding|tumble|tumbles|crashes|crashing"
    r")\b",
    re.I,
)

_WORD_POS = re.compile(
    r"\b("
    r"surge|soar|rally|jump|rebound|beat|beats|upgrade|strong|record|"
    r"bullish|outperform|growth|raise|raised|buyback|tailwind|momentum|"
    r"optimism|optimistic|accelerat|accelerating|exceed|exceeded|"
    r"undervalued|upside|bargain|discounted"
    r")\b",
    re.I,
)

# Negation flips the next clause's lean (simple: "not beat" -> bearish).
_NEGATION = re.compile(r"\b(not|no|never|fail|failed|fails|without)\b", re.I)


@dataclass
class HeadlineSentiment:
    label: str  # bullish | bearish | neutral
    score: float  # [-1, 1]
    pos_hits: list[str]
    neg_hits: list[str]
    phrase_pos: bool
    phrase_neg: bool


def classify_headline(text: str) -> HeadlineSentiment:
    """Classify one headline+summary string into bullish / bearish / neutral."""
    t = (text or "").strip()
    if not t:
        return HeadlineSentiment("neutral", 0.0, [], [], False, False)

    phrase_neg = bool(_PHRASE_NEG.search(t))
    phrase_pos = bool(_PHRASE_POS.search(t))
    neg_words = _WORD_NEG.findall(t)
    pos_words = _WORD_POS.findall(t)

    neg_hits = list(dict.fromkeys(neg_words))
    pos_hits = list(dict.fromkeys(pos_words))

    score = 0.0
    if phrase_neg:
        score -= 0.85
    if phrase_pos:
        score += 0.85
    score += 0.22 * min(len(pos_hits), 5)
    score -= 0.22 * min(len(neg_hits), 5)

    if _NEGATION.search(t) and phrase_pos and not phrase_neg:
        score *= 0.35
    if _NEGATION.search(t) and phrase_neg and not phrase_pos:
        score *= 0.35

    score = max(-1.0, min(1.0, score))

    if score >= 0.22:
        label = "bullish"
    elif score <= -0.22:
        label = "bearish"
    else:
        label = "neutral"

    return HeadlineSentiment(
        label=label,
        score=score,
        pos_hits=pos_hits[:8],
        neg_hits=neg_hits[:8],
        phrase_pos=phrase_pos,
        phrase_neg=phrase_neg,
    )
