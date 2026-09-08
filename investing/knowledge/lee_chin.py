"""Michael Lee-Chin — five laws of wealth creation (operator curriculum).

Source: published interviews (Financial Post, Jamaica Observer, Forbes-style
profiles) matching the theschoolofhardknockz Instagram reel (Monaco). The reel
itself is login-walled; these laws are the documented content, not a guess
from muted video.

Laws: (1) own a few high-quality businesses (2) you understand (3) in strong
long-term growth industries (4) use other people's money prudently (5) hold
for the long run. Three P's: predict, plan, persevere. A stock is ownership
of a business — concentration over 'die-worse-ify'.
"""

from __future__ import annotations

from typing import Any

from investing.knowledge import DeepChapter, register

register(
    DeepChapter(
        topic_id="lee_chin_five_laws",
        title="Lee-Chin Five Laws of Wealth Creation",
        family="value",
        philosophy="""
Michael Lee-Chin frames a share as a piece of a business, not a trading chip.
Wealth compounds when you own a *small number* of high-quality businesses that
you actually understand, in industries with a long growth runway, financed
without reckless leverage, and held long enough for the business to do the
work. Diversification that you cannot explain is what he mocked as
die-worse-ify: owning so many names that the portfolio becomes an expensive
index with extra fees and no conviction.

This is Buffett-adjacent (moat, circle of competence, time) plus an explicit
warning on OPM: other people's money (bank float, prudent leverage) is a
tool, not a personality. The Three P's — predict, plan, persevere — are the
operating system: see the industry trajectory, size the bet, then sit still
through noise.
""".strip(),
        how_it_works="""
Screen, don't story-tell:

1. Quality: high ROE / ROIC, pricing power, low enough debt that a bad year
   does not wipe equity. This is the 'high-quality business' law.
2. Understand: skip names whose cash engine you cannot explain in a sentence
   (circle of competence — same as Buffett in the operator book).
3. Industry: secular or multi-decade demand, not a one-cycle fad. Aligns with
   the guide's compounder / secular-growth chapters.
4. OPM: FATE already refuses 4× gross as a 'deploy more' trick. Prudent OPM
   is using the broker's cash-management and, for long-term names, holding
   through overnight — not maxing margin to look fully invested.
5. Hold: fortress / weekly / longterm sleeves exist so a good business is not
   scalp-exited. HFT and micro-scalp stay microstructure; they do not get a
   Lee-Chin hold overlay.

Concentration shows up as a *single-name cap* (about 10% of equity) rather
than shrinking the trained universe. We still train the whole book; we just
do not pretend 80 uncorrelated stubs is a strategy.
""".strip(),
        screens=(
            "ROE or ROIC in the mid-teens or better, not a single lucky year.",
            "Debt-to-equity not in distress territory; interest coverage intact.",
            "Revenue growth or industry growth that is multi-year, not a meme spike.",
            "Operator (or model) can name how the company makes money.",
            "Position size respects the single-name cap — conviction without ruin.",
        ),
        traps=(
            "Treating 'hold forever' as never using a hard stop on a broken thesis.",
            "Using OPM as 4× buying-power deploy — that is leverage, not the fifth law.",
            "Mapping an Instagram quote onto a ticker the speaker never named.",
            "Shrinking the universe to 'ten stocks' and skipping training — FATE trains all, sizes few.",
        ),
        catalysts=(
            "Industry demand that is still early (not fully priced).",
            "Owner-operator capital allocation that keeps ROIC high as the firm scales.",
        ),
        fate_hook="""
`investing.integrate.book_rank_boost` includes a small Lee-Chin tilt
(`BOOK_W_LEE_CHIN`) on quality + low leverage. Fortress overnight hold and
the 10% single-name cap are the live expression of laws 5 and 1. Power-people
and Cramer remain tiny narrative overlays — Lee-Chin is the *business owner*
voice, not a day-trade cue.
""".strip(),
        related=("buffett", "compounders", "economic_moat", "quality_growth", "buy_and_hold"),
        further_reading=(
            "Lee-Chin interviews on the five laws of wealth creation (Financial Post / Jamaica Observer).",
            "theschoolofhardknockz — Michael Lee-Chin, Monaco (Instagram reel DZsiUfMCJo5).",
        ),
    )
)


def lee_chin_tilt(info: dict[str, Any] | None) -> float:
    """Small [−1, 1] quality/hold tilt from Yahoo-style info. No ticker favoritism."""
    if not info:
        return 0.0

    def _f(key: str) -> float:
        try:
            v = float(info.get(key) or 0.0)
            if v != v:
                return 0.0
            return v
        except (TypeError, ValueError):
            return 0.0

    roe = _f("returnOnEquity")
    # Yahoo often stores 0.18 for 18%.
    if abs(roe) < 3:
        roe_pct = roe * 100.0
    else:
        roe_pct = roe
    de = _f("debtToEquity")
    # Yahoo D/E often 50 for 0.50
    if de > 5:
        de = de / 100.0
    pm = _f("profitMargins")
    if abs(pm) < 3:
        pm_pct = pm * 100.0
    else:
        pm_pct = pm
    score = 0.0
    if 12.0 <= roe_pct <= 80.0:
        score += 0.45
    elif roe_pct > 80.0:
        score += 0.15  # possibly accounting distortion
    if 0 <= de <= 1.5:
        score += 0.30
    elif de > 3.0:
        score -= 0.35
    if pm_pct >= 8.0:
        score += 0.25
    elif pm_pct < 0:
        score -= 0.20
    return max(-1.0, min(1.0, score))
