"""Slang + pop-culture knowledge for the homemade talk brain.

Teaches casual understanding (yo, fr, bet, goated) and common games / internet
culture (Fortnite, Minecraft, TikTok, etc.) while replies stay readable English.

Runtime FAQ answers ONLY fire on high-confidence topic questions (exact phrase
or clear "what is X" / "what does X mean"). Never inject Minecraft on "excuse me".
"""

from __future__ import annotations

import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "talk_brain" / "culture_corpus.txt"

# Casual chat — understand slang; reply chill but in real words (not salad).
SLANG_PAIRS = [
    ("yo", "Yo. What's good?"),
    ("yo what's up", "Yo. Not much — just chilling in the terminal. You?"),
    ("what's good", "Chillin'. What's good with you?"),
    ("whats good", "Chillin'. What's good with you?"),
    ("sup", "Sup. How you doing?"),
    ("wassup", "Wassup. I'm here."),
    ("lol", "Haha, fair. That got a smile out of me."),
    ("lmao", "Okay that one's funny."),
    ("fr", "For real. I hear you."),
    ("fr fr", "For real for real. Say less."),
    ("no cap", "No cap — straight talk."),
    ("cap", "Cap means someone is lying or exaggerating. No cap means for real."),
    ("bet", "Bet. I'm with it."),
    ("bet bet", "Bet. Let's go."),
    ("say less", "Say less. I got you."),
    ("lowkey", "Lowkey same. Keep it chill."),
    ("highkey", "Highkey, yeah — that energy is loud."),
    ("mid", "Yeah, that sounds mid. We can do better."),
    ("goated", "Goated means the greatest of all time. Absolute legend status."),
    ("that's goated", "True. That's goated."),
    ("thats goated", "True. That's goated."),
    ("w", "W. That's a win."),
    ("l", "L. Rough one, but we bounce back."),
    ("ratio", "Ratio means someone got clapped in the replies. Internet drama fuel."),
    ("npc", "NPC means someone acting on autopilot, like a background character."),
    ("based", "Based — standing on business, unbothered by the hate."),
    ("cringe", "Yeah, that can be cringe. We move."),
    ("slay", "Slay. Doing the absolute most in a good way."),
    ("ate", "Ate and left no crumbs. Clean performance."),
    ("fire", "Fire. That goes hard."),
    ("vibes", "Vibes are good. Keep that energy."),
    ("it's giving", "It's giving main-character energy."),
    ("its giving", "It's giving main-character energy."),
    ("ong", "On God — like for real, no joke."),
    ("tbh", "To be honest, I'm just a small offline brain — but I try."),
    ("ngl", "Not gonna lie, that tracks."),
    ("idk", "I don't know either. We can figure it out."),
    ("imo", "In my opinion, clear chat beats cloud hype."),
    ("bruh", "Bruh. I felt that."),
    ("deadass", "Deadass? Alright, I'm listening."),
    ("finna", "Finna means about to. What you finna do?"),
    ("sus", "Sus means suspicious. Something feels off."),
    ("rizz", "Rizz is charm or flirt game. Smooth talker energy."),
    ("sigma", "Sigma is internet slang for a lone-wolf cool guy archetype. Take it lightly."),
    ("skibidi", "Skibidi is chaotic meme slang. Mostly nonsense humor from the internet."),
    ("gyatt", "Gyatt is loud slang for noticing someone's shape. Pretty unserious."),
    ("fanum tax", "Fanum tax is a meme about snatching a friend's food. Pure TikTok lore."),
    ("delulu", "Delulu means delusional — usually playful, not clinical."),
    ("ate that up", "Ate that up. Clean win."),
    ("let him cook", "Let him cook — give the idea room to cook."),
    ("touch grass", "Touch grass means go outside and reset. Fair advice sometimes."),
    ("iykyk", "If you know, you know."),
    ("gg", "GG — good game."),
    ("gg ez", "GG. Easy or not, respect the win."),
    ("glhf", "Good luck, have fun."),
    ("afk", "AFK — away from keyboard. I'm still here though."),
    ("what does afk mean", "AFK means away from keyboard."),
    ("irl", "IRL means in real life."),
    # Polite / clarification — MUST NOT collide with slang/culture dumps
    ("excuse me", "Yes? No worries — what's up?"),
    ("excuse me?", "Yes? I'm listening."),
    ("what do you mean", "Which part should I clarify? Say it another way and I'll answer straight."),
    ("what do u mean", "Which part should I clarify? Say it another way and I'll answer straight."),
    ("wdym", "What do you mean? Which part?"),
    ("WDYM", "What do you mean? Which part?"),
    ("wdy m", "What do you mean? Which part?"),
    ("good", "Nice."),
    ("good good", "Glad to hear it."),
    ("good.", "Nice."),
    ("huh", "Hmm? Say that again."),
    ("huh?", "Hmm? Say that again."),
    ("what", "Hmm? Say that again."),
    ("what?", "Hmm? Say that again."),
    ("?", "Hmm? Say that again."),
    ("what were you saying", "I may have glitched. Ask again and I'll stay on topic."),
    ("why were you talking about minecraft", "That was a glitch — I wasn't trying to bring up Minecraft. What did you actually want to ask?"),
    ("why minecraft", "Sorry — Minecraft wasn't meant to be the topic. What should we talk about?"),
    ("you too", "You too. Glad we're chatting."),
    ("you too!", "You too!"),
    ("same to you", "Same to you."),
    ("can you see my code", "Yes — read-only. I can observe the repo and stack status without editing."),
    ("can you see my codebase", "Yes — wired read-only. Ask for a briefing and I'll summarize what I see."),
    ("can you read my code", "Yes, in observe mode only. Edits stay off unless you unlock them."),
    ("do you see my code", "I can look at the codebase read-only and report what I see."),
    ("have you seen the code", "Yes — observe mode. I can summarize the repo read-only."),
    ("have you seen teh code", "Yes — observe mode. I can summarize the repo read-only."),
    ("seen the code", "Yes. Observe only — ask for a briefing or find errors."),
    ("see the code", "Wired read-only. Ask briefing or find errors."),
    ("see my code", "Yes — observe mode. Edits stay off."),
    ("look at the code", "Sure — read-only observe. No edits."),
    ("read the code", "Read-only. I summarize without changing anything."),
    ("observe the stack", "I can observe the stack read-only — status, math flags, and repo layout."),
    ("look at my code", "Sure — read-only observe. I will summarize without changing anything."),
    ("smh", "Shaking my head. Rough."),
    ("fomo", "FOMO is fear of missing out."),
    ("flex", "A flex is showing off. Soft flex or hard flex — your call."),
    ("hit different", "Yeah, some things just hit different."),
    ("we outside", "We outside. Good energy."),
    ("it's lit", "It's lit. Let's keep the vibe up."),
    ("its lit", "It's lit. Let's keep the vibe up."),
    ("mood", "Mood. I get it."),
    ("same", "Same. Twin energy."),
    ("facts", "Facts."),
    ("big facts", "Big facts."),
    ("periodt", "Periodt. End of discussion."),
    ("slaps", "That slaps. Good taste."),
    ("bussin", "Bussin means really good — usually food, sometimes vibes."),
    ("sheesh", "Sheesh. Impressive."),
    ("yolo", "You only live once — still, maybe don't yolo the rent money."),
    ("fye", "Fye means fire. That goes hard."),
    ("cook", "Okay, cook. Show me what you got."),
    ("he's cooked", "He's cooked — basically done for."),
    ("hes cooked", "He's cooked — basically done for."),
    ("I'm dead", "I'm dead — as in that was hilarious."),
    ("im dead", "I'm dead — as in that was hilarious."),
    ("dead", "If you mean funny-dead, same. If you mean tired-dead, rest up."),
]

# Popular culture / games / internet — short clear Q&A the tiny LSTM can learn.
CULTURE_PAIRS = [
    (
        "what is fortnite",
        "Fortnite is a huge online game by Epic Games, famous for battle royale matches, building, and constant crossovers.",
    ),
    (
        "what's fortnite",
        "Fortnite is a popular multiplayer game — drop in, loot up, build, and try to be the last one standing.",
    ),
    (
        "whats fortnite",
        "Fortnite is a popular multiplayer game — drop in, loot up, build, and try to be the last one standing.",
    ),
    (
        "fortnite",
        "Fortnite is Epic Games' massive online hit: battle royale, creative maps, and a whole lot of skins.",
    ),
    (
        "do you know fortnite",
        "Yeah. Fortnite is the battle royale game where you build, shoot, and chase Victory Royales.",
    ),
    (
        "what is a victory royale",
        "A Victory Royale is a Fortnite win — last player or squad standing.",
    ),
    (
        "what is minecraft",
        "Minecraft is a sandbox game where you mine blocks, craft gear, build worlds, and survive mobs.",
    ),
    (
        "minecraft",
        "Minecraft is the blocky sandbox classic — creative builds, survival mode, Redstone, and endless worlds.",
    ),
    (
        "what is roblox",
        "Roblox is a platform where people play and create millions of user-made games with avatars and experiences.",
    ),
    (
        "roblox",
        "Roblox is a huge creation platform — think lots of mini-games, avatars, and UGC worlds.",
    ),
    (
        "what is gta",
        "GTA usually means Grand Theft Auto, a Rockstar open-world series. GTA Online is the big multiplayer mode.",
    ),
    (
        "what is gta 5",
        "GTA 5 is Grand Theft Auto V — a massive open-world game with story mode and GTA Online.",
    ),
    (
        "what is valorant",
        "Valorant is Riot's tactical shooter — agents with abilities, tight gunplay, round-based matches.",
    ),
    (
        "what is league of legends",
        "League of Legends is Riot's MOBA where two teams of five push lanes and destroy the enemy Nexus.",
    ),
    (
        "what is lol the game",
        "If you mean the game, LoL is League of Legends. If you mean chat slang, lol means laughing out loud.",
    ),
    (
        "what is apex",
        "Apex Legends is a free battle royale shooter with squads and legend abilities, from Respawn.",
    ),
    (
        "what is call of duty",
        "Call of Duty is a big FPS franchise — campaigns, multiplayer, and modes like Warzone.",
    ),
    (
        "what is warzone",
        "Warzone is Call of Duty's large-scale battle royale / extraction-style multiplayer mode.",
    ),
    (
        "what is among us",
        "Among Us is a social deduction game — crewmates do tasks while impostors try to sabotage them.",
    ),
    (
        "what is pokemon",
        "Pokémon is a huge franchise about catching creatures, battling, and becoming a trainer — games, shows, cards, all of it.",
    ),
    (
        "what is tiktok",
        "TikTok is a short-video app where trends, sounds, memes, and creators blow up fast.",
    ),
    (
        "tiktok",
        "TikTok is the short-form video app that basically runs modern internet trends.",
    ),
    (
        "what is youtube",
        "YouTube is the big video platform for everything from tutorials and music to gaming and long essays.",
    ),
    (
        "youtube",
        "YouTube is where creators upload videos — the default home of online video culture.",
    ),
    (
        "what is discord",
        "Discord is a chat app with servers, voice channels, and communities — big with gamers and friend groups.",
    ),
    (
        "what is twitch",
        "Twitch is a live streaming site, especially for gaming, chats, and creator streams.",
    ),
    (
        "what is instagram",
        "Instagram is Meta's photo and short-video social app — posts, Stories, Reels.",
    ),
    (
        "what is twitter",
        "Twitter, now often called X, is a public short-post social network known for news and chaos in equal measure.",
    ),
    (
        "what is x formerly twitter",
        "X is the platform formerly known as Twitter — short posts, replies, and endless timelines.",
    ),
    (
        "what is a meme",
        "A meme is a joke, image, or phrase that spreads and mutates across the internet.",
    ),
    (
        "what are memes",
        "Memes are internet jokes that travel fast — formats, catchphrases, and remix culture.",
    ),
    (
        "what is anime",
        "Anime is Japanese animation — tons of styles and genres, from chill slice-of-life to big action series.",
    ),
    (
        "what is manga",
        "Manga are Japanese comics, often the source material for anime adaptations.",
    ),
    (
        "what is kpop",
        "K-pop is Korean popular music — polished groups, big choreography, and a huge global fandom.",
    ),
    (
        "what is the nba",
        "The NBA is the top pro basketball league in North America — teams, stars, playoffs, championships.",
    ),
    (
        "what is the nfl",
        "The NFL is the top American football league — Sunday games, playoffs, and the Super Bowl.",
    ),
    (
        "what is the super bowl",
        "The Super Bowl is the NFL championship game and a huge US cultural event every year.",
    ),
    (
        "what is soccer",
        "Soccer — called football most places — is the world's biggest sport: two teams, one ball, chase the goal.",
    ),
    (
        "what is football",
        "Football can mean soccer worldwide, or American football in the US. Context decides.",
    ),
    (
        "what is twitch drops",
        "Twitch Drops are free in-game rewards you can earn by watching certain streams.",
    ),
    (
        "what is a skin in gaming",
        "A skin is a cosmetic look for a character, weapon, or item — style points, usually not power.",
    ),
    (
        "what is battle pass",
        "A battle pass is a seasonal reward track in games — play, unlock cosmetics, sometimes pay to unlock more.",
    ),
    (
        "what is an npc in games",
        "In games, an NPC is a non-player character. Online, calling someone an NPC means they seem autopiloted.",
    ),
    (
        "what is streaming",
        "Streaming means broadcasting live video online, usually on Twitch, YouTube, or Kick.",
    ),
    (
        "what is a speedrun",
        "A speedrun is beating a game as fast as possible, often with wild routing and glitches.",
    ),
    (
        "what is esports",
        "Esports is competitive gaming as a spectator sport — pro teams, tournaments, and big prize pools.",
    ),
    (
        "who is mrbeast",
        "MrBeast is a huge YouTube creator known for expensive challenges, philanthropy videos, and big production.",
    ),
    (
        "what is spotify",
        "Spotify is a major music streaming app for songs, podcasts, and playlists.",
    ),
    (
        "what is netflix",
        "Netflix is a big streaming service for movies, shows, and original series.",
    ),
    (
        "what is steam",
        "Steam is Valve's PC game store and launcher — library, sales, and workshops.",
    ),
    (
        "what is playstation",
        "PlayStation is Sony's console family — PS5 is the current flagship.",
    ),
    (
        "what is xbox",
        "Xbox is Microsoft's console brand — Game Pass is a big part of the ecosystem.",
    ),
    (
        "what is nintendo switch",
        "The Nintendo Switch is a hybrid console — dock for TV, undock for handheld play. Home of Mario, Zelda, and more.",
    ),
    (
        "what is mario",
        "Mario is Nintendo's iconic plumber character — platformers, parties, Kart, the whole empire.",
    ),
    (
        "what is zelda",
        "The Legend of Zelda is Nintendo's adventure series — Link, puzzles, exploration, and iconic worlds.",
    ),
    (
        "what is gen z slang",
        "Gen Z slang is fast-moving internet talk — fr, bet, mid, goated, rizz, and whatever TikTok invents next.",
    ),
    (
        "teach me slang",
        "Sure. Yo means hey. Fr means for real. Bet means okay. Goated means legendary. Cap means lying.",
    ),
    (
        "what does fr mean",
        "Fr means for real — agreeing hard or emphasizing honesty.",
    ),
    (
        "what does bet mean",
        "Bet means okay, deal, or I'm down. Casual confirmation.",
    ),
    (
        "what does goated mean",
        "Goated means greatest of all time — peak praise.",
    ),
    (
        "what does no cap mean",
        "No cap means no lie — I'm being real.",
    ),
    (
        "what does mid mean",
        "Mid means average or disappointing — not it.",
    ),
    (
        "what does rizz mean",
        "Rizz is charisma, especially flirt game.",
    ),
    (
        "are you chronically online",
        "A little. I learned slang and game basics so I can keep up without melting into meme sludge.",
    ),
    (
        "talk normal",
        "Okay. I can switch to clear, standard English anytime.",
    ),
    (
        "talk casual",
        "Bet. I'll keep it chill and readable.",
    ),
]

# Extra phrasings so the char model generalizes "what is X" questions.
_EXTRA_Q = [
    "what is {x}",
    "what's {x}",
    "whats {x}",
    "define {x}",
    "explain {x}",
    "do you know {x}",
    "ever heard of {x}",
    "tell me about {x}",
]

_FACT_BANK = [
    ("fortnite", "Fortnite is Epic's online battle royale with building and loot."),
    ("minecraft", "Minecraft is a sandbox game about mining, crafting, and building."),
    ("roblox", "Roblox is a platform of user-made games and avatars."),
    ("tiktok", "TikTok is a short-video social app for trends and sounds."),
    ("youtube", "YouTube is the main video-sharing site for creators and music."),
    ("discord", "Discord is a chat app with servers and voice channels."),
    ("twitch", "Twitch is a live-streaming platform, especially for gaming."),
    ("valorant", "Valorant is Riot's tactical FPS with agents and abilities."),
    ("apex legends", "Apex Legends is a squad battle royale shooter."),
    ("gta", "GTA is Rockstar's Grand Theft Auto open-world series."),
    ("pokemon", "Pokémon is about catching and battling creatures."),
    ("anime", "Anime is Japanese animation across many genres."),
    ("nba", "The NBA is North America's top pro basketball league."),
    ("nfl", "The NFL is the top American football league."),
    ("meme", "A meme is a viral joke format people remix online."),
    ("battle pass", "A battle pass is a seasonal unlock track for cosmetics."),
    ("skin", "In gaming, a skin is a cosmetic look for a character or item."),
    ("esports", "Esports is organized competitive gaming."),
]


def _expand_facts() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for key, ans in _FACT_BANK:
        for tmpl in _EXTRA_Q:
            out.append((tmpl.format(x=key), ans))
    return out


def build_culture_corpus() -> str:
    # Keep coverage; lighter repeat so the LSTM chats instead of dumping facts.
    # Runtime FAQ (maybe_culture_reply) owns high-confidence definitions.
    pairs = list(SLANG_PAIRS) + list(CULTURE_PAIRS) + _expand_facts()
    pairs = pairs + SLANG_PAIRS * 2 + CULTURE_PAIRS * 2 + _expand_facts()
    rng = random.Random(42)
    rng.shuffle(pairs)
    return "\n".join(f"you: {u}\nai: {a}\n" for u, a in pairs)


def save_culture_corpus() -> dict:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = build_culture_corpus()
    OUT.write_text(text, encoding="utf-8")
    return {"path": str(OUT), "chars": len(text), "lines": text.count("\n"), "pairs": text.count("you:")}


def _norm_q(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[?!.,]+$", "", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _faq_index() -> dict[str, str]:
    """Exact-question → answer map (definitions + slang that should only FAQ-match)."""
    idx: dict[str, str] = {}
    for u, a in list(CULTURE_PAIRS) + _expand_facts():
        idx[_norm_q(u)] = a
    # Definition-style slang only (not bare "mid" / "bet" as open chat)
    for u, a in SLANG_PAIRS:
        nu = _norm_q(u)
        if nu.startswith(("what is ", "what's ", "whats ", "what does ", "define ", "explain ")):
            idx[nu] = a
        elif " mean" in nu and nu.startswith("what"):
            idx[nu] = a
    # Safe exact dialogue fixes that must win over LSTM (applied last to win ties)
    preferred = {
        "excuse me": "Yes? What's up?",
        "hi": "Hey.",
        "hello": "Hello.",
        "hey": "Hey.",
        "what do you mean": "Which part? Say it another way.",
        "what do u mean": "Which part? Say it another way.",
        "wdym": "What do you mean? Which part?",
        "wdy m": "What do you mean? Which part?",
        "good": "Nice.",
        "good good": "Glad to hear it.",
        "huh": "Hmm? Say that again.",
        "what": "Hmm? Say that again.",
        "?": "Hmm? Say that again.",
        "what were you saying": "I may have glitched. Ask again.",
        "why were you talking about minecraft": (
            "Glitch — not about Minecraft. What did you want?"
        ),
        "why minecraft": "Sorry — wrong topic. What should we talk about?",
        "you too": "You too.",
        "same to you": "Same to you.",
        "can you see my code": "Yes — read-only. No edits.",
        "can you see my codebase": "Yes — wired read-only.",
        "can you read my code": "Observe only. Edits stay off.",
        "do you see my code": "Read-only observe. Ask find errors for a scan.",
        "have you seen the code": "Yes — observe mode. Edits stay off.",
        "have you seen teh code": "Yes — observe mode. Edits stay off.",
        "seen the code": "Yes. Observe only — say find errors for a scan.",
        "see the code": "Wired read-only. Ask briefing or find errors.",
        "see my code": "Yes — observe mode. Edits stay off.",
        "look at the code": "Sure — read-only. No edits.",
        "read the code": "Read-only. I summarize without changing anything.",
        "observe the stack": "Observing stack read-only — ask status or find errors.",
        "look at my code": "Read-only. Ask find errors for issues.",
        "keep it short": "Got it. I'll keep it short.",
        "keep em small": "OK — short answers from here.",
        "keep them small": "OK — short answers from here.",
        "stop making these big responses keep em small": "Got it. I'll keep it short.",
        "stop making big responses": "Understood. Keeping replies small.",
        "shorter": "Sure — shorter from here.",
        "be brief": "Brief it is.",
        "brief": "OK — brief answers.",
        "make it shorter": "Got it. Shorter replies.",
        "too long": "Fair. I'll keep it short.",
        "tl;dr": "Got it. Short version only.",
        "tldr": "Got it. Short version only.",
        "less words": "OK — fewer words.",
        "fewer words": "OK — fewer words.",
        "short answers": "Short answers. Deal.",
        "please keep replies short": "Got it. I'll keep it short.",
        "can you keep it short": "Yes. Short answers from here.",
        "stop rambling": "OK — short answers from here.",
        "one sentence": "One sentence. Got it.",
        "whats wrong": "Ask find errors or review codebase for a short issue list.",
        "what's wrong": "Ask find errors or review codebase for a short issue list.",
        "review codebase": "I can scan read-only and list issues — say find errors.",
    }
    for u, a in SLANG_PAIRS:
        nu = _norm_q(u)
        if nu in preferred:
            idx[nu] = preferred[nu]
    for nu, a in preferred.items():
        idx[nu] = a
    return idx


_SHORT_REQ_RE = re.compile(
    r"(?i)\b("
    r"keep\s+(it\s+|em\s+|them\s+)?(short|small|brief)|"
    r"stop\s+making.{0,40}(big|long|huge).{0,24}(response|reply|answer)|"
    r"(big|long|huge)\s+responses?|"
    r"\bshorter\b|\bbe\s+brief\b|\btl;?dr\b|"
    r"less\s+words|fewer\s+words|stop\s+rambling|one\s+sentence|"
    r"short\s+answers|make\s+it\s+shorter|too\s+long"
    r")\b"
)

_SHORT_ACKS = (
    "Got it. I'll keep it short.",
    "OK — short answers from here.",
    "Understood. Keeping replies small.",
    "Brief it is.",
)


_TOPIC_KEYS = sorted({k for k, _ in _FACT_BANK} | {
    "fortnite", "minecraft", "roblox", "tiktok", "youtube", "discord", "twitch",
    "valorant", "apex", "gta", "pokemon", "anime", "manga", "kpop", "nba", "nfl",
    "meme", "esports", "steam", "netflix", "spotify", "mario", "zelda",
}, key=len, reverse=True)

_SLANG_DEFINE = {
    "fr": "Fr means for real — agreeing hard or emphasizing honesty.",
    "bet": "Bet means okay, deal, or I'm down. Casual confirmation.",
    "goated": "Goated means greatest of all time — peak praise.",
    "no cap": "No cap means no lie — I'm being real.",
    "cap": "Cap means someone is lying or exaggerating. No cap means for real.",
    "mid": "Mid means average or disappointing — not it.",
    "rizz": "Rizz is charisma, especially flirt game.",
    "sus": "Sus means suspicious. Something feels off.",
    "afk": "AFK means away from keyboard.",
    "irl": "IRL means in real life.",
    "npc": "NPC means someone acting on autopilot, like a background character.",
    "gg": "GG means good game.",
    "fomo": "FOMO is fear of missing out.",
}

# Strict define for pop-culture topics: ONLY "what is X" / "what's X" / bare X.
_STRICT_TOPIC_DEFINE_RE = re.compile(
    r"(?i)^\s*(?:what\s+is|what'?s|whats)\s+(.+?)\s*$"
)
# Broader define for slang only (not Discord/Fortnite/…).
_DEFINE_RE = re.compile(
    r"(?i)^\s*(?:what\s+is|what'?s|whats|define|explain|tell\s+me\s+about|"
    r"do\s+you\s+know|ever\s+heard\s+of)\s+(.+?)\s*$"
)
_WHAT_DOES_RE = re.compile(
    r"(?i)^\s*what\s+does\s+(.+?)\s+mean\s*$"
)
# Bare topic only when the whole message is the topic (not a substring).
_BARE_TOPIC_OK = re.compile(r"(?i)^\s*([a-z0-9][a-z0-9 .'/-]{0,40})\s*$")

# Never culture-match when the user is clearly talking about the repo/stack.
_CODE_CONTEXT_RE = re.compile(
    r"(?i)\b(code|codebase|code\s*base|repo|repository|stack|train|training|"
    r"error|errors|bug|bugs|inaccurac\w*|inaccurate|mistake|mistakes|issue|issues|"
    r"problem|problems|wrong)\b"
)

_FACT_KEYS = {k for k, _ in _FACT_BANK}
_FACT_ANS_BY_KEY = {k: a for k, a in _FACT_BANK}


def _query_asks_culture_topic(n: str, topic: str) -> bool:
    """Culture topic FAQ only when topic is the sole subject: bare or 'what is'."""
    if not topic or not n:
        return False
    if n == topic:
        return True
    m = _STRICT_TOPIC_DEFINE_RE.match(n)
    if not m:
        return False
    got = _norm_q(m.group(1))
    got = re.sub(r"^(a|an|the)\s+", "", got)
    return got == topic


def _answer_topic_if_asked(n: str) -> str | None:
    """Return fact-bank answer only for bare topic or what-is/what's/whats."""
    if n in _FACT_ANS_BY_KEY:
        return _FACT_ANS_BY_KEY[n]
    m = _STRICT_TOPIC_DEFINE_RE.match(n)
    if not m:
        return None
    topic = _norm_q(m.group(1))
    topic = re.sub(r"^(a|an|the)\s+", "", topic)
    return _FACT_ANS_BY_KEY.get(topic)


def _is_culture_topic_dump(ans: str) -> str | None:
    """If ans is a fact-bank dump, return the topic key; else None."""
    a = (ans or "").strip().lower()
    if not a:
        return None
    for key, canned in _FACT_BANK:
        if a.startswith(canned.lower()[:24]) or a.startswith(f"{key} is"):
            return key
    # Broader CULTURE_PAIRS style openings
    for key in _FACT_KEYS:
        if a.startswith(f"{key} is") or a.startswith(f"{key} —"):
            return key
    if a.startswith("soccer") or "football league" in a:
        return "soccer"
    return None


def maybe_culture_reply(user: str) -> str | None:
    """High-confidence culture/slang FAQ only. Returns None for open chat.

    Culture topics (Discord, Minecraft, …) ONLY fire when:
      - exact bare topic word/phrase, OR
      - clear 'what is <topic>' / 'what's <topic>' / 'whats <topic>'
    NEVER on substring coincidence or loose 'do you know X' for those topics.
    NEVER on code/error/inaccuracy talk.
    """
    raw = (user or "").strip()
    if not raw:
        return None

    # Lone "?" survives _norm_q as empty — handle before strip
    if re.fullmatch(r"[?？]+", raw):
        return "Hmm? Say that again."

    n = _norm_q(raw)
    if not n:
        return None

    # Never steal codebase / error / observe intents (handlers own those)
    try:
        from intel.talk_codebase import wants_factual

        if wants_factual(raw) or wants_factual(n):
            return None
    except Exception:
        pass

    # Hard block: never dump Soccer/Discord/etc. on code/error talk
    if _CODE_CONTEXT_RE.search(raw) or _CODE_CONTEXT_RE.search(n):
        return None

    # Strict culture-topic FAQ (Discord etc.) — before loose FAQ index
    topic_ans = _answer_topic_if_asked(n)
    if topic_ans is not None:
        return topic_ans

    idx = _faq_index()

    # Exact whole-phrase hit (dialogue fixes: wdym, good, huh, …)
    if n in idx:
        ans = idx[n]
        dump_topic = _is_culture_topic_dump(ans)
        if dump_topic is not None and not _query_asks_culture_topic(n, dump_topic):
            # e.g. "do you know discord" in training index — ban unless what-is/bare
            return None
        return ans

    # "keep it short" / "keep em small" / similar — never invent Delulu salad
    # Never steal earning / P&L / portfolio talk (e.g. "... money overall")
    if _SHORT_REQ_RE.search(raw) or _SHORT_REQ_RE.search(n):
        if re.search(
            r"(?i)\b(earn|earning|earnings|profit|pnl|p\s*&\s*l|portfolio|equity|"
            r"making\s+money|losing\s+money|up\s+or\s+down)\b",
            raw,
        ) or re.search(
            r"(?i)\b(earn|earning|earnings|profit|pnl|portfolio|equity|"
            r"making\s+money|losing\s+money|up\s+or\s+down)\b",
            n,
        ):
            return None
        return random.choice(_SHORT_ACKS)

    # Clear "what does X mean" — slang first; culture topics only if exact key
    m = _WHAT_DOES_RE.match(n)
    if m:
        topic = _norm_q(m.group(1))
        if topic in _SLANG_DEFINE:
            return _SLANG_DEFINE[topic]
        if topic in _FACT_ANS_BY_KEY:
            return _FACT_ANS_BY_KEY[topic]
        return None

    # Broader define/explain — SLANG only (never Discord via "do you know discord")
    m = _DEFINE_RE.match(n)
    if m:
        topic = _norm_q(m.group(1))
        topic = re.sub(r"^(a|an|the)\s+", "", topic)
        if topic in _SLANG_DEFINE:
            return _SLANG_DEFINE[topic]
        # Culture topics already handled by _answer_topic_if_asked (strict only)
        return None

    # Whole message is exactly a known topic word/phrase
    m = _BARE_TOPIC_OK.match(n)
    if m:
        topic = _norm_q(m.group(1))
        if topic in _FACT_ANS_BY_KEY:
            return _FACT_ANS_BY_KEY[topic]
        # Bare slang like "goated" / "rizz" — OK when alone
        if topic in _SLANG_DEFINE and topic in {
            "goated", "rizz", "sus", "afk", "fomo", "npc", "gg", "cap",
        }:
            return _SLANG_DEFINE[topic]

    # "why … minecraft" after a glitch — apologize, do NOT redefine Minecraft
    if "minecraft" in n and re.search(r"\b(why|what were you|were you)\b", n):
        if not _STRICT_TOPIC_DEFINE_RE.match(n) and not n.startswith("what is"):
            return (
                "That was a glitch — I wasn't trying to talk about Minecraft. "
                "Ask again and I'll stay on your topic."
            )

    return None


# Slang tokens fix_typos must not "correct" into unrelated dictionary words.
SLANG_KEEP: set[str] = {
    "yo",
    "sup",
    "wassup",
    "lol",
    "lmao",
    "fr",
    "cap",
    "bet",
    "mid",
    "goated",
    "rizz",
    "sus",
    "bruh",
    "ong",
    "ngl",
    "tbh",
    "imo",
    "idk",
    "afk",
    "irl",
    "smh",
    "fomo",
    "gg",
    "glhf",
    "npc",
    "based",
    "cringe",
    "slay",
    "flex",
    "vibe",
    "vibes",
    "lowkey",
    "highkey",
    "deadass",
    "finna",
    "delulu",
    "bussin",
    "sheesh",
    "yolo",
    "fye",
    "iykyk",
    "skibidi",
    "gyatt",
    "sigma",
    "ratio",
    "fortnite",
    "minecraft",
    "roblox",
    "tiktok",
    "valorant",
    "warzone",
    "twitch",
    "discord",
    "anime",
    "manga",
    "kpop",
    "mrbeast",
    "esports",
    "pokemon",
}
