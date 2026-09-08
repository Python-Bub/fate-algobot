"""Alternative / real assets / passive — deep chapters."""

from __future__ import annotations

from investing.knowledge import DeepChapter, FormulaSpec, register

_F = FormulaSpec

# --- alternative family ---

register(
    DeepChapter(
        topic_id="venture_capital",
        title="Venture Capital",
        family="alternative",
        philosophy="""
Venture capital funds early-stage private companies in exchange for equity,
targeting power-law outcomes: most investments fail or return capital, a few
return the fund many times over. The philosophy is portfolio construction
over single-name heroics — you cannot diligence your way to certainty in
pre-revenue startups; you diversify across stages, sectors, and vintages and
accept irreducible binary risk. Edge comes from deal flow, founder selection,
and post-investment value-add (hiring, follow-on reserves, exit navigation).

VC is illiquid for 7–12+ years. LPs earn premium for locking capital and
bearing mark-to-model volatility. Public market investors access VC themes
via growth equities or secondaries funds; direct VC requires accreditation
and patience.
""".strip(),
        how_it_works="""
Fund lifecycle: raise fund → deploy over 3–5 years → reserve for follow-ons
→ exit via IPO, M&A, or secondary sales → distribute proceeds. GPs earn
management fee (≈2%) plus carry (≈20% above hurdle). Due diligence covers
team, TAM, product, unit economics, cap table, and terms (liquidation prefs).

Stages: pre-seed, seed, Series A/B/C. Each stage trades risk for valuation.
Power-law means GPs double down on winners. DPI (distributions to paid-in)
matters more than paper TVPI. J-curve: early negative marks before exits.
""".strip(),
        formulas=(
            _F(
                "TVPI",
                r"TVPI = \frac{NAV + Distributions}{Paid\text{-}in\ Capital}",
                "Total value to paid-in; > 1× means paper + cash exceeds contributions.",
            ),
            _F(
                "DPI",
                r"DPI = \frac{Distributions}{Paid\text{-}in\ Capital}",
                "Cash actually returned — the ultimate scorecard.",
            ),
            _F(
                "Power-law intuition",
                r"Fund\ return \approx \sum_{few} mega\text{-}winners",
                "Top decile deals often dominate fund IRR.",
            ),
        ),
        screens=(
            "GP track record across vintages (not one lucky fund)",
            "Sector expertise matches portfolio thesis",
            "Fund size appropriate for stage (not $2B seed fund)",
            "Terms: reasonable fees, aligned carry, reserve policy",
            "Diversification across 20+ underlying bets for LP funds-of-funds",
        ),
        traps=(
            "Survivorship in GP marketing materials",
            "Illusion of liquidity via stale NAV marks",
            "Concentration in one vintage year",
            "Ignoring dilution in follow-on rounds",
        ),
        catalysts=("IPO window opens", "strategic M&A boom", "secondary market liquidity"),
        fate_hook="Knowledge chapter; public growth/early-stage names appear in rank pipeline via growth factors.",
        related=("seed_investing", "angel_investing", "private_equity", "innovation"),
        further_reading=("Sahlman — VC structure", "Peter Thiel — Zero to One"),
    )
)

register(
    DeepChapter(
        topic_id="private_equity",
        title="Private Equity",
        family="alternative",
        philosophy="""
Private equity buys mature (or maturing) companies, improves operations,
adds leverage judiciously, and exits at higher multiples or EBITDA. Returns
come from earnings growth, multiple expansion, and debt paydown — the
LBO algebra. Unlike VC's power law, PE targets more predictable cash flows
with operational levers. Edge is sourcing proprietary deals, sector
operating partners, and disciplined capital structure.

PE illiquidity and fees demand premium returns over public equities net of
all costs. For public investors, PE-like exposure appears in small-cap
value, spin-offs, and conglomerates with fixable operations.
""".strip(),
        how_it_works="""
Deal: acquire target (often auction or proprietary) → diligence QoE →
finance with equity + debt tranches → 3–5 year hold with EBITDA growth
(initiatives, add-ons, pricing) → exit IPO or strategic sale. Covenants
and interest coverage bind financial risk.

LPs commit to blind pools; pacing matters. Secondaries market allows
mid-life stake sales. Public PE firms (BX, KKR) offer liquid beta to
fund economics without direct LP commitment.
""".strip(),
        formulas=(
            _F(
                "LBO return bridge",
                r"MOIC \approx \frac{EBITDA_{exit}}{EBITDA_{entry}} \times \frac{Multiple_{exit}}{Multiple_{entry}} \times \frac{Debt_{paid}}{Equity_{in}}",
                "Three levers: growth, re-rating, deleveraging.",
            ),
            _F(
                "IRR vs MOIC",
                r"IRR = f(MOIC, hold\ period)",
                "High MOIC over 7 years may beat higher MOIC over 3 — time matters.",
            ),
            _F(
                "EV/EBITDA entry",
                r"\frac{EV}{EBITDA} \text{ at purchase vs exit}",
                "Multiple arbitrage central to PE underwriting.",
                "investing.formulas.analysis.ev_ebitda",
            ),
        ),
        screens=(
            "Entry multiple vs peer comps and history",
            "Debt/EBITDA sustainable in recession case",
            "Operational plan credible (not only financial engineering)",
            "GP co-invest and fee alignment",
            "Exit pathway visible (strategic buyers, IPO window)",
        ),
        traps=(
            "Leverage magnifying cyclical downturn",
            "Multiple compression on exit",
            "Dividend recap leaving thin equity cushion",
            "Fee drag on fund-of-funds layering",
        ),
        catalysts=("Credit market reopening", "strategic bidder auction", "IPO window"),
        fate_hook="Knowledge chapter; PE operational targets overlap turnaround and special situations in equity ranks.",
        related=("venture_capital", "leveraged_investing", "distressed_debt", "comps"),
        further_reading=("Bain Global PE Report", "Josh Kosman — The Buyout of America"),
    )
)

register(
    DeepChapter(
        topic_id="angel_investing",
        title="Angel Investing",
        family="alternative",
        philosophy="""
Angel investors deploy personal capital into seed and pre-seed startups,
often before institutional VC leads. Beyond money, angels offer network,
hiring help, and customer introductions. The philosophy mirrors VC power
law but with smaller checks, higher failure rates, and less diversification
unless the angel builds a portfolio deliberately. Most angels lose money on
average; edge is sector expertise and access to exceptional founders early.

Treat angel checks as venture bets sized to zero without emotional
attachment. Co-invest with reputable leads when possible; terms matter
(convertible notes, SAFEs, pro-rata rights).
""".strip(),
        how_it_works="""
Sourcing: accelerators, founder networks, syndicates (AngelList). Evaluate
team, problem, solution, early traction. Typical check $5K–$250K into
$1–5M rounds. Reserve capital for follow-on if company raises Series A.

Portfolio: 20–30+ bets for power-law exposure. Track ownership %, prefs
stack, and dilution. Exits rare for years; secondary sales emerging for
late private names. Tax: QSBS exclusion can shield gains if qualified.
""".strip(),
        formulas=(
            _F(
                "Ownership post-round",
                r"Own = \frac{Check}{Post\text{-}money\ valuation}",
                "Dilutes in every subsequent round without pro-rata.",
            ),
            _F(
                "Expected portfolio return",
                r"E[R] \approx p_{win} \times MOIC_{win} + (1-p_{win}) \times 0",
                "Low p_win requires very high MOIC on winners.",
            ),
        ),
        screens=(
            "Founder-market fit and full-time commitment",
            "Cap table not already over-diluted",
            "Lead investor or credible syndicate for next round",
            "Terms standard (not punitive SAFE)",
            "Personal portfolio ≤ 5–10% alts in angel sleeve",
        ),
        traps=(
            "Friends-and-family emotion overriding diligence",
            "No pro-rata → winner dilution",
            "Single-company concentration",
            "Ignoring QSBS and tax documentation",
        ),
        catalysts=("Series A lead commits", "revenue inflection", "acqui-hire exit"),
        fate_hook="Knowledge; public market analog via early-stage growth topic and innovation ranks.",
        related=("seed_investing", "venture_capital", "crowdfunding"),
        further_reading=("Jason Calacanis — Angel", "Kauffman Foundation angel studies"),
    )
)

register(
    DeepChapter(
        topic_id="seed_investing",
        title="Seed Investing",
        family="alternative",
        philosophy="""
Seed investing is the first institutional or semi-institutional capital
validating product-market fit after friends-and-family. Valuations are
narrative-driven; financial metrics are sparse. The bet is that a small
team can reach milestones (MVP, first revenue, retention) that unlock
Series A at a step-up. Failure mode is often not product but *financing
risk* — good companies die when follow-on capital dries up.

Seed philosophy emphasizes optionality: smaller valuations, more ownership,
and patience through pivots. Specialists focus on one vertical to pattern-
match winners faster than generalists.
""".strip(),
        how_it_works="""
Instruments: SAFEs, convertible notes, priced seed rounds. Milestones:
launch, $1M ARR, NRR > 100%, CAC payback < 18 months (SaaS heuristics).
Seed funds run portfolio approach; angels cluster via SPVs.

Due diligence lighter than Series B but must cover cap table, IP
assignment, and founder vesting. Track runway monthly. Public market
proxy: recent IPOs and high-growth small caps in same theme.
""".strip(),
        formulas=(
            _F(
                "Runway",
                r"Runway = \frac{Cash}{Monthly\ burn}",
                "Seed companies live or die by months of cash.",
            ),
            _F(
                "Step-up to Series A",
                r"Step\text{-}up = \frac{Pre_A}{Post_{seed}}",
                "Target 2–3×+ for seed investors on quality A round.",
            ),
        ),
        screens=(
            "18+ months runway post-round or path to profitability",
            "Founder vesting 4-year standard",
            "Market large enough for VC-scale outcome",
            "Clear milestone to Series A",
            "Clean IP and corporate structure",
        ),
        traps=(
            "Seed fund size too large for stage",
            "Pivot without cap table reset",
            "Vanity metrics (downloads without retention)",
            "Down round signaling death spiral",
        ),
        catalysts=("Series A term sheet", "enterprise pilot conversion", "regulatory approval"),
        fate_hook="Knowledge chapter; links to `early_stage` and `innovation` growth topics in catalog.",
        related=("angel_investing", "venture_capital", "early_stage"),
        further_reading=("Paul Graham essays", "Y Combinator startup library"),
    )
)

register(
    DeepChapter(
        topic_id="crowdfunding",
        title="Equity Crowdfunding",
        family="alternative",
        philosophy="""
Equity crowdfunding lets many small investors buy private company shares
through regulated platforms (Reg CF, Reg A+ in the US). It democratizes
access to startup equity once reserved for accredited investors. Philosophy:
broad participation with lower minimums, but information asymmetry and
illiquidity remain — the crowd is not a substitute for professional diligence.

Treat crowdfunding as venture exposure with extra friction: limited
secondary liquidity, marketing-heavy pitches, and adverse selection
(companies that could not raise from institutions). Size accordingly.
""".strip(),
        how_it_works="""
Issuer files offering on platform → marketing to retail → investors commit
online → funds held in escrow until minimum reached → securities issued
(usually common or SAFE). Caps apply per investor and per company annually.

Post-investment: updates via platform, no liquid market. Some Reg A+
names trade on OTC with thin volume. Compare terms to institutional round
if one exists concurrently.
""".strip(),
        formulas=(
            _F(
                "Investor cap (Reg CF concept)",
                r"Max\ invest = f(net\ worth,\ income)",
                "SEC limits protect retail from over-concentration.",
            ),
        ),
        screens=(
            "Audited or reviewed financials for larger offerings",
            "Use of funds specific and reasonable",
            "Management background verified",
            "Valuation vs comparable institutional deals",
            "Platform reputation and compliance history",
        ),
        traps=(
            "Marketing narrative without traction",
            "Hidden liquidation preferences",
            "Issuer bankruptcy — total loss",
            "No path to institutional follow-on",
        ),
        catalysts=("Reg A+ uplist", "institutional co-invest", "revenue milestone"),
        fate_hook="Knowledge chapter; no direct FATE pipeline integration.",
        related=("angel_investing", "seed_investing", "venture_capital"),
        further_reading=("SEC investor bulletin on crowdfunding", "Crowdfund Capital Advisors research"),
    )
)

register(
    DeepChapter(
        topic_id="collectibles",
        title="Collectibles Investing",
        family="alternative",
        philosophy="""
Collectibles — sports cards, memorabilia, comics, vintage toys — derive
value from scarcity, condition, provenance, and cultural demand, not
discounted cash flows. The philosophy is passion plus scarcity economics:
markets are opaque, illiquid, and sentiment-driven. Authentication is
everything; a graded PSA 10 can trade at multiples of raw copies. Long-run
returns cluster in iconic assets with enduring fan bases.

Collectibles diversify poorly against stocks in crises but offer
uncorrelated joy and potential inflation hedge in trophy assets.
Transaction costs (auction fees, grading, insurance) materially reduce
realized returns.
""".strip(),
        how_it_works="""
Research comparable sales (Goldin, PWCC, eBay completed). Grade via PSA/BGS
for cards; condition drives price stairs. Storage: climate control, theft
prevention. Liquidity: sell at auction with 10–20% fees; private sales
faster but less price discovery.

Fractional platforms tokenize shares in high-end pieces — liquidity illusion
until exit. Tax: collectibles may face higher capital gains rates in some
jurisdictions. Diversify across categories to reduce taste risk.
""".strip(),
        formulas=(
            _F(
                "All-in cost basis",
                r"Basis = Purchase + Grading + Shipping + Insurance + Fees",
                "True return must net all friction.",
            ),
            _F(
                "CAGR (realized)",
                r"CAGR = \left(\frac{Net\ proceeds}{Basis}\right)^{1/t} - 1",
                "Use net proceeds after auction fees.",
            ),
        ),
        screens=(
            "Population report — true scarcity",
            "Authentication from tier-1 grader",
            "Comparable sales in last 90 days",
            "Storage and insurance budgeted",
            "Liquidity plan (auction vs private)",
        ),
        traps=(
            "Counterfeits and altered cards",
            "Fad genres (speculative modern prints)",
            "Illiquid — forced sale at discount",
            "Fractional platform governance risk",
        ),
        catalysts=("Hall of fame induction", "anniversary nostalgia wave", "documentary/media hype"),
        fate_hook="Knowledge chapter; no equity rank wiring.",
        related=("fine_art", "rare_coins", "watches"),
        further_reading=("McNair — collectibles market reports", "PWCC market indices"),
    )
)

register(
    DeepChapter(
        topic_id="fine_art",
        title="Fine Art Investing",
        family="alternative",
        philosophy="""
Fine art treats paintings, sculpture, and works on paper as stores of value
with aesthetic and cultural premium. Unlike securities, there is no earnings
yield — only collector demand, museum retrospectives, and wealth effects.
Masterworks by canonical artists (Picasso, Basquiat, contemporary blue
chips) appreciate slowly with high friction. The philosophy balances
enjoyment of ownership with realistic return expectations net of costs.

Art lags equities in liquidity and transparency. Masterworks and fractional
platforms broaden access but add layer risk. Specialist dealers and
auction houses remain price setters.
""".strip(),
        how_it_works="""
Channels: auction (Christie's, Sotheby's), galleries, private treaty, art
funds. Due diligence: provenance, condition reports, authenticity committees
for certain artists. Storage: museum-grade climate, insurance at fair
value. Sell timing: season (spring/fall auctions), macro wealth cycles.

Indices (Mei Moses / Art Market Research) track repeat sales — selection
bias toward winners. Contemporary art more volatile than Old Masters.
""".strip(),
        formulas=(
            _F(
                "Hammer price vs all-in",
                r"All\text{-}in = Hammer \times (1 + buyer's\ premium) + shipping + insurance",
                "Buyer's premium often 20–25% above hammer.",
            ),
            _F(
                "Repeat-sale index (concept)",
                r"Return = \frac{P_{t_2}}{P_{t_1}} - 1 \text{ for matched lots}",
                "Tracks same work resold — survivorship toward appreciating pieces.",
            ),
        ),
        screens=(
            "Provenance chain complete",
            "Condition report acceptable",
            "Artist market depth (recent comparable sales)",
            "Insurance and storage budgeted",
            "Authenticity guaranteed or expert consensus",
        ),
        traps=(
            "Forgery and attribution disputes",
            "Illiquid — no bid at reserve",
            "Fashion cycle in contemporary artists",
            "High carry costs eroding decades-long holds",
        ),
        catalysts=("Major retrospective", "record auction for same artist", "wealth boom in buyer regions"),
        fate_hook="Knowledge chapter.",
        related=("collectibles", "wine", "real_estate"),
        further_reading=("Thierry Ehrmann — Artprice analytics", "McAndrew — Art Market Report"),
    )
)

register(
    DeepChapter(
        topic_id="wine",
        title="Wine Investing",
        family="alternative",
        philosophy="""
Investment-grade wine — classified Bordeaux, Burgundy grand crus, trophy
Napa — appreciates as supply is consumed and critic scores fix reputations.
The asset is physical, fragile, and storage-dependent. Philosophy: scarcity
plus provenance plus critic validation (Parker, Wine Spectator). Unlike
financial assets, bottles can spoil, break, or counterfeit.

Wine offers enjoyment optionality: drink the dividend. Pure investment
requires professional storage (bonded warehouse), perfect provenance, and
patience through vintage cycles. Returns are lumpy: great vintages re-rate
on release; mediocre years languish for decades. Currency matters — Bordeaux
is euro-denominated demand with global buyers.
""".strip(),
        how_it_works="""
Buy en primeur (futures) or mature bottles from reputable merchants.
Store in bonded facility for tax and insurance efficiency. Track Liv-ex
100 index and regional sub-indices. Sell via merchants, auctions, or
exchange platforms.

Due diligence: vintage quality, producer reputation, fill level, label
condition, storage history. Fraud exists — buy from chain-of-custody sources.
Build a case list diversified across regions (Bordeaux left bank, Burgundy,
Champagne, Napa) so weather shocks do not wipe the sleeve. Hold 7–10 years
minimum; transaction costs on entry and exit often consume 15–25% round trip.
Monitor critic re-scores and drinking windows — maturity peaks can coincide
with best exit liquidity.
""".strip(),
        formulas=(
            _F(
                "Liv-ex return",
                r"R = \frac{Index_t}{Index_{t-1}} - 1",
                "Benchmark for investment wine basket.",
            ),
            _F(
                "Carry cost",
                r"Annual\ carry = storage + insurance + financing",
                "Reduces net CAGR over hold period.",
            ),
        ),
        screens=(
            "Investment-grade producer and vintage",
            "Bonded storage with insurance",
            "Ullage and label condition documented",
            "Purchase from reputable merchant",
            "Liquidity: active secondary market for label",
        ),
        traps=(
            "Heat-damaged stock",
            "Counterfeit labels in blue-chip names",
            "Changing taste (Parker era vs lower alcohol trend)",
            "Currency and tariff on cross-border trade",
        ),
        catalysts=("Perfect critic score", "poor harvest raising prior vintage scarcity", "Asia demand wave"),
        fate_hook="Knowledge chapter.",
        related=("fine_art", "collectibles", "inflation"),
        further_reading=("Liv-ex market analysis", "Wine Spectator investment guides"),
    )
)

register(
    DeepChapter(
        topic_id="watches",
        title="Luxury Watch Investing",
        family="alternative",
        philosophy="""
Luxury watch investing targets iconic references — Rolex Daytona, Patek
Nautilus, Audemars Royal Oak — where brand heat, waitlists, and limited
production create scarcity beyond precious metal content. The philosophy
combines craftsmanship appreciation with sneaker-like hype cycles. Steel
sport models often outperform gold because aspirational demand exceeds
supply. Condition, box/papers, and service history drive liquidity.

Watches are wearable collateral — enjoyment plus potential appreciation.
But fashion shifts: today's unicorn can cool when brand floods gray market.
""".strip(),
        how_it_works="""
Buy authorized dealer (MSRP lottery) or secondary (Chrono24, auctions).
Track comparable sales; beware frankenwatches and aftermarket parts.
Service at manufacturer or certified center preserves value. Store with
insurance when not worn.

Vintage market requires scholarship: dial variants, movement calibers,
provenance. Modern investable pieces often flip above retail immediately
then mean-revert when supply normalizes.
""".strip(),
        formulas=(
            _F(
                "Secondary premium",
                r"Premium = \frac{P_{secondary}}{P_{retail}} - 1",
                "High premium signals hype; compression risk on normalization.",
            ),
        ),
        screens=(
            "Reference with documented secondary liquidity",
            "Complete set (box, papers, links)",
            "Manufacturer or authorized service history",
            "Authenticate movement and serial",
            "Insurance at replacement value",
        ),
        traps=(
            "Aftermarket dial/hand swaps",
            "Gray market warranty gaps",
            "Hype cycle peak buying",
            "Brand policy change increasing retail supply",
        ),
        catalysts=("Discontinuation rumor", "celebrity association", "limited edition release"),
        fate_hook="Knowledge chapter.",
        related=("collectibles", "precious_metals"),
        further_reading=("WatchCharts indices", "Hodinkee market commentary"),
    )
)

register(
    DeepChapter(
        topic_id="rare_coins",
        title="Rare Coin Investing",
        family="alternative",
        philosophy="""
Rare coins blend numismatic history, grade, mintage, and precious metal
content. A 1909-S VDB Lincoln cent in MS67 trades on scarcity and condition,
not melt value alone. Philosophy: study series, buy quality, hold long.
Third-party grading (PCGS, NGC) standardized markets but dealer spreads
still wide. Gold and silver bullion coins (Eagles, Maple Leafs) are
commodity-linked; true numismatics are collector markets.

Coins offer inflation-linked metal floor with optionality on rarity premium.
Education prevents overpaying for common coins in fancy slabs.
""".strip(),
        how_it_works="""
Learn series key dates, population reports, and price guides (Greysheet,
CDN). Buy from reputable dealers or major auctions (Heritage, Stack's).
Grade determines price stairs — jump from MS64 to MS65 can be nonlinear.

Storage: safes, deposit boxes; insurance. Liquidity: dealer buyback below
retail; auction for trophy pieces. Tax: collectibles rate may apply.
""".strip(),
        formulas=(
            _F(
                "Numismatic premium",
                r"Premium = \frac{Coin\ price}{Melt\ value} - 1",
                "Separates collector value from metal content.",
            ),
            _F(
                "Population scarcity",
                r"Scarcity \propto \frac{1}{PCGS/NGC\ count\ at\ grade}",
                "Fewer graded examples at top grade supports price.",
            ),
        ),
        screens=(
            "PCGS/NGC graded with CAC sticker optional quality signal",
            "Key date or low mintage verified",
            "Greysheet/CDN bid-ask reasonable",
            "Not cleaned or damaged",
            "Purchase from Authorized Purchaser or major auction",
        ),
        traps=(
            "Common coin in high grade still common",
            "Counterfeit ancients and key dates",
            "Wide dealer spread on resale",
            "Spot metal crash hurting bullion-heavy coins",
        ),
        catalysts=("Record auction for series", "gold/silver rally lifting floor", "anniversary demand"),
        fate_hook="Knowledge chapter; `precious_metals` topic for bullion overlap.",
        related=("collectibles", "precious_metals", "gold"),
        further_reading=("Red Book — U.S. coin guide", "PCGS CoinFacts"),
    )
)

# --- real_assets family ---

register(
    DeepChapter(
        topic_id="real_estate",
        title="Real Estate Investing",
        family="real_assets",
        philosophy="""
Direct real estate ownership generates rental income and potential
appreciation while offering inflation-linked cash flows and tangible
collateral. Unlike stocks, properties are illiquid, lumpy, and operationally
intensive — tenants, capex, zoning, and leverage dominate outcomes. Philosophy:
location and entry cap rate set the foundation; operations and financing
determine whether you compound or bleed.

Real estate diversifies portfolios with low correlation to equities when
leverage is moderate. Public access via REITs trades liquidity for tax
complexity of direct ownership.
""".strip(),
        how_it_works="""
Analyze market rent, vacancy, expenses, and capex → derive NOI → cap rate
= NOI / price → compare to cost of debt → DSCR for lender comfort. Value-add:
renovate to raise rents; core: stable yield; opportunistic: development.

Financing: fixed-rate mortgages lock cost; floating adds risk. Hold period
5–10+ years typical. Exit: sell, 1031 exchange (US), or refinance and
distribute. REITs offer sector tilts without landlord labor.
""".strip(),
        formulas=(
            _F(
                "Cap rate",
                r"Cap = \frac{NOI}{Property\ Value}",
                "Unlevered yield; lower cap = higher price per income dollar.",
            ),
            _F(
                "NOI",
                r"NOI = Gross\ Rent - Operating\ Expenses",
                "Before debt service and taxes.",
            ),
            _F(
                "Cash-on-cash return",
                r"CoC = \frac{Annual\ Cash\ Flow\ after\ debt}{Equity\ invested}",
                "Levered yield to equity investors.",
            ),
            _F(
                "DSCR",
                r"DSCR = \frac{NOI}{Debt\ Service}",
                "Lenders often require > 1.2–1.25.",
            ),
        ),
        screens=(
            "Cap rate vs market comps and debt cost spread positive",
            "Vacancy and rent growth assumptions conservative",
            "Inspection and environmental clean",
            "DSCR comfortable in stress case",
            "Property management plan (self vs pro)",
        ),
        traps=(
            "Over-leverage in rising rate environment",
            "Deferred maintenance capex surprise",
            "Rent control / regulatory shock",
            "Illiquidity forcing distressed sale",
        ),
        catalysts=("Rate cuts compressing cap rates", "zoning up-density", "infrastructure improving location"),
        fate_hook="REIT income topic and sector ranks cover listed real estate; direct RE knowledge contextual.",
        related=("reit_income", "infrastructure_assets", "inflation", "farmland"),
        further_reading=("Kiyosaki — not recommended; prefer Brueggeman & Fisher", "NAREIT research"),
    )
)

register(
    DeepChapter(
        topic_id="farmland",
        title="Farmland Investing",
        family="real_assets",
        philosophy="""
Farmland captures agricultural productivity and finite land supply with
food-demand tailwinds. Returns blend rental/crop share income and land
appreciation. Inflation-linked food prices and biofuel demand support
long-run thesis. Complexity: weather, commodity prices, water rights,
tenant quality, and regional politics (California water, Midwest ethanol).

Institutional access via farmland REITs (FPI), funds (Gladstone), or direct
purchase. Low correlation to equities historically; illiquid direct stakes.
""".strip(),
        how_it_works="""
Evaluate soil quality, water access, drainage, and crop suitability. Lease
to operator (cash rent vs sharecrop). Track corn/soy/wheat futures for
income proxy. Land values follow farm net income and interest rates.

Due diligence: title, easements, environmental, property taxes. Diversify
geography and crop type. Climate change shifts productive regions over decades.
""".strip(),
        formulas=(
            _F(
                "Farmland yield",
                r"Yield = \frac{Annual\ rent}{Land\ price}",
                "Analogous to cap rate.",
            ),
            _F(
                "Farm net income link",
                r"Land\ value \propto NI_{farm} / cap",
                "Commodity prices and yields drive NOI.",
            ),
        ),
        screens=(
            "Water rights secure and sustainable",
            "Tenant credit and farming track record",
            "Soil tests and productivity index",
            "Yield spread over local risk-free rate",
            "Diversification across regions",
        ),
        traps=(
            "Drought and climate stress",
            "Commodity price collapse",
            "Illiquid — no buyer at appraised value",
            "Regulatory restriction on water or chemicals",
        ),
        catalysts=("Food price inflation", "institutional allocation trend", "biofuel policy"),
        fate_hook="Knowledge chapter; agriculture sector in equity pipeline for agribusiness exposure.",
        related=("commodity_macro", "real_estate", "inflation", "timberland"),
        further_reading=("NCREIF Farmland Index", "USDA land value reports"),
    )
)

register(
    DeepChapter(
        topic_id="timberland",
        title="Timberland Investing",
        family="real_assets",
        philosophy="""
Timberland combines biological tree growth (volume accrues ~2–7% annually)
with optionality to harvest when lumber prices peak. You earn while you wait
— trees grow regardless of S&P prints. Inflation hedge and diversification
benefits attract institutions. Requires long horizons (10–20+ years) and
expertise in silviculture, species mix, and local sawmill markets.

TIMOs and REITs (PCH, RYN) offer liquid proxies; direct ownership suits
patient capital with operational partners.
""".strip(),
        how_it_works="""
Species (pine, Douglas fir, hardwoods) and age class determine harvest
schedule. Thinning generates interim cash; final harvest is lump sum.
Prices tie to housing starts, repair/remodel, and export demand (China).

Carbon credits emerging revenue stream. Fire, pest, and storm risk require
insurance and geographic diversification. Appraisals lag spot lumber futures.
""".strip(),
        formulas=(
            _F(
                "Biological growth",
                r"Volume_{t+1} \approx Volume_t \times (1 + g_{bio})",
                "Trees add tonnage annually — carry return.",
            ),
            _F(
                "Timberland total return",
                r"R = R_{income} + R_{appreciation} + R_{biological}",
                "Three components in NCREIF timber index.",
            ),
        ),
        screens=(
            "Site index and stocking levels healthy",
            "Road access and mill proximity",
            "Species matched to regional demand",
            "Carbon opportunity optional upside",
            "Insurance for catastrophic fire",
        ),
        traps=(
            "Housing downturn delaying harvest at carrying cost",
            "Pest/disease (pine beetle)",
            "Illiquidity of direct parcels",
            "Environmental regulation on harvesting",
        ),
        catalysts=("Housing starts rebound", "lumber supply shock", "carbon credit pricing"),
        fate_hook="Knowledge chapter; materials sector partial proxy in equities.",
        related=("farmland", "real_estate", "infrastructure_assets"),
        further_reading=("NCREIF Timberland Index", "Weyerhaeuser investor education"),
    )
)

register(
    DeepChapter(
        topic_id="infrastructure_assets",
        title="Infrastructure Real Assets",
        family="real_assets",
        philosophy="""
Infrastructure — toll roads, airports, regulated utilities, pipelines,
fiber networks — generates long-lived cash flows often inflation-linked or
regulated. Philosophy: bond-like equity with GDP-linked upside. Listed
infrastructure (MLPs, infra funds) offers liquidity; direct/project finance
offers yield but construction and political risk.

Assets sit between pure real estate and utilities: contracted revenues,
high barriers to entry, ESG scrutiny on fossil pipelines vs renewables.
Infrastructure often trades on yield spread to Treasuries — when rates
rise, prices fall even when contracted cash flows are stable. Match horizon
to concession life: a 30-year asset in a 5-year mandate is a mismatch.
""".strip(),
        how_it_works="""
Models: availability-based (fixed payments) vs demand-based (volume risk).
Underwrite concession length, tariff escalators, maintenance capex, and
refinancing. Listed proxies: Brookfield Infrastructure, utility hybrids.

Political risk: renegotiation of tolls, permit delays. Green transition
favors grid, renewables transmission, data-center power. MLPs pass through
K-1 tax complexity. Stress-test volume declines on toll roads and throughput
on pipelines. Read regulatory filings for allowed ROE and rate-case calendars.
Diversify across regulated utilities, user-pay transport, and digital infra
(cell towers, fiber) so one policy shock does not dominate. Compare dividend
yield plus growth to corporate bond yields in same rating bucket.
""".strip(),
        formulas=(
            _F(
                "Project IRR",
                r"0 = \sum_t \frac{CF_t}{(1+IRR)^t}",
                "Lifecycle cash flows including construction and ops.",
            ),
            _F(
                "Dividend yield (listed)",
                r"Yield = \frac{Annual\ DPS}{Price}",
                "Income component for infra equities.",
            ),
            _F(
                "Inflation linker",
                r"Tariff_t = Tariff_0 \times (1 + CPI)^t",
                "Contractual escalators protect real returns.",
            ),
        ),
        screens=(
            "Concession or regulation length ≥ 15 years",
            "Maintenance capex funded",
            "Political jurisdiction stable",
            "ESG alignment with mandate",
            "Debt/EBITDA within covenants",
        ),
        traps=(
            "Demand risk on greenfield toll roads",
            "Regulatory clawback",
            "MLP tax complexity for holders",
            "Construction overrun on project finance",
        ),
        catalysts=("Rate cut re-rating yield stocks", "infrastructure bill", "privatization wave"),
        fate_hook="`infrastructure_income` income topic; utilities/industrials sector ranks.",
        related=("infrastructure_income", "utilities", "real_estate"),
        further_reading=("Brookfield infrastructure white papers", "McKinsey global infrastructure outlook"),
    )
)

register(
    DeepChapter(
        topic_id="precious_metals",
        title="Precious Metals",
        family="real_assets",
        philosophy="""
Gold and silver serve as monetary metals and crisis diversifiers without
cash-flow yield. Gold often rises when real interest rates fall, USD weakens,
or geopolitical risk spikes — it is insurance, not a growth stock. Silver
adds industrial demand (solar, electronics), making it more volatile and
cyclical. Philosophy: size as portfolio ballast (often 5–10% debate), not
core wealth driver.

Physical bullion, ETFs (GLD), miners, and streaming companies offer
different risk profiles. Miners embed operational leverage to spot prices.
""".strip(),
        how_it_works="""
Track real rates, USD index, central-bank purchases, and ETF flows. Gold
futures curve usually mild contango; storage costs for physical. Miners:
AISC (all-in sustaining cost) vs spot determines margin expansion.

Silver: industrial demand ~50% of use — reflation helps; recession hurts.
Platinum/palladium more industrial. Allocate by vehicle: physical for tail
hedge, ETFs for liquidity, miners for leveraged beta.
""".strip(),
        formulas=(
            _F(
                "Real rate link",
                r"Gold \uparrow \text{ when } r_{real} \downarrow,\quad r_{real} = r_{nominal} - \pi^e",
                "Opportunity cost framework.",
            ),
            _F(
                "Miner leverage",
                r"EBITDA_{miner} \propto (Spot - AISC) \times Volume",
                "Spot rise expands margins nonlinearly.",
            ),
        ),
        screens=(
            "Allocation size matches insurance goal",
            "Vehicle liquidity needs (physical vs ETF)",
            "Miner balance sheet and AISC vs spot",
            "Storage/insurance for physical",
            "Tax treatment of collectibles vs ETFs",
        ),
        traps=(
            "No yield — drag in long bull equity markets",
            "Miner operational blow-ups despite high gold",
            "Physical storage and counterfeit risk",
            "Silver industrial slump in recession",
        ),
        catalysts=("Fed pivot lower real rates", "geopolitical shock", "central bank buying"),
        fate_hook="Gold/oil asset classes in catalog; commodity macro and inflation topics contextual.",
        related=("inflation", "commodity_macro", "gold", "rare_coins"),
        further_reading=("Erb & Harvey — gold return drivers", "World Gold Council research"),
    )
)

# --- passive family ---

register(
    DeepChapter(
        topic_id="index_investing",
        title="Index Investing",
        family="passive",
        philosophy="""
Index investing owns the market basket — typically cap-weighted — to capture
average returns at minimal cost. The philosophical wager is humility: you
unlikely beat the aggregate after fees and taxes over decades. Broad
diversification, low turnover, and transparent rules remove manager risk
and behavioral churn. Jack Bogle's insight: gross return minus cost equals
net return; minimize cost and let capitalism compound.

Cap-weight concentrates in today's largest companies — feature and bug.
It automatically tilts to winners but may overweight bubbles at peaks.
""".strip(),
        how_it_works="""
Buy mutual fund or ETF tracking S&P 500, total market, or global index.
Reinvest dividends. Rebalance only when personal allocation drifts. Compare
expense ratios (1–3 bps for leaders). Tax-loss harvest in taxable accounts
with similar index pairs.

Alternatives: equal-weight, fundamental-weight tweak concentration. FATE
uses index-like universe for ranks but active security selection on top.
""".strip(),
        formulas=(
            _F(
                "Index return",
                r"R_p \approx \sum_i w_i R_i, \quad w_i = \frac{MC_i}{\sum MC}",
                "Cap-weight return is large-stock dominated.",
            ),
            _F(
                "Tracking error",
                r"TE = \sigma(R_{fund} - R_{index})",
                "Should be tiny for good index funds.",
            ),
        ),
        screens=(
            "Expense ratio < 10 bps for core US equity",
            "Tracking difference vs index minimal over 3+ years",
            "Fund AUM and liquidity adequate",
            "Tax efficiency (ETF vs mutual fund in taxable)",
            "Broad enough index for diversification goal",
        ),
        traps=(
            "Cap-weight mega-concentration risk",
            "Hidden costs in spread/tracking",
            "Home country bias ignoring global index",
            "Panic selling at bottoms defeating purpose",
        ),
        catalysts=("Long equity risk premium accruing", "fee compression benefiting net returns"),
        fate_hook="Live `analytics/strategy_registry.py` index strategy; rank universe spans broad equities.",
        related=("etf_investing", "buy_and_hold", "lazy_portfolios", "core_satellite"),
        further_reading=("Bogle — Common Sense on Mutual Funds", "SPIVA scorecards"),
    )
)

register(
    DeepChapter(
        topic_id="etf_investing",
        title="ETF Investing",
        family="passive",
        philosophy="""
ETFs are index funds that trade intraday like stocks — transparency,
tax efficiency, and granular asset-class access in one ticker. Philosophy:
same humility as indexing with added flexibility for rebalancing, tax-loss
harvesting, and tactical tilts without mutual fund cutoff times. The ETF
wrapper is a tool; the underlying strategy (cap-weight, factor, sector)
defines outcomes.

Watch structure: physical replication vs swaps, securities lending revenue,
and premium/discount to NAV in stressed markets.
""".strip(),
        how_it_works="""
Choose ETF by index, cost, AUM, spread, and issuer quality. Place limit
orders; avoid market open volatility. Use sector, factor, bond, commodity
ETFs to build lazy or core-satellite portfolios. Compare capital gains
distributions — ETFs generally more tax-efficient than mutual funds.

International: watch withholding tax on dividends. Leveraged/inverse ETFs
are tactical only (see inverse_etfs chapter).
""".strip(),
        formulas=(
            _F(
                "Premium/discount",
                r"Prem = \frac{Price_{ETF} - NAV}{NAV}",
                "Arbitrage keeps most ETFs near NAV; stress widens gaps.",
            ),
            _F(
                "Total cost of ownership",
                r"TCO = Expense + Spread + Tracking\ slippage",
                "All-in cost beyond headline ER.",
            ),
        ),
        screens=(
            "AUM > $500M for liquidity (rule of thumb)",
            "Bid-ask spread tight vs trade size",
            "Expense ratio competitive for index tracked",
            "Creation/redemption mechanism clear",
            "Dividend yield and tax docs understood",
        ),
        traps=(
            "Thin ETF wide spreads eating edge",
            "Synthetic ETF counterparty risk",
            "Wrong index (not total market when intended)",
            "Leveraged ETF long hold",
        ),
        catalysts=("New low-cost ETF launch", "tax-loss harvest pair availability"),
        fate_hook="ETF asset class live in catalog; strategy registry supports passive implementations.",
        related=("index_investing", "lazy_portfolios", "factor", "smart_beta"),
        further_reading=("ETF.com education", "BlackRock/iShares methodology guides"),
    )
)

register(
    DeepChapter(
        topic_id="dca",
        title="Dollar-Cost Averaging",
        family="passive",
        philosophy="""
Dollar-cost averaging invests fixed dollar amounts on a schedule regardless
of price — buying more shares when cheap, fewer when expensive. It does not
maximize expected return vs lump sum (markets rise on average), but it
minimizes regret and timing anxiety. Philosophy: behavioral discipline and
consistent savings beat waiting for the perfect bottom that never feels safe.

DCA is a plan for contributions, not a excuse to never deploy a windfall
when allocation targets are clearly underweight.
""".strip(),
        how_it_works="""
Automate transfers to brokerage; buy target fund monthly/quarterly. Works
best for recurring income (401k, paycheck). Compare average cost basis to
lump-sum alternative mentally — accept modest statistical drag for smoother
psychology.

In volatile markets DCA accidentally buys dips; in straight rallies lump sum
wins. Combine with asset allocation targets: DCA into underweight sleeves.
""".strip(),
        formulas=(
            _F(
                "Average cost basis",
                r"\bar{P} = \frac{\sum_j D_j}{\sum_j Shares_j}",
                "Dollar-weighted average purchase price.",
            ),
            _F(
                "Shares per period",
                r"Shares_t = \frac{D}{P_t}",
                "Fixed D buys more units when price low.",
            ),
        ),
        screens=(
            "Automated schedule enforced",
            "Low-cost fund/ETF as DCA vehicle",
            "Allocation drift reviewed annually",
            "Windfall policy defined (lump vs DCA)",
            "Emergency fund separate — don't DCA rent money",
        ),
        traps=(
            "DCA into single speculative stock",
            "Stopping contributions at bottoms",
            "Ignoring fees on tiny frequent trades",
            "Perpetual DCA of cash hoard without target allocation",
        ),
        catalysts=("Paycheck rhythm", "bonus split into tranches by policy"),
        fate_hook="Knowledge; fortress rebalancing can automate systematic deployment.",
        related=("buy_and_hold", "index_investing", "target_date"),
        further_reading=("Vanguard lump sum vs DCA study", "Bernstein — behavioral investing"),
    )
)

register(
    DeepChapter(
        topic_id="buy_and_hold",
        title="Buy and Hold",
        family="passive",
        philosophy="""
Buy and hold maintains positions through volatility, trusting long-run
economic growth and compounding. Minimizes taxes, trading costs, and
behavioral errors from reacting to headlines. Philosophy: time in market
beats timing market — but only if holdings are diversified, low-cost, and
aligned with risk tolerance. Holding a concentrated loser forever is not
virtue; holding a broad index through crashes is.

Requires emotional preparation for 50% drawdowns without selling at the trough.
""".strip(),
        how_it_works="""
Select core index or quality portfolio → purchase → reinvest dividends →
ignore daily noise → rebalance only on calendar or allocation bands. Tax
advantage: long-term capital gains rates, deferred compounding.

Contrast with passive index only: buy-and-hold can apply to individual
compounders if conviction deep. Document thesis so you know when to sell
(moat broken) vs when to hold (routine correction).
""".strip(),
        formulas=(
            _F(
                "Compound growth",
                r"V_T = V_0 (1 + r)^T",
                "Long horizon magnifies steady returns.",
            ),
            _F(
                "Real return",
                r"R_{real} \approx R_{nominal} - \pi",
                "Purchasing power matters over decades.",
            ),
        ),
        screens=(
            "Low-cost diversified core",
            "Risk tolerance matches equity allocation",
            "Written investment policy statement",
            "Tax-advantaged accounts for high-turnover avoided",
            "Estate plan for long holds",
        ),
        traps=(
            "Holding single stock to zero",
            "No rebalance → equity drift too high pre-retirement",
            "Panic sell once per cycle destroys returns",
            "Ignoring fundamental thesis change",
        ),
        catalysts=("Decades of earnings growth", "dividend reinvestment"),
        fate_hook="Fortress and strategy registry support low-turnover implementations.",
        related=("index_investing", "dca", "lazy_portfolios", "compounders"),
        further_reading=("Jeremy Siegel — Stocks for the Long Run", "Malkiel — Random Walk"),
    )
)

register(
    DeepChapter(
        topic_id="lazy_portfolios",
        title="Lazy Portfolios",
        family="passive",
        philosophy="""
Lazy portfolios use a handful of low-cost index funds, rebalance occasionally,
and otherwise leave investments alone. Philosophy: complexity is often
negative alpha — more funds, more timing, more fees, more mistakes. Classic
variants: three-fund (US, international, bonds), permanent portfolio
(stocks, bonds, gold, cash), Rick Ferri's core-four. Simplicity sustains
behavior through boring years.

Accept lazy does not mean careless: initial asset allocation must match goals,
and occasional rebalance prevents drift.
""".strip(),
        how_it_works="""
Pick allocation (e.g. 60/40 or age-based). Implement with 2–4 ETFs. Set
annual or 5% band rebalance rule. Automate contributions. Ignore hot tips.

Compare to target-date funds — lazy DIY saves a few bps but requires discipline.
Tax location: bonds in tax-deferred, equities in taxable for loss harvesting.
""".strip(),
        formulas=(
            _F(
                "Rebalance band",
                r"Trade\ if\ |w_i - w_i^*| > band",
                "e.g. 5% absolute drift from policy weight.",
            ),
            _F(
                "Portfolio return",
                r"R_p = \sum_i w_i R_i",
                "Weighted sum of sleeve returns.",
            ),
        ),
        screens=(
            "≤ 5 funds total for true simplicity",
            "Weighted average ER < 10 bps",
            "IPS documents target weights",
            "Rebalance calendar in calendar app",
            "Emergency fund outside portfolio",
        ),
        traps=(
            "Adding satellite funds until not lazy",
            "Never rebalancing after equity rally",
            "Wrong bond duration for horizon",
            "Home bias skipping international sleeve",
        ),
        catalysts=("Annual rebalance date", "large contribution triggering allocation check"),
        fate_hook="Knowledge; strategic_aa formulas inform policy weights for lazy implementations.",
        related=("core_satellite", "index_investing", "target_date", "strategic_aa"),
        further_reading=("Rick Ferri — All About Asset Allocation", "Bogleheads wiki lazy portfolios"),
    )
)

register(
    DeepChapter(
        topic_id="target_date",
        title="Target-Date Funds",
        family="passive",
        philosophy="""
Target-date funds (TDFs) glide from aggressive to conservative allocation
as a retirement date approaches — one fund encapsulates strategic asset
allocation and rebalancing. Philosophy: set-and-forget for 401(k) investors
who will not rebalance manually. The glidepath is a bet on reduced human
capital (job income) and shorter horizon near retirement demanding less equity risk.

Not all glidepaths identical — compare "to" vs "through" retirement and
underlying fund fees (often fund-of-funds).
""".strip(),
        how_it_works="""
Pick vintage year nearest expected retirement. Fund holds stock/bond mix
that shifts automatically — e.g. 90/10 at 30 years out, 50/50 at retirement.
Employer plan default for many participants. Evaluate expense ratio, underlying
index vs active, and glidepath steepness.

Near retirement, TDF becomes conservative — sequence-of-returns risk mitigated
but inflation longevity risk rises. Some hold post-retirement for simplicity.
""".strip(),
        formulas=(
            _F(
                "Glidepath equity weight",
                r"w_{equity}(T) = w_0 - k \cdot (Year - Year_0)",
                "Linear or curved decline toward retirement.",
            ),
            _F(
                "Sequence risk",
                r"Retirement\ wealth\ sensitive\ to\ returns\ in\ years\ just\ before/after\ retire",
                "Motivation for de-risking glidepath.",
            ),
        ),
        screens=(
            "Expense ratio < 0.20% if possible in plan",
            "Glidepath matches risk tolerance (aggressive vs conservative vintage)",
            "Underlying diversification US/intl/bonds",
            "No excessive company stock overlap",
            "Understand 'to' vs 'through' design",
        ),
        traps=(
            "Multiple TDF vintages mixed unintentionally",
            "Too conservative too early — longevity risk",
            "High-fee active TDF underperforming",
            "Assuming TDF fits pre-retirement taxable goals",
        ),
        catalysts=("Automatic payroll contributions", "glidepath shift reducing equity annually"),
        fate_hook="Knowledge; strategic_aa and portfolio_optimization inform glidepath design.",
        related=("lazy_portfolios", "strategic_aa", "dca", "buy_and_hold"),
        further_reading=("SEC target-date disclosure guide", "Morningstar TDF landscape reports"),
    )
)

register(
    DeepChapter(
        topic_id="core_satellite",
        title="Core-Satellite Investing",
        family="passive",
        philosophy="""
Core-satellite anchors most capital in passive index core (beta cheaply)
while satellites pursue active alpha, factors, or themes with a risk budget.
Philosophy: don't bet the farm on conviction — harvest market returns from
core, experiment with satellites sized to survive being wrong. Institutions
call it alpha overlay; individuals call it 'mostly index, some fun money.'

Discipline: define max satellite % (e.g. 20%) and rebalance when winners
inflate satellite weight.
""".strip(),
        how_it_works="""
Example: 70% total US+intl index, 20% factor tilt (value/momentum ETF),
10% thematic (AI, biotech). Rebalance annually. Track satellite vs core
performance attribution — if satellite consistently lags after costs, shrink it.

FATE rank pipeline can inform satellite stock picks while core stays indexed.
Tax: harvest losses in satellite active sleeve.
""".strip(),
        formulas=(
            _F(
                "Active share (satellite)",
                r"Active\ Share \approx \frac{1}{2}\sum_i |w_i - w_{bench,i}|",
                "Measures deviation from benchmark in satellite sleeve.",
            ),
            _F(
                "Portfolio return decomposition",
                r"R_p = w_{core} R_{core} + w_{sat} R_{sat}",
                "Attribute performance to each sleeve.",
            ),
        ),
        screens=(
            "Core ≥ 60–80% for most investors",
            "Satellite thesis written with exit rules",
            "Satellite turnover and costs tracked",
            "No unintended factor doubling (value core + value satellite)",
            "Rebalance when satellite drifts > policy band",
        ),
        traps=(
            "Satellite becomes majority via winner drift",
            "Chasing last year's thematic winner",
            "Active satellite with no edge — negative alpha drag",
            "Tax inefficiency in high-turnover satellite",
        ),
        catalysts=("Satellite thesis catalyst hit", "core rebalance with new cash"),
        fate_hook="Rank scores suitable for satellite active sleeve; core via strategy_registry index.",
        related=("index_investing", "factor", "thematic_investing", "tactical_aa"),
        further_reading=("CFA Institute core-satellite papers", "Vanguard advisor's alpha research"),
    )
)
