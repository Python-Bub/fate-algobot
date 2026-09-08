"""Options & derivatives strategies — deep chapters (derivatives family)."""

from __future__ import annotations

from investing.knowledge import DeepChapter, FormulaSpec, register

_F = FormulaSpec

register(
    DeepChapter(
        topic_id="options",
        title="Options",
        family="derivatives",
        philosophy="""
An option is a contract granting the right — not the obligation — to buy
(call) or sell (put) an underlying at a strike price before expiration. You
pay premium upfront for asymmetry: defined maximum loss (long options) or
defined-risk spreads versus naked stock risk. Options encode views on direction,
volatility, and time — not just price.

They are leverage with a clock. Theta eats long premium daily; vega punishes
long options when implied vol collapses after events. Master the Greeks before
size.
""".strip(),
        how_it_works="""
Calls profit when underlying rises above strike + premium; puts when it falls
below strike − premium. European-style pricing (Black-Scholes) assumes lognormal
returns, constant vol, and continuous trading — a model, not reality. American
exercise and dividends matter for early exercise on deep ITM calls.

Workflow: (1) define view (direction, vol, time), (2) select structure (single,
spread, combo), (3) check liquidity (open interest, bid-ask), (4) size by max
loss, (5) plan exit (profit target, time stop, roll). FATE implements BS and
parity checks in `investing.formulas.derivatives` for research overlays.
""".strip(),
        formulas=(
            _F(
                "Black-Scholes call",
                r"C = S e^{-qT} \Phi(d_1) - K e^{-rT} \Phi(d_2)",
                "European call fair value with dividend yield q.",
                "investing.formulas.derivatives.black_scholes_call",
            ),
            _F(
                "Black-Scholes put",
                r"P = K e^{-rT} \Phi(-d_2) - S e^{-qT} \Phi(-d_1)",
                "European put fair value; put-call parity links to call.",
                "investing.formulas.derivatives.black_scholes_put",
            ),
            _F(
                "d₁, d₂",
                r"d_1 = \frac{\ln(S/K) + (r - q + \sigma^2/2)T}{\sigma\sqrt{T}}, \quad d_2 = d_1 - \sigma\sqrt{T}",
                "Standard normal inputs to Φ(·).",
            ),
            _F(
                "Put-call parity",
                r"C - P = S e^{-qT} - K e^{-rT}",
                "Arbitrage relation for European options on same strike/expiry.",
                "investing.formulas.derivatives.put_call_parity_check",
            ),
        ),
        screens=(
            "Open interest and volume adequate at strike/expiry",
            "Bid-ask spread reasonable vs premium (< 10% for liquid names)",
            "Implied vol vs 30d realized — know if buying or selling vol",
            "Days to expiry match thesis horizon",
            "Max loss defined before entry",
        ),
        traps=(
            "Buying OTM lottery tickets with steady theta bleed",
            "Ignoring ex-div early assignment on short calls",
            "Illiquid strikes with fake mid quotes",
            "Confusing notional leverage with risk-defined spreads",
        ),
        catalysts=(
            "Earnings / FDA moving implied vol",
            "Vol crush post-event for long vol positions",
            "Pin risk into expiration at round strikes",
        ),
        fate_hook="Pricing in `investing.formulas.derivatives` (BS call/put, parity residual). Income overlays soft-linked via covered_call / protective_put helpers.",
        related=("covered_calls", "protective_puts", "volatility_trading", "leveraged_investing"),
        further_reading=(
            "Hull — Options, Futures, and Other Derivatives",
            "Natenberg — Option Volatility and Pricing",
        ),
    )
)

register(
    DeepChapter(
        topic_id="covered_calls",
        title="Covered Calls",
        family="derivatives",
        philosophy="""
A covered call sells a call option against stock you already own, collecting
premium that partially offsets downside and enhances yield in flat or mildly
bullish markets. You trade unlimited upside above the strike for income today —
classic “rent your shares” strategy popular with income investors and funds.

It is not free money. Sharp rallies cap participation; sharp drops hurt despite
premium cushion. Best when you would be happy to sell at the strike anyway.
""".strip(),
        how_it_works="""
Own ≥ 100 shares per contract. Sell OTM call (typically 0.20–0.40 delta) with
30–45 DTE for theta sweet spot. If stock stays below strike, keep premium and
repeat. If above strike at expiry, shares called away at strike (effective sell
price = strike + premium collected). Roll up/out if bullish continuation desired.

FATE `covered_call_max_return` computes assigned return; income catalog links
soft yield screens for overlay research.
""".strip(),
        formulas=(
            _F(
                "Covered call max return (assigned)",
                r"R_{max} = \frac{K - S + premium}{S}",
                "Total return if called away at strike K.",
                "investing.formulas.derivatives.covered_call_max_return",
            ),
            _F(
                "Static yield",
                r"Yield = \frac{premium}{S}",
                "Premium as fraction of stock cost — annualize by DTE for comparison.",
            ),
            _F(
                "Breakeven",
                r"BE = S - premium",
                "Stock can fall to breakeven before net loss at expiry.",
            ),
        ),
        screens=(
            "Would sell stock at strike willingly",
            "IV elevated vs history ( richer premium )",
            "Ex-div date: assignment risk if dividend > extrinsic",
            "Not selling deep ITM unless intentional acceleration",
            "Tax lot awareness in taxable accounts",
        ),
        traps=(
            "Capping upside right before blow-off rally",
            "Selling calls on volatile small caps with huge moves",
            "Forgetting assignment on ex-div for ITM calls",
            "Double-counting premium as ‘safe income’ without downside",
        ),
        catalysts=(
            "Elevated IV into earnings then sell post-crush (timing risk)",
            "Slow grind up market ideal for repeated OTM writes",
            "Buy-write index rebalance flows",
        ),
        fate_hook="`investing.formulas.derivatives.covered_call_max_return`; catalog `covered_call_income` soft status; pair with owned positions in fortress book.",
        related=("options", "income_investing", "protective_puts", "collar"),
        further_reading=(
            "CBOE — BuyWrite index methodology",
            "McMillan — Options as a Strategic Investment",
        ),
    )
)

register(
    DeepChapter(
        topic_id="protective_puts",
        title="Protective Puts",
        family="derivatives",
        philosophy="""
A protective put buys downside insurance on stock you own — paying premium
like an insurance deductible. No matter how far the stock falls, you can sell
at the strike (minus premium cost). It is portfolio catastrophe insurance, not
a profit center; over long calm periods, repeated put buying drags returns.

Use when tail risk matters more than average return — before known binary events,
in concentrated positions, or when psychologically you cannot hold through
20% drawdowns without selling lows.
""".strip(),
        how_it_works="""
Own shares; buy OTM or ATM put with expiry covering your risk window. Max loss
≈ (S − K) + premium if held to expiry and exercised. If stock rallies, lose
premium but participate fully in upside (unlike collar). Choose strike as
deductible you can afford; longer expiry costs more vega/theta balance.

FATE `protective_put_floor` estimates effective floor return for research sizing.
""".strip(),
        formulas=(
            _F(
                "Protective put floor return",
                r"R_{floor} = \frac{K - S - premium}{S}",
                "Worst-case return at expiry if exercising put (often negative = cost of insurance).",
                "investing.formulas.derivatives.protective_put_floor",
            ),
            _F(
                "Put payoff at expiry",
                r"\Pi = \max(K - S_T, 0) - premium",
                "Long put P&L combined with stock P&L offsets downside.",
            ),
            _F(
                "Black-Scholes put",
                r"P = K e^{-rT} \Phi(-d_2) - S e^{-qT} \Phi(-d_1)",
                "Fair value benchmark for put premium paid.",
                "investing.formulas.derivatives.black_scholes_put",
            ),
        ),
        screens=(
            "Strike = acceptable max loss level",
            "Expiry covers event window (earnings, FDA, macro)",
            "IV not at extreme (insurance expensive at peak fear)",
            "Liquidity at chosen strike",
            "Plan: hold to expiry vs roll vs monetize on crash",
        ),
        traps=(
            "Buying puts too late after vol spike (overpay)",
            "Letting puts expire worthless repeatedly without thesis review",
            "Strike too far OTM — false sense of protection",
            "Ignoring correlation — index put ≠ single-stock idiosyncratic risk",
        ),
        catalysts=(
            "Vol cheap before known risk event",
            "Portfolio concentration into binary date",
            "Hedging into election / FOMC week",
        ),
        fate_hook="`investing.formulas.derivatives.protective_put_floor`; catalog `protective_puts` soft; use alongside fortress position risk review.",
        related=("options", "covered_calls", "tail_risk", "collar"),
        further_reading=(
            "Taleb — Dynamic Hedging (tail philosophy)",
            "CBOE — protective put index literature",
        ),
    )
)

register(
    DeepChapter(
        topic_id="iron_condors",
        title="Iron Condors",
        family="derivatives",
        philosophy="""
An iron condor sells OTM call spread and OTM put spread simultaneously,
profiting when the underlying stays between inner strikes through expiry —
classic “short volatility, long time decay” structure. Max gain is net credit
received; max loss is wing width minus credit. It wins often in small amounts
and loses rarely in large chunks if price breaks a wing.

It is not income for all seasons: gap risk through wings, vol spikes, and
early assignment on short legs can hurt. Respect margin and tail events.
""".strip(),
        how_it_works="""
Example: stock at 100. Sell 105 call, buy 110 call (call spread); sell 95 put,
buy 90 put (put spread). Collect net credit. Profit zone roughly 95–105 at
expiry (adjusted for credit). Manage at 50% max profit, or defend tested side
by rolling untested side / converting to vertical. Exit before binary events.

FATE `iron_condor_max_profit` returns net credit as max gain reference for
research calculators.
""".strip(),
        formulas=(
            _F(
                "Iron condor max profit",
                r"\Pi_{max} = credit",
                "Net premium received if all options expire worthless OTM.",
                "investing.formulas.derivatives.iron_condor_max_profit",
            ),
            _F(
                "Max loss",
                r"L_{max} = width - credit",
                "Width of wider spread minus credit (same on call or put side).",
            ),
            _F(
                "Breakevens",
                r"BE_{up} = K_{short\_call} + credit, \quad BE_{down} = K_{short\_put} - credit",
                "Outer profitability boundaries at expiry.",
            ),
        ),
        screens=(
            "IV rank elevated ( selling rich vol )",
            "No earnings inside hold period unless intentional",
            "Wing width vs credit ≥ 1:3 reward:risk target",
            "Underlying historically range-bound",
            "Plan for 2× credit loss as management trigger",
        ),
        traps=(
            "Short vol into earnings gap through wing",
            "Illiquid wings with poor fills",
            "Pin risk at short strike into expiry",
            "Over-leveraging margin on ‘high probability’ trades",
        ),
        catalysts=(
            "Post-event IV crush after strangle sellers win",
            "Low-vol grind market",
            "Mean-reverting index regime",
        ),
        fate_hook="`investing.formulas.derivatives.iron_condor_max_profit`; pairs conceptually with `range_trading` knowledge.",
        related=("credit_spreads", "strangles", "range_trading", "volatility_trading"),
        further_reading=(
            "Tastytrade / IBKR education on iron condor management",
            "Natenberg — short premium risk chapters",
        ),
    )
)

register(
    DeepChapter(
        topic_id="credit_spreads",
        title="Credit Spreads",
        family="derivatives",
        philosophy="""
Credit spreads sell one option and buy a further OTM option on the same side,
collecting net premium with defined maximum loss equal to spread width minus
credit. Bull put spreads express bullish/neutral views below current price;
bear call spreads express bearish/neutral above. They are the workhorse of
short-premium directional trading with capped risk versus naked shorts.

Edge is probability management: high win rate, smaller wins, occasional full
width loss. Discipline on position count and correlation prevents one macro
gap from wiping the month.
""".strip(),
        how_it_works="""
Bull put: sell put at K_high, buy put at K_low (K_high > K_low). Collect credit.
Max loss if underlying below K_low at expiry. Bear call: sell call at K_low, buy
at K_high. Manage at 50–75% profit or roll for credit. Width choice trades
premium vs risk; 5-wide vs 10-wide on same underlying.

Same margin efficiency as iron condor single side; often used directionally
instead of symmetric condor.
""".strip(),
        formulas=(
            _F(
                "Credit spread max profit",
                r"\Pi_{max} = credit",
                "Keep entire net premium if short leg expires OTM.",
            ),
            _F(
                "Max loss",
                r"L_{max} = (K_{short} - K_{long}) - credit",
                "For puts; mirror for calls with strike ordering reversed.",
            ),
            _F(
                "Return on risk",
                r"RoR = \frac{credit}{L_{max}}",
                "Compare trades on credit relative to capital at risk.",
            ),
        ),
        screens=(
            "Short strike beyond technical support/resistance",
            "30–45 DTE typical entry; 21 DTE management rule",
            "IV percentile > 30 for richer credit",
            "Max loss per trade ≤ 2–5% of options buying power",
            "Avoid highly correlated spreads on same sector",
        ),
        traps=(
            "Selling puts on stocks you wouldn’t own at strike",
            "No exit plan when tested — hope holding to expiry",
            "Assignment on short leg early in deep ITM puts",
            "Gap through long leg on news",
        ),
        catalysts=(
            "Elevated skew selling OTM puts on indices",
            "Post-rally call spread fade in extended names",
            "Vol mean reversion after spike",
        ),
        fate_hook="Conceptual overlap with `iron_condor_max_profit` credit math in `investing.formulas.derivatives`; research-only in FATE equity stack today.",
        related=("debit_spreads", "iron_condors", "covered_calls", "options"),
        further_reading=(
            "Options Playbook — spread structures",
            "McMillan — vertical spreads",
        ),
    )
)

register(
    DeepChapter(
        topic_id="debit_spreads",
        title="Debit Spreads",
        family="derivatives",
        philosophy="""
Debit spreads pay upfront net premium: buy an option closer to the money and
sell a further OTM option to reduce cost and cap max gain. They express
directional views with less theta bleed than outright long options — you partially
finance the long leg by giving up unlimited upside beyond the short strike.

Defined risk and lower cost make them beginner-friendly long-vol directional
structures, but max gain is limited and you still fight time decay on the net debit.
""".strip(),
        how_it_works="""
Bull call: buy call K_low, sell call K_high. Net debit = cost. Max gain =
width − debit if S ≥ K_high at expiry. Bear put: buy put K_high, sell put K_low.
Choose width where reward:risk justifies probability. Often used into events
when outright straddle too expensive — sell OTM wing to pay for ATM.

Exit at percentage profit of max gain or time stop if thesis wrong.
""".strip(),
        formulas=(
            _F(
                "Debit spread max gain",
                r"\Pi_{max} = width - debit",
                "Best case at expiry if underlying beyond short strike.",
            ),
            _F(
                "Max loss",
                r"L_{max} = debit",
                "Premium paid is entire risk — cannot lose more.",
            ),
            _F(
                "Breakeven (bull call)",
                r"BE = K_{long} + debit",
                "Underlying must exceed this for profit at expiry.",
            ),
        ),
        screens=(
            "Reward:risk ≥ 1:1 unless high conviction",
            "Liquidity on both legs",
            "Event timing: enough DTE post-catalyst for move",
            "IV not so high that debit erodes edge vs spread",
            "Align long strike with technical trigger level",
        ),
        traps=(
            "Buying far OTM debit spreads as lottery tickets",
            "Spread too narrow — commissions dominate",
            "Holding through vol crush after event with no move",
            "Ignoring early assignment risk on short leg if ITM",
        ),
        catalysts=(
            "Pre-earnings directional view with capped cost",
            "Breakout entry with defined risk vs stock",
            "Vol cheap vs expected move (compare to straddle)",
        ),
        fate_hook="Payoff math parallels BS legs in `investing.formulas.derivatives`; no live options execution in default FATE stack — research overlay.",
        related=("credit_spreads", "options", "straddles", "breakout"),
        further_reading=(
            "Options Industry Council — spread tutorials",
            "Natenberg — vertical spread chapter",
        ),
    )
)

register(
    DeepChapter(
        topic_id="calendar_spreads",
        title="Calendar Spreads",
        family="derivatives",
        philosophy="""
Calendar (time) spreads sell near-term option and buy longer-dated option at
the *same strike*, betting on differential time decay and volatility term structure.
Front-month theta bleeds faster; back-month retains value if stock pins near
strike or forward vol rises. Classic play when front IV is inflated around
events while back month is relatively calm.

Max loss is typically net debit paid; profit peaks if underlying at short strike
at front expiry with elevated back-month value — a narrow peak, not a free lunch.
""".strip(),
        how_it_works="""
At-the-money calendar: sell 30 DTE call, buy 60 DTE call same K. If stock
near K at front expiry, short expires worthless, long still has time value.
Risk: large move away from strike hurts both legs differently; vol crush in
back month after event damages long. Double calendar adds put side for wider pin.

Manage before front expiry: close whole spread or roll short leg. Avoid
earnings on short leg unless explicitly trading vol crush dynamics.
""".strip(),
        formulas=(
            _F(
                "Calendar net debit",
                r"Debit = C_{long}(T_2) - C_{short}(T_1), \quad T_2 > T_1",
                "Upfront cost; max loss usually equals debit for long calendar.",
            ),
            _F(
                "Theta differential",
                r"\Theta_{net} \approx \Theta_{short} - \Theta_{long}",
                "Short near-term decays faster — positive theta if pinned.",
            ),
            _F(
                "Vol term structure",
                r"IV(T_1) vs IV(T_2)",
                "Ideal entry often inverted term structure around events.",
            ),
        ),
        screens=(
            "Front IV > back IV (event in front month)",
            "Strike at expected pin / max pain zone",
            "Plan exit date = 1–3 days before front expiry",
            "Underlying low event risk beyond front expiry",
            "Liquidity in both expiries",
        ),
        traps=(
            "Stock trends hard away from strike — both legs lose",
            "Vol crush hits long leg after event",
            "Early assignment on short American option",
            "Illiquid back month with wide spreads",
        ),
        catalysts=(
            "Earnings week IV inversion",
            "Known pin into OPEX at round strike",
            "Fed day front-month vol spike",
        ),
        fate_hook="Term-structure concept only in FATE today; BS pricing in `investing.formulas.derivatives` for leg marks.",
        related=("options", "volatility_trading", "iron_condors", "straddles"),
        further_reading=(
            "McMillan — calendar and diagonal spreads",
            "CBOE — volatility term structure papers",
        ),
    )
)

register(
    DeepChapter(
        topic_id="straddles",
        title="Straddles",
        family="derivatives",
        philosophy="""
A long straddle buys ATM call and ATM put — profiting from large moves in
either direction, paying combined premium as breakeven hurdle. It is a pure
long-vol, long-gamma bet: you need *realized* move to exceed *implied* move
priced into options. Short straddles sell both (income strategy) with unlimited
risk — institutional territory with strict risk controls.

Earnings are the textbook long straddle setup when you believe consensus
underprices the move; vol crush punishes longs if move is smaller than implied.
""".strip(),
        how_it_works="""
Long: buy call K, buy put K same expiry. Breakeven up = K + total premium;
down = K − premium. Max loss = premium if S = K at expiry. Short: sell both,
collect premium, need S to stay inside breakevens — short gamma danger.

FATE `straddle_payoff` computes expiry P&L for scenario analysis.
""".strip(),
        formulas=(
            _F(
                "Long straddle payoff",
                r"\Pi = |S_T - K| - (C + P)",
                "Intrinsic at expiry minus premiums paid.",
                "investing.formulas.derivatives.straddle_payoff",
            ),
            _F(
                "Breakevens",
                r"BE_{up} = K + premium, \quad BE_{down} = K - premium",
                "Move size required for profit at expiry.",
            ),
            _F(
                "Implied move (approx)",
                r"Move_{implied} \approx \frac{ATM_{straddle}}{S}",
                "Market-priced expected move into event.",
            ),
        ),
        screens=(
            "Compare implied move to historical earnings moves",
            "IV rank not at multi-year high before buying long",
            "Exit plan before vol crush post-event",
            "Liquidity at ATM strike",
            "Short straddle: margin and tail hedge defined",
        ),
        traps=(
            "Long straddle into peak IV (overpay)",
            "Short straddle on meme stock gap risk",
            "Ignoring gamma scalping costs intraday",
            "Hold through expiry with wide spreads on exit",
        ),
        catalysts=(
            "Earnings / FDA binary",
            "Election / FOMC surprise",
            "Merger rumor resolution",
        ),
        fate_hook="`investing.formulas.derivatives.straddle_payoff`; event overlap with `event_driven` / ML `is_earnings_day` features.",
        related=("strangles", "volatility_trading", "event_driven", "calendar_spreads"),
        further_reading=(
            "Natenberg — straddle and strangle chapters",
            "CBOE — implied move calculators",
        ),
    )
)

register(
    DeepChapter(
        topic_id="strangles",
        title="Strangles",
        family="derivatives",
        philosophy="""
A long strangle buys OTM call and OTM put — cheaper than straddle but requires
a *larger* move to profit. It is the retail-friendly pre-earnings vol play when
ATM straddle too expensive. Short strangles sell OTM wings (iron condor without
protection if naked — never naked for mortals).

You are still betting realized vol exceeds implied; just with lower upfront cost
and wider breakevens.
""".strip(),
        how_it_works="""
Choose call strike above spot, put strike below, same expiry. Total premium <
straddle. Profit if S beyond either breakeven at expiry. Often 10–15 delta wings
for balance of cost vs probability. Manage winners before expiry; don’t require
holding through last day theta cliff unless intentional.

Pair with stock hedge or convert to iron condor by selling further wings if
direction emerges.
""".strip(),
        formulas=(
            _F(
                "Long strangle payoff",
                r"\Pi = \max(S_T - K_c, 0) + \max(K_p - S_T, 0) - premium",
                "Sum of OTM leg intrinsics minus cost.",
            ),
            _F(
                "Breakevens",
                r"BE_{up} = K_c + premium, \quad BE_{down} = K_p - premium",
                "Wider apart than straddle due to OTM strikes.",
            ),
            _F(
                "Straddle vs strangle cost",
                r"Premium_{strangle} < Premium_{straddle}",
                "Cheaper but needs bigger move.",
            ),
        ),
        screens=(
            "Historical move exceeds implied + strangle distance",
            "Strikes beyond technical noise band",
            "IV elevated but straddle prohibitively expensive",
            "Event date before expiry",
            "Plan vol crush exit timing",
        ),
        traps=(
            "Move happens but not enough to clear wide breakevens",
            "Selling strangles without wing protection",
            "Pin between strikes at expiry — total loss",
            "Repeated lottery strangles bleeding premium",
        ),
        catalysts=(
            "Pre-earnings when implied move understates tail history",
            "FDA binary on biotech",
            "Macro shock week",
        ),
        fate_hook="Payoff analysis alongside `straddle_payoff` in `investing.formulas.derivatives`; earnings flags in ML features.",
        related=("straddles", "iron_condors", "event_driven", "volatility_trading"),
        further_reading=(
            "Tastytrade — strangle vs straddle studies",
            "Hull — combination strategies",
        ),
    )
)

register(
    DeepChapter(
        topic_id="butterfly",
        title="Butterfly Spreads",
        family="derivatives",
        philosophy="""
Butterfly spreads combine bull and bear verticals sharing a middle strike —
low-cost, high-payout-if-precise bets that underlying expires near the center
strike. Long butterfly: buy wing, sell 2× body, buy wing (calls or puts).
Max profit at pin to middle strike; max loss usually net debit (long fly).

They are lottery tickets with structure — cheap because probability of exact
pin is low. Used by traders expecting low movement into expiry or targeting
max pain / OPEX pin levels.
""".strip(),
        how_it_works="""
Call butterfly: buy K1 call, sell 2× K2 calls, buy K3 call with K2−K1 = K3−K2.
Pay small debit. Best outcome S = K2 at expiry. Short butterfly (sell body)
collects credit but dangerous — rare for retail. Iron butterfly is straddle
+ wings = short ATM straddle with defined risk like iron condor at same center.

Enter when cheap vs expected pin; exit before expiry week gamma swings if
profit target hit.
""".strip(),
        formulas=(
            _F(
                "Long call butterfly max profit",
                r"\Pi_{max} = (K_2 - K_1) - debit",
                "Achieved if S_T = K_2 at expiry.",
            ),
            _F(
                "Max loss",
                r"L_{max} = debit",
                "Net premium paid for long butterfly.",
            ),
            _F(
                "Iron butterfly relation",
                r"IC \approx \text{short straddle} + \text{long wings}",
                "Same center-strike pin logic with defined wings.",
            ),
        ),
        screens=(
            "Expect low movement or specific pin target",
            "Debit small vs wing width ( favorable odds display )",
            "Avoid into high-vol events unless intentional short fly",
            "OPEX week with max pain hypothesis",
            "Liquidity at all three strikes",
        ),
        traps=(
            "Stock moves away from body — 100% debit loss",
            "Commission eats tiny debit trades",
            "Confusing long vs short butterfly risk",
            "Pin theory wrong — stock never cooperates",
        ),
        catalysts=(
            "OPEX / quad witching pin dynamics",
            "Low IV environment cheap long flies",
            "Range-bound index into expiry",
        ),
        fate_hook="Research-only; payoff geometry complements `iron_condor_max_profit` credit/debit framing in `investing.formulas.derivatives`.",
        related=("iron_condors", "calendar_spreads", "range_trading", "options"),
        further_reading=(
            "Options Playbook — butterfly",
            "Max pain / OPEX pin literature (retail quant blogs)",
        ),
    )
)
