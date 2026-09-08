"""Growth investing — deep chapters (1/1 through the family)."""

from __future__ import annotations

from investing.knowledge import DeepChapter, FormulaSpec, register

_F = FormulaSpec

register(
    DeepChapter(
        topic_id="growth",
        title="Growth Investing",
        family="growth",
        philosophy="""
Growth investing is the conviction that tomorrow’s earnings power matters more than
today’s price tag. You pay a premium for businesses expanding revenue, margins, and
market share faster than the economy — betting that compounding fundamentals will
pull the stock higher even if the starting multiple looks rich. The philosophy
rests on a simple asymmetry: a great company can grow into its valuation, but a
mediocre one rarely grows out of a bad business.

Unlike pure value, growth accepts uncertainty about the distant future in exchange
for exposure to nonlinear upside when a franchise scales. The edge is not
guessing the next hot ticker; it is distinguishing durable, reinvestment-driven
expansion from one-off spikes, accounting gimmicks, or TAM slides that never
convert to cash. Growth without quality is speculation; growth with moats and
disciplined capital allocation is how most long-run wealth in equities has been
created outside deep-value cycles.


Wall Street’s quarterly obsession cuts both ways: short-term misses create entry points in long-duration growers, but also tempt management toward accounting games. The disciplined growth investor underwrites five-year per-share economics, not one guide-down.""".strip(),
        how_it_works="""
Practitioners start with the growth engine: where does incremental revenue come
from (new customers, pricing, geography, product lines), and can the company
reinvest at attractive returns? Screen for above-market revenue and EPS growth,
then stress-test sustainability — customer concentration, competitive response,
margin trajectory, and balance-sheet capacity to fund growth without dilution.

Workflow: (1) identify categories with long runways, (2) filter for accelerating
or consistently high growth rates, (3) compare valuation (P/E, EV/Sales, PEG) to
growth quality, (4) size positions for volatility and thesis risk, (5) monitor
whether growth is re-accelerating or decelerating — the critical inflection for
multiples. Growth portfolios often cluster in technology, healthcare, and
consumer brands, but the method applies anywhere unit economics improve with scale.

Growth thrives in falling-rate, risk-on regimes and suffers when discount rates
rise or when the market punishes “long duration” earnings. Diversification across
several growth engines reduces single-name blow-ups from missed quarters.


Position sizing should reflect estimate dispersion — wider error bars mean smaller weights. Many professionals maintain a core of proven growers and a satellite book for higher-beta names, rebalancing when relative performance skews risk beyond mandate.""".strip(),
        formulas=(
            _F(
                "Price-to-earnings (growth context)",
                r"P/E = \frac{P}{EPS}",
                "High P/E is acceptable only when earnings growth is fast and durable enough to compress the multiple over time.",
            ),
            _F(
                "PEG ratio",
                r"PEG = \frac{P/E}{\text{EPS growth}\%}",
                "Price/earnings divided by EPS growth expressed as a percent (15 for 15%). Lower PEG suggests growth is not fully priced in.",
                "investing.formulas.growth.peg_ratio",
            ),
            _F(
                "Revenue growth (YoY)",
                r"g_{rev} = \frac{Rev_t - Rev_{t-1}}{Rev_{t-1}}",
                "Top-line acceleration often leads earnings; watch for price/volume mix and organic vs acquisition-driven growth.",
            ),
            _F(
                "Reinvestment link",
                r"g \approx ROIC \times \text{Reinvestment Rate}",
                "Sustainable growth requires reinvesting at returns above the cost of capital — not financial engineering alone.",
            ),
        ),
        screens=(
            "Revenue and EPS growth above market/GDP for 3+ years (or clear inflection)",
            "Gross margin stable or expanding as scale increases",
            "Manageable debt; FCF positive or credible path as model matures",
            "PEG or P/E vs growth not extreme vs history and peers",
            "Insider ownership and sane stock-based compensation",
            "Avoid one-customer / one-product binary risk without sizing discipline",
        ),
        traps=(
            "Growth trap: high multiple on decelerating growth (multiple compression)",
            "Acquisition roll-ups masking organic stagnation",
            "Stock-based comp diluting per-share growth",
            "TAM fantasy without unit economics proof",
            "Cyclical peak mistaken for structural growth",
        ),
        catalysts=(
            "Earnings beats and guidance raises resetting the growth narrative",
            "New product cycles or geographic expansion",
            "Operating leverage as fixed costs are absorbed",
            "Index inclusion and institutional discovery",
        ),
        fate_hook="Growth blend in `investing.integrate.book_rank_boost` uses `investing.formulas.growth` (PEG, GARP, hypergrowth, quality, compounder scores) with `BOOK_W_GROWTH`.",
        related=("garp", "quality_growth", "compounders", "hypergrowth", "secular_growth"),
        further_reading=(
            "Philip Fisher — Common Stocks and Uncommon Profits",
            "Peter Lynch — One Up on Wall Street",
            "McKinsey — Valuation (growth and reinvestment chapters)",
        ),
    )
)

register(
    DeepChapter(
        topic_id="garp",
        title="GARP (Growth at a Reasonable Price)",
        family="growth",
        philosophy="""
GARP sits between pure growth zeal and deep value austerity: you want companies
growing faster than the market, but you refuse to pay unlimited multiples for that
growth. Peter Lynch popularized the idea that a stock trading at a P/E near its
earnings growth rate — a PEG near 1 — offers a reasonable trade-off between
quality of growth and price paid. Pay PEG well above 1 and you need perfection;
pay PEG below 1 and the market may be underestimating durability or speed of
compounding.

GARP is explicitly anti-momentum-at-any-price. It acknowledges that growth stocks
correct violently when estimates slip, so valuation discipline is the margin of
safety. The philosophy favors mid-cap growers with visible runway, understandable
business models, and earnings you can underwrite — not lottery tickets priced for
dominance before dominance arrives.


Lynch’s framework assumes you can estimate growth within a reasonable band — when estimates are wildly dispersed, PEG loses meaning. Cross-sector GARP requires normalization: a utility at PEG 1 is not the same risk as a software name at PEG 1.""".strip(),
        how_it_works="""
Start with a growth screen: EPS growth (historical and forward) above a hurdle
(often 10–15%+). Compute PEG = P/E ÷ EPS growth% (growth as percent, not decimal).
Classic GARP framing: PEG ≤ 1 is attractive; PEG ≈ 1–1.5 is often fair for quality;
PEG > 1.5 demands exceptional moat evidence. Cross-check with cash flow, debt, and
whether growth is organic.

**2026 caveat:** PEG breaks on cyclicals and near-zero earnings; for software,
prefer adjusted operating EPS (SBC / amortization) so PEG is not fake-cheap.
AI-capex hypergrowth names can print “reasonable” PEGs on trailing growth while
still carrying cycle risk — treat those as partial fits, not automatic buys.
Cross-check PEG with a simple DCF range; agreement raises confidence.

Lynch also looked for P/E below the growth rate with a stable base business — the
“fast grower” bucket. Combine PEG with quality filters (ROE, margins) to avoid
cheap PEG from cyclical earnings peaks. Rebalance when PEG expands after a rally
even if the story remains intact — price is part of the thesis.

GARP tends to work in markets transitioning from value to growth leadership and
when investors over-discount temporary slowdowns in otherwise durable franchises.


Pair PEG with balance-sheet quality: a leveraged cyclical at PEG 0.7 ahead of peak earnings will look expensive within two quarters. Maintain a watchlist of names transitioning from expensive to fair PEG on estimate cuts — often the wrong time to average down without a catalyst.""".strip(),
        formulas=(
            _F(
                "PEG ratio (exact)",
                r"PEG = \frac{P/E}{\text{EPS growth}\%}",
                "Divide trailing or forward P/E by expected EPS growth expressed as a percentage (e.g. P/E 20 and 20% growth → PEG 1.0).",
                "investing.formulas.growth.peg_ratio",
            ),
            _F(
                "GARP threshold",
                r"PEG \le 1 \Rightarrow \text{growth at reasonable price}",
                "Lynch-style rule of thumb: at PEG ≤ 1 you are not overpaying for each unit of growth — subject to quality and duration checks.",
            ),
            _F(
                "GARP score (FATE)",
                r"score \propto \frac{PEG_{\max} - PEG}{PEG_{\max}}",
                "Positive when PEG < peg_max (default 1.0); negative when growth is expensive vs earnings multiple.",
                "investing.formulas.growth.garp_score",
            ),
            _F(
                "Forward vs trailing PEG",
                r"PEG_f = \frac{P/E_{forward}}{g_{forward}\%}",
                "Forward PEG aligns price with next-year expectations; trailing PEG uses realized growth — triangulate both.",
            ),
        ),
        screens=(
            "EPS growth ≥ 10–15% (3-yr CAGR or credible forward)",
            "PEG ≤ 1.0 on forward estimates (≤ 1.2 with wide moat exception)",
            "P/E below historical peak and below pure-growth peers if growth similar",
            "Debt manageable; FCF supports growth capex",
            "No imminent patent cliff / major customer loss",
            "Insider alignment; avoid serial diluters",
        ),
        traps=(
            "PEG illusion from peak-cycle earnings (denominator inflated)",
            "One-year growth spike from easy comps",
            "Using broker hype growth rates without haircut",
            "Ignoring balance sheet — cheap PEG on levered cyclical",
            "PEG undefined when growth ≤ 0 (shows as expensive/avoid)",
        ),
        catalysts=(
            "Estimate revisions upward while PEG still ≤ 1",
            "Multiple expansion as market recognizes sustained GARP profile",
            "Share repurchase when PEG attractive",
            "Segment disclosure clarifying faster-growing unit",
        ),
        fate_hook="`garp_score` and `peg_ratio` in `investing.formulas.growth`; blended at 40% weight inside growth family in `investing.integrate.book_rank_boost` (PEG logged in meta).",
        related=("growth", "quality_growth", "compounders", "peg", "buffett"),
        further_reading=(
            "Peter Lynch — One Up on Wall Street (PEG / fast growers)",
            "Martin Zweig — Winning on Wall Street",
        ),
    )
)

register(
    DeepChapter(
        topic_id="hypergrowth",
        title="Hypergrowth Investing",
        family="growth",
        philosophy="""
Hypergrowth targets companies expanding revenue at exceptional rates — often 40%,
60%, or 100%+ year over year — usually by capturing a new category, riding viral
adoption, or land-grabbing in winner-take-most markets. The philosophy accepts
near-term profit sacrifice: management reinvests every marginal dollar into
acquisition, R&D, and scale because the cost of losing share exceeds the cost of
burning cash. You are buying optionality on a future dominant franchise, not
current earnings.

The payoff can be extraordinary, but the base rate of failure is high. Many
hypergrowers never reach profitability; others face brutal competition once the
TAM slide ends. Position sizing and portfolio-level diversification are not
optional — they are part of the strategy. Hypergrowth is for investors who can
underwrite product-market fit, competitive dynamics, and funding runway, not for
those who need smooth drawdowns.


Capital markets alternate between funding hypergrowth generously and shutting the window overnight — your thesis must survive both. Treat each hypergrowth position as a venture bet with public liquidity: define upfront what proof would invalidate the story.""".strip(),
        how_it_works="""
Identify hypergrowth via top-line acceleration: sequential revenue growth,
billings/backlog if SaaS, same-store sales if consumer, subscriber net adds if
platform. Earnings may be negative — focus on unit economics (CAC/LTV, gross
margin after scale, contribution margin by cohort). Map the TAM and current
penetration; hypergrowth slows mathematically as the base grows.

Entry often follows product-market fit proof (retention, NPS, declining CAC) rather
than first revenue dollar. Exit rules matter: deceleration below a threshold,
competitive share loss, or rising cash burn without funding access. Public
hypergrowers re-rate violently on guidance — expect 30–50% drawdowns in names
that still work long term.

Hypergrowth clusters in software, biotech (revenue or pipeline events), e-commerce,
and disruptive hardware. Pair with secular tailwinds when possible.


Use scenario tables (bear/base/bull) for revenue and cash need rather than a single DCF. When secondary offerings come at premium, that validates demand; at discount, it signals stress. Track insider selling versus scheduled 10b5-1 plans to separate routine from abandonment.""".strip(),
        formulas=(
            _F(
                "Revenue growth rate",
                r"g_{rev} = \frac{Rev_t - Rev_{t-1}}{Rev_{t-1}}",
                "Hypergrowth typically means sustained high double-digit or triple-digit top-line expansion.",
            ),
            _F(
                "Rule of 40 (SaaS heuristic)",
                r"R40 = g_{rev}\% + \text{FCF margin}\%",
                "Growth% plus FCF margin ≥ 40 is a common SaaS health check; hypergrowers often trade on growth alone early.",
            ),
            _F(
                "Hypergrowth score (FATE)",
                r"score = f(g_{rev}, g_{earn})",
                "Composite of revenue and earnings growth (tanh-scaled) in [-1, 1] for book rank boost.",
                "investing.formulas.growth.hypergrowth_score",
            ),
            _F(
                "Burn multiple",
                r"Burn\ Multiple = \frac{\text{Net Burn}}{\text{Net New ARR}}",
                "Efficiency of growth spend; lower is better when profitability is deferred.",
            ),
        ),
        screens=(
            "Revenue growth ≥ 40% YoY (or category-leading acceleration)",
            "Gross margin path credible toward scale economics",
            "Cash runway ≥ 18–24 months or access to capital markets",
            "Retention / cohort data support land-and-expand thesis",
            "TAM large enough to justify current valuation if share gains continue",
            "Competitive moat forming (network, data, switching costs)",
        ),
        traps=(
            "Growth purely from discounting / unsustainable CAC",
            "Covid or one-time pull-forward disguised as structural hypergrowth",
            "Dilution treadmill in unprofitable issuers",
            "Multiple compression when growth decelerates from 80% to 40% — still ‘fast’ but punished",
            "Regulatory or platform-risk (app store, reimbursement) ignored",
        ),
        catalysts=(
            "Beat-and-raise quarters confirming TAM capture",
            "Operating leverage inflection (first profitable quarter)",
            "Strategic partnership or distribution unlock",
            "Index inclusion after profitability milestone",
        ),
        fate_hook="`hypergrowth_score` in `investing.formulas.growth`; 20% weight in growth blend inside `investing.integrate.book_rank_boost` using Yahoo revenue/earnings growth.",
        related=("early_stage", "disruptor", "innovation", "secular_growth", "growth"),
        further_reading=(
            "Bessemer — State of the Cloud / Cloud 100 metrics",
            "Revenue growth and unit economics playbooks (SaaS)",
        ),
    )
)

register(
    DeepChapter(
        topic_id="momentum_growth",
        title="Momentum Growth",
        family="growth",
        philosophy="""
Momentum growth fuses two persistent anomalies: stocks with strong recent price
trends tend to keep outperforming in the medium term, and companies with
accelerating fundamentals tend to attract capital and estimate revisions. The
philosophy is not to chase random spikes — it is to own leaders that the market
is already rewarding because earnings, guidance, and relative strength align.
You ride the wave while it confirms; you exit when momentum breaks or growth
decelerates.

This style accepts looking ‘late’ by traditional value standards. The edge comes
from systematic discipline: predefining entry (breakouts, 52-week highs with
fundamental filter) and exit (moving averages, relative strength deterioration)
so emotion does not turn winners into round-trips. Momentum growth fails in
violent regime shifts — rate shocks, growth-to-value rotations — when prior
leaders suffer synchronized drawdowns.


Momentum is fragile when liquidity dries up — crashes tend to hit prior winners hardest in risk-off episodes. The discipline is to respect stops and trend breaks even when fundamentals still look fine on paper; price is telling you something about discount rates or crowding.""".strip(),
        how_it_works="""
Build a universe of growth names (positive estimate revisions, revenue/EPS growth
above median). Rank by price momentum: 6–12 month return skipping last month
(12-1), or distance from 52-week high. Enter top quintile with liquidity and
risk controls; rebalance monthly or on signal. Overlay fundamental growth so you
avoid low-quality junk rallies.

Combine with earnings drift: post-earnings announcement drift often extends
momentum after beats. Use stops or trend filters — momentum is long volatility
in crashes. Pair with position limits per sector to avoid all-in software beta.

Academic and practitioner evidence supports cross-sectional momentum; combining
with growth reduces some ‘junk momentum’ exposure. Works best in trending,
liquidity-rich markets; mean-reverting chop destroys Sharpe.


Implement rebalance rules monthly or weekly to avoid over-trading, but enforce hard exits when momentum rank falls below median. Combine with earnings-date awareness — gap risk around prints can overwhelm a smooth momentum path. Capacity limits matter: illiquid small caps cannot absorb large momentum flows.""".strip(),
        formulas=(
            _F(
                "Momentum return (12-1)",
                r"Mom_{12-1} = \frac{P_{t-21}}{P_{t-252}} - 1",
                "Return over ~12 months skipping the most recent ~month to reduce short-term reversal noise.",
                "analytics/hedge_fund_stack.py",
            ),
            _F(
                "Relative strength",
                r"RS = \frac{P}{P_{52w,\max}}",
                "Price as fraction of 52-week high; leaders often cluster near highs before breakdown.",
            ),
            _F(
                "PEG + momentum (conceptual)",
                r"Score = w_m \cdot Mom + w_g \cdot (-PEG)",
                "Blend trend with reasonable growth price — avoid chasing expensive decelerators.",
            ),
        ),
        screens=(
            "12-1 momentum top decile within growth universe",
            "Price within 10–15% of 52-week high (or fresh breakout on volume)",
            "EPS/revenue growth positive and not decelerating sharply",
            "Above 200-day moving average (optional trend filter)",
            "Liquidity: ADV supports entry/exit without excessive impact",
        ),
        traps=(
            "Momentum without fundamentals — meme / story stocks",
            "Climax tops: parabolic move + exhaustion gap",
            "Crowded trades unwind synchronously",
            "Ignoring transaction costs and taxes on high turnover",
            "Rate regime change crushing long-duration growth leaders",
        ),
        catalysts=(
            "Earnings beat extending estimate revision cycle",
            "Breakout on volume after consolidation",
            "Sector rotation into growth leadership",
            "Index rebalancing flows into rising weights",
        ),
        fate_hook="Momentum proxy (`mom_12_1` from price history) feeds quant factor tilt in `investing.integrate`; growth formulas complement when `BOOK_USE_MOMENTUM` enabled. Catalog links `momentum_return` in hedge fund stack.",
        related=("growth", "garp", "quant", "technical_analysis", "quality_growth"),
        further_reading=(
            "Jegadeesh & Titman — momentum literature",
            "Cliff Asness — factor momentum frameworks",
        ),
    )
)

register(
    DeepChapter(
        topic_id="quality_growth",
        title="Quality Growth",
        family="growth",
        philosophy="""
Quality growth rejects the false choice between ‘cheap and junky’ and ‘fast and
fragile.’ It seeks businesses that grow at above-average rates while earning high
returns on capital, maintaining durable margins, and carrying modest leverage.
The philosophy mirrors Buffett’s evolution toward wonderful companies — but keeps
a growth investor’s focus on reinvestment runway rather than cigar-butt prices.

High-quality growers compound through cycles: they fund R&D and acquisitions from
internal cash, survive recessions without emergency dilution, and widen moats while
weaker competitors retrench. You pay more than deep value for this resilience, but
you avoid many growth traps where revenue rises while per-share value stagnates.
Quality is the filter that turns growth from a lottery into a compounding engine.


Quality is slow-burn alpha: it often lags in speculative bubbles and shines when balance sheets matter again. The investor accepts moderate headline growth in exchange for sleep — knowing that a 12% grower with 25% ROIC may create more wealth than a 30% grower burning cash.""".strip(),
        how_it_works="""
Screen for growth (revenue/EPS CAGR) plus quality proxies: ROE/ROIC above cost
of capital, stable or rising gross margins, low-to-moderate debt/equity, consistent
FCF conversion. Penalize accounting red flags (receivables growing faster than
revenue, frequent ‘adjusted’ metrics). Prefer businesses where growth comes from
reinvestment at high incremental ROIC, not from price cuts or leverage.

Hold through volatility when quality metrics intact; sell when moat erodes (margin
compression without explanation, ROIC trending toward WACC, reckless M&A). Quality
growth often overlaps GARP when PEG is reasonable — wonderful growth at a foolish
price still hurts.

Works across sectors: healthcare franchises, industrial technology, consumer
staples with innovation pipelines, and software with high retention.


Build a quality scorecard updated quarterly: ROIC trend, receivables/revenue, SBC as % of revenue, and net debt trajectory. When two metrics deteriorate simultaneously, downgrade even if the story sounds intact. Quality growth pairs naturally with dividend initiators — a sign of cash confidence without abandoning reinvestment.""".strip(),
        formulas=(
            _F(
                "Return on equity",
                r"ROE = \frac{\text{Net Income}}{\text{Equity}}",
                "Sustained high ROE with moderate leverage signals durable economics.",
            ),
            _F(
                "Quality growth score (FATE)",
                r"score = f(ROE, PM, D/E, g_{rev})",
                "Blends profitability, margins, leverage, and revenue growth into [-1, 1].",
                "investing.formulas.growth.quality_growth_score",
            ),
            _F(
                "FCF conversion",
                r"FCF\ Conv = \frac{FCF}{Net\ Income}",
                "Quality growers convert earnings to cash consistently (> 0.8 typical target).",
            ),
            _F(
                "Reinvestment rate",
                r"RR = \frac{\text{Net CapEx} + \Delta WC}{NOPAT}",
                "High RR only valuable when ROIC on reinvestment stays elevated.",
            ),
        ),
        screens=(
            "Revenue growth above sector median 3+ years",
            "ROE/ROIC consistently above 15% (sector-adjusted)",
            "Debt/equity below peer median; interest coverage comfortable",
            "Gross margin stable or expanding",
            "FCF positive and growing with earnings",
            "Management capital allocation track record (buybacks at fair prices, disciplined M&A)",
        ),
        traps=(
            "Peak-cycle ROE on cyclicals mistaken for quality",
            "Low debt because business cannot support leverage (weak, not conservative)",
            "Growth from acquisitions destroying ROIC",
            "Overpaying for quality — no margin of safety left",
        ),
        catalysts=(
            "Share gains during competitor distress",
            "New product line extending reinvestment runway",
            "Multiple re-rating when market rewards quality in risk-off periods",
            "Dividend initiation without sacrificing growth capex",
        ),
        fate_hook="`quality_growth_score` in `investing.formulas.growth`; 20% of growth blend in `investing.integrate.book_rank_boost` (ROE, margins, debt, revenue growth from Yahoo).",
        related=("compounders", "buffett", "garp", "growth", "economic_moat"),
        further_reading=(
            "Pat Dorsey — The Little Book That Builds Wealth",
            "Joel Greenblatt — The Little Book That Still Beats the Market (quality + value)",
        ),
    )
)

register(
    DeepChapter(
        topic_id="compounders",
        title="Compounders",
        family="growth",
        philosophy="""
Compounders are the holy grail of long-horizon equity investing: businesses that
reinvest a large portion of earnings at high incremental returns for many years,
creating wealth through time rather than through a single catalyst or re-rating.
The philosophy treats the stock as a partial ownership stake in a cash-generating
machine that you rarely trade. Volatility is noise; moat erosion and capital
misallocation are the real sell signals.

Unlike event-driven or hypergrowth strategies, compounders prioritize duration
and predictability. You accept moderate top-line growth if ROIC is exceptional and
reinvestment opportunities remain. Low payout ratios are a feature — management
is keeping fuel in the tank. The mental model is exponential: small differences in
reinvestment rate and ROIC compound into vast per-share value gaps over decades.


The hardest compounder decision is when to sell: never is wrong if the moat breaks, always is wrong if you overpay at entry. Many wealth outcomes come from doing nothing for a decade — which requires emotional design (position size, account type) not just intellectual conviction.""".strip(),
        how_it_works="""
Identify compounders via sustained high ROE/ROIC, long runway for reinvestment
(same-store growth + new markets + adjacencies), and management that allocates
capital rationally (internal projects first, then buybacks when cheap, avoid
value-destroying empire building). Payout ratio stays low to moderate; dividend
growth may exist but is not the primary return driver.

Hold through 20–30% drawdowns if fundamentals intact. Add on weakness when
valuation becomes attractive vs historical range. Monitor incremental ROIC on new
investments — the first sign of maturity is when reinvestment returns approach
WACC and cash piles up without productive use.

Classic compounders span consumer brands, payment networks, industrial software,
and healthcare equipment — anywhere switching costs and scale advantages persist.


Track incremental ROIC on new investments via segment disclosure when available. When excess cash piles up with no reinvestment runway, push for buybacks or dividends — hoarding can signal maturity. Compare valuation to historical P/E band; even compounders deserve trim rules when priced at euphoric multiples.""".strip(),
        formulas=(
            _F(
                "Compounding identity",
                r"V_T \approx V_0 \times (1 + ROIC \times RR)^T",
                "Value scales with return on reinvested capital and reinvestment rate over time.",
            ),
            _F(
                "Compounder score (FATE)",
                r"score = f(ROE, g_{earn}, payout)",
                "Rewards high ROE, earnings growth, and low payout (more reinvestment fuel).",
                "investing.formulas.growth.compounder_score",
            ),
            _F(
                "Sustainable growth",
                r"g = ROE \times (1 - payout)",
                "Retention × return on equity approximates per-share growth when ROE is stable.",
            ),
            _F(
                "PEG sanity for compounders",
                r"PEG = \frac{P/E}{\text{EPS growth}\%}",
                "Even compounders can be overpaid — PEG helps cap entry enthusiasm.",
                "investing.formulas.growth.peg_ratio",
            ),
        ),
        screens=(
            "ROE/ROIC top quartile for 10+ years (or since IPO for younger firms)",
            "Revenue and EPS per share growing without chronic dilution",
            "Payout ratio below 50% unless capital-light model",
            "Moat evidence: pricing power, retention, share stability",
            "Insider ownership; CEO tenure with compounding track record",
            "FCF redeployed productively — not hoarded indefinitely without plan",
        ),
        traps=(
            "Mature compounder priced for past glory (ROIC mean-reverting)",
            "Diworsification M&A at peak multiples",
            "Accounting ROE inflated by leverage or buybacks alone",
            "Ignoring disruption risk (Kodak-style compounders)",
        ),
        catalysts=(
            "Long-run EPS compounding (no single event required)",
            "Opportunistic buybacks in selloffs",
            "International expansion extending reinvestment runway",
            "Operating leverage as fixed platform scales",
        ),
        fate_hook="`compounder_score` in `investing.formulas.growth`; 20% weight in growth family blend via `investing.integrate.book_rank_boost`.",
        related=("quality_growth", "buffett", "secular_growth", "garp", "dividend_growth"),
        further_reading=(
            "Buffett Letters to Berkshire Shareholders",
            "Lawrence Cunningham — Quality Investing",
        ),
    )
)

register(
    DeepChapter(
        topic_id="innovation",
        title="Innovation Investing",
        family="growth",
        philosophy="""
Innovation investing backs companies creating new products, platforms, or business
models that change how work gets done, how consumers spend, or how industries
produce value. The philosophy treats R&D and product velocity as assets — not
expenses to minimize — because the winner in a new category often captures
disproportionate economics. You are funding experimentation with the expectation
that a portfolio of bets produces a few outsized winners paying for many failures.

Unlike steady compounders, innovation portfolios tolerate binary outcomes and
long proof periods before revenue inflects. The edge is domain expertise: understanding
technology adoption, regulatory pathways, and whether innovation is defensible
(patents, data, ecosystem) or easily copied. Diversification and stage-aware
sizing manage the base rate of failure without abandoning exposure to transformative
upside.


Innovation portfolios resemble venture portfolios: a few winners pay for many zeros. Public-market liquidity is a double-edged sword — you can exit fast, but also panic out of correct long-term bets on volatile KPIs. Stage-appropriate sizing is not optional decoration; it is core risk management.""".strip(),
        how_it_works="""
Map the innovation pipeline: R&D spend as % of sales, patent filings, product
roadmaps, beta customer wins, and time-to-revenue for new SKUs. For software,
track release cadence and net retention on new modules; for biotech, clinical
milestones and probability-weighted NPV; for hardware, design wins and BOM cost
curves.

Invest early when evidence of product-market fit is emerging but the market still
prices skepticism — or invest at inflection when first commercial scale proves
unit economics. Avoid funding ‘innovation theater’ (conferences without shipping
products). Monitor competitive response: incumbents may copy features or acquire
threats.

Portfolio construction: core positions in proven innovators plus satellite stakes
in higher-risk R&D optionality. Rebalance when innovation converts to cash or
when pipeline stalls.


Maintain an innovation calendar: product launches, FDA dates, developer conferences, and patent expiries. Weight positions by evidence stage — more capital after commercial proof, less when science risk dominates. Read competitor patent landscapes and hiring trends as leading indicators beyond press releases.""".strip(),
        formulas=(
            _F(
                "R&D intensity",
                r"RD\% = \frac{R\&D}{Revenue}",
                "Higher R&D % signals investment in future products; must eventually convert to growth or it is value destruction.",
            ),
            _F(
                "Revenue from new products",
                r"NPI\% = \frac{Rev_{\text{new products}}}{Rev_{\text{total}}}",
                "Share of sales from recent launches — innovation must show up in the top line.",
            ),
            _F(
                "PEG for scaling innovators",
                r"PEG = \frac{P/E}{\text{EPS growth}\%}",
                "Once earnings exist, PEG disciplines price vs growth from new platforms.",
                "investing.formulas.growth.peg_ratio",
            ),
        ),
        screens=(
            "R&D or product spend aligned with stated strategy (not starved for EPS)",
            "Pipeline with dated milestones and addressable markets",
            "Early customer logos, design wins, or Phase 2+ clinical data (sector-dependent)",
            "Management with track record of shipping, not just pitching",
            "Balance sheet supports runway to commercialization",
            "IP or ecosystem moat forming around innovation",
        ),
        traps=(
            "Perpetual ‘pre-revenue’ story without milestone discipline",
            "Innovation copied by hyperscaler / incumbent bundle",
            "Regulatory rejection (FDA, antitrust) binary risk underpriced",
            "Acquisition of hype without integration skill",
        ),
        catalysts=(
            "Product launch exceeding adoption targets",
            "Partnership with distribution leader",
            "Patent grant or regulatory approval",
            "First profitable segment proving scalable model",
        ),
        fate_hook="Innovation names often score via `hypergrowth_score` and `quality_growth_score` in `investing.formulas.growth` when revenue/ROE inflect; blended in `investing.integrate`.",
        related=("disruptor", "early_stage", "hypergrowth", "secular_growth", "growth"),
        further_reading=(
            "Clayton Christensen — The Innovator's Dilemma",
            "Ark Invest / industry innovation frameworks (adapt critically)",
        ),
    )
)

register(
    DeepChapter(
        topic_id="disruptor",
        title="Disruptor Investing",
        family="growth",
        philosophy="""
Disruptor investing targets companies attacking incumbents with superior economics,
technology, or customer experience — often starting in overlooked niches and
moving upmarket until the legacy model breaks. Clayton Christensen’s insight:
incumbents rationally ignore low-end entrants until it is too late. The philosophy
accepts short-term unprofitability and skepticism from traditional metrics because
disruptors optimize for share and learning curves, not quarterly EPS.

The payoff is asymmetric when adoption crosses the chasm: revenue inflects, margins
expand with scale, and incumbents cannot retool fast enough. The risk is equally
real — many ‘disruptors’ are features, not companies, and incumbents can acquire,
litigate, or subsidize defense. You need a view on why this attacker wins permanently,
not just why the incumbent is hated today.


Disruption narratives are seductive; incumbent cash flows are patient. The disruptor investor must model both adoption speed and incumbent response — price wars, lobbying, and bundling can delay victory for years while destroying margins on both sides.""".strip(),
        how_it_works="""
Identify disruption signals: incumbents raising prices while losing share, customer
NPS gaps, cost curves falling (batteries, solar, cloud compute), or regulatory
barriers falling. Model unit economics vs legacy alternative — if the disruptor is
already cheaper or better at equal price, adoption accelerates.

Track share gains in beachhead segment, then adjacent markets. Watch incumbent
response: price cuts, bundling, lobbying. Size for volatility around earnings
when the market toggles between ‘disruption works’ and ‘incumbent fights back.’

Public disruptors often trade at extreme multiples early; use scenario analysis
(bull/base/bear TAM penetration) rather than single-point DCF. Pair with secular
themes (electrification, fintech, cloud) when tailwinds align.


Build a thesis map: beachhead segment, next adjacency, and terminal share assumption. Update when unit economics cross breakeven versus legacy alternative. Watch gross margin trajectory — disruptors that only win on price without cost advantage rarely achieve durable profits.

Document kill criteria upfront: share loss for two consecutive quarters, margin collapse without scale benefit, or regulatory block — exit before narrative denial sets in.""".strip(),
        formulas=(
            _F(
                "Disruption cost gap",
                r"\Delta Cost = Cost_{incumbent} - Cost_{disruptor}",
                "Widenning cost or experience gap drives adoption; monitor when gap closes.",
            ),
            _F(
                "Market share trajectory",
                r"\Delta Share_t = Share_t - Share_{t-1}",
                "Sustained share gains in core segment validate disruption thesis.",
            ),
            _F(
                "Hypergrowth overlay",
                r"score = f(g_{rev}, g_{earn})",
                "Disruptors in land-grab phase map to hypergrowth scoring in FATE.",
                "investing.formulas.growth.hypergrowth_score",
            ),
            _F(
                "TAM penetration",
                r"Pen = \frac{Rev}{TAM}",
                "Low penetration with strong unit economics implies long runway if moat forms.",
            ),
        ),
        screens=(
            "Clear 10x better / 10x cheaper claim with customer evidence",
            "Share gains vs named incumbent over 4+ quarters",
            "Gross margin path credible at scale",
            "Regulatory and legal overhang underwritten",
            "Management with domain depth, not generic ‘platform’ language",
            "Funding runway if pre-profit",
        ),
        traps=(
            "Incumbent acquires disruptor at premium — thesis ends",
            "Disruption stalls at niche — never crosses chasm",
            "Capital intensity higher than model (factories, subsidies)",
            "Multiple compression when growth slows even if share still gains",
        ),
        catalysts=(
            "Inflection quarter: profitability or FCF positive at scale",
            "Major customer win vs incumbent",
            "Regulatory tailwind (subsidy, approval)",
            "Incumbent retreat / bankruptcy in legacy segment",
        ),
        fate_hook="Disruptors with high revenue/earnings growth feed `hypergrowth_score`; quality filters via `quality_growth_score` in `investing.integrate` growth blend.",
        related=("innovation", "hypergrowth", "early_stage", "secular_growth", "growth"),
        further_reading=(
            "Clayton Christensen — The Innovator's Dilemma",
            "Rebecca Henderson — incumbent response case studies",
        ),
    )
)

register(
    DeepChapter(
        topic_id="early_stage",
        title="Early-Stage Growth (Public)",
        family="growth",
        philosophy="""
Early-stage growth in public markets focuses on younger companies — recent IPOs,
SPAC listings, or small caps still proving unit economics, market fit, and
scalable go-to-market. The philosophy is venture-like underwriting with public-market
liquidity: you accept wide estimate dispersion, lock-up expirations, and guidance
misses in exchange for getting in before institutional coverage and index weight
accumulate. Edge comes from reading S-1/prospectus footnotes, cohort data, and
management credibility more carefully than the first-week narrative.

These names swing on funding sentiment, short interest, and single KPI prints.
Position sizing and liquidity awareness are not afterthoughts — they are core to
survival. Early-stage public growth is where hypergrowth meets binary risk; the
best outcomes become compounders, the worst dilute to zero.


Public early-stage investing is venture with a ticker — lock-ups, secondary overhang, and sparse analyst coverage create dislocations both ways. Liquidity is a risk factor equal to business risk: the same thesis can be right and still untradeable in a crisis.""".strip(),
        how_it_works="""
Source ideas from IPO calendar, venture-backed exits, and screens for small/mid
cap with high revenue growth but limited analyst coverage. Read the S-1: customer
concentration, related-party deals, stock-based comp, path to profitability, use
of proceeds. Track lock-up expiry and secondary offering risk.

Entry: post-IPO base formation or first proof of retention/ margin improvement —
avoid chasing day-one pops unless fundamentals confirm. Exit: broken unit economics,
failed follow-on demand, or guidance cut breaking the adoption story. Use smaller
weights per name; cluster risk in ‘hot’ sectors (EV, crypto-adjacent) can dominate.

Liquidity: average daily volume must support your exit without moving the market.
Short interest can amplify both squeezes and collapses — know the borrow story.


Track share count quarterly — SBC and secondary offerings are silent dilution of your growth. Set maximum position size as a function of ADV (e.g., days to exit). Post-lock-up, watch whether insiders hold or distribute; insider selling clusters often precede multiple compression even when KPIs still grow.""".strip(),
        formulas=(
            _F(
                "Post-IPO return",
                r"R_{IPO} = \frac{P - P_{offer}}{P_{offer}}",
                "Context for entry discipline vs first-day euphoria.",
            ),
            _F(
                "EV / Revenue (early stage)",
                r"EV/S = \frac{Enterprise\ Value}{Revenue}",
                "Common valuation yardstick when Earnings negative; compare vs growth and gross margin peers.",
            ),
            _F(
                "Cash runway",
                r"Runway = \frac{Cash}{Quarterly\ Burn}",
                "Months until financing need — critical for pre-profit early stage.",
            ),
            _F(
                "PEG when earnings emerge",
                r"PEG = \frac{P/E}{\text{EPS growth}\%}",
                "Transition metric as early-stage names reach profitability.",
                "investing.formulas.growth.peg_ratio",
            ),
        ),
        screens=(
            "Years public < 5 (or market cap below institutional threshold)",
            "Revenue growth top decile; gross margin improving or best-in-class",
            "Cash runway ≥ 18 months post-IPO",
            "Founder-led with meaningful insider stake",
            "Lock-up expired or absorbed without collapse",
            "ADV sufficient for your strategy size",
        ),
        traps=(
            "IPO pop driven by allocation scarcity, not fundamentals",
            "SPAC promote structures / warrant overhang",
            "Guidance sandbagging then miss culture",
            "Liquidity vacuum — cannot exit on bad news",
            "Retail narrative without institutional diligence",
        ),
        catalysts=(
            "First profitable quarter or positive FCF",
            "Analyst initiation coverage",
            "Index inclusion (Russell reconstitution)",
            "Lock-up expiry absorbed; stock finds support",
            "Secondary offering at premium validates demand",
        ),
        fate_hook="Early-stage names with Yahoo growth fields score via `hypergrowth_score` and `garp_score` when P/E and EPS growth available in `investing.integrate.book_rank_boost`.",
        related=("hypergrowth", "innovation", "disruptor", "growth", "ipo"),
        further_reading=(
            "Jay Ritter — IPO academic literature",
            "S-1 reading guides (a16z, investor blogs)",
        ),
    )
)

register(
    DeepChapter(
        topic_id="secular_growth",
        title="Secular Growth Themes",
        family="growth",
        philosophy="""
Secular growth investing tilts toward multi-year structural shifts — aging
demographics, cloud migration, electrification, healthcare innovation, emerging
middle-class consumption — rather than quarterly GDP noise. The philosophy holds
that certain tailwinds persist across business cycles, and beneficiaries with
durable competitive positions can compound through recessions that crush cyclicals.
You are mapping the world’s slow-moving forces and owning the toll roads, not
betting on a single quarter’s inventory swing.

Theme investing risks crowding: everyone sees the same slide deck. Edge requires
picking execution winners within the theme, paying attention to valuation even
for ‘obvious’ trends, and avoiding late-cycle euphoria when every SPAC claims
AI exposure. Secular does not mean safe — wrong entry price or wrong horse still
hurts for years.


Secular themes can be right and still lose money if you buy the top of narrative enthusiasm. The investor’s job is to own the toll collectors with pricing power, not every logo on the thematic slide. Patience through mid-cycle slowdowns within a secular uptrend separates tourists from allocators.""".strip(),
        how_it_works="""
Define the theme with evidence: TAM growth rates, policy support, cost curves,
demographic data. Build a basket of enablers (picks-and-shovels), pure-plays, and
quality compounders riding the trend. Rebalance when valuations detach from
fundamentals or when the theme becomes consensus overweight.

Monitor for saturation signals: slowing order books, pricing pressure, regulatory
pushback, or capital flooding into low-return capacity. Secular themes can have
cyclical sub-components — solar installs ebb and flow even while penetration rises.

Hold periods measured in years. Combine top-down theme conviction with bottom-up
quality and GARP discipline (PEG ≤ 1 where earnings exist) so you do not overpay
for narrative alone.


Rebalance thematic sleeves annually: trim names trading at historical valuation highs, add laggards with intact fundamentals. Monitor capital formation — when every PE fund launches a ‘thematic’ vehicle, future returns often compress. Pair top-down TAM work with bottom-up unit economics on each holding.

Document position limits per theme so a single regulatory headline cannot dominate portfolio risk.""".strip(),
        formulas=(
            _F(
                "Theme TAM CAGR",
                r"CAGR = \left(\frac{TAM_T}{TAM_0}\right)^{1/T} - 1",
                "Structural market growth underpinning the secular thesis.",
            ),
            _F(
                "Penetration curve",
                r"S(t) = \frac{1}{1 + e^{-k(t-t_0)}}",
                "S-curve adoption model — early inflection vs mature slowdown phases.",
            ),
            _F(
                "GARP within theme",
                r"PEG = \frac{P/E}{\text{EPS growth}\%} \le 1",
                "Even secular winners deserve reasonable price — classic GARP filter.",
                "investing.formulas.growth.garp_score",
            ),
            _F(
                "Quality compounder overlay",
                r"score = f(ROE, g_{earn}, payout)",
                "Best secular holdings often score as compounders in FATE.",
                "investing.formulas.growth.compounder_score",
            ),
        ),
        screens=(
            "Revenue growth consistently above GDP + industry for theme beneficiaries",
            "Policy/regulatory tailwind documented (or headwind underwritten)",
            "Fragmented industry consolidating to scale players (optional)",
            "Valuation not at historical euphoria percentile",
            "Diversified across 8–15 names per theme",
            "Monitor ETF flows / crowding metrics",
        ),
        traps=(
            "Theme ETF overcrowding — correlated drawdowns",
            "Every company rebranding as theme exposure",
            "Capital cycle oversupply (e.g. chip fabs, solar manufacturing)",
            "Secular story with cyclical peak earnings (peak P/E trap)",
        ),
        catalysts=(
            "Policy passage (IRA, infrastructure bills)",
            "Cost curve crossing critical threshold (grid parity, EV TCO)",
            "Demographic milestone accelerating demand",
            "Consolidation M&A among theme leaders",
        ),
        fate_hook="Secular growers aggregate in growth blend: `garp_score`, `quality_growth_score`, `compounder_score` from `investing.formulas.growth` via `investing.integrate.book_rank_boost`.",
        related=("growth", "compounders", "garp", "innovation", "infrastructure_income"),
        further_reading=(
            "McKinsey Global Institute — trend reports",
            "IEA / industry bodies for energy transition data",
        ),
    )
)
