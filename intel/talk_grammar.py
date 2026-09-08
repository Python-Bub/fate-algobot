"""Grammar + typo teaching data for the homemade talk brain.

Goal: replies sound like careful English; inputs with typos still map to intent.
"""

from __future__ import annotations

import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "talk_brain" / "grammar_corpus.txt"

# Perfect-English conversational replies (teacher style).
CLEAN_PAIRS = [
    ("hey", "Hey."),
    ("hi", "Hi."),
    ("hello", "Hello."),
    ("how are you", "I am well, thank you. How are you?"),
    ("what's up", "Not much. Ready to talk."),
    ("thanks", "You are welcome."),
    ("thank you", "You are welcome."),
    ("bye", "Goodbye."),
    ("see you", "See you later."),
    ("who are you", "I am a small offline chat brain on this computer."),
    ("what are you", "I am an offline chat brain — no cloud AI."),
    ("are you smart", "Still learning. I try to stay clear and honest."),
    ("tell me a joke", "Why did the comma break up with the apostrophe? It needed space."),
    ("be serious", "Understood. Direct answers from here."),
    ("help", "Just type. /status for stack, /quit to leave."),
    ("i made a typo", "No worries — I will read past typos."),
    ("fix my english", "Speak naturally. I will answer in clear English."),
    ("use perfect grammar", "I will reply with clear, correct English."),
    ("do you understand typos", "Yes. I try to read past typos and answer the meaning."),
    ("what is grammar", "Grammar is the rules for forming words and sentences correctly."),
    ("explain a sentence", "A complete sentence usually needs a subject and a verb."),
    ("is this correct", "Share the sentence and I will restate it clearly."),
    ("good morning", "Morning."),
    ("good night", "Good night."),
    ("i am bored", "We can talk about whatever is on your mind."),
    ("i am sad", "Sorry you feel that way. I am here."),
    ("i am happy", "Glad to hear that."),
    ("ok", "Okay."),
    ("okay", "Okay."),
    ("how is it going", "Going well. How are you?"),
    ("how's it going", "Going well. How are you?"),
    ("alright well how is it going", "Pretty well. Just chatting."),
    ("do you understand complex vocabulary", "Common words and some tech terms — I am a small offline model."),
    ("oh do you understand complex vocabulary", "Somewhat. I chat in plain English, not dictionary dumps."),
    ("complex vocabulary", "Plain conversation beats dictionary fragments. Ask away."),
    ("please read my codebase", "Read-only. Ask briefing or find errors."),
    ("read my codebase", "Wired read-only. I can summarize repo and stack status."),
    ("can you see my code", "Yes — observe only. No edits."),
    ("you too", "You too."),
    ("excuse me", "Yes? What's up?"),
    ("what do you mean", "Which part? Say it another way."),
    ("yes", "Understood."),
    ("no", "Understood."),
    ("maybe", "Fair. We can decide later."),
    ("what time is it", "No live clock here — check your device."),
    ("weather", "No weather API. Still happy to chat."),
    ("random", "Okay — here is a plain sentence: The train left on time."),
    ("say something smart", "Clear thinking starts with clear language."),
    ("say something random", "Okay — here is a plain sentence: Clear words beat fancy ones."),
    ("wdym", "What do you mean? Which part?"),
    ("good", "Nice."),
    ("good good", "Glad to hear it."),
    ("huh", "Hmm? Say that again."),
    ("what", "Hmm? Say that again."),
    ("teach me english", "Ask me to define a word or fix a sentence."),
    ("subject verb agreement", "Singular subject → singular verb: she runs. Plural: they run."),
    ("when to use their", "Their = possession. There = place. They're = they are."),
    ("its or it's", "It's = it is. Its = possession."),
    ("your or you're", "Your = possession. You're = you are."),
    ("then or than", "Then = time. Than = comparison."),
    ("affect or effect", "Affect is usually a verb. Effect is usually a noun."),
    ("comma splice", "Do not join two full sentences with only a comma."),
    ("run on sentence", "Split jammed ideas into shorter complete sentences."),
    ("keep it short", "Got it. I'll keep it short."),
    ("keep em small", "OK — short answers from here."),
    ("shorter", "Sure — shorter from here."),
    ("be brief", "Brief it is."),
    ("stop making these big responses keep em small", "Got it. I'll keep it short."),
]

# Common typo / slang → intended meaning, reply still perfect English.
TYPO_PAIRS = [
    ("helo", "Hello."),
    ("hallo", "Hello."),
    ("how r u", "I am well. How are you?"),
    ("how are yu", "I am well. How are you?"),
    ("wat's up", "Not much. Ready to talk."),
    ("whats up", "Not much. Ready to talk."),
    ("whats goin on", "Not much. Ready to talk."),
    ("what's goin on", "Not much. Ready to talk."),
    ("whats going on", "Not much. Ready to talk."),
    ("hows it going", "Going well. How are you?"),
    ("sup", "Sup."),
    ("thx", "You are welcome."),
    ("ty", "You are welcome."),
    ("thanku", "You are welcome."),
    ("plz", "Sure — what do you need?"),
    ("pls help", "Sure — what do you need?"),
    ("i dont no", "That is okay. We can figure it out."),
    ("i dunno", "That is okay. We can figure it out."),
    ("idk", "That is okay. We can figure it out."),
    ("wht does that mean", "Tell me the word and I will explain."),
    ("defin this", "Share the word and I will define it."),
    ("teh", "Got it — the. What next?"),
    ("becuase", "Got it — because."),
    ("recieve", "Spelling is receive."),
    ("seperate", "Spelling is separate."),
    ("definately", "Spelling is definitely."),
    ("tomorow", "Spelling is tomorrow."),
    ("tommorow", "Spelling is tomorrow."),
    ("gonna", "Got it — you mean going to."),
    ("wanna", "Got it — want to."),
    ("gotta", "Got it — got to."),
    ("im good", "Glad you are doing well."),
    ("i'm fine", "Glad you are doing well."),
    ("cant", "Got it. What is not working?"),
    ("wont", "Got it. Tell me more."),
    ("doesnt work", "Sorry — describe the problem."),
    ("it aint working", "Sorry — describe the problem."),
    ("ur cool", "Thanks."),
    ("u there", "Yes, I am here."),
    ("are u ther", "Yes, I am here."),
    ("speak proply", "I will reply in clear English."),
    ("use grammer", "I will use careful grammar."),
    ("fix grammer", "I will use careful grammar."),
    ("perfec english", "Clear English — got it."),
    ("sayinng", "I think you meant saying. Go on."),
    ("smth", "Got it — something."),
    ("yk", "Got it — you know."),
    ("nay", "Got it — any."),
    ("malfuncioning", "Got it — malfunctioning."),
    ("keep em small", "OK — short answers from here."),
    ("stop making these big responses keep em small", "Got it. I'll keep it short."),
]


def _mutate_typo(word: str, rng: random.Random) -> str:
    if len(word) < 3 or not word.isalpha():
        return word
    chars = list(word)
    mode = rng.randint(0, 3)
    i = rng.randint(0, len(chars) - 1)
    if mode == 0 and i + 1 < len(chars):  # swap
        chars[i], chars[i + 1] = chars[i + 1], chars[i]
    elif mode == 1:  # drop
        chars.pop(i)
    elif mode == 2:  # duplicate
        chars.insert(i, chars[i])
    else:  # nearby key-ish replace
        chars[i] = rng.choice("abcdefghijklmnopqrstuvwxyz")
    return "".join(chars)


def synthesize_extra(n: int = 400, seed: int = 7) -> list[tuple[str, str]]:
    """Generate typo'd questions → polished answers from clean pairs."""
    rng = random.Random(seed)
    out: list[tuple[str, str]] = []
    for _ in range(n):
        src, ans = rng.choice(CLEAN_PAIRS)
        words = src.split()
        messy = " ".join(_mutate_typo(w, rng) if rng.random() < 0.55 else w for w in words)
        if messy == src:
            messy = src + " " + rng.choice(["pls", "thx", "??", "asap"])
        out.append((messy, ans))
    return out


def build_grammar_corpus() -> str:
    pairs = list(CLEAN_PAIRS) + list(TYPO_PAIRS) + synthesize_extra(600)
    # Repeat clean pairs so polished English dominates learning
    pairs = pairs + CLEAN_PAIRS * 12 + TYPO_PAIRS * 6
    rng = random.Random(11)
    rng.shuffle(pairs)
    blocks = [f"you: {u}\nai: {a}\n" for u, a in pairs]
    return "\n".join(blocks)


def save_grammar_corpus() -> dict:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = build_grammar_corpus()
    OUT.write_text(text, encoding="utf-8")
    return {"path": str(OUT), "chars": len(text), "lines": text.count("\n")}


# Chat slang / common typos the generic spellchecker often misses or mis-corrects.
# Applied BEFORE pyspellchecker — prevents mangling like smth→smith / helo→help.
_CHAT_FIXES: dict[str, str] = {
    # standalone short forms (spellchecker must NOT invent these)
    "u": "you",
    "r": "are",
    "ur": "your",
    "wee": "we",  # typo: "are wee earning" → "are we earning"
    "y": "why",
    "yrs": "yours",
    "im": "I'm",
    "ive": "I've",
    "id": "I'd",
    "ill": "I'll",
    "dont": "don't",
    "doesnt": "doesn't",
    "didnt": "didn't",
    "wont": "won't",
    "cant": "can't",
    "isnt": "isn't",
    "wasnt": "wasn't",
    "werent": "weren't",
    "havent": "haven't",
    "hasnt": "hasn't",
    "hadnt": "hadn't",
    "wouldnt": "wouldn't",
    "couldnt": "couldn't",
    "shouldnt": "shouldn't",
    "arent": "aren't",
    "whats": "what's",
    "thats": "that's",
    "theres": "there's",
    "heres": "here's",
    "hows": "how's",
    "wheres": "where's",
    "whos": "who's",
    "theyre": "they're",
    "youre": "you're",
    "weve": "we've",
    "lets": "let's",
    # greetings — helo must stay hello (not help)
    "helo": "hello",
    "hallo": "hello",
    "helloo": "hello",
    "helllo": "hello",
    "hellp": "help",
    "hii": "hi",
    "hiii": "hi",
    "pls": "please",
    "plz": "please",
    "thx": "thanks",
    "ty": "thanks",
    "thanku": "thank you",
    "thanx": "thanks",
    "bc": "because",
    "cuz": "because",
    "becuase": "because",
    "becasue": "because",
    "beacuse": "because",
    # classic 1-edit / transposition English
    "teh": "the",
    "hte": "the",
    "tehse": "these",
    "thse": "these",
    "thsi": "this",
    "tihs": "this",
    "adn": "and",
    "nad": "and",
    "taht": "that",
    "thta": "that",
    "htat": "that",
    "waht": "what",
    "wht": "what",
    "wat": "what",
    "wot": "what",
    "whag": "what",
    "wha": "what",
    "wath": "what",
    "jsut": "just",
    "juts": "just",
    "liek": "like",
    "lik": "like",
    "wierd": "weird",
    "weired": "weird",
    "recieve": "receive",
    "recieved": "received",
    "seperate": "separate",
    "seperated": "separated",
    "definately": "definitely",
    "occured": "occurred",
    "untill": "until",
    "wich": "which",
    "whcih": "which",
    "whihc": "which",
    "acount": "account",
    "adress": "address",
    "arguement": "argument",
    "calender": "calendar",
    "cemetary": "cemetery",
    "comming": "coming",
    "enviroment": "environment",
    "existance": "existence",
    "familar": "familiar",
    "finaly": "finally",
    "foriegn": "foreign",
    "freind": "friend",
    "goverment": "government",
    "happend": "happened",
    "harrass": "harass",
    "independant": "independent",
    "knowlege": "knowledge",
    "librery": "library",
    "mispell": "misspell",
    "neccessary": "necessary",
    "occassion": "occasion",
    "posession": "possession",
    "priviledge": "privilege",
    "probaly": "probably",
    "realy": "really",
    "remeber": "remember",
    "succesful": "successful",
    "sucess": "success",
    "suprise": "surprise",
    "tomorow": "tomorrow",
    "tommorow": "tomorrow",
    "tommorrow": "tomorrow",
    "truely": "truly",
    "usefull": "useful",
    "writting": "writing",
    "aweful": "awful",
    "begining": "beginning",
    "beleive": "believe",
    "beleive": "believe",
    "belive": "believe",
    "changable": "changeable",
    "collegue": "colleague",
    "concious": "conscious",
    "curiousity": "curiosity",
    "dissapear": "disappear",
    "embarass": "embarrass",
    "experiance": "experience",
    "gaurd": "guard",
    "guage": "gauge",
    "hieght": "height",
    "ignorence": "ignorance",
    "immediatly": "immediately",
    "liason": "liaison",
    "maintainance": "maintenance",
    "millenium": "millennium",
    "noticable": "noticeable",
    "persistant": "persistent",
    "prefered": "preferred",
    "refered": "referred",
    "religous": "religious",
    "rythm": "rhythm",
    "sence": "sense",
    "sieze": "seize",
    "simular": "similar",
    "strenght": "strength",
    "thier": "their",
    "threshhold": "threshold",
    "tounge": "tongue",
    "unfortunatly": "unfortunately",
    "vaccuum": "vacuum",
    "visious": "vicious",
    "wether": "whether",
    "whereever": "wherever",
    "goin": "going",
    "doin": "doing",
    "nothin": "nothing",
    "somethin": "something",
    "anythin": "anything",
    "smth": "something",
    "smthin": "something",
    "smtg": "something",
    "sumthin": "something",
    "sumthing": "something",
    "yk": "you know",
    "yknow": "you know",
    "ya": "you",
    "nay": "any",
    "eny": "any",
    "anuy": "any",
    "sayin": "saying",
    "sayinng": "saying",
    "sayng": "saying",
    "sayign": "saying",
    "talkin": "talking",
    "lookin": "looking",
    "tryin": "trying",
    "havin": "having",
    "makin": "making",
    "comin": "coming",
    "malfuncioning": "malfunctioning",
    "malfunctiong": "malfunctioning",
    "malfuncitoning": "malfunctioning",
    "malfuntioning": "malfunctioning",
    "malfunctionin": "malfunctioning",
    "malfunctoning": "malfunctioning",
    "gonna": "going to",
    "wanna": "want to",
    "gotta": "got to",
    "kinda": "kind of",
    "sorta": "sort of",
    "dunno": "don't know",
    "idk": "I don't know",
    "tbh": "to be honest",
    "rn": "right now",
    "nvm": "never mind",
    "omw": "on my way",
    "grammer": "grammar",
    "engish": "english",
    "proply": "properly",
    "perfec": "perfect",
    "ther": "there",
    "yu": "you",
    "yuo": "you",
    "oyu": "you",
    "abt": "about",
    "ppl": "people",
    "bcuz": "because",
    "bcz": "because",
    "tho": "though",
    "thru": "through",
    "tjrough": "through",
    "throuogh": "through",
    "throuhg": "through",
    "throught": "through",
    "findiing": "finding",
    "findng": "finding",
    "findin": "finding",
    "nite": "night",
    "tmrw": "tomorrow",
    "tmr": "tomorrow",
    "msg": "message",
    "msgs": "messages",
    "rsp": "response",
    "resp": "response",
    "em": "them",
    "alot": "a lot",
    "aswell": "as well",
    "noone": "no one",
}

# FATE / trading / tech terms — never "correct" these into unrelated dictionary words.
# Prefer leaving unknown domain words alone over wrong substitutions (codebase→codename).
_DOMAIN_KEEP: set[str] = {
    "codebase",
    "codebases",
    "fortress",
    "alpaca",
    "parquet",
    "ticker",
    "tickers",
    "lstm",
    "lstms",
    "hft",
    "obi",
    "scalp",
    "scalper",
    "intraday",
    "backtest",
    "backtesting",
    "backtests",
    "papertrade",
    "papertrading",
    "algo",
    "algobot",
    "fate",
    "yahoo",
    "ohlcv",
    "vwap",
    "atr",
    "rsi",
    "macd",
    "ema",
    "sma",
    "sharpe",
    "drawdown",
    "orderbook",
    "websocket",
    "websockets",
    "daemon",
    "daemonize",
    "venv",
    "pytorch",
    "numpy",
    "pandas",
    "fastapi",
    "uvicorn",
    "repo",
    "repos",
    "readme",
    "gitignore",
    "jsonl",
    "parquet",
    "checkpoint",
    "checkpoints",
    "retrain",
    "finetune",
    "embeddings",
    "tokenizer",
    "tokenizers",
    "inference",
    "latency",
    "throughput",
    "microservice",
    "microservices",
    "ops",
    "devops",
    "ci",
    "cd",
    "gpu",
    "mps",
    "cuda",
    "vocab",
    "opendict",
    "wordnet",
    "merriam",
    "grammar",
    "typo",
    "typos",
}


def _looks_like_ticker(tok: str) -> bool:
    """ALL-CAPS 1–5 letter tokens (NVDA, AAPL) — never spell-correct."""
    return bool(tok) and tok.isalpha() and tok.isupper() and 1 <= len(tok) <= 5


def _apply_case(src: str, fixed: str) -> str:
    if not src or not fixed:
        return fixed
    # Multi-word chat expansions (yk → you know): keep lowercase unless src title-ish
    if " " in fixed:
        if src.isupper():
            return fixed.upper()
        if src[0].isupper():
            return fixed[:1].upper() + fixed[1:]
        return fixed
    if src.isupper():
        return fixed.upper()
    if src[0].isupper():
        return fixed[:1].upper() + fixed[1:]
    return fixed


def _split_tok(tok: str) -> tuple[str, str, str]:
    lead = ""
    trail = ""
    core = tok
    while core and not core[0].isalnum():
        lead += core[0]
        core = core[1:]
    while core and not core[-1].isalnum():
        trail = core[-1] + trail
        core = core[:-1]
    return lead, core, trail


def _freq_pick(sp, low: str, protect: set[str], *, max_dist: int) -> str | None:
    """Pick a high-frequency 1-edit (or 2-edit for long words) candidate, or None."""
    try:
        sp.distance = max_dist
    except Exception:
        pass
    raw_cands = sp.candidates(low) or set()
    cands = sorted(
        {
            c.lower()
            for c in raw_cands
            if c and c.lower() != low and c.lower() not in protect and str(c).isalpha()
        },
        key=lambda c: (-int(sp.word_frequency[c] or 0), c),
    )
    if not cands:
        return None
    # helo/helllo → hello, never help
    if any(c.startswith("hel") for c in (low,)) and "hello" in cands and low != "help":
        return "hello"
    best = cands[0]
    best_f = int(sp.word_frequency[best] or 0)
    second_f = int(sp.word_frequency[cands[1]] or 0) if len(cands) > 1 else 0
    # Clear frequency winner — covers tjrough→through, hte→the, whag→what
    if len(cands) == 1:
        return best
    ratio_need = 5.0 if len(low) <= 4 else 3.0
    if best_f >= ratio_need * max(second_f, 1):
        return best
    if best_f >= 1_000_000 and best_f >= 2.5 * max(second_f, 1):
        return best
    return None


def maybe_grammar_lesson(user: str) -> str | None:
    """Grammar FAQ only when the user explicitly asks a usage question."""
    n = re.sub(r"[^a-z0-9\s']+", " ", (user or "").lower())
    n = re.sub(r"\s+", " ", n).strip()
    if not n:
        return None
    lessons = {
        "then or than": "Then = time. Than = comparison.",
        "then vs than": "Then = time. Than = comparison.",
        "difference between then and than": "Then = time. Than = comparison.",
        "when to use then": "Then = time / sequence. Than = comparison.",
        "when to use than": "Than = comparison. Then = time / sequence.",
        "its or it's": "It's = it is. Its = possession.",
        "it's or its": "It's = it is. Its = possession.",
        "your or you're": "Your = possession. You're = you are.",
        "you're or your": "Your = possession. You're = you are.",
        "affect or effect": "Affect is usually a verb. Effect is usually a noun.",
        "when to use their": "Their = possession. There = place. They're = they are.",
        "there their they're": "Their = possession. There = place. They're = they are.",
    }
    if n in lessons:
        return lessons[n]
    if n.startswith(("difference between then", "then versus than", "than versus then")):
        return "Then = time. Than = comparison."
    return None


def fix_typos(text: str) -> str:
    """Best-effort local typo repair before the brain sees the user message.

    1) Explicit chat/slang map (u→you, tjrough→through, helo→hello, …)
    2) Spellchecker: edit distance 1 (distance 2 only if len≥6 and d1 empty)
       — frequency-ranked, never touch protected domain/slang tokens,
       — skip tokens already in the dictionary,
       — very short tokens (len≤2) are map-only.
    """
    raw = (text or "").strip()
    if not raw:
        return raw

    try:
        from intel.talk_culture import SLANG_KEEP
    except Exception:
        SLANG_KEEP = set()

    protect = set(_DOMAIN_KEEP) | set(SLANG_KEEP)
    # Multi-word chat expansions produce spaces — protect value tokens too
    for v in _CHAT_FIXES.values():
        for part in v.lower().split():
            if part.isalpha():
                protect.add(part)

    def _chat_only(tok: str) -> str:
        lead, core, trail = _split_tok(tok)
        if not core:
            return tok
        if _looks_like_ticker(core) or core.lower() in protect:
            return tok
        low = core.lower()
        if low in _CHAT_FIXES:
            core = _apply_case(core, _CHAT_FIXES[low])
        return lead + core + trail

    try:
        from spellchecker import SpellChecker

        sp = SpellChecker(distance=1)
        try:
            # Keep domain words recognized so we don't "fix" them away
            sp.word_frequency.load_words(list(_DOMAIN_KEEP) | set(SLANG_KEEP))
        except Exception:
            pass
        out: list[str] = []
        for tok in raw.split():
            lead, core, trail = _split_tok(tok)
            if not core:
                out.append(tok)
                continue
            if _looks_like_ticker(core) or core.lower() in _DOMAIN_KEEP or core.lower() in SLANG_KEEP:
                out.append(lead + core + trail)
                continue
            low = core.lower()
            if low in _CHAT_FIXES:
                core = _apply_case(core, _CHAT_FIXES[low])
                out.append(lead + core + trail)
                continue
            # len ≤2: map only (a/i/u/r/y handled above)
            if not core.isalpha() or len(core) <= 2:
                out.append(lead + core + trail)
                continue
            if low in sp:
                out.append(lead + core + trail)
                continue
            cand = _freq_pick(sp, low, set(_DOMAIN_KEEP) | set(SLANG_KEEP), max_dist=1)
            if cand is None and len(low) >= 6:
                cand = _freq_pick(sp, low, set(_DOMAIN_KEEP) | set(SLANG_KEEP), max_dist=2)
            if cand:
                core = _apply_case(core, cand)
            out.append(lead + core + trail)
        return " ".join(out)
    except Exception:
        return " ".join(_chat_only(tok) for tok in raw.split())
