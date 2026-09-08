"""Advanced strategies / analysis methods — deep chapters."""

from __future__ import annotations

from investing.knowledge import DeepChapter, FormulaSpec, register

_F = FormulaSpec

# --- advanced family ---

register(
    DeepChapter(
        topic_id="merger_arb",
        title="Merger Arbitrage",
        family="advanced",
        philosophy="""
Merger arbitrage buys the target stock after a deal is announced, earning
the spread to the offer price if the transaction closes. You are selling
insurance against deal break — compensated for regulatory risk, financing
failure, shareholder vote loss, and macro shocks that kill M&A appetite.
Philosophy: repeat many small positive spreads with rigorous break
probability analysis beats betting on one heroic deal.

This is not risk-free: broken deals can gap down 30–50%. Position sizing
and diversification across uncorrelated deals are core to survival.
""".strip(),
        how_it_works="""
Workflow: screen announced deals → compute gross spread and annualized
return → estimate break probability from precedent, antitrust, financing,
vote math → size inversely to risk → monitor milestones (HSR, proxy, close
date). Stock-for-stock deals may require hedge on acquirer.

Types: cash deals (simpler), stock deals (hedge ratio), hostile (higher
break risk), strategic vs financial buyer. Legal timeline drives IRR —
delayed close compresses annualized return but may widen spread opportunity.
""".strip(),
        formulas=(
            _F(
                "Merger spread",
                r"Spread = \frac{Deal\ Price - P}{P}",
                "Gross profit if deal closes at stated terms.",
            ),
            _F(
                "Annualized spread",
                r"Ann = \left(1 + Spread\right)^{365/days} - 1",
                "Compare deals on time-adjusted basis.",
            ),
            _F(
                "Expected return",
                r"E[R] = p_{close} \cdot Spread + (1-p_{close}) \cdot Loss_{break}",
                "Probability-weighted outcome — heart of risk arb.",
            ),
        ),
        screens=(
            "Spread compensates for estimated break risk",
            "Antitrust path plausible (no direct overlap red flag)",
            "Financing committed for LBO",
            "Vote threshold achievable",
            "Diversify ≥ 8–15 deals",
        ),
        traps=(
            "Concentration in one break wiping year",
            "Ignoring material adverse change clauses",
            "Stock deal acquirer collapse unhedged",
            "Regulatory surprise (FTC block)",
        ),
        catalysts=("Proxy approval", "regulatory clearance", "early close"),
        fate_hook="Knowledge; event-driven trading and earnings evaluator flag catalysts; special_situations overlap.",
        related=("special_situations", "event_driven", "distressed_debt"),
        further_reading=("Moore — Merger Arbitrage", "Mitchell & Pulvino — deal risk studies"),
    )
)

register(
    DeepChapter(
        topic_id="convertible_arb",
        title="Convertible Arbitrage",
        family="advanced",
        philosophy="""
Convertible arbitrage buys convertible bonds (debt + embedded equity option)
and hedges the equity delta by shorting common stock — harvesting volatility,
credit spread, and cheap optionality. Philosophy: extract mispriced convexity
while staying roughly neutral to small stock moves. Requires dynamic hedging:
as stock rises, delta rises → short more; as stock falls, cover shorts.

A specialist strategy — borrow, corporate credit, and vol modeling must be
world-class. Retail access limited; concept still educates on bond-equity
linkage and gamma.
""".strip(),
        how_it_works="""
Buy convert → compute delta from option model → short stock to neutralize
→ earn coupon minus borrow cost plus trading gamma (profit from hedging
stock swings). Credit hedge optional (CDS) if issuer fragile. Catalysts:
repricing on earnings, takeout premium, vol crush.

Risks: credit event (stock gaps down through hedge), hard borrow, vol
collapse hurting option value. Portfolio many small positions diversifies
issuer risk.
""".strip(),
        formulas=(
            _F(
                "Convert delta hedge",
                r"Shares_{short} = \Delta \times \frac{Par}{Conversion\ ratio}",
                "Neutralize small moves in underlying.",
            ),
            _F(
                "Conversion parity",
                r"Parity = \frac{Stock \times Par}{Conversion\ price}",
                "Bond price vs equity-linked fair value.",
            ),
            _F(
                "Gamma P&L (concept)",
                r"P\&L_{\gamma} \approx \tfrac{1}{2}\Gamma (\Delta S)^2",
                "Profit from re-hedging as stock moves.",
            ),
        ),
        screens=(
            "Cheap vol vs realized history",
            "Credit spread compensates default risk",
            "Borrow available on hedge leg",
            "Liquidity in convert and stock",
            "Issuer diversification",
        ),
        traps=(
            "Credit blow-up (stock down, convert down, short wins insufficient)",
            "Gamma scalping costs exceed edge",
            "Forced short cover in squeeze",
            "Illiquid converts mark stale",
        ),
        catalysts=("Vol expansion", "takeout bid", "credit upgrade"),
        fate_hook="Knowledge chapter; options Greeks in `investing.formulas.options`.",
        related=("options", "volatility_trading", "distressed_debt"),
        further_reading=("Calamos — convertible investing", "Agarwal & Naik — convert arb returns"),
    )
)

register(
    DeepChapter(
        topic_id="volatility_trading",
        title="Volatility Trading",
        family="advanced",
        philosophy="""
Volatility trading expresses views on realized vs implied volatility — not
direction per se. Options imply a breakeven move (IV); if realized vol is
lower, systematic sellers collect premium; if shocks arrive, long vol pays.
Philosophy: vol is mean-reverting but fat-tailed — short vol earns steady
small gains interrupted by rare large losses (volmageddon).

Understand VIX as sentiment gauge, not investable asset long term. Position
size for tail risk when short; define max loss when long (theta bleed).
""".strip(),
        how_it_works="""
Strategies: (1) short strangles/iron condors when IV rich vs forecast,
(2) long straddles into events when IV cheap vs expected move, (3) variance
swaps at institutional level, (4) VIX futures term structure trades
(contango roll down). Hedge with spreads to cap tail.

Monitor skew, term structure, and correlation. Earnings: compare implied
move to historical realized. Risk: gap opens blow short vol; long vol bleeds
in calm summers.
""".strip(),
        formulas=(
            _F(
                "Implied vs realized",
                r"Edge \propto IV - RV_{forecast}",
                "Sell when IV overstates expected realized; buy when understated.",
            ),
            _F(
                "Straddle breakeven",
                r"BE_{\uparrow} = S_0 + Premium, \quad BE_{\downarrow} = S_0 - Premium",
                "Underlying must move beyond total premium paid.",
            ),
            _F(
                "Vega exposure",
                r"\Delta P \approx \mathcal{V} \cdot \Delta \sigma",
                "Option value sensitivity to implied vol change.",
                "investing.formulas.options",
            ),
        ),
        screens=(
            "IV percentile vs 1-year range",
            "Event implied move vs historical earnings move",
            "Position defined-risk (spreads not naked)",
            "Margin stress test on +10 VIX points",
            "Theta budget for long vol holds",
        ),
        traps=(
            "Short vol unlimited tail (Feb 2018)",
            "Long vol theta decay in quiet markets",
            "Misreading VIX futures roll cost",
            "Over-leveraged iron condors at lows",
        ),
        catalysts=("CPI/FOMC surprise", "geopolitical gap", "earnings shock"),
        fate_hook="Options formulas soft in `investing.formulas.options`; HFT vol signals separate stack.",
        related=("options", "bear_strategies", "event_driven"),
        further_reading=("Sinclair — Volatility Trading", "CBOE VIX white papers"),
    )
)

register(
    DeepChapter(
        topic_id="distressed_debt",
        title="Distressed Debt",
        family="advanced",
        philosophy="""
Distressed debt buys bonds, loans, or claims of troubled issuers trading
well below par, betting on recovery via restructuring, asset sales, or
improved operations. Philosophy: bankruptcy is a process, not an endpoint —
legal rules create claims hierarchy (secured > unsecured > equity) and
negotiation windows where informed capital earns outsized returns. Requires
credit, legal, and game-theory fluency.

Losses are real when recovery is zero; diversification and seniority matter.
Public market proxy: HY spreads widening, CCC bucket, post-reorg equities.
""".strip(),
        how_it_works="""
Screen 13D/8-K, missed coupons, exchange offers, Ch. 11 filings. Model
enterprise value scenarios → allocate to debt tranches → compare to bond
price. Trade bank debt, bonds, or post-reorg equity (GORO). Fulcrum security
converts to equity in reorg.

Timeline: months to years in court. Liquidity dries — position sizing for
hold. Catalysts: DIP financing, 363 sale, plan confirmation.
""".strip(),
        formulas=(
            _F(
                "Recovery rate",
                r"Recovery = \frac{Proceeds\ to\ tranche}{Face\ value}",
                "Central underwriting variable.",
            ),
            _F(
                "Yield to maturity (distressed)",
                r"YTM \approx \frac{Coupon + (Par - P)/years}{P}",
                "Simplified current yield on deep discount.",
            ),
            _F(
                "Fulcrum concept",
                r"Tranche\ where\ EV \approx Claim\ amount",
                "Often becomes equity in restructuring.",
            ),
        ),
        screens=(
            "Seniority appropriate for scenario",
            "Collateral coverage in liquidation case",
            "Legal counsel quality on restructuring",
            "Liquidity for exit or hold to plan",
            "Issuer industry salvageable demand",
        ),
        traps=(
            "Buying subordinated with no recovery",
            "Fighting secured lenders in court without resources",
            "Illiquidity trapping capital",
            "Equitization wipe of junior debt",
        ),
        catalysts=("Plan confirmation", "363 asset sale", "economic upturn lifting EV"),
        fate_hook="Knowledge; turnaround and contrarian equity screens overlap distressed candidates.",
        related=("turnaround", "special_situations", "private_equity"),
        further_reading=("Moyer — Distressed Debt Analysis", "Rosenberg — Vulture Investors"),
    )
)

register(
    DeepChapter(
        topic_id="leveraged_investing",
        title="Leveraged Investing",
        family="advanced",
        philosophy="""
Leverage amplifies exposure via margin, derivatives, or leveraged ETFs —
magnifying gains and losses and introducing path dependency. Philosophy:
leverage is a tool, not a strategy; use only when edge and risk management
are explicit. Borrowing at rate r to earn return R works when R > r
consistently, but volatility triggers margin calls before long-run averages
materialize.

Kelly and fractional Kelly frame sizing; most investors should use far
less than theoretical optimum.
""".strip(),
        how_it_works="""
Channels: brokerage margin (Reg T 50% initial), portfolio margin for
sophisticates, futures notional, LEAPS, 2×/3× ETFs (daily reset). Monitor
maintenance margin, interest expense, and drawdown triggers.

De-lever before forced liquidation. Pair leverage with hedges or strict
stops. LBO is corporate leverage; personal leverage is personal bankruptcy
risk.
""".strip(),
        formulas=(
            _F(
                "Leveraged return",
                r"R_{lev} \approx LR \cdot R_{asset} - (L-1) \cdot r_{borrow}",
                "L = leverage multiple; borrow cost drags.",
            ),
            _F(
                "Margin call threshold",
                r"Equity\% = \frac{Assets - Debt}{Assets} < maintenance \Rightarrow call",
                "Forced sale at worst prices.",
            ),
            _F(
                "Kelly fraction",
                r"f^* = \frac{p \cdot b - q}{b}",
                "Theoretical optimal bet size; use fraction in practice.",
                "investing.formulas.quant.kelly_fraction",
            ),
        ),
        screens=(
            "Leverage ratio within written policy max",
            "Borrow rate and margin interest known",
            "Stress test −30% asset move survivable",
            "No leverage on illiquid holdings",
            "Emergency liquidity reserve outside margin",
        ),
        traps=(
            "Margin call cascade",
            "Leveraged ETF decay in chop",
            "Concentrated bet + leverage = ruin",
            "Ignoring correlation in portfolio margin",
        ),
        catalysts=("Vol collapse enabling cheaper leverage", "refinance lower borrow rate"),
        fate_hook="Risk formulas in `investing.formulas.risk`; fortress monitors drawdown limits.",
        related=("private_equity", "inverse_etfs", "portfolio_optimization"),
        further_reading=("Thorp — Kelly criterion", "SEC margin disclosure"),
    )
)

register(
    DeepChapter(
        topic_id="esg",
        title="ESG Investing",
        family="advanced",
        philosophy="""
ESG integrates environmental, social, and governance criteria with financial
analysis — reflecting values, regulatory trajectory, and evidence that
governance quality and risk management affect long-run returns. Philosophy:
not all ESG scores are equal; avoid box-checking. Materiality differs by
sector — carbon for utilities, data privacy for tech, labor for retail.

ESG is not automatically lower return; exclusions may tilt away from
sin stocks that historically carried premia. Clarify whether goal is impact,
risk reduction, or regulatory compliance.
""".strip(),
        how_it_works="""
Approaches: negative screening (exclude tobacco, weapons), positive tilt
(best-in-class), integration (ESG inputs to DCF risk), thematic (clean energy),
engagement (proxy voting). Data from MSCI, Sustainalytics, ISS — compare
methodologies.

Watch greenwashing, inconsistent ratings, and carbon accounting boundaries
(Scope 1–3). Regulatory: EU SFDR, SEC climate disclosure evolving.
""".strip(),
        formulas=(
            _F(
                "Carbon intensity",
                r"CI = \frac{Scope\ 1+2\ emissions}{Revenue}",
                "Normalize emissions for comparability.",
            ),
            _F(
                "ESG tilt portfolio",
                r"w_i \propto w_{bench,i} \times ESG\_score_i^{+}",
                "Overweight high ESG within sector neutrality optional.",
            ),
        ),
        screens=(
            "Material ESG risks mapped to financial statements",
            "Rating agency methodology understood",
            "Engagement policy for proxy season",
            "Track record vs benchmark on risk-adjusted basis",
            "Avoid concentration in ESG marketing narratives",
        ),
        traps=(
            "Rating divergence — same company different scores",
            "Exclusion tracking error vs benchmark",
            "Impact washing without measurement",
            "Ignoring governance in favor of E scores alone",
        ),
        catalysts=("Regulatory mandate", "customer ESG demand", "cost of capital penalty for laggards"),
        fate_hook="Knowledge; governance proxies in quality/Buffett scores partially overlap G pillar.",
        related=("buffett", "qualitative", "thematic_investing"),
        further_reading=("PRI — Principles for Responsible Investment", "Aswath Damodaran — ESG and value"),
    )
)

register(
    DeepChapter(
        topic_id="thematic_investing",
        title="Thematic Investing",
        family="advanced",
        philosophy="""
Thematic investing builds portfolios around structural narratives — AI,
electrification, aging demographics, water scarcity — cutting across GICS
sectors. Philosophy: identify durable megatrends, not quarterly fads.
Themes can be right macro but wrong entry (bubble) or wrong picks (losers
in winning industry). Diversify within theme; size satellite sleeve modestly.

Contrast with sector rotation: themes are multi-sector; sectors are single
GICS bucket. Hype cycles peak when ETFs launch with 'AI' in name.
""".strip(),
        how_it_works="""
Map theme to revenue exposure (not just marketing). Use supply chain leaders,
picks-and-shovels, and beneficiaries at each adoption S-curve stage. ETF
themes offer quick exposure; stock picking offers precision with idiosyncratic
risk.

Monitor adoption metrics, policy subsidies, and competitive moats. Rebalance
when valuations embed perfection. Pair with core index for balance.
""".strip(),
        formulas=(
            _F(
                "Theme revenue exposure",
                r"Exposure = \frac{Revenue_{theme}}{Revenue_{total}}",
                "Pure-play vs conglomerate dilution.",
            ),
            _F(
                "TAM penetration",
                r"Penetration = \frac{Current\ market}{TAM}",
                "Early vs late theme stage indicator.",
            ),
        ),
        screens=(
            "Theme durable ≥ 5–10 year horizon",
            "Valuation not pricing infinite penetration",
            "Multiple holdings — not single poster child",
            "Revenue exposure verified in filings",
            "Policy/regulatory tailwind or neutrality",
        ),
        traps=(
            "Theme ETF launched at peak",
            "Conglomerate rebranding as 'AI stock'",
            "Concentration in one sub-theme",
            "Ignoring rate sensitivity of long-duration theme stocks",
        ),
        catalysts=("Adoption inflection", "subsidy passage", "cost curve breakthrough"),
        fate_hook="Sector extended topics (ai, cloud) and growth ranks support thematic tilts in satellite sleeve.",
        related=("secular_growth", "innovation", "core_satellite", "sector_rotation"),
        further_reading=("McKinsey thematic reports", "ARK research style with skepticism"),
    )
)

register(
    DeepChapter(
        topic_id="tactical_aa",
        title="Tactical Asset Allocation",
        family="advanced",
        philosophy="""
Tactical asset allocation (TAA) shifts portfolio weights among stocks, bonds,
cash, and alternatives based on short- to medium-term outlooks — deviating
from strategic policy weights when signals justify. Philosophy: modest timing
edge can compound if disciplined; hubris destroys. Most investors should
limit tactical bands (±5–10%) to avoid whipsaw and taxes.

TAA is not market timing heroics — it's risk management when valuations,
rates, or sentiment reach extremes.
""".strip(),
        how_it_works="""
Start from strategic weights (60/40). Apply signals: CAPE high → trim equity
5%; yield curve inverted → add duration; VIX spike → rebalance into equities
if policy says buy fear. Use rules, not headlines. Transaction costs and
taxes cap turnover.

Implement via ETF sleeves, futures for liquidity, or cash buffer. Document
triggers in IPS. Review hit rate — if tactical moves lag, shrink bands.
""".strip(),
        formulas=(
            _F(
                "Tactical band",
                r"w_i \in [w_i^* - \Delta,\ w_i^* + \Delta]",
                "Policy weight ± tactical delta.",
            ),
            _F(
                "Sharpe of timing",
                r"Sharpe_{TAA} = \frac{E[R_{TAA} - R_{strategic}]}{\sigma(\Delta R)}",
                "Measure whether tactics add risk-adjusted value.",
                "investing.formulas.risk.sharpe_ratio",
            ),
        ),
        screens=(
            "Pre-defined signals in IPS",
            "Turnover budget annually",
            "Tax impact estimated before trade",
            "Bands not exceeded without committee/review",
            "Track record vs strategic buy-and-hold",
        ),
        traps=(
            "Chasing last quarter's winner sleeve",
            "Over-trading on noise",
            "No reversion to strategic weights",
            "Behavioral timing (sell low buy high)",
        ),
        catalysts=("Valuation extreme", "vol spike", "regime shift in `regime_detector`"),
        fate_hook="`regime_detector.py` and fortress overlays inform tactical tilts within bands.",
        related=("strategic_aa", "business_cycle", "global_macro", "sector_rotation"),
        further_reading=("Faber — tactical allocation research", "GMO valuation-based TAA"),
    )
)

register(
    DeepChapter(
        topic_id="strategic_aa",
        title="Strategic Asset Allocation",
        family="advanced",
        philosophy="""
Strategic asset allocation sets long-run policy weights matched to goals,
horizon, and risk tolerance — the portfolio's constitution. Philosophy:
time in each asset class, not timing, drives most outcomes. Rebalance when
drift exceeds bands to sell winners and buy laggards mechanically. CAPM
and mean-variance inform expected return and risk tradeoffs, but estimation
error means simple robust policies often beat ornate optimization.

Strategic is the anchor; tactical is the optional overlay.
""".strip(),
        how_it_works="""
Define objectives (retirement, endowment). Estimate expected returns, vol,
correlations → solve for weights on efficient frontier or use rule-of-thumb
(age in bonds). Implement with low-cost funds. Rebalance calendar or threshold.

Review annually — not monthly. Change strategic weights only when life
circumstances change, not after one bad year.
""".strip(),
        formulas=(
            _F(
                "CAPM expected return",
                r"E[R_i] = r_f + \beta_i (E[R_m] - r_f)",
                "Baseline equity return given beta.",
                "investing.formulas.risk.capm_beta",
            ),
            _F(
                "Sharpe ratio",
                r"Sharpe = \frac{E[R_p - r_f]}{\sigma_p}",
                "Risk-adjusted return for allocation comparison.",
                "investing.formulas.risk.sharpe_ratio",
            ),
            _F(
                "Portfolio return",
                r"R_p = \sum_i w_i R_i",
                "Weighted sum of asset class returns.",
            ),
        ),
        screens=(
            "IPS documents policy weights",
            "Rebalance rule defined",
            "Tax location optimized",
            "Emergency fund outside strategic portfolio",
            "Risk tolerance questionnaire on file",
        ),
        traps=(
            "Abandoning policy at market bottom",
            "Optimization with garbage covariance inputs",
            "Home country bias",
            "Ignoring human capital (job beta)",
        ),
        catalysts=("Life event horizon change", "inheritance shifting risk capacity"),
        fate_hook="Live `capm_beta` and `sharpe_ratio` in `investing.formulas.risk`; fortress uses policy weights.",
        related=("portfolio_optimization", "tactical_aa", "lazy_portfolios", "multi_asset"),
        further_reading=("Brinson — asset allocation determinants", "Ibbotson SBBI yearbook"),
    )
)

register(
    DeepChapter(
        topic_id="portfolio_optimization",
        title="Portfolio Optimization",
        family="advanced",
        philosophy="""
Portfolio optimization solves for weights maximizing risk-adjusted return
subject to constraints — classic Markowitz mean-variance and extensions
(risk parity, Black-Litterman, robust optimization). Philosophy: inputs
dominate outputs; expected returns are estimated badly, so optimizers
chase noise (error maximization). Use optimization for discipline and
risk budgeting, not oracle weights.

Shrinkage covariances, resampling, and constraints (max weight, sector caps)
make solutions usable.
""".strip(),
        how_it_works="""
Estimate μ (returns), Σ (covariance) from history or models → solve
max Sharpe or min variance → apply constraints → implement → monitor drift.
Black-Litterman blends equilibrium returns with investor views. Risk parity
equalizes risk contributions instead of dollars.

Backtest out-of-sample; turnover and costs in objective. FATE uses optimization
concepts in fortress risk budgeting.
""".strip(),
        formulas=(
            _F(
                "Mean-variance objective",
                r"\max_w \frac{w^T \mu - r_f}{\sqrt{w^T \Sigma w}}",
                "Maximize Sharpe ratio portfolio.",
            ),
            _F(
                "Minimum variance",
                r"\min_w w^T \Sigma w \quad s.t. \quad \sum w_i = 1",
                "Global minimum variance portfolio.",
            ),
            _F(
                "Sharpe ratio",
                r"Sharpe = \frac{E[R_p - r_f]}{\sigma_p}",
                "Objective function scalar.",
                "investing.formulas.risk.sharpe_ratio",
            ),
        ),
        screens=(
            "Covariance matrix shrinkage applied",
            "Max single-name weight cap",
            "Out-of-sample Sharpe > in-sample sanity check",
            "Turnover penalty in optimization",
            "Constraints match mandate (long-only, sector)",
        ),
        traps=(
            "Error maximization from noisy μ",
            "Ill-conditioned covariance matrix",
            "Look-ahead bias in backtest",
            "Ignoring transaction costs",
        ),
        catalysts=("New asset class addition", "correlation regime shift"),
        fate_hook="`sharpe_ratio` and `capm_beta` live in `investing.formulas.risk`; fortress applies risk constraints.",
        related=("strategic_aa", "risk_parity", "multi_asset", "risk"),
        further_reading=("Markowitz — Portfolio Selection", "de Prado — robust optimization"),
    )
)

register(
    DeepChapter(
        topic_id="tax_loss_harvesting",
        title="Tax-Loss Harvesting",
        family="advanced",
        philosophy="""
Tax-loss harvesting sells losers to realize capital losses that offset gains
and up to $3K ordinary income (US), then rebuys similar — not identical —
exposure after wash-sale rules clear. Philosophy: after-tax return is what
you keep; harvesting adds 0.5–1.5%+ annually in taxable accounts without
changing economic exposure materially. Requires taxable account and tracking
of wash-sale windows (30 days before/after).

Do not let tax tail wag investment dog — harvest losses on positions you
would sell anyway, paired with index substitutes.
""".strip(),
        how_it_works="""
Identify lots underwater → sell → buy correlated substitute ETF (IVV ↔ VOO)
→ wait 31 days if needed → swap back or keep substitute. Automate in direct
indexing platforms. Track wash sales across accounts and spouse.

Harvest in down years to build loss carryforwards. Coordinate with year-end
gain realization. Municipal bond and IRA accounts irrelevant for this tactic.
""".strip(),
        formulas=(
            _F(
                "Tax savings",
                r"Savings = Loss \times TaxRate",
                "Offset at marginal capital gains rate.",
            ),
            _F(
                "After-tax return boost",
                r"\Delta R_{after\text{-}tax} \approx \frac{Savings}{Portfolio}",
                "Annualized benefit depends on harvest frequency.",
            ),
        ),
        screens=(
            "Taxable account only",
            "Substitute security not substantially identical",
            "Wash-sale calendar tracked",
            "Loss lots identified with specific ID",
            "Coordinate with rebalancing plan",
        ),
        traps=(
            "Wash sale disallowing loss",
            "Selling winner accidentally breaking thesis",
            "Substitute with higher expense ratio eroding benefit",
            "State tax nuances ignored",
        ),
        catalysts=("Market drawdown creating harvest opportunities", "year-end gain offset need"),
        fate_hook="Knowledge; fortress rebalancing can flag tax lots externally when integrated.",
        related=("etf_investing", "index_investing", "strategic_aa"),
        further_reading=("Kitces — tax-loss harvesting", "Vanguard direct indexing research"),
    )
)

register(
    DeepChapter(
        topic_id="sector_rotation",
        title="Sector Rotation",
        family="advanced",
        philosophy="""
Sector rotation overweights sectors expected to lead the next cycle phase
and underweights laggards — connecting macro, earnings breadth, and relative
strength. Philosophy: sectors are the right granularity between macro and
stock picking for many investors. Early cycle: financials, industrials;
late cycle: staples, healthcare; recession: utilities, Treasuries.

Timing is imperfect; partial rotation beats all-in-all-out whipsaw. The
investment clock is a map, not GPS — arrive late to a rotation and you
still may capture the middle of a phase. Avoid doubling up: if macro
already max-long cyclicals, sector rotation should not stack the same bet
without acknowledging risk budget.
""".strip(),
        how_it_works="""
Signals: business cycle phase (`regime_hmm`), PMI sector splits, earnings
revision breadth by GICS, relative strength 6–12m, yield curve. Implement
via sector ETFs (XLF, XLE, etc.) or stock screens within sectors.

Rebalance quarterly or on phase change. Cap sector concentration for risk.
Combine with bottom-up picks within leading sectors. Build a composite score:
weight RS 40%, earnings revision breadth 30%, macro phase fit 30%. Require
two consecutive months of signal agreement before full tilt to reduce
whipsaw. Track implementation shortfall — sector ETFs gap on rebalances;
use limit orders or staged trades. After rotation, measure attribution:
did the sector sleeve add value vs static benchmark?
""".strip(),
        formulas=(
            _F(
                "Sector relative strength",
                r"RS_i = \frac{P_{i,t}/P_{i,0}}{P_{SPY,t}/P_{SPY,0}}",
                "Outperformance vs benchmark over window.",
                "investing.formulas.sector",
            ),
            _F(
                "Rotation weight tilt",
                r"w_i = w_{bench,i} + \alpha \cdot signal_i",
                "Tilt toward sectors with positive composite signal.",
            ),
        ),
        screens=(
            "Cycle phase ≥ 2 indicators aligned",
            "RS and earnings revisions confirm",
            "Sector ETF liquidity adequate",
            "Max sector overweight defined (e.g. +10% vs benchmark)",
            "Transaction costs vs tilt magnitude",
        ),
        traps=(
            "Rotating after move completed",
            "Single indicator false signal",
            "Ignoring stock-specific risk within sector",
            "Tax drag in taxable accounts",
        ),
        catalysts=("PMI inflection", "Fed pivot benefiting rate-sensitive sector", "oil shock helping energy"),
        fate_hook="Soft `sector_rotation` in `investing.formulas.sector`; `regime_detector` drives phase calls.",
        related=("business_cycle", "top_down", "tactical_aa", "industry"),
        further_reading=("Stovall — Sector Investing", "Sam Stovall S&P sector guides"),
    )
)

register(
    DeepChapter(
        topic_id="multi_asset",
        title="Multi-Asset Investing",
        family="advanced",
        philosophy="""
Multi-asset investing combines equities, bonds, commodities, alternatives,
and cash in one risk-managed portfolio — seeking diversification across
drivers of return. Philosophy: correlations are unstable; diversification
works best when painful (bonds hedge equities until inflation shock). Stress
test assumptions; include assets that behave differently in crises.

Endowment model popularized illiquid alts; retail multi-asset uses liquid
ETFs and funds with simpler governance.
""".strip(),
        how_it_works="""
Define risk budget (vol target 10%). Allocate to sleeves with low historical
correlation. Rebalance. Use risk parity or strategic weights. Monitor
correlation breakdown — 2008 and 2022 taught bonds don't always hedge.

Alternatives sleeve: REITs, gold, managed futures, private equity funds
of funds. Liquidity ladder: cash for 1 year, bonds 1–5, equities long.
""".strip(),
        formulas=(
            _F(
                "Portfolio variance",
                r"\sigma_p^2 = w^T \Sigma w",
                "Diversification reduces σ if correlations < 1.",
            ),
            _F(
                "Correlation breakdown stress",
                r"\rho_{equity,bond} \rightarrow 1 \text{ in liquidity crisis}",
                "Motivation for tail hedges beyond bonds.",
            ),
        ),
        screens=(
            "≥ 4 asset classes represented",
            "Liquidity matches spending needs",
            "Stress test 2008 and 2022 paths",
            "Alternative sleeve sized for illiquidity",
            "Rebalance policy documented",
        ),
        traps=(
            "False diversification (all equity risk)",
            "Illiquid alts without liquidity premium",
            "Ignoring currency exposure in global sleeve",
            "Over-engineering for small portfolios",
        ),
        catalysts=("Correlation regime shift", "risk parity unwind creating opportunities"),
        fate_hook="Fortress multi-sleeve risk; `investing.formulas.risk` for portfolio metrics.",
        related=("strategic_aa", "risk_parity", "global_macro", "portfolio_optimization"),
        further_reading=("Bridgewater — All Weather principles", "Yale endowment reports"),
    )
)

# --- analysis family ---

register(
    DeepChapter(
        topic_id="fundamental",
        title="Fundamental Analysis",
        family="analysis",
        philosophy="""
Fundamental analysis examines financial statements, business models, and
competitive position to estimate intrinsic worth — asking what a business is
truly worth independent of daily price noise. Philosophy: price is what you
pay, value is what you get. Markets misprice when complexity, neglect, or
emotion obscure cash-flow reality. Fundamentals anchor long horizons; they
do not guarantee short-term performance.
""".strip(),
        how_it_works="""
Pipeline: understand business → analyze statements → forecast drivers →
value (DCF, comps) → compare to price → monitor thesis KPIs. Cross-check
accruals vs cash flow, capital allocation, and industry structure.

FATE `analytics.value_investing` automates core screens; human judgment
handles moat and management qualitative overlay.
""".strip(),
        formulas=(
            _F(
                "Free cash flow",
                r"FCF = CFO - CapEx",
                "Cash available after maintaining the business.",
            ),
            _F(
                "Intrinsic value",
                r"IV = \sum \frac{CF_t}{(1+r)^t} + \frac{TV}{(1+r)^n}",
                "DCF anchor for fundamentals.",
                "analytics.value_investing.intrinsic_value",
            ),
        ),
        screens=(
            "Revenue and margin drivers understood",
            "FCF positive or credible path",
            "Balance sheet supports downturn",
            "Valuation vs history and peers",
            "Thesis KPIs tracked quarterly",
        ),
        traps=(
            "Narrative without numbers",
            "Peak-cycle earnings as normal",
            "Ignoring dilution and stock comp",
            "Complexity without edge",
        ),
        catalysts=("Earnings validating thesis", "multiple expansion on proof"),
        fate_hook="Live `analytics/value_investing.py` — intrinsic value, deep value, Graham, Buffett scores.",
        related=("valuation", "financial_statement", "dcf", "bottom_up"),
        further_reading=("Graham & Dodd — Security Analysis", "McKinsey — Valuation"),
    )
)

register(
    DeepChapter(
        topic_id="technical",
        title="Technical Analysis",
        family="analysis",
        philosophy="""
Technical analysis studies price, volume, and pattern history to forecast
short- to medium-term direction — based on the idea that collective behavior
leaves footprints in charts. Philosophy: timing and risk management, not
replacement for fundamentals on multi-year holds. All information is in the
price is half-true; sentiment and liquidity show up before filings.

Use indicators as context, not oracle. Combine with stops and position sizing.
""".strip(),
        how_it_works="""
Tools: trend (moving averages, MACD), momentum (RSI), volatility (Bollinger),
structure (support/resistance, breakouts). Volume confirms moves. Multi-timeframe
analysis aligns daily entries with weekly trend.

Backtest patterns with realistic costs. FATE uses trend_ema_macd and structure
patterns in hedge fund stack for soft signals.
""".strip(),
        formulas=(
            _F(
                "RSI",
                r"RSI = 100 - \frac{100}{1 + RS}, \quad RS = \frac{Avg\ gain}{Avg\ loss}",
                "Overbought >70, oversold <30 — context not command.",
                "investing.formulas.technical.rsi",
            ),
            _F(
                "MACD",
                r"MACD = EMA_{12} - EMA_{26}",
                "Trend momentum crossover signal.",
                "investing.formulas.technical.macd",
            ),
            _F(
                "Mean reversion z-score",
                r"z = \frac{P - \mu}{\sigma}",
                "Stretch from moving average.",
                "signals.dip_momentum",
            ),
        ),
        screens=(
            "Trend direction defined on higher timeframe",
            "Volume confirms breakout",
            "Risk/reward ≥ 2:1 at entry",
            "Stop level placed before entry",
            "Not fighting strong fundamental deterioration",
        ),
        traps=(
            "Indicator overload conflicting signals",
            "Curve-fitted patterns",
            "Ignoring gap risk overnight",
            "Trading illiquid names on chart alone",
        ),
        catalysts=("Breakout on volume", "oversold bounce in uptrend"),
        fate_hook="Soft RSI/MACD in `investing.formulas.technical`; trend signals in hedge_fund_stack.",
        related=("trend_following", "mean_reversion", "breakout", "sentiment"),
        further_reading=("Murphy — Technical Analysis of Financial Markets", "Pring — Technical Analysis Explained"),
    )
)

register(
    DeepChapter(
        topic_id="quant_analysis",
        title="Quantitative Analysis",
        family="analysis",
        philosophy="""
Quantitative analysis replaces discretionary judgment with statistical models,
factor tests, and reproducible signals — demanding rigorous validation and
humility about overfitting. Philosophy: measure everything testable; invest
where evidence persists out-of-sample. Quant analysis is the research layer
behind quant investing execution, not a black box to trust blindly.

Correlation ≠ causation; multiple testing inflates false discoveries.
Pre-register hypotheses and use holdout data. A signal with t-stat 2.0 in one
decade may be noise; require economic intuition linking feature to return.
Report turnover, capacity, and drawdown paths — not just Sharpe on paper.
""".strip(),
        how_it_works="""
Universe → features → model (linear, ML, ranking) → backtest with costs →
production with monitoring. FATE: factor_value, factor_momentum, factor_quality
in hedge_fund_stack; ML horizon heads in ml_model.py.

Walk-forward validation, purged CV for overlapping labels, and regime slicing
are mandatory hygiene. Split data before and after major structural breaks
(2009, 2020). Neutralize unintended industry bets so factor scores do not
merely replicate sector momentum. Document decay: re-fit IC quarterly and
retire signals that fall below threshold. Quant analysis ends with a position
limit and a kill switch, not just a backtest chart.
""".strip(),
        formulas=(
            _F(
                "Information coefficient",
                r"IC = corr(rank(signal), rank(forward\_return))",
                "Predictive power of signal.",
            ),
            _F(
                "Factor return",
                r"R_{factor} = R_{long\ leg} - R_{short\ leg}",
                "Long-short factor portfolio return.",
                "analytics.hedge_fund_stack",
            ),
        ),
        screens=(
            "IC stable across subperiods",
            "Turnover and cost-adjusted Sharpe acceptable",
            "Signal decay half-life estimated",
            "No lookahead in fundamentals",
            "Capacity vs ADV",
        ),
        traps=(
            "Data mining 100 factors",
            "Survivorship bias",
            "Regime overfit",
            "Ignoring short availability",
        ),
        catalysts=("New validated factor", "regime where signal historically works"),
        fate_hook="Live factor and ML modules per catalog; `analytics.hedge_fund_stack.py` core.",
        related=("quant", "factor_analysis", "ml_investing", "risk"),
        further_reading=("de Prado — Advances in Financial Machine Learning",),
    )
)

register(
    DeepChapter(
        topic_id="qualitative",
        title="Qualitative Analysis",
        family="analysis",
        philosophy="""
Qualitative analysis evaluates management quality, culture, brand strength,
governance, and competitive dynamics through judgment — factors spreadsheets
capture poorly. Philosophy: two companies with identical ratios can diverge
for years based on stewardship and moat durability. Buffett's circle of
competence is qualitative: can you trust these people with your capital for
a decade?

Qualitative does not mean unverifiable — triangulate from capital allocation
history, employee reviews, customer NPS, and channel checks.
""".strip(),
        how_it_works="""
Read 10-K MD&A, proxy (comp, board), earnings calls (candor vs obfuscation).
Score management on buyback discipline, M&A track record, insider ownership.
Assess moat sources qualitatively then confirm in ROIC trends.

Red flags: auditor changes, related-party deals, promotional CEOs, empire
building. FATE transcript_factor and news_sentiment add soft qualitative signal.
""".strip(),
        formulas=(),
        screens=(
            "CEO/CFO tenure and relevant experience",
            "Insider ownership meaningful",
            "Capital allocation history value-accretive",
            "Board independence and expertise",
            "Customer and employee reputation checks",
        ),
        traps=(
            "Charisma without execution",
            "Founder cult ignoring governance",
            "Narrative investing without unit economics",
            "Confirmation bias in channel checks",
        ),
        catalysts=("Management change upgrade", "culture turnaround visible in retention"),
        fate_hook="`transcript_factor` and `news_sentiment` in sentiment_pipeline; Buffett quality score proxies governance.",
        related=("management", "economic_moat", "buffett", "esg"),
        further_reading=("Phil Fisher — scuttlebutt method", "Pat Dorsey — moat qualitative framework"),
    )
)

register(
    DeepChapter(
        topic_id="macro_analysis",
        title="Macro Analysis",
        family="analysis",
        philosophy="""
Macro analysis assesses economy-wide drivers — growth, inflation, policy,
liquidity — that frame sector and asset returns. Philosophy: you need not
forecast perfectly; avoiding major regime mistakes (max long cyclicals into
recession) often beats stock-picking alpha. Macro sets the sandbox; micro
picks the toys.

Triangulate leading, coincident, and lagging indicators; markets price
expectations, so second derivative (change in growth of growth) matters.
""".strip(),
        how_it_works="""
Monitor GDP nowcasts, payrolls, CPI, Fed funds futures, yield curve, credit
spreads, USD, oil. Map to regime (expansion, slowdown, stagflation, recovery).
Feed into sector weights and risk posture.

FATE `regime_hmm` classifies states for downstream tilts. Macro analysis
informs top-down; does not replace fundamental security work.
""".strip(),
        formulas=(
            _F(
                "Taylor rule (benchmark)",
                r"i^* \approx r^* + \pi + 0.5(\pi - \pi^*) + 0.5(y - y^*)",
                "Policy rate fair value estimate.",
            ),
            _F(
                "Regime HMM",
                r"P(S_t \mid X_t)",
                "Probabilistic macro state.",
                "regime_detector.py",
            ),
            _F(
                "Real rate",
                r"r_{real} = r_{nominal} - \pi^e",
                "Links macro to growth stock multiples and gold.",
            ),
        ),
        screens=(
            "Leading indicators weighted over lagging",
            "Cross-asset consistency check",
            "Scenario matrix documented",
            "Policy path vs market pricing gap",
            "Global not just US if portfolio global",
        ),
        traps=(
            "Single indicator obsession",
            "Fighting Fed with max leverage",
            "Confusing soft landing narrative with data",
            "Recency in extrapolating trends",
        ),
        catalysts=("CPI surprise", "NFP miss", "central bank pivot"),
        fate_hook="Live `regime_hmm` in `regime_detector.py`; yield_spread for rate macro.",
        related=("global_macro", "top_down", "business_cycle", "interest_rate"),
        further_reading=("Ray Dalio — economic machine", "BIS macro research"),
    )
)

register(
    DeepChapter(
        topic_id="industry",
        title="Industry Analysis",
        family="analysis",
        philosophy="""
Industry analysis maps sector structure, growth drivers, regulation, and
value chain economics — positioning a company within its competitive arena.
Philosophy: a great manager in a terrible industry fights gravity; industry
tailwinds lift mediocre operators. Understand TAM growth, consolidation stage,
and where profit pools sit (chip design vs fab vs OS).

Porter's five forces remain the organizing framework: rivalry, entrants,
substitutes, buyer power, supplier power.
""".strip(),
        how_it_works="""
Define industry boundaries (NAICS/GICS can mislead — use economic links).
Size TAM and growth. Map value chain margin capture. Identify regulation
and cyclicality. Compare peer set KPIs (same-store sales, ARPU, utilization).

FATE `analytics/industry_comovement.py` tracks sector co-movement for
relative trades and risk clustering.
""".strip(),
        formulas=(
            _F(
                "Herfindahl-Hirschman Index",
                r"HHI = \sum_i s_i^2",
                "Concentration measure; high HHI ⇒ oligopoly pricing potential.",
            ),
            _F(
                "Industry margin",
                r"M_{ind} = \frac{\sum EBIT}{\sum Revenue}",
                "Aggregate profitability benchmark for firms.",
            ),
        ),
        screens=(
            "TAM growth ≥ GDP or explainable share gains",
            "Profit pool shifting analysis",
            "Regulatory pipeline scanned",
            "Peer KPI comparison apples-to-apples",
            "Cycle position identified",
        ),
        traps=(
            "Defining industry too narrow (missing substitutes)",
            "Peak cycle TAM extrapolation",
            "Ignoring platform disruption from adjacent industry",
            "GICS sector ≠ economic industry",
        ),
        catalysts=("Regulatory change", "consolidation wave", "technology shift"),
        fate_hook="Live `analytics/industry_comovement.py` for sector clustering.",
        related=("competitive", "sector_rotation", "top_down"),
        further_reading=("Porter — Competitive Strategy", "McKinsey industry primers"),
    )
)

register(
    DeepChapter(
        topic_id="competitive",
        title="Competitive Analysis",
        family="analysis",
        philosophy="""
Competitive analysis compares rivals' moats, market share, pricing power, and
strategic positioning — clarifying who wins when capital floods a fashionable
sector. Philosophy: stock picking is often implicit betting on relative
competitive outcome, not just cheap multiples. Five forces and strategic
group mapping reveal whether competition will destroy returns on capital.

Winner-take-most dynamics (network effects) differ from fragmented commodity
competition — valuation multiples should differ accordingly.
""".strip(),
        how_it_works="""
Identify strategic groups (cost leaders vs differentiators). Track market
share trends, NPS, churn, pricing actions. Analyze capex races and R&D
efficiency. Read competitor earnings for demand signals.

Moat checklist: switching costs, network effects, scale, brand, regulatory
licenses. Score target vs top two rivals on each dimension.
""".strip(),
        formulas=(
            _F(
                "Market share",
                r"MS_i = \frac{Revenue_i}{\sum_j Revenue_j}",
                "Track delta MS over 3–5 years.",
            ),
            _F(
                "ROIC spread vs peers",
                r"Spread = ROIC_i - ROIC_{peer\ median}",
                "Sustained positive spread suggests advantage.",
            ),
        ),
        screens=(
            "Moat source identified and evidenced",
            "Share stable or gaining vs top rival",
            "Pricing power in inflation pass-through test",
            "Capex war not destroying industry ROIC",
            "New entrant threat assessed",
        ),
        traps=(
            "Equating size with moat",
            "Ignoring disruptive entrant from outside industry",
            "Accounting ROIC inflated by leverage",
            "Patent cliff without pipeline",
        ),
        catalysts=("Share gain quarter", "rival exit/consolidation", "pricing power demonstration"),
        fate_hook="Buffett quality and economic_moat analysis overlap; industry_comovement for peer sets.",
        related=("economic_moat", "industry", "buffett", "qualitative"),
        further_reading=("Porter — five forces", "Christensen — Innovator's Dilemma"),
    )
)

register(
    DeepChapter(
        topic_id="financial_statement",
        title="Financial Statement Analysis",
        family="analysis",
        philosophy="""
Financial statement analysis dissects income statement, balance sheet, and
cash flow for quality, trends, and red flags — because accruals can lie while
cash eventually tells truth. Philosophy: reconcile net income to free cash flow;
understand what is recurring vs one-time; read footnotes before the headline
EPS beat. Banks, insurers, and REITs need specialized templates.

Quality of earnings matters as much as quantity for valuation durability.
""".strip(),
        how_it_works="""
Income: revenue recognition, gross margin bridge, opex leverage, tax rate
sustainability. Balance sheet: liquidity, leverage, working capital swings,
off-balance sheet obligations. Cash flow: CFO vs NI, capex maintenance vs
growth, financing dependence.

Ratios: current ratio, interest coverage, cash conversion cycle, accruals
ratio (NI − CFO). FATE value_investing module ingests Yahoo fundamentals.
""".strip(),
        formulas=(
            _F(
                "Cash conversion",
                r"CCC = DIO + DSO - DPO",
                "Days cash tied in working capital.",
            ),
            _F(
                "Accruals ratio",
                r"Accruals = \frac{NI - CFO}{Total\ Assets}",
                "High positive accruals warn of low cash earnings quality.",
            ),
            _F(
                "Interest coverage",
                r"Coverage = \frac{EBIT}{Interest}",
                "Debt service safety margin.",
            ),
        ),
        screens=(
            "CFO ≥ 80% of NI over 3 years",
            "Debt maturities mapped",
            "Stock-based comp as % of revenue tracked",
            "Auditor clean opinion, no going concern",
            "Related-party transactions disclosed",
        ),
        traps=(
            "Adjusted EBITDA excluding real costs",
            "Capitalized expenses inflating earnings",
            "Channel stuffing revenue",
            "Pension assumptions smoothing NI",
        ),
        catalysts=("Cash flow inflection", "deleveraging from asset sale"),
        fate_hook="Live fundamentals via `analytics/value_investing.py` screens.",
        related=("fundamental", "valuation", "risk", "management"),
        further_reading=("Sloan — accruals anomaly", "Schilit — Financial Shenanigans"),
    )
)

register(
    DeepChapter(
        topic_id="valuation",
        title="Valuation Analysis",
        family="analysis",
        philosophy="""
Valuation analysis converts forecasts into price estimates — triangulating
DCF, trading comps, precedent transactions, and asset-based methods.
Philosophy: valuation is a range, not a point; assumptions dominate outputs.
Conservative inputs and multiple methods beat false precision. Margin of
safety closes the gap between estimate and purchase price.

Growth, risk, and reinvestment must be internally consistent — you cannot
assume high growth, high margins, and low risk simultaneously without moat
justification.
""".strip(),
        how_it_works="""
Build driver-based model (revenue, margin, capex, WC, tax) → DCF with
sensitivity table → cross-check EV/EBITDA vs peers → optional SOTP for
conglomerates → synthesize fair value range → compare to market price.

Document bear/base/bull. Update when drivers change, not when price annoys you.
""".strip(),
        formulas=(
            _F(
                "DCF intrinsic value",
                r"IV = \sum \frac{FCF_t}{(1+WACC)^t} + \frac{TV}{(1+WACC)^n}",
                "Enterprise DCF; equity = EV − net debt.",
                "analytics.value_investing.intrinsic_value",
            ),
            _F(
                "EV/EBITDA",
                r"\frac{EV}{EBITDA}",
                "Primary trading multiple for many industries.",
                "investing.formulas.analysis.ev_ebitda",
            ),
            _F(
                "Margin of safety",
                r"MOS = \frac{IV - P}{IV}",
                "Purchase discipline.",
                "analytics.value_investing.margin_of_safety",
            ),
            _F(
                "WACC",
                r"WACC = \frac{E}{V}r_e + \frac{D}{V}r_d(1-T)",
                "Discount rate for DCF.",
                "investing.formulas.analysis.wacc",
            ),
        ),
        screens=(
            "Triangulation ≥ 2 methods within reasonable spread",
            "Sensitivity on WACC and terminal growth",
            "Peer comps truly comparable",
            "Terminal value < 70% of EV unless justified",
            "MOS hurdle met for buys",
        ),
        traps=(
            "Hockey-stick terminal growth",
            "Comps from bubble peers",
            "Ignoring net debt and dilution",
            "Circular logic (using price to justify price)",
        ),
        catalysts=("Market re-rating toward fair value", "catalyst unlocking SOTP"),
        fate_hook="Live intrinsic_value, margin_of_safety, ev_ebitda, wacc across value and formulas modules.",
        related=("dcf", "wacc", "comps", "intrinsic_value"),
        further_reading=("Damodaran on Valuation", "McKinsey — Valuation"),
    )
)

register(
    DeepChapter(
        topic_id="risk",
        title="Risk Analysis",
        family="analysis",
        philosophy="""
Risk analysis quantifies volatility, drawdown, factor exposures, and tail
scenarios for sizing and hedging — asking whether return compensates for
risk taken. Philosophy: return without risk context is meaningless; survival
enables compounding. Risk is multidimensional: market beta, credit, liquidity,
concentration, and model risk differ.

VaR and Sharpe are tools, not answers. Stress tests and scenario analysis
capture fat tails mean-variance misses.
""".strip(),
        how_it_works="""
Estimate beta, vol, correlation matrix. Compute Sharpe, Sortino, max drawdown.
Decompose factor exposures (Fama-French, momentum). Run scenarios (rates +200bp,
recession EPS −30%). Set position limits from worst-case loss tolerance.

FATE `investing.formulas.risk` implements CAPM beta and Sharpe; fortress
enforces live risk budgets.
""".strip(),
        formulas=(
            _F(
                "CAPM beta",
                r"\beta_i = \frac{Cov(R_i, R_m)}{Var(R_m)}",
                "Market sensitivity for hedging and expected return.",
                "investing.formulas.risk.capm_beta",
            ),
            _F(
                "Sharpe ratio",
                r"Sharpe = \frac{E[R - r_f]}{\sigma}",
                "Return per unit total risk.",
                "investing.formulas.risk.sharpe_ratio",
            ),
            _F(
                "Max drawdown",
                r"MDD = \max_t \frac{Peak_t - Value_t}{Peak_t}",
                "Worst peak-to-trough loss path.",
            ),
            _F(
                "Value at Risk (concept)",
                r"VaR_\alpha = \inf\{l : P(Loss \leq l) \geq \alpha\}",
                "Loss threshold at confidence α — know limitations.",
            ),
        ),
        screens=(
            "Portfolio beta within mandate",
            "Max single-name weight cap",
            "Stress loss < survivability threshold",
            "Liquidity days-to-exit estimated",
            "Factor crowding monitored",
        ),
        traps=(
            "VaR false comfort in fat tails",
            "Historical vol underestimating regime shift",
            "Ignoring correlation spike in crisis",
            "Leverage hidden in derivatives",
        ),
        catalysts=("Vol regime drop enabling size increase", "hedge payoff in stress"),
        fate_hook="Live `capm_beta`, `sharpe_ratio` in `investing.formulas.risk`; fortress risk loop.",
        related=("portfolio_optimization", "strategic_aa", "scenario", "monte_carlo"),
        further_reading=(
            "Lo — adaptive markets",
            "Taleb — black swan (skeptical risk)",
        ),
    )
)

register(
    DeepChapter(
        topic_id="sentiment",
        title="Sentiment Analysis",
        family="analysis",
        philosophy="""
Sentiment analysis gauges market mood from news, social media, surveys, and
positioning — extreme bullishness or fear often marks turning points when
fundamentals lag price. Philosophy: markets are reflexive; positioning can
become causal (forced covering, panic selling). Sentiment is a contrarian
input at extremes, not a standalone strategy in the middle of the range.

Combine with fundamentals — cheap and hated beats cheap and forgotten vs
cheap and still beloved.
""".strip(),
        how_it_works="""
Sources: news NLP, Twitter/Reddit volume, AAII survey, put/call ratio, fund
flows, short interest. Score sentiment z-score vs history. FATE `news_sentiment`
and transcript factors in sentiment_pipeline.

Use as overlay: reduce size when euphoric, add when capitulation with intact
thesis. Avoid fading strong trends on mild sentiment readings alone.
""".strip(),
        formulas=(
            _F(
                "Sentiment z-score",
                r"z = \frac{S - \mu_S}{\sigma_S}",
                "Extreme positive/negative flags potential reversal.",
                "sentiment_pipeline.py",
            ),
            _F(
                "Put/call ratio",
                r"PCR = \frac{Put\ volume}{Call\ volume}",
                "High PCR can indicate fear (contrarian buy signal at extremes).",
            ),
        ),
        screens=(
            "Sentiment at historical percentile >90 or <10",
            "Positioning data confirms (short interest, fund cash)",
            "Fundamental thesis still intact on fear",
            "Liquidity adequate for contrarian entry",
            "Catalyst for sentiment normalization",
        ),
        traps=(
            "Fading momentum on weak sentiment signal",
            "Social media bots distorting NLP",
            "Sentiment lagging in fast crashes",
            "Crowded contrarian trade",
        ),
        catalysts=("Capitulation volume spike", "short squeeze exhaustion", "news shock fading"),
        fate_hook="Live `news_sentiment` in `sentiment_pipeline.py`; feeds rank overlays.",
        related=("contrarian", "news_trading", "alt_data", "technical"),
        further_reading=("Baker & Wurgler — investor sentiment", "CNN Fear & Greed methodology"),
    )
)

register(
    DeepChapter(
        topic_id="alt_data",
        title="Alternative Data Analysis",
        family="analysis",
        philosophy="""
Alternative data analysis uses non-traditional datasets — satellite imagery,
web traffic, credit card panels, app downloads, job postings — to gain
informational edge before consensus updates. Philosophy: edge decays as data
commoditizes; legal and ethical compliance (MNPI, privacy) is non-negotiable.
Validate coverage bias (only US consumers, only premium cards) before trading.

Alt data supplements fundamentals; rare replaces them entirely.
""".strip(),
        how_it_works="""
Vendor or scrape → normalize → map to tickers → backtest correlation with
reported revenue → production signal with decay monitoring. FATE uses news
and transcript NLP via intel/news_factor_engine and sentiment_pipeline.

Latency matters: by the time satellite parking lot data is widely available,
alpha may be gone. Combine multiple weak alt signals for robustness.
""".strip(),
        formulas=(
            _F(
                "Nowcast error",
                r"Error = Actual\ revenue - Alt\_data\_forecast",
                "Track MAPE across quarters for signal quality.",
            ),
            _F(
                "Signal decay",
                r"IC_t = IC_0 \cdot e^{-\lambda t}",
                "Information coefficient erodes as adoption spreads.",
            ),
        ),
        screens=(
            "Legal review completed",
            "Coverage matches investable universe",
            "Out-of-sample correlation significant",
            "Decay rate estimated",
            "Vendor stability and lineage documented",
        ),
        traps=(
            "Spurious correlation in short history",
            "Privacy regulation blocking dataset",
            "Overfitting to one vendor revision",
            "MNPI contamination",
        ),
        catalysts=("Earnings confirming alt signal", "new dataset with genuine lead"),
        fate_hook="Live `news_sentiment`, `transcript_factor` in intel/news_factor_engine and sentiment_pipeline.",
        related=("ai_investing", "quant_analysis", "sentiment"),
        further_reading=("Novy-Marx — alt data cautions", "Eagle Alpha industry reports"),
    )
)

register(
    DeepChapter(
        topic_id="factor_analysis",
        title="Factor Analysis",
        family="analysis",
        philosophy="""
Factor analysis decomposes returns into systematic style exposures — value,
size, momentum, quality, low vol — explaining performance and unintended
bets. Philosophy: you may think you pick stocks, but regression says you're
long momentum and short value. Know your factor loadings to avoid surprise
drawdowns when styles rotate.

Factors are earned premia or risk compensation; crowding and regime shifts
cause multi-year droughts.
""".strip(),
        how_it_works="""
Run regressions: R_p − r_f = α + β_MKT MKT + β_SMB SMB + β_HML HML + β_UMD UMD + ε.
Interpret α as skill after factor adjustment. FATE computes factor_value,
factor_momentum, factor_quality in hedge_fund_stack for ranks.

Use for attribution monthly; adjust portfolio to target intentional tilts only.
""".strip(),
        formulas=(
            _F(
                "Fama-French regression",
                r"R_i - r_f = \alpha + \sum_k \beta_k F_k + \epsilon",
                "Multi-factor attribution framework.",
            ),
            _F(
                "Factor exposure",
                r"\beta_k = \frac{Cov(R_i, F_k)}{Var(F_k)}",
                "Sensitivity to factor return F_k.",
                "analytics.hedge_fund_stack",
            ),
        ),
        screens=(
            "Factor betas intentional vs accidental",
            "Crowding metrics for factor trade",
            "Rolling 36m attribution reviewed",
            "α significant after costs (skeptical)",
            "Correlation among factors in crisis",
        ),
        traps=(
            "Style drift undetected",
            "Double momentum via ETF stacking",
            "Data mining factors on US 1970–2010 only",
            "Ignoring transaction costs of factor tilts",
        ),
        catalysts=("Factor mean reversion after drought", "regime favoring your tilt"),
        fate_hook="Live factor_value, factor_momentum, factor_quality in `analytics.hedge_fund_stack.py`.",
        related=("factor", "quant_analysis", "risk", "smart_beta"),
        further_reading=("Fama & French — factor papers", "Ilmanen — Expected Returns"),
    )
)

register(
    DeepChapter(
        topic_id="scenario",
        title="Scenario Analysis",
        family="analysis",
        philosophy="""
Scenario analysis models outcomes under bull, base, and bear assumptions —
stress-testing thesis robustness and position sizing. Philosophy: single-point
forecasts create false confidence; ranges force intellectual honesty about
what breaks the investment. Assign probabilities conservatively; fat tails
deserve explicit bear cases even if low probability.

Scenarios link to action: buy only if bear case acceptable, not just if bull
case exciting.
""".strip(),
        how_it_works="""
Define 3–5 scenarios with drivers (revenue growth, margin, multiple, rates).
Assign probabilities summing to 100%. Compute equity value per scenario →
expected value = Σ p_i V_i. Compare to price and downside loss magnitude.

FATE `scenario_weights` in investing.formulas.scenario supports weighted
outcomes. Update scenarios on earnings, not daily price.
""".strip(),
        formulas=(
            _F(
                "Expected value",
                r"EV = \sum_i p_i \cdot V_i",
                "Probability-weighted scenario values.",
                "investing.formulas.analysis.scenario_expected_value",
            ),
            _F(
                "Bear case loss",
                r"Loss_{bear} = \frac{P - V_{bear}}{P}",
                "Downside from current price if bear materializes.",
            ),
        ),
        screens=(
            "Bear case survivable (liquidity, solvency, emotion)",
            "Probabilities documented with rationale",
            "Drivers mutually consistent per scenario",
            "Trigger points to revisit thesis",
            "Position size scales with bear loss",
        ),
        traps=(
            "Bull-heavy probabilities always",
            "Scenarios not mutually exclusive events confused",
            "Stale scenarios after material news",
            "Ignoring correlation across portfolio scenarios",
        ),
        catalysts=("Scenario pivot trigger hit", "earnings confirming base case"),
        fate_hook="Soft `scenario_weights` in `investing.formulas.scenario`.",
        related=("monte_carlo", "valuation", "risk", "dcf"),
        further_reading=("Howard Marks — scenario thinking", "CFA curriculum scenario analysis"),
    )
)

register(
    DeepChapter(
        topic_id="monte_carlo",
        title="Monte Carlo Simulation",
        family="analysis",
        philosophy="""
Monte Carlo simulation generates thousands of random paths for returns,
prices, or portfolio values to estimate probability distributions — communicating
uncertainty better than single-point DCF outputs. Philosophy: inputs are
distributions, not false-precision scalars; output is a range of outcomes
and percentiles (P10, P50, P90), not one fair value.

GBM is a starting point, not reality — fat tails and correlation breaks
require stress overlays beyond vanilla Monte Carlo.
""".strip(),
        how_it_works="""
Specify distributions for drivers (growth μ, σ; margins; rates). Draw random
samples → compute N path valuations or portfolio returns → histogram outcomes
→ read percentile MOS. FATE `monte_carlo_mean_paths` in investing.formulas.scenario
implements GBM terminal mean for teaching demos.

Use for: DCF sensitivity, retirement success probability, option path P&L.
Seed RNG for reproducibility in research.
""".strip(),
        formulas=(
            _F(
                "GBM path",
                r"S_{t+1} = S_t \exp\left((\mu - \frac{\sigma^2}{2})\Delta t + \sigma\sqrt{\Delta t}\,Z\right)",
                "Geometric Brownian motion step; Z ~ N(0,1).",
                "investing.formulas.analysis.monte_carlo_mean_paths",
            ),
            _F(
                "Percentile value",
                r"V_{P_k} = \text{kth percentile of simulated } V_T",
                "e.g. P10 bear, P50 median, P90 bull.",
            ),
            _F(
                "Probability of loss",
                r"P(V_T < P_0) = \frac{\#\{paths < P_0\}}{N}",
                "Risk metric for position sizing.",
            ),
        ),
        screens=(
            "Input distributions justified (not arbitrary)",
            "≥ 10,000 paths for stable percentiles",
            "Correlated variables use copula/Cholesky where needed",
            "Fat-tail stress scenario alongside MC",
            "Results compared to analytical DCF",
        ),
        traps=(
            "Garbage μ,σ producing pretty charts",
            "Independence assumption across years",
            "Ignoring path dependency of leverage",
            "Overconfidence from P50 alone",
        ),
        catalysts=("Narrowing distribution as uncertainty resolves",),
        fate_hook="Soft `monte_carlo` in `investing.formulas.scenario` / `analysis.monte_carlo_mean_paths`.",
        related=("scenario", "dcf", "risk", "valuation"),
        further_reading=("Glasserman — Monte Carlo Methods in Finance",),
    )
)

register(
    DeepChapter(
        topic_id="dcf",
        title="DCF Analysis",
        family="analysis",
        philosophy="""
DCF analysis discounts projected free cash flows plus terminal value to
derive enterprise and equity value — the bridge from business drivers to
fair price. Philosophy: small changes in WACC or terminal growth swing outputs
wildly; therefore sensitivity tables and conservative assumptions matter more
than spreadsheet decimals. DCF is mandatory thinking even when you ultimately
decide via comps.

Terminal value often dominates — stress it as perpetuity growth, exit multiple,
or both.
""".strip(),
        how_it_works="""
Forecast explicit period (5–10y) FCF from revenue, margin, tax, capex, WC.
Discount at WACC. Terminal: Gordon g or exit EV/EBITDA. Enterprise value −
net debt = equity ÷ shares = per-share IV. Compare to price; build sensitivity
grid on WACC × g.

FATE implements intrinsic_value and terminal_value in analytics.value_investing
with Yahoo FCF feeds.
""".strip(),
        formulas=(
            _F(
                "DCF",
                r"EV = \sum_{t=1}^{n} \frac{FCF_t}{(1+WACC)^t} + \frac{TV}{(1+WACC)^n}",
                "Enterprise value from discounted flows.",
                "analytics.value_investing.intrinsic_value",
            ),
            _F(
                "Terminal value (Gordon)",
                r"TV = \frac{FCF_n(1+g)}{WACC - g}",
                "Requires g < WACC.",
                "analytics.value_investing.terminal_value",
            ),
            _F(
                "Equity value",
                r"E = EV - NetDebt + NonOpAssets",
                "Bridge to per-share value.",
            ),
        ),
        screens=(
            "FCF forecast tied to explicit drivers",
            "WACC defensible (beta, ERP, credit spread)",
            "g ≤ GDP-like in terminal",
            "TV sensitivity table completed",
            "Cross-check EV/EBITDA implied by TV",
        ),
        traps=(
            "g ≥ WACC",
            "Peak margins forever",
            "Ignoring SBC dilution",
            "TV > 80% with heroic g",
        ),
        catalysts=("Market convergence to DCF fair value", "FCF beat raising IV"),
        fate_hook="Live `intrinsic_value`, `terminal_value` in `analytics.value_investing.py`.",
        related=("wacc", "intrinsic_value", "valuation", "monte_carlo"),
        further_reading=("Damodaran — DCF models", "McKinsey — Valuation"),
    )
)

register(
    DeepChapter(
        topic_id="wacc",
        title="WACC Estimation",
        family="analysis",
        philosophy="""
Weighted average cost of capital blends cost of equity and after-tax cost of
debt to discount future cash flows — the hurdle rate for creating value.
Philosophy: WACC disagreement drives most DCF arguments; beta, equity risk
premium, and credit spread estimates are judgment calls with wide error bands.
Use consistent methodology across comparables.

Cost of equity via CAPM is common; practitioners add size and country premia
for international or small-cap names.
""".strip(),
        how_it_works="""
Cost of equity r_e = r_f + β × ERP (adjust for leverage if unlevering beta).
Cost of debt r_d from yield or rating spread, tax-adjusted. Weights E/V and
D/V from market values. Plug into WACC formula → discount FCF.

Sensitivity: ±1% WACC can move IV 15–25% on typical models. Document every
input source.
""".strip(),
        formulas=(
            _F(
                "WACC",
                r"WACC = \frac{E}{V}r_e + \frac{D}{V}r_d(1-T)",
                "Standard weighted average formula.",
                "investing.formulas.analysis.wacc",
            ),
            _F(
                "CAPM cost of equity",
                r"r_e = r_f + \beta (ERP)",
                "Beta from regression vs index; ERP ~5–7% historical debate.",
                "investing.formulas.risk.capm_beta",
            ),
            _F(
                "Unlevered beta",
                r"\beta_u = \frac{\beta_l}{1 + (1-T)\frac{D}{E}}",
                "Relever for target capital structure.",
            ),
        ),
        screens=(
            "Beta estimated with 2–5y weekly returns",
            "ERP consistent with company country",
            "Debt cost from market yield not book coupon",
            "Market value weights not book",
            "Sensitivity table on r_e and WACC",
        ),
        traps=(
            "Using book D/E weights",
            "Beta from thin trading or wrong index",
            "Ignoring operating leases as debt",
            "Vanity low WACC inflating IV",
        ),
        catalysts=("Credit upgrade lowering r_d", "beta fall as company matures"),
        fate_hook="Soft `wacc` in `investing.formulas.analysis` / valuation module.",
        related=("dcf", "valuation", "capm_beta", "risk"),
        further_reading=("Damodaran — cost of capital", "Brealey & Myers — Principles of Corporate Finance"),
    )
)

register(
    DeepChapter(
        topic_id="comps",
        title="Comparable Company Analysis",
        family="analysis",
        philosophy="""
Comparable company analysis values a firm using trading multiples of similar
public peers — EV/EBITDA, P/E, EV/Sales — adjusting for growth, margins,
risk, and scale. Philosophy: the market's current pricing of peers is a
reality check on your DCF; comps fail when peers are not truly comparable
or when the whole sector is in a bubble.

Normalize EBITDA, use forward metrics for growth names, and document why
your target deserves premium/discount to median.
""".strip(),
        how_it_works="""
Select 5–10 peers same industry, size band, geography. Compute multiples for
each; take median/mean. Apply to target metric → implied EV or price. Triangulate
EV/EBITDA, P/E, PEG. Adjust for net debt to equity value.

FATE `ev_ebitda` and comps_implied_price in investing.formulas.analysis.
""".strip(),
        formulas=(
            _F(
                "EV/EBITDA",
                r"\frac{EV}{EBITDA}",
                "Capital-structure-neutral multiple; primary for industrials.",
                "investing.formulas.analysis.ev_ebitda",
            ),
            _F(
                "Implied price",
                r"P_{implied} = Multiple_{peer} \times Metric_{per\ share}",
                "e.g. peer P/E × target EPS.",
                "investing.formulas.analysis.comps_implied_price",
            ),
            _F(
                "PEG ratio",
                r"PEG = \frac{P/E}{g}",
                "Growth-adjusted multiple; g in percent.",
            ),
        ),
        screens=(
            "Peers truly comparable business model",
            "Use LTM and NTM metrics consistently",
            "Adjust for one-time items in EBITDA",
            "Document premium/discount rationale",
            "Cross-check with DCF not far divergent",
        ),
        traps=(
            "Bubble comps implying bubble valuation",
            "Different accounting standards across peers",
            "Negative EBITDA forcing P/S only",
            "Ignoring net debt in EV bridge",
        ),
        catalysts=("Peer re-rating dragging target", "sector multiple expansion"),
        fate_hook="Soft `ev_ebitda_comps` in `investing.formulas.valuation` / analysis module.",
        related=("valuation", "dcf", "precedent_transactions", "wacc"),
        further_reading=("Wall Street Prep — trading comps", "Rosenbaum & Pearl — Investment Banking"),
    )
)

register(
    DeepChapter(
        topic_id="precedent_transactions",
        title="Precedent Transaction Analysis",
        family="analysis",
        philosophy="""
Precedent transaction analysis benchmarks value using multiples paid in recent
M&A deals for similar targets — capturing control premium and synergy
expectations that trading comps omit. Philosophy: strategics pay more than
market; financial sponsors pay LBO math. Use precedents for takeout valuation
and merger arb ceiling, not going-concern minority stakes without catalyst.

Deal multiples include synergies buyers expect — adjust down for minority.
""".strip(),
        how_it_works="""
Screen deals last 3–5 years same industry, size, geography. Collect EV/EBITDA,
EV/Revenue at announcement. Compute median; apply to target. Note strategic
vs sponsor, competitive auction vs negotiated, regulatory conditions.

Compare to trading comps premium — typical control premium 20–40% depending
sector. Update for current rate environment (LBO multiples compress with rates).
""".strip(),
        formulas=(
            _F(
                "Control premium",
                r"Premium = \frac{Deal - Price_{pre}}{Price_{pre}}",
                "Measure over undisturbed price.",
            ),
            _F(
                "Transaction EV/EBITDA",
                r"\frac{EV_{deal}}{EBITDA_{LTM}}",
                "Deal multiple including synergies priced in.",
            ),
        ),
        screens=(
            "Deals < 3 years old unless structural change",
            "Target size within 0.5–2× revenue scale",
            "Exclude distressed fire sales from median",
            "Synergy narrative assessed for overpayment",
            "Regulatory precedent for antitrust clearance",
        ),
        traps=(
            "One outlier deal skewing median",
            "Different accounting EBITDA definitions",
            "Failed deals included",
            "Applying 2021 multiples in 2026 rate regime",
        ),
        catalysts=("Strategic review announcement", "activist pushing sale", "industry consolidation wave"),
        fate_hook="Knowledge; merger_arb and special_situations link to transaction pricing.",
        related=("comps", "merger_arb", "special_situations", "valuation"),
        further_reading=("Rosenbaum & Pearl — precedent transactions chapter",),
    )
)

register(
    DeepChapter(
        topic_id="economic_moat",
        title="Economic Moat Analysis",
        family="analysis",
        philosophy="""
Economic moat analysis identifies durable competitive advantages that protect
returns on capital from competition and commoditization. Philosophy: without
a moat, growth investments destroy value as competitors arbitrage profits;
with a moat, reinvestment compounds at high ROIC for years. Moats are not
marketing slogans — they must show up in stable margins and ROIC > WACC
through cycles.

Moats can erode: technology shifts, regulation, or management mistakes
breach once-wide castles.
""".strip(),
        how_it_works="""
Moat sources checklist (Morningstar/Dorsey framework):
(1) Network effects — value rises with users (payments, platforms).
(2) Switching costs — painful to leave (ERP, bank relationships).
(3) Intangible assets — brand, patents, licenses.
(4) Cost advantage — scale, process, location.
(5) Efficient scale — natural oligopoly (pipelines, rating agencies).

Score each 0–2; corroborate with 5–10y gross margin and ROIC vs peers.
FATE `buffett_quality` proxies moat via ROE, margins, leverage.
""".strip(),
        formulas=(
            _F(
                "ROIC vs WACC",
                r"ROIC - WACC > 0 \Rightarrow value\ creating",
                "Moat shows as sustained positive spread.",
            ),
            _F(
                "Moat duration (concept)",
                r"Years\ ROIC > WACC\ through\ cycle",
                "Longer duration justifies higher terminal multiple.",
            ),
            _F(
                "Buffett quality score",
                r"Quality = f(ROE, margins, leverage)",
                "FATE composite moat proxy.",
                "analytics.value_investing.buffett_quality",
            ),
        ),
        screens=(
            "ROIC > WACC for 5+ years",
            "Gross margin stable vs competitors",
            "Pricing power in inflation pass-through",
            "Share stable or gaining",
            "At least one identifiable moat source",
        ),
        traps=(
            "Confusing market share with moat in commodity biz",
            "Patent cliff without pipeline",
            "Regulatory moat that politics can revoke",
            "Peak-cycle ROIC mistaken for structural",
        ),
        catalysts=("Moat widening via network growth", "competitor exit"),
        fate_hook="Live `buffett_quality` in `analytics.value_investing.py`; qualitative moat list in chapter.",
        related=("buffett", "competitive", "qualitative", "compounders"),
        further_reading=("Pat Dorsey — The Little Book That Builds Wealth", "Morningstar moat methodology"),
    )
)

register(
    DeepChapter(
        topic_id="management",
        title="Management Analysis",
        family="analysis",
        philosophy="""
Management analysis judges leadership on capital allocation, integrity,
operational execution, and alignment with minority shareholders — because
great businesses with poor stewards destroy value through vanity M&A,
dilution, and accounting games. Philosophy: bet on jockeys when the horse
race is long; one brilliant product cannot offset decades of value-leaking
decisions. Track record matters more than charisma on investor day.

Insider ownership and sensible compensation structures align interests;
empire building and related-party deals do not.
""".strip(),
        how_it_works="""
Review: proxy DEF 14A (comp, board), insider Form 4 flows, buyback timing
(vs price), M&A ROIC post-deals, earnings call Q&A candor, employee reviews
(Glassdoor), auditor tenure. Red flags: frequent restructuring charges,
auditor switches, promotional accounting metrics.

Score 1–5 on allocation, integrity, operations. Pair with economic_moat —
great management cannot fix no-moat industry indefinitely.
""".strip(),
        formulas=(),
        screens=(
            "Insider ownership > 1% for mid-cap+ or meaningful $ for founders",
            "Buybacks primarily when P < IV estimate",
            "M&A deals earn ROIC > WACC post-integration",
            "Board majority independent with relevant expertise",
            "CEO/CFO low unexplained turnover in C-suite",
        ),
        traps=(
            "Star CEO cult ignoring board weakness",
            "Stock comp dilution disguised as talent retention",
            "Roll-up accounting complexity",
            "Founder control without minority protection",
        ),
        catalysts=("Activist forcing capital return", "management upgrade", "insider cluster buying"),
        fate_hook="Transcript NLP and news sentiment soft-flag management tone; Buffett quality overlaps allocation proxies.",
        related=("qualitative", "buffett", "esg", "financial_statement"),
        further_reading=("William Thorndike — The Outsiders", "Buffett on compensation in letters"),
    )
)
