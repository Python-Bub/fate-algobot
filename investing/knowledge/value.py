"""Value investing — deep chapters (1/1 through the family)."""

from __future__ import annotations

from investing.knowledge import DeepChapter, FormulaSpec, register

_F = FormulaSpec

register(
    DeepChapter(
        topic_id="deep_value",
        title="Deep Value Investing",
        family="value",
        philosophy="""
Deep value investing is the art of buying what the crowd refuses to own —
stocks so unpopular that Wall Street has walked away, trading at a steep
discount to a conservative estimate of true worth. The edge is not forecasting
genius; it is buying with such a large margin of safety that mediocre outcomes
still protect capital and good outcomes produce outsized returns.

Unlike growth investing, which pays up for the future, deep value pays
nearly nothing for the present and almost nothing for hope. The hardest skill
is separating a genuine bargain from a value trap: a stock that is cheap
because the business is structurally impaired and stays cheap — or goes to
zero — as the underlying franchise dies.
""".strip(),
        how_it_works="""
Practitioners start from accounting value (assets, earnings power, cash) and
ask: “If a private buyer took the whole company offline tomorrow, what would
they pay?” Market price is treated as temporary noise; the work is estimating
liquidation or normalized-earnings floors.

Typical workflow: (1) screen for historically low P/E and P/B (often P/B < 1),
(2) require low debt and liquid assets so the balance sheet can survive a
downturn, (3) discard frauds, terminal businesses, and serial capital destroys,
(4) buy a basket so no single failure ends the strategy, (5) wait for mean
reversion, activist pressure, or improving fundamentals to close the gap.

Deep value thrives after panics and in neglected smalls/mids. It underperforms
in long bull markets when cheap stocks stay cheap and narratives dominate.
""".strip(),
        formulas=(
            _F(
                "Price-to-earnings",
                r"P/E = \frac{P}{EPS}",
                "Historically low P/E vs a company’s own history and peers is the first deep-value filter. Extremely low multiples can signal either a bargain or collapsing earnings — always check the ‘E’.",
                "analytics.value_investing.analyze_value",
            ),
            _F(
                "Price-to-book",
                r"P/B = \frac{P}{\text{Book equity per share}}",
                "P/B < 1 means you pay less than accounting net assets. Useful for asset-heavy firms; less meaningful for asset-light brands.",
            ),
            _F(
                "Margin of safety (price)",
                r"MOS = \frac{IV - P}{IV}",
                "The buffer between intrinsic value and purchase price. Deep value demands a large MOS because estimates are noisy.",
                "analytics.value_investing.margin_of_safety",
            ),
        ),
        screens=(
            "Trailing or forward P/E in the bottom quartile of history / peers",
            "P/B < 1 (or < sector median for soft assets)",
            "Debt/equity modest; current assets cover near-term claims",
            "Positive free cash flow or clear path to it",
            "No serial dilution, auditor switches, or related-party red flags",
            "Basket of 20–40 names preferred over one ‘perfect’ cheap stock",
        ),
        traps=(
            "Value trap: low multiples because earnings and assets are permanently impaired",
            "Accounting book value inflated by goodwill that will be written off",
            "Leverage that turns a mild recession into bankruptcy",
            "Melting ice cubes (newspapers, legacy retail) that stay ‘cheap’ forever",
            "Catching falling knives without a catalyst or asset floor",
        ),
        catalysts=(
            "Mean reversion of multiples as fear fades",
            "Asset sales, spin-offs, or liquidation dividends",
            "Activist investors forcing capital return",
            "Cyclical recovery in earnings (industrials, materials)",
        ),
        fate_hook="Live in `analytics.value_investing` via `deep_value` flag (low P/E + P/B < 1 + low debt). Feeds `value_investing_rank_boost`.",
        related=("intrinsic_value", "graham", "net_net", "contrarian", "turnaround"),
        further_reading=(
            "Benjamin Graham — The Intelligent Investor",
            "Seth Klarman — Margin of Safety",
            "Joel Greenblatt — You Can Be a Stock Market Genius (related specials)",
        ),
    )
)

register(
    DeepChapter(
        topic_id="intrinsic_value",
        title="Intrinsic Value (DCF Anchor)",
        family="value",
        philosophy="""
Intrinsic value is the true economic worth of an asset based on the cash it
will generate for its owners — independent of today’s stock quote. Market
value is a temporary auction price; intrinsic value is the anchor. A dollar
received in the future is worth less than a dollar today (inflation, risk,
opportunity cost), so all future cash must be discounted.

Investing becomes: estimate IV carefully, buy only when price << IV, and let
the market eventually respect the cash truth. Wrong estimates are inevitable —
that is why margin of safety exists.
""".strip(),
        how_it_works="""
The workhorse model is discounted cash flow (DCF): project free cash flows for
n years, discount each at required return r, then add a terminal value for
cash beyond the explicit horizon, also discounted. Terminal value often assumes
perpetual growth at rate g with g < r (otherwise the math explodes / goes negative).

IV per share = equity DCF ÷ diluted shares. Compare to market price. Sensitivity
tables on r and g matter more than false precision to the penny.

**2026 practice notes:** for stable businesses, r commonly sits ~8–12% (ask what
*you* require, not a textbook CAPM toy). Keep perpetual g ~2–3% (≤ long-run
nominal GDP). Terminal value often dominates 60–80% of the DCF — so always
publish a range, not one “precise” number. Cross-check with PEG / multiples;
DCF alone is precise but often wrong.
""".strip(),
        formulas=(
            _F(
                "Intrinsic value (DCF)",
                r"IV = \sum_{t=1}^{n} \frac{CF_t}{(1+r)^t} + \frac{TV}{(1+r)^n}",
                "Where CF_t = cash flow in year t, r = required return, TV = terminal value, n = forecast years. Primary valuation identity.",
                "analytics.value_investing.intrinsic_value",
            ),
            _F(
                "Terminal value (Gordon)",
                r"TV = \frac{CF_n \times (1+g)}{r - g}",
                "Perpetuity after year n at growth g. WARNING: g must be < r or the denominator blows up / goes nonsense. Stress-test g and r — TV usually dominates the answer.",
                "analytics.value_investing.terminal_value",
            ),
            _F(
                "Margin of safety",
                r"MOS = \frac{IV - P}{IV}",
                "Buffer if your IV estimate is slightly off. Deep practitioners often require 30–50%+ depending on uncertainty.",
                "analytics.value_investing.margin_of_safety",
            ),
            _F(
                "PEG (cross-check)",
                r"PEG = \frac{P/E}{g_{\%}}",
                "GARP sanity check: ≤1 historically attractive, 1–1.5 fair for quality, >1.5 often rich. Breaks on cyclicals / near-zero earnings.",
            ),
        ),
        screens=(
            "Stable or growing free cash flow (not just accounting earnings)",
            "Credible mid-cycle margins (not peak-cycle optimism)",
            "Discount rate r reflecting business risk (not a vanity 5–6%)",
            "g capped ~2–3% and well below r",
            "Cross-check DCF vs PEG/comps and asset value — triangulation",
            "Sensitivity table: r ±1–2pp and g ±0.5–1pp",
        ),
        traps=(
            "Hockey-stick forecasts with no competitive reality",
            "g ≥ r yielding infinite/negative nonsense values",
            "Ignoring share dilution (IV looks high per old share count)",
            "Using peak FCF as CF_0 forever",
            "False precision: three decimal places on a rough model",
            "Anchoring on one method (DCF or PEG alone)",
        ),
        catalysts=("Price appreciation as cash compounds into consensus", "Buybacks when P < IV", "Take-private at premium to market but near IV"),
        fate_hook="Exact formulas in `analytics.value_investing`. Yahoo FCF projected n years then TV; per-share IV vs price → MOS → rank boost.",
        related=("deep_value", "dcf", "wacc", "valuation", "buffett"),
        further_reading=("Aswath Damodaran — Damodaran on Valuation", "McKinsey — Valuation"),
    )
)

register(
    DeepChapter(
        topic_id="graham",
        title="Graham Investing",
        family="value",
        philosophy="""
Benjamin Graham taught two pillars: (1) Mr. Market is manic-depressive — prices
are invitations, not instructions; buy only when absurdly cheap. (2) Margin of
safety is the difference between price and a conservative value estimate that
protects you when you are wrong.

Graham preferred quantitative rules over storytelling. He treated common stocks
like fractional ownership of businesses and demanded a liquidation-aware floor
so even a mediocre business bought cheaply would not destroy capital overnight.
""".strip(),
        how_it_works="""
Graham screens: strong current assets vs liabilities, modest debt, earnings
stability across years, and a purchase price offering a wide discount to tangible
value. Net-nets (see that chapter) are the extreme form. He diversified widely
among cheap issues rather than concentrating on narrative darlings.

Modern Grahamians adapt ratios (earnings yield vs bond yields, EV/EBIT) but keep
the spirit: statistical cheapness + balance-sheet defense + humility about forecasting.
""".strip(),
        formulas=(
            _F(
                "NCAV",
                r"NCAV = \text{Current Assets} - \text{Total Liabilities} - \text{Preferred}",
                "Net current asset value — Graham’s conservative liquidation proxy ignoring fixed assets and goodwill.",
                "analytics.value_investing.ncav",
            ),
            _F(
                "NCAV per share",
                r"NCAVPS = \frac{NCAV}{\text{Shares}}",
                "Compare to market price. Graham famously favored buying below ~2/3 of NCAVPS.",
            ),
            _F(
                "Graham number (common variant)",
                r"P_{\max} \approx \sqrt{22.5 \times EPS \times BVPS}",
                "Rule-of-thumb ceiling combining earnings and book; not gospel, but a Graham-flavored sanity check.",
            ),
        ),
        screens=(
            "Current ratio ≥ 1.5–2; debt conservative vs tangible assets",
            "Positive NCAV; price ≤ 2/3 NCAVPS for classic deep Graham",
            "Earnings positive in most of last 5–10 years",
            "Dividend history optional but helpful as discipline signal",
            "Diversify across many statistical bargains",
        ),
        traps=(
            "Ignoring fraud or asset write-downs that vaporize NCAV",
            "Applying net-net screens to bank/insurance accounting naively",
            "Holding forever without a sell rule when value is realized",
            "Modern markets have fewer classic net-nets — don’t force fits",
        ),
        catalysts=("Liquidation", "take-private", "earnings normalization", "multiple mean reversion"),
        fate_hook="`is_graham_net_net` and NCAV helpers in `analytics.value_investing`; classic multiple DEFAULT 1.5× market cap (configurable).",
        related=("net_net", "deep_value", "asset_based", "intrinsic_value"),
        further_reading=("Graham & Dodd — Security Analysis", "The Intelligent Investor"),
    )
)

register(
    DeepChapter(
        topic_id="buffett",
        title="Buffett Investing (Quality Compounders)",
        family="value",
        philosophy="""
Warren Buffett evolved from Graham’s cigar butts to buying wonderful businesses
at fair prices — companies with economic moats that protect high returns on
capital for decades. Prefer understanding a business deeply (“circle of
competence”) over dabbling in opaque industries. Time horizon is forever when
the moat holds; compounding beats frenetic trading.

Owner earnings matter more than reported GAAP. Character of management —
capital allocation, candor, alignment — is part of intrinsic value.
""".strip(),
        how_it_works="""
Identify moat sources: intangible assets (brand, patents), switching costs,
network effects, cost advantages, efficient scale. Confirm the moat in the
numbers: high sustained ROE/ROIC, stable gross margins, low maintenance
capex relative to growth capex.

Value using owner earnings (cash truly available to owners) discounted
conservatively. Buy when the price is reasonable, not necessarily at NCAV.
Hold through volatility unless the moat is broken or capital can be
redeployed at far higher expected returns.
""".strip(),
        formulas=(
            _F(
                "Owner earnings (Buffett)",
                r"OE \approx NI + D\&A - \text{Maintenance CapEx} - \Delta WC_{\text{maint}}",
                "Cash generation for owners after keeping the business competitive — better than raw NI for DCF.",
                "investing.formulas.value_extras.owner_earnings",
            ),
            _F(
                "Return on equity",
                r"ROE = \frac{\text{Net Income}}{\text{Equity}}",
                "Sustained high ROE with low leverage is a moat fingerprint (watch accounting distortions).",
            ),
            _F(
                "Reinvestment / growth link",
                r"g \approx ROIC \times \text{Reinvestment Rate}",
                "Growth is earned by reinvesting at high returns — not by wishing.",
            ),
        ),
        screens=(
            "ROE / ROIC elevated vs cost of capital for many years",
            "Gross margin stability; pricing power evidence",
            "Modest leverage; understandable business model",
            "Management with ownership and sane capital allocation (buybacks when cheap, not vanity M&A)",
            "Fair P/E or PEG — wonderful ≠ any price",
        ),
        traps=(
            "Confusing a temporary high ROE with a permanent moat",
            "Overpaying for quality (no MOS left)",
            "Circle-of-competence violations (tech you don’t understand)",
            "Moat erosion from disruption while thesis stays nostalgic",
        ),
        catalysts=("Long compounding", "share shrink via opportunistic buybacks", "bolt-on M&A that earns cost of capital+"),
        fate_hook="`buffett_quality` score in `analytics.value_investing` (ROE, margins, leverage). Soft quality growth also in book composite.",
        related=("compounders", "quality_growth", "economic_moat", "intrinsic_value"),
        further_reading=("Buffett Letters to Berkshire Shareholders", "Pat Dorsey — The Little Book That Builds Wealth"),
    )
)

register(
    DeepChapter(
        topic_id="contrarian",
        title="Contrarian Investing",
        family="value",
        philosophy="""
Contrarian investing buys when others are forced or emotionally compelled to
sell — and demands proof that the crowd is mathematically wrong, not merely
unpopular. Temporary bad headlines, one ugly earnings print, or forced
deleveraging by funds can dislocate price from long-term value. Fatal franchise
damage is not a contrarian opportunity; it is a value trap with an audience.
""".strip(),
        how_it_works="""
Separate transient vs permanent impairment: accounting one-offs, cyclical
downturns, and solvable execution misses vs secular demand destruction, fraud,
or obsolete products. Require independent underwriting (DCF, asset cover,
customer retention) that does not rely on “it must bounce.”

Position sizing respects that being early looks identical to being wrong for
a long time. Catalysts help — but deep contrarians also accept multi-year waits
when MOS is wide enough.
""".strip(),
        formulas=(
            _F(
                "Drawdown from peak",
                r"DD = \frac{P_{\text{peak}} - P}{P_{\text{peak}}}",
                "Large DD is necessary but not sufficient; pair with quality/cash tests.",
            ),
            _F(
                "Contrarian tilt (FATE soft)",
                r"tilt \propto (-q_{52w}) \times quality^{+}",
                "Reward deep 52-week declines only when balance-sheet/quality proxies remain intact.",
                "analytics.value_investing.analyze_value",
            ),
        ),
        screens=(
            "Large price decline with intact long-term earnings power thesis",
            "Insider buying or debt refinance success as soft confirmation",
            "Short interest / fund outflows creating mechanical pressure",
            "Avoid binary terminal news (going concern, fraud probes) unless specialist",
        ),
        traps=(
            "Catching knives in structural decline",
            "Average-down addiction without thesis update",
            "Social proof of other contrarians ≠ analysis",
        ),
        catalysts=("Earnings beat that resets narrative", "activist", "cyclical trough", "index inclusion after stigma fades"),
        fate_hook="Contrarian component inside `analyze_value` when 52w change is deeply negative and Buffett quality > threshold.",
        related=("deep_value", "turnaround", "special_situations", "sentiment"),
        further_reading=("David Dreman — Contrarian Investment Strategies",),
    )
)

register(
    DeepChapter(
        topic_id="net_net",
        title="Net-Net Investing",
        family="value",
        philosophy="""
A net-net is a company trading below its Net Current Asset Value — Graham’s
estimate of what common shareholders would scrap together if current assets
were monetized and every liability (and preferred) paid. Fixed assets and
goodwill are treated as free call options. The margin of safety is literal:
even a failed going concern may still return cash in liquidation.
""".strip(),
        how_it_works="""
Compute NCAV = current assets − total liabilities − preferred (and often
minority interest). Divide by shares → NCAVPS. Graham preferred buying at
≤ ~⅔ of NCAVPS. Stricter Net-Net Working Capital (NNWC) haircuts receivables
(~75%) and inventory (~50%) to reflect liquidation realities.

Net-nets cluster in neglected microcaps. Diversify because some never recover;
the basket’s statistical edge historically came from survivors and takeovers.
""".strip(),
        formulas=(
            _F(
                "NCAV",
                r"NCAV = CA - TL - Pref",
                "Classic Graham liquidation cushion for common equity.",
                "analytics.value_investing.ncav",
            ),
            _F(
                "NNWC (stricter)",
                r"NNWC = Cash + 0.75\,AR + 0.5\,Inv - TL",
                "Haircut working-capital assets for fire-sale prices.",
                "investing.formulas.value_extras.nnwc",
            ),
            _F(
                "Graham buy rule",
                r"P \le \tfrac{2}{3}\,NCAVPS",
                "Classic purchase threshold used by Graham-Newman era practice.",
            ),
            _F(
                "Net-net screen (FATE)",
                r"NCAV \ge k \times MarketCap \quad (k \approx 1.5)",
                "Equivalent framing: net current assets dominate entire firm value.",
                "analytics.value_investing.is_graham_net_net",
            ),
        ),
        screens=(
            "Positive NCAV; price << NCAVPS (target ≤ 2/3)",
            "Cash-heavy balance sheet preferred",
            "Avoid Chinese reverse-merger fraud patterns / opaque filers",
            "Check off-balance liabilities, litigation, pensions",
            "Hold as basket; set time or value realization exits",
        ),
        traps=(
            "Assets pledged or illiquid despite ‘current’ classification",
            "Burn rate consuming cash before catalyst",
            "Control shareholders blocking fair liquidation",
            "Universe too small / illiquid for large funds — capacity constrained",
        ),
        catalysts=("Liquidating dividend", "takeover", "activist", "earnings surprise closing discount"),
        fate_hook="`is_graham_net_net` + NCAV in value module; NNWC helper in `investing.formulas.value_extras`.",
        related=("graham", "deep_value", "asset_based"),
        further_reading=("Graham — Security Analysis", "Net-net practitioner blogs / NCAV studies"),
    )
)

register(
    DeepChapter(
        topic_id="asset_based",
        title="Asset-Based Investing",
        family="value",
        philosophy="""
Asset-based investing focuses on what the company owns *now* — land, cash,
securities, inventory, PP&E — rather than optimistic future earnings.
You profit if you can buy the whole firm below a realistic private-market
value of those assets and wait for a catalyst that forces recognition
(sale, breakup, NAV mark, activist).
""".strip(),
        how_it_works="""
Rebuild the balance sheet at market or replacement cost: cash at face,
marketable securities mark-to-market, real estate appraisals, inventory at
realizable value, subtract debt and preferred. Compare NAV per share to price.

Works best for holding companies, REITs/NAV vehicles, natural resources, and
closed-end funds trading at discounts. Earnings may look poor even when assets
are treasure — that mismatch is the opportunity.
""".strip(),
        formulas=(
            _F(
                "Net asset value",
                r"NAV = \sum Asset_i^{fair} - Liabilities - Pref",
                "Fair-value of assets minus claims ahead of common.",
            ),
            _F(
                "NAV discount",
                r"Discount = \frac{NAV - MktCap}{NAV}",
                "Positive discount means market implies assets are worth less than your mark — investigate why.",
            ),
        ),
        screens=(
            "Transparent asset schedule (properties, secs, cash)",
            "Discount to conservative NAV ≥ hurdle (e.g. 20–40%)",
            "Low double-pledge / encumbrance risk",
            "Credible path to unlock (sales program, tender, liquidation vote)",
        ),
        traps=(
            "Stale appraisals; NAV fiction",
            "Tax leakage on asset sales ignored",
            "Controlling shareholder who never unlocks value",
        ),
        catalysts=("Asset sale program", "conversion to liquidating trust", "take-private", "activist NAV campaign"),
        fate_hook="Related to SOTP/NAV tools in `investing.formulas.analysis` / `sotp`. Soft signal via P/B and balance-sheet rich screens.",
        related=("sum_of_the_parts", "net_net", "real_estate", "special_situations"),
        further_reading=("Klarman — Margin of Safety (asset chapters)",),
    )
)

register(
    DeepChapter(
        topic_id="special_situations",
        title="Special Situations Investing",
        family="value",
        philosophy="""
Special situations (Joel Greenblatt’s playground) exploit structural market
inefficiencies: spin-offs, restructurings, merger securities, rights offerings,
bankruptcies, recapitalizations. The edge is often forced selling, complexity,
and institutional mandates — not predicting GDP. Look down first: if you do
not lose money, most remaining paths are acceptable.
""".strip(),
        how_it_works="""
Map the event: who must sell and why? Read Form 10 / proxy / PSA. Underwrite
the stub or spun entity on clean pro formas. Check management incentives (skin
in the game). Complexity and neglect are features when you can model payoffs.

Hold through the disorderly distribution period (often 6–18 months) while
the shareholder base turns over and coverage appears.
""".strip(),
        formulas=(
            _F(
                "Stub value (conceptual)",
                r"V_{stub} = V_{parent}^{pre} - V_{spin}^{distributed} - frictions",
                "When a parent distributes a spin, residual parent value can be mispriced relative to sum of parts.",
            ),
            _F(
                "Merger spread",
                r"Spread = \frac{DealPrice - P}{P}",
                "Risk-arb yield for agreeing to deal risk; underwrite break probability separately.",
            ),
        ),
        screens=(
            "Spin-off / split-off calendar; Form 10 available",
            "Evidence of forced institutional selling",
            "Insider alignment on the interesting stub",
            "Leverage post-deal survivable",
            "Risk/reward asymmetric if base case works",
        ),
        traps=(
            "Toxic waste spin designed to dump liabilities",
            "Deal break risk underpriced in merger arb",
            "Complexity cosplay without edge",
        ),
        catalysts=("Distribution day + seasoning", "index adds/deletes", "research initiation", "strategic bids"),
        fate_hook="Knowledge/status soft today; event calendar + news factors can flag catalysts. Pair with SOTP tools when segment data exists.",
        related=("sum_of_the_parts", "merger_arbitrage", "turnaround", "contrarian"),
        further_reading=("Joel Greenblatt — You Can Be a Stock Market Genius",),
    )
)

register(
    DeepChapter(
        topic_id="sum_of_the_parts",
        title="Sum-of-the-Parts (SOTP) Valuation",
        family="value",
        philosophy="""
Large conglomerates often trade at a conglomerate discount: the market struggles
to value dissimilar segments under one ticker. SOTP values each piece with the
right method (DCF, EV/EBITDA comps, NAV), adds them, subtracts net debt, and
compares to market cap. If SOTP equity >> price, wait for a catalyst that
forces recognition — or activism that breaks the firm apart.
""".strip(),
        how_it_works="""
1) Identify reportable segments. 2) Choose multiples or DCFs fit for each.
3) Sum segment enterprise values. 4) Adjust for corporate costs, net debt,
non-operating assets/liabilities. 5) Derive equity value and per-share target.
6) Optionally apply an explicit conglomerate discount if unlock is uncertain.

Book framing: Wall Street undervalues complexity; your job is accurate addition
followed by patience for the catalyst.
""".strip(),
        formulas=(
            _F(
                "SOTP equity",
                r"E_{SOTP} = \sum_i V_i - NetDebt - NL + NA",
                "Sum of segment values minus net debt and non-op liabilities plus non-op assets.",
                "investing.formulas.analysis.sotp_equity",
            ),
            _F(
                "Conglomerate discount",
                r"Disc = \frac{E_{SOTP} - MktCap}{E_{SOTP}}",
                "Fraction of modeled value not reflected in the stock price.",
                "investing.formulas.analysis.conglomerate_discount",
            ),
            _F(
                "Segment EV via multiple",
                r"EV_i = Multiple_i \times Metric_i",
                "e.g. EV/EBITDA × segment EBITDA for industrial piece; DCF for another.",
            ),
        ),
        screens=(
            "Multi-segment filer with disclosed EBITDA/revenue by part",
            "Peers available for each major segment",
            "SOTP upside ≥ hurdle after conservative multiples",
            "Plausible unlock (spin, sale, tracking stock, activist)",
        ),
        traps=(
            "Double-counting corporate costs / synergies fantasy",
            "Stale segment accounting; transfer pricing games",
            "Ignoring tax on separations",
            "Permanent discount if capital allocation is chronically bad",
        ),
        catalysts=("Announced breakup", "segment IPO", "sale of crown jewel", "activist 13D"),
        fate_hook="`investing.formulas.sotp` / `analysis.sotp_equity`. Soft status until segment feeds automated; still usable in manual/research path.",
        related=("asset_based", "special_situations", "valuation", "buffett"),
        further_reading=("Wall Street Prep — SOTP", "Investopedia — Sum of Parts"),
    )
)

register(
    DeepChapter(
        topic_id="turnaround",
        title="Turnaround Investing",
        family="value",
        philosophy="""
Turnaround investing buys companies exiting distress — new management,
repaired balance sheets, operational fixes, or industry healing — before the
market believes the recovery. Upside can be multi-bagger; risk is permanent
capital loss if the turn fails. Evidence beats narrative: cash burn slowing,
margins stabilizing, refinancing closed, customer wins.
""".strip(),
        how_it_works="""
Stage the turn: (1) liquidity crisis survival, (2) operational stabilization,
(3) renewed growth. Prefer stage 2–3 with cleaned debt and honest write-offs
behind them. Underwrite downside if turn fails (asset cover, covenant headroom).

Catalysts: first clean quarter, credit upgrade, activist operational plan,
industry volume rebound. Time stops if liquidity bridge fails.
""".strip(),
        formulas=(
            _F(
                "Cash runway",
                r"Runway \approx \frac{Cash}{\text{Monthly burn}}",
                "How long until insolvency without a fix — turnaround clock.",
            ),
            _F(
                "Interest coverage",
                r"Coverage = \frac{EBIT}{\text{Interest}}",
                "Rising coverage is early proof the turn is working.",
            ),
        ),
        screens=(
            "New credible management with relevant ops experience",
            "Debt maturity wall refinanced or extended",
            "Gross margin troughing; opex discipline visible",
            "Asset sales that shrink debt without gutting core",
            "Avoid fraud-driven collapses unless specialist distressed",
        ),
        traps=(
            "Hopeium before liquidity is secured",
            "Diworsifying M&A mid-turn",
            "Dilutive rescue finance wiping equity",
            "Cyclical bounce mistaken for structural turn",
        ),
        catalysts=("Refi close", "earnings inflection", "ratings upgrade", "strategic premium bid"),
        fate_hook="Overlaps contrarian + special situations. News/sentiment + balance-sheet screens soft-flag candidates; pair with deep fundamental review.",
        related=("contrarian", "special_situations", "distressed_debt", "deep_value"),
        further_reading=("Operational turnaround case studies; distressed playbooks",),
    )
)
