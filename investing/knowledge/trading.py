"""Trading styles & tactics — deep chapters (trading family)."""

from __future__ import annotations

from investing.knowledge import DeepChapter, FormulaSpec, register

_F = FormulaSpec

register(
    DeepChapter(
        topic_id="day_trading",
        title="Day Trading",
        family="trading",
        philosophy="""
Day trading closes every position before the session ends — no overnight gap
risk, no earnings bombs at 4:01 p.m. The appeal is immediate feedback and
leveraged attention on liquid names. The reality is brutal arithmetic: spreads,
commissions, and partial fills erode small edges; most discretionary day traders
underperform after costs. Success requires a defined setup, hard daily loss limits,
and emotional detachment from individual tickets.

Day trading is a profession, not a side hobby on lunch break. Treat it like
operating a machine: signals, size, stop, target, journal — repeat.
""".strip(),
        how_it_works="""
Pre-market: scan universe for gap, volume, catalyst, and prior-day structure.
During session: wait for setup (VWAP reclaim, opening range break, pullback to
support) with confirmation volume. Enter with predefined risk (R); exit at target,
time stop, or session flat rule. Post-market: review adherence to plan, not just
P&L.

FATE’s day-trade stack (`analytics/day_trade_engine.py`) scans Yahoo intraday
bars, ranks setups via `day_trade_rank`, enforces risk in `day_trade_risk`,
and mandates cash-out — mirroring professional flat-by-close discipline.
""".strip(),
        formulas=(
            _F(
                "RSI (Wilder)",
                r"RSI = 100 - \frac{100}{1 + RS}, \quad RS = \frac{\overline{gain}}{\overline{loss}}",
                "Overbought/oversold oscillator; context matters more than 70/30 folklore.",
                "investing.formulas.technical.rsi",
            ),
            _F(
                "Intraday VWAP",
                r"VWAP = \frac{\sum P_i V_i}{\sum V_i}",
                "Session volume-weighted fair price; institutions benchmark executions here.",
            ),
            _F(
                "Risk-reward",
                r"RR = \frac{target - entry}{entry - stop}",
                "Require RR ≥ 2:1 unless win rate is exceptionally high.",
            ),
        ),
        screens=(
            "Liquid: avg volume and tight spread",
            "Defined setup (OR break, VWAP bounce) — no impulsive clicks",
            "Daily max loss hit → flat and done",
            "Position size from stop distance, not gut",
            "Flat 5–15 min before close unless explicit hold rule",
        ),
        traps=(
            "Revenge trading after morning loss",
            "Chasing extended moves without pullback entry",
            "Ignoring halts and LULD volatility bands",
            "Overconfidence from one lucky week",
        ),
        catalysts=(
            "Gap on earnings/guidance with volume follow-through",
            "Sector sympathy move on peer news",
            "Index futures impulse at open",
        ),
        fate_hook="`analytics/day_trade_engine.py`, `day_trade_rank`, `day_trade_setups`, `day_trade_risk`; signals in `data/intel/day_trade_*.json`.",
        related=("scalping", "swing_trading", "breakout", "news_trading"),
        further_reading=(
            "Andrew Aziz — How to Day Trade for a Living",
            "SEC — Pattern day trader rule (FINRA 4210)",
        ),
    )
)

register(
    DeepChapter(
        topic_id="swing_trading",
        title="Swing Trading",
        family="trading",
        philosophy="""
Swing trading holds positions for days to weeks — long enough to capture a
move, short enough to avoid tying capital for quarters. It sits between day
trading’s noise and position trading’s macro patience. Edge comes from
identifying inflection points: pullbacks in trends, post-earnings drift,
sector rotation, or mean reversion at range extremes.

Overnight risk is real. Size positions assuming gaps against you. Swing traders
live on the daily chart but must respect intraday levels for entries and stops.
""".strip(),
        how_it_works="""
Identify trend or range on daily/4H chart. Wait for setup: flag breakout, RSI
dip in uptrend, MACD cross with price above 50-day MA. Enter on confirmation
candle; stop below structure (swing low, range floor). Target prior high,
measured move, or trail with MA. Hold 2–10 sessions typical; exit on stop,
target, or time if thesis stale.

FATE structure module scores swing context (HH/HL, S/R distance) for rank
boosts; hedge-fund trend and mean-reversion tilts align with swing horizons.
""".strip(),
        formulas=(
            _F(
                "MACD",
                r"MACD = EMA_{12} - EMA_{26}, \quad Signal = EMA_9(MACD)",
                "Momentum crossovers filter swing entries in direction of trend.",
                "investing.formulas.technical.macd",
            ),
            _F(
                "Trend score",
                r"trend \propto EMA_{short} - EMA_{long}",
                "EMA stack bullish when short above long.",
                "investing.formulas.technical.trend_score",
            ),
            _F(
                "Z-score stretch",
                r"Z = \frac{P - \mu}{\sigma}",
                "Buy dip when Z < −2 in established uptrend (not falling knife).",
                "investing.formulas.technical.zscore",
            ),
        ),
        screens=(
            "Daily trend aligned (price vs 20/50 MA)",
            "Setup at support with declining sell volume",
            "Risk ≤ 1–2% account per trade",
            "Catalyst or sector tailwind within hold window",
            "Avoid holding through binary events unless intentional",
        ),
        traps=(
            "Swing turn into bag-hold when stop ignored",
            "Buying breakout without volume confirmation",
            "Correlation cluster — five tech swings = one bet",
            "Earnings surprise gap through stop",
        ),
        catalysts=(
            "Post-earnings drift after beat + raise",
            "Sector ETF breakout pulling components",
            "Insider/cluster buy filing",
        ),
        fate_hook="`analytics/structure_patterns.py` for swing structure; `analytics/hedge_fund_stack` trend/mean-reversion boosts on multi-day horizon.",
        related=("position_trading", "trend_following", "breakout", "mean_reversion"),
        further_reading=(
            "Minervini — Trade Like a Stock Market Wizard",
            "Bulkowski — Encyclopedia of Chart Patterns",
        ),
    )
)

register(
    DeepChapter(
        topic_id="position_trading",
        title="Position Trading",
        family="trading",
        philosophy="""
Position trading takes multi-week to multi-month views driven by macro themes,
sector cycles, or fundamental inflection — closer to investing than scalping,
but still tactical on timing and sizing. The edge is patience and thesis clarity:
know *why* you hold, what would falsify the thesis, and how much drawdown you
can endure without panic selling the bottom.

Lower turnover reduces costs and tax friction. The cost is psychological:
watching 20% drawdowns while headlines scream crisis. Position traders need
written plans and position sizes that allow volatility to be noise, not ruin.
""".strip(),
        how_it_works="""
Build thesis (rate cycle, commodity squeeze, product cycle). Map to liquid
vehicles (ETFs, leaders, options overlay optional). Enter on technical
confirmation or scale in on dips. Size for 15–25% adverse move without
mandatory exit. Monitor thesis inputs monthly: data series, not daily quotes.
Exit on thesis break, valuation stretch, or better opportunity cost.

FATE position horizon aligns with ML long head (`LONG_HORIZON_DAYS`), fortress
min-hold, and fundamental ranks — multi-day to multi-week holding intent.
""".strip(),
        formulas=(
            _F(
                "Relative strength",
                r"RS = \frac{P_{stock}/P_{stock,0}}{P_{bench}/P_{bench,0}}",
                "Outperformance vs benchmark confirms leadership for trend positions.",
            ),
            _F(
                "Drawdown",
                r"DD = \frac{P_{peak} - P}{P_{peak}}",
                "Position size so max tolerable DD × leverage ≤ risk budget.",
            ),
            _F(
                "Sharpe (hold-period)",
                r"Sharpe = \frac{\mu - r_f}{\sigma}",
                "Evaluate position strategy on monthly returns, not daily noise.",
                "investing.formulas.quant.sharpe_ratio",
            ),
        ),
        screens=(
            "Thesis document with falsification triggers",
            "Liquidity adequate for full exit in ≤ 3 days",
            "Correlation to existing book understood",
            "Fundamental + technical alignment (not one alone)",
            "Plan for add/trim levels, not only entry",
        ),
        traps=(
            "Thesis drift — original reason gone, hope remains",
            "Illiquid small cap sized like large cap",
            "Ignoring macro shock that breaks correlation assumptions",
            "Confusing position trade with passive index hold",
        ),
        catalysts=(
            "Macro data confirming rate/ inflation path",
            "Sector earnings revision cycle turning up",
            "Policy shift (tariffs, subsidies) benefiting theme",
        ),
        fate_hook="`fortress_live.py` min-hold and ML long horizon; `ml_model.py` LONG_HORIZON_DAYS; rank pipeline for multi-week conviction names.",
        related=("trend_following", "buy_and_hold", "macro", "sector_rotation"),
        further_reading=(
            "Stan Weinstein — Secrets for Profiting in Bull and Bear Markets",
            "Livermore (annotated) — Reminiscences (position sizing lessons)",
        ),
    )
)

register(
    DeepChapter(
        topic_id="scalping",
        title="Scalping",
        family="trading",
        philosophy="""
Scalping targets the smallest repeatable price increments — ticks and cents —
with high trade count and strict discipline. One trade means little; edge is
law of large numbers minus costs. Scalpers need the best fees, fastest data,
and iron stops because a single oversized loss wipes dozens of winners.

Scalping is incompatible with distracted multitasking. It is microstructure
craft: reading the tape, level 2, and spread dynamics in real time.
""".strip(),
        how_it_works="""
Identify active liquid name with tight spread. Trade around known levels (VWAP,
prior H/L, whole/half dollars). Enter on brief imbalance or pullback; exit
quickly at fixed tick target or time stop (30–120 seconds to minutes). Never
average down. Daily cap on trades and loss.

FATE HFT research tools (`tools/hft_scalper_backtest.py`, OBI tape signals)
inform scalping edges on paper; production day-trade module uses coarser bars
but shares risk discipline.
""".strip(),
        formulas=(
            _F(
                "Expectancy per trade",
                r"E = p \cdot win - (1-p) \cdot loss",
                "Must exceed round-trip fees for positive edge.",
            ),
            _F(
                "Break-even win rate",
                r"p^* = \frac{loss}{win + loss}",
                "Higher payoff ratio lowers required win rate.",
            ),
            _F(
                "Z-score (micro mean reversion)",
                r"Z = \frac{P - \mu}{\sigma}",
                "Fade tiny extremes when spread stable.",
                "investing.formulas.technical.zscore",
            ),
        ),
        screens=(
            "Spread ≤ 1–2 ticks; depth on both sides",
            "Fixed target/stop in ticks before entry",
            "Max daily trades and loss limit",
            "Avoid first/last 5 min unless specialist",
            "Track fee drag explicitly",
        ),
        traps=(
            "Paying taker fees on both sides",
            "Scalp turning into swing when wrong",
            "Low-float halts and sweep risk",
            "Platform lag vs market quote",
        ),
        catalysts=(
            "Volatility expansion widening tick range",
            "News spike with sustained volume",
            "Open auction imbalance",
        ),
        fate_hook="`tools/hft_scalper_backtest.py`; OBI/tape in `hft/src/obi-tape/`; day-trade risk limits as coarse production cousin.",
        related=("day_trading", "hft", "mean_reversion", "range_trading"),
        further_reading=(
            "Bob Volman — Understanding Price Action (scalping focus)",
            "Hasbrouck — microstructure for tape readers",
        ),
    )
)

register(
    DeepChapter(
        topic_id="trend_following",
        title="Trend Following",
        family="trading",
        philosophy="""
Trend following bets that prices move persistently — winners keep winning,
losers keep losing — rather than reverting instantly. It is the antithesis of
“buy low, sell high” at every tick; it is “buy high, sell higher” once trend
confirms. Edge comes from catching fat tails; cost is whipsaw in ranges.

Systematic trend followers accept low win rates (40% is fine) because average
win >> average loss. Patience and uniform rules beat discretion mid-trade.
""".strip(),
        how_it_works="""
Define trend filter: price above 200 MA, 50>200 cross, MACD > 0, or Donchian
breakout. Enter on signal; initial stop below recent swing or ATR multiple.
Trail stop (chandelier, MA ratchet) to lock gains. Exit when filter flips or
stop hit — no narrative override.

FATE computes `trend_score` and MACD-based signals in `investing.formulas.technical`
and `analytics/hedge_fund_stack` for rank boosts on trending names.
""".strip(),
        formulas=(
            _F(
                "EMA trend spread",
                r"spread = \frac{EMA_{short} - EMA_{long}}{EMA_{long}}",
                "Normalized distance between moving averages.",
                "investing.formulas.technical.trend_score",
            ),
            _F(
                "MACD",
                r"MACD = EMA_{12} - EMA_{26}",
                "Sign and slope indicate momentum direction.",
                "investing.formulas.technical.macd",
            ),
            _F(
                "Breakout score",
                r"score \propto \frac{P - P_{lo}}{P_{hi} - P_{lo}}",
                "Near N-day high ⇒ bullish breakout tilt.",
                "investing.formulas.technical.breakout_score",
            ),
        ),
        screens=(
            "Higher highs + higher lows on daily chart",
            "Relative strength vs SPY positive 3–6 months",
            "Volume expansion on breakout bars",
            "Stop defined before entry (ATR or structure)",
            "Avoid late-stage parabolic without trail",
        ),
        traps=(
            "Trend following in mean-reverting chop",
            "Moving stop up too tight → shaken out before move",
            "Single-name trend without sector confirmation",
            "Leveraged ETF trend decay on daily reset products",
        ),
        catalysts=(
            "Index breakout pulling trend systems in",
            "Commodity supply shock sustaining momentum",
            "Rate regime shift favoring growth/value leadership",
        ),
        fate_hook="`investing.formulas.technical.trend_score`, `breakout_score`; live in `analytics/hedge_fund_stack` momentum/trend factors.",
        related=("breakout", "position_trading", "momentum", "swing_trading"),
        further_reading=(
            "Jesse Livermore / Trend following CTAs (S&P Diversified Trend Index)",
            "Covel — Trend Following",
        ),
    )
)

register(
    DeepChapter(
        topic_id="mean_reversion",
        title="Mean Reversion Trading",
        family="trading",
        philosophy="""
Mean reversion assumes prices temporarily overshoot fair value — driven by
panic, euphoria, or flow imbalances — and snap back toward average, VWAP, or
peer-relative norm. It fails catastrophically when the move is *informational*
not *emotional*: fraud, bankruptcy, paradigm shift. Context separates dip-buy
from catching a falling knife.

Best in range-bound, liquid markets with clear anchors. Pair with trend filter:
revert *within* uptrend pullbacks, not blind bottom-fishing in collapse.
""".strip(),
        how_it_works="""
Measure stretch: z-score vs 20-day mean, RSI < 30, price at lower Bollinger
band, or spread vs sector ETF. Enter when stretch extreme *and* stabilizing
(bullish candle, volume climax). Target mean or mid-band; stop below recent
low or band violation. Shorter hold than trend trades.

FATE: `mean_reversion_score` blends z-score and RSI; `signals/dip_momentum.py`
and hedge-fund stack apply dip-buy tilts when quality supports reversion.
""".strip(),
        formulas=(
            _F(
                "Z-score",
                r"Z = \frac{P - \mu}{\sigma}",
                "Standardized deviation from rolling mean; |Z| > 2 is stretched.",
                "investing.formulas.technical.zscore",
            ),
            _F(
                "Bollinger %B",
                r"\%B = \frac{P - lower}{upper - lower}",
                "0 = lower band, 1 = upper band; < 0 or > 1 = outside bands.",
                "investing.formulas.technical.bollinger",
            ),
            _F(
                "RSI",
                r"RSI = 100 - \frac{100}{1 + RS}",
                "RSI < 30 oversold in range contexts.",
                "investing.formulas.technical.rsi",
            ),
            _F(
                "Mean-reversion composite",
                r"MR = f(Z, RSI)",
                "FATE combined tilt for rank pipeline.",
                "investing.formulas.technical.mean_reversion_score",
            ),
        ),
        screens=(
            "No fundamental thesis break (earnings, guidance intact)",
            "Liquidity for exit at mean",
            "Z < −2 or RSI < 30 with stabilization candle",
            "Sector not in free-fall (peer check)",
            "Time stop if no reversion in N sessions",
        ),
        traps=(
            "Reversion in trending crash (value trap)",
            "Low-float name never mean-reverts — goes to zero",
            "Fading a short squeeze",
            "Using 20-day mean when regime shifted to new level",
        ),
        catalysts=(
            "Capitulation volume spike then base",
            "Index rebalance selling exhausted",
            "Short covering into close",
        ),
        fate_hook="`investing.formulas.technical.mean_reversion_score`; `signals/dip_momentum.py`; hedge-fund `mean_reversion` in stack.",
        related=("range_trading", "stat_arb", "contrarian", "swing_trading"),
        further_reading=(
            "Connors & Alvarez — Short Term Trading Strategies That Work",
            "Lo & MacKinlay — mean reversion in indexes",
        ),
    )
)

register(
    DeepChapter(
        topic_id="breakout",
        title="Breakout Trading",
        family="trading",
        philosophy="""
Breakout trading enters when price clears a defined ceiling — range high,
triangle apex, base — betting that trapped shorts, stop clusters, and momentum
buyers fuel continuation. The classic failure mode is the *false breakout*:
price pokes above resistance then reverses, triggering late longs’ stops.

Edge requires filtering: volume surge, close above level (not just wick),
market/sector tailwind, and retest-hold when possible.
""".strip(),
        how_it_works="""
Mark structure: N-day high, trendline, pattern boundary from swing pivots.
Set alert at break level + buffer (tick or ATR fraction). On break with volume
> average, enter; stop just below broken level (now support). Target measured
move (pattern height) or trail. If price fails back inside range quickly,
exit — false break rule.

FATE `analytics/structure_patterns.py` scores objective swing structure and
breakout context; `breakout_score` in technical formulas quantifies proximity
to range extremes for ranks.
""".strip(),
        formulas=(
            _F(
                "Breakout score",
                r"score \in [-1,1] \text{ from price vs N-day range}",
                "Near high ⇒ positive breakout tilt.",
                "investing.formulas.technical.breakout_score",
            ),
            _F(
                "Measured move",
                r"target = breakout + (base_{high} - base_{low})",
                "Classic pattern projection for reward estimate.",
            ),
            _F(
                "Volume confirmation",
                r"V_{break} > k \cdot \overline{V}_{20}",
                "k often 1.5–2×; low-volume breaks suspect.",
            ),
        ),
        screens=(
            "Consolidation ≥ 3–4 weeks (base maturity)",
            "Volume expansion on break bar",
            "Close above level, not intraday poke only",
            "RS vs market not lagging badly",
            "Stop below breakout level defined pre-trade",
        ),
        traps=(
            "Breakout into major resistance / 52w high supply",
            "Low-float pump with no volume follow-through",
            "Chasing 5%+ extension from break entry",
            "Ignoring market regime (bear market rally fade)",
        ),
        catalysts=(
            "Earnings gap through range",
            "Sector ETF breakout dragging laggards",
            "Short interest squeeze on clean break",
        ),
        fate_hook="`analytics/structure_patterns.py` swing/S/R scoring; `investing.formulas.technical.breakout_score` in rank composite.",
        related=("trend_following", "swing_trading", "structure", "momentum"),
        further_reading=(
            "Bulkowski — Chart pattern statistics",
            "Minervini — SEPA stage-2 breakout criteria",
        ),
    )
)

register(
    DeepChapter(
        topic_id="range_trading",
        title="Range Trading",
        family="trading",
        philosophy="""
Range trading buys support and sells resistance when price oscillates in a
horizontal channel — no higher highs or lower lows on the timeframe you trade.
It monetizes mean reversion inside boundaries. When ranges break, range traders
must stop fighting the new trend or face large losses.

Ideal in low-volatility, post-trend consolidation environments. Requires clear
visual and statistical bounds; fuzzy ranges produce fuzzy P&L.
""".strip(),
        how_it_works="""
Identify range high/low from swing pivots; confirm ADX low or flat MA slope.
Buy near support with stop below range; sell near resistance with stop above.
Alternatively fade Bollinger touches back toward mid-band. Reduce size near
middle (choppy). Exit entire approach if close outside range on volume (breakout
handoff to trend module).

FATE Bollinger and z-score tools map directly to range fades; structure module
detects flat S/R zones for context weighting.
""".strip(),
        formulas=(
            _F(
                "Bollinger bands",
                r"mid = \mu_{20}, \quad upper/lower = mid \pm 2\sigma",
                "Fade touches of outer bands in confirmed range.",
                "investing.formulas.technical.bollinger",
            ),
            _F(
                "Z-score at boundary",
                r"Z = \frac{P - \mu}{\sigma}",
                "Z ≈ ±2 at band extremes in Gaussian-ish ranges.",
                "investing.formulas.technical.zscore",
            ),
            _F(
                "Range width",
                r"width = \frac{high - low}{mid}",
                "Narrow width → eventual breakout energy building.",
            ),
        ),
        screens=(
            "≥ 2 touches each of support and resistance",
            "ADX < 20 or 50 MA slope flat",
            "No major catalyst imminent inside range",
            "Stop outside range boundary",
            "Take profit at opposite boundary or mid-band",
        ),
        traps=(
            "Range trading a slow bleed (lower highs) thinking it’s flat",
            "Full size at mid-range noise",
            "Ignoring breakout volume at boundary",
            "Ranges in dying illiquid names — boundaries lie",
        ),
        catalysts=(
            "Volatility contraction before earnings (iron condor season)",
            "Post-trend digestion phase",
            "Interim period between macro events",
        ),
        fate_hook="`investing.formulas.technical.bollinger`, `zscore`, `mean_reversion_score`; structure flat S/R in `analytics/structure_patterns.py`.",
        related=("mean_reversion", "iron_condors", "swing_trading", "volatility_trading"),
        further_reading=(
            "Connors — range-bound research on RSI(2)",
            "Pring — Technical Analysis Explained (trading ranges)",
        ),
    )
)

register(
    DeepChapter(
        topic_id="news_trading",
        title="News Trading",
        family="trading",
        philosophy="""
News trading reacts to information shocks — earnings, FDA, M&A rumors, macro
prints — before prices fully reflect the surprise. Speed and source quality
determine edge; sentiment without verification is gambling. The market discounts
headlines in seconds for liquid large caps; microcaps may drift minutes to days.

Trade the reaction structure: initial spike, fade, or continuation — not
the headline adjective alone (“great earnings” can sell off on guidance).
""".strip(),
        how_it_works="""
Monitor curated feeds (wire, SEC, trusted terminals). Classify event type and
historical reaction pattern. Pre-define: will this beat/miss move persist or
mean-revert? Enter on confirmation (hold above VWAP post-spike) or fade
overreaction when stats favor revert. Size smaller on binary FDA/legal events.
Always know halt rules.

FATE ingests news through sentiment pipelines; `sentiment_pipeline.py` and
intel engines score headlines for fortress buy/sell confidence modulation.
""".strip(),
        formulas=(
            _F(
                "Surprise (conceptual)",
                r"Surprise = \frac{Actual - Consensus}{|\Consensus|}",
                "Standardized earnings surprise drives initial gap magnitude.",
            ),
            _F(
                "Sentiment factor",
                r"F_{news} \in [-1,1]",
                "Aggregated NLP score with time decay.",
            ),
            _F(
                "Post-news drift",
                r"DRIFT = R_{t+1:t+k} \mid sign(Surprise)",
                "PEAD: post-earnings announcement drift literature.",
            ),
        ),
        screens=(
            "Source tier-1 (8-K, PR wire) not random social",
            "Liquidity sufficient for planned size in first 5 min",
            "Historical reaction template for this event type",
            "Spread not blown out 5× normal",
            "Flat or hedged into unrelated macro same day",
        ),
        traps=(
            "Trading headline without reading full text",
            "Front-running fake rumors",
            "Held through halt resume against you",
            "LLM summary wrong on numbers",
        ),
        catalysts=(
            "Earnings beat/miss + guidance change",
            "FDA approval/rejection binary",
            "M&A leak or definitive agreement",
        ),
        fate_hook="`sentiment_pipeline.py`, `intel/news_factor_engine.py`, fortress `_intel_news_factors` and `_news_supports_buy` gates.",
        related=("event_driven", "ai_investing", "day_trading", "earnings"),
        further_reading=(
            "Tetlock — Giving Content to Investor Sentiment",
            "Loughran & McDonald — textual analysis in finance",
        ),
    )
)

register(
    DeepChapter(
        topic_id="event_driven",
        title="Event-Driven Trading",
        family="trading",
        philosophy="""
Event-driven trading positions around *scheduled or discrete* corporate events
where payoff distribution is skewed: M&A spreads, spin-offs, earnings, restructurings,
index rebalances, regulatory rulings. Edge is superior scenario analysis — assigning
probabilities and losses to each branch — versus implied market odds.

Unlike pure news trading speed, event-driven often holds days to weeks through
a known calendar date, requiring legal doc literacy and risk caps on deal breaks.
""".strip(),
        how_it_works="""
Catalog event and branches (deal closes vs breaks; beat vs miss). Estimate
probability-weighted P&L. Enter when market price misprices odds vs your tree.
Hedge factor exposure if needed (market-neutral merger arb). Size by worst-case
loss (break fee, gap down). Exit on event resolution or thesis change.

FATE flags earnings via features (`is_earnings_day`, `days_to_earnings` in
`ml_model.py`); HFT earnings evaluator and special-situations knowledge
overlap for catalyst awareness.
""".strip(),
        formulas=(
            _F(
                "Merger spread (annualized)",
                r"Spread = \frac{Deal - P}{P}, \quad ann = Spread \times \frac{365}{days}",
                "Compensation for deal risk; compare to break-loss probability.",
            ),
            _F(
                "Expected value",
                r"EV = \sum_i p_i \cdot P\&L_i",
                "Probability-weighted outcomes across scenario tree.",
            ),
            _F(
                "Earnings surprise",
                r"Surprise = Actual - Consensus",
                "Drives initial gap; drift may follow sign.",
            ),
        ),
        screens=(
            "Legal docs read (merger agreement, collars, MAC clauses)",
            "Regulatory/antitrust path mapped",
            "Worst-case loss bounded and sized",
            "Calendar: know exact announcement datetime",
            "Liquidity for exit if deal breaks",
        ),
        traps=(
            "Merger arb without reading break triggers",
            "Illiquid target trapped on deal break",
            "Regulatory denial tail risk underpriced",
            "Spin-off stub ignored by index trackers temporarily — opportunity *and* trap",
        ),
        catalysts=(
            "Shareholder vote date",
            "HSR/regulatory decision window",
            "Earnings + guidance reset",
            "Index rebalance effective date",
        ),
        fate_hook="ML features `is_earnings_day` / `days_to_earnings`; `hft/src/earnings/earnings-evaluator.ts`; overlaps `special_situations` value chapter.",
        related=("news_trading", "special_situations", "merger_arbitrage", "earnings"),
        further_reading=(
            "Joel Greenblatt — You Can Be a Stock Market Genius",
            "Risk arb primers (Merger Arbitrage Limited)",
        ),
    )
)
