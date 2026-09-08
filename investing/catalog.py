"""
Beginner investing book taxonomy for FATE_AlgoBot.

Maps strategies, asset classes, sectors, and analysis methods to
implementation status (live rank wiring, soft formula proxy, knowledge).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Status = Literal["live", "soft", "knowledge"]


@dataclass(frozen=True)
class Topic:
    id: str
    title: str
    family: str
    parent: str = ""
    status: Status = "knowledge"
    formulas: tuple[str, ...] = ()
    summary: str = ""
    module: str = ""


def _t(
    id: str,
    title: str,
    family: str,
    *,
    parent: str = "",
    status: Status = "knowledge",
    formulas: tuple[str, ...] = (),
    summary: str = "",
    module: str = "",
) -> Topic:
    return Topic(id, title, family, parent, status, formulas, summary, module)

STRATEGY_TOPICS: tuple[Topic, ...] = (
    _t("deep_value", "Deep Value", "value", status="live", formulas=("deep_value_screen",), module="analytics/value_investing.py", summary="Deep value investing seeks stocks trading far below conservative estimates of worth, often with distressed optics or cyclical troughs. FATE screens for low multiples combined with balance-sheet support to find mispriced equities."),
    _t("intrinsic_value", "Intrinsic Value", "value", status="live", formulas=("intrinsic_value", "terminal_value", "margin_of_safety",), module="analytics/value_investing.py", summary="Intrinsic value is the present value of all future cash a business can distribute to owners, discounted at an appropriate rate. It anchors buy decisions when market price offers a sufficient margin of safety below this estimate."),
    _t("graham", "Graham Value", "value", status="live", formulas=("graham_net_net", "ncav",), module="analytics/value_investing.py", summary="Benjamin Graham pioneered quantitative value screens emphasizing net-net working capital and strict balance-sheet margins of safety. His framework favors cheap, understandable businesses with limited downside rather than heroic growth forecasts."),
    _t("buffett", "Buffett Quality Value", "value", status="live", formulas=("buffett_quality",), module="analytics/value_investing.py", summary="Warren Buffett evolved Graham's cigar-butt approach into buying wonderful businesses at fair prices with durable competitive advantages. Quality metrics—ROE, stable margins, low leverage—proxy moat strength alongside reasonable valuation."),
    _t("contrarian", "Contrarian", "value", status="live", formulas=("contrarian_tilt",), module="analytics/value_investing.py", summary="Contrarian investors deliberately lean against crowd sentiment, buying unloved names and avoiding euphoric favorites. The edge comes from behavioral mispricing when fear or greed pushes prices away from fundamentals."),
    _t("net_net", "Net-Net", "value", status="live", formulas=("graham_net_net", "ncav",), module="analytics/value_investing.py", summary="A net-net stock trades below net current asset value minus all liabilities, offering a literal liquidation cushion. Graham used this as a deep-value basket filter for small caps with tangible asset backing."),
    _t("asset_based", "Asset-Based Value", "value", summary="Asset-based valuation sums tangible and intangible resources—real estate, inventory, brands—and compares them to market cap. It suits capital-heavy or holding-company structures where earnings understate embedded asset worth."),
    _t("special_situations", "Special Situations", "value", summary="Special situations include spin-offs, restructurings, bankruptcies emerging from court, and other corporate events that create temporary mispricing. Skilled investors analyze event timelines and forced sellers rather than steady-state DCF alone."),
    _t("sum_of_the_parts", "Sum-of-the-Parts", "value", status="soft", formulas=("sotp",), module="investing.formulas.sotp", summary="Sum-of-the-parts values each business segment separately and aggregates them, often revealing a conglomerate discount in the stock price. It is essential for diversified companies where consolidated P/E obscures hidden value."),
    _t("turnaround", "Turnaround", "value", summary="Turnaround investing targets companies exiting distress through new management, balance-sheet repair, or operational fixes. Returns can be large, but timing and execution risk are high until evidence of sustainable recovery appears."),
    _t("growth", "Growth Investing", "growth", summary="Growth investors prioritize revenue and earnings expansion over current valuation multiples, betting that today's premium fades as the company scales. Success depends on identifying durable growth rather than temporary spikes."),
    _t("garp", "GARP", "growth", status="live", formulas=("garp_peg",), module="investing.formulas.garp", summary="Growth at a reasonable price blends growth screens with valuation discipline, often using PEG ratios to avoid overpaying for momentum. GARP seeks companies expanding faster than the market without extreme multiple risk."),
    _t("hypergrowth", "Hypergrowth", "growth", summary="Hypergrowth strategies focus on companies growing revenue at exceptional rates, often reinvesting all cash flow to capture market share. These names carry high volatility and depend on TAM expansion and competitive moats forming quickly."),
    _t("momentum_growth", "Momentum Growth", "growth", status="live", formulas=("momentum_return",), module="analytics/hedge_fund_stack.py", summary="Momentum growth combines strong price trends with fundamental growth, riding winners that continue to outperform on both charts and estimates. It exploits persistence in relative strength while filtering for underlying business acceleration."),
    _t("quality_growth", "Quality Growth", "growth", status="live", formulas=("factor_quality",), module="analytics/hedge_fund_stack.py", summary="Quality growth emphasizes high-return, low-leverage businesses that compound steadily rather than betting on binary outcomes. Metrics like ROIC stability and margin durability separate sustainable compounders from fragile high flyers."),
    _t("compounders", "Compounders", "growth", summary="Compounders reinvest at high incremental returns for long periods, creating wealth through time rather than single catalysts. Investors hold through volatility, trusting management capital allocation and widening moats."),
    _t("innovation", "Innovation Investing", "growth", summary="Innovation investing backs companies creating new products, platforms, or business models that disrupt incumbents. Winners can dominate categories, but many fail; diversification and stage-aware sizing manage binary risk."),
    _t("disruptor", "Disruptor", "growth", summary="Disruptors attack established industries with superior economics, technology, or customer experience, often starting small and scaling fast. Early identification requires understanding adoption curves and incumbent response lag."),
    _t("early_stage", "Early-Stage Growth", "growth", summary="Early-stage growth targets younger public companies or recent IPOs still proving unit economics and market fit. Position sizing and liquidity awareness matter because these names swing on guidance and funding sentiment."),
    _t("secular_growth", "Secular Growth", "growth", summary="Secular growth themes ride multi-year structural shifts—aging populations, digitization, electrification—rather than short business cycles. Portfolios tilt toward beneficiaries of durable tailwinds with visible runway."),
    _t("dividend", "Dividend Investing", "income", status="live", formulas=("ggm_dividend",), module="investing.formulas.dividend", summary="Dividend investing selects stocks with reliable cash payouts that return capital to shareholders on a schedule. Total return combines yield with dividend growth and any price appreciation over holding periods."),
    _t("dividend_growth", "Dividend Growth", "income", status="live", formulas=("ggm_dividend", "dividend_growth_rate",), module="investing.formulas.dividend", summary="Dividend growth strategies favor companies that raise payouts consistently, signaling confidence and disciplined capital allocation. Compounding yield-on-cost can exceed initial headline yields over decades."),
    _t("high_yield", "High-Yield Income", "income", summary="High-yield strategies prioritize current income through elevated dividend or coupon rates, often in mature or leveraged sectors. Investors must weigh payout sustainability against trap risk when yields look too good."),
    _t("preferred_shares", "Preferred Shares", "income", summary="Preferred shares sit between bonds and common stock, offering fixed dividends and priority over common in liquidation. They suit income investors seeking higher yields than senior debt with less volatility than common equity."),
    _t("covered_call_income", "Covered Call Income", "income", status="soft", formulas=("covered_call_yield",), module="investing.formulas.options", summary="Covered call income sells call options against owned stock to collect premium, enhancing yield in flat or mildly bullish markets. The trade-off is capped upside if the stock rallies sharply above the strike."),
    _t("reit_income", "REIT Income", "income", summary="REIT income strategies hold real estate investment trusts that pass through rental cash flows as high dividends. Sector diversification across property types helps manage interest-rate sensitivity and occupancy cycles."),
    _t("bond_laddering", "Bond Laddering", "income", summary="Bond laddering staggers maturities so income arrives regularly and reinvestment risk is spread across rate environments. It provides predictable cash flow with less duration concentration than a single long bond."),
    _t("municipal_bonds", "Municipal Bonds", "income", summary="Municipal bonds fund state and local projects and often offer tax-advantaged income for qualifying investors. Credit quality varies by issuer; general obligation and revenue bonds carry different security structures."),
    _t("preferred_stock", "Preferred Stock Income", "income", summary="Preferred stock income strategies build portfolios of preferred issues across banks, utilities, and REITs for steady distributions. Callable features and rate sensitivity require monitoring reinvestment when issues are redeemed."),
    _t("infrastructure_income", "Infrastructure Income", "income", summary="Infrastructure income targets assets—pipelines, toll roads, utilities—with long-lived contracts and inflation-linked revenue. Listed infrastructure equities and MLPs provide liquid access with regulatory and political nuances."),
    _t("quant", "Quantitative Investing", "quant", summary="Quantitative investing systematizes security selection and portfolio construction using statistical models and data pipelines. It reduces discretionary bias but requires robust research, execution, and risk controls."),
    _t("factor", "Factor Investing", "quant", status="live", formulas=("factor_value", "factor_momentum", "factor_quality", "factor_low_vol",), module="analytics/hedge_fund_stack.py", summary="Factor investing tilts portfolios toward drivers of return such as value, momentum, quality, and low volatility identified in academic research. Smart implementation manages crowding, turnover, and regime shifts."),
    _t("smart_beta", "Smart Beta", "quant", status="live", formulas=("factor_value", "factor_momentum",), module="analytics/hedge_fund_stack.py", summary="Smart beta rules-based indexes reweight traditional market-cap benchmarks toward desired factor exposures. They offer transparent, lower-cost alternatives to pure cap-weighted passive funds."),
    _t("stat_arb", "Statistical Arbitrage", "quant", status="live", formulas=("pair_spread_z",), module="analytics/hedge_fund_stack.py", summary="Statistical arbitrage exploits mean-reverting relationships between related securities using z-scores and cointegration tests. Market-neutral construction aims to isolate spread alpha from broad market direction."),
    _t("risk_parity", "Risk Parity", "quant", summary="Risk parity allocates capital so each asset class contributes similar risk rather than similar dollars, often using leverage on lower-volatility bonds. The goal is smoother returns across macro regimes."),
    _t("ml_investing", "ML Investing", "quant", status="live", formulas=("ml_horizon_heads",), module="ml_model.py", summary="Machine learning investing trains models on historical features to forecast returns, volatility, or regime shifts. FATE uses calibrated horizon heads blended into daily rank scores with strict out-of-sample discipline."),
    _t("forecast_combination", "Forecast Combination", "quant", status="live", formulas=("precision_weighted_combination", "logit_evidence_algebra"), module="analytics/vector_math.py", summary="Forecast combination weights independent models by inverse error variance in log-odds space so a pick is sized only when heads agree. FATE uses Bates–Granger / Grinold precision weights for horizon fusion, hedge-fund factors, and book-family scores."),
    _t("ai_investing", "AI Investing", "quant", status="live", formulas=("news_sentiment", "transcript_factor",), module="sentiment_pipeline.py", summary="AI investing applies large language models and neural networks to text, audio, and alternative data for alpha and risk signals. News and transcript factors in FATE feed sentiment overlays into the rank pipeline."),
    _t("algo_trading", "Algorithmic Trading", "quant", status="live", module="alpaca_broker.py", summary="Algorithmic trading automates order placement, sizing, and timing according to predefined rules or models. It improves consistency and speed but demands monitoring for model drift and market microstructure changes."),
    _t("hft", "High-Frequency Trading", "quant", status="live", module="hft/src/obi-tape/obi-tape-signals.ts", summary="High-frequency trading operates on sub-second horizons, capturing small inefficiencies via speed and microstructure signals. FATE's HFT stack uses order-book imbalance and tape velocity on paper-equity compatible infrastructure."),
    _t("automated_portfolio", "Automated Portfolio Management", "quant", status="live", module="fortress_live.py", summary="Automated portfolio management rebalances, tax-manages, and risk-controls holdings without daily human intervention. Robo-advisor logic and FATE's fortress loop exemplify systematic oversight at scale."),
    _t("day_trading", "Day Trading", "trading", summary="Day trading opens and closes positions within the same session, avoiding overnight gap risk. It requires strict risk limits, liquidity, and discipline because transaction costs and emotional pressure erode edges quickly."),
    _t("swing_trading", "Swing Trading", "trading", summary="Swing trading holds positions for days to weeks, capturing moves between support and resistance or post-catalyst drift. It balances intraday noise filtering with enough time for technical setups to play out."),
    _t("position_trading", "Position Trading", "trading", summary="Position trading takes multi-week to multi-month views aligned with trends, fundamentals, or macro themes. Lower turnover reduces costs but demands patience through drawdowns and news volatility."),
    _t("scalping", "Scalping", "trading", summary="Scalping seeks tiny profits from numerous quick trades, relying on tight spreads and rapid execution. Edge per trade is small; success depends on volume, fee structure, and strict stop discipline."),
    _t("trend_following", "Trend Following", "trading", status="live", formulas=("trend_ema_macd", "relative_strength",), module="analytics/hedge_fund_stack.py", summary="Trend following rides established directional moves, buying strength and selling weakness rather than predicting tops. Moving-average stacks, MACD, and relative strength vs benchmarks identify participation."),
    _t("mean_reversion", "Mean Reversion", "trading", status="live", formulas=("mean_reversion_z",), module="signals/dip_momentum.py", summary="Mean reversion assumes prices temporarily overshoot fair value and snap back toward averages or peers. Z-scores, Bollinger bands, and RSI extremes help time entries when stretch meets liquidity."),
    _t("breakout", "Breakout Trading", "trading", status="live", formulas=("breakout_structure",), module="analytics/structure_patterns.py", summary="Breakout trading enters when price clears defined resistance with volume, betting on continuation as trapped shorts cover and momentum buyers arrive. False breakouts require stops and confirmation filters."),
    _t("range_trading", "Range Trading", "trading", summary="Range trading buys support and sells resistance within horizontal channels when trends are absent. It works in mean-reverting markets but fails catastrophically when ranges break into new trends."),
    _t("news_trading", "News Trading", "trading", status="live", formulas=("news_sentiment",), module="sentiment_pipeline.py", summary="News trading reacts to headlines, earnings, and macro releases before prices fully reflect information. Speed, source quality, and sentiment scoring separate durable moves from headline noise."),
    _t("event_driven", "Event-Driven Trading", "trading", status="live", formulas=("earnings_surprise",), module="hft/src/earnings/earnings-evaluator.ts", summary="Event-driven trading positions around identifiable catalysts—M&A, spin-offs, earnings surprises, regulatory decisions. The edge is superior scenario analysis and timing relative to implied market odds."),
    _t("options", "Options", "derivatives", summary="Options grant the right, not obligation, to buy or sell an underlying at a strike before expiry. They enable defined-risk speculation, income enhancement, and portfolio hedging when used with clear Greeks awareness."),
    _t("covered_calls", "Covered Calls", "derivatives", status="soft", formulas=("covered_call_yield",), module="investing.formulas.options", summary="Covered calls sell call options against long stock, collecting premium that partially offsets downside. They are popular income overlays but cap participation in sharp rallies."),
    _t("protective_puts", "Protective Puts", "derivatives", status="soft", formulas=("protective_put_cost",), module="investing.formulas.options", summary="Protective puts buy downside insurance by purchasing put options against owned shares. Cost is the premium paid, analogous to an insurance deductible on portfolio drawdowns."),
    _t("iron_condors", "Iron Condors", "derivatives", summary="Iron condors combine short and long puts and calls to profit when price stays within a range until expiry. They collect premium in low-volatility environments but face large losses if price breaks wings."),
    _t("credit_spreads", "Credit Spreads", "derivatives", summary="Credit spreads sell one option and buy a further OTM option to collect net premium with defined risk. Bull put and bear call structures express directional views with less capital than naked short options."),
    _t("debit_spreads", "Debit Spreads", "derivatives", summary="Debit spreads pay upfront premium for a long option partially financed by a short option, capping both cost and max gain. They suit directional bets with lower theta bleed than outright long options."),
    _t("calendar_spreads", "Calendar Spreads", "derivatives", summary="Calendar spreads sell near-term options and buy longer-dated options at the same strike, betting on time decay differentials and volatility term structure. They shine when front-month IV exceeds back-month around events."),
    _t("straddles", "Straddles", "derivatives", summary="Long straddles buy at-the-money call and put to profit from large moves in either direction. They lose money if the underlying stays flat as time decay erodes both legs."),
    _t("strangles", "Strangles", "derivatives", summary="Strangles buy OTM call and put, cheaper than straddles but requiring a larger move to profit. They are classic pre-earnings volatility plays when implied vol may misprice realized movement."),
    _t("butterfly", "Butterfly Spreads", "derivatives", summary="Butterfly spreads combine bull and bear spreads centered on a target price for low-cost, high-payout-if-precise bets. Maximum profit occurs if the underlying expires exactly at the middle strike."),
    _t("short_selling", "Short Selling", "short", summary="Short selling borrows shares and sells them, profiting if price falls and losing if it rises. Borrow availability, recall risk, and unlimited loss potential demand rigorous risk management."),
    _t("long_short", "Long-Short Equity", "short", summary="Long-short equity pairs long winners with short losers to seek alpha while reducing net market exposure. Skill lies in both sides of the book—avoiding crowded shorts and managing beta drift."),
    _t("market_neutral", "Market Neutral", "short", status="live", formulas=("pair_spread_z", "beta_neutral",), module="analytics/hedge_fund_stack.py", summary="Market neutral strategies target zero beta by balancing long and short exposures of similar size. Returns depend on stock selection skill rather than directional market moves."),
    _t("pair_trading", "Pair Trading", "short", status="soft", formulas=("pair_spread_z",), module="analytics/hedge_fund_stack.py", summary="Pair trading goes long one security and short a correlated peer when their spread diverges from historical norms. Convergence trades require cointegration awareness and patience through extended dislocations."),
    _t("inverse_etfs", "Inverse ETFs", "short", summary="Inverse ETFs deliver negative daily exposure to an index through derivatives, useful for tactical hedges without margin shorting. Daily reset compounding makes them poor long-term bear bets."),
    _t("bear_strategies", "Bear Strategies", "short", summary="Bear strategies profit from declining markets via shorts, puts, or inverse products during downtrends or recessions. Timing entry and covering squeezes matter because bear rallies can be violent."),
    _t("global_macro", "Global Macro", "macro", status="live", formulas=("regime_hmm",), module="regime_detector.py", summary="Global macro invests across countries and asset classes based on top-down views of growth, policy, and geopolitics. Successful managers synthesize rates, currencies, and commodities into coherent cross-asset themes."),
    _t("top_down", "Top-Down Analysis", "macro", summary="Top-down analysis starts with economy, policy, and sector trends before selecting individual securities. It ensures portfolio tilts align with the prevailing macro wind rather than fighting it."),
    _t("bottom_up", "Bottom-Up Analysis", "macro", summary="Bottom-up analysis evaluates company fundamentals first, treating macro as context rather than driver. It suits stock pickers who believe security-specific edge dominates sector timing."),
    _t("currency", "Currency Macro", "macro", summary="Currency macro trades FX pairs based on interest-rate differentials, trade balances, and central-bank policy paths. Carry, momentum, and valuation frameworks guide positioning in G10 and emerging markets."),
    _t("commodity_macro", "Commodity Macro", "macro", summary="Commodity macro positions in oil, metals, and agriculture reflect supply-demand imbalances and geopolitical shocks. Futures curves and inventory data help distinguish temporary spikes from structural shortages."),
    _t("interest_rate", "Interest-Rate Macro", "macro", status="live", formulas=("yield_spread",), module="regime_detector.py", summary="Interest-rate macro trades the yield curve, duration, and rate-sensitive sectors as central banks tighten or ease. Inverted curves and real-rate moves often precede equity regime shifts."),
    _t("inflation", "Inflation Investing", "macro", summary="Inflation investing favors real assets, pricing power, and TIPS when purchasing power erodes. Historical regimes show equities with strong moats and commodities can hedge unexpected inflation surges."),
    _t("deflation", "Deflation Hedging", "macro", summary="Deflation hedging emphasizes quality bonds, cash, and defensive equities when prices and wages fall. Debt burdens rise in real terms during deflation, stressing highly leveraged cyclicals."),
    _t("business_cycle", "Business Cycle Investing", "macro", status="live", formulas=("regime_hmm",), module="regime_detector.py", summary="Business cycle investing rotates sectors—early cycle favors cyclicals, late cycle favors defensives—based on expansion and contraction phases. Leading indicators and earnings revisions mark transitions."),
    _t("venture_capital", "Venture Capital", "alternative", summary="Venture capital funds early private companies in exchange for equity, targeting outsized returns from a few big winners. Illiquidity, long horizons, and power-law outcomes define the asset class."),
    _t("private_equity", "Private Equity", "alternative", summary="Private equity buys and improves mature companies using leverage, operational changes, and eventual exit via sale or IPO. Returns come from EBITDA growth, multiple expansion, and debt paydown."),
    _t("angel_investing", "Angel Investing", "alternative", summary="Angel investors deploy personal capital into seed-stage startups, often alongside mentorship and network access. Most investments fail; diversification and sector expertise mitigate total loss risk."),
    _t("seed_investing", "Seed Investing", "alternative", summary="Seed investing provides the earliest institutional or semi-institutional capital to validate product-market fit. Valuations are narrative-driven, and follow-on funding risk dominates outcomes."),
    _t("crowdfunding", "Equity Crowdfunding", "alternative", summary="Equity crowdfunding lets many small investors buy private company shares through regulated platforms. It democratizes access but offers limited liquidity and uneven disclosure quality."),
    _t("collectibles", "Collectibles", "alternative", summary="Collectibles—cards, memorabilia, vintage goods—derive value from scarcity, condition, and collector demand rather than cash flows. Authentication, storage, and fickle taste create idiosyncratic risk."),
    _t("fine_art", "Fine Art", "alternative", summary="Fine art investing treats paintings and sculptures as stores of value with aesthetic and cultural premium. Masterworks appreciate slowly, carry high transaction costs, and lack transparent pricing."),
    _t("wine", "Wine Investing", "alternative", summary="Wine investing buys investment-grade bottles expected to appreciate as supply dwindles and critics score vintages. Storage, provenance, and changing consumer preferences make it a specialist market."),
    _t("watches", "Luxury Watches", "alternative", summary="Luxury watch investing targets limited editions and iconic references that appreciate with brand heat and scarcity. Counterfeits and servicing costs require expert due diligence."),
    _t("rare_coins", "Rare Coins", "alternative", summary="Rare coin investing values numismatic history, grade, and mintage alongside precious metal content. Grading standards and dealer spreads materially affect realized returns."),
    _t("real_estate", "Real Estate", "real_assets", summary="Direct real estate investing owns physical property for rental income and appreciation. Location, cap rates, leverage, and management quality drive long-run returns."),
    _t("farmland", "Farmland", "real_assets", summary="Farmland investing captures agricultural productivity and land scarcity with inflation-linked food demand. Weather, commodity prices, and water rights add regional complexity."),
    _t("timberland", "Timberland", "real_assets", summary="Timberland combines biological growth of trees with optionality to harvest when lumber prices peak. It offers diversification and inflation hedging but requires long holding periods."),
    _t("infrastructure_assets", "Infrastructure", "real_assets", summary="Infrastructure assets—ports, grids, fiber—generate contracted or regulated cash flows over decades. Political risk and capex cycles matter alongside yield stability."),
    _t("precious_metals", "Precious Metals", "real_assets", summary="Precious metals like gold and silver serve as inflation hedges and crisis diversifiers without cash-flow yield. They tend to outperform when real rates fall or confidence in fiat currencies wavers."),
    _t("index_investing", "Index Investing", "passive", status="live", module="analytics/strategy_registry.py", summary="Index investing buys broad market-cap weighted funds to capture average market returns at minimal cost. It beats most active managers net of fees over long horizons through diversification and discipline."),
    _t("etf_investing", "ETF Investing", "passive", status="live", summary="ETFs trade intraday like stocks while holding diversified baskets of assets transparently. They offer tax efficiency, sector tilts, and global access with lower minimums than many mutual funds."),
    _t("dca", "Dollar-Cost Averaging", "passive", summary="Dollar-cost averaging invests fixed amounts on a schedule, buying more shares when prices are low and fewer when high. It reduces timing anxiety and enforces consistent savings behavior."),
    _t("buy_and_hold", "Buy and Hold", "passive", summary="Buy and hold maintains positions through volatility, trusting long-term economic growth and compounding. It minimizes taxes and trading costs but requires tolerance for deep drawdowns."),
    _t("lazy_portfolios", "Lazy Portfolios", "passive", summary="Lazy portfolios use a handful of low-cost index funds rebalanced occasionally—classic three-fund or permanent portfolio variants. Simplicity and low maintenance appeal to investors avoiding complexity."),
    _t("target_date", "Target-Date Funds", "passive", summary="Target-date funds glide from aggressive to conservative allocations as a retirement date approaches. They automate rebalancing and are default choices in many employer plans."),
    _t("core_satellite", "Core-Satellite", "passive", summary="Core-satellite investing anchors most capital in passive index core holdings while satellites pursue active alpha or factor tilts. It balances low-cost beta with controlled risk budget for experimentation."),
    _t("merger_arb", "Merger Arbitrage", "advanced", summary="Merger arbitrage buys targets after announced deals, earning the spread to deal price if closing succeeds. Deal break risk, regulatory delay, and financing conditions define the payoff profile."),
    _t("convertible_arb", "Convertible Arbitrage", "advanced", summary="Convertible arbitrage hedges equity delta of convertible bonds while harvesting volatility and credit spread. It requires dynamic hedging as stock prices and implied vol move."),
    _t("volatility_trading", "Volatility Trading", "advanced", summary="Volatility trading expresses views on realized vs implied volatility through options and variance swaps. Selling vol collects premium in calm markets; buying vol pays off in shocks."),
    _t("distressed_debt", "Distressed Debt", "advanced", summary="Distressed debt buys bonds or loans of troubled companies at deep discounts, betting on restructuring recovery. Legal process expertise and liquidity constraints separate specialists from generalists."),
    _t("leveraged_investing", "Leveraged Investing", "advanced", summary="Leveraged investing amplifies exposure with margin, derivatives, or leveraged ETFs, magnifying gains and losses. Path dependency and financing costs make it suitable only with strict risk limits."),
    _t("esg", "ESG Investing", "advanced", summary="ESG investing integrates environmental, social, and governance criteria alongside financial metrics. It reflects values, regulatory trends, and growing evidence linking governance quality to long-run performance."),
    _t("thematic_investing", "Thematic Investing", "advanced", summary="Thematic investing builds portfolios around structural narratives—AI, aging, water scarcity—cutting across traditional sectors. Concentration and hype cycles require distinguishing durable trends from fads."),
    _t("tactical_aa", "Tactical Asset Allocation", "advanced", summary="Tactical asset allocation shifts weights among stocks, bonds, and alternatives based on short- to medium-term outlooks. Success depends on timely signals and transaction cost control versus static strategic weights."),
    _t("strategic_aa", "Strategic Asset Allocation", "advanced", status="live", formulas=("capm_beta", "sharpe_ratio",), module="investing.formulas.risk", summary="Strategic asset allocation sets long-run policy weights matched to risk tolerance and goals, rebalancing when drift exceeds bands. CAPM and Sharpe frameworks inform expected return and risk budgeting."),
    _t("portfolio_optimization", "Portfolio Optimization", "advanced", status="live", formulas=("sharpe_ratio", "capm_beta",), module="investing.formulas.risk", summary="Portfolio optimization solves for weights maximizing risk-adjusted return subject to constraints using mean-variance or extensions. Estimation error in inputs makes robust methods and shrinkage essential."),
    _t("tax_loss_harvesting", "Tax-Loss Harvesting", "advanced", summary="Tax-loss harvesting sells losers to offset capital gains and rebuys similar exposure after wash-sale rules allow. It adds after-tax alpha in taxable accounts without changing economic exposure materially."),
    _t("sector_rotation", "Sector Rotation", "advanced", status="soft", formulas=("sector_rotation",), module="investing.formulas.sector", summary="Sector rotation overweights sectors expected to lead the next cycle phase and underweights laggards. Macro indicators, relative strength, and earnings breadth guide timing."),
    _t("multi_asset", "Multi-Asset Investing", "advanced", summary="Multi-asset investing combines equities, bonds, commodities, and alternatives in one risk-managed portfolio. Correlation dynamics shift in crises, so diversification assumptions need stress testing."),
)

ASSET_CLASS_TOPICS: tuple[Topic, ...] = (
    _t("stocks", "Stocks", "asset_class", status="live", summary="Equities represent fractional ownership in corporations with upside from earnings growth and dividends. They historically outperform bonds long term but exhibit higher drawdown volatility."),
    _t("bonds", "Bonds", "asset_class", summary="Bonds are loans to governments or corporations paying periodic interest and returning principal at maturity. Duration and credit quality drive price sensitivity to rates and default risk."),
    _t("cash", "Cash", "asset_class", summary="Cash and cash equivalents—T-bills, money markets—preserve nominal capital and provide liquidity. Real returns erode during inflation but cash enables opportunistic deployment after selloffs."),
    _t("etfs", "ETFs", "asset_class", status="live", summary="Exchange-traded funds hold baskets of securities and trade on exchanges throughout the day. They offer diversified, transparent exposure at low cost across virtually every asset class."),
    _t("mutual_funds", "Mutual Funds", "asset_class", summary="Mutual funds pool investor capital for professional management, priced once daily at NAV. Active share, fees, and tax efficiency vary widely versus passive alternatives."),
    _t("index_funds", "Index Funds", "asset_class", status="live", summary="Index funds passively track a benchmark such as the S&P 500 with minimal turnover. They deliver market beta efficiently and anchor core portfolio allocations."),
    _t("options_asset", "Options", "asset_class", summary="Options are derivative contracts giving rights to buy or sell underlying assets at set strikes. They add leverage, hedging, and income strategies beyond direct ownership."),
    _t("futures", "Futures", "asset_class", summary="Futures obligate purchase or sale of an asset at a future date at a agreed price. They dominate commodity and rate trading with margin and daily mark-to-market."),
    _t("forwards", "Forwards", "asset_class", summary="Forwards are customized OTC contracts similar to futures but non-standardized and illiquid. Corporates use them to hedge currency and commodity exposures bilaterally."),
    _t("swaps", "Swaps", "asset_class", summary="Swaps exchange cash flows—fixed for floating rates, currency legs, or credit exposure—between counterparties. They enable precise hedging and relative-value trades at institutional scale."),
    _t("commodities", "Commodities", "asset_class", summary="Commodities are physical goods—energy, metals, crops—priced by global supply and demand. They diversify portfolios and hedge inflation but carry storage and roll-yield considerations."),
    _t("gold", "Gold", "asset_class", summary="Gold is a monetary metal held as reserve asset and jewelry with minimal industrial use relative to supply. It often rises when real yields fall or geopolitical risk spikes."),
    _t("silver", "Silver", "asset_class", summary="Silver combines monetary demand with industrial usage in electronics and solar. It is more volatile than gold and can outperform in reflationary industrial upswings."),
    _t("platinum", "Platinum", "asset_class", summary="Platinum is a precious industrial metal critical for catalytic converters and hydrogen tech. Supply concentration in South Africa adds supply-shock sensitivity."),
    _t("oil", "Oil", "asset_class", summary="Crude oil powers transportation and petrochemicals, making it central to global growth and geopolitics. Futures curves and OPEC policy drive short-term price swings."),
    _t("natural_gas", "Natural Gas", "asset_class", summary="Natural gas fuels power generation and heating with growing LNG export markets. Seasonal demand and storage levels create pronounced regional price dynamics."),
    _t("crypto", "Cryptocurrency", "asset_class", summary="Cryptocurrencies are digital bearer assets on decentralized ledgers with volatile, sentiment-driven pricing. Bitcoin often trades as macro liquidity proxy; altcoins carry higher idiosyncratic risk."),
    _t("stablecoins", "Stablecoins", "asset_class", summary="Stablecoins peg value to fiat currencies, enabling crypto settlement and DeFi collateral. Reserve transparency and regulatory status determine trust beyond the peg promise."),
    _t("real_estate_asset", "Real Estate", "asset_class", summary="Real estate as an asset class spans residential, commercial, and land with income and appreciation components. Direct ownership differs from REIT liquidity and tax treatment."),
    _t("reits", "REITs", "asset_class", summary="REITs are tax-advantaged vehicles owning income-producing property and paying high dividends. They correlate with rates and sector-specific occupancy trends."),
    _t("pe_asset", "Private Equity", "asset_class", summary="Private equity funds buy and reshape companies away from public markets. J-curve reporting and long lockups suit institutional capital with patience."),
    _t("vc_asset", "Venture Capital", "asset_class", summary="Venture capital funds early-stage innovation with high failure rates and occasional outsized winners. Access is typically limited to accredited and institutional investors."),
    _t("hedge_funds", "Hedge Funds", "asset_class", summary="Hedge funds pursue absolute return using long-short, macro, and event strategies with performance fees. Liquidity terms and opacity require careful manager selection."),
    _t("collectibles_asset", "Collectibles", "asset_class", summary="Collectibles store value in physical rarity—art, coins, memorabilia—without earnings yield. Markets are opaque, illiquid, and driven by taste and authentication."),
    _t("art", "Art", "asset_class", summary="Art as an asset combines aesthetic enjoyment with potential capital appreciation on masterworks. Transaction costs, insurance, and provenance research are material."),
)

SECTOR_TOPICS: tuple[Topic, ...] = (
    _t("technology", "Technology", "sector", summary="The technology sector spans software, hardware, and services enabling digital transformation across the economy. It leads long bull markets but faces rapid obsolescence and regulatory scrutiny."),
    _t("software", "Software", "sector", parent="Technology", summary="Applications and platforms delivered digitally with high margins and recurring revenue models."),
    _t("hardware", "Hardware", "sector", parent="Technology", summary="Physical devices—computers, servers, peripherals—subject to cyclical demand and supply chains."),
    _t("semiconductors", "Semiconductors", "sector", parent="Technology", summary="Chips power every electronic device; the sector is capital intensive with boom-bust inventory cycles."),
    _t("ai", "Artificial Intelligence", "sector", parent="Technology", summary="AI companies build models, infrastructure, and applications automating cognition and decision-making."),
    _t("robotics", "Robotics", "sector", parent="Technology", summary="Robotics automates physical tasks in factories, logistics, and services with sensors and actuators."),
    _t("cloud", "Cloud Computing", "sector", parent="Technology", summary="Cloud delivers compute and storage on demand, shifting capex to opex for enterprises globally."),
    _t("cybersecurity", "Cybersecurity", "sector", parent="Technology", summary="Cybersecurity protects data and systems from breaches, a growing spend line as threats evolve."),
    _t("consumer_electronics", "Consumer Electronics", "sector", parent="Technology", summary="Smartphones, wearables, and gadgets compete on innovation cycles and brand ecosystems."),
    _t("data_centers", "Data Centers", "sector", parent="Technology", summary="Data centers house servers and networking for cloud and AI workloads with power and cooling intensity."),
    _t("quantum", "Quantum Computing", "sector", parent="Technology", summary="Quantum computing pursues exponential speedups for select problems still largely pre-commercial."),
    _t("communication", "Communication Services", "sector", summary="Telecom, media, entertainment, and interactive platforms connecting audiences and advertisers worldwide."),
    _t("healthcare", "Healthcare", "sector", summary="Pharmaceuticals, biotech, providers, and devices addressing human health with regulatory and patent dynamics."),
    _t("financials", "Financials", "sector", summary="Banks, insurers, asset managers, and payment networks intermediating capital and risk in the economy."),
    _t("consumer_discretionary", "Consumer Discretionary", "sector", summary="Retail, autos, leisure, and housing-sensitive brands tied to consumer confidence and employment."),
    _t("consumer_staples", "Consumer Staples", "sector", summary="Food, beverage, household, and personal products with steady demand through economic cycles."),
    _t("industrials", "Industrials", "sector", summary="Manufacturing, aerospace, defense, and capital goods benefiting from capex and infrastructure spending."),
    _t("energy", "Energy", "sector", summary="Oil, gas, and renewables powering industry and transport with geopolitical and environmental overlays."),
    _t("materials", "Materials", "sector", summary="Chemicals, mining, and packaging tied to global construction and industrial production cycles."),
    _t("utilities", "Utilities", "sector", summary="Regulated electric, gas, and water utilities offering bond-like equity with dividend focus."),
    _t("real_estate_sector", "Real Estate", "sector", summary="Property ownership and development spanning commercial, residential, and specialized niches."),
    _t("agriculture", "Agriculture", "sector", summary="Agribusiness, fertilizers, and farm equipment feeding global populations amid weather and trade risk."),
    _t("transportation", "Transportation", "sector", summary="Airlines, rails, trucking, and shipping moving goods and people with fuel and labor sensitivity."),
    _t("space", "Space", "sector", summary="Satellites, launch services, and space economy ventures commercializing orbit and exploration."),
    _t("emerging_industries", "Emerging Industries", "sector", summary="New sectors—EVs, clean tech, fintech—crossing traditional boundaries with rapid innovation."),
    _t("reit_office", "Office REITs", "sector", parent="Real Estate", summary="Office REITs own workplace properties sensitive to remote-work trends and lease rollover."),
    _t("reit_retail", "Retail REITs", "sector", parent="Real Estate", summary="Retail REITs hold shopping centers and malls facing e-commerce competition and tenant health."),
    _t("reit_residential", "Residential REITs", "sector", parent="Real Estate", summary="Residential REITs operate apartments and single-family rentals benefiting from housing demand."),
    _t("reit_industrial", "Industrial REITs", "sector", parent="Real Estate", summary="Industrial REITs own warehouses and logistics hubs riding e-commerce fulfillment growth."),
    _t("reit_healthcare", "Healthcare REITs", "sector", parent="Real Estate", summary="Healthcare REITs lease to hospitals, senior housing, and medical offices with demographic tailwinds."),
    _t("reit_datacenter", "Data Center REITs", "sector", parent="Real Estate", summary="Data center REITs provide colocation and connectivity for cloud and AI compute loads."),
    _t("reit_self_storage", "Self-Storage REITs", "sector", parent="Real Estate", summary="Self-storage REITs offer flexible unit rentals with resilient recession-era demand patterns."),
    _t("reit_hotel", "Hotel REITs", "sector", parent="Real Estate", summary="Hotel REITs own lodging assets with high operating leverage to travel and business cycles."),
    _t("reit_net_lease", "Net Lease REITs", "sector", parent="Real Estate", summary="Net lease REITs sign long triple-net leases to investment-grade tenants for bond-like cash flows."),
)

ANALYSIS_TOPICS: tuple[Topic, ...] = (
    _t("fundamental", "Fundamental Analysis", "analysis", status="live", formulas=("intrinsic_value",), module="analytics/value_investing.py", summary="Fundamental analysis examines financial statements, business models, and competitive position to estimate intrinsic worth. It asks what a business is truly worth independent of daily price noise."),
    _t("technical", "Technical Analysis", "analysis", status="soft", formulas=("rsi", "macd",), module="investing.formulas.technical", summary="Technical analysis studies price, volume, and pattern history to forecast short- to medium-term direction. Indicators like RSI and MACD help time entries but work best combined with risk controls and context."),
    _t("quant_analysis", "Quantitative Analysis", "analysis", status="live", formulas=("factor_value", "factor_momentum",), module="analytics/hedge_fund_stack.py", summary="Quantitative analysis applies statistical models and factor tests to systematic security selection. It replaces gut feel with reproducible signals while demanding rigorous validation."),
    _t("qualitative", "Qualitative Analysis", "analysis", summary="Qualitative analysis evaluates management quality, culture, brand strength, and governance through judgment rather than spreadsheets alone. Soft factors often explain why similar companies trade at different multiples."),
    _t("macro_analysis", "Macro Analysis", "analysis", status="live", formulas=("regime_hmm",), module="regime_detector.py", summary="Macro analysis assesses economy-wide drivers—GDP, policy, inflation—that frame sector and asset returns. Getting the macro backdrop right prevents fighting powerful headwinds with stock picking alone."),
    _t("industry", "Industry Analysis", "analysis", status="live", module="analytics/industry_comovement.py", summary="Industry analysis maps sector structure, growth drivers, and regulation to position a company within its value chain. Understanding industry economics reveals whether tailwinds or margin pressure dominate."),
    _t("competitive", "Competitive Analysis", "analysis", summary="Competitive analysis compares rivals' moats, market share, and pricing power using frameworks like Porter's five forces. It clarifies who wins long term when capital floods a fashionable sector."),
    _t("financial_statement", "Financial Statement Analysis", "analysis", status="live", module="analytics/value_investing.py", summary="Financial statement analysis dissects income, balance sheet, and cash flow for quality, trends, and red flags. Accruals, leverage, and cash conversion often tell a truer story than headline earnings."),
    _t("valuation", "Valuation Analysis", "analysis", status="live", formulas=("intrinsic_value", "margin_of_safety",), module="analytics/value_investing.py", summary="Valuation analysis converts forecasts into price estimates via DCF, multiples, and asset-based methods. The art lies in choosing conservative assumptions and comparing methods for triangulation."),
    _t("risk", "Risk Analysis", "analysis", status="live", formulas=("sharpe_ratio", "capm_beta",), module="investing.formulas.risk", summary="Risk analysis quantifies volatility, drawdown, factor exposures, and tail scenarios for position sizing. CAPM beta and Sharpe ratio help compare whether return compensates for risk taken."),
    _t("sentiment", "Sentiment Analysis", "analysis", status="live", formulas=("news_sentiment",), module="sentiment_pipeline.py", summary="Sentiment analysis gauges market mood from news, social media, surveys, and positioning data. Extreme bullishness or fear often marks turning points when fundamentals lag price."),
    _t("alt_data", "Alternative Data Analysis", "analysis", status="live", formulas=("news_sentiment", "transcript_factor",), module="intel/news_factor_engine.py", summary="Alternative data analysis uses non-traditional datasets—satellite imagery, web traffic, credit card panels—to gain informational edge. Privacy, coverage bias, and decay rates require careful validation."),
    _t("factor_analysis", "Factor Analysis", "analysis", status="live", formulas=("factor_value", "factor_momentum", "factor_quality",), module="analytics/hedge_fund_stack.py", summary="Factor analysis decomposes returns into systematic style exposures like value, size, and momentum. Knowing factor loadings explains performance and avoids unintended concentration."),
    _t("scenario", "Scenario Analysis", "analysis", status="soft", formulas=("scenario_weights",), module="investing.formulas.scenario", summary="Scenario analysis models outcomes under bull, base, and bear assumptions to stress-test thesis robustness. It forces explicit thinking about what breaks an investment case."),
    _t("monte_carlo", "Monte Carlo Simulation", "analysis", status="soft", formulas=("monte_carlo",), module="investing.formulas.scenario", summary="Monte Carlo simulation generates thousands of random paths for returns or portfolio values to estimate probability distributions. It communicates uncertainty better than single-point forecasts alone."),
    _t("dcf", "DCF Analysis", "analysis", status="live", formulas=("intrinsic_value", "terminal_value",), module="analytics/value_investing.py", summary="DCF analysis discounts projected free cash flows plus terminal value to derive enterprise and equity value. Small changes in growth or discount rate assumptions swing outputs, so sensitivity tables matter."),
    _t("wacc", "WACC Estimation", "analysis", status="soft", formulas=("wacc",), module="investing.formulas.valuation", summary="Weighted average cost of capital blends the cost of equity and after-tax cost of debt to discount future cash flows. Beta, equity risk premium, and credit spread estimates drive most DCF disagreement."),
    _t("comps", "Comparable Company Analysis", "analysis", status="soft", formulas=("ev_ebitda_comps",), module="investing.formulas.valuation", summary="Comparable company analysis values a firm using trading multiples of similar public peers such as EV/EBITDA. Adjustments for growth, margins, and control premium separate fair comps from misleading matches."),
    _t("precedent_transactions", "Precedent Transactions", "analysis", summary="Precedent transaction analysis benchmarks value using multiples paid in recent M&A deals for similar targets. Control premiums and synergies explain why deal multiples often exceed trading comps."),
    _t("economic_moat", "Economic Moat Analysis", "analysis", status="live", formulas=("buffett_quality",), module="analytics/value_investing.py", summary="Economic moat analysis identifies durable competitive advantages—network effects, switching costs, scale—that protect returns on capital. Wide moats justify higher multiples when growth reinvestment remains attractive."),
    _t("management", "Management Analysis", "analysis", summary="Management analysis judges leadership capital allocation, integrity, and alignment with minority shareholders. Great businesses with poor stewards can destroy value through empire building or dilution."),
)

def _extended_sectors() -> tuple[Topic, ...]:
    try:
        from investing.sectors_extended import SECTOR_LEAF_TOPICS

        return SECTOR_LEAF_TOPICS
    except Exception:
        return ()


ALL_TOPICS: tuple[Topic, ...] = (
    STRATEGY_TOPICS
    + ASSET_CLASS_TOPICS
    + SECTOR_TOPICS
    + _extended_sectors()
    + ANALYSIS_TOPICS
)


def all_topics() -> tuple[Topic, ...]:
    return ALL_TOPICS


def by_family(family: str) -> tuple[Topic, ...]:
    return tuple(t for t in ALL_TOPICS if t.family == family)


def by_status(status: Status) -> tuple[Topic, ...]:
    return tuple(t for t in ALL_TOPICS if t.status == status)


def topic_count() -> dict[str, int]:
    families: dict[str, int] = {}
    statuses: dict[str, int] = {}
    for t in ALL_TOPICS:
        families[t.family] = families.get(t.family, 0) + 1
        statuses[t.status] = statuses.get(t.status, 0) + 1
    return {"total": len(ALL_TOPICS), "by_family": families, "by_status": statuses}
