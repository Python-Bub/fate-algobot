#!/usr/bin/env python3
"""Smoke: talk intent routing + one-letter typo repair.

  ./venv/bin/python tools/smoke_talk_intents.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("TALK_CONNECT_CODEBASE", "true")
os.environ.setdefault("TALK_ALLOW_EDITS", "false")


def _route(user: str, *, prior: str = "", last_offer: str = "") -> tuple[str, str]:
    """Mirror operator_terminal_chat handler order (no LSTM)."""
    from intel.talk_browser import maybe_lookup, maybe_open
    from intel.talk_codebase import (
        _INCOMPLETE_EARNING_CONT,
        _prior_earning_context,
        maybe_handle,
        wants_error_scan,
        wants_observe,
        wants_portfolio,
    )
    from intel.talk_culture import maybe_culture_reply
    from intel.talk_grammar import fix_typos, maybe_grammar_lesson

    cleaned = fix_typos(user)
    opened = maybe_open(cleaned) or maybe_open(user)
    if opened is not None:
        return opened, "browser"
    fact = maybe_handle(user, prior=prior, last_offer=last_offer) or maybe_handle(
        cleaned, prior=prior, last_offer=last_offer
    )
    if fact is not None:
        kind = "errors" if wants_error_scan(cleaned) or wants_error_scan(user) else "observe"
        if wants_portfolio(cleaned) or wants_portfolio(user):
            kind = "portfolio"
        if _INCOMPLETE_EARNING_CONT.match(cleaned.strip()) or _INCOMPLETE_EARNING_CONT.match(
            (user or "").strip()
        ):
            if _prior_earning_context(prior):
                kind = "portfolio"
        from intel.talk_codebase import incomplete_prompt_reply, is_affirmation

        if incomplete_prompt_reply(cleaned) or incomplete_prompt_reply(user):
            # Incomplete "Do you" — but not earning-continuation "are we"
            if kind != "portfolio":
                kind = "incomplete"
        if last_offer and (is_affirmation(cleaned) or is_affirmation(user)):
            kind = last_offer if last_offer in ("errors", "observe", "portfolio") else "affirm"
        if prior and kind == "observe":
            from intel.talk_codebase import _FOLLOWUP_THEM_PAT, wants_factual

            if _FOLLOWUP_THEM_PAT.search(cleaned) and (
                wants_factual(prior) or wants_error_scan(prior)
            ):
                kind = "errors"
        return fact, kind
    looked = maybe_lookup(cleaned) or maybe_lookup(user)
    if looked is not None:
        return looked, "lookup"
    cult = maybe_culture_reply(cleaned) or maybe_culture_reply(user)
    if cult is not None:
        return cult, "culture"
    gram = maybe_grammar_lesson(cleaned) or maybe_grammar_lesson(user)
    if gram is not None:
        return gram, "grammar"
    return "", "lstm"


_BLEED = ("discord", "soccer", "minecraft", "fortnite", "roblox", "tiktok", "anoked", "anomeshing")
_GRAMMAR_LEAK = ("then = time", "than = comparison", "you are welcome")


def _assert_no_bleed(prompt: str, reply: str) -> None:
    low = (reply or "").lower()
    for bad in _BLEED:
        if bad in low:
            raise AssertionError(f"{prompt!r} bled culture ({bad}): {reply!r}")


def main() -> int:
    from intel.talk_culture import maybe_culture_reply
    from intel.talk_grammar import fix_typos

    fails: list[str] = []

    # --- One-letter / common typo repair (≥25) ---
    print("=== typo repair ===")
    typo_cases = [
        ("teh", "the"),
        ("hte", "the"),
        ("u", "you"),
        ("r", "are"),
        ("ur", "your"),
        ("wee", "we"),
        ("wat", "what"),
        ("whag", "what"),
        ("whats", "what's"),
        ("goin", "going"),
        ("sayinng", "saying"),
        ("nay", "any"),
        ("smth", "something"),
        ("yk", "you know"),
        ("dont", "don't"),
        ("cant", "can't"),
        ("wont", "won't"),
        ("couldnt", "couldn't"),
        ("adn", "and"),
        ("taht", "that"),
        ("tehse", "these"),
        ("wierd", "weird"),
        ("recieve", "receive"),
        ("helo", "hello"),
        ("becuase", "because"),
        ("seperate", "separate"),
        ("tjrough", "through"),
        ("findiing", "finding"),
        ("teh code already worked once", "the code already worked once"),
        ("take ur time to read tjrough the code", "take your time to read through the code"),
        ("Try findiing errors", "Try finding errors"),
        ("inaccuracies", "inaccuracies"),
        ("codebase", "codebase"),
        ("fortress", "fortress"),
        ("alpaca", "alpaca"),
        ("LSTM", "LSTM"),
        ("tickers", "tickers"),
    ]
    typo_ok = 0
    for src, expect in typo_cases:
        got = fix_typos(src)
        ok = got == expect
        if not ok:
            fails.append(f"typo {src!r}: got {got!r} want {expect!r}")
        else:
            typo_ok += 1
        print(f"  [{'OK' if ok else 'FAIL'}] {src!r} → {got!r}")
    print(f"  typo pass {typo_ok}/{len(typo_cases)}")

    # --- Exact failing user prompts ---
    cases = [
        ("Read the code", "observe", None, ""),
        ("So are there any inaccuracies", "errors", "Read the code", ""),
        ("like do u read any of them", "errors", "So are there any inaccuracies", ""),
        ("do u read any inaccuracies", "errors", None, ""),
        ("are there any inaccuracies", "errors", None, ""),
        ("find errors", "errors", None, ""),
        ("Try findiing errors", "errors", None, ""),
        ("Try finding errors", "errors", None, ""),
        ("check for errors", "errors", None, ""),
        ("what's wrong", "errors", None, ""),
        ("do you read", "observe", None, ""),
        ("have you read the code", "observe", None, ""),
        ("seen the code", "observe", None, ""),
        ("take ur time to read tjrough the code", "observe", None, ""),
        ("Yes, do that.", "errors", "Try finding errors", "errors"),
        ("yes do that", "errors", None, "errors"),
        ("do that", "errors", None, "errors"),
        ("do you see the equity", "portfolio", None, ""),
        ("Do you see the value of the portfolio", "portfolio", None, ""),
        ("yo do u see the portfolio", "portfolio", None, ""),
        ("Do you see the portfolio", "portfolio", None, ""),
        ("well are we earning", "portfolio", None, ""),
        ("are we earning", "portfolio", None, ""),
        ("am i earning money", "portfolio", None, ""),
        ("are wee earning money overall", "portfolio", None, ""),
        ("are we", "portfolio", "well are we earning", ""),
        ("is the portfolio value going up or down", "portfolio", None, ""),
        ("Do you", "incomplete", None, ""),
        ("buying power", "portfolio", None, ""),
        ("account value", "portfolio", None, ""),
    ]

    print("=== failing / required prompts ===")
    for prompt, expect_kind, prior, offer in cases:
        reply, kind = _route(prompt, prior=prior or "", last_offer=offer or "")
        cleaned = fix_typos(prompt)
        cult = maybe_culture_reply(cleaned) or maybe_culture_reply(prompt)
        ok = True
        try:
            _assert_no_bleed(prompt, reply)
            if cult is not None:
                _assert_no_bleed(prompt, cult)
                if expect_kind in ("errors", "observe", "portfolio", "incomplete"):
                    raise AssertionError(f"culture stole {prompt!r}: {cult!r}")
            if kind != expect_kind:
                raise AssertionError(f"expected {expect_kind}, got {kind}: {reply!r}")
            if not reply or reply.endswith((" or say", " or say ")):
                raise AssertionError(f"truncated/empty reply for {prompt!r}: {reply!r}")
            if "hmm?" in reply.lower() and "say that again" in reply.lower() and expect_kind != "culture":
                if expect_kind not in ("incomplete",):
                    raise AssertionError(f"huh-fallback for {prompt!r}: {reply!r}")
            if "observe mod" in reply.lower() and not reply.lower().rstrip(".").endswith("mode"):
                if "observe mode" not in reply.lower():
                    raise AssertionError(f"truncated observe tease for {prompt!r}: {reply!r}")
            if expect_kind == "errors":
                low = reply.lower()
                if "i can check the stack" in low:
                    raise AssertionError(f"tease instead of error_report: {reply!r}")
                if "then = time" in low or "anoked" in low:
                    raise AssertionError(f"bad leak on errors: {reply!r}")
            if expect_kind == "portfolio":
                low = reply.lower()
                if "fair. we can decide" in low or "anoked" in low or "anomeshing" in low:
                    raise AssertionError(f"portfolio hit LSTM garbage: {reply!r}")
                if "equity" not in low and "account" not in low and "portfolio" not in low and "paper" not in low:
                    raise AssertionError(f"portfolio reply missing numbers/status: {reply!r}")
                # Earning / P&L prompts must never hit keep-short or grammar rewrite dumps
                for leak in (
                    "short answers from here",
                    "keep it short",
                    "share the sentence",
                    "got it — want to",
                    "not sure i got that",
                ):
                    if leak in low:
                        raise AssertionError(f"earning/P&L leaked FAQ/LSTM ({leak}): {reply!r}")
                if any(
                    x in prompt.lower()
                    for x in ("earn", "up or down", "are we", "am i earning")
                ):
                    if not any(x in low for x in ("up today", "down today", "equity $", "equity")):
                        raise AssertionError(f"earning reply missing UP/DOWN or equity: {reply!r}")
                    if "want to" in low or "restate" in low:
                        raise AssertionError(f"earning hit grammar dump: {reply!r}")
            if expect_kind == "incomplete":
                if "do i what" not in reply.lower():
                    raise AssertionError(f"incomplete want Do I what?: {reply!r}")
                for leak in _GRAMMAR_LEAK:
                    if leak in reply.lower():
                        raise AssertionError(f"incomplete leaked {leak}: {reply!r}")
            for leak in _GRAMMAR_LEAK:
                if expect_kind not in ("grammar",) and leak in reply.lower() and expect_kind == "errors":
                    raise AssertionError(f"grammar leak on {prompt!r}: {reply!r}")
            if "then = time" in reply.lower() and expect_kind != "grammar":
                raise AssertionError(f"Then/Than hijack on {prompt!r}: {reply!r}")
            if "you are welcome" in reply.lower() and "thank" not in prompt.lower():
                raise AssertionError(f"thanks hijack on {prompt!r}: {reply!r}")
        except AssertionError as e:
            ok = False
            fails.append(str(e))
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {prompt!r} → {kind}: {reply[:110]!r}")

    # Explicit grammar ask still works
    print("=== grammar gate ===")
    gram_cases = [
        ("then or than", True),
        ("Yes, do that.", False),
        ("Do you", False),
        ("do you see the equity", False),
    ]
    from intel.talk_grammar import maybe_grammar_lesson

    for prompt, should in gram_cases:
        g = maybe_grammar_lesson(fix_typos(prompt)) or maybe_grammar_lesson(prompt)
        fired = g is not None
        ok = fired == should
        if not ok:
            fails.append(f"grammar gate {prompt!r}: fired={fired} want={should} ans={g!r}")
        print(f"  [{'OK' if ok else 'FAIL'}] {prompt!r} fire={fired} (want {should})")

    # --- Discord must ONLY fire for bare / what is / what's ---
    print("=== discord culture gate ===")
    discord_ok = [
        ("discord", True),
        ("what is discord", True),
        ("what's discord", True),
        ("whats discord", True),
        ("do you know discord", False),
        ("ever heard of discord", False),
        ("tell me about discord", False),
        ("define discord", False),
        ("explain discord", False),
        ("do you read any inaccuracies", False),
        ("like do u read any of them", False),
        ("Yes, do that.", False),
        ("Do you see the portfolio", False),
    ]
    for prompt, should_fire in discord_ok:
        cult = maybe_culture_reply(fix_typos(prompt)) or maybe_culture_reply(prompt)
        fired = cult is not None and "discord" in (cult or "").lower()
        ok = fired == should_fire
        if not ok:
            fails.append(
                f"discord gate {prompt!r}: fired={fired} expected={should_fire} ans={cult!r}"
            )
        print(
            f"  [{'OK' if ok else 'FAIL'}] {prompt!r} fire={fired} "
            f"(want {should_fire}) ans={None if cult is None else cult[:60]!r}"
        )
        if cult is not None and not should_fire and any(b in (cult or "").lower() for b in _BLEED):
            fails.append(f"unexpected culture bleed on {prompt!r}: {cult!r}")
        if not should_fire and cult is not None and prompt.lower() in {
            "do you read any inaccuracies",
            "like do u read any of them",
            "yes, do that.",
            "do you see the portfolio",
        }:
            fails.append(f"culture should be None for {prompt!r}, got {cult!r}")

    print("=== root-cause check ===")
    bad = "do you read any inaccuracies"
    cult = maybe_culture_reply(bad)
    reply, kind = _route(bad)
    print(f"  maybe_culture_reply({bad!r}) = {cult!r}")
    print(f"  route kind={kind} reply={reply[:120]!r}")
    if cult is not None:
        fails.append("FAQ still returns Discord/culture for inaccuracy prompt")
    if kind != "errors":
        fails.append(f"inaccuracy prompt not routed to errors (got {kind})")

    # Live-failing transcript table
    print("=== live transcript smoke ===")
    live = [
        ("take ur time to read tjrough the code", "observe", "", ""),
        ("Try findiing errors", "errors", "", ""),
        ("Yes, do that.", "errors", "Try findiing errors", "errors"),
        ("do you see the equity", "portfolio", "", ""),
        ("Do you", "incomplete", "", ""),
        ("Do you see the value of the portfolio", "portfolio", "", ""),
        ("yo do u see the portfolio", "portfolio", "", ""),
        ("Do you see the portfolio", "portfolio", "", ""),
        ("well are we earning", "portfolio", "", ""),
        ("are we", "portfolio", "well are we earning", ""),
        ("are wee earning money overall", "portfolio", "", ""),
        ("am i earning money", "portfolio", "", ""),
        ("is the portfolio value going up or down", "portfolio", "", ""),
    ]
    for prompt, expect, prior, offer in live:
        reply, kind = _route(prompt, prior=prior, last_offer=offer)
        ok = kind == expect and reply and "then = time" not in reply.lower()
        ok = ok and "anoked" not in reply.lower() and "you are welcome" not in reply.lower()
        if kind == "observe" and "tjrough" in (fix_typos(prompt) if False else ""):
            ok = False
        if "tjrough" in prompt.lower():
            cleaned = fix_typos(prompt)
            if "tjrough" in cleaned.lower() or "through" not in cleaned.lower():
                ok = False
                fails.append(f"tjrough not fixed in {prompt!r} → {cleaned!r}")
        if not ok and kind != expect:
            fails.append(f"live {prompt!r}: kind={kind} want={expect} reply={reply!r}")
        elif not ok:
            fails.append(f"live {prompt!r}: bad reply {reply!r}")
        print(f"  [{'OK' if ok else 'FAIL'}] {prompt!r} → {kind}: {reply[:100]!r}")

    if fails:
        print("\nFAILED:")
        for f in fails:
            print(f"  - {f}")
        return 1
    print(f"\nALL GREEN (typos {typo_ok}/{len(typo_cases)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
