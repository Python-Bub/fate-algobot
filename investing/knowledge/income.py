"""Income investing — deep chapters (1/1 through the family)."""

from __future__ import annotations

from investing.knowledge import DeepChapter, FormulaSpec, register

_F = FormulaSpec

register(
    DeepChapter(
        topic_id="dividend",
        title="Dividend Investing",
        family="income",
        philosophy="""
Dividend investing treats cash returned to shareholders as the primary proof that
a business is real, profitable, and disciplined — not merely a story on a slide.
Regular payouts provide a tangible return stream independent of daily price noise,
appealing to retirees, endowments, and anyone who wants equities without betting
entirely on capital gains. The philosophy is conservative at its core: companies
that can fund dividends through cycles demonstrate earnings quality and management
commitment to owners.

Dividends are not free money — they are capital allocation choices. A high payout
can starve reinvestment; a skipped dividend can crater a stock. The art is matching
yield to sustainability: coverage by earnings and free cash flow, balance-sheet
strength, and industry norms. Total return still matters — dividend yield plus
price change — but the income sleeve anchors psychology and cash planning in
volatile markets.


Dividend investing rewards patience and punishes surprise cuts more than missed earnings beats. The income investor thinks in calendar cash — matching payout dates to spending needs — while still watching total return because permanent capital loss overwhelms any yield.""".strip(),
        how_it_works="""
Build a universe of dividend payers: positive dividend history, payout ratio below
a sector-appropriate ceiling, and debt serviceable in downturns. Rank by yield,
but penalize yields that look too good (often traps). Reinvest dividends (DRIP)
to compound share count, or spend for living expenses — match portfolio design to
goal.

Valuation uses dividend discount models: Gordon Growth values perpetual dividend
streams. Compare implied value to price for margin of safety. Monitor ex-dividend
dates, special dividends, and tax treatment (qualified vs ordinary).

Sector clusters: utilities, consumer staples, banks, energy majors. Diversify
across sectors so one commodity or rate shock does not dominate income. Pair yield
with quality screens — dividend aristocrats emphasize consistency over raw yield.


Construct a dividend calendar across months to smooth cash receipt; many stocks pay quarterly on clustered dates. Compare after-tax yield to muni or bond alternatives at your bracket. Use DRIP in accumulation phase; switch to cash sweep in distribution phase without forcing sells in down markets unless coverage breaks.""".strip(),
        formulas=(
            _F(
                "Dividend yield",
                r"Yield = \frac{D_{annual}}{P}",
                "Annual dividend per share divided by price — the headline income rate.",
                "investing.formulas.income.dividend_yield",
            ),
            _F(
                "Gordon Growth Model",
                r"P_0 = \frac{D_1}{r - g}",
                "Intrinsic value from next year’s dividend D₁, required return r, and perpetual growth g — requires g < r.",
                "investing.formulas.income.gordon_growth_value",
            ),
            _F(
                "Payout ratio",
                r"Payout = \frac{DPS}{EPS}",
                "Fraction of earnings paid as dividends; > 1 is usually unsustainable without asset sales or debt.",
            ),
            _F(
                "Dividend coverage",
                r"Coverage = \frac{EPS}{DPS}",
                "Earnings cover for the dividend; values above 1.2–1.5 add comfort.",
                "investing.formulas.income.dividend_coverage",
            ),
        ),
        screens=(
            "Positive dividend for 5+ years (10+ for aristocrat-style)",
            "Payout ratio < 60–75% (sector-adjusted)",
            "FCF covers dividend with cushion",
            "Debt/equity and interest coverage acceptable",
            "Yield above benchmark (e.g. S&P) but not extreme outlier vs peers",
            "No recent dividend cut without clear recovery plan",
        ),
        traps=(
            "Dividend trap: high yield from falling price, not rising payout",
            "Payout > earnings for multiple years",
            "Special dividend mistaken for recurring income",
            "Sector concentration (all REITs or all banks)",
        ),
        catalysts=(
            "Dividend initiation or increase announcement",
            "Multiple expansion when rates fall (yield stocks bid)",
            "Share buyback plus stable dividend (total payout rise)",
            "Earnings recovery restoring coverage after cut",
        ),
        fate_hook="Gordon model and coverage in `investing.formulas.income`; `book_rank_boost` in `investing.integrate` applies GGM MOS + yield score with `BOOK_W_INCOME` and `BOOK_DDM_R` / `BOOK_DDM_G`.",
        related=("dividend_growth", "high_yield", "reit_income", "preferred_shares", "compounders"),
        further_reading=(
            "Jeremy Siegel — The Future for Investors (dividends matter)",
            "S&P Dividend Aristocrats methodology",
        ),
    )
)

register(
    DeepChapter(
        topic_id="dividend_growth",
        title="Dividend Growth Investing",
        family="income",
        philosophy="""
Dividend growth investing prioritizes companies that raise payouts consistently
— often annually for decades — over those offering the highest headline yield today.
The philosophy rests on a powerful compounding mechanic: yield-on-cost rises as
dividends increase while you hold, sometimes exceeding initial high-yield names
within years. Management that raises dividends signals confidence in future cash
flows and capital discipline; repeated increases build a covenant with shareholders
that cuts are culturally painful.

This is income investing with a growth mindset. You accept lower current yield for
faster dividend CAGR, betting that quality compounders return more cash over a
20-year horizon than distressed high-yielders. Dividend growth correlates with
quality factors: stable ROE, moderate payout, strong brands, and pricing power
that passes inflation to customers before shareholders.


Dividend growth is a quality signal with a long memory — boards do not raise payouts unless they expect future cash. The strategy sacrifices headline yield for a rising stream that often outpaces inflation without requiring you to chase risky high-yield traps.""".strip(),
        how_it_works="""
Screen for dividend growth streak (5, 10, 25 years — various indices exist),
minimum dividend growth rate (e.g. 5%+ CAGR), and payout ratio room to grow.
Aristocrats (25+ years increases) and Champions (25+ years any amount) provide
lists; verify fundamentals, not just streak mechanics.

Model future income: project dividend D_t = D_0 × (1+g_d)^t. Compare to bond
ladders — dividend growth often beats fixed coupons over long horizons with tax
advantages on qualified dividends. Reinvest raises via DRIP to accelerate compounding.

Sell when dividend cut, payout ratio breaches safety, or ROIC deteriorates —
the streak breaking is usually the thesis breaking. Avoid overpaying: even great
dividend growers suffer if entry P/E is extreme.


Project five-year income using conservative dividend CAGR (below historical if payout is rising). Screen for payout headroom: a 40% payout growing 8% is safer than 85% payout growing 8%. When a stalwart skips a raise (not a cut), treat it as yellow flag — investigate before adding.""".strip(),
        formulas=(
            _F(
                "Dividend growth rate",
                r"g_d = \left(\frac{D_t}{D_0}\right)^{1/t} - 1",
                "CAGR of dividends per share — the core metric for this strategy.",
            ),
            _F(
                "Yield on cost",
                r"YOC = \frac{D_{current}}{P_{purchase}}",
                "Current dividend divided by original cost — shows compounding income power.",
            ),
            _F(
                "Gordon Growth (dividend form)",
                r"P_0 = \frac{D_1}{r - g}",
                "Value a perpetually growing dividend stream; g is long-run dividend growth, must satisfy g < r.",
                "investing.formulas.income.gordon_growth_value",
            ),
            _F(
                "Sustainable dividend growth",
                r"g_d \approx ROE \times (1 - payout)",
                "Retention × return on equity bounds plausible long-run dividend growth.",
            ),
        ),
        screens=(
            "Dividend increased ≥ 5 years (stricter for aristocrat/champion lists)",
            "5-yr dividend CAGR ≥ 5–7%",
            "Payout ratio below 60% with room to grow",
            "Earnings and FCF growth support future raises",
            "Debt manageable through cycles",
            "ROE consistently above cost of capital",
        ),
        traps=(
            "Small base effect (tiny dividend raised 10% — meaningless dollars)",
            "Debt-funded dividend growth",
            "Streak maintained via minimal $0.01 raises while fundamentals weaken",
            "Overconcentration in slow-growth high-payout sectors",
        ),
        catalysts=(
            "Annual dividend increase above historical average",
            "Payout ratio reset lower after buybacks (more room to grow)",
            "Earnings acceleration enabling faster dividend CAGR",
            "Inclusion in dividend growth indices (institutional flows)",
        ),
        fate_hook="GGM in `investing.formulas.income.gordon_growth_value` with configurable r,g in `investing.integrate`; dividend coverage and payout feed income score alongside yield.",
        related=("dividend", "compounders", "quality_growth", "high_yield", "buffett"),
        further_reading=(
            "S&P Dividend Aristocrats / Dividend Achievers",
            "Peter Lynch — dividend growth in stalwarts",
        ),
    )
)

register(
    DeepChapter(
        topic_id="high_yield",
        title="High-Yield Income",
        family="income",
        philosophy="""
High-yield income strategies maximize current cash flow — from elevated dividend
yields on common stock, high-coupon bonds, or hybrid securities — accepting that
the highest yields often signal distress, cyclical peaks, or structural payout
stress. The philosophy is explicit trade-off: you need income now (retirement,
endowment spending) and will work harder on credit analysis to avoid traps. A 8%
yield that cuts to 2% destroys total return; a 5% yield that grows beats both on
a decade view.

High yield is not ‘set and forget.’ It demands ongoing monitoring of coverage,
leverage, commodity exposure, and refinancing walls. Diversification across issuers
and sectors reduces idiosyncratic blow-ups. The best high-yield outcomes combine
above-market yield with a catalyst to repair balance sheet or normalize payout
after a temporary impairment.


High yield is compensation for risk, not a gift — the market rarely leaves free 10% yields for stable credits. Your edge is forensic work on coverage, covenants, and industry cyclicality, accepting that some positions will cut and must be sized accordingly.""".strip(),
        how_it_works="""
Screen for yield above index median (e.g. top quartile of investable universe)
then apply sustainability filters: payout ratio, FCF coverage, net debt/EBITDA,
interest coverage, and recent dividend history (cuts in last 5 years flagged).

Segment by risk bucket: stable high yield (pipelines, telcos), cyclical high yield
(energy, shipping), and distressed yield (turnaround). Size cyclical and distressed
smaller. Use bond market signals — credit spreads widening often precede equity
dividend cuts.

Tax and account placement matter: hold tax-inefficient high yield in IRAs when
possible. Compare to IG bond yield + equity risk premium — is extra yield compensation
adequate for downgrade/default risk?


Segment the portfolio into tiers: core sustainable yield, opportunistic turnaround yield, and speculative yield with strict caps. Use bond market CDS or credit ratings as early warning for equity dividends. Reinvest selectively — sometimes the best action after a cut is redeploy into survivors, not average down.

Review dividend announcements within 24 hours — cuts cluster by sector and early exit preserves capital for redeployment.""".strip(),
        formulas=(
            _F(
                "Dividend yield",
                r"Yield = \frac{D}{P}",
                "Headline yield — compare to peers and history, not in isolation.",
                "investing.formulas.income.dividend_yield",
            ),
            _F(
                "High-yield score (FATE)",
                r"score = f(yield, payout, coverage)",
                "Rewards attractive yield with sustainable payout and EPS coverage; penalizes payout > 1.",
                "investing.formulas.income.high_yield_score",
            ),
            _F(
                "Interest coverage",
                r"Coverage = \frac{EBIT}{Interest}",
                "For levered high-yield issuers — falling coverage precedes dividend stress.",
            ),
            _F(
                "FCF payout",
                r"FCF\ Payout = \frac{Dividends}{FCF}",
                "Cash-based payout sustainability — more honest than EPS during write-downs.",
            ),
        ),
        screens=(
            "Yield top quartile vs sector benchmark",
            "Payout ratio < 90% (stricter for common stock)",
            "FCF/dividend > 1.1×",
            "No dividend cut in last 3 years unless documented turn",
            "Credit rating or spread not in free-fall",
            "Diversify: no single name > 3–5% of income portfolio",
        ),
        traps=(
            "Yield trap: price collapse inflates yield before cut",
            "Return of capital masquerading as income (ROC)",
            "Cyclical peak earnings supporting unsustainable payout",
            "Leveraged balance sheet + rising rates",
        ),
        catalysts=(
            "Deleveraging restoring dividend safety",
            "Asset sale funding debt paydown",
            "Commodity price recovery (sector-specific)",
            "Refinancing closed at manageable coupon",
        ),
        fate_hook="`high_yield_score` and `dividend_coverage` in `investing.formulas.income`; blended in income family via `investing.integrate.book_rank_boost` (40% weight on yield/sustainability).",
        related=("dividend", "reit_income", "preferred_shares", "infrastructure_income", "turnaround"),
        further_reading=(
            "High-yield equity research (utilities, MLPs, telco)",
            "Credit analysis primers for equity income investors",
        ),
    )
)

register(
    DeepChapter(
        topic_id="preferred_shares",
        title="Preferred Shares",
        family="income",
        philosophy="""
Preferred shares occupy the capital stack between senior debt and common equity:
holders typically receive fixed (or floating) dividends before common dividends,
and have priority over common in liquidation — but sit junior to bonds and bank
deposits. The philosophy favors investors who want higher income than investment-grade
bonds with less volatility and call risk than common stock, accepting that preferreds
lack common’s unlimited upside and often carry issuer call features that cap gains
when rates fall.

Preferreds are contracts — read the prospectus. Cumulative vs non-cumulative,
convertible features, trust-preferred structures, and regulatory capital treatment
(for bank prefs) all change risk. Income is the main return driver; price moves
with interest rates, credit spreads, and issuer health.


Preferreds are bond-like until they are not — credit stress converts them into equity-like drawdowns without equity-like upside. Read the indenture: cumulative features, voting triggers on missed payments, and change-of-control puts can dominate total return more than coupon.""".strip(),
        how_it_works="""
Identify preferred issues from banks, utilities, REITs, and insurers — often
$25 par with quarterly dividends quoted as annual coupon (e.g. 6% = $1.50/year).
Buy at or below par when possible; premium purchases increase yield-to-call risk.
Monitor call dates: issuers redeem when refinancing cheaper, capping price upside.

Rate sensitivity: when rates rise, fixed-rate prefs typically fall like long bonds;
floating-rate prefs help in rising-rate environments. Credit events (bank stress)
hit prefs before senior debt but after commons are wiped — 2008 lesson.

Portfolio: ladder maturities/call dates, diversify issuers, avoid over-concentration
in one capital stack. ETFs exist for diversification but embed fees and index rules.


Build a call-date ladder like a bond ladder — know when issuers can redeem you at par. Prefer buying at discount to par when credit is stable; avoid premium purchases near call unless yield-to-call still clears hurdle. Monitor issuer common dividend — if common is cut, preferred may follow in stress scenarios.""".strip(),
        formulas=(
            _F(
                "Current yield (preferred)",
                r"Yield = \frac{D_{annual}}{P}",
                "Annual dividend divided by market price — not YTM if callable.",
            ),
            _F(
                "Yield to call",
                r"YTC = \text{IRR to earliest call date}",
                "Return if issuer calls at par — critical when trading above par.",
            ),
            _F(
                "Current yield vs bond",
                r"Spread = Yield_{pref} - Yield_{IG}",
                "Compensation for subordination and equity-like features.",
            ),
            _F(
                "Gordon Growth (common comparison)",
                r"P_0 = \frac{D_1}{r - g}",
                "Common dividend valuation anchor; preferred often valued as bond-like with g ≈ 0.",
                "investing.formulas.income.gordon_growth_value",
            ),
        ),
        screens=(
            "Investment-grade issuer or understood credit profile",
            "Current yield attractive vs IG corporates of similar maturity",
            "Cumulative dividends if non-investment-grade (missed payments must catch up)",
            "Call date ≥ 2 years or YTC acceptable",
            "Liquidity: average volume supports exit",
            "Not deeply subordinated within complex bank capital stack unless specialist",
        ),
        traps=(
            "Callable at par when you paid premium",
            "Non-cumulative preferred — dividends skipped permanently",
            "Convertible prefs diluting on conversion surprise",
            "Illiquid issues with wide bid-ask",
        ),
        catalysts=(
            "Rate cut lowering refi cost — call likely",
            "Credit upgrade tightening spread",
            "Issuer redemption at par (return of capital event)",
            "Special situation: post-restructuring prefs with improved coverage",
        ),
        fate_hook="Preferred dividends roll into equity yield fields when common prefs absent; income scoring via `high_yield_score` / GGM path in `investing.integrate` for dividend-paying common proxies.",
        related=("preferred_stock", "bond_laddering", "high_yield", "reit_income", "dividend"),
        further_reading=(
            "FINRA — preferred securities investor alert",
            "Issuer prospectus supplements (mandatory reading)",
        ),
    )
)

register(
    DeepChapter(
        topic_id="covered_call_income",
        title="Covered Call Income",
        family="income",
        philosophy="""
Covered call writing sells call options against stock you already own, collecting
premium that enhances income — especially in flat or mildly bullish markets. The
philosophy exchanges unlimited upside above the strike for immediate cash flow:
you are paid to cap gains at a level you deem acceptable. For income-focused
investors, premiums can materially lift total return when underlying appreciation
is modest, turning a low-yield stock into a higher ‘economic yield.’

This is not free income — you bear full downside on the stock minus premium received,
and you may regret the cap if the stock surges. Covered calls fit names you would
hold anyway, where you would sell into strength near resistance. They are poorly
suited to high-conviction moonshots where uncapped upside is the thesis.


Covered calls transform equity risk into a structured payoff — you are short volatility and long the underlying. That fits income mandates in range markets but underperforms in melt-up rallies unless you roll intelligently. Treat premium as partial sale of upside, not ‘free money.’""".strip(),
        how_it_works="""
Own ≥ 100 shares per contract. Sell out-of-the-money calls (e.g. 5–10% above spot)
with 30–45 days to expiration for balanced premium vs assignment risk. If stock
stays below strike, keep premium and repeat. If above strike at expiry, shares
called away — return is stock gain to strike plus premium (max return formula).

Manage rolls: if stock approaches strike early, buy back call or roll up/out.
Tax: premiums adjust cost basis; assignment triggers gain/loss on shares. Use
tax-advantaged accounts when turnover is high.

 ETFs (buy-write, JEPI-style) automate but embed strategy rules and fees.


Select strikes where you are genuinely willing to sell — emotional regret causes poor rolls. Track annualized premium yield versus historical volatility; writing calls when IV is low wastes edge. Around ex-dividend, early assignment risk rises for deep ITM calls — adjust strike or skip the cycle.

Keep a log of rolled positions for tax lot matching — sloppy records turn income strategy into an accounting headache.""".strip(),
        formulas=(
            _F(
                "Covered call premium yield",
                r"Yield_{cc} = \frac{Premium}{Stock\ Price}",
                "Income from option premium as fraction of stock value — annualize for comparison.",
                "investing.formulas.options",
            ),
            _F(
                "Max return if assigned",
                r"R_{max} = \frac{K - S + Premium}{S}",
                "Maximum return if stock is called at strike K: gain to strike plus premium, divided by initial stock price S.",
                "investing.formulas.derivatives.covered_call_max_return",
            ),
            _F(
                "Breakeven at expiry",
                r"P_{be} = S - Premium",
                "Stock price where combined position breaks even excluding prior gains.",
            ),
            _F(
                "Annualized buy-write yield (approx)",
                r"Yield_{ann} \approx Yield_{cc} \times \frac{365}{Days}",
                "Rough annualization — overstated if you would not write every cycle identically.",
            ),
        ),
        screens=(
            "Underlying is long-term hold with acceptable call-away price",
            "IV rank elevated — richer premiums",
            "Strike 5–15% OTM balancing income vs upside",
            "DTE 30–45 days (theta sweet spot for many writers)",
            "Liquidity in options chain (tight spreads)",
            "Dividend ex-date considered (early assignment risk around div)",
        ),
        traps=(
            "Capping upside on a multi-bagger thesis",
            "Writing calls on falling stock — premium does not cover drawdown",
            "Assignment in taxable account with short-term gain",
            "Naked call confusion — must own shares (covered only)",
        ),
        catalysts=(
            "Elevated implied volatility post-earnings",
            "Range-bound market extending premium harvesting",
            "Dividend capture with call premium overlay",
            "Roll after partial premium decay (theta harvest)",
        ),
        fate_hook="`covered_call_max_return` in `investing.formulas.derivatives`; catalog status soft — pair with options module when live. Income family in `investing.integrate` focuses on dividend GGM path.",
        related=("dividend", "high_yield", "options_basics", "reit_income", "alt_passive"),
        further_reading=(
            "CBOE — buy-write index methodology",
            "Lawrence McMillan — Options as a Strategic Investment",
        ),
    )
)

register(
    DeepChapter(
        topic_id="reit_income",
        title="REIT Income",
        family="income",
        philosophy="""
Real Estate Investment Trusts (REITs) pass through rental and mortgage income
to shareholders as high dividends. U.S. REITs must distribute **≥90% of taxable
income** as dividends to keep the pass-through tax status — that legal payout
floor is why headline yields look rich versus ordinary corporates. The philosophy
treats REITs as liquid real estate wrappers — income without direct property
management — with diversification across property types (industrial, data centers,
apartments, healthcare, retail). REIT income appeals when investors want
inflation-linked cash flows tied to leases and asset values, not just corporate
buybacks.

REITs are rate-sensitive: cap rates and discount rates move with Treasury yields,
so total return swings with the bond market even when occupancy is stable. Not all
REITs are equal — triple-net retail differs from coastal apartments differs from
tower REITs. Understanding lease structure, tenant credit, development pipeline,
and balance-sheet maturity is essential; headline yield alone misleads.


REITs bundle real estate cash flows with public-market volatility — you earn rent economics but mark assets daily. The income investor focuses on AFFO durability and lease quality, accepting that rate cycles will move prices even when tenants pay on time.""".strip(),
        how_it_works="""
Screen by dividend yield, AFFO (adjusted funds from operations) payout ratio,
leverage (net debt/EBITDA), and property-type tailwinds. Prefer AFFO over GAAP
EPS — depreciation distorts earnings. Check same-store NOI growth, lease expirations,
and tenant concentration.

Valuation: price/AFFO vs historical range, NAV estimates from cap rates on assets,
and implied cap rate vs private market transactions. Rising rates hurt levered REITs
with floating debt; fixed-rate long leases help.

Portfolio: diversify property types and geographies; use ETFs for broad exposure
or individual names for thesis. Monitor Fed path and credit spreads as macro overlay.


Stress-test AFFO under rising rates (floating debt share) and under occupancy shocks (tenant bankruptcy scenarios). Compare dividend yield to AFFO yield — large gaps signal cut risk or non-cash adjustments. Use property-type ETFs for core exposure and single names for high-conviction sector views.

Review lease rollover schedules annually — a cheap yield today may face vacancy cliff in three years when major tenants expire.""".strip(),
        formulas=(
            _F(
                "AFFO payout ratio",
                r"Payout_{AFFO} = \frac{Dividends}{AFFO}",
                "Sustainable REIT payout metric — target often < 85–90%.",
            ),
            _F(
                "Cap rate",
                r"Cap = \frac{NOI}{Property\ Value}",
                "NOI yield on assets — higher cap = lower price/NAV all else equal.",
            ),
            _F(
                "Implied cap rate (REIT)",
                r"Cap_{implied} = \frac{NOI_{enterprise}}{EV}",
                "Market-implied yield on operating income — compare to private market caps.",
            ),
            _F(
                "Dividend yield",
                r"Yield = \frac{D}{P}",
                "REIT headline income — verify against AFFO coverage.",
                "investing.formulas.income.dividend_yield",
            ),
        ),
        screens=(
            "AFFO payout < 90%",
            "Same-store NOI growth positive",
            "Net debt/EBITDA within sector norms",
            "Lease maturity ladder manageable",
            "Property type aligned with secular demand (industrial, towers) vs challenged (mall)",
            "Insider/management alignment; sensible development cap",
        ),
        traps=(
            "GAAP EPS payout meaningless (depreciation)",
            "Dividend cut after overleveraged acquisition spree",
            "Retail/obsolescence secular decline",
            "Rate spike + floating-rate debt combo",
        ),
        catalysts=(
            "NAV premium/discount closing via asset sales",
            "Occupancy inflection post-COVID or sector shock",
            "Rate cut cycle boosting property values",
            "M&A takeout at NAV premium",
        ),
        fate_hook="REIT dividends flow through Yahoo `dividendRate` / yield into `investing.integrate` income score (`gordon_growth_value`, `high_yield_score`, coverage).",
        related=("dividend", "high_yield", "real_estate", "infrastructure_income", "asset_based"),
        further_reading=(
            "NAREIT — REIT fundamentals",
            "Green Street — sector cap rate research",
        ),
    )
)

register(
    DeepChapter(
        topic_id="bond_laddering",
        title="Bond Laddering",
        family="income",
        philosophy="""
Bond laddering staggers fixed-income maturities so principal returns at regular
intervals and income arrives predictably — reducing the bet on any single rate
environment. The philosophy rejects timing the yield curve in favor of structural
discipline: when a rung matures, reinvest at the long end (or pre-set ladder spacing)
to maintain the ladder. You trade some yield optimization for sleep-at-night cash
flow and reinvestment optionality.

Ladders suit investors who need known liquidity dates (tuition, retirement spending)
and who want less duration concentration than owning one 30-year bond. They also
mitigate reinvestment risk vs holding all short paper — you lock some long yields
while still getting periodic principal to reinvest if rates rise.


A ladder is a commitment device: it stops you from betting everything on one maturity date or yield level. The income is predictable; the trade-off is you will never catch the perfect bottom in rates — which is acceptable for most liability-driven investors.""".strip(),
        how_it_works="""
Construct equal-dollar rungs across maturities (e.g. 1–10 years annually). Hold
to maturity unless credit deteriorates — mark-to-market swings matter only if
you sell early. On maturity, buy new 10-year (or longest target) rung to preserve
structure. Use Treasuries for zero credit work; corporates/municipals add spread
with issuer diligence.

Compare ladder yield to aggregate bond fund — ladder gives control and defined
maturity; fund gives professional management and continuous duration. ETFs can
approximate ladders (target maturity ETFs) with fees and tracking nuances.

Tax: hold taxable munis or Treasuries appropriately; place corporates in tax-deferred
when yields are fully taxable.


Automate reinvestment rules before maturity — decide in advance whether to roll to the same tenor or shorten if rates spike. Keep a liquidity buffer outside the ladder for emergencies so you never sell rungs at the worst mark. Review credit annually even for buy-and-hold corporates.

Document target weights per rung so reinvestment after maturity does not accidentally shorten or lengthen the ladder.""".strip(),
        formulas=(
            _F(
                "Ladder average yield",
                r"\bar{y} = \frac{1}{n}\sum_{i=1}^{n} y_i",
                "Simple average yield across rungs — approximation of portfolio income rate.",
            ),
            _F(
                "Macaulay duration (concept)",
                r"D_{Mac} = \frac{\sum t \cdot PV(CF_t)}{Price}",
                "Weighted average time to cash flows — ladder lowers single-point duration vs bullet bond.",
            ),
            _F(
                "Reinvestment at maturity",
                r"CF_T = Principal_T + Coupon_{accrued}",
                "Cash returned at each rung for reinvestment at prevailing rates.",
            ),
            _F(
                "Present value of bond",
                r"P = \sum \frac{C}{(1+y)^t} + \frac{F}{(1+y)^T}",
                "Price from yield y, coupons C, face F — building block for rung pricing.",
            ),
        ),
        screens=(
            "Rung spacing matches liquidity needs (annual common)",
            "Credit quality minimum (Treasury/IG corporate/muni per mandate)",
            "Diversified issuers if corporates (no single name dominates)",
            "Callable bonds avoided or priced with YTC",
            "Ladder length matches horizon (10-year ladder for 10-year need)",
        ),
        traps=(
            "Selling rungs in panic at mark-to-market loss",
            "Callable bonds shortening ladder unexpectedly",
            "Concentrated single issuer corporate ladder",
            "Ignoring inflation eroding real income on nominal ladder",
        ),
        catalysts=(
            "Maturity cash redeployed into higher-rate environment",
            "Credit upgrade on corporate rung (optional sell-to-upgrade)",
            "Fed cutting — long rungs appreciate if sold tactically (deviates from pure hold)",
        ),
        fate_hook="Fixed-income ladder logic complements equity income in `investing.integrate`; bond yields not auto-scored in book boost today — pair with macro/rates modules for allocation context.",
        related=("municipal_bonds", "dividend", "high_yield", "infrastructure_income", "alt_passive"),
        further_reading=(
            "Vanguard — bond ladder guides",
            "Fabozzi — Fixed Income Mathematics",
        ),
    )
)

register(
    DeepChapter(
        topic_id="municipal_bonds",
        title="Municipal Bond Income",
        family="income",
        philosophy="""
Municipal bonds fund state and local governments, schools, hospitals, and infrastructure —
paying interest that is often exempt from federal income tax (and sometimes state tax
for in-state residents). The philosophy favors high-bracket taxable investors who
boost after-tax income versus fully taxable Treasuries or corporates of similar
credit quality.

**Soft correction:** munis are tax-advantaged, **not riskless**. Credit events
(Detroit, Puerto Rico), interest-rate / duration risk, call risk, and thin
liquidity still destroy principal. Lower coupon reflects the tax break — not a
government guarantee of safety. Treat them like bonds with preferential tax
treatment, not like cash.

Understanding security structure matters: general obligation (GO) bonds backed by
taxing power vs revenue bonds tied to a project (toll road, hospital receipts).
Pensions, demographics, and political willingness to pay affect GO credit; revenue
bonds depend on project economics. Insurance/wraps add comfort but do not eliminate
analysis need.


Muni advantage is tax math, not magic — at low brackets, taxable bonds may win on TEY. The strategy shines for high earners in high-tax states when in-state exemption stacks with federal exemption on qualifying issues.""".strip(),
        how_it_works="""
Compute taxable-equivalent yield (TEY) = muni yield / (1 − marginal tax rate).
Compare to corporate/Treasury after tax. Build ladders or buy funds; individual
issues suit larger accounts with research capacity. Watch call features, AMT exposure
on some private-activity bonds, and liquidity (many munis trade rarely).

State diversification reduces single-government risk; revenue diversification reduces
project risk. Monitor pension funded ratios and budget deficits for GO credits.
During stress (Detroit, Puerto Rico), recovery hierarchies and legal frameworks
determine outcomes — read offering statements.

Use muni ETFs for broad exposure; direct bonds for tax lot control and known maturity.


Use EMMA for official statements on any individual bond — never rely on broker summaries alone. Ladder GO and revenue separately so project risk does not cluster. For funds, watch expense ratio and AMT exposure; for individuals, track lot-level TEY when swapping.

For large purchases, request official statement from broker and verify call schedule — yield-to-worst often drives true return more than coupon.""".strip(),
        formulas=(
            _F(
                "Taxable-equivalent yield",
                r"TEY = \frac{y_{muni}}{1 - t_{marginal}}",
                "Muni yield grossed up to compare with taxable bonds at your tax bracket.",
            ),
            _F(
                "After-tax corporate yield",
                r"y_{after} = y_{corp} \times (1 - t)",
                "Compare to muni yield on equal footing.",
            ),
            _F(
                "Present value (muni)",
                r"P = \sum \frac{C}{(1+y)^t} + \frac{F}{(1+y)^T}",
                "Standard bond pricing — tax exemption affects y, not formula shape.",
            ),
            _F(
                "Duration / rate risk",
                r"\Delta P \approx -D \cdot \Delta y",
                "Long munis still lose mark-to-market when rates rise.",
            ),
        ),
        screens=(
            "TEY exceeds comparable taxable after your bracket",
            "Credit rating ≥ policy minimum (AAA/AA common for conservative)",
            "GO vs revenue risk understood and diversified",
            "Callable issues priced with yield-to-worst",
            "AMT status checked if subject to alternative minimum tax",
            "In-state exemption benefit weighed vs diversification",
        ),
        traps=(
            "Treating munis as riskless / cash equivalents (they are not)",
            "Ignoring credit, rate, and liquidity risk because of tax exemption",
            "Chasing yield in BBB/high-yield muni without credit skill",
            "Concentrated single municipality or project",
            "Callable bonds called when you needed income stream",
            "Illiquidity forcing sale at discount",
        ),
        catalysts=(
            "Tax law changes affecting muni demand",
            "Credit upgrade/downgrade re-rating",
            "Infrastructure bill increasing new issue supply",
            "Rate cuts boosting muni prices (mark-to-market gain)",
        ),
        fate_hook="Muni TEY not in equity `book_rank_boost`; income philosophy aligns with `investing.formulas.income` yield math — use for after-tax allocation vs dividend equities.",
        related=("bond_laddering", "infrastructure_income", "dividend", "high_yield", "alt_passive"),
        further_reading=(
            "MSRB — EMMA disclosure system",
            "Municipal Market Analytics / rating agency GO reports",
        ),
    )
)

register(
    DeepChapter(
        topic_id="preferred_stock",
        title="Preferred Stock Income Strategies",
        family="income",
        philosophy="""
Preferred stock income strategies build portfolios weighted toward preferred
securities across banks, utilities, REITs, and hybrids — seeking steady distributions
with less common-equity beta than outright stock ownership. The philosophy treats
preferreds as an income sleeve distinct from bonds (subordination, equity-like
features) and distinct from common (capped upside, fixed dividends). Portfolio
managers ladder issuers, mix fixed and floating coupons, and actively manage around
call dates and rate cycles.

Scale matters: individual preferred issues can be illiquid; strategy implementations
often use ETFs (PFF, sector prefs) or separately managed accounts. The goal is
predictable cash flow with controlled drawdowns — not home runs. When rates or
credit dislocate, opportunities appear in discounted prefs of solvent issuers,
but catching falling knives in bank capital stacks requires specialist skill.


A diversified preferred portfolio behaves like a high-yield bond fund with equity subordination — sector tilts (banks, utilities) dominate risk. Active management focuses on call timing and credit migration rather than picking one ‘best’ coupon.""".strip(),
        how_it_works="""
Construct target allocation: e.g. 40% bank prefs, 30% utility, 20% REIT, 10% other.
Within each, rank by yield-to-worst, call protection, cumulative status, and issuer
credit trend. Rebalance quarterly; roll called issues into new primary market
or secondary opportunities.

Monitor Fed path: rising rates hurt fixed-rate prefs; floating-rate structures
help. Credit cycles: widen spreads → price declines but higher yields for new
money. Pair with common equity or CDS signals for early warning on issuers.

Tax: qualified dividend treatment often applies but verify issue structure; some
prefs pay ordinary income. Hold in appropriate accounts.


Set issuer limits (e.g., 5% per parent) to avoid hidden concentration through multiple series. When Fed policy shifts, rotate fixed-to-float mix. Compare fund expenses vs individual issue pick-up — for smaller accounts, ETFs may be optimal after-tax net of fees.

Quarterly, recompute portfolio yield-to-worst after call notices — passive holders get surprised when issues vanish at par.""".strip(),
        formulas=(
            _F(
                "Portfolio yield",
                r"Y_p = \frac{\sum D_i}{\sum P_i}",
                "Weighted income on cost/market across preferred holdings.",
            ),
            _F(
                "Yield to worst",
                r"YTW = \min(YTC, YTM, \ldots)",
                "Conservative yield assuming earliest adverse call or maturity.",
            ),
            _F(
                "Duration approximation",
                r"\Delta P \approx -D \cdot \Delta y",
                "Rate sensitivity for fixed-dividend preferreds.",
            ),
            _F(
                "Gordon Growth (common dividend contrast)",
                r"P_0 = \frac{D_1}{r - g}",
                "Common stock income valued with growth; preferreds often modeled with g ≈ 0 plus credit spread.",
                "investing.formulas.income.gordon_growth_value",
            ),
        ),
        screens=(
            "Diversified across ≥ 15–20 issuers (or ETF equivalent)",
            "Average credit quality matches mandate",
            "YTW acceptable vs IG corporates + equity subordination premium",
            "Call schedule mapped next 24 months",
            "Cumulative feature for lower-rated issuers",
            "Liquidity budget for rebalancing",
        ),
        traps=(
            "Single-sector concentration (all bank Tier-1 prefs)",
            "Premium to par with near-term call",
            "Chasing yield in distressed issuer",
            "ETF premium/discount to NAV ignored",
        ),
        catalysts=(
            "Rate peak → pref rally",
            "Issuer redemption wave — reinvest at new yields",
            "Credit normalization after sector scare",
            "New issue supply at attractive spreads",
        ),
        fate_hook="Preferred income parallels `high_yield_score` logic for equity yielders; `investing.integrate` income path uses `gordon_growth_value` and dividend coverage on common dividend payers as proxy sleeve.",
        related=("preferred_shares", "high_yield", "reit_income", "bond_laddering", "dividend"),
        further_reading=(
            "iShares / Invesco preferred ETF fact sheets",
            "Federal Reserve — bank capital and preferred treatment",
        ),
    )
)

register(
    DeepChapter(
        topic_id="infrastructure_income",
        title="Infrastructure Income",
        family="income",
        philosophy="""
Infrastructure income targets assets with long economic lives — pipelines, regulated
utilities, toll roads, airports, cell towers — often backed by contracts, regulated
returns, or inflation-linked tariffs. The philosophy favors predictable cash flows
over binary growth: you own the toll booth on essential services with high barriers
to entry. Listed infrastructure equities, MLPs, and some REITs provide liquid
access; unlisted funds offer illiquidity premium.

Political and regulatory risk is intrinsic: rate cases, environmental rules, and
permitting can change returns overnight. MLPs carry K-1 tax complexity; utilities
carry rate-base politics. The income is attractive when you underwrite regulatory
compact stability and inflation pass-through mechanisms — not when you treat
infrastructure as a bond substitute without reading the regulatory footnotes.


Infrastructure sits between utilities and private equity — long assets, visible cash flows, but political overlay on every tariff and permit. The income is often inflation-linked in theory; in practice, regulatory lag can delay pass-through for years.""".strip(),
        how_it_works="""
Segment: regulated utilities (stable dividends, rate base growth), midstream MLPs
(contracted fee volumes, commodity exposure varies), transport (tolls, ports),
and digital infrastructure (towers, fiber). Screen distribution coverage, leverage,
growth capex funding, and regulatory calendar.

MLPs: distinguish fee-based vs commodity-sensitive; check IDR structures (legacy)
and simplification trends. Utilities: model allowed ROE and rate base CAGR.
Inflation-linked revenue (CPI escalators in contracts) protects real income.

Portfolio mix balances yield vs growth capex pipelines; diversify geography and
regulatory regime. Monitor interest rates — infrastructure trades partly as
bond proxy.


Separate fee-based midstream from commodity-exposed pipes in modeling — same ‘infrastructure’ label, different risk. For MLPs, understand UBTI if held in IRAs. Track growth capex funding: equity issuance at discount destroys income growth; debt-funded capex needs coverage projections.

Read rate-case dockets for utilities and FERC filings for pipelines — regulatory text moves stocks before headlines. Model dividend growth as allowed ROE times rate-base growth minus funding drag.""".strip(),
        formulas=(
            _F(
                "Distribution coverage (MLP)",
                r"Coverage = \frac{Distributable\ Cash\ Flow}{Distributions}",
                "Analogous to dividend coverage — must exceed 1.0 sustainably.",
            ),
            _F(
                "Regulated utility rate base growth",
                r"RB_t = RB_{t-1} + CapEx_{allowed} - Depreciation",
                "Allowed capital investment drives future earnings and dividends.",
            ),
            _F(
                "Yield + growth total return heuristic",
                r"TR \approx Yield + g_{div}",
                "Infrastructure often valued as bond-plus-growth when regulated returns stable.",
            ),
            _F(
                "Dividend yield",
                r"Yield = \frac{D}{P}",
                "Headline infrastructure income — pair with coverage and regulatory outlook.",
                "investing.formulas.income.dividend_yield",
            ),
            _F(
                "Gordon Growth",
                r"P_0 = \frac{D_1}{r - g}",
                "Value stable dividend growers; g < r. Useful for utility dividend growth names.",
                "investing.formulas.income.gordon_growth_value",
            ),
        ),
        screens=(
            "Distribution/dividend coverage > 1.2×",
            "Net debt/EBITDA within sector guardrails",
            "Fee-based or regulated revenue ≥ 70% (midstream/utilities)",
            "Inflation escalation in contracts where inflation is thesis",
            "Clear regulatory path (rate case schedule, permitted returns)",
            "Tax form tolerance (K-1 vs 1099-DIV)",
        ),
        traps=(
            "Commodity volume risk in non-fee midstream",
            "Political windfall profits tax / rate clawback",
            "Overleveraged growth capex before cash flow inflects",
            "MLP simplification transactions diluting LP economics",
        ),
        catalysts=(
            "Rate case approval with favorable ROE",
            "Contract renewal at higher tariffs",
            "Inflation CPI true-up in toll/lease contracts",
            "Consolidation premium in fragmented midstream",
        ),
        fate_hook="Infrastructure yielders score via `investing.formulas.income` (`dividend_yield`, `high_yield_score`, `gordon_growth_value`) in `investing.integrate.book_rank_boost` when held as dividend equities.",
        related=("reit_income", "high_yield", "dividend_growth", "secular_growth", "bond_laddering"),
        further_reading=(
            "GLIO / Cohen & Steers — listed infrastructure",
            "EIA / FERC — pipeline and utility regulatory context",
        ),
    )
)
