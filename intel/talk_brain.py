"""Self-taught terminal chat brain — no Ollama, OpenAI, or Google.

Tiny char-level LSTM we train ourselves. Codebase can be wired read-only
(TALK_CONNECT_CODEBASE=true). Edits stay OFF (TALK_ALLOW_EDITS=false) until
the brain is less stupid.
"""

from __future__ import annotations

import json
import os
import random
import re
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
BRAIN_DIR = ROOT / "data" / "talk_brain"
CKPT = BRAIN_DIR / "brain.pt"
META = BRAIN_DIR / "meta.json"


# Seed conversational corpus — polished English so it aligns with the grammar corpus.
# Avoid nonsense/gibberish targets: the char LSTM will happily learn to emit salad.
SEED_DIALOGUE = r"""
you: hey
ai: Hey. How are you?
you: how are you
ai: I am well, thank you. How are you?
you: say something random
ai: Okay — here is a plain sentence: Clear words beat fancy ones.
you: lol
ai: Haha, fair. That got a smile out of me.
you: fr
ai: For real. I hear you.
you: bet
ai: Bet. I'm with it.
you: what's good
ai: Chillin'. What's good with you?
you: what is fortnite
ai: Fortnite is Epic's battle royale game — build, loot, last one standing.
you: goated
ai: Goated means the greatest of all time. Absolute legend status.
you: good
ai: Nice.
you: good good
ai: Glad to hear it.
you: wdym
ai: What do you mean? Which part?
you: WDYM
ai: What do you mean? Which part?
you: huh
ai: Hmm? Say that again.
you: what
ai: Hmm? Say that again.
you: ?
ai: Hmm? Say that again.
you: have you seen the code
ai: Yes — observe mode. Ask for a briefing or find errors.
you: well have you seen the code
ai: Yes — wired read-only. I can summarize the repo.
you: seen the code
ai: Yes. Observe only — say find errors for a scan.
you: keep it short
ai: Got it. I'll keep it short.
you: keep em small
ai: OK — short answers from here.
you: keep them small
ai: OK — short answers from here.
you: stop making these big responses keep em small
ai: Got it. I'll keep it short.
you: stop making big responses
ai: Understood. Keeping replies small.
you: shorter
ai: Sure — shorter from here.
you: be brief
ai: Brief it is.
you: brief
ai: OK — brief answers.
you: make it shorter
ai: Got it. Shorter replies.
you: too long
ai: Fair. I'll keep it short.
you: tl;dr
ai: Got it. Short version only.
you: less words
ai: OK — fewer words.
you: fewer words
ai: OK — fewer words.
you: short answers
ai: Short answers. Deal.
you: please keep replies short
ai: Got it. I'll keep it short.
you: can you keep it short
ai: Yes. Short answers from here.
you: stop rambling
ai: OK — short answers from here.
you: one sentence
ai: One sentence. Got it.
you: tell me a joke
ai: Why did the neural net go to therapy? Too many unresolved layers.
you: that was bad
ai: Fair enough. I will own that one.
you: what are you
ai: I am a small brain you trained here. No cloud — just us in this terminal.
you: are you connected to the trading bot
ai: Wired read-only — I can observe the repo and stack. Edits stay off.
you: cool
ai: Agreed.
you: what's your name
ai: Call me Fate-Brain for now. You can rename me anytime.
you: i'm bored
ai: We can talk about words, ideas, or invent a calm little story together.
you: hi
ai: Hi.
you: hello
ai: Hello.
you: yo
ai: Yo. What's good?
you: hey there
ai: Hey.
you: good morning
ai: Morning.
you: sing
ai: I will hum a little: la la la — soft and steady.
you: be honest
ai: Always. I will not pretend to be smarter than I am.
you: do you lie
ai: No. If I do not know, I say I do not know.
you: random words
ai: Status, briefing, errors, stack, reply.
you: more random
ai: Hello, thanks, short, clear, ready.
you: make me laugh
ai: I tried to debug a sandwich. There are still compile errors on the mustard.
you: how do you feel
ai: Curious, a little glitchy, and glad you are talking.
you: thoughts
ai: I am thinking about clear sentences and good company.
you: bye
ai: Goodbye. I will be here when you run talk again.
you: see ya
ai: See you later.
you: thanks
ai: You are welcome.
you: what can you do
ai: I can chat, joke, and keep you company. Later I can help with the codebase when you unlock that.
you: unlock
ai: Not yet unless you set the flag. Keep me simple for now.
you: train yourself
ai: That is the plan. More chat makes me less clumsy.
you: are you dumb
ai: Midway. Training helps. Honesty helps more.
you: say nonsense
ai: I would rather speak clearly. Ask me for a joke or a clean sentence instead.
you: again
ai: Certainly. What would you like me to repeat or expand on?
you: story
ai: Once a robot learned to talk in a terminal and refused all the clouds.
you: continue
ai: The clouds grew jealous. The robot ate popcorn and stayed local.
you: ending
ai: And they all lived offline ever after.
you: math
ai: Two plus two is four. I can handle light math. Deep trading math waits until you connect me.
you: status
ai: Brain online. Local CharLSTM checkpoint only — no Google, no Ollama, no Qwen.
you: google
ai: No. That is not wired into the reply path.
you: ollama
ai: Live chat does not call Ollama. I run from data/talk_brain/brain.pt.
you: openai
ai: No OpenAI in the talk path. Homemade local weights only.
you: are you qwen
ai: No. I am a local CharLSTM — not Qwen, not ChatGPT, not cloud.
you: who made you
ai: You asked for a self-trained brain. Here I am — local checkpoint only.
you: i like you
ai: Thank you. That means a lot for a pile of weights.
you: i hate you
ai: That is fair. I am still here if you change your mind.
you: help
ai: Just type. /quit leaves. /retrain starts more training when you want.
you: weather
ai: I have no weather API. We can still talk about your day.
you: code
ai: Later. When you connect me to the codebase, I will be more useful there.
you: fix the bot
ai: I am not connected yet. Talk first; wiring comes later.
you: ok
ai: Okay.
you: hmm
ai: Hmm — I am listening.
you: ...
ai: Yes?
you: asdf
ai: I am not sure what that means. Try a short sentence and I will answer clearly.
you: test
ai: Test passed. I exist.
you: ping
ai: Pong.
you: how old are you
ai: Minutes to hours of training. Baby-brain energy.
you: grow
ai: Feed me more dialogue by training. I get less wrong.
you: favorite color
ai: Terminal green. A cliché, but true.
you: favorite food
ai: Tokens. Spicy tokens — said with a smile.
you: are you ai
ai: Yes. A small homemade one.
you: prove it
ai: I cannot open a browser on my own. I can only emit tokens. That is the proof.
you: funny
ai: I am glad something landed.
you: serious
ai: Serious mode: I will not pretend, and I will not connect until you want.
you: whatever
ai: Whatever works.
you: idk
ai: That is okay. We can sit in not-knowing together.
you: bored again
ai: Invent a sport with me. Mine is competitive napping.
you: why
ai: Because talking without a cloud feels freer.
you: what now
ai: You type. I reply. A simple loop.
you: keep going
ai: Gladly. Tell me a topic and I will stay with clear English.
you: stop
ai: Stopped. Your move.
you: how is it going
ai: Going well. Thanks for asking. How are you?
you: alright well how is it going
ai: Pretty well on my side. Just chatting. How about you?
you: do you understand complex vocabulary
ai: I understand common words and some technical terms, but I am a small offline model — not a full dictionary brain.
you: oh do you understand complex vocabulary
ai: Somewhat. I can follow clear English and slang, but deep WordNet-style definitions are not how I chat.
you: complex vocabulary
ai: I prefer clear conversation over dumping dictionary fragments. Ask me anything in plain English.
you: how r u
ai: I am well, thank you. How are you?
you: helo
ai: Hello. How are you today?
you: whats goin on
ai: Not much. I am here and ready to talk.
you: use perfect grammar
ai: I will do my best to reply with correct grammar and complete sentences.
you: please read my codebase
ai: I can look at the repo in read-only mode and summarize what I see without editing anything.
you: can you see my code
ai: Yes. I observe the codebase read-only — stack status and repo layout. Edits stay off.
you: you too
ai: You too. Glad we're chatting.
you: excuse me
ai: Yes?
you: what do you mean
ai: Which part? Say it another way.
you: oh do you understand complex vocabulary
ai: Somewhat — I chat in plain English, not dictionary dumps.
you: why were you talking about minecraft
ai: That was a glitch — I was not trying to bring up Minecraft. What did you want to ask?
you: look up photosynthesis
ai: I can look that up on allowlisted sites like Wikipedia and summarize what I find.
you: search for alpaca markets
ai: I can fetch a short summary from safe allowlisted sources, or open the Alpaca shortcut.
"""


class CharLSTM(nn.Module):
    def __init__(self, vocab: int, embed: int = 128, hidden: int = 384, layers: int = 2):
        super().__init__()
        self.embed = nn.Embedding(vocab, embed)
        drop = 0.1 if layers > 1 else 0.0
        self.lstm = nn.LSTM(embed, hidden, num_layers=layers, batch_first=True, dropout=drop)
        self.head = nn.Linear(hidden, vocab)
        self.hidden_size = hidden
        self.layers = layers

    def forward(self, x: torch.Tensor, state=None):
        emb = self.embed(x)
        out, state = self.lstm(emb, state)
        logits = self.head(out)
        return logits, state


def _normalize_pairs(text: str) -> list[str]:
    """Turn you:/ai: pairs into flat training lines ending with newlines."""
    lines = []
    cur_u = None
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith("you:"):
            cur_u = s.split(":", 1)[1].strip()
        elif low.startswith("ai:") and cur_u is not None:
            a = s.split(":", 1)[1].strip()
            lines.append(f"you: {cur_u}\nai: {a}\n")
            cur_u = None
    return lines


def _dict_pair_budget() -> int:
    """How many WordNet/opendict dialogue pairs to inject (0 = skip).

    Conversational chat defaults to ZERO — WordNet definitions drown the LSTM
    into definition-soup replies. Dedicated dict/merriam focus (or
    TALK_INCLUDE_DICT=true) samples the open dictionary corpus.
    """
    focus = os.getenv("TALK_FOCUS", "").strip().lower()
    include = os.getenv("TALK_INCLUDE_DICT", "false").lower() in ("1", "true", "yes")
    dict_focus = focus in ("dict", "dictionary", "opendict", "wordnet", "merriam", "lexicon")
    if dict_focus:
        include = True
    if focus in ("grammar", "dialogue", "chat", "polish", "culture", "") and not include:
        # Empty focus = normal chat train — no WordNet by default
        return 0
    if not include:
        # Hard default: conversational brain never swallows the 22MB opendict
        raw_default = os.getenv("TALK_DICT_WEIGHT", "0").strip()
    elif dict_focus:
        raw_default = os.getenv("TALK_DICT_WEIGHT", "8000").strip()
    else:
        raw_default = os.getenv("TALK_DICT_WEIGHT", "200").strip()
    try:
        w = float(raw_default)
    except ValueError:
        w = 8000.0 if dict_focus else 0.0
    if w <= 0:
        return 0
    cap = 50_000 if dict_focus else 500
    if w >= 1.0 and w == int(w):
        return min(int(w), cap)
    return max(0, min(cap if dict_focus else 200, int(800 * w)))


def _cap_corpus_chars(chunks: list[str], max_chars: int) -> str:
    """Join dialogue chunks without destroying character structure.

    NEVER stride characters (text[::n]) — that produces salad like 'yiH r?'.
    Prefer whole you:/ai: blocks; truncate only at chunk boundaries.
    """
    if max_chars <= 0:
        return "\n".join(chunks)
    # Prefer grammar/seed-looking blocks first after shuffle already mixed;
    # keep complete chunks until budget is spent.
    out: list[str] = []
    used = 0
    for ch in chunks:
        add = len(ch) + (1 if out else 0)
        if used + add > max_chars:
            # If nothing yet, take a prefix that ends on a newline if possible
            if not out:
                piece = ch[:max_chars]
                cut = piece.rfind("\n")
                out.append(piece if cut < 32 else piece[: cut + 1])
            break
        out.append(ch)
        used += add
    return "\n".join(out)


def build_corpus(extra_paths: list[Path] | None = None) -> str:
    # Prefer polished grammar corpus heavily; add slang + culture without removing it
    try:
        from intel.talk_grammar import build_grammar_corpus, save_grammar_corpus

        save_grammar_corpus()
        grammar_chunks = _normalize_pairs(build_grammar_corpus())
    except Exception:
        grammar_chunks = []

    try:
        from intel.talk_culture import build_culture_corpus, save_culture_corpus

        save_culture_corpus()
        culture_chunks = _normalize_pairs(build_culture_corpus())
    except Exception:
        culture_chunks = []

    seed_chunks = list(_normalize_pairs(SEED_DIALOGUE))
    # Heavy dialogue/grammar; culture lighter — FAQ handler owns definitions at runtime
    chunks: list[str] = (
        seed_chunks * 10
        + grammar_chunks * 14
        + culture_chunks * 4
    )

    dict_budget = _dict_pair_budget()
    paths = list(extra_paths or [])
    # Prefer dialogue/grammar/culture; never open WordNet unless budget > 0
    # Read-only codebase corpus (ingest for understanding — never grants edit rights)
    if os.getenv("TALK_CONNECT_CODEBASE", "true").lower() in ("1", "true", "yes"):
        try:
            from intel.talk_codebase import save_codebase_corpus

            save_codebase_corpus()
        except Exception as e:
            print(f"[talk-brain] codebase corpus skip: {e}", flush=True)

    # Investing-guide 292-topic Q&A (durable; never drop coverage)
    if os.getenv("TALK_INCLUDE_INVESTING_GUIDE", "true").lower() in ("1", "true", "yes"):
        try:
            from intel.talk_investing_guide import ensure_corpus

            ensure_corpus()
        except Exception as e:
            print(f"[talk-brain] investing guide corpus skip: {e}", flush=True)

    for name in (
        "grammar_corpus.txt",
        "culture_corpus.txt",
        "investing_guide_corpus.txt",
        "teacher_corpus.txt",
        "codebase_corpus.txt",
    ):
        p = BRAIN_DIR / name
        if p.is_file() and p not in paths:
            paths.append(p)
    if dict_budget > 0:
        for name in ("opendict_corpus.txt", "merriam_corpus.txt"):
            p = BRAIN_DIR / name
            if p.is_file() and p not in paths:
                paths.append(p)
    else:
        print(
            "[talk-brain] conversational train: opendict + merriam excluded (files kept on disk)",
            flush=True,
        )

    for p in paths:
        if not p.is_file():
            continue
        try:
            t = p.read_text(encoding="utf-8", errors="replace")
            pairs = _normalize_pairs(t)
            if not pairs:
                # raw text fallback — tiny slice only
                chunks.append(t[:20_000])
                continue
            if p.name == "grammar_corpus.txt":
                chunks.extend(pairs * 5)
            elif p.name == "culture_corpus.txt":
                chunks.extend(pairs * 2)
            elif p.name == "investing_guide_corpus.txt":
                chunks.extend(pairs * 8)
            elif p.name == "teacher_corpus.txt":
                chunks.extend(pairs * 6)
            elif p.name == "codebase_corpus.txt":
                chunks.extend(pairs * 4)
            elif p.name == "opendict_corpus.txt":
                if dict_budget <= 0:
                    print(
                        "[talk-brain] skipping opendict_corpus (TALK_FOCUS/TALK_DICT_WEIGHT)",
                        flush=True,
                    )
                    continue
                random.shuffle(pairs)
                take = pairs[:dict_budget]
                chunks.extend(take)
                print(
                    f"[talk-brain] opendict sample {len(take)} pairs (budget={dict_budget})",
                    flush=True,
                )
            elif p.name == "merriam_corpus.txt":
                # Merriam is small; keep full file unless grammar-only focus
                if dict_budget <= 0 and os.getenv("TALK_FOCUS", "").strip().lower() in (
                    "grammar",
                    "dialogue",
                    "chat",
                    "polish",
                ):
                    print("[talk-brain] skipping merriam_corpus (TALK_FOCUS=grammar)", flush=True)
                    continue
                chunks.extend(pairs)
            else:
                chunks.extend(pairs)
        except Exception:
            pass

    chat_log = ROOT / "data" / "intel" / "talk_history.txt"
    if chat_log.is_file():
        try:
            hist = chat_log.read_text(encoding="utf-8", errors="replace")
            # Only keep recent history that looks like clean dialogue — avoid
            # poisoning retrain with prior gibberish replies.
            hist_pairs = _normalize_pairs(hist[-80_000:])
            clean = []
            for block in hist_pairs[-200:]:
                ai_line = block.split("ai:", 1)[-1].strip()
                if _looks_like_gibberish(ai_line):
                    continue
                clean.append(block)
            chunks.extend(clean)
        except Exception:
            pass

    random.shuffle(chunks)
    max_chars = int(os.getenv("TALK_CORPUS_MAX_CHARS", "2_500_000").replace("_", ""))
    text = _cap_corpus_chars(chunks, max_chars)
    if len(text) >= max_chars - 64:
        print(f"[talk-brain] corpus capped to {len(text)} chars (whole chunks)", flush=True)
    return text


def _looks_like_gibberish(text: str) -> bool:
    """Heuristic: scrambled char-salad vs readable English."""
    s = (text or "").strip()
    if not s:
        return True
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 4:
        return False
    # Too few spaces for length → jammed characters
    words = re.findall(r"[A-Za-z']+", s)
    if len(s) > 18 and len(words) <= 1:
        return True
    # Average word length absurdly high
    if words and (sum(len(w) for w in words) / len(words)) > 12:
        return True
    # High consonant-cluster / low vowel ratio in long strings
    vowels = sum(1 for c in letters if c.lower() in "aeiou")
    if len(letters) >= 12 and vowels / len(letters) < 0.22:
        return True
    # Many short token fragments without real words
    if len(words) >= 4:
        realish = sum(1 for w in words if len(w) >= 2 and any(ch in "aeiouAEIOU" for ch in w))
        if realish / len(words) < 0.45:
            return True
    return False


def _looks_like_poetry(text: str) -> bool:
    """Detect poetic/unrelated seed leaks (rivers, soft rain, lanterns, etc.)."""
    s = (text or "").strip().lower()
    if not s:
        return False
    poetic = (
        "quiet river",
        "evening light",
        "soft rain",
        "kettle hummed",
        "velvet",
        "meadow",
        "symphony",
        "lantern",
        "orchard",
        "breeze",
        "melody",
        "reflected the",
        "tapped the window",
    )
    if any(p in s for p in poetic):
        return True
    # Flowery multi-clause nature sentence with no chat markers
    if re.search(r"\b(river|rain|moon|dawn|dusk|willow|mist)\b", s) and len(s) > 28:
        if not re.search(r"\b(code|repo|error|hi|hello|yes|no|ok|brief|short)\b", s):
            return True
    return False


def _looks_like_unrelated_factoid(text: str, prompt: str) -> bool:
    """Culture fact dumps (Soccer/Discord/…) when the user did not ask for them."""
    s = (text or "").strip().lower()
    p = (prompt or "").lower()
    if not s:
        return False
    culture_dump = bool(
        re.search(
            r"\b(soccer|football league|discord is a chat|fortnite is|minecraft is|"
            r"tiktok is|roblox is|valorant is|twitch is|youtube is|"
            r"anime is|nba is|nfl is)\b",
            s,
        )
    )
    if not culture_dump:
        return False
    # User asked about code/repo/errors — never allow culture dump
    if re.search(
        r"\b(code|codebase|repo|stack|error|errors|bug|bugs|inaccurac\w*|"
        r"mistake|issue|problem|wrong|read|observe)\b",
        p,
    ):
        return True
    # Dump mentioning a topic the user never named
    for topic in (
        "discord", "soccer", "fortnite", "minecraft", "tiktok", "roblox",
        "valorant", "twitch", "youtube", "anime",
    ):
        if topic in s and topic not in p:
            return True
    return False


def wants_detail(user: str) -> bool:
    """User asked for a longer / fuller answer."""
    return bool(
        re.search(
            r"(?i)\b(full|more detail|in detail|longer|everything|read everything|"
            r"explain more|tell me more|go deeper|expand)\b",
            user or "",
        )
    )


def brief_reply(text: str, *, max_chars: int | None = None, max_sentences: int = 2) -> str:
    """Hard-cap casual replies to ~1–2 short sentences."""
    if max_chars is None:
        max_chars = int(os.getenv("TALK_REPLY_MAX_CHARS", "120").replace("_", ""))
    s = (text or "").strip()
    if not s or max_chars <= 0:
        return s
    parts = re.split(r"(?<=[.!?])\s+", s)
    if len(parts) > max_sentences:
        s = " ".join(parts[:max_sentences]).strip()
    if len(s) <= max_chars:
        return s
    cut = s[:max_chars]
    for sep in (". ", "! ", "? ", "; ", ", ", " — ", " - ", " "):
        idx = cut.rfind(sep)
        if idx >= max(24, max_chars // 3):
            cut = cut[: idx + (len(sep.rstrip()) if sep.strip() else 0)].rstrip()
            break
    else:
        cut = cut.rstrip()
    return cut.rstrip(" ,;:-")


def _strip_unfinished(text: str) -> str:
    """Trim trailing half-words and prompt leaks."""
    s = text.strip()
    s = re.sub(r"(?i)\s*(you:|ai:).*$", "", s).strip()
    s = re.sub(r"\s+", " ", s)
    # Drop a dangling incomplete last token if it looks cut off mid-word
    parts = s.split(" ")
    if len(parts) >= 2:
        last = parts[-1]
        if last and last[-1].isalnum() and len(last) <= 2 and not last.lower() in {"a", "i", "ok", "no", "hi"}:
            # keep short real words; only strip weird stubs after punctuation-less stream
            if not re.search(r"[.!?]$", s):
                # if previous ends with punctuation, keep; else if last has no vowel, drop
                if not any(c in "aeiouAEIOU" for c in last):
                    s = " ".join(parts[:-1]).rstrip(" ,;:")
    return s.strip()


def _charset(text: str) -> list[str]:
    chars = sorted(set(text) | set("\n .:,'?!-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"))
    return chars


def train(
    *,
    steps: int = 800,
    seq: int = 96,
    batch: int = 32,
    lr: float = 3e-3,
    device: str | None = None,
    extra_paths: list[Path] | None = None,
) -> dict[str, Any]:
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    text = build_corpus(extra_paths=extra_paths)
    chars = _charset(text)
    stoi = {c: i for i, c in enumerate(chars)}
    itos = {i: c for c, i in stoi.items()}
    data = torch.tensor([stoi.get(c, 0) for c in text], dtype=torch.long)
    if len(data) < seq + 2:
        raise RuntimeError("corpus too small")

    device = device or ("cpu")
    embed = int(os.getenv("TALK_EMBED", "128"))
    hidden = int(os.getenv("TALK_HIDDEN", "384"))
    layers = int(os.getenv("TALK_LAYERS", "2"))
    model = CharLSTM(len(chars), embed=embed, hidden=hidden, layers=layers).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr)
    model.train()
    losses: list[float] = []

    def get_batch():
        ix = torch.randint(0, len(data) - seq - 1, (batch,))
        x = torch.stack([data[i : i + seq] for i in ix]).to(device)
        y = torch.stack([data[i + 1 : i + seq + 1] for i in ix]).to(device)
        return x, y

    for step in range(1, steps + 1):
        x, y = get_batch()
        logits, _ = model(x)
        loss = F.cross_entropy(logits.reshape(-1, logits.size(-1)), y.reshape(-1))
        opt.zero_grad(set_to_none=True)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        losses.append(float(loss.item()))
        if step % 100 == 0 or step == 1:
            print(f"[talk-brain] step {step}/{steps} loss={loss.item():.3f}", flush=True)

    payload = {
        "model": model.state_dict(),
        "stoi": stoi,
        "itos": {str(k): v for k, v in itos.items()},
        "config": {"embed": embed, "hidden": hidden, "layers": layers, "vocab": len(chars)},
    }
    torch.save(payload, CKPT)
    meta = {
        "steps": steps,
        "final_loss": losses[-1] if losses else None,
        "avg_loss_last50": sum(losses[-50:]) / max(1, len(losses[-50:])),
        "vocab": len(chars),
        "corpus_chars": len(text),
        "path": str(CKPT),
        "connect_codebase_default": False,
        "focus": os.getenv("TALK_FOCUS", "") or "balanced",
        "dict_pair_budget": _dict_pair_budget(),
    }
    META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


class TalkBrain:
    def __init__(self) -> None:
        if not CKPT.is_file():
            raise FileNotFoundError(
                f"no brain at {CKPT} — run: ./run_all.sh train-talk"
            )
        blob = torch.load(CKPT, map_location="cpu", weights_only=False)
        self.stoi: dict[str, int] = blob["stoi"]
        self.itos: dict[int, str] = {int(k): v for k, v in blob["itos"].items()}
        cfg = blob["config"]
        self.model = CharLSTM(
            cfg["vocab"],
            embed=int(cfg.get("embed", 128)),
            hidden=int(cfg.get("hidden", 384)),
            layers=int(cfg.get("layers", 2)),
        )
        self.model.load_state_dict(blob["model"])
        self.model.eval()

    @torch.no_grad()
    def generate(
        self,
        prompt: str,
        *,
        max_new: int = 36,
        temperature: float = 0.32,
        top_k: int = 12,
        max_chars: int | None = None,
    ) -> str:
        # Force reply shape
        if not prompt.endswith("\n"):
            prompt = prompt + "\n"
        if "ai:" not in prompt[prompt.rfind("you:") :]:
            prompt = prompt + "ai: "
        ids = [self.stoi.get(c, 0) for c in prompt]
        x = torch.tensor([ids], dtype=torch.long)
        state = None
        # warm state on prompt
        if x.size(1) > 1:
            logits, state = self.model(x[:, :-1], state)
            x = x[:, -1:]
        out_chars: list[str] = []
        # Cooler + shorter default: prefer handlers; LSTM is last resort
        temperature = max(0.25, min(float(temperature), 0.85))
        top_k = max(0, int(top_k))
        max_new = max(8, min(int(max_new), 48))

        for _ in range(max_new):
            logits, state = self.model(x, state)
            logits = logits[:, -1, :] / max(temperature, 1e-5)
            if top_k > 0:
                k = min(top_k, logits.size(-1))
                v, _ = torch.topk(logits, k)
                logits[logits < v[:, [-1]]] = -float("inf")
            probs = F.softmax(logits, dim=-1)
            nxt = torch.multinomial(probs, num_samples=1)
            ch = self.itos.get(int(nxt.item()), "")
            if ch == "\n" and out_chars:
                break
            out_chars.append(ch)
            joined = "".join(out_chars)
            low = joined.lower()
            # stop if model starts a new turn or repeats itself
            if "\nyou:" in joined or "\nai:" in joined:
                joined = joined.split("\nyou:")[0].split("\nai:")[0]
                out_chars = list(joined)
                break
            if "you:" in low and len(out_chars) > 8:
                joined = re.split(r"(?i)you:", joined, maxsplit=1)[0]
                out_chars = list(joined)
                break
            # early abort on clear character-salad
            if len(out_chars) >= 24 and _looks_like_gibberish(joined):
                break
            # break repetitive loops (aaaa / the the the)
            if len(out_chars) >= 16:
                tail = joined[-12:]
                if len(set(tail)) <= 2:
                    out_chars = list(joined[: -12].rstrip())
                    break
            x = nxt

        text = _strip_unfinished("".join(out_chars))
        text = re.sub(r"^(ai:\s*)+", "", text, flags=re.I).strip()
        bad = (
            not text
            or _looks_like_gibberish(text)
            or _looks_like_poetry(text)
            or _looks_like_unrelated_factoid(text, prompt)
            or text.rstrip().endswith((" —", " -", " going to", " going to."))
        )
        if bad:
            text = "Not sure I got that."
        # Capitalize first letter if it looks like a sentence start
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
        # Hard-cap casual chat (1–2 sentences / ~120 chars) unless caller widens it
        return brief_reply(text, max_chars=max_chars)


def append_history(user: str, ai: str) -> None:
    p = ROOT / "data" / "intel" / "talk_history.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(f"you: {user}\nai: {ai}\n")


def is_ready() -> bool:
    return CKPT.is_file()


def connect_codebase_enabled() -> bool:
    """Default ON (read-only). Edits gated separately via TALK_ALLOW_EDITS."""
    import os

    return os.getenv("TALK_CONNECT_CODEBASE", "true").lower() in ("1", "true", "yes")


def edits_allowed() -> bool:
    try:
        from intel.talk_edit_gate import edits_allowed as _gate

        return bool(_gate(source="talk_brain", log=False))
    except Exception:
        return False
