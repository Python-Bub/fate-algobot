"""Asset classes and sectors — deep encyclopedia chapters."""

from __future__ import annotations

from investing.knowledge import DeepChapter, FormulaSpec, register

_F = FormulaSpec


register(
    DeepChapter(
        topic_id="stocks",
        title="Stocks",
        family="asset_class",
        philosophy="""
Equities are fractional ownership claims on corporate cash flows — the engine of long-run wealth creation in developed markets. Stocks offer unlimited upside from earnings growth, buybacks, and dividends, but drawdowns of 30–50% are normal in recessions. Portfolio role: growth engine and inflation hedge over decades; size by risk tolerance and horizon.
""".strip(),
        how_it_works="""
Returns decompose into dividends, earnings growth, and multiple expansion/compression. Analyze via fundamentals (P/E, FCF yield, ROIC), sector positioning, and macro regime. Diversify across industries and geographies; single-stock risk is idiosyncratic. Tax lots, turnover, and factor tilts (value, momentum, quality) shape net outcomes.
""".strip(),
        formulas=(
            _F(
                "Total return",
                r"R = \frac{P_1 - P_0 + D}{P_0}",
                "Price appreciation plus dividends over the holding period.",
                code_fn="analytics.value_investing.analyze_value",
            ),
            _F(
                "Earnings yield",
                r"E/P = \frac{EPS}{P}",
                "Inverse of P/E; compare to bond yields for equity risk premium.",
            ),
            _F(
                "Sharpe ratio",
                r"SR = \frac{R_p - R_f}{\sigma_p}",
                "Risk-adjusted return; penalizes volatility without upside.",
            ),
        ),
        screens=(
        "Positive FCF and manageable leverage",
        "ROIC above WACC over a cycle",
        "Reasonable valuation vs history and peers",
        "Diversified revenue and geography",
        ),
        traps=(
        "Concentration in one theme or mega-cap",
        "Chasing momentum without earnings support",
        "Ignoring dilution from SBC",
        "Confusing narrative with unit economics",
        ),
        catalysts=(
        "Earnings beats and guidance raises",
        "Buyback acceleration",
        "Sector rotation into neglected areas",
        "M&A at premium",
        ),
        fate_hook="Equity analytics in `analytics/value_investing.py`; sector mapping via `analytics/industry_taxonomy.py` and co-movement clusters in `analytics/industry_comovement.py`.",
        related=(
        "etfs",
        "index_funds",
        "fundamental",
        "growth",
        ),
        further_reading=(
        "Burton Malkiel — A Random Walk Down Wall Street",
        "Aswath Damodaran — Investment Valuation",
        ),
    )
)

register(
    DeepChapter(
        topic_id="bonds",
        title="Bonds",
        family="asset_class",
        philosophy="""
Bonds are contractual claims on fixed or floating cash flows — ballast for portfolios when equities sell off. Return drivers: coupon income, price change from yield moves, and credit spread dynamics. Duration is the dominant risk: long bonds amplify rate sensitivity.
""".strip(),
        how_it_works="""
Price moves inversely to yield. Investment-grade corporates add spread over Treasuries; high yield trades equity-like in stress. Ladder maturities to manage reinvestment risk. Real return = nominal minus inflation; TIPS link to CPI.
""".strip(),
        formulas=(
            _F(
                "Current yield",
                r"CY = \frac{\text{Annual coupon}}{P}",
                "Coupon income relative to price; ignores capital gains/losses at maturity.",
            ),
            _F(
                "Modified duration",
                r"D_m \approx -\frac{1}{P}\frac{dP}{dy}",
                "Approximate % price change per 1% yield move.",
            ),
            _F(
                "Yield to maturity",
                r"P = \sum_{t=1}^{n}\frac{C}{(1+y)^t} + \frac{F}{(1+y)^n}",
                "IRR of all cash flows if held to maturity.",
            ),
        ),
        screens=(
        "Duration matched to liability horizon",
        "Credit quality appropriate to risk budget",
        "Positive real yield after inflation",
        "Liquidity for rebalancing needs",
        ),
        traps=(
        "Reaching for yield in weak credits",
        "Ignoring duration in rising-rate regimes",
        "Callable bonds shortening effective maturity",
        "Illiquid munis in stress",
        ),
        catalysts=(
        "Fed pivot lowering front-end rates",
        "Spread compression in risk-on",
        "Flight-to-quality bid in recessions",
        "Upgrade by rating agencies",
        ),
        fate_hook="Macro regime detection in `regime_detector.py` frames rate and credit backdrop for fixed-income allocation.",
        related=(
        "cash",
        "reits",
        "utilities",
        ),
        further_reading=(
        "Fabozzi — Bond Markets, Analysis, and Strategies",
        "Howard Marks — Mastering the Market Cycle",
        ),
    )
)

register(
    DeepChapter(
        topic_id="cash",
        title="Cash",
        family="asset_class",
        philosophy="""
Cash is optionality — dry powder for opportunistic deployment after selloffs and a shock absorber for near-term liabilities. Nominal safety does not guarantee real purchasing power; inflation erodes idle cash. In portfolios, cash is tactical, not strategic alpha.
""".strip(),
        how_it_works="""
T-bills, money markets, and high-yield savings pay short rates tied to central bank policy. Sweep accounts and ultra-short bond funds add modest yield with minimal duration. Hold enough for 6–12 months expenses and known outflows; excess cash is a drag in bull markets.
""".strip(),
        formulas=(
            _F(
                "Real cash return",
                r"r_{real} \approx r_{nom} - \pi",
                "Nominal yield minus expected inflation.",
            ),
            _F(
                "Opportunity cost",
                r"OC = R_{equity} - r_{cash}",
                "Foregone return while waiting to deploy.",
            ),
        ),
        screens=(
        "FDIC/SIPC coverage limits respected",
        "No lockups needed for near-term spending",
        "Yield competitive vs T-bill alternatives",
        ),
        traps=(
        "Inflation silently eroding purchasing power",
        "Chasing yield in non-liquid structures",
        "Hoarding cash from fear indefinitely",
        "Confusing stablecoin yield with cash",
        ),
        catalysts=(
        "Market dislocation creating entry points",
        "Rate cuts reducing opportunity cost",
        "Known large purchase requiring liquidity",
        ),
        fate_hook="Cash allocation informed by macro regime signals in `regime_detector.py`.",
        related=(
        "bonds",
        "stablecoins",
        "macro_analysis",
        ),
        further_reading=(
        "Nick Murray — Simple Wealth, Inevitable Wealth",
        ),
    )
)

register(
    DeepChapter(
        topic_id="etfs",
        title="ETFs",
        family="asset_class",
        philosophy="""
ETFs democratize diversified exposure with intraday liquidity and transparent holdings. They wrap indices, factors, sectors, and alternatives in a single ticker — efficient building blocks for asset allocation. Cost and tracking difference vs benchmark matter more than brand.
""".strip(),
        how_it_works="""
Creation/redemption via authorized participants keeps ETF price near NAV. Passive ETFs minimize turnover and tax events; active ETFs add manager discretion. Watch expense ratio, bid-ask spread, AUM, and index methodology (equal-weight vs cap-weight).
""".strip(),
        formulas=(
            _F(
                "Tracking difference",
                r"TD = R_{ETF} - R_{index}",
                "Net performance gap after fees, sampling, and dividends.",
            ),
            _F(
                "Expense ratio drag",
                r"R_{net} \approx R_{gross} - ER",
                "Annual fee compounds against long-run returns.",
            ),
        ),
        screens=(
        "Expense ratio < category median",
        "AUM and volume support tight spreads",
        "Index methodology matches thesis",
        "Tax efficiency vs mutual fund alternative",
        ),
        traps=(
        "Leveraged/inverse ETFs for long holds",
        "Thin ETFs with wide spreads",
        "Synthetic replication counterparty risk",
        "Sector ETFs masquerading as diversification",
        ),
        catalysts=(
        "Fee compression across providers",
        "New thematic ETF launches",
        "Tax-loss harvesting within ETF basket",
        ),
        fate_hook="Universe screening uses sector tags from `analytics/industry_taxonomy.py` for ETF-equity overlap analysis.",
        related=(
        "index_funds",
        "stocks",
        "mutual_funds",
        ),
        further_reading=(
        "ETF.com — ETF Education Center",
        "Rick Ferri — The Power of Passive Investing",
        ),
    )
)

register(
    DeepChapter(
        topic_id="mutual_funds",
        title="Mutual Funds",
        family="asset_class",
        philosophy="""
Mutual funds pool capital for professional management, priced once daily at NAV. Active share and fee drag determine whether managers earn their keep. They suit automatic investment plans but often lag passive alternatives after fees and taxes.
""".strip(),
        how_it_works="""
Open-end structure: buy/sell at end-of-day NAV. Active managers pick securities; passive clones track indices. Turnover generates taxable distributions in taxable accounts. Compare expense ratio, active share, manager tenure, and after-tax returns.
""".strip(),
        formulas=(
            _F(
                "Active share",
                r"AS = \frac{1}{2}\sum_i |w_i - w_{bench,i}|",
                "Portfolio deviation from benchmark; low AS suggests closet indexing.",
            ),
            _F(
                "Information ratio",
                r"IR = \frac{R_p - R_b}{\sigma(R_p - R_b)}",
                "Active return per unit of tracking error.",
            ),
        ),
        screens=(
        "Expense ratio justified by persistent alpha",
        "Manager tenure > 5 years",
        "Low turnover in taxable accounts",
        "Clear strategy consistency",
        ),
        traps=(
        "Style drift without notice",
        "Morningstar rear-view chasing",
        "Hidden 12b-1 and soft-dollar costs",
        "Tax-inefficient year-end distributions",
        ),
        catalysts=(
        "Star manager departure or arrival",
        "Strategy capacity constraints",
        "Regulatory fee disclosure reforms",
        ),
        fate_hook="Fund holdings overlap mapped via `analytics/industry_comovement.py` peer clusters.",
        related=(
        "etfs",
        "index_funds",
        "asset_management",
        ),
        further_reading=(
        "John Bogle — Common Sense on Mutual Funds",
        ),
    )
)

register(
    DeepChapter(
        topic_id="index_funds",
        title="Index Funds",
        family="asset_class",
        philosophy="""
Index funds deliver market beta at minimal cost — the default core holding for most long-horizon investors. Beating the index after fees is hard; matching it cheaply is a durable edge. Cap-weighted indices favor winners automatically; factor indices tilt deliberately.
""".strip(),
        how_it_works="""
Full replication or sampling tracks a published index (S&P 500, Total Market, MSCI World). Rebalance on index committee changes. Dividends reinvested; tracking error from cash drag and sampling. Use in 401(k)s and IRAs where ETF access is limited.
""".strip(),
        formulas=(
            _F(
                "Market beta",
                r"\beta = \frac{\mathrm{Cov}(R_p, R_m)}{\mathrm{Var}(R_m)}",
                "Sensitivity to broad market moves; index funds target β ≈ 1.",
            ),
            _F(
                "Cap weight",
                r"w_i = \frac{MC_i}{\sum MC}",
                "Largest companies dominate index return contribution.",
            ),
        ),
        screens=(
        "Lowest expense ratio in category",
        "Tracking error < 0.2% annually",
        "Broad diversification (500+ names)",
        "Dividend reinvestment available",
        ),
        traps=(
        "Concentration risk in cap-weight indices",
        "Front-running index rebalances",
        "Ignoring international/emerging allocation",
        "Confusing index with strategy",
        ),
        catalysts=(
        "Index inclusion for mid-cap graduates",
        "Fee wars driving ER toward zero",
        "Custom index launches",
        ),
        fate_hook="Benchmark constituents classified in `analytics/industry_taxonomy.py` for sector-neutral overlays.",
        related=(
        "etfs",
        "stocks",
        "passive_investing",
        ),
        further_reading=(
        "John Bogle — The Little Book of Common Sense Investing",
        ),
    )
)

register(
    DeepChapter(
        topic_id="options_asset",
        title="Options",
        family="asset_class",
        philosophy="""
Options transfer risk between parties — leverage, hedging, and income beyond direct ownership. Buyers pay premium for convexity; sellers collect theta while bearing tail risk. Not an asset class for buy-and-hold; a toolkit requiring defined risk.
""".strip(),
        how_it_works="""
Calls profit from upside above strike; puts protect downside. Spreads cap risk/reward. Greeks (delta, gamma, theta, vega) describe sensitivity. Earnings and ex-div dates inject volatility. Use for hedging equity books or generating premium on held stocks.
""".strip(),
        formulas=(
            _F(
                "Put-call parity",
                r"C - P = S - Ke^{-rT}",
                "Arbitrage link between calls, puts, stock, and strike PV.",
            ),
            _F(
                "Black-Scholes",
                r"C = S N(d_1) - Ke^{-rT} N(d_2)",
                "Theoretical European call price under lognormal assumptions.",
                code_fn="investing.formulas.derivatives",
            ),
        ),
        screens=(
        "Defined max loss on every trade",
        "Liquidity: tight bid-ask on strikes",
        "IV rank vs historical for selling premium",
        "Position size < 5% of portfolio per idea",
        ),
        traps=(
        "Selling naked options without margin discipline",
        "Holding short options through binary events",
        "Ignoring early assignment on American calls",
        "Confusing lottery tickets with investing",
        ),
        catalysts=(
        "Volatility crush post-earnings",
        "Dividend capture with covered calls",
        "Portfolio hedge before macro events",
        ),
        fate_hook="Options context in `investing/knowledge/derivatives.py`; underlying equities tagged via `analytics/industry_taxonomy.py`.",
        related=(
        "futures",
        "swaps",
        "covered_calls",
        ),
        further_reading=(
        "Sheldon Natenberg — Option Volatility and Pricing",
        ),
    )
)

register(
    DeepChapter(
        topic_id="futures",
        title="Futures",
        family="asset_class",
        philosophy="""
Futures obligate future delivery at an agreed price — the backbone of commodity, rate, and index trading. Margin and daily mark-to-market amplify capital efficiency but also blow-up risk. Basis (spot vs futures) reveals carry and storage economics.
""".strip(),
        how_it_works="""
Long futures profit when price rises; short the reverse. Roll contracts before expiry to maintain exposure — roll yield can help or hurt. Contango (upward sloping curve) penalizes long commodity holders; backwardation rewards them. Index futures offer cheap beta with leverage.
""".strip(),
        formulas=(
            _F(
                "Basis",
                r"B = S - F",
                "Spot minus futures; converges to zero at expiry.",
            ),
            _F(
                "Cost of carry",
                r"F \approx S e^{(r + u - y)T}",
                "Storage, financing, and convenience yield drive curve shape.",
            ),
        ),
        screens=(
        "Margin buffer for 2–3x normal daily move",
        "Roll schedule planned before expiry week",
        "Curve shape understood for directional bias",
        "Correlation to portfolio hedge objective",
        ),
        traps=(
        "Leverage without stop discipline",
        "Negative roll yield eroding commodity longs",
        "Delivery on physical contracts if not closed",
        "Illiquid back-month contracts",
        ),
        catalysts=(
        "OPEC or weather shocks moving curves",
        "Curve inversion signaling tight supply",
        "Index rebalancing flows in equity futures",
        ),
        fate_hook="Commodity futures tie to energy/materials sector signals in `analytics/industry_comovement.py`.",
        related=(
        "forwards",
        "commodities",
        "oil",
        ),
        further_reading=(
        "Hull — Options, Futures, and Other Derivatives",
        ),
    )
)

register(
    DeepChapter(
        topic_id="forwards",
        title="Forwards",
        family="asset_class",
        philosophy="""
Forwards are customized OTC agreements to exchange an asset at a future date — tailored for corporate hedging where exchange futures don't fit. Counterparty credit risk and illiquidity are the price of customization.
""".strip(),
        how_it_works="""
Corporates hedge FX receivables, commodity inputs, or interest rates via bilateral forwards with banks. Terms (notional, date, price) are negotiated; no daily MTM on exchange. Mark-to-market for accounting; CSA agreements collateralize exposure.
""".strip(),
        formulas=(
            _F(
                "Forward price",
                r"F_0 = S_0 e^{rT}",
                "Cost-of-carry for non-dividend asset in risk-neutral measure.",
            ),
            _F(
                "FX forward",
                r"F = S \frac{1 + r_d T}{1 + r_f T}",
                "Covered interest parity links FX forwards to rate differential.",
            ),
        ),
        screens=(
        "Counterparty rated investment grade",
        "Hedge ratio matches economic exposure",
        "Accounting hedge designation if required",
        "CSA collateral terms clear",
        ),
        traps=(
        "Wrong-way risk with correlated counterparty",
        "Over-hedging operational exposure",
        "Forgetting roll/renewal at expiry",
        "Basis risk vs imperfect hedge",
        ),
        catalysts=(
        "Rate differential shifts moving FX forwards",
        "Commodity price spikes triggering margin calls",
        "Regulatory IM requirements changing costs",
        ),
        fate_hook="Corporate FX/commodity exposure often maps to multinational sectors in `analytics/industry_taxonomy.py`.",
        related=(
        "futures",
        "swaps",
        "macro_analysis",
        ),
        further_reading=(
        "Hull — Options, Futures, and Other Derivatives",
        ),
    )
)

register(
    DeepChapter(
        topic_id="swaps",
        title="Swaps",
        family="asset_class",
        philosophy="""
Swaps exchange cash-flow streams — fixed for floating rates, currencies, or credit exposure — enabling precise institutional hedging and relative-value trades. They dominate balance-sheet management at banks and large corporates.
""".strip(),
        how_it_works="""
In an interest-rate swap, one party pays fixed and receives floating (or vice versa) on a notional without exchanging principal. CDS transfer credit risk; currency swaps exchange principal and coupons across currencies. OTC nature requires ISDA documentation and collateral.
""".strip(),
        formulas=(
            _F(
                "Swap PV",
                r"V = \sum_{i} (CF_{fixed,i} - CF_{float,i}) \cdot DF_i",
                "Net present value of fixed vs floating legs.",
            ),
            _F(
                "DV01",
                r"\frac{dV}{dy} \approx -D \cdot V \cdot 0.0001",
                "Dollar value of 1bp rate move on swap book.",
            ),
        ),
        screens=(
        "ISDA master with CSA in place",
        "Notional matches underlying debt exposure",
        "Mark-to-market monitored daily",
        "Clear termination events defined",
        ),
        traps=(
        "Unhedged mark-to-market volatility",
        "Wrong index on floating leg (SOFR vs LIBOR legacy)",
        "Counterparty default in stress",
        "Basis between swap curve and bond curve",
        ),
        catalysts=(
        "Central bank rate path repricing",
        "Credit spread blowouts affecting CDS",
        "Regulatory capital changes on swap exposure",
        ),
        fate_hook="Rate-sensitive sectors (utilities, REITs) in `analytics/industry_comovement.py` correlate with swap-implied rate views.",
        related=(
        "bonds",
        "forwards",
        "financials",
        ),
        further_reading=(
        "Tuckman & Serrat — Fixed Income Securities",
        ),
    )
)

register(
    DeepChapter(
        topic_id="commodities",
        title="Commodities",
        family="asset_class",
        philosophy="""
Commodities are real assets priced by global supply, demand, and storage economics — diversifiers with low long-run correlation to equities. They hedge inflation but carry no yield; returns come from price change and roll yield, not cash flow.
""".strip(),
        how_it_works="""
Access via futures, ETFs, or producers. Energy, metals, and agriculture respond to different drivers: OPEC, China capex, weather. Contango erodes passive long exposure; active roll selection matters. Producers offer equity-like leverage to commodity prices.
""".strip(),
        formulas=(
            _F(
                "Roll yield",
                r"RY \approx \frac{F_{near} - F_{next}}{F_{near}}",
                "Return from rolling front contract to next month.",
            ),
            _F(
                "Real commodity return",
                r"r_{real} \approx r_{nom} - \pi",
                "Nominal commodity move minus inflation.",
            ),
        ),
        screens=(
        "Understand contango/backwardation before going long",
        "Diversify across energy, metals, agriculture",
        "Size for volatility (2–3x equity vol)",
        "Prefer backwardated markets for passive longs",
        ),
        traps=(
        "Buy-and-hold commodity ETFs in persistent contango",
        "Single-commodity concentration",
        "Confusing producer equity with spot exposure",
        "Ignoring storage and transport bottlenecks",
        ),
        catalysts=(
        "Supply disruption (war, weather, strike)",
        "China stimulus boosting industrial demand",
        "Dollar weakness lifting dollar-priced commodities",
        ),
        fate_hook="Commodity producers classified under energy/materials in `analytics/industry_taxonomy.py`.",
        related=(
        "gold",
        "oil",
        "futures",
        ),
        further_reading=(
        "Claude Erb & Campbell Harvey — Expected Returns on Commodities",
        ),
    )
)

register(
    DeepChapter(
        topic_id="gold",
        title="Gold",
        family="asset_class",
        philosophy="""
Gold is the oldest monetary metal — no yield, no cash flow, but centuries of store-of-value demand. It often rises when real yields fall, the dollar weakens, or geopolitical fear spikes. Portfolio role: tail hedge and crisis liquidity, not growth engine.
""".strip(),
        how_it_works="""
Price driven by real rates, USD, central-bank buying, and jewelry/investment demand. Physical, ETFs (GLD), or miners provide exposure; miners add operating leverage. Gold correlates weakly with equities long-run but can surge in panic.
""".strip(),
        formulas=(
            _F(
                "Real yield link",
                r"P_{gold} \uparrow \text{ when } r_{real} \downarrow",
                "Inverse relationship with inflation-adjusted bond yields.",
            ),
            _F(
                "Miner leverage",
                r"\beta_{miner} > 1 \text{ to gold price}",
                "AISC margins amplify gold moves in equity form.",
            ),
        ),
        screens=(
        "Allocation 5–10% as diversifier",
        "Prefer low-fee physical ETF over levered miners",
        "Monitor real 10y yield as macro driver",
        "Rebalance after crisis spikes",
        ),
        traps=(
        "Expecting income from non-yielding metal",
        "Miner operational risk masquerading as gold exposure",
        "Overweighting after parabolic rallies",
        "Storage and insurance costs on physical bars",
        ),
        catalysts=(
        "Fed easing lowering real yields",
        "Central bank reserve diversification",
        "Geopolitical escalation",
        "USD structural decline",
        ),
        fate_hook="Gold miners mapped to materials sector leaves in `analytics/industry_taxonomy.py`.",
        related=(
        "silver",
        "commodities",
        "macro_analysis",
        ),
        further_reading=(
        "Ray Dalio — Principles for Dealing with the Changing World Order",
        ),
    )
)

register(
    DeepChapter(
        topic_id="silver",
        title="Silver",
        family="asset_class",
        philosophy="""
Silver straddles monetary and industrial demand — more volatile than gold with dual drivers from investment flows and solar/electronics fabrication. Reflationary industrial upswings can amplify silver vs gold.
""".strip(),
        how_it_works="""
Gold/silver ratio signals relative value; high ratio favors silver catch-up. Industrial ~50% of demand ties to global manufacturing. Miners and ETFs (SLV) provide access; physical coins/bars for direct holding.
""".strip(),
        formulas=(
            _F(
                "Gold/silver ratio",
                r"GSR = \frac{P_{gold}}{P_{silver}}",
                "Historical mean ~60; extremes signal relative value.",
            ),
            _F(
                "Industrial demand share",
                r"\text{Industrial} / \text{Total demand}",
                "Higher share = more cyclical silver behavior.",
            ),
        ),
        screens=(
        "GSR above historical mean for relative value",
        "Solar capex cycle supportive",
        "Volatility budget allows 2x gold sizing",
        "Prefer low-cost ETF or tier-1 miners",
        ),
        traps=(
        "Treat silver as gold-lite without industrial risk",
        "Thin-market manipulation in futures",
        "Miner by-product economics distorting cost curves",
        "Ignoring gold/silver ratio extremes",
        ),
        catalysts=(
        "Solar installation boom",
        "Gold rally pulling silver beta",
        "GSR mean reversion trade",
        "Industrial restocking cycle",
        ),
        fate_hook="Silver miners under materials/precious metals in `analytics/industry_taxonomy.py`.",
        related=(
        "gold",
        "platinum",
        "solar",
        ),
        further_reading=(
        "The Silver Institute — World Silver Survey",
        ),
    )
)

register(
    DeepChapter(
        topic_id="platinum",
        title="Platinum",
        family="asset_class",
        philosophy="""
Platinum is a precious industrial metal — catalytic converters, hydrogen fuel cells, and jewelry. South African supply concentration creates supply-shock sensitivity rare in other metals.
""".strip(),
        how_it_works="""
Auto catalyst demand tied to vehicle production and emissions rules; hydrogen economy offers long-duration optionality. PGM basket trades (platinum/palladium spread) reflect substitution dynamics. Physical ETFs and miners provide equity access.
""".strip(),
        formulas=(
            _F(
                "Platinum/palladium spread",
                r"S = P_{Pt} - P_{Pd}",
                "Substitution in autocatalysts moves spread.",
            ),
            _F(
                "Supply concentration",
                r"SA\ share \approx 70\%",
                "Single-region risk premium in platinum pricing.",
            ),
        ),
        screens=(
        "Auto production cycle direction",
        "Hydrogen policy tailwinds",
        "SA power/load-shedding supply risk monitored",
        "Small position size given illiquidity",
        ),
        traps=(
        "ICE-to-EV transition destroying autocatalyst demand",
        "SA labor and power disruptions",
        "Illiquid market with wide spreads",
        "Confusing platinum with generic precious metals",
        ),
        catalysts=(
        "Hydrogen infrastructure investment",
        "Emissions regulation tightening PGM loadings",
        "SA supply disruption",
        "Jewelry demand recovery in China",
        ),
        fate_hook="PGM miners classified under materials in `analytics/industry_taxonomy.py`.",
        related=(
        "gold",
        "silver",
        "hydrogen",
        ),
        further_reading=(
        "World Platinum Investment Council — quarterly demand reports",
        ),
    )
)

register(
    DeepChapter(
        topic_id="oil",
        title="Oil",
        family="asset_class",
        philosophy="""
Crude oil powers global transport and petrochemicals — the most geopolitically sensitive commodity. Short-term price swings from OPEC policy, inventory, and demand shocks; long-run challenged by energy transition.
""".strip(),
        how_it_works="""
Brent and WTI benchmarks; futures curve shape signals tightness. E&P equities offer leveraged oil beta with operational risk; refiners earn crack spreads. OPEC+ cuts, shale responsiveness, and SPR releases move markets.
""".strip(),
        formulas=(
            _F(
                "Crack spread",
                r"CS = P_{gasoline} + P_{distillate} - P_{crude}",
                "Refiner margin from converting crude to products.",
            ),
            _F(
                "Breakeven shale",
                r"P_{BE} = \frac{OPEX + DDA}{barrels}",
                "Price needed for shale producer cash neutrality.",
            ),
        ),
        screens=(
        "Curve backwardation for bullish structure",
        "OPEC discipline vs cheating history",
        "Global demand indicators (PMI, miles driven)",
        "E&P balance sheet strength for equity exposure",
        ),
        traps=(
        "Permian growth overwhelming OPEC cuts",
        "Refining capacity bottlenecks distorting cracks",
        "Geopolitical premium fading slowly",
        "Energy transition stranding reserves",
        ),
        catalysts=(
        "OPEC surprise cut or hike",
        "Middle East supply disruption",
        "SPR release or refill",
        "China demand stimulus",
        ),
        fate_hook="Energy sector E&P/refining leaves in `analytics/industry_taxonomy.py`; co-movement clusters in `analytics/industry_comovement.py`.",
        related=(
        "natural_gas",
        "energy",
        "oil_exploration",
        ),
        further_reading=(
        "Daniel Yergin — The Prize",
        ),
    )
)

register(
    DeepChapter(
        topic_id="natural_gas",
        title="Natural Gas",
        family="asset_class",
        philosophy="""
Natural gas bridges coal-to-renewables transition — power generation, heating, and growing LNG export markets. As a commodity asset class, seasonal demand and storage levels create pronounced regional price dynamics unlike global oil. As an equity sector (E&P and midstream), the same drivers transmit to producer cash flows, dividend coverage, and balance-sheet stress — highly cyclical with commodity torque.
""".strip(),
        how_it_works="""
Henry Hub (US) vs TTF (Europe) vs JKM (Asia) benchmarks diverge with infrastructure. Winter heating and summer cooling drive seasonal spikes; LNG liquefaction adds global arbitrage. For equities, analyze breakeven costs, hedging books, pipeline contract mix (fee-based vs commodity-exposed), and leverage through the price cycle. Mature producers trade on P/E and FCF yield at mid-cycle gas; growth LNG names on project NPV and take-or-pay contracts. Screen for balance-sheet resilience, capital discipline, and peer-relative cost curves.
""".strip(),
        formulas=(
            _F(
                "Storage vs 5yr avg",
                r"\Delta S = S_{now} - S_{5yr}",
                "Inventory surplus/deficit drives seasonal pricing.",
            ),
            _F(
                "Spark spread",
                r"SS = P_{power} - \frac{P_{gas}}{HR}",
                "Gas plant profitability: power price minus gas cost.",
            ),
        ),
        screens=(
        "Storage trajectory into injection/withdrawal season",
        "LNG export capacity utilization",
        "Weather forecast for heating/cooling demand",
        "Pipeline constraint bottlenecks",
        "Top-quartile ROIC vs gas E&P/midstream peers",
        "Net debt/EBITDA manageable for cycle stage",
        ),
        traps=(
        "Negative prices at hub during oversupply",
        "Regulatory bans on new pipeline capacity",
        "Renewables cannibalizing gas peaker hours",
        "Single-basin producer concentration",
        "Secular decline misread as cyclical dip in gas equities",
        "Equity dilution from growth capex or acquisitions",
        ),
        catalysts=(
        "Polar vortex demand spike",
        "LNG export terminal startup",
        "Coal plant retirement boosting gas burn",
        "EU restocking after crisis",
        "Market share gains vs sub-industry peers",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="Natural gas producers and midstream under energy in `analytics/industry_taxonomy.py`; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "oil",
        "lng",
        "utilities",
        "energy",
        ),
        further_reading=(
        "EIA — Natural Gas Weekly Update",
        ),
    )
)

register(
    DeepChapter(
        topic_id="crypto",
        title="Cryptocurrency",
        family="asset_class",
        philosophy="""
Cryptocurrencies are digital bearer assets on decentralized ledgers — volatile, sentiment-driven, and regulatory uncertain. Bitcoin trades as macro liquidity and digital-gold narrative; altcoins carry higher idiosyncratic and smart-contract risk.
""".strip(),
        how_it_works="""
BTC/ETH dominate market cap; on-chain metrics (hash rate, active addresses, exchange flows) supplement price analysis. Halving cycles, ETF flows, and stablecoin supply affect liquidity. Size small (1–5% max); expect 50%+ drawdowns.
""".strip(),
        formulas=(
            _F(
                "Realized volatility",
                r"\sigma_{real} = \sqrt{\frac{252}{n}\sum r_i^2}",
                "Annualized daily return std; crypto often 60–100%+.",
            ),
            _F(
                "NVT ratio",
                r"NVT = \frac{Market\ Cap}{Daily\ On\text{-}chain\ Volume}",
                "Network value to transactions; high NVT suggests overvaluation.",
            ),
        ),
        screens=(
        "Position size ≤ 5% of portfolio",
        "Cold storage for long holds",
        "Regulatory jurisdiction clarity",
        "Liquidity on major exchanges",
        ),
        traps=(
        "Leverage on centralized exchanges",
        "Altcoin total loss risk",
        "Custody and key-loss irreversibility",
        "Confusing narrative with adoption metrics",
        ),
        catalysts=(
        "Spot ETF inflows",
        "Halving supply shock",
        "Institutional custody adoption",
        "Regulatory clarity legislation",
        ),
        fate_hook="Crypto-adjacent equities (miners, exchanges) tagged in `analytics/industry_taxonomy.py` under emerging industries.",
        related=(
        "stablecoins",
        "blockchain_infra",
        "digital_payments",
        ),
        further_reading=(
        "Saifedean Ammous — The Bitcoin Standard",
        "Chris Burniske — Cryptoassets",
        ),
    )
)

register(
    DeepChapter(
        topic_id="stablecoins",
        title="Stablecoins",
        family="asset_class",
        philosophy="""
Stablecoins peg to fiat (usually USD) — settlement rails for crypto markets and DeFi collateral. Trust depends on reserve transparency and regulatory status, not just the peg promise.
""".strip(),
        how_it_works="""
Fiat-backed (USDC, USDT) hold Treasuries/bank deposits; algorithmic designs failed historically. Yield on reserves flows to issuers. De-pegs occur when reserves questioned (SVB/USDC event). Use for trading settlement, not long-term savings.
""".strip(),
        formulas=(
            _F(
                "Peg deviation",
                r"\Delta = \frac{P - 1.00}{1.00}",
                "Premium/discount to $1 signals market stress.",
            ),
            _F(
                "Reserve ratio",
                r"RR = \frac{Reserves}{Outstanding}",
                "Must exceed 100% for full backing.",
            ),
        ),
        screens=(
        "Monthly attestation from Big-4 auditor",
        "Short-duration Treasuries dominate reserves",
        "Redemption tested at scale",
        "Regulatory license or charter progress",
        ),
        traps=(
        "Algorithmic stablecoin reflexive death spirals",
        "Opaque reserve composition",
        "Counterparty bank failure (USDC/SVB)",
        "Yield chasing on unregulated issuers",
        ),
        catalysts=(
        "Stablecoin legislation passing",
        "Bank charter for major issuer",
        "De-pegging creating arbitrage or panic",
        "Fed payment system integration",
        ),
        fate_hook="FinTech and blockchain infrastructure leaves in `analytics/industry_taxonomy.py`.",
        related=(
        "crypto",
        "digital_payments",
        "blockchain_infra",
        ),
        further_reading=(
        "BIS — Stablecoins and the future of money",
        ),
    )
)

register(
    DeepChapter(
        topic_id="real_estate_asset",
        title="Real Estate",
        family="asset_class",
        philosophy="""
Real estate combines income (rent) and appreciation on illiquid physical property — direct ownership differs from REIT liquidity and tax treatment. Leverage amplifies returns but also foreclosure risk.
""".strip(),
        how_it_works="""
Direct: buy, operate, maintain, sell. Cap rate = NOI/price. Leverage via mortgage; depreciation shelters income. REITs offer liquid fractional exposure. Location, tenant quality, and rate environment drive values.
""".strip(),
        formulas=(
            _F(
                "Cap rate",
                r"CR = \frac{NOI}{V}",
                "Unlevered yield; inverse relationship with property values.",
            ),
            _F(
                "Cash-on-cash",
                r"CoC = \frac{CF_{after\ debt}}{Equity}",
                "Levered cash return on invested equity.",
            ),
        ),
        screens=(
        "Cap rate vs local market comps",
        "Debt service coverage > 1.25x",
        "Tenant credit and lease term",
        "Exit liquidity plan defined",
        ),
        traps=(
        "Over-leveraging into rate hikes",
        "Vacancy and capex underestimation",
        "Illiquidity in downturns",
        "Ignoring property tax and insurance inflation",
        ),
        catalysts=(
        "Rate cuts lowering cap rates",
        "Gentrification or rezoning",
        "Inflation passing through to rents",
        "1031 exchange deferring gains",
        ),
        fate_hook="REIT subtypes mapped in `analytics/industry_taxonomy.py`; property-type co-movement in `analytics/industry_comovement.py`.",
        related=(
        "reits",
        "reit_residential",
        "real_estate_sector",
        ),
        further_reading=(
        "Gary Keller — The Millionaire Real Estate Investor",
        ),
    )
)

register(
    DeepChapter(
        topic_id="reits",
        title="REITs",
        family="asset_class",
        philosophy="""
REITs are tax-advantaged vehicles owning income-producing property — high dividends, rate sensitivity, and sector-specific occupancy trends. They bridge direct real estate economics with public-market liquidity.
""".strip(),
        how_it_works="""
Must distribute 90%+ of taxable income. Analyze AFFO (adjusted funds from operations), not GAAP EPS. Property types (industrial, residential, data center) have different cycles. NAV discounts/premiums signal market vs appraised value.
""".strip(),
        formulas=(
            _F(
                "AFFO yield",
                r"AFFO\ yield = \frac{AFFO\ per\ share}{Price}",
                "True cash earnings yield after maintenance capex.",
            ),
            _F(
                "FFO",
                r"FFO = Net\ Income + Depreciation - Gains\ on\ sales",
                "REIT earnings metric adding back non-cash depreciation.",
            ),
            _F(
                "NAV premium",
                r"Prem = \frac{Price - NAV\ per\ share}{NAV\ per\ share}",
                "Market price vs appraised asset value.",
            ),
        ),
        screens=(
        "AFFO payout ratio < 85% for safety",
        "Occupancy and same-store NOI growth positive",
        "Weighted avg lease term and tenant quality",
        "Debt/EBITDA appropriate for property type",
        ),
        traps=(
        "Buying on dividend yield alone ignoring AFFO coverage",
        "Rate spike compressing all REIT multiples",
        "Development pipeline execution risk",
        "Non-traded REIT illiquidity and fees",
        ),
        catalysts=(
        "Fed pivot lowering discount rates",
        "Occupancy recovery post-disruption",
        "Asset sales at premium to NAV",
        "Index inclusion increasing float",
        ),
        fate_hook="REIT property-type taxonomy in `analytics/industry_taxonomy.py`; sector co-movement clusters in `analytics/industry_comovement.py`.",
        related=(
        "real_estate_asset",
        "reit_industrial",
        "reit_datacenter",
        ),
        further_reading=(
        "NAREIT — REIT industry fundamentals",
        "Green Street — REIT research",
        ),
    )
)

register(
    DeepChapter(
        topic_id="pe_asset",
        title="Private Equity",
        family="asset_class",
        philosophy="""
Private equity buys and reshapes companies away from public markets — illiquidity premium and operational improvement vs J-curve reporting and long lockups. Suited to institutional capital with patience.
""".strip(),
        how_it_works="""
GP raises fund, acquires companies (LBO), improves operations, exits via IPO/sale. IRR and MOIC measure performance; J-curve shows early losses from fees and write-ups later. Vintage year diversification matters; top-quartile GPs persist.
""".strip(),
        formulas=(
            _F(
                "MOIC",
                r"MOIC = \frac{Distributions + NAV}{Paid\text{-}in\ capital}",
                "Multiple on invested capital.",
            ),
            _F(
                "IRR",
                r"\sum_{t}\frac{CF_t}{(1+IRR)^t} = 0",
                "Time-weighted return; sensitive to exit timing.",
            ),
        ),
        screens=(
        "GP track record across vintages",
        "Fund size vs strategy capacity",
        "Fee structure (2/20 vs discounted)",
        "Diversified vintage and strategy exposure",
        ),
        traps=(
        "Stale NAV marking in downturns",
        "Fee drag without DPI returns",
        "Re-leveraging same assets across funds",
        "Illiquidity during personal cash needs",
        ),
        catalysts=(
        "IPO window reopening for exits",
        "Credit market easing for LBO financing",
        "Public-to-private take-private wave",
        "Secondary market LP stake sales",
        ),
        fate_hook="Listed PE sponsors under financials sector in `analytics/industry_taxonomy.py`.",
        related=(
        "vc_asset",
        "sector_private_equity",
        "hedge_funds",
        ),
        further_reading=(
        "Bain — Global Private Equity Report",
        ),
    )
)

register(
    DeepChapter(
        topic_id="vc_asset",
        title="Venture Capital",
        family="asset_class",
        philosophy="""
Venture capital funds early-stage innovation — power-law returns where a few winners pay for many zeros. Access limited to accredited/institutional investors; patience through 10+ year fund lives required.
""".strip(),
        how_it_works="""
Seed to growth stages; GPs pick teams and markets, deploy capital in tranches tied to milestones. TVPI and DPI track paper vs realized returns. DPI < 1 for years is normal; fund concentration in winners drives outcomes.
""".strip(),
        formulas=(
            _F(
                "TVPI",
                r"TVPI = \frac{NAV + Distributions}{Paid\text{-}in}",
                "Total value to paid-in capital.",
            ),
            _F(
                "DPI",
                r"DPI = \frac{Distributions}{Paid\text{-}in}",
                "Realized return; ultimate measure of cash back.",
            ),
        ),
        screens=(
        "GP specialization matches sector thesis",
        "Fund size appropriate for stage",
        "Portfolio construction 25+ companies",
        "Pro-rata rights in winners preserved",
        ),
        traps=(
        "Mark-to-market fantasy in down rounds",
        "Single-company fund concentration",
        "Recycling without DPI",
        "Accessing VC via public proxies with misfit exposure",
        ),
        catalysts=(
        "IPO or M&A exit for portfolio company",
        "Follow-on round at higher valuation",
        "Sector tailwind (AI, biotech)",
        "Secondary sale providing liquidity",
        ),
        fate_hook="Public VC-adjacent names under `sector_venture_capital` in `analytics/industry_taxonomy.py`.",
        related=(
        "pe_asset",
        "sector_venture_capital",
        "ai",
        ),
        further_reading=(
        "Sequoia — Adventures in Capitalism",
        "Paul Graham — essays on startups",
        ),
    )
)

register(
    DeepChapter(
        topic_id="hedge_funds",
        title="Hedge Funds",
        family="asset_class",
        philosophy="""
Hedge funds pursue absolute return via long-short, macro, and event strategies — performance fees and opacity require careful manager selection. Not an asset class but a vehicle structure.
""".strip(),
        how_it_works="""
Long/short equity, global macro, quant, and event-driven styles differ radically. Lockups, gates, and side pockets affect liquidity. Sharpe and max drawdown vs benchmarks; alpha decay as AUM scales.
""".strip(),
        formulas=(
            _F(
                "Sharpe ratio",
                r"SR = \frac{R_p - R_f}{\sigma_p}",
                "Risk-adjusted return for absolute-return mandate.",
            ),
            _F(
                "Max drawdown",
                r"MDD = \max_t \frac{Peak_t - Trough_t}{Peak_t}",
                "Worst peak-to-trough loss.",
            ),
        ),
        screens=(
        "Audited track record 5+ years",
        "AUM vs strategy capacity",
        "Liquidity terms match investor horizon",
        "Low correlation to equity beta",
        ),
        traps=(
        "Style drift into crowded trades",
        "Gated redemptions in crisis",
        "2/20 fees without alpha",
        "Survivorship bias in fund databases",
        ),
        catalysts=(
        "Volatility regime favoring strategy",
        "Dislocation creating event opportunities",
        "Redemption cycle clearing weak managers",
        ),
        fate_hook="Hedge-fund equity holdings overlap analysis via `analytics/industry_comovement.py` 13F clusters.",
        related=(
        "pe_asset",
        "quant_analysis",
        "long_short",
        ),
        further_reading=(
        "Jack Schwager — Market Wizards series",
        ),
    )
)

register(
    DeepChapter(
        topic_id="collectibles_asset",
        title="Collectibles",
        family="asset_class",
        philosophy="""
Collectibles store value in physical rarity — art, coins, memorabilia — without earnings yield. Markets are opaque, illiquid, and taste-driven; authentication and provenance are everything.
""".strip(),
        how_it_works="""
Auction houses and private dealers set prices; indices (MEI Michel, PWCC) track segments. Storage, insurance, and transaction costs (20%+ round-trip) erode returns. Passion assets can outperform but lack cash flow for valuation anchors.
""".strip(),
        formulas=(
            _F(
                "Total cost of ownership",
                r"TCO = P + Insurance + Storage + Fees",
                "Purchase plus ongoing carry costs.",
            ),
            _F(
                "Holding period return",
                r"R = \frac{P_{sale} - TCO_{buy}}{TCO_{buy}}",
                "Net after all transaction and carry costs.",
            ),
        ),
        screens=(
        "Expert authentication obtained",
        "Provenance documented",
        "Insurance at replacement value",
        "Liquidity plan (auction calendar)",
        ),
        traps=(
        "Forgery and restoration fraud",
        "Illiquid market forcing fire-sale",
        "Fad categories (Beanie Babies)",
        "Overpaying at auction fever peak",
        ),
        catalysts=(
        "Celebrity association boosting category",
        "Museum exhibition increasing demand",
        "Generational wealth transfer selling",
        "Index inclusion legitimizing segment",
        ),
        fate_hook="No direct FATE pipeline; luxury goods sector in `analytics/industry_taxonomy.py` is nearest public-market proxy.",
        related=(
        "art",
        "luxury_goods",
        "pe_asset",
        ),
        further_reading=(
        "Deloitte — Art & Finance Report",
        ),
    )
)

register(
    DeepChapter(
        topic_id="art",
        title="Art",
        family="asset_class",
        philosophy="""
Art combines aesthetic enjoyment with potential capital appreciation on masterworks — transaction costs, insurance, and provenance research are material. Contemporary art is fashion-sensitive; Old Masters are supply-constrained.
""".strip(),
        how_it_works="""
Primary market (galleries) vs secondary (auctions). Blue-chip artists (Picasso, Basquiat) have deepest liquidity. Fractional platforms democratize access but add layer fees. Art lending uses pieces as collateral at LTV ~50%.
""".strip(),
        formulas=(
            _F(
                "Hammer price total",
                r"Total = Hammer + Buyer\'s\ premium\ (\sim 25\%)",
                "All-in acquisition cost above hammer.",
            ),
            _F(
                "Art lending LTV",
                r"LTV = \frac{Loan}{Appraised\ value} \leq 0.50",
                "Conservative leverage on illiquid collateral.",
            ),
        ),
        screens=(
        "Catalogue raisonné confirms authenticity",
        "Condition report reviewed",
        "Comparable auction results researched",
        "Storage climate-controlled",
        ),
        traps=(
        "Attribution disputes post-purchase",
        "Contemporary fad without staying power",
        "Undisclosed restoration",
        "Overconcentration in single artist",
        ),
        catalysts=(
        "Major retrospective at MoMA/Tate",
        "Artist death supply freeze",
        "Asian collector demand surge",
        "Fractional platform liquidity event",
        ),
        fate_hook="Luxury conglomerates (LVMH-adjacent) in consumer discretionary via `analytics/industry_taxonomy.py`.",
        related=(
        "collectibles_asset",
        "luxury_goods",
        "pe_asset",
        ),
        further_reading=(
        "Thierry Ehrmann — Artprice indices",
        "McAndrew — The Art Market",
        ),
    )
)

register(
    DeepChapter(
        topic_id="technology",
        title="Technology",
        family="sector",
        philosophy="""
Technology is the economy's productivity engine — software, hardware, and services enabling digital transformation. It leads long bull markets but faces rapid obsolescence, regulatory scrutiny, and multiple compression when rates rise.
""".strip(),
        how_it_works="""
Sector structure spans semiconductors (cyclical capex), software (recurring revenue, high margins), cloud (scale economies), and emerging AI/robotics. Analyze via revenue growth, gross margin trajectory, R&D intensity, and customer concentration. Valuation ranges from utility-like cloud to option-like early AI.
""".strip(),
        formulas=(
            _F(
                "Rule of 40",
                r"R40 = g_{rev} + \text{FCF margin}\%",
                "SaaS health metric: growth plus profitability.",
            ),
            _F(
                "EV/Sales",
                r"EV/S = \frac{Enterprise\ Value}{Revenue}",
                "Common for pre-profit tech.",
            ),
        ),
        screens=(),
        traps=(),
        catalysts=(),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "software",
        "semiconductors",
        "ai",
        "cloud",
        ),
        further_reading=(
        "McKinsey — Technology Trends Outlook",
        ),
    )
)

register(
    DeepChapter(
        topic_id="software",
        title="Software",
        family="sector",
        philosophy="""
Software delivers digital capability at near-zero marginal cost — the highest-margin segment in technology when retention is strong.
""".strip(),
        how_it_works="""
Business models: perpetual license (legacy), subscription/SaaS (recurring), usage-based (consumption). Key metrics: ARR, net revenue retention (NRR), CAC payback, Rule of 40. Switching costs and ecosystem lock-in create moats.
""".strip(),
        formulas=(
            _F(
                "NRR",
                r"NRR = \frac{ARR_{start} + expansion - churn}{ARR_{start}}",
                "Net revenue retention; >120% is elite.",
            ),
        ),
        screens=(),
        traps=(),
        catalysts=(),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "cloud",
        "cybersecurity",
        "saas",
        "ai",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="hardware",
        title="Hardware",
        family="sector",
        philosophy="""
Hardware equity investors must separate secular industry structure from cyclical noise.
Barriers to entry, switching costs, and capital intensity determine whether returns mean-revert
or compound. Position size against regulatory and technological disruption specific to this leaf,
not the broad GICS parent alone.
""".strip(),
        how_it_works="""
Underwrite pricing power, volume growth, and cost inflation pass-through for hardware.
Compare ROIC vs WACC over a full cycle; prefer firms that earn excess returns with conservative
leverage. Valuation: use sector-native multiples (P/E, EV/EBITDA, EV/Sales, FCF yield) versus
5–10 year medians and closest peers. Track leading indicators (orders, utilization, inventories,
same-store sales) before trailing EPS.
""".strip(),
        formulas=(
            _F(
                "ROIC spread",
                r"Spread = ROIC - WACC",
                "Economic profit signal for the leaf.",
            ),
            _F(
                "Peer relative",
                r"Z = \\frac{Multiple - Peer\\ median}{Peer\\ StDev}",
                "Rich/cheap vs comps.",
            ),
        ),
        screens=(
        "ROIC above WACC for Hardware peer set",
        "Revenue growth ≥ sub-industry median",
        "Net debt/EBITDA appropriate for cycle",
        "Valuation ≤ 5y sector median unless growth justifies premium",
        ),
        traps=(
        "Cyclical peak earnings treated as permanent in hardware",
        "Customer or input concentration ignored",
        "Accounting distortions (one-time gains) in headline multiples",
        ),
        catalysts=(
        "Industry capacity discipline / consolidation",
        "Regulatory or standard-change unlocking demand",
        "Cost deflation expanding margins",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "semiconductors",
        "consumer_electronics",
        "data_centers",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="semiconductors",
        title="Semiconductors",
        family="sector",
        philosophy="""
Semiconductors power every electronic device — the most capital-intensive, cyclical segment in technology with boom-bust inventory cycles.
""".strip(),
        how_it_works="""
Value chain: design (fabless), manufacturing (foundries), equipment (ASML, AMAT). Analyze node leadership, utilization rates, and inventory corrections. AI accelerators (GPU, TPU) reshaping demand mix.
""".strip(),
        formulas=(
            _F(
                "Book-to-bill",
                r"B/B = \frac{Orders}{Billings}",
                ">1 signals rising demand.",
            ),
        ),
        screens=(),
        traps=(),
        catalysts=(),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "ai",
        "data_centers",
        "hardware",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="ai",
        title="Artificial Intelligence",
        family="sector",
        philosophy="""
Artificial Intelligence equity investors must separate secular industry structure from cyclical noise.
Barriers to entry, switching costs, and capital intensity determine whether returns mean-revert
or compound. Position size against regulatory and technological disruption specific to this leaf,
not the broad GICS parent alone.
""".strip(),
        how_it_works="""
Underwrite pricing power, volume growth, and cost inflation pass-through for artificial intelligence.
Compare ROIC vs WACC over a full cycle; prefer firms that earn excess returns with conservative
leverage. Valuation: use sector-native multiples (P/E, EV/EBITDA, EV/Sales, FCF yield) versus
5–10 year medians and closest peers. Track leading indicators (orders, utilization, inventories,
same-store sales) before trailing EPS.
""".strip(),
        formulas=(
            _F(
                "ROIC spread",
                r"Spread = ROIC - WACC",
                "Economic profit signal for the leaf.",
            ),
            _F(
                "Peer relative",
                r"Z = \\frac{Multiple - Peer\\ median}{Peer\\ StDev}",
                "Rich/cheap vs comps.",
            ),
        ),
        screens=(
        "ROIC above WACC for Artificial Intelligence peer set",
        "Revenue growth ≥ sub-industry median",
        "Net debt/EBITDA appropriate for cycle",
        "Valuation ≤ 5y sector median unless growth justifies premium",
        ),
        traps=(
        "Cyclical peak earnings treated as permanent in artificial intelligence",
        "Customer or input concentration ignored",
        "Accounting distortions (one-time gains) in headline multiples",
        ),
        catalysts=(
        "Industry capacity discipline / consolidation",
        "Regulatory or standard-change unlocking demand",
        "Cost deflation expanding margins",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "semiconductors",
        "cloud",
        "software",
        "data_centers",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="robotics",
        title="Robotics",
        family="sector",
        philosophy="""
Robotics equity investors must separate secular industry structure from cyclical noise.
Barriers to entry, switching costs, and capital intensity determine whether returns mean-revert
or compound. Position size against regulatory and technological disruption specific to this leaf,
not the broad GICS parent alone.
""".strip(),
        how_it_works="""
Underwrite pricing power, volume growth, and cost inflation pass-through for robotics.
Compare ROIC vs WACC over a full cycle; prefer firms that earn excess returns with conservative
leverage. Valuation: use sector-native multiples (P/E, EV/EBITDA, EV/Sales, FCF yield) versus
5–10 year medians and closest peers. Track leading indicators (orders, utilization, inventories,
same-store sales) before trailing EPS.
""".strip(),
        formulas=(
            _F(
                "ROIC spread",
                r"Spread = ROIC - WACC",
                "Economic profit signal for the leaf.",
            ),
            _F(
                "Peer relative",
                r"Z = \\frac{Multiple - Peer\\ median}{Peer\\ StDev}",
                "Rich/cheap vs comps.",
            ),
        ),
        screens=(
        "ROIC above WACC for Robotics peer set",
        "Revenue growth ≥ sub-industry median",
        "Net debt/EBITDA appropriate for cycle",
        "Valuation ≤ 5y sector median unless growth justifies premium",
        ),
        traps=(
        "Cyclical peak earnings treated as permanent in robotics",
        "Customer or input concentration ignored",
        "Accounting distortions (one-time gains) in headline multiples",
        ),
        catalysts=(
        "Industry capacity discipline / consolidation",
        "Regulatory or standard-change unlocking demand",
        "Cost deflation expanding margins",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "ai",
        "industrials",
        "manufacturing",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="cloud",
        title="Cloud Computing",
        family="sector",
        philosophy="""
Cloud computing delivers compute, storage, and platforms on demand — shifting enterprise capex to opex.
""".strip(),
        how_it_works="""
Hyperscalers (AWS, Azure, GCP) dominate IaaS; SaaS sits on top. Analyze revenue growth, operating margin expansion at scale, and customer workload migration pace.
""".strip(),
        formulas=(
            _F(
                "Cloud revenue growth",
                r"g = \frac{Rev_t - Rev_{t-1}}{Rev_{t-1}}",
                "Hyperscaler growth deceleration signals maturation.",
            ),
        ),
        screens=(),
        traps=(),
        catalysts=(),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "software",
        "data_centers",
        "cybersecurity",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="cybersecurity",
        title="Cybersecurity",
        family="sector",
        philosophy="""
Cybersecurity equity investors must separate secular industry structure from cyclical noise.
Barriers to entry, switching costs, and capital intensity determine whether returns mean-revert
or compound. Position size against regulatory and technological disruption specific to this leaf,
not the broad GICS parent alone.
""".strip(),
        how_it_works="""
Underwrite pricing power, volume growth, and cost inflation pass-through for cybersecurity.
Compare ROIC vs WACC over a full cycle; prefer firms that earn excess returns with conservative
leverage. Valuation: use sector-native multiples (P/E, EV/EBITDA, EV/Sales, FCF yield) versus
5–10 year medians and closest peers. Track leading indicators (orders, utilization, inventories,
same-store sales) before trailing EPS.
""".strip(),
        formulas=(
            _F(
                "ROIC spread",
                r"Spread = ROIC - WACC",
                "Economic profit signal for the leaf.",
            ),
            _F(
                "Peer relative",
                r"Z = \\frac{Multiple - Peer\\ median}{Peer\\ StDev}",
                "Rich/cheap vs comps.",
            ),
        ),
        screens=(
        "ROIC above WACC for Cybersecurity peer set",
        "Revenue growth ≥ sub-industry median",
        "Net debt/EBITDA appropriate for cycle",
        "Valuation ≤ 5y sector median unless growth justifies premium",
        ),
        traps=(
        "Cyclical peak earnings treated as permanent in cybersecurity",
        "Customer or input concentration ignored",
        "Accounting distortions (one-time gains) in headline multiples",
        ),
        catalysts=(
        "Industry capacity discipline / consolidation",
        "Regulatory or standard-change unlocking demand",
        "Cost deflation expanding margins",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "cloud",
        "software",
        "technology",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="consumer_electronics",
        title="Consumer Electronics",
        family="sector",
        philosophy="""
Consumer Electronics equity investors must separate secular industry structure from cyclical noise.
Barriers to entry, switching costs, and capital intensity determine whether returns mean-revert
or compound. Position size against regulatory and technological disruption specific to this leaf,
not the broad GICS parent alone.
""".strip(),
        how_it_works="""
Underwrite pricing power, volume growth, and cost inflation pass-through for consumer electronics.
Compare ROIC vs WACC over a full cycle; prefer firms that earn excess returns with conservative
leverage. Valuation: use sector-native multiples (P/E, EV/EBITDA, EV/Sales, FCF yield) versus
5–10 year medians and closest peers. Track leading indicators (orders, utilization, inventories,
same-store sales) before trailing EPS.
""".strip(),
        formulas=(
            _F(
                "ROIC spread",
                r"Spread = ROIC - WACC",
                "Economic profit signal for the leaf.",
            ),
            _F(
                "Peer relative",
                r"Z = \\frac{Multiple - Peer\\ median}{Peer\\ StDev}",
                "Rich/cheap vs comps.",
            ),
        ),
        screens=(
        "ROIC above WACC for Consumer Electronics peer set",
        "Revenue growth ≥ sub-industry median",
        "Net debt/EBITDA appropriate for cycle",
        "Valuation ≤ 5y sector median unless growth justifies premium",
        ),
        traps=(
        "Cyclical peak earnings treated as permanent in consumer electronics",
        "Customer or input concentration ignored",
        "Accounting distortions (one-time gains) in headline multiples",
        ),
        catalysts=(
        "Industry capacity discipline / consolidation",
        "Regulatory or standard-change unlocking demand",
        "Cost deflation expanding margins",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "hardware",
        "semiconductors",
        "technology",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="data_centers",
        title="Data Centers",
        family="sector",
        philosophy="""
Data Centers equity investors must separate secular industry structure from cyclical noise.
Barriers to entry, switching costs, and capital intensity determine whether returns mean-revert
or compound. Position size against regulatory and technological disruption specific to this leaf,
not the broad GICS parent alone.
""".strip(),
        how_it_works="""
Underwrite pricing power, volume growth, and cost inflation pass-through for data centers.
Compare ROIC vs WACC over a full cycle; prefer firms that earn excess returns with conservative
leverage. Valuation: use sector-native multiples (P/E, EV/EBITDA, EV/Sales, FCF yield) versus
5–10 year medians and closest peers. Track leading indicators (orders, utilization, inventories,
same-store sales) before trailing EPS.
""".strip(),
        formulas=(
            _F(
                "ROIC spread",
                r"Spread = ROIC - WACC",
                "Economic profit signal for the leaf.",
            ),
            _F(
                "Peer relative",
                r"Z = \\frac{Multiple - Peer\\ median}{Peer\\ StDev}",
                "Rich/cheap vs comps.",
            ),
        ),
        screens=(
        "ROIC above WACC for Data Centers peer set",
        "Revenue growth ≥ sub-industry median",
        "Net debt/EBITDA appropriate for cycle",
        "Valuation ≤ 5y sector median unless growth justifies premium",
        ),
        traps=(
        "Cyclical peak earnings treated as permanent in data centers",
        "Customer or input concentration ignored",
        "Accounting distortions (one-time gains) in headline multiples",
        ),
        catalysts=(
        "Industry capacity discipline / consolidation",
        "Regulatory or standard-change unlocking demand",
        "Cost deflation expanding margins",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "cloud",
        "reit_datacenter",
        "utilities",
        "ai",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="quantum",
        title="Quantum Computing",
        family="sector",
        philosophy="""
Quantum Computing equity investors must separate secular industry structure from cyclical noise.
Barriers to entry, switching costs, and capital intensity determine whether returns mean-revert
or compound. Position size against regulatory and technological disruption specific to this leaf,
not the broad GICS parent alone.
""".strip(),
        how_it_works="""
Underwrite pricing power, volume growth, and cost inflation pass-through for quantum computing.
Compare ROIC vs WACC over a full cycle; prefer firms that earn excess returns with conservative
leverage. Valuation: use sector-native multiples (P/E, EV/EBITDA, EV/Sales, FCF yield) versus
5–10 year medians and closest peers. Track leading indicators (orders, utilization, inventories,
same-store sales) before trailing EPS.
""".strip(),
        formulas=(
            _F(
                "ROIC spread",
                r"Spread = ROIC - WACC",
                "Economic profit signal for the leaf.",
            ),
            _F(
                "Peer relative",
                r"Z = \\frac{Multiple - Peer\\ median}{Peer\\ StDev}",
                "Rich/cheap vs comps.",
            ),
        ),
        screens=(
        "ROIC above WACC for Quantum Computing peer set",
        "Revenue growth ≥ sub-industry median",
        "Net debt/EBITDA appropriate for cycle",
        "Valuation ≤ 5y sector median unless growth justifies premium",
        ),
        traps=(
        "Cyclical peak earnings treated as permanent in quantum computing",
        "Customer or input concentration ignored",
        "Accounting distortions (one-time gains) in headline multiples",
        ),
        catalysts=(
        "Industry capacity discipline / consolidation",
        "Regulatory or standard-change unlocking demand",
        "Cost deflation expanding margins",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "semiconductors",
        "technology",
        "ai",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="communication",
        title="Communication Services",
        family="sector",
        philosophy="""
Communication Services equity investors must separate secular industry structure from cyclical noise.
Barriers to entry, switching costs, and capital intensity determine whether returns mean-revert
or compound. Position size against regulatory and technological disruption specific to this leaf,
not the broad GICS parent alone.
""".strip(),
        how_it_works="""
Underwrite pricing power, volume growth, and cost inflation pass-through for communication services.
Compare ROIC vs WACC over a full cycle; prefer firms that earn excess returns with conservative
leverage. Valuation: use sector-native multiples (P/E, EV/EBITDA, EV/Sales, FCF yield) versus
5–10 year medians and closest peers. Track leading indicators (orders, utilization, inventories,
same-store sales) before trailing EPS.
""".strip(),
        formulas=(
            _F(
                "ROIC spread",
                r"Spread = ROIC - WACC",
                "Economic profit signal for the leaf.",
            ),
            _F(
                "Peer relative",
                r"Z = \\frac{Multiple - Peer\\ median}{Peer\\ StDev}",
                "Rich/cheap vs comps.",
            ),
        ),
        screens=(
        "ROIC above WACC for Communication Services peer set",
        "Revenue growth ≥ sub-industry median",
        "Net debt/EBITDA appropriate for cycle",
        "Valuation ≤ 5y sector median unless growth justifies premium",
        ),
        traps=(
        "Cyclical peak earnings treated as permanent in communication services",
        "Customer or input concentration ignored",
        "Accounting distortions (one-time gains) in headline multiples",
        ),
        catalysts=(
        "Industry capacity discipline / consolidation",
        "Regulatory or standard-change unlocking demand",
        "Cost deflation expanding margins",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "internet_services",
        "streaming",
        "telecommunications",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="healthcare",
        title="Healthcare",
        family="sector",
        philosophy="""
Healthcare equity investors must separate secular industry structure from cyclical noise.
Barriers to entry, switching costs, and capital intensity determine whether returns mean-revert
or compound. Position size against regulatory and technological disruption specific to this leaf,
not the broad GICS parent alone.
""".strip(),
        how_it_works="""
Underwrite pricing power, volume growth, and cost inflation pass-through for healthcare.
Compare ROIC vs WACC over a full cycle; prefer firms that earn excess returns with conservative
leverage. Valuation: use sector-native multiples (P/E, EV/EBITDA, EV/Sales, FCF yield) versus
5–10 year medians and closest peers. Track leading indicators (orders, utilization, inventories,
same-store sales) before trailing EPS.
""".strip(),
        formulas=(
            _F(
                "ROIC spread",
                r"Spread = ROIC - WACC",
                "Economic profit signal for the leaf.",
            ),
            _F(
                "Peer relative",
                r"Z = \\frac{Multiple - Peer\\ median}{Peer\\ StDev}",
                "Rich/cheap vs comps.",
            ),
        ),
        screens=(
        "ROIC above WACC for Healthcare peer set",
        "Revenue growth ≥ sub-industry median",
        "Net debt/EBITDA appropriate for cycle",
        "Valuation ≤ 5y sector median unless growth justifies premium",
        ),
        traps=(
        "Cyclical peak earnings treated as permanent in healthcare",
        "Customer or input concentration ignored",
        "Accounting distortions (one-time gains) in headline multiples",
        ),
        catalysts=(
        "Industry capacity discipline / consolidation",
        "Regulatory or standard-change unlocking demand",
        "Cost deflation expanding margins",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "pharmaceuticals",
        "biotechnology",
        "medical_devices",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="financials",
        title="Financials",
        family="sector",
        philosophy="""
Financials equity investors must separate secular industry structure from cyclical noise.
Barriers to entry, switching costs, and capital intensity determine whether returns mean-revert
or compound. Position size against regulatory and technological disruption specific to this leaf,
not the broad GICS parent alone.
""".strip(),
        how_it_works="""
Underwrite pricing power, volume growth, and cost inflation pass-through for financials.
Compare ROIC vs WACC over a full cycle; prefer firms that earn excess returns with conservative
leverage. Valuation: use sector-native multiples (P/E, EV/EBITDA, EV/Sales, FCF yield) versus
5–10 year medians and closest peers. Track leading indicators (orders, utilization, inventories,
same-store sales) before trailing EPS.
""".strip(),
        formulas=(
            _F(
                "ROIC spread",
                r"Spread = ROIC - WACC",
                "Economic profit signal for the leaf.",
            ),
            _F(
                "Peer relative",
                r"Z = \\frac{Multiple - Peer\\ median}{Peer\\ StDev}",
                "Rich/cheap vs comps.",
            ),
        ),
        screens=(
        "ROIC above WACC for Financials peer set",
        "Revenue growth ≥ sub-industry median",
        "Net debt/EBITDA appropriate for cycle",
        "Valuation ≤ 5y sector median unless growth justifies premium",
        ),
        traps=(
        "Cyclical peak earnings treated as permanent in financials",
        "Customer or input concentration ignored",
        "Accounting distortions (one-time gains) in headline multiples",
        ),
        catalysts=(
        "Industry capacity discipline / consolidation",
        "Regulatory or standard-change unlocking demand",
        "Cost deflation expanding margins",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "banks",
        "insurance",
        "asset_management",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="consumer_discretionary",
        title="Consumer Discretionary",
        family="sector",
        philosophy="""
Consumer Discretionary equity investors must separate secular industry structure from cyclical noise.
Barriers to entry, switching costs, and capital intensity determine whether returns mean-revert
or compound. Position size against regulatory and technological disruption specific to this leaf,
not the broad GICS parent alone.
""".strip(),
        how_it_works="""
Underwrite pricing power, volume growth, and cost inflation pass-through for consumer discretionary.
Compare ROIC vs WACC over a full cycle; prefer firms that earn excess returns with conservative
leverage. Valuation: use sector-native multiples (P/E, EV/EBITDA, EV/Sales, FCF yield) versus
5–10 year medians and closest peers. Track leading indicators (orders, utilization, inventories,
same-store sales) before trailing EPS.
""".strip(),
        formulas=(
            _F(
                "ROIC spread",
                r"Spread = ROIC - WACC",
                "Economic profit signal for the leaf.",
            ),
            _F(
                "Peer relative",
                r"Z = \\frac{Multiple - Peer\\ median}{Peer\\ StDev}",
                "Rich/cheap vs comps.",
            ),
        ),
        screens=(
        "ROIC above WACC for Consumer Discretionary peer set",
        "Revenue growth ≥ sub-industry median",
        "Net debt/EBITDA appropriate for cycle",
        "Valuation ≤ 5y sector median unless growth justifies premium",
        ),
        traps=(
        "Cyclical peak earnings treated as permanent in consumer discretionary",
        "Customer or input concentration ignored",
        "Accounting distortions (one-time gains) in headline multiples",
        ),
        catalysts=(
        "Industry capacity discipline / consolidation",
        "Regulatory or standard-change unlocking demand",
        "Cost deflation expanding margins",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "retail",
        "automobiles",
        "restaurants",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="consumer_staples",
        title="Consumer Staples",
        family="sector",
        philosophy="""
Consumer Staples equity investors must separate secular industry structure from cyclical noise.
Barriers to entry, switching costs, and capital intensity determine whether returns mean-revert
or compound. Position size against regulatory and technological disruption specific to this leaf,
not the broad GICS parent alone.
""".strip(),
        how_it_works="""
Underwrite pricing power, volume growth, and cost inflation pass-through for consumer staples.
Compare ROIC vs WACC over a full cycle; prefer firms that earn excess returns with conservative
leverage. Valuation: use sector-native multiples (P/E, EV/EBITDA, EV/Sales, FCF yield) versus
5–10 year medians and closest peers. Track leading indicators (orders, utilization, inventories,
same-store sales) before trailing EPS.
""".strip(),
        formulas=(
            _F(
                "ROIC spread",
                r"Spread = ROIC - WACC",
                "Economic profit signal for the leaf.",
            ),
            _F(
                "Peer relative",
                r"Z = \\frac{Multiple - Peer\\ median}{Peer\\ StDev}",
                "Rich/cheap vs comps.",
            ),
        ),
        screens=(
        "ROIC above WACC for Consumer Staples peer set",
        "Revenue growth ≥ sub-industry median",
        "Net debt/EBITDA appropriate for cycle",
        "Valuation ≤ 5y sector median unless growth justifies premium",
        ),
        traps=(
        "Cyclical peak earnings treated as permanent in consumer staples",
        "Customer or input concentration ignored",
        "Accounting distortions (one-time gains) in headline multiples",
        ),
        catalysts=(
        "Industry capacity discipline / consolidation",
        "Regulatory or standard-change unlocking demand",
        "Cost deflation expanding margins",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "food_manufacturers",
        "beverage_companies",
        "household_products",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="industrials",
        title="Industrials",
        family="sector",
        philosophy="""
Industrials equity investors must separate secular industry structure from cyclical noise.
Barriers to entry, switching costs, and capital intensity determine whether returns mean-revert
or compound. Position size against regulatory and technological disruption specific to this leaf,
not the broad GICS parent alone.
""".strip(),
        how_it_works="""
Underwrite pricing power, volume growth, and cost inflation pass-through for industrials.
Compare ROIC vs WACC over a full cycle; prefer firms that earn excess returns with conservative
leverage. Valuation: use sector-native multiples (P/E, EV/EBITDA, EV/Sales, FCF yield) versus
5–10 year medians and closest peers. Track leading indicators (orders, utilization, inventories,
same-store sales) before trailing EPS.
""".strip(),
        formulas=(
            _F(
                "ROIC spread",
                r"Spread = ROIC - WACC",
                "Economic profit signal for the leaf.",
            ),
            _F(
                "Peer relative",
                r"Z = \\frac{Multiple - Peer\\ median}{Peer\\ StDev}",
                "Rich/cheap vs comps.",
            ),
        ),
        screens=(
        "ROIC above WACC for Industrials peer set",
        "Revenue growth ≥ sub-industry median",
        "Net debt/EBITDA appropriate for cycle",
        "Valuation ≤ 5y sector median unless growth justifies premium",
        ),
        traps=(
        "Cyclical peak earnings treated as permanent in industrials",
        "Customer or input concentration ignored",
        "Accounting distortions (one-time gains) in headline multiples",
        ),
        catalysts=(
        "Industry capacity discipline / consolidation",
        "Regulatory or standard-change unlocking demand",
        "Cost deflation expanding margins",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "aerospace",
        "defense",
        "machinery",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="energy",
        title="Energy",
        family="sector",
        philosophy="""
Energy equity investors must separate secular industry structure from cyclical noise.
Barriers to entry, switching costs, and capital intensity determine whether returns mean-revert
or compound. Position size against regulatory and technological disruption specific to this leaf,
not the broad GICS parent alone.
""".strip(),
        how_it_works="""
Underwrite pricing power, volume growth, and cost inflation pass-through for energy.
Compare ROIC vs WACC over a full cycle; prefer firms that earn excess returns with conservative
leverage. Valuation: use sector-native multiples (P/E, EV/EBITDA, EV/Sales, FCF yield) versus
5–10 year medians and closest peers. Track leading indicators (orders, utilization, inventories,
same-store sales) before trailing EPS.
""".strip(),
        formulas=(
            _F(
                "ROIC spread",
                r"Spread = ROIC - WACC",
                "Economic profit signal for the leaf.",
            ),
            _F(
                "Peer relative",
                r"Z = \\frac{Multiple - Peer\\ median}{Peer\\ StDev}",
                "Rich/cheap vs comps.",
            ),
        ),
        screens=(
        "ROIC above WACC for Energy peer set",
        "Revenue growth ≥ sub-industry median",
        "Net debt/EBITDA appropriate for cycle",
        "Valuation ≤ 5y sector median unless growth justifies premium",
        ),
        traps=(
        "Cyclical peak earnings treated as permanent in energy",
        "Customer or input concentration ignored",
        "Accounting distortions (one-time gains) in headline multiples",
        ),
        catalysts=(
        "Industry capacity discipline / consolidation",
        "Regulatory or standard-change unlocking demand",
        "Cost deflation expanding margins",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "oil_exploration",
        "solar",
        "pipelines",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="materials",
        title="Materials",
        family="sector",
        philosophy="""
Materials equity investors must separate secular industry structure from cyclical noise.
Barriers to entry, switching costs, and capital intensity determine whether returns mean-revert
or compound. Position size against regulatory and technological disruption specific to this leaf,
not the broad GICS parent alone.
""".strip(),
        how_it_works="""
Underwrite pricing power, volume growth, and cost inflation pass-through for materials.
Compare ROIC vs WACC over a full cycle; prefer firms that earn excess returns with conservative
leverage. Valuation: use sector-native multiples (P/E, EV/EBITDA, EV/Sales, FCF yield) versus
5–10 year medians and closest peers. Track leading indicators (orders, utilization, inventories,
same-store sales) before trailing EPS.
""".strip(),
        formulas=(
            _F(
                "ROIC spread",
                r"Spread = ROIC - WACC",
                "Economic profit signal for the leaf.",
            ),
            _F(
                "Peer relative",
                r"Z = \\frac{Multiple - Peer\\ median}{Peer\\ StDev}",
                "Rich/cheap vs comps.",
            ),
        ),
        screens=(
        "ROIC above WACC for Materials peer set",
        "Revenue growth ≥ sub-industry median",
        "Net debt/EBITDA appropriate for cycle",
        "Valuation ≤ 5y sector median unless growth justifies premium",
        ),
        traps=(
        "Cyclical peak earnings treated as permanent in materials",
        "Customer or input concentration ignored",
        "Accounting distortions (one-time gains) in headline multiples",
        ),
        catalysts=(
        "Industry capacity discipline / consolidation",
        "Regulatory or standard-change unlocking demand",
        "Cost deflation expanding margins",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "chemicals",
        "copper",
        "steel",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="utilities",
        title="Utilities",
        family="sector",
        philosophy="""
Utilities equity investors must separate secular industry structure from cyclical noise.
Barriers to entry, switching costs, and capital intensity determine whether returns mean-revert
or compound. Position size against regulatory and technological disruption specific to this leaf,
not the broad GICS parent alone.
""".strip(),
        how_it_works="""
Underwrite pricing power, volume growth, and cost inflation pass-through for utilities.
Compare ROIC vs WACC over a full cycle; prefer firms that earn excess returns with conservative
leverage. Valuation: use sector-native multiples (P/E, EV/EBITDA, EV/Sales, FCF yield) versus
5–10 year medians and closest peers. Track leading indicators (orders, utilization, inventories,
same-store sales) before trailing EPS.
""".strip(),
        formulas=(
            _F(
                "ROIC spread",
                r"Spread = ROIC - WACC",
                "Economic profit signal for the leaf.",
            ),
            _F(
                "Peer relative",
                r"Z = \\frac{Multiple - Peer\\ median}{Peer\\ StDev}",
                "Rich/cheap vs comps.",
            ),
        ),
        screens=(
        "ROIC above WACC for Utilities peer set",
        "Revenue growth ≥ sub-industry median",
        "Net debt/EBITDA appropriate for cycle",
        "Valuation ≤ 5y sector median unless growth justifies premium",
        ),
        traps=(
        "Cyclical peak earnings treated as permanent in utilities",
        "Customer or input concentration ignored",
        "Accounting distortions (one-time gains) in headline multiples",
        ),
        catalysts=(
        "Industry capacity discipline / consolidation",
        "Regulatory or standard-change unlocking demand",
        "Cost deflation expanding margins",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "electric_utilities",
        "renewable_utilities",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="real_estate_sector",
        title="Real Estate",
        family="sector",
        philosophy="""
Real Estate equity investors must separate secular industry structure from cyclical noise.
Barriers to entry, switching costs, and capital intensity determine whether returns mean-revert
or compound. Position size against regulatory and technological disruption specific to this leaf,
not the broad GICS parent alone.
""".strip(),
        how_it_works="""
Underwrite pricing power, volume growth, and cost inflation pass-through for real estate.
Compare ROIC vs WACC over a full cycle; prefer firms that earn excess returns with conservative
leverage. Valuation: use sector-native multiples (P/E, EV/EBITDA, EV/Sales, FCF yield) versus
5–10 year medians and closest peers. Track leading indicators (orders, utilization, inventories,
same-store sales) before trailing EPS.
""".strip(),
        formulas=(
            _F(
                "ROIC spread",
                r"Spread = ROIC - WACC",
                "Economic profit signal for the leaf.",
            ),
            _F(
                "Peer relative",
                r"Z = \\frac{Multiple - Peer\\ median}{Peer\\ StDev}",
                "Rich/cheap vs comps.",
            ),
        ),
        screens=(
        "ROIC above WACC for Real Estate peer set",
        "Revenue growth ≥ sub-industry median",
        "Net debt/EBITDA appropriate for cycle",
        "Valuation ≤ 5y sector median unless growth justifies premium",
        ),
        traps=(
        "Cyclical peak earnings treated as permanent in real estate",
        "Customer or input concentration ignored",
        "Accounting distortions (one-time gains) in headline multiples",
        ),
        catalysts=(
        "Industry capacity discipline / consolidation",
        "Regulatory or standard-change unlocking demand",
        "Cost deflation expanding margins",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "reit_industrial",
        "reit_residential",
        "reits",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="agriculture",
        title="Agriculture",
        family="sector",
        philosophy="""
Agriculture equity investors must separate secular industry structure from cyclical noise.
Barriers to entry, switching costs, and capital intensity determine whether returns mean-revert
or compound. Position size against regulatory and technological disruption specific to this leaf,
not the broad GICS parent alone.
""".strip(),
        how_it_works="""
Underwrite pricing power, volume growth, and cost inflation pass-through for agriculture.
Compare ROIC vs WACC over a full cycle; prefer firms that earn excess returns with conservative
leverage. Valuation: use sector-native multiples (P/E, EV/EBITDA, EV/Sales, FCF yield) versus
5–10 year medians and closest peers. Track leading indicators (orders, utilization, inventories,
same-store sales) before trailing EPS.
""".strip(),
        formulas=(
            _F(
                "ROIC spread",
                r"Spread = ROIC - WACC",
                "Economic profit signal for the leaf.",
            ),
            _F(
                "Peer relative",
                r"Z = \\frac{Multiple - Peer\\ median}{Peer\\ StDev}",
                "Rich/cheap vs comps.",
            ),
        ),
        screens=(
        "ROIC above WACC for Agriculture peer set",
        "Revenue growth ≥ sub-industry median",
        "Net debt/EBITDA appropriate for cycle",
        "Valuation ≤ 5y sector median unless growth justifies premium",
        ),
        traps=(
        "Cyclical peak earnings treated as permanent in agriculture",
        "Customer or input concentration ignored",
        "Accounting distortions (one-time gains) in headline multiples",
        ),
        catalysts=(
        "Industry capacity discipline / consolidation",
        "Regulatory or standard-change unlocking demand",
        "Cost deflation expanding margins",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "farming",
        "seeds",
        "fertilizers",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="transportation",
        title="Transportation",
        family="sector",
        philosophy="""
Transportation equity investors must separate secular industry structure from cyclical noise.
Barriers to entry, switching costs, and capital intensity determine whether returns mean-revert
or compound. Position size against regulatory and technological disruption specific to this leaf,
not the broad GICS parent alone.
""".strip(),
        how_it_works="""
Underwrite pricing power, volume growth, and cost inflation pass-through for transportation.
Compare ROIC vs WACC over a full cycle; prefer firms that earn excess returns with conservative
leverage. Valuation: use sector-native multiples (P/E, EV/EBITDA, EV/Sales, FCF yield) versus
5–10 year medians and closest peers. Track leading indicators (orders, utilization, inventories,
same-store sales) before trailing EPS.
""".strip(),
        formulas=(
            _F(
                "ROIC spread",
                r"Spread = ROIC - WACC",
                "Economic profit signal for the leaf.",
            ),
            _F(
                "Peer relative",
                r"Z = \\frac{Multiple - Peer\\ median}{Peer\\ StDev}",
                "Rich/cheap vs comps.",
            ),
        ),
        screens=(
        "ROIC above WACC for Transportation peer set",
        "Revenue growth ≥ sub-industry median",
        "Net debt/EBITDA appropriate for cycle",
        "Valuation ≤ 5y sector median unless growth justifies premium",
        ),
        traps=(
        "Cyclical peak earnings treated as permanent in transportation",
        "Customer or input concentration ignored",
        "Accounting distortions (one-time gains) in headline multiples",
        ),
        catalysts=(
        "Industry capacity discipline / consolidation",
        "Regulatory or standard-change unlocking demand",
        "Cost deflation expanding margins",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "airlines",
        "railroads",
        "shipping",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="space",
        title="Space",
        family="sector",
        philosophy="""
Space equity investors must separate secular industry structure from cyclical noise.
Barriers to entry, switching costs, and capital intensity determine whether returns mean-revert
or compound. Position size against regulatory and technological disruption specific to this leaf,
not the broad GICS parent alone.
""".strip(),
        how_it_works="""
Underwrite pricing power, volume growth, and cost inflation pass-through for space.
Compare ROIC vs WACC over a full cycle; prefer firms that earn excess returns with conservative
leverage. Valuation: use sector-native multiples (P/E, EV/EBITDA, EV/Sales, FCF yield) versus
5–10 year medians and closest peers. Track leading indicators (orders, utilization, inventories,
same-store sales) before trailing EPS.
""".strip(),
        formulas=(
            _F(
                "ROIC spread",
                r"Spread = ROIC - WACC",
                "Economic profit signal for the leaf.",
            ),
            _F(
                "Peer relative",
                r"Z = \\frac{Multiple - Peer\\ median}{Peer\\ StDev}",
                "Rich/cheap vs comps.",
            ),
        ),
        screens=(
        "ROIC above WACC for Space peer set",
        "Revenue growth ≥ sub-industry median",
        "Net debt/EBITDA appropriate for cycle",
        "Valuation ≤ 5y sector median unless growth justifies premium",
        ),
        traps=(
        "Cyclical peak earnings treated as permanent in space",
        "Customer or input concentration ignored",
        "Accounting distortions (one-time gains) in headline multiples",
        ),
        catalysts=(
        "Industry capacity discipline / consolidation",
        "Regulatory or standard-change unlocking demand",
        "Cost deflation expanding margins",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "satellites",
        "launch_providers",
        "defense",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="emerging_industries",
        title="Emerging Industries",
        family="sector",
        philosophy="""
Emerging Industries equity investors must separate secular industry structure from cyclical noise.
Barriers to entry, switching costs, and capital intensity determine whether returns mean-revert
or compound. Position size against regulatory and technological disruption specific to this leaf,
not the broad GICS parent alone.
""".strip(),
        how_it_works="""
Underwrite pricing power, volume growth, and cost inflation pass-through for emerging industries.
Compare ROIC vs WACC over a full cycle; prefer firms that earn excess returns with conservative
leverage. Valuation: use sector-native multiples (P/E, EV/EBITDA, EV/Sales, FCF yield) versus
5–10 year medians and closest peers. Track leading indicators (orders, utilization, inventories,
same-store sales) before trailing EPS.
""".strip(),
        formulas=(
            _F(
                "ROIC spread",
                r"Spread = ROIC - WACC",
                "Economic profit signal for the leaf.",
            ),
            _F(
                "Peer relative",
                r"Z = \\frac{Multiple - Peer\\ median}{Peer\\ StDev}",
                "Rich/cheap vs comps.",
            ),
        ),
        screens=(
        "ROIC above WACC for Emerging Industries peer set",
        "Revenue growth ≥ sub-industry median",
        "Net debt/EBITDA appropriate for cycle",
        "Valuation ≤ 5y sector median unless growth justifies premium",
        ),
        traps=(
        "Cyclical peak earnings treated as permanent in emerging industries",
        "Customer or input concentration ignored",
        "Accounting distortions (one-time gains) in headline multiples",
        ),
        catalysts=(
        "Industry capacity discipline / consolidation",
        "Regulatory or standard-change unlocking demand",
        "Cost deflation expanding margins",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "ev_manufacturers",
        "autonomous_vehicles",
        "carbon_capture",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="reit_office",
        title="Office REITs",
        family="sector",
        philosophy="""
Office REITs own workplace properties. Hybrid/remote work permanently reduced demand for
commodity Class B/C space while trophy CBDs with amenities and transit still clear. This is a
secular story first, rate story second: higher vacancies + concession packages destroy NOI even
when cap rates are stable. Invest only where tenant flight-to-quality and mark-to-market rents
still create AFFO path, or where liquidation/NAV discounts exceed lasting lease risk.
""".strip(),
        how_it_works="""
Underwrite occupancy trajectory, lease expiration wall (next 24–36 months), and average free
rent/TI packages. Trophy assets in gateway markets can still grow NOI via marking leases to
higher face rents; suburban multi-tenant boxes often face negative re-leasing spreads. Watch
debt maturity schedule — office collateral is hard to refinance in stressed CMBS markets.
Preferred metrics: same-store cash NOI, leased vs occupied (shadow vacancy), NAV vs share
price, and % of rents from investment-grade tenants.
""".strip(),
        formulas=(
            _F(
                "Cash NOI yield",
                r"Cash\\ NOI\\ yield = \\frac{Cash\\ NOI}{Asset\\ value}",
                "True cash yield after concessions.",
            ),
            _F(
                "Releasing spread",
                r"Spread = \\frac{New\\ rent - Expiring\\ rent}{Expiring\\ rent}",
                "Positive spread needed to grow NOI.",
            ),
        ),
        screens=(
        "Occupancy ≥85% with stabilizing trend",
        "Lease wall <20% of ABR next 12m",
        "Net debt/EBITDA ≤7x",
        "Share price ≤0.75× consensus NAV with clear lease-up path",
        ),
        traps=(
        "Calling a value trap 'cheap NAV' when rents keep resetting down",
        "Ignoring ground-lease or environmental liabilities",
        "Refi cliffs on floating-rate debt",
        ),
        catalysts=(
        "Return-to-office mandates + CBD leasing data",
        "Asset sales unlocking NAV",
        "Fed cuts easing refinance",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "real_estate_sector",
        "reits",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="reit_retail",
        title="Retail REITs",
        family="sector",
        philosophy="""
Retail REITs span grocery-anchored centers, power centers, and malls. E-commerce permanently
changed traffic patterns; winners own necessity retail with strong co-tenancy and losers own
fashion malls with weak anchors. Credit of the tenant roster matter as much as geography.
""".strip(),
        how_it_works="""
Segment by format. Grocery-anchored open-air centers have resilient traffic and shorter lease
structures that reprice faster. Class A malls with experiential mix and tourism can still compound;
Class B/C malls often become redevelopment optionality. Track sales PSF, occupancy cost ratios,
and anchor health. Capex for redevelopment is the hidden claim on FFO.
""".strip(),
        formulas=(
            _F(
                "Occupancy cost",
                r"OCR = \\frac{Rent+CAM}{Tenant\\ sales}",
                "Sustainable OCR typically mid-teens for soft goods.",
            ),
            _F(
                "FFO payout",
                r"Payout = \\frac{Dividends}{FFO}",
                "High payout + heavy remdev = dividend cut risk.",
            ),
        ),
        screens=(
        "Occupancy ≥93%",
        "Tenant sales growth positive",
        "Top-10 tenant concentration <25%",
        "Net debt/EBITDA ≤6x",
        ),
        traps=(
        "Anchor bankruptcy cascade",
        "Treating mall REITs as bond proxies",
        "Ignoring online penetration by category",
        ),
        catalysts=(
        "Retailer expansion cycles",
        "Mixed-use densification approvals",
        "Rate relief on floating debt",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "reit_retail",
        "retail",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="reit_residential",
        title="Residential REITs",
        family="sector",
        philosophy="""
Residential REITs (multifamily / SFR) monetize housing scarcity and demographic demand. Rent
growth is capped by affordability (rent-to-income) and local supply pipelines. Sunbelt supply
waves can crush rent growth even when national demand is fine — location is the strategy.
""".strip(),
        how_it_works="""
Focus on same-store revenue/NOI growth, turnover, and bad debt. Underwrite new deliveries in
each MSA vs absorption. Prefer Sunbelt names with staggered lease rolls when supply is peaking;
prefer coastal/supply-constrained when building costs stay high. SFR has different opex and HOA
complexity. Balance sheet: long fixed-rate debt is a moat in rising-rate tapes.
""".strip(),
        formulas=(
            _F(
                "Same-store NOI growth",
                r"SSNOI\\ \\Delta = \\frac{NOI_t - NOI_{t-1}}{NOI_{t-1}}",
                "Organic growth engine.",
            ),
            _F(
                "Rent-to-income",
                r"RTI = \\frac{Asking\\ rent}{Household\\ income}",
                "Affordability ceiling ~28–35%.",
            ),
        ),
        screens=(
        "SSNOI growth ≥ peer median",
        "Occupancy ≥94%",
        "Supply as % of stock <2% in core MSAs",
        "Investment-grade balance sheet",
        ),
        traps=(
        "Ignoring deliveries 12–18m forward",
        "Overpaying peak rent growth",
        "SFR weather/capex underestimation",
        ),
        catalysts=(
        "Supply trough after delivery wave",
        "Immigration/household formation",
        "Rate cuts supporting homebuyer vs renter mix",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "reit_residential",
        "real_estate_asset",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="reit_industrial",
        title="Industrial REITs",
        family="sector",
        philosophy="""
Industrial REITs own warehouses and logistics nodes. Secular e-commerce + inventory rebuild +
nearshoring drove historic rent spikes; the question now is mark-to-market leftover vs slowing
absorption. Best assets are last-mile infill and modern bulk with clear heights and power.
""".strip(),
        how_it_works="""
Cash flow comes from contractual rent + contractual escalators + releasing to market. Large
spread between in-place and market rents = multi-year NOI runway even if asking rents flatline.
Watch vacancy, new starts, and land values. Customer concentration (Amazon, 3PLs) and lease
duration matter. Development yields on cost vs cap rates decide if growth is accretive.
""".strip(),
        formulas=(
            _F(
                "Mark-to-market",
                r"MTM = \\frac{Market\\ rent - In\\!-\\!place\\ rent}{In\\!-\\!place\\ rent}",
                "Embedded NOI upside on rollover.",
            ),
            _F(
                "Development yield",
                r"Yield\\ on\\ cost = \\frac{Stabilized\\ NOI}{Total\\ project\\ cost}",
                "Must exceed going-in cap + risk.",
            ),
        ),
        screens=(
        "In-place vs market rent gap ≥15%",
        "Occupancy ≥96%",
        "Development pipeline ≤15% of GAV",
        "Net debt/EBITDA ≤5.5x",
        ),
        traps=(
        "Paying peak caps on muted MTM left",
        "Landbank with no entitlement path",
        "Power-constrained sites mislabeled modern",
        ),
        catalysts=(
        "Import rebound / inventory restock",
        "Onshoring manufacturing",
        "Cold-storage scarcity",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "reit_industrial",
        "logistics",
        "ecommerce",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="reit_healthcare",
        title="Healthcare REITs",
        family="sector",
        philosophy="""
Healthcare REITs lease to senior housing, medical office (MOB), hospitals, and life-science.
Demographics support long-term demand, but operator quality and reimbursement risk dominate
near-term cash flow. This is not a pure real-estate beta — it is tenant credit + clinical ops.
""".strip(),
        how_it_works="""
Senior housing: RevPOR, occupancy, labor costs. MOB: outpatient shift and health-system
sponsorship. Skilled nursing: Medicaid/Medicare mix — regulatory. Life science: lab demand
correlated to biotech funding cycles. Prefer diversified coverage with strong coverage
ratios and master leases where appropriate. Track EBITDAR coverage of rent.
""".strip(),
        formulas=(
            _F(
                "EBITDAR coverage",
                r"Coverage = \\frac{EBITDAR}{Cash\\ rent}",
                "Operator cushion above rent.",
            ),
            _F(
                "RevPOR",
                r"RevPOR = \\frac{Resident\\ revenue}{Occupied\\ units}",
                "Senior housing unit economics.",
            ),
        ),
        screens=(
        "Coverage ≥1.2x portfolio",
        "No single operator >15% ABR",
        "MOB occupancy ≥90%",
        "Investment-grade or well-covered SHOP",
        ),
        traps=(
        "Operator distress contagion",
        "Treating SHOP as NNN stability",
        "Biotech lab vacancy after funding winters",
        ),
        catalysts=(
        "Baby-boomer move-in wave",
        "Outpatient surgery migration",
        "Labor cost normalization",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "reit_healthcare",
        "healthcare",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="reit_datacenter",
        title="Data Center REITs",
        family="sector",
        philosophy="""
Data center REITs monetize power, cooling, and interconnection for cloud/AI. The scarce
resource is megawatts + latency adjacency, not just raised-floor SF. Hyperscaler leases drive
growth but create concentration and renegotiation risk.
""".strip(),
        how_it_works="""
Key KPIs: leased MW, interconnection revenue growth, churn, and power availability roadmaps.
Development is multi-year and capital intensive — watch funded pipeline and pre-leasing.
Valuation often on AFFO and EV/EBITDA with growth premium for AI demand. Jurisdiction power
policy and water cooling constraints are binding. Compare wholesale vs retail colocation mix.
""".strip(),
        formulas=(
            _F(
                "AFFO yield",
                r"AFFO\\ yield = \\frac{AFFO}{Price}",
                "Cash earnings yield.",
            ),
            _F(
                "MW leased growth",
                r"\\Delta MW = \\frac{MW_t - MW_{t-1}}{MW_{t-1}}",
                "Volume growth under AI cycle.",
            ),
        ),
        screens=(
        "Interconnection revenue growing faster than rent",
        "Pre-leased development ≥50%",
        "Hyperscaler concentration disclosed & tolerable",
        "Power delivery schedule credible",
        ),
        traps=(
        "Ignoring power queue delays",
        "AI hype without contracted capacity",
        "Capex intensity starving dividends",
        ),
        catalysts=(
        "New hyperscaler campus announcements",
        "Grid interconnection approvals",
        "Liquidity rebound in digital infra M&A",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "reit_datacenter",
        "data_centers",
        "cloud",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="reit_self_storage",
        title="Self-Storage REITs",
        family="sector",
        philosophy="""
Self-storage REITs rent flexible units with sticky, month-to-month demand. Business thrives on
life-events (move, divorce, death) more than GDP. New supply in hot MSAs is the enemy; branded
platforms with digital funnel and variable street rates compound better than mom-and-pop books.
""".strip(),
        how_it_works="""
Drive street rates and occupancy together — pushing rate into weakness kills move-ins. Watch
existing customer rate increases (ECRI) vs churn. REITs win on densify/acquire fragmented markets
and operating leverage from platforms. Seasonal patterns and student markets create cadence.
Debt is usually light vs other REITs; equity multiples sensitive to rate and supply prints.
""".strip(),
        formulas=(
            _F(
                "REVPAM",
                r"REVPAM = \\frac{Revenue}{Available\\ SF\\ (avg)}",
                "Same-store operating pulse.",
            ),
            _F(
                "Street vs in-place",
                r"Gap = Street\\ rate - In\\!-\\!place\\ rate",
                "Leading indicator of portfolio yields.",
            ),
        ),
        screens=(
        "Same-store occupancy ≥90%",
        "Supply deliveries disclosed MSA-by-MSA",
        "Platform opex ratio improving",
        "Net debt/EBITDA ≤5x",
        ),
        traps=(
        "National rollups into oversupplied Sunbelt MSAs",
        "Aggressive ECRI sparking churn spikes",
        "Ignoring property tax resets after reassessment",
        ),
        catalysts=(
        "Consolidation M&A",
        "Supply cliff after overbuild",
        "Storm-driven emergency demand",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "reit_self_storage",
        "real_estate_sector",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="reit_hotel",
        title="Hotel REITs",
        family="sector",
        philosophy="""
Hotel REITs own lodging with high operating leverage to ADR and occupancy. Near-term cash
flow is cyclical; brand and manager agreements determine fee drag. Leisure vs corporate vs
group mix sets the recovery path after shocks.
""".strip(),
        how_it_works="""
Read RevPAR, ADR, occupancy vs STR comps and booking windows. Extended-stay and select-service
often have better margins; luxury is prestige with higher opex/beta. Capex reserves (FFE)
are mandatory. Prefer ladders of unsecured debt and assets in constrained supply markets
(coastal/urban core). Soft brands and management contract flexibility matter on exit.
""".strip(),
        formulas=(
            _F(
                "RevPAR",
                r"RevPAR = ADR \\times Occupancy",
                "Top-line lodging productivity.",
            ),
            _F(
                "GOP margin",
                r"GOP\\ margin = \\frac{Gross\\ operating\\ profit}{Revenue}",
                "Property-level operating power.",
            ),
        ),
        screens=(
        "RevPAR index ≥100 vs comp set",
        "Net debt/EBITDA ≤4.5x at mid-cycle",
        "Group pace booking solid 6–12m out",
        "FFE reserve adequately funded",
        ),
        traps=(
        "Peak ADR multiples into recession",
        "Ignoring renovation downtime",
        "Brand-imposed PIP (property improvement) surprises",
        ),
        catalysts=(
        "International travel rebound",
        "Corporate group return",
        "Asset sales at hotel NAV premiums",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "reit_hotel",
        "hotels",
        "travel",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="reit_net_lease",
        title="Net Lease REITs",
        family="sector",
        philosophy="""
Net-lease REITs collect long-duration triple-net rents from credit tenants — bond-like cash
flows with residual real estate risk. Spreads vs corporate credit and residual value after
lease expiry decide equity IRRs. Sale-leaseback is the growth engine.
""".strip(),
        how_it_works="""
Portfolio KPIs: WALT, investment-grade % of ABR, unitary vs multi-tenant, and rent escalators
(fixed vs CPI). Underwrite unit-level four-wall coverage for retail tenants. Watch tenant
concentration (dollar stores, pharmacies, QSR). Cap-rate compression trades reverse hard when
credit spreads blow out. AFFO growth = acquisitions + escalators − asset sales.
""".strip(),
        formulas=(
            _F(
                "WALT",
                r"WALT = \\sum w_i \\times remaining\\ term_i",
                "Cash-flow duration.",
            ),
            _F(
                "Cap-rate spread",
                r"Spread = Cap\\ rate - Treasury\\ yield",
                "Risk premium vs risk-free.",
            ),
        ),
        screens=(
        "WALT ≥9 years",
        "IG tenants ≥40% ABR",
        "Top tenant <5% ABR",
        "Acquisition cap above cost of capital",
        ),
        traps=(
        "Chasing volume at thin spreads",
        "Single-tenant industrial with no alternative use",
        "Calling NNN risk-free",
        ),
        catalysts=(
        "Sale-leaseback waves from corporates",
        "Credit spread tightening",
        "Retailer expansion footprints",
        ),
        fate_hook="Sector classification and peer grouping in `analytics/industry_taxonomy.py`; return co-movement in `analytics/industry_comovement.py`.",
        related=(
        "reit_net_lease",
        "bonds",
        "reits",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="internet_services",
        title="Internet Services",
        family="sector",
        philosophy="""
Internet platforms and services delivering content, commerce, and cloud connectivity at scale. Equity investors in Internet Services must understand how communication tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to internet services. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Internet Services peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in internet services",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies internet_services tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "communication",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="social_media",
        title="Social Media",
        family="sector",
        philosophy="""
Social networks monetize attention via advertising and subscriptions amid engagement and regulation risk. Equity investors in Social Media must understand how communication tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to social media. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Social Media peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in social media",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies social_media tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "communication",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="telecommunications",
        title="Telecommunications",
        family="sector",
        philosophy="""
Wireless and wireline carriers provide essential connectivity with capital-heavy networks and regulatory overlays. Equity investors in Telecommunications must understand how communication tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to telecommunications. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Telecommunications peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in telecommunications",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies telecommunications tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "communication",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="streaming",
        title="Streaming",
        family="sector",
        philosophy="""
Streaming services compete for subscribers with content libraries and global distribution. Equity investors in Streaming must understand how communication tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to streaming. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Streaming peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in streaming",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies streaming tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "communication",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="gaming",
        title="Gaming",
        family="sector",
        philosophy="""
Video game publishers and platforms monetize playtime through titles, DLC, and live services. Equity investors in Gaming must understand how communication tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to gaming. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Gaming peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in gaming",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies gaming tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "communication",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="digital_advertising",
        title="Digital Advertising",
        family="sector",
        philosophy="""
Ad-tech and digital media capture marketing spend shifting from traditional channels. Equity investors in Digital Advertising must understand how communication tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to digital advertising. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Digital Advertising peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in digital advertising",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies digital_advertising tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "communication",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="pharmaceuticals",
        title="Pharmaceuticals",
        family="sector",
        philosophy="""
Large drug manufacturers develop and commercialize patented and generic medicines worldwide. Equity investors in Pharmaceuticals must understand how healthcare tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to pharmaceuticals. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(
            _F(
                "rNPV",
                r"rNPV = \sum \frac{P(success) \cdot CF}{(1+r)^t}",
                "Risk-adjusted pipeline valuation.",
            ),
        ),
        screens=(
        "Top-quartile ROIC vs Pharmaceuticals peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in pharmaceuticals",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies pharmaceuticals tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "healthcare",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="biotechnology",
        title="Biotechnology",
        family="sector",
        philosophy="""
Biotech firms develop novel therapies with binary clinical and regulatory outcomes. Equity investors in Biotechnology must understand how healthcare tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to biotechnology. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(
            _F(
                "rNPV",
                r"rNPV = \sum \frac{P(success) \cdot CF}{(1+r)^t}",
                "Risk-adjusted pipeline valuation.",
            ),
        ),
        screens=(
        "Top-quartile ROIC vs Biotechnology peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in biotechnology",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies biotechnology tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "healthcare",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="medical_devices",
        title="Medical Devices",
        family="sector",
        philosophy="""
Device makers sell implants, diagnostics tools, and equipment into hospitals and clinics. Equity investors in Medical Devices must understand how healthcare tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to medical devices. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Medical Devices peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in medical devices",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies medical_devices tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "healthcare",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="diagnostics",
        title="Diagnostics",
        family="sector",
        philosophy="""
Diagnostics companies enable disease detection through labs, kits, and imaging modalities. Equity investors in Diagnostics must understand how healthcare tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to diagnostics. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Diagnostics peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in diagnostics",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies diagnostics tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "healthcare",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="healthcare_services",
        title="Healthcare Services",
        family="sector",
        philosophy="""
Service providers deliver care coordination, outpatient services, and specialty treatment networks. Equity investors in Healthcare Services must understand how healthcare tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to healthcare services. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Healthcare Services peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in healthcare services",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies healthcare_services tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "healthcare",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="hospitals",
        title="Hospitals",
        family="sector",
        philosophy="""
Hospital operators earn from inpatient and outpatient care with labor and reimbursement intensity. Equity investors in Hospitals must understand how healthcare tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to hospitals. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Hospitals peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in hospitals",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies hospitals tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "healthcare",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="health_insurance",
        title="Health Insurance",
        family="sector",
        philosophy="""
Insurers underwrite medical risk and manage networks between patients, employers, and providers. Equity investors in Health Insurance must understand how healthcare tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to health insurance. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Health Insurance peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in health insurance",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies health_insurance tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "healthcare",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="gene_editing",
        title="Gene Editing",
        family="sector",
        philosophy="""
Gene-editing platforms pursue durable cures via CRISPR and related molecular tools. Equity investors in Gene Editing must understand how healthcare tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to gene editing. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(
            _F(
                "rNPV",
                r"rNPV = \sum \frac{P(success) \cdot CF}{(1+r)^t}",
                "Risk-adjusted pipeline valuation.",
            ),
        ),
        screens=(
        "Top-quartile ROIC vs Gene Editing peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in gene editing",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies gene_editing tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "healthcare",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="drug_manufacturing",
        title="Drug Manufacturing",
        family="sector",
        philosophy="""
Contract and specialty manufacturers produce APIs and finished doses for branded and generic firms. Equity investors in Drug Manufacturing must understand how healthcare tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to drug manufacturing. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Drug Manufacturing peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in drug manufacturing",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies drug_manufacturing tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "healthcare",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="banks",
        title="Banks",
        family="sector",
        philosophy="""
Commercial banks take deposits and lend, earning net interest margin under capital regulation. Equity investors in Banks must understand how financials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to banks. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(
            _F(
                "Net interest margin",
                r"NIM = \frac{Interest\ income - Interest\ expense}{Avg\ earning\ assets}",
                "Core bank profitability driver.",
            ),
        ),
        screens=(
        "Top-quartile ROIC vs Banks peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in banks",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies banks tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "financials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="investment_banks",
        title="Investment Banks",
        family="sector",
        philosophy="""
Investment banks advise on M&A and underwrite securities amid deal-cycle volatility. Equity investors in Investment Banks must understand how financials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to investment banks. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(
            _F(
                "Net interest margin",
                r"NIM = \frac{Interest\ income - Interest\ expense}{Avg\ earning\ assets}",
                "Core bank profitability driver.",
            ),
        ),
        screens=(
        "Top-quartile ROIC vs Investment Banks peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in investment banks",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies investment_banks tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "financials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="asset_management",
        title="Asset Management",
        family="sector",
        philosophy="""
Asset managers earn fees on AUM across active and passive strategies. Equity investors in Asset Management must understand how financials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to asset management. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(
            _F(
                "Fee rate on AUM",
                r"Rev = AUM \times fee\ rate",
                "Revenue scales with assets and fee compression risk.",
            ),
        ),
        screens=(
        "Top-quartile ROIC vs Asset Management peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in asset management",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies asset_management tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "financials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="insurance",
        title="Insurance",
        family="sector",
        philosophy="""
Insurers collect premiums and invest float while managing underwriting and catastrophe risk. Equity investors in Insurance must understand how financials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to insurance. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Insurance peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in insurance",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies insurance tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "financials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="fintech",
        title="FinTech",
        family="sector",
        philosophy="""
FinTech disrupts payments, lending, and brokerage with software-led distribution. Equity investors in FinTech must understand how financials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to fintech. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs FinTech peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in fintech",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies fintech tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "financials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="credit_cards",
        title="Credit Cards",
        family="sector",
        philosophy="""
Card networks and issuers monetize transactions and revolving credit balances. Equity investors in Credit Cards must understand how financials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to credit cards. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Credit Cards peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in credit cards",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies credit_cards tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "financials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="exchanges",
        title="Exchanges",
        family="sector",
        philosophy="""
Exchanges and market infrastructure firms provide listing, matching, and data services. Equity investors in Exchanges must understand how financials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to exchanges. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Exchanges peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in exchanges",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies exchanges tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "financials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="mortgage_lenders",
        title="Mortgage Lenders",
        family="sector",
        philosophy="""
Mortgage originators and servicers are highly sensitive to rates and housing volumes. Equity investors in Mortgage Lenders must understand how financials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to mortgage lenders. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Mortgage Lenders peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in mortgage lenders",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies mortgage_lenders tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "financials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="sector_private_equity",
        title="Private Equity (Sector)",
        family="sector",
        philosophy="""
Listed PE sponsors and BDCs offer public access to buyout and credit strategies. Equity investors in Private Equity (Sector) must understand how financials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to private equity (sector). Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Private Equity (Sector) peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in private equity (sector)",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies sector_private_equity tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "financials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="sector_venture_capital",
        title="Venture Capital (Sector)",
        family="sector",
        philosophy="""
Public VC-related vehicles and growth equity platforms capture startup ecosystem exposure. Equity investors in Venture Capital (Sector) must understand how financials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to venture capital (sector). Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Venture Capital (Sector) peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in venture capital (sector)",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies sector_venture_capital tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "financials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="retail",
        title="Retail",
        family="sector",
        philosophy="""
Brick-and-mortar and omnichannel retailers sell discretionary goods with inventory and traffic risk. Equity investors in Retail must understand how consumer discretionary tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to retail. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Retail peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in retail",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies retail tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "consumer_discretionary",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="ecommerce",
        title="E-commerce",
        family="sector",
        philosophy="""
Online marketplaces and specialty e-tailers compete on selection, logistics, and price. Equity investors in E-commerce must understand how consumer discretionary tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to e-commerce. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs E-commerce peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in e-commerce",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies ecommerce tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "consumer_discretionary",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="luxury_goods",
        title="Luxury Goods",
        family="sector",
        philosophy="""
Luxury brands monetize exclusivity and aspirational demand across cycles and geographies. Equity investors in Luxury Goods must understand how consumer discretionary tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to luxury goods. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Luxury Goods peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in luxury goods",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies luxury_goods tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "consumer_discretionary",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="apparel",
        title="Apparel",
        family="sector",
        philosophy="""
Apparel makers and retailers face fashion cycles, sourcing costs, and promotional intensity. Equity investors in Apparel must understand how consumer discretionary tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to apparel. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Apparel peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in apparel",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies apparel tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "consumer_discretionary",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="restaurants",
        title="Restaurants",
        family="sector",
        philosophy="""
Restaurant chains leverage brand and unit economics with labor and commodity sensitivity. Equity investors in Restaurants must understand how consumer discretionary tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to restaurants. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Restaurants peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in restaurants",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies restaurants tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "consumer_discretionary",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="hotels",
        title="Hotels",
        family="sector",
        philosophy="""
Hotel operators and franchisors earn from occupancy and RevPAR tied to travel demand. Equity investors in Hotels must understand how consumer discretionary tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to hotels. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(
            _F(
                "RevPAR / RASM",
                r"RevPAR = \frac{Room\ revenue}{Available\ rooms}",
                "Revenue per available room; key lodging metric.",
            ),
        ),
        screens=(
        "Top-quartile ROIC vs Hotels peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in hotels",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies hotels tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "consumer_discretionary",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="travel",
        title="Travel",
        family="sector",
        philosophy="""
Online travel and leisure platforms connect consumers to trips and experiences. Equity investors in Travel must understand how consumer discretionary tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to travel. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Travel peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in travel",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies travel tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "consumer_discretionary",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="cruise_lines",
        title="Cruise Lines",
        family="sector",
        philosophy="""
Cruise operators run floating resorts with high operating leverage to bookings. Equity investors in Cruise Lines must understand how consumer discretionary tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to cruise lines. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(
            _F(
                "RevPAR / RASM",
                r"RevPAR = \frac{Room\ revenue}{Available\ rooms}",
                "Revenue per available room; key lodging metric.",
            ),
        ),
        screens=(
        "Top-quartile ROIC vs Cruise Lines peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in cruise lines",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies cruise_lines tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "consumer_discretionary",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="airlines",
        title="Airlines",
        family="sector",
        philosophy="""
Airlines move passengers with fuel, labor, and capacity discipline as key variables. Equity investors in Airlines must understand how consumer discretionary tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to airlines. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(
            _F(
                "RevPAR / RASM",
                r"RevPAR = \frac{Room\ revenue}{Available\ rooms}",
                "Revenue per available room; key lodging metric.",
            ),
        ),
        screens=(
        "Top-quartile ROIC vs Airlines peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in airlines",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies airlines tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "consumer_discretionary",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="automobiles",
        title="Automobiles",
        family="sector",
        philosophy="""
Auto OEMs produce vehicles with long product cycles and dealer networks. Equity investors in Automobiles must understand how consumer discretionary tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to automobiles. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Automobiles peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in automobiles",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies automobiles tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "consumer_discretionary",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="ev_manufacturers",
        title="EV Manufacturers",
        family="sector",
        philosophy="""
EV makers compete on range, software, and manufacturing scale in the electrification shift. Equity investors in EV Manufacturers must understand how consumer discretionary tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to ev manufacturers. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs EV Manufacturers peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in ev manufacturers",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies ev_manufacturers tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "consumer_discretionary",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="auto_parts",
        title="Auto Parts",
        family="sector",
        philosophy="""
Parts suppliers feed OEMs and aftermarket channels with cyclical auto production. Equity investors in Auto Parts must understand how consumer discretionary tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to auto parts. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Auto Parts peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in auto parts",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies auto_parts tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "consumer_discretionary",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="food_manufacturers",
        title="Food Manufacturers",
        family="sector",
        philosophy="""
Packaged food companies deliver steady demand with brand and commodity cost management. Equity investors in Food Manufacturers must understand how consumer staples tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to food manufacturers. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Food Manufacturers peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in food manufacturers",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies food_manufacturers tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "consumer_staples",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="beverage_companies",
        title="Beverage Companies",
        family="sector",
        philosophy="""
Beverage firms sell soft drinks, alcohol, and hydration brands with global distribution. Equity investors in Beverage Companies must understand how consumer staples tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to beverage companies. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Beverage Companies peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in beverage companies",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies beverage_companies tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "consumer_staples",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="household_products",
        title="Household Products",
        family="sector",
        philosophy="""
Household product makers sell cleaning and home goods with defensive cash flows. Equity investors in Household Products must understand how consumer staples tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to household products. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Household Products peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in household products",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies household_products tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "consumer_staples",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="personal_care",
        title="Personal Care",
        family="sector",
        philosophy="""
Personal care brands sell hygiene and beauty products with brand loyalty and pricing power. Equity investors in Personal Care must understand how consumer staples tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to personal care. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Personal Care peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in personal care",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies personal_care tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "consumer_staples",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="tobacco",
        title="Tobacco",
        family="sector",
        philosophy="""
Tobacco companies generate high free cash flow amid regulatory and volume headwinds. Equity investors in Tobacco must understand how consumer staples tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to tobacco. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Tobacco peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in tobacco",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies tobacco tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "consumer_staples",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="aerospace",
        title="Aerospace",
        family="sector",
        philosophy="""
Aerospace suppliers and OEMs build aircraft systems with long order backlogs. Equity investors in Aerospace must understand how industrials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to aerospace. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Aerospace peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in aerospace",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies aerospace tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "industrials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="defense",
        title="Defense",
        family="sector",
        philosophy="""
Defense contractors supply weapons and platforms funded by multi-year government budgets. Equity investors in Defense must understand how industrials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to defense. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Defense peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in defense",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies defense tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "industrials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="construction",
        title="Construction",
        family="sector",
        philosophy="""
Construction firms build infrastructure and buildings tied to public and private capex. Equity investors in Construction must understand how industrials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to construction. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Construction peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in construction",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies construction tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "industrials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="engineering",
        title="Engineering",
        family="sector",
        philosophy="""
Engineering and EPCM firms design complex industrial and infrastructure projects. Equity investors in Engineering must understand how industrials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to engineering. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Engineering peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in engineering",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies engineering tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "industrials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="machinery",
        title="Machinery",
        family="sector",
        philosophy="""
Machinery makers sell equipment into construction, agriculture, and manufacturing cycles. Equity investors in Machinery must understand how industrials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to machinery. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Machinery peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in machinery",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies machinery tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "industrials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="logistics",
        title="Logistics",
        family="sector",
        philosophy="""
Logistics providers move and warehouse goods as trade and e-commerce volumes fluctuate. Equity investors in Logistics must understand how industrials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to logistics. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Logistics peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in logistics",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies logistics tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "industrials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="railroads",
        title="Railroads",
        family="sector",
        philosophy="""
Railroads haul freight efficiently over long distances with oligopolistic networks. Equity investors in Railroads must understand how industrials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to railroads. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Railroads peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in railroads",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies railroads tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "industrials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="shipping",
        title="Shipping",
        family="sector",
        philosophy="""
Ocean shipping moves bulk and container cargo with freight-rate cyclicality. Equity investors in Shipping must understand how industrials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to shipping. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Shipping peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in shipping",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies shipping tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "industrials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="trucking",
        title="Trucking",
        family="sector",
        philosophy="""
Trucking firms provide flexible freight with fuel, driver, and spot-rate sensitivity. Equity investors in Trucking must understand how industrials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to trucking. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Trucking peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in trucking",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies trucking tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "industrials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="packaging",
        title="Packaging",
        family="sector",
        philosophy="""
Packaging producers supply containers to consumer and industrial end markets. Equity investors in Packaging must understand how industrials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to packaging. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Packaging peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in packaging",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies packaging tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "industrials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="oil_exploration",
        title="Oil Exploration",
        family="sector",
        philosophy="""
E&P companies explore and produce oil with oil-price and reserve risk. Equity investors in Oil Exploration must understand how energy tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to oil exploration. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(
            _F(
                "Crack spread",
                r"CS = P_{products} - P_{crude}",
                "Refining margin indicator.",
            ),
        ),
        screens=(
        "Top-quartile ROIC vs Oil Exploration peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in oil exploration",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies oil_exploration tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "energy",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="oil_refining",
        title="Oil Refining",
        family="sector",
        philosophy="""
Refiners crack crude into fuels earning crack spreads through cycles. Equity investors in Oil Refining must understand how energy tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to oil refining. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(
            _F(
                "Crack spread",
                r"CS = P_{products} - P_{crude}",
                "Refining margin indicator.",
            ),
        ),
        screens=(
        "Top-quartile ROIC vs Oil Refining peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in oil refining",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies oil_refining tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "energy",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="lng",
        title="LNG",
        family="sector",
        philosophy="""
LNG exporters liquefy and ship natural gas into global trade flows. Equity investors in LNG must understand how energy tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to lng. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs LNG peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in lng",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies lng tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "energy",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="pipelines",
        title="Pipelines",
        family="sector",
        philosophy="""
Pipeline midstream assets move hydrocarbons under fee and volume contracts. Equity investors in Pipelines must understand how energy tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to pipelines. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Pipelines peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in pipelines",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies pipelines tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "energy",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="solar",
        title="Solar",
        family="sector",
        philosophy="""
Solar developers and manufacturers ride renewable adoption and policy support. Equity investors in Solar must understand how energy tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to solar. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Solar peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in solar",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies solar tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "energy",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="wind",
        title="Wind",
        family="sector",
        philosophy="""
Wind power OEMs and operators build renewable generation capacity. Equity investors in Wind must understand how energy tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to wind. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Wind peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in wind",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies wind tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "energy",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="nuclear",
        title="Nuclear",
        family="sector",
        philosophy="""
Nuclear utilities and fuel cycle firms provide baseload low-carbon power. Equity investors in Nuclear must understand how energy tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to nuclear. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Nuclear peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in nuclear",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies nuclear tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "energy",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="hydrogen",
        title="Hydrogen",
        family="sector",
        philosophy="""
Hydrogen technology spans production, transport, and industrial decarbonization use cases. Equity investors in Hydrogen must understand how energy tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to hydrogen. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Hydrogen peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in hydrogen",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies hydrogen tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "energy",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="battery_storage",
        title="Battery Storage",
        family="sector",
        philosophy="""
Battery and storage companies enable renewable firming and EV energy density. Equity investors in Battery Storage must understand how energy tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to battery storage. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Battery Storage peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in battery storage",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies battery_storage tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "energy",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="chemicals",
        title="Chemicals",
        family="sector",
        philosophy="""
Chemical firms produce specialty and commodity molecules for industry. Equity investors in Chemicals must understand how materials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to chemicals. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Chemicals peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in chemicals",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies chemicals tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "materials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="steel",
        title="Steel",
        family="sector",
        philosophy="""
Steel producers serve construction and manufacturing with highly cyclical pricing. Equity investors in Steel must understand how materials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to steel. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Steel peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in steel",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies steel tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "materials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="aluminum",
        title="Aluminum",
        family="sector",
        philosophy="""
Aluminum smelters and fabricators supply lightweight metal for transport and packaging. Equity investors in Aluminum must understand how materials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to aluminum. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Aluminum peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in aluminum",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies aluminum tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "materials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="copper",
        title="Copper",
        family="sector",
        philosophy="""
Copper miners benefit from electrification demand and scarce new supply. Equity investors in Copper must understand how materials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to copper. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Copper peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in copper",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies copper tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "materials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="lithium",
        title="Lithium",
        family="sector",
        philosophy="""
Lithium producers feed battery supply chains for EVs and storage. Equity investors in Lithium must understand how materials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to lithium. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Lithium peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in lithium",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies lithium tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "materials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="rare_earths",
        title="Rare Earths",
        family="sector",
        philosophy="""
Rare earth producers supply magnets and electronics critical to defense and EVs. Equity investors in Rare Earths must understand how materials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to rare earths. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Rare Earths peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in rare earths",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies rare_earths tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "materials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="cement",
        title="Cement",
        family="sector",
        philosophy="""
Cement makers supply construction materials with local regional pricing. Equity investors in Cement must understand how materials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to cement. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Cement peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in cement",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies cement tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "materials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="glass",
        title="Glass",
        family="sector",
        philosophy="""
Glass manufacturers serve containers, construction, and automotive markets. Equity investors in Glass must understand how materials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to glass. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Glass peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in glass",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies glass tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "materials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="paper",
        title="Paper",
        family="sector",
        philosophy="""
Paper and pulp companies produce packaging and printing grades. Equity investors in Paper must understand how materials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to paper. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Paper peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in paper",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies paper tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "materials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="fertilizers",
        title="Fertilizers",
        family="sector",
        philosophy="""
Fertilizer producers supply nutrients critical to crop yields and food security. Equity investors in Fertilizers must understand how materials tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to fertilizers. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Fertilizers peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in fertilizers",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies fertilizers tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "materials",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="electric_utilities",
        title="Electric Utilities",
        family="sector",
        philosophy="""
Electric utilities generate and distribute power under regulated returns. Equity investors in Electric Utilities must understand how utilities tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to electric utilities. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Electric Utilities peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in electric utilities",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies electric_utilities tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "utilities",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="water_utilities",
        title="Water Utilities",
        family="sector",
        philosophy="""
Water utilities provide essential service with defensive, regulated cash flows. Equity investors in Water Utilities must understand how utilities tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to water utilities. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Water Utilities peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in water utilities",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies water_utilities tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "utilities",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="gas_utilities",
        title="Gas Utilities",
        family="sector",
        philosophy="""
Gas utilities distribute natural gas to homes and businesses. Equity investors in Gas Utilities must understand how utilities tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to gas utilities. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Gas Utilities peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in gas utilities",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies gas_utilities tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "utilities",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="renewable_utilities",
        title="Renewable Utilities",
        family="sector",
        philosophy="""
Renewable-focused utilities and IPPs own wind, solar, and storage fleets. Equity investors in Renewable Utilities must understand how utilities tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to renewable utilities. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Renewable Utilities peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in renewable utilities",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies renewable_utilities tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "utilities",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="reit_cell_tower",
        title="Cell Tower REITs",
        family="sector",
        philosophy="""
Tower REITs lease antenna space to wireless carriers with long contracts. Equity investors in Cell Tower REITs must understand how real estate tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to cell tower reits. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(
            _F(
                "AFFO yield",
                r"AFFO\ yield = \frac{AFFO}{Price}",
                "Cash earnings yield for tower REITs.",
            ),
        ),
        screens=(
        "Top-quartile ROIC vs Cell Tower REITs peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in cell tower reits",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies reit_cell_tower tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "real_estate_sector",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="farming",
        title="Farming",
        family="sector",
        philosophy="""
Farm operators grow crops and raise animals exposed to weather and commodity prices. Equity investors in Farming must understand how agriculture tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to farming. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Farming peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in farming",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies farming tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "agriculture",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="ag_equipment",
        title="Agricultural Equipment",
        family="sector",
        philosophy="""
Ag equipment makers sell tractors and implements into farm capex cycles. Equity investors in Agricultural Equipment must understand how agriculture tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to agricultural equipment. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Agricultural Equipment peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in agricultural equipment",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies ag_equipment tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "agriculture",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="seeds",
        title="Seeds",
        family="sector",
        philosophy="""
Seed and trait companies sell genetically improved seeds to growers. Equity investors in Seeds must understand how agriculture tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to seeds. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Seeds peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in seeds",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies seeds tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "agriculture",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="livestock",
        title="Livestock",
        family="sector",
        philosophy="""
Livestock producers raise cattle, poultry, and hogs for protein demand. Equity investors in Livestock must understand how agriculture tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to livestock. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Livestock peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in livestock",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies livestock tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "agriculture",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="food_distribution",
        title="Food Distribution",
        family="sector",
        philosophy="""
Distributors connect farms and processors to grocery and foodservice channels. Equity investors in Food Distribution must understand how agriculture tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to food distribution. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Food Distribution peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in food distribution",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies food_distribution tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "agriculture",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="fisheries",
        title="Fisheries",
        family="sector",
        philosophy="""
Seafood producers and aquafarms supply protein with sustainability challenges. Equity investors in Fisheries must understand how agriculture tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to fisheries. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Fisheries peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in fisheries",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies fisheries tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "agriculture",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="ports",
        title="Ports",
        family="sector",
        philosophy="""
Port operators handle cargo volumes tied to global trade. Equity investors in Ports must understand how transportation tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to ports. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Ports peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in ports",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies ports tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "transportation",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="airports",
        title="Airports",
        family="sector",
        philosophy="""
Airport operators earn from aeronautical and retail concession traffic. Equity investors in Airports must understand how transportation tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to airports. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Airports peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in airports",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies airports tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "transportation",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="freight_forwarding",
        title="Freight Forwarding",
        family="sector",
        philosophy="""
Freight forwarders arrange multimodal shipping for shippers worldwide. Equity investors in Freight Forwarding must understand how transportation tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to freight forwarding. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Freight Forwarding peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in freight forwarding",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies freight_forwarding tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "transportation",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="public_transit",
        title="Public Transit",
        family="sector",
        philosophy="""
Transit-related firms and suppliers serve urban mobility systems. Equity investors in Public Transit must understand how transportation tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to public transit. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Public Transit peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in public transit",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies public_transit tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "transportation",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="satellites",
        title="Satellite Companies",
        family="sector",
        philosophy="""
Satellite operators provide imaging, broadband, and navigation services. Equity investors in Satellite Companies must understand how space tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to satellite companies. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Satellite Companies peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in satellite companies",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies satellites tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "space",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="launch_providers",
        title="Launch Providers",
        family="sector",
        philosophy="""
Launch companies put payloads into orbit competing on cost per kilogram. Equity investors in Launch Providers must understand how space tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to launch providers. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Launch Providers peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in launch providers",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies launch_providers tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "space",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="space_infrastructure",
        title="Space Infrastructure",
        family="sector",
        philosophy="""
Space infrastructure covers ground stations, components, and orbital services. Equity investors in Space Infrastructure must understand how space tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to space infrastructure. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Space Infrastructure peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in space infrastructure",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies space_infrastructure tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "space",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="carbon_capture",
        title="Carbon Capture",
        family="sector",
        philosophy="""
Carbon capture technologies remove or sequester CO₂ for industrial decarbonization. Equity investors in Carbon Capture must understand how emerging industries tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to carbon capture. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Carbon Capture peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in carbon capture",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies carbon_capture tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "emerging_industries",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="synthetic_biology",
        title="Synthetic Biology",
        family="sector",
        philosophy="""
Synbio designs organisms and biomolecules for materials, food, and therapeutics. Equity investors in Synthetic Biology must understand how emerging industries tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to synthetic biology. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Synthetic Biology peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in synthetic biology",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies synthetic_biology tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "emerging_industries",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="fusion_energy",
        title="Fusion Energy",
        family="sector",
        philosophy="""
Fusion startups pursue net energy gain for abundant low-carbon power. Equity investors in Fusion Energy must understand how emerging industries tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to fusion energy. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Fusion Energy peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in fusion energy",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies fusion_energy tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "emerging_industries",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="3d_printing",
        title="3D Printing",
        family="sector",
        philosophy="""
Additive manufacturing builds complex parts with less waste than machining. Equity investors in 3D Printing must understand how emerging industries tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to 3d printing. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs 3D Printing peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in 3d printing",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies 3d_printing tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "emerging_industries",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="drone_technology",
        title="Drone Technology",
        family="sector",
        philosophy="""
Drone platforms serve imaging, delivery, and defense use cases. Equity investors in Drone Technology must understand how emerging industries tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to drone technology. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Drone Technology peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in drone technology",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies drone_technology tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "emerging_industries",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="autonomous_vehicles",
        title="Autonomous Vehicles",
        family="sector",
        philosophy="""
AV stacks combine sensors, software, and compute for driverless mobility. Equity investors in Autonomous Vehicles must understand how emerging industries tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to autonomous vehicles. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Autonomous Vehicles peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in autonomous vehicles",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies autonomous_vehicles tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "emerging_industries",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="wearable_technology",
        title="Wearable Technology",
        family="sector",
        philosophy="""
Wearables track health and productivity on the body with sensor fusion. Equity investors in Wearable Technology must understand how emerging industries tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to wearable technology. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Wearable Technology peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in wearable technology",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies wearable_technology tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "emerging_industries",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="digital_payments",
        title="Digital Payments",
        family="sector",
        philosophy="""
Digital payments rail move money online with take rates and network effects. Equity investors in Digital Payments must understand how emerging industries tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to digital payments. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Digital Payments peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in digital payments",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies digital_payments tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "emerging_industries",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="blockchain_infra",
        title="Blockchain Infrastructure",
        family="sector",
        philosophy="""
Blockchain infrastructure provides rails for crypto settlement and tokenization. Equity investors in Blockchain Infrastructure must understand how emerging industries tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to blockchain infrastructure. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Blockchain Infrastructure peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in blockchain infrastructure",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies blockchain_infra tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "emerging_industries",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="clean_water",
        title="Clean Water Technology",
        family="sector",
        philosophy="""
Water tech improves purification, desalination, and efficiency for scarce freshwater. Equity investors in Clean Water Technology must understand how emerging industries tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to clean water technology. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Clean Water Technology peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in clean water technology",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies clean_water tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "emerging_industries",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="waste_management",
        title="Waste Management",
        family="sector",
        philosophy="""
Waste managers collect and process refuse with landfill and recycling assets. Equity investors in Waste Management must understand how emerging industries tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to waste management. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Waste Management peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in waste management",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies waste_management tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "emerging_industries",
        ),
        further_reading=(),
    )
)

register(
    DeepChapter(
        topic_id="recycling",
        title="Recycling",
        family="sector",
        philosophy="""
Recycling firms circularize materials streams with commodity residual exposure. Equity investors in Recycling must understand how emerging industries tailwinds and headwinds transmit to individual company fundamentals.
""".strip(),
        how_it_works="""
Key drivers include end-market demand growth, pricing power, input cost pass-through, and regulatory or technological disruption specific to recycling. Valuation varies: mature sub-industries trade on P/E and FCF yield; growth niches on EV/Sales or pipeline NPV. Cyclicality depends on capex intensity, commodity linkage, and consumer vs enterprise exposure. Screen for balance-sheet resilience, management capital allocation track record, and market share trends vs peers in the same leaf.
""".strip(),
        formulas=(),
        screens=(
        "Top-quartile ROIC vs Recycling peers",
        "Revenue growth at or above sub-industry average",
        "Net debt/EBITDA manageable for cycle stage",
        "Valuation vs 5-year sector median reasonable",
        ),
        traps=(
        "Secular decline misread as cyclical dip in recycling",
        "Customer or supplier concentration risk ignored",
        "Equity dilution from growth capex or acquisitions",
        "Regulatory change not priced into estimates",
        ),
        catalysts=(
        "Market share gains vs sub-industry peers",
        "New product or geography expansion",
        "Operating leverage from fixed cost absorption",
        "Industry consolidation or M&A premium",
        ),
        fate_hook="`analytics/industry_taxonomy.py` classifies recycling tickers; peer co-movement and sector beta in `analytics/industry_comovement.py`.",
        related=(
        "emerging_industries",
        ),
        further_reading=(),
    )
)

