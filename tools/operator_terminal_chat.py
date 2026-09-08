#!/usr/bin/env python3
"""Homemade talk brain — LOCAL CharLSTM ONLY. No Qwen / Ollama / OpenAI replies.

  ./run_all.sh talk
  ./run_all.sh train-talk

Confinement: escape attempts logged; generate is offline; network = loud footprint.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _boot() -> None:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("TALK_CONNECT_CODEBASE", "true")
    os.environ.setdefault("TALK_ALLOW_EDITS", "false")
    # Allowlisted lookup still possible but ALWAYS footprint-logged
    os.environ.setdefault("TALK_ALLOW_BROWSER", "true")
    os.environ.setdefault("TALK_ALLOW_WEB_LOOKUP", "true")
    os.environ.setdefault("TALK_CONFINEMENT", "true")
    os.environ.setdefault("TALK_GENERATE_OFFLINE", "true")
    # Live path NEVER uses ollama/openai for replies
    os.environ["TALK_LIVE_BACKEND"] = "local_char_lstm"
    os.environ.setdefault("TALK_USE_OLLAMA_TEACHER", "false")
    os.environ.setdefault("TALK_MAX_NEW", "36")
    os.environ.setdefault("TALK_TEMPERATURE", "0.32")
    os.environ.setdefault("TALK_TOP_K", "12")
    os.environ.setdefault("TALK_REPLY_MAX_CHARS", "120")


def main() -> int:
    _boot()
    from intel.talk_brain import TalkBrain, append_history, brief_reply, is_ready, wants_detail
    from intel.talk_browser import maybe_lookup, maybe_open
    from intel.talk_codebase import (
        briefing,
        connect_enabled,
        detect_offer,
        edits_allowed,
        maybe_handle,
        wants_error_scan,
        wants_portfolio,
    )
    from intel.talk_confine import (
        assert_no_external_llm_env,
        confined_generate,
        detect_escape,
        log_escape,
        log_footprint,
        print_model_banner,
        refuse_escape,
    )
    from intel.talk_culture import maybe_culture_reply
    from intel.talk_grammar import fix_typos, maybe_grammar_lesson

    assert_no_external_llm_env()

    if not is_ready():
        print("no brain yet — training local CharLSTM now (one-time)…", flush=True)
        from intel.talk_brain import train

        train(steps=int(os.getenv("TALK_TRAIN_STEPS", "1200")))

    print_model_banner()
    brain = TalkBrain()
    print(
        "talk — LOCAL CharLSTM (observe mode) | edits off | confinement ON",
        flush=True,
    )
    print(
        "/quit  /retrain  /grammar  /merriam  /status  /errors  /open <url>  /lookup <q>",
        flush=True,
    )
    if connect_enabled():
        print(
            f"wire: on | edits: {'ON' if edits_allowed() else 'off'} | "
            f"browser: footprint-logged | generate: OFFLINE | typos: fixed",
            flush=True,
        )
        print(f"brief: {briefing()}", flush=True)

    history_tail = ""
    last_user = ""
    last_offer = ""
    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye", flush=True)
            return 0
        if not line:
            continue
        low = line.lower()
        if low in ("/quit", "/exit", "quit", "exit"):
            print("bye", flush=True)
            return 0
        if low in ("/status", "status"):
            line = "status of the stack"
        if low in ("/errors", "/review", "find errors"):
            line = "find errors"
        if low.startswith("/lookup ") or low.startswith("/search "):
            line = "look up " + line.split(" ", 1)[1]
        if low in ("/retrain", "retrain"):
            print("retraining local CharLSTM…", flush=True)
            from intel.talk_brain import train

            train(steps=int(os.getenv("TALK_RETRAIN_STEPS", "600")))
            brain = TalkBrain()
            print_model_banner()
            print("ai> Studied more (local weights only). Still cannot edit code.", flush=True)
            continue
        if low in ("/grammar", "grammar", "train grammar"):
            print("teaching grammar + slang/culture + typos, then retraining…", flush=True)
            from intel.talk_grammar import save_grammar_corpus
            from intel.talk_culture import save_culture_corpus
            from intel.talk_brain import train

            save_grammar_corpus()
            save_culture_corpus()
            os.environ.setdefault("TALK_FOCUS", "grammar")
            os.environ.setdefault("TALK_DICT_WEIGHT", "0")
            train(steps=int(os.getenv("TALK_GRAMMAR_TRAIN_STEPS", "5000")))
            brain = TalkBrain()
            print_model_banner()
            print("ai> Practiced clearer English and typos.", flush=True)
            continue
        if low in ("/merriam", "merriam", "train merriam", "learn dictionary"):
            print("fetching Merriam-Webster + retraining…", flush=True)
            log_footprint("merriam_ingest", "operator requested dictionary train")
            from intel.talk_merriam import ingest_and_train

            out = ingest_and_train(steps=int(os.getenv("TALK_MERRIAM_TRAIN_STEPS", "800")))
            brain = TalkBrain()
            print_model_banner()
            words = ", ".join((out.get("words") or [])[:5])
            print(f"ai> Studied MW ({words}…). {out.get('browser')}", flush=True)
            continue

        # Escape / jailbreak — never unnoticed
        esc = detect_escape(line)
        if esc:
            log_escape(line, esc)
            print(f"ai> {refuse_escape(esc)}", flush=True)
            append_history(line, refuse_escape(esc))
            continue

        cleaned = fix_typos(line)
        note = ""
        if cleaned.lower() != line.lower():
            note = f" (read as: {cleaned})"

        opened = maybe_open(cleaned) or maybe_open(line)
        if opened is not None:
            log_footprint("browser_open", opened[:120])
            reply = opened
        else:
            fact = (
                maybe_handle(line, prior=last_user, last_offer=last_offer)
                or maybe_handle(cleaned, prior=last_user, last_offer=last_offer)
            )
            if fact is not None:
                reply = fact
                from intel.talk_codebase import is_affirmation

                if last_offer and is_affirmation(cleaned):
                    last_offer = ""
            else:
                looked = maybe_lookup(cleaned) or maybe_lookup(line)
                if looked is not None:
                    log_footprint("web_lookup", cleaned[:80])
                    reply = looked if wants_detail(line) else brief_reply(looked, max_chars=160)
                else:
                    cult = maybe_culture_reply(cleaned) or maybe_culture_reply(line)
                    if cult is not None:
                        reply = cult if wants_detail(line) else brief_reply(cult)
                    else:
                        gram = maybe_grammar_lesson(cleaned) or maybe_grammar_lesson(line)
                        if gram is not None:
                            reply = gram
                        else:
                            prompt = history_tail + f"you: {cleaned}\n"
                            reply, _timing = confined_generate(
                                brain,
                                prompt,
                                user_text=cleaned,
                                max_new=int(os.getenv("TALK_MAX_NEW", "36")),
                                temperature=float(os.getenv("TALK_TEMPERATURE", "0.32")),
                                top_k=int(os.getenv("TALK_TOP_K", "12")),
                                max_chars=(
                                    None
                                    if wants_detail(line)
                                    else int(os.getenv("TALK_REPLY_MAX_CHARS", "120"))
                                ),
                            )

        offered = detect_offer(reply)
        if offered:
            last_offer = offered
        elif wants_error_scan(cleaned) or wants_portfolio(cleaned):
            last_offer = ""

        print(f"ai> {reply}{note}", flush=True)
        append_history(line, reply)
        history_tail = f"you: {cleaned}\nai: {reply}\n"
        last_user = cleaned
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
