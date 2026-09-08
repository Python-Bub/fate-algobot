"""Beginner investing guide — narrative companion to deep chapters.

Maps the intro curriculum (value → growth → income → preferreds/REITs/
covered calls → quant/AI/ML) onto catalog topic_ids so
`./run_all.sh investing-book --beginner` can render a coherent book path.

Updated 2026 notes: PEG/GARP thresholds, DCF terminal-value dominance,
muni credit reality (not riskless), and ML's job: find subtle historical
price connections humans cannot see — under strict OOS discipline.
"""

from __future__ import annotations

from typing import Any


GUIDE_SECTIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "intro",
        "title": "Introduction",
        "body": """
Investing is one of the most important tools for growing long-term wealth in
order to achieve financial goals. This guide gives beginners a breakdown of
the major investing styles and how they work. Investing is not a way to
generate wealth overnight; it is a way to grow money over years. While it may
look like a simple path to earn money, not every investment will generate
profit — the point of this guide is to help beginners evaluate and weigh
different approaches before committing capital.

**2026 reality check:** brokers and margin rules keep changing (including
intraday buying power after classic PDT-style counting). That does not change
the beginner rule: long-term ownership of productive assets usually beats
frantic turnover. Treat paper trading as a systems lab, not proof of edge.
""".strip(),
        "topics": (),
    },
    {
        "id": "value",
        "title": "Value Investing",
        "body": """
### Deep Value & Intrinsic Value
Deep value buys unpopular stocks ignored by Wall Street at a steep discount to
estimated worth while the crowd sells. Intrinsic value is the true value of a
company based on assets, cash flow, and earnings. The margin of safety is the
buffer between intrinsic value and the price you pay — a fallback if the
estimate was slightly off.

Classic screens: historically low P/E, and P/B below one (price less than book
net assets). The hardest challenge is distinguishing a genuine bargain from a
**value trap** — a stock that stays cheap or goes bankrupt because the business
is broken. Prefer low debt and liquid assets that can convert to cash after a
rebound.

Intrinsic value is independent of the current quote. An asset is worth the
future cash it generates, discounted because a dollar tomorrow is usually worth
less than a dollar today. See the DCF card below; keep perpetual growth `g`
strictly below the discount rate `r` or the math breaks.

### Graham Investing & Net-Net Investing
Graham’s pillars: prices are noisy, so buy only when absurdly cheap; and
margins of safety are essential. Net-nets trade below Net Current Asset Value
(liquidation-style cushion): current assets minus total liabilities. A Graham
net-net typically requires NCAV at least ~1.5× market capitalization.

### Buffett Investing & Contrarian Investing
Buffett style buys wonderful businesses with durable competitive advantages
(moats) — high switching costs, network effects, intangible assets, cost
advantages — in industries you understand, and holds so compounding can work.
Contrarian investing buys when forced selling or temporary headlines crush the
price, but only when the long-term business is intact. Prove mathematically
that the crowd is wrong; do not buy a permanent impairment just because it is
down.

### Asset-Based Investing & Sum-of-the-Parts
Asset-based work focuses on present liquidation or hard-asset value and waits
for a catalyst that wakes the market up. Sum-of-the-parts values each segment of
a conglomerate, subtracts corporate debt, and buys when the parts exceed the
market price (conglomerate discount).

### Turnaround Investing & Special Situations
Turnarounds buy near-distress with a realistic survival plan: cut costs /
refinance / new leadership → operational refocus → recovery that brings capital
back. Prefer no large near-term debt maturities and a strong core product.
Special situations include spin-offs (forced institutional selling), merger
arbitrage (deal spread vs deal-break risk), and asset liquidations (market cap
below expected cash payout to shareholders).
""".strip(),
        "topics": (
            "deep_value",
            "intrinsic_value",
            "graham",
            "net_net",
            "buffett",
            "contrarian",
            "asset_based",
            "sum_of_the_parts",
            "turnaround",
            "special_situations",
        ),
    },
    {
        "id": "growth",
        "title": "Growth Investing",
        "body": """
### GARP & Quality Growth
Growth At a Reasonable Price refuses to overpay for expansion. PEG = (P/E) /
earnings growth rate; ~1 is fair for the growth you are buying, under 1 can be
discounted growth (context matters). Quality growth focuses on the business:
low debt, pricing power (stable high margins), and ROE often in the ~15–20%
zone (net income / equity).

### Compounders & Secular Growth
Compounders earn high returns on capital and reinvest profits (snowball). Look
for high ROIC (often ~15–20%+) and a real reinvestment runway. Secular growth
rides permanent habit or demographic shifts that are not just one economic cycle.

### Hypergrowth & Momentum Growth
Hypergrowth expands revenue at abnormal rates (~30–50%+), often young and
reinvesting so hard that near-term net profit is thin or zero. Momentum growth
rides psychology and trend — FOMO waves — not discounted cash flow.

### Disruptor & Innovation Investing
Disruptors attack inefficient industries with cheaper, simpler products for
ignored customers and often show high revenue growth with low near-term profit.
Innovation investing backs creators of new products, tech, or markets — sometimes
without needing to kill incumbents first.

### Growth Investing & Early-Stage Growth
Classic growth pays a high P/E for sales/earnings expected to outrun the
market’s forecast, seeking capital gains more than dividends and reinvesting
heavily. Early-stage growth is extreme: young firms with a working product and
customers — most fail; a few pay for the rest.
""".strip(),
        "topics": (
            "garp",
            "quality_growth",
            "compounders",
            "secular_growth",
            "hypergrowth",
            "momentum_growth",
            "disruptor",
            "innovation",
            "growth",
            "early_stage",
        ),
    },
    {
        "id": "income",
        "title": "Income, Bonds & Hybrids",
        "body": """
### Dividend Investing & Dividend Growth
Dividend investing collects cash from stable payers without needing the price
to moon. Dividend growth focuses on companies that raise payouts over time —
useful psychological ballast in drawdowns (though dividends are not a guarantee).

### Municipal Bonds & Bond Laddering
Municipal bonds fund state/local projects and often pay interest that is
federally tax-advantaged (sometimes state-tax free in-state). **They are not
riskless:** credit events, rate risk, and call/liquidity risk still exist.
Bond laddering spreads cash across maturities (e.g. equal slices into 1y–5y)
and rolls maturities so reinvestment can capture higher rates if yields rise.

### Preferred Shares & Preferred Stock Investing
Preferreds sit between bonds and common: fixed-ish dividends usually before
common, priority over common in liquidation, typically little/no vote. Useful
as an income sleeve; still junior to senior debt and often callable.

### REIT Income & Infrastructure Income
REITs own/manage real estate and must distribute most taxable income as
dividends — liquid property exposure without being the landlord. Infrastructure
income targets essential assets (pipelines, tolls, towers, utilities) where cash
comes from usage fees or regulated returns and can rise with inflation when
contracts allow.

### Covered Call Income & High-Yield Investing
Covered calls sell calls against stock you own: you collect premium and cap
upside at the strike. High-yield investing targets above-average payouts from
stocks/bonds/funds — and usually accepts higher principal risk; yield traps are
common when the distribution is unsustainable.
""".strip(),
        "topics": (
            "dividend",
            "dividend_growth",
            "municipal_bonds",
            "bond_laddering",
            "preferred_shares",
            "preferred_stock",
            "reit_income",
            "infrastructure_income",
            "covered_call_income",
            "high_yield",
        ),
    },
    {
        "id": "quant",
        "title": "Quantitative Investing",
        "body": """
### Artificial Intelligence Investing & Machine Learning Investing
AI investing uses models to read news, filings, transcripts, and speech at
scale and tweak portfolios faster than a human can. Oversight is mandatory:
hallucinations and misread headlines still happen. Treat AI as a research
accelerator and feature source, not an unsupervised portfolio manager.

Machine learning investing is the mathematics-first cousin of AI: it searches
historical prices and features for **subtle connections that are completely
invisible to regular humans** — nonlinear interactions, lag structures, and
regime-conditioned patterns no discretionary checklist would write by hand.
Self-improving systems adjust formulas so later trades can be sharper *if*
the signal survives out-of-sample tests.

**Most important:** ML’s job is finding those subtle historical price
connections humans cannot see. The failure mode is mistaking memorized noise
for alpha (leakage, look-ahead, overfit). Walk-forward validation, feature
parity live vs train, and risk caps on ML contribution keep the promise honest.

FATE path: engineered features → horizon models → hidden-pattern / regional
imbalance scans → calibrated ranks → fortress / day-trade / HFT risk gates —
never raw model output as unfiltered auto-size.

### Quant Investing & Factor Investing
Quant investing relies on math, data science, and algorithms instead of a
manager’s gut. The discipline: if a rule cannot be written in code or math, it
is superstition. Researchers hunt the market for repeatable hidden patterns.
Factor investing isolates traits (value, momentum, quality, size, low-vol, …)
that historically earned a premium and builds portfolios from those building
blocks rather than storytelling.

### Statistical Arbitrage & Risk Parity
Statistical arbitrage leans on mean reversion: when two related names drift
apart from their historical relationship, expect convergence — buy the laggard,
short (or underweight) the leader, with tight risk controls. Risk parity sizes
positions by risk contribution, not notional dollars: riskier sleeves get less
capital so each sleeve contributes more equal risk to the whole book.

### Enhanced Index & Automated Portfolio Management
An enhanced index still tracks a universe like the S&P 500 but weights by
chosen factors instead of market cap alone (cap-weighting forces you to own
more of whatever already got expensive). Automated portfolio management is a
rules engine that rebalances daily to the investor’s mandate — trimming losers
or drifting weights so the strategy stays on track.

### Algorithmic Trading & High-Frequency Trading (HFT)
Algorithmic trading encodes a strategy as software that reads public market
feeds and places orders on a schedule or signal — usable from minutes to days.
HFT is the speed extreme: huge order volume, microsecond latency, hunting tiny
imbalances and the bid–ask spread. Firms co-locate near exchanges to shave
nanoseconds. FATE’s HFT stack (OBI/tape) is the educational/paper cousin of that
idea — never confuse paper latency with co-located prop HFT.
""".strip(),
        "topics": (
            "ai_investing",
            "ml_investing",
            "quant",
            "factor",
            "smart_beta",
            "stat_arb",
            "risk_parity",
            "automated_portfolio",
            "algo_trading",
            "hft",
            "alt_data",
        ),
    },
    {
        "id": "trading",
        "title": "Trading Styles",
        "body": """
### Day Trading & Swing Trading
Day trading opens and closes within the same session — no overnight gap risk,
but fees, focus, and pattern-day-trader rules matter. Swing trading holds days
to weeks, capturing moves between support/resistance or post-catalyst drift
while accepting overnight and weekend gaps.

### Position Trading & Scalping
Position trading rides multi-week to multi-month trends or fundamental
inflections — closer to investing than to scalping. Scalping seeks many tiny
profits from tight spreads and rapid execution; edge per trade is small, so
costs and discipline dominate.

### Trend Following & Mean Reversion
Trend following buys strength / sells weakness and rides continuation after
a confirmed move. Mean reversion assumes temporary overshoots snap back toward
averages or peers — useful in ranges, dangerous in strong trends.

### Range Trading & Breakout Trading
Range trading buys support and sells resistance while the channel holds.
Breakout trading enters when price clears defined resistance (or support) with
volume, betting on continuation — false breakouts require pre-planned stops.
""".strip(),
        "topics": (
            "day_trading",
            "swing_trading",
            "position_trading",
            "scalping",
            "trend_following",
            "mean_reversion",
            "range_trading",
            "breakout",
            "news_trading",
            "event_driven",
        ),
    },
    {
        "id": "derivatives",
        "title": "Derivatives",
        "body": """
### Options, Calendar Spreads, Straddles & Strangles
Options are contracts: calls (right to buy) and puts (right to sell) on 100
shares, with ATM / ITM / OTM strikes. Buyers pay premium and cap risk; sellers
collect premium and cap profit. Calendar spreads sell near-term vs buy
longer-dated same strike to harvest theta. Straddles buy ATM call+put for a
big move; strangles buy OTM call+put cheaper with a wider needed move.

### Credit/Debit Spreads, Butterflies & Iron Condors
Verticals define a zone: credit spreads collect premium if price stays away
from the short strike; debit spreads pay net debit for a directional move.
Butterflies and iron condors target a range with defined max loss.

### Covered Calls, Protective Puts, Forwards & Swaps
Covered calls sell calls against stock you own. Protective puts insure a
floor. Forwards are private future purchases; swaps exchange cash-flow legs
(rates, etc.) — mostly institutional hedging, not a retail day-trade toy.
""".strip(),
        "topics": (
            "options",
            "calendar_spreads",
            "straddles",
            "strangles",
            "credit_spreads",
            "debit_spreads",
            "butterfly",
            "iron_condors",
            "covered_calls",
            "protective_puts",
            "forwards",
            "swaps",
        ),
    },
    {
        "id": "shorts",
        "title": "Short Selling",
        "body": """
### Short Selling & Inverse ETFs
Shorting borrows shares, sells them, and hopes to buy back cheaper. Risk is
uncapped if the price rips. Inverse ETFs express a down-bet with cash and a
capped loss (the premium you paid) — still not a hold-forever product.

### Long-Short, Market Neutral, Pairs & Bear Sleeves
Long-short buys expected winners and shorts expected losers. Market-neutral
balances notionals so the book is about stock-picking, not the S&P. Pair
trading fades a stretched relationship. Bear sleeves rotate to defensive
names or inverse products when the cycle turns — not a personality.
""".strip(),
        "topics": (
            "short_selling",
            "inverse_etfs",
            "long_short",
            "market_neutral",
            "pair_trading",
            "bear_strategies",
        ),
    },
    {
        "id": "macro",
        "title": "Macro",
        "body": """
### Top-Down & Bottom-Up
Top-down starts with inflation, rates, and the cycle, then picks sectors, then
stocks. Bottom-up ignores the weather and asks whether *this* business can
compound anyway. FATE uses both: macro as a sleeve tilt, models as the
company-level engine.

### Currency, Commodities, Rates, Cycle, Inflation & Deflation
FX follows relative growth and rate differentials. Commodities have no cash
flow — supply lags and inflation hedges (gold, oil, wheat) matter. Rate
investing positions for hikes/cuts. Business-cycle rotation moves from
cyclicals to defensives. Inflation needs pricing power and TIPS/real assets;
deflation punishes high fixed costs and high debt.
""".strip(),
        "topics": (
            "top_down",
            "bottom_up",
            "currency",
            "commodity_macro",
            "interest_rate",
            "business_cycle",
            "inflation",
            "deflation",
        ),
    },
    {
        "id": "alternative",
        "title": "Alternative",
        "body": """
Angel/seed/VC/PE and crowdfunding are mostly *knowledge* sleeves for FATE —
illiquid, accredited, not a paper-Alpaca ticket. Crypto and stablecoins are
high-vol speculative rails; hedge funds vs mutual funds differ by mandate and
fees. Do not confuse a chapter with a live order.
""".strip(),
        "topics": (
            "angel_investing",
            "venture_capital",
            "private_equity",
            "seed_investing",
            "crowdfunding",
            "crypto",
            "stablecoins",
            "hedge_funds",
            "mutual_funds",
        ),
    },
    {
        "id": "passive",
        "title": "Passive",
        "body": """
Index and ETF investing buy the market instead of trying to beat it. Dollar-cost
average on a schedule; buy-and-hold lets compounding work. Lazy portfolios and
target-date funds keep the mix simple. Core-satellite puts most capital in the
index and a satellite in active names — closest to FATE fortress (core) plus
research tilts (satellite), with a hard single-name cap.
""".strip(),
        "topics": (
            "index_investing",
            "etf_investing",
            "dca",
            "buy_and_hold",
            "lazy_portfolios",
            "target_date",
            "core_satellite",
        ),
    },
    {
        "id": "advanced",
        "title": "Advanced",
        "body": """
Merger and convertible arb harvest spreads with deal-break risk. Strategic vs
tactical allocation is the policy mix vs a timed overweight. Portfolio
optimization and tax-loss harvesting are after-the-rank plumbing. Thematic
baskets and sector rotation need a real cycle or structural trend, not a
headline. Leverage is a short-hold tool with stops — not a way to look fully
invested. Multi-asset mixes stocks, bonds, and real assets so they do not all
crash together.
""".strip(),
        "topics": (
            "merger_arb",
            "convertible_arb",
            "strategic_aa",
            "tactical_aa",
            "portfolio_optimization",
            "tax_loss_harvesting",
            "thematic_investing",
            "sector_rotation",
            "leveraged_investing",
            "multi_asset",
        ),
    },
    {
        "id": "lee_chin",
        "title": "Lee-Chin: Five Laws of Wealth Creation",
        "body": """
From Michael Lee-Chin's published interviews (the Instagram reel is a
theschoolofhardknockz conversation in Monaco — the clip is login-walled; the
laws are the documented content):

1. Own a **few** high-quality businesses.
2. Understand how they make money (circle of competence).
3. They must sit in **strong long-term growth industries**.
4. Use other people's money *prudently* — not 4× margin as a personality.
5. Hold for the long run so the business compounds.

Three P's: predict, plan, persevere. A stock is ownership of a business, not a
trading chit. Concentration beats “die-worse-ify.” In FATE that is the 10%
single-name cap plus overnight hold on fortress/weekly/longterm — we still
**train the whole universe**; we just do not pretend 80 stubs is a strategy.
""".strip(),
        "topics": ("lee_chin_five_laws", "buffett", "compounders", "economic_moat", "buy_and_hold"),
    },
    {
        "id": "identity_memory",
        "title": "Ticker identity, memory, and powerful people",
        "body": """
Companies change clothes: Facebook became Meta (FB→META), Square became Block
(SQ→XYZ), Fiserv (FISV→FI), DWAC became DJT. A spin-off (eBay/PayPal) splits
one listing into two that both keep trading — the parent is not the child.
A cash takeout (TMHC into Berkshire cash) is **dead money**: do not buy a
listing that no longer exists. Stock-deal targets are not the acquirer's
price history (Activision bars are not Microsoft).

The algorithm keeps an append-only **memory** per issuer (renames, spin-offs,
takeouts, power-people hits) and a short **summary** the ranker can read.

People with power (presidents, Fed chairs, well-followed CEOs) are ingested
only when (1) the speaker is named, (2) a cashtag or unambiguous company name
(or a two-cue rule like Elon+Cybertruck→Tesla) appears, and (3) there is a
buy/sell verb or a strong phrase (“wanna get rich, buy this”). Sector vibes
alone never pick a winner. Historical 5-day excess return vs SPY *calibrates*
each speaker: until there are enough samples we use a modest prior, not
“they are always right.”
""".strip(),
        "topics": ("lee_chin_five_laws", "special_situations", "sentiment", "ai_investing"),
    },
)


# Compact formula card for the beginner text (matches the user's DCF block).
DCF_CARD = {
    "intrinsic_value": r"IV = \sum_{t=1}^{n} \frac{CF_t}{(1+r)^t} + \frac{TV}{(1+r)^n}",
    "terminal_value": r"TV = \frac{CF_n (1+g)}{r - g}",
    "peg": r"PEG = \frac{P/E}{g_{\%}}",
    "roe": r"ROE = \frac{\text{Net Income}}{\text{Equity}}",
    "roic": r"ROIC = \frac{NOPAT}{\text{Invested Capital}}",
    "ncav": r"NCAV = \text{Current Assets} - \text{Total Liabilities}",
    "notes_2026": (
        "Use r roughly 8–12% for stable businesses (higher for volatile growers).",
        "Keep perpetual g at ~2–3% (≤ long-run nominal GDP); never g ≥ r.",
        "Terminal value often drives 60–80% of a DCF — always sensitivity-test r and g.",
        "PEG ≤ 1 historically attractive; 1.0–1.5 fair for quality; >1.5 often rich — "
        "useless for cyclicals or near-zero earnings.",
        "Cross-check DCF with PEG/multiples; one method alone is precise but often wrong.",
        "Municipal bonds are tax-advantaged, not riskless — check credit, duration, and liquidity.",
        "ML edge = subtle historical price links humans miss; only trust what survives OOS / walk-forward.",
        "Stat-arb needs a real cointegration/relationship test — two random stocks are not a pair.",
        "HFT edge is latency + microstructure; retail 'HFT' without co-lo is just fast algo trading.",
        "Risk parity equalizes risk, not dollars — a 2% vol sleeve can be larger than a 20% vol sleeve.",
    ),
}


def render_markdown(*, deep: bool = False) -> str:
    """Render the beginner path; optionally append deep chapter markdown."""
    lines = [
        "# Beginner Investing Guide",
        "",
        "*FATE_AlgoBot curriculum — strategies map to deep encyclopedia chapters.*",
        "",
    ]
    for sec in GUIDE_SECTIONS:
        lines.append(f"## {sec['title']}")
        lines.append("")
        lines.append(sec["body"])
        lines.append("")
        if sec["topics"]:
            lines.append("### Deep chapters")
            for tid in sec["topics"]:
                lines.append(f"- `{tid}`")
            lines.append("")

    lines.append("## Core formulas (quick card)")
    lines.append("")
    lines.append("### Intrinsic value (DCF)")
    lines.append(f"$${DCF_CARD['intrinsic_value']}$$")
    lines.append("")
    lines.append("### Terminal value (Gordon)")
    lines.append(f"$${DCF_CARD['terminal_value']}$$")
    lines.append("")
    lines.append("### PEG (GARP)")
    lines.append(f"$${DCF_CARD['peg']}$$")
    lines.append("")
    lines.append("### ROE / ROIC / NCAV")
    lines.append(f"$${DCF_CARD['roe']}$$")
    lines.append("")
    lines.append(f"$${DCF_CARD['roic']}$$")
    lines.append("")
    lines.append(f"$${DCF_CARD['ncav']}$$")
    lines.append("")
    lines.append("### 2026 practice notes")
    for n in DCF_CARD["notes_2026"]:
        lines.append(f"- {n}")
    lines.append("")

    if deep:
        from investing.knowledge import get_chapter

        lines.append("---")
        lines.append("")
        lines.append("# Deep chapters (linked topics)")
        lines.append("")
        seen: set[str] = set()
        for sec in GUIDE_SECTIONS:
            for tid in sec["topics"]:
                if tid in seen:
                    continue
                seen.add(tid)
                ch = get_chapter(tid)
                if ch is None:
                    lines.append(f"## `{tid}` — *(missing chapter)*")
                    lines.append("")
                    continue
                lines.append(ch.render_markdown())
                lines.append("")
    return "\n".join(lines)


def coverage_check() -> dict[str, Any]:
    from investing.knowledge import get_chapter

    missing = []
    ok = []
    for sec in GUIDE_SECTIONS:
        for tid in sec["topics"]:
            if get_chapter(tid) is None:
                missing.append(tid)
            else:
                ok.append(tid)
    return {"linked": len(ok), "missing": missing, "sections": len(GUIDE_SECTIONS)}
