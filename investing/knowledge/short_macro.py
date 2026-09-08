"""Short selling / macro — deep chapters (short + macro families)."""

from __future__ import annotations

from investing.knowledge import DeepChapter, FormulaSpec, register

_F = FormulaSpec

register(
    DeepChapter(
        topic_id="short_selling",
        title="Short Selling",
        family="short",
        philosophy="""
Short selling is the mirror image of ownership: you borrow shares, sell them
into the market, and hope to buy them back cheaper later. The economic logic
is identical to value investing in reverse — you believe price exceeds a
conservative estimate of worth, and you profit when the gap closes. Unlike
longs, where the worst case is losing your stake, shorts face theoretically
unlimited loss if price rises without bound.

The edge is rarely permanent pessimism; it is identifying overvaluation,
fraud, broken business models, or crowded longs where downside is
underpriced. Shorts also serve a social function: they price bad news into
markets faster and can restrain bubbles. The craft demands humility, tight
risk limits, and respect for borrow mechanics — a great thesis can still
bankrupt you if a squeeze arrives before truth.
""".strip(),
        how_it_works="""
Workflow: (1) identify overvalued or impaired businesses with a clear
underwriting case, (2) locate borrowable stock and confirm fee/rebate terms,
(3) sell short with defined stop or size cap, (4) monitor catalysts and
short interest, (5) cover when thesis resolves or risk budget is breached.

Borrow is not guaranteed — hard-to-borrow names carry high fees and recall
risk (forced buy-in). Mark-to-market losses require margin; a rising stock
can force liquidation at the worst moment. Many professionals pair shorts
with long hedges (see long-short and market-neutral chapters) rather than
running naked directional shorts. Position sizing is smaller than equivalent
longs because tail risk is asymmetric.
""".strip(),
        formulas=(
            _F(
                "Short P&L",
                r"P\&L_{short} = (P_{sell} - P_{buy}) \times Q",
                "Profit when cover price is below sale price. Q is shares shorted.",
            ),
            _F(
                "Short beta exposure",
                r"\beta_{portfolio} = \sum_i w_i \beta_i \quad (w_i < 0 \text{ for shorts})",
                "Short positions contribute negative beta. A $1M short in β=1.2 stock adds −$1.2M market exposure.",
                "analytics.hedge_fund_stack",
            ),
            _F(
                "Borrow cost drag",
                r"Annual\ drag \approx fee\% \times notional",
                "Hard-to-borrow names can charge 20–100%+ annualized; erodes edge on slow-burn theses.",
            ),
        ),
        screens=(
            "Clear overvaluation vs normalized earnings or asset value",
            "Catalyst within horizon (earnings miss, fraud probe, refinancing failure)",
            "Borrow available at acceptable fee; recall risk assessed",
            "High short interest only if you accept squeeze risk — size down",
            "Stop or time stop defined before entry",
        ),
        traps=(
            "Unlimited loss on open-ended squeeze (meme stocks, takeover rumors)",
            "Borrow recall forcing cover at peak",
            "Right thesis, wrong timing — markets can stay irrational",
            "Accounting fraud shorts without legal cushion",
            "Crowded short book — everyone covers together",
        ),
        catalysts=(
            "Earnings disappointment resetting estimates",
            "Credit downgrade or covenant breach",
            "Regulatory action or product failure",
            "Insider selling cluster / auditor resignation",
        ),
        fate_hook="Short-side signals soft in rank pipeline; beta and pair tools in `analytics.hedge_fund_stack` support hedged books. Borrow data external.",
        related=("long_short", "market_neutral", "bear_strategies", "contrarian"),
        further_reading=(
            "Edward Chanos — short-selling case studies",
            "Aswath Damodaran — valuation for skeptics",
        ),
    )
)

register(
    DeepChapter(
        topic_id="long_short",
        title="Long-Short Equity",
        family="short",
        philosophy="""
Long-short equity seeks alpha from stock selection on both sides of the book:
own what is cheap and improving, short what is expensive and deteriorating.
Net market exposure can be tuned from bullish to bearish, but the core bet is
relative performance — the long basket should beat the short basket regardless
of whether the index rises or falls. This is how many hedge funds aim for
absolute return with controlled beta.

The discipline is bilateral: weak longs and weak shorts both destroy returns.
Crowded shorts in high-quality momentum names are a classic failure mode.
Successful managers run independent research pipelines for each leg, size by
conviction and liquidity, and rebalance when factor drift or beta imbalance
accumulates. Costs (borrow, turnover, spreads) matter — edge must exceed
friction net of fees.
""".strip(),
        how_it_works="""
Typical construction: rank universe on composite scores (value, quality,
momentum, sentiment). Long top decile, short bottom decile, dollar-neutral
or beta-neutral weighting. Rebalance weekly to monthly; trim names that
hit stops or violate thesis. Risk overlays cap sector, factor, and single-name
concentration.

Portfolio beta is monitored continuously. If net β drifts positive in a rally,
shorts may be too small or longs too momentum-heavy. Gross exposure (long +
short notional) affects leverage and financing cost. Many funds run 130/30
(130% long, 30% short) for a mild long bias while harvesting spread alpha.
""".strip(),
        formulas=(
            _F(
                "Net exposure",
                r"Net = \frac{\sum Long - \sum Short}{\text{AUM}}",
                "Positive net = net long market; zero ≈ market-neutral.",
            ),
            _F(
                "Gross exposure",
                r"Gross = \frac{\sum Long + \sum Short}{\text{AUM}}",
                "Leverage indicator; 200% gross means $2 deployed per $1 AUM.",
            ),
            _F(
                "Long-short spread return",
                r"R_{LS} \approx R_{long} - R_{short}",
                "Alpha proxy when books are balanced; ignores financing and borrow costs.",
            ),
            _F(
                "Beta-neutral weight",
                r"w_{short} \approx w_{long} \times \frac{\beta_{long}}{\beta_{short}}",
                "Scale short leg so portfolio β ≈ 0.",
                "analytics.hedge_fund_stack",
            ),
        ),
        screens=(
            "Long candidates: positive FCF, improving estimates, reasonable valuation",
            "Short candidates: deteriorating margins, extreme multiples, weak balance sheet",
            "Avoid shorting highest-momentum leaders without catalyst",
            "Gross exposure within mandate; borrow feasible on short leg",
            "Factor exposure intentional, not accidental",
        ),
        traps=(
            "Short leg becomes crowded momentum long — painful squeeze",
            "Style drift: longs and shorts both value → still beta-heavy",
            "Ignoring borrow costs on persistent shorts",
            "Over-leverage gross in calm vol, forced delever in spikes",
        ),
        catalysts=(
            "Earnings season separating winners from losers",
            "Factor rotation favoring your long/short tilt",
            "Index rebalancing flows",
        ),
        fate_hook="Factor ranks in `analytics.hedge_fund_stack` feed long-short tilts; `pair_spread_z` and beta tools support neutral construction.",
        related=("market_neutral", "pair_trading", "factor", "stat_arb"),
        further_reading=(
            "Jacques Financial — equity market neutral primers",
            "CFA Institute — long-short equity overview",
        ),
    )
)

register(
    DeepChapter(
        topic_id="market_neutral",
        title="Market Neutral",
        family="short",
        philosophy="""
Market-neutral strategies target zero (or near-zero) correlation to broad
equity indices. Returns should come from security selection, pairs, or
statistical arbitrage — not from betting the market direction. Investors
who cannot forecast macro but believe they can rank stocks within a sector
find this structure appealing: smooth-ish equity curves in theory, though
in practice factor shocks and correlation breakdowns still hurt.

True neutrality is harder than labeling. Beta-neutral today may be beta-positive
tomorrow after a rally in your long book. Sector neutrality, factor neutrality,
and currency hedging add layers. The philosophy is humility about macro combined
with conviction about micro mispricings that will converge.
""".strip(),
        how_it_works="""
Build matched long and short portfolios of similar size, sector, and beta.
Common implementations: (1) dollar-neutral top/bottom decile, (2) beta-
adjusted weights using rolling regression, (3) pair baskets hedged with
index futures. Rebalance when drift exceeds bands (e.g. |β| > 0.1).

Monitor exposure to size, value, momentum factors — unintended tilts become
hidden macro bets. Financing: longs earn collateral; shorts pay borrow. In
low-vol regimes, carry on the short book can erode thin alpha. Risk limits
on gross exposure and single-name weight prevent one blow-up from dominating.
""".strip(),
        formulas=(
            _F(
                "Portfolio beta",
                r"\beta_p = \sum_i w_i \beta_i",
                "Target β_p ≈ 0 for market neutrality.",
                "investing.formulas.risk.capm_beta",
            ),
            _F(
                "Beta hedge ratio",
                r"h = \frac{\beta_{long\ book}}{\beta_{index}} \times \frac{V_{long}}{V_{index\ contract}}",
                "Index futures contracts to offset residual beta.",
            ),
            _F(
                "Pair spread z-score",
                r"z = \frac{spread - \mu_{spread}}{\sigma_{spread}}",
                "Standardized deviation of log-price ratio; entry often at |z| > 2.",
                "analytics.hedge_fund_stack",
            ),
        ),
        screens=(
            "Rolling portfolio |β| below threshold (e.g. 0.1)",
            "Long and short gross within policy (e.g. 100/100)",
            "Sector and cap matched across legs where possible",
            "Pair cointegration or correlation stable out-of-sample",
            "Borrow and financing costs modeled in expected alpha",
        ),
        traps=(
            "Correlation breakdown — spreads diverge further before mean reversion",
            "Hidden factor bets (all long quality, all short junk)",
            "Leverage disguised as neutrality",
            "Capacity limits in small-cap pairs",
        ),
        catalysts=(
            "Mean reversion of pair spreads",
            "Earnings dispersion within sector",
            "Reduction in market-wide correlation (stock-picking environment)",
        ),
        fate_hook="Live `pair_spread_z` and `beta_neutral` in `analytics.hedge_fund_stack`. Rank pipeline can tilt toward low-beta constructions.",
        related=("pair_trading", "long_short", "stat_arb", "risk_parity"),
        further_reading=(
            "Andrew Lo — Market neutral hedge funds",
            "Ernie Chan — pairs trading chapters",
        ),
    )
)

register(
    DeepChapter(
        topic_id="pair_trading",
        title="Pair Trading",
        family="short",
        philosophy="""
Pair trading is the simplest relative-value trade: two securities that
normally move together have diverged, and you bet the spread reverts. Go
long the laggard, short the leader, and earn the convergence without
calling market direction. The intellectual appeal is statistical — if the
relationship is stable, extreme dislocations are temporary unless the
economic link is broken (merger failure, regulatory split, product shift).

Pairs are not free money. Cointegration can decay; “historical norm” may
have been noise. The philosophy is patience plus stop discipline: spreads
can widen further (Long-Term Capital Management lesson), so size and
horizon must match the statistical evidence, not hope alone.
""".strip(),
        how_it_works="""
Select pairs: same industry, similar business model, historical correlation
> 0.7 or cointegration test significant. Compute spread (log price ratio or
residual from regression). Track rolling mean and std; enter when z-score
exceeds ±2, exit near 0 or at time stop. Hedge ratio from regression
β of stock A on stock B determines relative share counts.

Risk: fundamental divergence (one wins market share permanently). Monitor
news on both legs. Portfolio of many pairs diversifies idiosyncratic blow-ups.
Transaction costs and borrow on the short leg must be included in backtests.
""".strip(),
        formulas=(
            _F(
                "Log spread",
                r"spread_t = \ln(P_{A,t}) - \ln(P_{B,t})",
                "Stationary spread preferred; raw price ratio can drift with different betas.",
            ),
            _F(
                "Z-score",
                r"z_t = \frac{spread_t - \bar{spread}}{\sigma_{spread}}",
                "Entry signal when |z| > 2; exit as z → 0.",
                "analytics.hedge_fund_stack",
            ),
            _F(
                "Hedge ratio (OLS)",
                r"P_A = \alpha + \beta P_B + \epsilon \Rightarrow Q_B = \beta \times Q_A",
                "Shares of B per share of A to neutralize dollar drift.",
            ),
            _F(
                "Half-life of mean reversion",
                r"spread_t = \phi \cdot spread_{t-1} + \epsilon, \quad HL = -\frac{\ln 2}{\ln \phi}",
                "Estimates expected days to revert; sets holding period expectations.",
            ),
        ),
        screens=(
            "Cointegration or high stable correlation over 2+ years",
            "|z| > 2 at entry with liquidity on both legs",
            "No pending merger/antitrust break between names",
            "Borrow available on short leg",
            "Diversify across ≥ 10 pairs",
        ),
        traps=(
            "Spurious correlation — unrelated stocks that diverge forever",
            "Regime change (disruption kills one franchise)",
            "Z-score hits 4 before reversion — insufficient capital",
            "Ignoring corporate actions (splits, spin-offs)",
        ),
        catalysts=(
            "Earnings convergence",
            "Sector re-rating affecting both names",
            "Index inclusion/exclusion flows",
        ),
        fate_hook="Soft `pair_spread_z` in `analytics.hedge_fund_stack`; stat-arb family shares infrastructure with market-neutral.",
        related=("market_neutral", "stat_arb", "mean_reversion", "long_short"),
        further_reading=(
            "Gatev, Goetzmann & Rouwenhorst — pairs trading paper",
            "Ernie Chan — Algorithmic Trading",
        ),
    )
)

register(
    DeepChapter(
        topic_id="inverse_etfs",
        title="Inverse ETFs",
        family="short",
        philosophy="""
Inverse ETFs deliver negative daily exposure to an index or sector via
derivatives — a tactical hedge for investors who cannot or will not short
stock directly. They democratize bearish expression without margin accounts
or locate borrow. The critical philosophical point: they are *daily* instruments.
Compounding math means a −1× product held for months in a choppy market
often underperforms intuitive “opposite of the index” expectations.

Use inverse ETFs as short-term insurance or trading vehicles, not as a
long-term structural short substitute. Understand path dependency: volatility
erodes constant-leverage products even when the index ends flat.
""".strip(),
        how_it_works="""
Each day the fund resets exposure to −1× (or −2×, −3× for leveraged inverse)
of the benchmark return. If the index rises 10% then falls 10%, a 1× inverse
does not return to par — both legs compound against the holder in volatility.

Typical use: hedge a long equity book overnight or through a known risk event;
trade a tactical downtrend with tight stops; pair with options for defined risk.
Check expense ratios, swap counterparty disclosures, and liquidity (bid-ask).
For multi-week bear views, puts or direct shorts often behave more predictably.
""".strip(),
        formulas=(
            _F(
                "Daily inverse return",
                r"R_{inv,t} \approx -k \times R_{index,t}",
                "k = leverage factor (1, 2, or 3). Reset daily.",
            ),
            _F(
                "Volatility drag (conceptual)",
                r"V_{T} \approx V_0 \times \prod_t (1 + R_{inv,t}) \neq -V_0 \times \frac{P_{index,T}}{P_{index,0}}",
                "Multi-day path matters; choppy markets erode NAV vs naive opposite.",
            ),
            _F(
                "Hedge notional",
                r"Notional_{hedge} \approx \beta_{portfolio} \times AUM",
                "Size inverse ETF to offset estimated portfolio beta.",
            ),
        ),
        screens=(
            "Holding period days to weeks, not years",
            "Understand leverage factor (1× vs 3×)",
            "Adequate volume and tight spreads",
            "Expense ratio acceptable for tactical use",
            "Know index tracked (some use futures, not cash index)",
        ),
        traps=(
            "Buy-and-hold inverse in sideways market — slow bleed",
            "3× products amplify decay and gap risk",
            "End-of-day reset misses intraday crash protection needs",
            "Tax treatment in taxable accounts (K-1 structures rare but check)",
        ),
        catalysts=(
            "Known macro shock (Fed surprise, geopolitical)",
            "Portfolio rebalancing into risk-off",
            "Earnings-week hedge for concentrated long book",
        ),
        fate_hook="Knowledge chapter; tactical hedging external to rank pipeline. Beta from `investing.formulas.risk` sizes hedge notional.",
        related=("bear_strategies", "short_selling", "protective_puts", "tactical_aa"),
        further_reading=(
            "ETF issuer prospectuses (daily reset disclosure)",
            "SEC investor bulletin on leveraged/inverse ETFs",
        ),
    )
)

register(
    DeepChapter(
        topic_id="bear_strategies",
        title="Bear Strategies",
        family="short",
        philosophy="""
Bear strategies profit when asset prices fall — through shorts, inverse
products, put options, or raising cash. They are not pessimism for its own
sake; they are risk management and opportunism when valuations, credit,
or sentiment signal elevated crash probability. Bears who survive long enough
often become the bulls who buy the bottom — the skill is timing entry and
covering violent bear-market rallies that wipe out premature shorts.

Permanent bears rarely win; cyclical bears who respect risk limits do.
The philosophy balances capital preservation in downturns with willingness
to redeploy when margin of safety reappears. Bear positioning is expensive
(carry, theta, borrow) — use it when evidence outweighs cost.
""".strip(),
        how_it_works="""
Implementation menu: (1) reduce net exposure / raise cash, (2) buy puts or
collars on indices or holdings, (3) short weak balance sheets and bubble
narratives, (4) tactical inverse ETFs, (5) long volatility (see volatility
trading chapter). Combine macro signals (yield curve, credit spreads, PMI)
with valuation (high CAPE, narrow market breadth) for regime awareness.

Cover rules matter: define what invalidates the bear thesis (all-time highs
on breadth expansion, credit repair). Bear rallies of 10–20% are common
within secular declines — shorts without stops get carried out.
""".strip(),
        formulas=(
            _F(
                "Put payoff",
                r"Payoff = \max(K - S_T, 0) - Premium",
                "Long put gains as stock falls below strike K.",
                "investing.formulas.options",
            ),
            _F(
                "CAPE (Shiller P/E)",
                r"CAPE = \frac{P}{10\text{-year average real EPS}",
                "High CAPE historically associates with lower forward 10-year returns — not a timing clock.",
            ),
            _F(
                "Credit spread",
                r"Spread = Y_{HY} - Y_{Treasury}",
                "Widening spreads signal risk-off; tightening can end bear trades.",
            ),
        ),
        screens=(
            "Macro deterioration: inverted curve, rising unemployment claims",
            "Valuation stretched vs history (CAPE, market cap / GDP)",
            "Breadth narrowing — index held by few mega-caps",
            "Credit stress in fragile issuers",
            "Defined risk via puts vs unlimited short",
        ),
        traps=(
            "Shorting too early in bubble — squeeze before pop",
            "Inverse ETF decay in choppy correction",
            "Perma-bear missing years of compounding",
            "Ignoring policy put / central bank intervention",
        ),
        catalysts=(
            "Recession confirmation",
            "Credit event (bank stress, LBO default wave)",
            "Earnings recession across cyclicals",
            "Geopolitical shock",
        ),
        fate_hook="`regime_detector.py` and yield-spread signals inform risk-off posture; rank pipeline can de-risk via fortress overlays.",
        related=("inverse_etfs", "short_selling", "deflation", "volatility_trading"),
        further_reading=(
            "Russell Napier — The Asian Financial Crisis / credit histories",
            "Howard Marks — memos on cycles",
        ),
    )
)

register(
    DeepChapter(
        topic_id="global_macro",
        title="Global Macro",
        family="macro",
        philosophy="""
Global macro managers trade the big forces — growth, inflation, interest
rates, currencies, commodities, geopolitics — across countries and asset
classes. The thesis is that policy mistakes, terms-of-trade shocks, and
capital flows create multi-month dislocations larger than single-stock
noise. Unlike bottom-up stock picking, edge comes from synthesizing
central-bank reaction functions, fiscal trajectories, and cross-market
arbitrage (e.g. rates vs FX vs equities telling different stories).

Macro is humbling: consensus trades crowd quickly; tail events dominate
P&L. Successful shops combine scenario planning, position sizing by
conviction, and willingness to flip when data changes. No single model
owns truth; triangulation across markets does.
""".strip(),
        how_it_works="""
Research loop: monitor leading indicators (PMI, payrolls, inflation prints),
central-bank guidance, and market-implied paths (OIS, futures curves, FX
forwards). Form a view on growth/inflation quadrant → map to trades:
steepeners/flattener, long/short duration, commodity exposure, EM vs DM FX,
equity beta tilt, credit quality rotation.

Positions span futures, FX, rates, ETFs, and equities as expression vehicles.
Risk is portfolio-level: correlation assumptions break in crises. Regime
detection (expansion, slowdown, stagflation, recovery) guides which playbook
is active. Size scales with edge clarity and liquidity.
""".strip(),
        formulas=(
            _F(
                "Taylor rule (conceptual)",
                r"i^* \approx r^* + \pi + 0.5(\pi - \pi^*) + 0.5(y - y^*)",
                "Benchmark policy rate given inflation and output gaps — anchor for rate views.",
            ),
            _F(
                "Real exchange rate",
                r"RER = \frac{E \times P^*}{P}",
                "Competitiveness driver for currency macro trades.",
            ),
            _F(
                "Regime detection",
                r"P(S_t \mid X_t) \text{ via HMM}",
                "Hidden Markov models classify macro states from observables.",
                "regime_detector.py",
            ),
        ),
        screens=(
            "Cross-asset consistency: do rates, FX, and equities agree?",
            "Position sizing vs liquidity (futures roll, EM depth)",
            "Scenario matrix: growth up/down × inflation up/down",
            "Stop-loss on narrative break (data surprise)",
            "Carry and financing on leveraged expressions",
        ),
        traps=(
            "Fighting central banks with oversized conviction",
            "Illiquid EM expressions during stress",
            "Single-indicator macro (one CPI print ≠ regime)",
            "Over-leverage in quiet vol that spikes overnight",
        ),
        catalysts=(
            "Central bank pivot",
            "Fiscal shock (stimulus, austerity)",
            "Commodity supply disruption",
            "Election / geopolitical regime change",
        ),
        fate_hook="Live `regime_hmm` in `regime_detector.py` frames macro backdrop for sector and rank tilts.",
        related=("top_down", "currency", "interest_rate", "business_cycle"),
        further_reading=(
            "George Soros — The Alchemy of Finance",
            "Steven Drobny — Inside the House of Money",
        ),
    )
)

register(
    DeepChapter(
        topic_id="top_down",
        title="Top-Down Analysis",
        family="macro",
        philosophy="""
Top-down investing starts with the forest, then picks trees: economy,
policy, sector trends, and only then individual securities. The premise is
that macro and sector tides move most stocks — fighting a hawkish Fed with
cheap small-cap value rarely ends well even if stock picking is skilled.
Top-down is not macro forecasting heroics; it is aligning portfolio tilt
with the prevailing wind so security selection works harder, not harder
against gravity.

Investors blend degrees: pure top-down rotates sectors and factors;
hybrid top-down sets risk budget then bottom-up fills names. The philosophy
respects that *when* you own something matters as much as *what* you own
in cyclical and rate-sensitive domains.
""".strip(),
        how_it_works="""
Framework: (1) classify cycle phase (early, mid, late, recession), (2) map
phase to sector winners (cyclicals early, defensives late), (3) set regional
and cap exposure, (4) within favored sectors run bottom-up screens for best
risk/reward. Update quarterly or on regime shift signals.

Tools: yield curve shape, LEI, earnings revision breadth, PMI new orders,
credit spreads, inflation trend. Equity implementation via sector ETFs,
factor tilts, or stock screens filtered by GICS. Fixed income duration
and credit quality complete the policy portfolio.
""".strip(),
        formulas=(
            _F(
                "Yield curve slope",
                r"Slope = Y_{10y} - Y_{2y}",
                "Steep slope often early-cycle; inversion warns slowdown.",
                "regime_detector.py",
            ),
            _F(
                "Sector relative strength",
                r"RS_{sector} = \frac{P_{sector}/P_{sector,0}}{P_{SPY}/P_{SPY,0}}",
                "Leaders outperforming benchmark suggest rotation target.",
            ),
        ),
        screens=(
            "Cycle phase identified with ≥ 2 confirming indicators",
            "Sector weights aligned to phase playbook",
            "Bottom-up names only in favored sectors (or hedge elsewhere)",
            "Geographic exposure matches growth/inflation view",
            "Rebalance when phase signals flip",
        ),
        traps=(
            "Macro timing precision illusion",
            "Ignoring stock-specific blow-ups in favored sector",
            "Lagging indicators — phase shift already priced",
            "Over-rotation turnover and taxes",
        ),
        catalysts=(
            "PMI inflection",
            "Fed policy shift",
            "Earnings breadth expansion/contraction",
        ),
        fate_hook="Sector rotation soft formula in `investing.formulas.sector`; regime detector informs top-down tilt in fortress.",
        related=("bottom_up", "business_cycle", "sector_rotation", "global_macro"),
        further_reading=(
            "Sam Stovall — Sector Investing",
            "Merrill Lynch Investment Clock (classic framework)",
        ),
    )
)

register(
    DeepChapter(
        topic_id="bottom_up",
        title="Bottom-Up Analysis",
        family="macro",
        philosophy="""
Bottom-up analysis evaluates companies on their own merits — financials,
moat, management, valuation — treating macro as background noise unless
it threatens solvency or demand. The belief: security-specific edge from
deeper work beats sector timing for patient investors with long horizons.
Warren Buffett’s circle of competence is bottom-up: understand the business,
ignore the macro forecast you cannot reliably make.

Macro still matters at extremes: liquidity crises hit all stocks; rate
shocks compress all multiples. Bottom-up does not mean macro-blind — it
means not *starting* from GDP forecasts. Risk management can overlay macro
hedges without contaminating stock selection discipline.
""".strip(),
        how_it_works="""
Process: screen universe on quality and valuation metrics → deep dive 10-K,
calls, competitors → model FCF and scenarios → buy with MOS → monitor
thesis drivers (not daily macro). Portfolio diversification across
industries provides implicit macro smoothing.

When bottom-up disagrees with top-down (great company in hated sector),
size smaller or demand extra MOS. Earnings transcripts reveal company-specific
demand better than national PMI for that name. Pair with qualitative analysis
on management and moat.
""".strip(),
        formulas=(
            _F(
                "Intrinsic value anchor",
                r"IV = \sum \frac{CF_t}{(1+r)^t} + \frac{TV}{(1+r)^n}",
                "Bottom-up price target from company cash flows, not sector multiple alone.",
                "analytics.value_investing.intrinsic_value",
            ),
            _F(
                "ROIC",
                r"ROIC = \frac{NOPAT}{\text{Invested Capital}}",
                "Company-specific quality independent of macro label.",
            ),
        ),
        screens=(
            "Understandable business model and unit economics",
            "Moat evidence in margins and ROIC persistence",
            "Valuation vs own history and peers (not sector story alone)",
            "Balance sheet survives recession scenario",
            "Management alignment and capital allocation track record",
        ),
        traps=(
            "Ignoring sector headwind until estimates reset",
            "Value trap without company-specific catalyst",
            "Concentration in one industry macro shock",
            "DCF using peak-cycle margins as normal",
        ),
        catalysts=(
            "Company-specific product win",
            "Margin inflection from self-help",
            "Activist or strategic bid",
        ),
        fate_hook="Core `analytics.value_investing` and rank boosts are bottom-up fundamental engines; macro overlays optional.",
        related=("fundamental", "valuation", "economic_moat", "top_down"),
        further_reading=(
            "Philip Fisher — Common Stocks and Uncommon Profits",
            "Buffett shareholder letters",
        ),
    )
)

register(
    DeepChapter(
        topic_id="currency",
        title="Currency Macro",
        family="macro",
        philosophy="""
Currency macro trades FX pairs based on interest-rate differentials,
balance-of-payments dynamics, central-bank policy paths, and risk appetite.
Currencies are the clearest expression of relative macro: a hawkish central
bank with terms-of-trade tailwinds attracts capital; a funding currency
cheapens when global risk-taking expands. Carry trades harvest rate
differentials but blow up in risk-off spasms when crowded positions unwind.

FX is zero-sum at the aggregate level and highly levered for retail.
Professional edge combines macro narrative, positioning data, and valuation
(PPP, REER) — not guessing daily noise. Respect that policy intervention
and verbal jawboning move markets faster than goods-trade fundamentals.
""".strip(),
        how_it_works="""
Frameworks: (1) *Carry* — long high-yielder vs low-yielder, sized for vol;
(2) *Momentum* — trend follow strong performers; (3) *Valuation* — fade
extreme REER deviations; (4) *Flow* — track reserves, trade balance, cape
account. Express via spot FX, forwards, or currency-hedged equity ETFs.

G10 pairs (EUR/USD, USD/JPY) offer liquidity; EM FX adds spread and
political risk. Hedge equity exposure: unhedged foreign stocks embed FX bet.
Rolling hedges cost the rate differential — sometimes intentional, sometimes not.
""".strip(),
        formulas=(
            _F(
                "Covered interest parity",
                r"F/S \approx \frac{1 + r_d}{1 + r_f}",
                "Forward discount/premium tied to rate differential.",
            ),
            _F(
                "Carry return (simplified)",
                r"Carry \approx r_{high} - r_{low} - \Delta spot",
                "Earn interest differential minus adverse spot move.",
            ),
            _F(
                "Real exchange rate",
                r"RER = E \times \frac{P_{foreign}}{P_{domestic}}",
                "Valuation anchor for long-horizon mean reversion views.",
            ),
        ),
        screens=(
            "Rate differential direction matches trade",
            "Positioning not extreme crowded carry",
            "Central bank rhetoric aligned or priced",
            "Liquidity adequate for stop execution",
            "Hedge ratio for equity FX exposure explicit",
        ),
        traps=(
            "Carry unwind in risk-off (2008, 2020)",
            "Peg break / capital control surprise",
            "Leverage on tight stops in gap-open markets",
            "Ignoring intervention risk",
        ),
        catalysts=(
            "Central bank surprise hike/cut",
            "Terms-of-trade shock (oil for CAD/NOK)",
            "Risk-on/risk-off regime flip",
        ),
        fate_hook="Macro knowledge; FX not in equity rank pipeline. Regime detector contextualizes risk appetite for USD proxy trades.",
        related=("global_macro", "interest_rate", "inflation", "multi_asset"),
        further_reading=(
            "Clifton — Currency Strategy",
            "IMF External Sector Reports",
        ),
    )
)

register(
    DeepChapter(
        topic_id="commodity_macro",
        title="Commodity Macro",
        family="macro",
        philosophy="""
Commodity macro positions in energy, metals, and agriculture reflect
real-economy supply and demand, inventories, and geopolitical risk —
not corporate earnings narratives. Commodities often lead inflation
surprises and hurt or help importing vs exporting nations. They diversify
equity/bond portfolios when correlations are low, though in liquidity
crises correlations can spike toward one.

Investors use commodities as inflation hedge, growth signal (copper),
safe-haven adjunct (gold), or geopolitical stress expression (oil).
Futures curves matter: contango bleeds long ETFs; backwardation pays roll
yield. Physical constraints (OPEC, weather, strikes) create non-Gaussian spikes.
""".strip(),
        how_it_works="""
Analysis stack: (1) supply (OPEC quotas, mine output, harvest forecasts),
(2) demand (China PMI, industrial production), (3) inventories (EIA, LME,
USDA reports), (4) curve shape (prompt vs deferred prices), (5) USD link
(most commodities priced in dollars). Trade via futures, commodity ETFs,
or equities along the value chain (miners, refiners).

Macro pairing: long oil in reflation; long gold when real rates fall;
short industrial metals in China slowdown thesis. Position size for gap risk
around inventory prints and Middle East headlines.
""".strip(),
        formulas=(
            _F(
                "Roll yield (conceptual)",
                r"Roll\ yield \approx \frac{F_{near} - F_{far}}{F_{near}}",
                "Backwardation (near > far) benefits longs rolling contracts.",
            ),
            _F(
                "Gold vs real rates",
                r"Gold \uparrow \text{ when } r_{real} \downarrow,\quad r_{real} \approx r_{nominal} - \pi^e",
                "Opportunity cost of holding non-yielding metal falls as real rates drop.",
            ),
            _F(
                "Terms of trade",
                r"TOT = \frac{P_{exports}}{P_{imports}}",
                "Commodity exporters benefit when TOT improves.",
            ),
        ),
        screens=(
            "Inventory trend vs seasonal norms",
            "Curve not in severe contango for long ETF holds",
            "USD direction consistent with thesis",
            "Geopolitical premium sized, not ignored",
            "Margin and roll schedule understood",
        ),
        traps=(
            "Contango bleed in long-only commodity ETFs",
            "Single inventory print over-interpreted",
            "Equity commodity proxies with idiosyncratic ops risk",
            "Leveraged futures blow-ups",
        ),
        catalysts=(
            "OPEC decision / SPR release",
            "Weather shock (hurricanes, drought)",
            "China stimulus driving metals demand",
        ),
        fate_hook="Commodity macro contextual; energy sector ranks in equity pipeline. Real-rate framing links to `regime_detector.py`.",
        related=("inflation", "global_macro", "precious_metals", "sector_rotation"),
        further_reading=(
            "Daniel Yergin — The Prize (energy)",
            "Gorton & Rouwenhorst — commodity futures as asset class",
        ),
    )
)

register(
    DeepChapter(
        topic_id="interest_rate",
        title="Interest-Rate Macro",
        family="macro",
        philosophy="""
Interest rates are the economy's price of time and risk. Rate macro trades
the yield curve, central-bank path, and rate-sensitive assets — banks,
REITs, utilities, long-duration growth. Every asset competes with the
risk-free rate; when rates rise faster than earnings grow, multiples
compress. Understanding nominal vs real rates separates reflation trades
from true tightening pain.

Bond villains are equity heroes at turns: peak rates often coincide with
equity bottoms. Macro investors watch Fed funds futures, dot plots, and
term premium for edges vs stale narratives.
""".strip(),
        how_it_works="""
Trades: (1) duration — long bonds when recession priced in; short when
inflation sticky; (2) curve — steepeners (growth recovery) vs flatteners
(hiking near end); (3) credit — HY vs IG as cycle indicator; (4) equities
— rotate rate-sensitive sectors. Express via Treasuries, futures (ZN, ZB),
TIPS, or sector ETFs.

Monitor: CPI/PCE, payrolls, Fed speak, auction demand, term premium
estimates. Real rate = nominal − breakeven inflation drives gold and
growth stock relative performance.
""".strip(),
        formulas=(
            _F(
                "Real interest rate",
                r"r_{real} = r_{nominal} - \pi^e",
                "True cost of capital after inflation; drives gold and long-duration equity.",
            ),
            _F(
                "Yield spread (10y–2y)",
                r"Spread = Y_{10} - Y_{2}",
                "Classic recession indicator when negative.",
                "regime_detector.py",
            ),
            _F(
                "Duration approximation",
                r"\Delta P \approx -D \times \Delta y",
                "Bond price sensitivity to yield change; D = modified duration.",
            ),
            _F(
                "Fed funds implied path",
                r"\sum p_i \cdot r_i \text{ from OIS/futures}",
                "Market-priced rate trajectory vs your macro view.",
            ),
        ),
        screens=(
            "Real rate direction vs equity growth tilt",
            "Curve shape matches cycle call",
            "Rate-sensitive sector weights intentional",
            "Duration risk in bond sleeve sized to volatility tolerance",
            "Inflation breakevens vs CPI trend",
        ),
        traps=(
            "Fighting Fed too early",
            "Duration concentration in long bonds before supply shock",
            "Confusing nominal hike with tight real policy",
            "Reach for yield in credit ignoring cycle turn",
        ),
        catalysts=(
            "CPI surprise",
            "Fed pivot language",
            "Bank stress / credit event moving flight-to-quality",
        ),
        fate_hook="Live `yield_spread` in `regime_detector.py`; rate regime informs sector and fortress risk posture.",
        related=("inflation", "deflation", "business_cycle", "global_macro"),
        further_reading=(
            "Fabozzi — Fixed Income Analysis",
            "Ray Dalio — How the Economic Machine Works",
        ),
    )
)

register(
    DeepChapter(
        topic_id="inflation",
        title="Inflation Investing",
        family="macro",
        philosophy="""
Inflation erodes purchasing power of nominal cash and fixed coupons.
Inflation investing seeks assets that reprice, pass through costs, or
contractually adjust — TIPS, commodities, real estate, pricing-power
equities, I-bonds. The distinction between expected inflation (priced in)
and *surprise* inflation drives returns: markets prepare for 2% CPI;
portfolios win or lose on deviations.

Not all inflation is equal: demand-pull favors cyclicals; supply-shock
stagflation hurts both bonds and many stocks. Real returns matter:
nominal 8% with 6% inflation is only 2% real.
""".strip(),
        how_it_works="""
Hedges: TIPS (principal adjusts with CPI), commodity exposure, REITs with
rent escalators, short-duration bonds, floating-rate debt, equities with
wide moats and pricing power. Avoid long nominal Treasuries and fixed-rate
long bonds in sustained surprise inflation.

Equity sectors: energy, materials often lead early inflation; staples with
pricing power hold margins; long-duration growth suffers as discount rates
rise. Monitor breakevens, wage growth, shelter CPI, and fiscal impulse.
""".strip(),
        formulas=(
            _F(
                "Fisher equation",
                r"r_{nominal} \approx r_{real} + \pi^e",
                "Nominal rates embed inflation expectations.",
            ),
            _F(
                "Real return",
                r"R_{real} = \frac{1 + R_{nominal}}{1 + \pi} - 1",
                "Purchasing power gain after inflation.",
            ),
            _F(
                "TIPS breakeven",
                r"BE = Y_{nominal} - Y_{TIPS}",
                "Market-implied CPI over bond life.",
            ),
        ),
        screens=(
            "Breakevens rising vs Fed target — hedge tilt",
            "Pricing power: gross margin stability in CPI spikes",
            "Real asset weight vs mandate",
            "Debt structure: fixed vs floating at issuer level",
            "Geographic mix (high-inflation EM exposure)",
        ),
        traps=(
            "Commodity hedge in contango bleed",
            "REITs hit by rates even with inflation",
            "Wage-price spiral over-modeled from one print",
            "TIPS illiquidity in stress",
        ),
        catalysts=(
            "CPI/PCE upside surprise",
            "Fiscal expansion / tariff shock",
            "Oil supply disruption",
        ),
        fate_hook="Inflation regime feeds macro context in `regime_detector.py`; value/quality screens favor pricing-power names.",
        related=("commodity_macro", "interest_rate", "precious_metals", "real_estate"),
        further_reading=(
            "Bernanke — inflation targeting literature",
            "Ilmanen — Expected Returns (inflation regimes)",
        ),
    )
)

register(
    DeepChapter(
        topic_id="deflation",
        title="Deflation Hedging",
        family="macro",
        philosophy="""
Deflation — falling general prices — raises the real burden of debt and
punishes leveraged cyclicals. Cash becomes king; long-duration nominal
bonds rally as rates fall; high-quality franchises with pricing power
survive better than commodity producers and indebted consumers. Deflation
is rarer in modern fiat regimes but appears in deleveraging cycles
(Japan, 2008–09 scare, pandemic demand shock).

Hedging deflation means owning what benefits from lower rates and stable
nominal claims, while avoiding assets whose cash flows collapse when
prices and wages fall.
""".strip(),
        how_it_works="""
Portfolio tilt: lengthen Treasury duration, quality investment-grade credit,
defensive equities (staples, healthcare), raise cash, reduce commodity and
high-beta cyclicals. Short or avoid highly leveraged banks and junk credit.

Signals: core CPI persistently below target, negative output gap, debt
deleveraging, bank tightening credit. Japan lesson: equity multiples can
stay compressed for decades in mild deflation — don't assume V-recovery.
""".strip(),
        formulas=(
            _F(
                "Debt deflation spiral",
                r"Real\ debt \uparrow \text{ as } P \downarrow \Rightarrow defaults \uparrow",
                "Fisher debt-deflation mechanism stresses leveraged balance sheets.",
            ),
            _F(
                "Bond rally in deflation",
                r"P \uparrow \text{ as } y \downarrow \quad (\Delta P \approx -D \cdot \Delta y)",
                "Duration assets outperform in falling-rate deflation.",
            ),
        ),
        screens=(
            "Core inflation trend below target multiple prints",
            "Quality balance sheets; low net debt / EBITDA",
            "Duration in fixed income sleeve elevated within risk limit",
            "Cyclical and commodity underweight",
            "Liquidity buffer for opportunistic deployment",
        ),
        traps=(
            "Confusing disinflation (slowing CPI) with debt-crushing deflation",
            "Reach for yield in HY before defaults wave",
            "Assuming Fed cannot respond with QE/fiscal",
            "Illiquid assets trapped in deleveraging",
        ),
        catalysts=(
            "Credit crunch / bank pullback",
            "Demand collapse shock",
            "Policy mistake tightening into slack",
        ),
        fate_hook="Risk-off regime in `regime_detector.py` aligns with deflation hedges; fortress can raise cash and quality tilt.",
        related=("interest_rate", "deflation", "bear_strategies", "business_cycle"),
        further_reading=(
            "Irving Fisher — debt-deflation theory",
            "Richard Koo — balance sheet recession",
        ),
    )
)

register(
    DeepChapter(
        topic_id="business_cycle",
        title="Business Cycle Investing",
        family="macro",
        philosophy="""
The business cycle — expansion, peak, contraction, trough — rotates
which sectors, factors, and credit instruments outperform. Early cycle
favors cyclicals and credit risk; late cycle favors defensives and quality;
recession favors Treasuries and staples. No one rings a bell at peaks, but
leading indicators (LEI, yield curve, hours worked, lending standards)
shift probabilities. Cycle investing is Bayesian updating, not prophecy.

Missing a cycle turn hurts less than fighting the prevailing phase with
max conviction. Blend cycle awareness with security selection: even in
recession some stocks compound; even in boom some go bust.
""".strip(),
        how_it_works="""
Map indicators to phase: LEI falling + curve inverted → late/recession
playbook. Rotate sector weights (industrials, financials early; utilities,
healthcare late). Adjust factor tilts (momentum in mid-cycle; quality in
late). Credit: widen spreads → reduce HY; tighten → add carefully.

FATE ties cycle to `regime_hmm` and sector rotation formulas. Rebalance
on signal persistence, not single data prints. Earnings revision breadth
across GICS sectors confirms rotation thesis.
""".strip(),
        formulas=(
            _F(
                "Output gap",
                r"Gap = \frac{Y - Y^*}{Y^*}",
                "Positive gap late-cycle inflationary; negative gap slack.",
            ),
            _F(
                "Sector rotation signal",
                r"Rotate\ to\ sector\ with\ max(RS_{6m}) \cap earnings\ breadth^{+}",
                "Relative strength plus fundamental confirmation.",
                "investing.formulas.sector",
            ),
            _F(
                "Regime HMM",
                r"S_t \in \{expansion, slowdown, recession, recovery\}",
                "Probabilistic phase classification.",
                "regime_detector.py",
            ),
        ),
        screens=(
            "≥ 2 leading indicators agree on phase shift",
            "Sector weights within 5% of policy targets post-rotation",
            "Credit exposure matches phase (HY underweight late)",
            "Earnings revisions broadening/narrowing tracked",
            "Drawdown plan if phase call wrong",
        ),
        traps=(
            "Lagging indicators — employment peaks after stocks",
            "False recession calls (2011, 2016 mini-scares)",
            "Over-trading rotations — taxes and whipsaw",
            "Ignoring global cycle desync (US vs Europe)",
        ),
        catalysts=(
            "LEI inflection",
            "Fed easing into trough",
            "Fiscal stimulus at recession",
        ),
        fate_hook="Live `regime_hmm` + sector rotation in `regime_detector.py` / `investing.formulas.sector`; drives tactical sector tilts.",
        related=("top_down", "sector_rotation", "global_macro", "tactical_aa"),
        further_reading=(
            "Burns & Mitchell — cycle measurement",
            "NBER business cycle dating methodology",
        ),
    )
)
