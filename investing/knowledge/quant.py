"""Quantitative investing — deep chapters (quant family)."""

from __future__ import annotations

from investing.knowledge import DeepChapter, FormulaSpec, register

_F = FormulaSpec

register(
    DeepChapter(
        topic_id="quant",
        title="Quantitative Investing",
        family="quant",
        philosophy="""
Quantitative investing replaces gut feel with reproducible rules: every position
must trace back to data, a model, and a risk budget. The edge is not clairvoyance
but process — systematic screening, disciplined sizing, and honest out-of-sample
validation. Markets are noisy; quant work accepts that most signals are weak and
combines many small edges rather than betting the farm on one indicator.

The discipline cuts both ways. Automation removes emotional churn but amplifies
model error if research is sloppy. A quant must be as skeptical of backtests as
a value investor is of hockey-stick DCFs. Live trading is where correlation
regimes shift, costs bite, and capacity limits appear. Humility and monitoring
are part of the strategy, not afterthoughts.
""".strip(),
        how_it_works="""
The pipeline: (1) define the investable universe and data feeds, (2) engineer
features (returns, volatility, fundamentals, alt data), (3) estimate signals
or forecast distributions, (4) map signals to portfolio weights with explicit
risk constraints, (5) execute with cost-aware algorithms, (6) monitor drift,
drawdown, and factor exposures in production.

Quant stacks rarely rely on a single model. FATE blends factor tilts, ML horizon
heads, sentiment overlays, and hedge-fund-style micro-signals into rank scores
rather than one monolithic alpha. Research hygiene matters: walk-forward splits,
purged cross-validation around corporate events, and stress tests when volatility
regimes flip. Position sizing uses volatility scaling or Kelly fractions capped
for robustness. The goal is a repeatable decision function that survives bad
quarters without abandoning the process.
""".strip(),
        formulas=(
            _F(
                "CAPM expected return",
                r"E[R_i] = r_f + \beta_i (R_m - r_f)",
                "Baseline required return given market beta. β > 1 amplifies market swings; β < 1 dampens them.",
                "investing.formulas.quant.capm_expected_return",
            ),
            _F(
                "Sharpe ratio",
                r"Sharpe = \frac{E[R - r_f]}{\sigma(R)}",
                "Return per unit of total volatility. Compare strategies only when inputs are consistently annualized.",
                "investing.formulas.quant.sharpe_ratio",
            ),
            _F(
                "Sortino ratio",
                r"Sortino = \frac{E[R - r_f]}{\sigma_{\downarrow}(R)}",
                "Like Sharpe but penalizes downside deviation only — better when upside volatility is desirable.",
                "investing.formulas.quant.sortino_ratio",
            ),
            _F(
                "Kelly fraction (conceptual)",
                r"f^* = \frac{edge}{odds}",
                "Optimal bet size for repeated independent edges; in practice use fractional Kelly to survive estimation error.",
                "investing.formulas.quant.kelly_fraction",
            ),
        ),
        screens=(
            "Signal IC / hit rate stable out-of-sample (not just in-sample R²)",
            "Turnover and transaction costs modeled before live deployment",
            "Max drawdown and tail scenarios within mandate",
            "Correlation to existing book — avoid accidental factor doubling",
            "Capacity: ADV participation limits respected for each name",
        ),
        traps=(
            "Overfitting: 50 parameters on 50 stocks",
            "Survivorship bias and point-in-time fundamental errors",
            "Regime change: a model trained in low-vol bleeds in crises",
            "False precision: three decimal places on noisy estimates",
            "Ignoring microstructure and slippage at scale",
        ),
        catalysts=(
            "New data sources with genuine information lead",
            "Regime shift where your factor historically mean-reverts",
            "Competitor exit reducing crowding in a niche signal",
        ),
        fate_hook="Core math in `investing.formulas.quant`. Rank pipeline blends quant signals via `analytics.hedge_fund_stack`, `ml_model.py`, and `fortress_live.py`.",
        related=("factor", "ml_investing", "risk_parity", "algo_trading"),
        further_reading=(
            "Ernie Chan — Quantitative Trading",
            "Marcos López de Prado — Advances in Financial Machine Learning",
        ),
    )
)

register(
    DeepChapter(
        topic_id="factor",
        title="Factor Investing",
        family="quant",
        philosophy="""
Factor investing asks: *which characteristics*, not *which stories*, explain
long-run returns? Decades of research identify tilts — value, size, momentum,
quality, low volatility — that compensate investors for bearing systematic risks
or behavioral biases. A factor portfolio is a deliberate bet that these premia
persist after costs, even if any single year disappoints.

Factors are not free lunch. They can underperform for years (momentum crashes,
value traps in growth bubbles). Implementation details — definition of “cheap,”
rebalance frequency, sector neutrality — matter as much as the academic label.
Smart investors treat factors as *tilts* within a diversified core, not religion.
""".strip(),
        how_it_works="""
Start from a benchmark universe. Score each name on factor proxies: low P/B and
P/E for value, market cap for size, 12–1 month return for momentum, ROE and
leverage for quality, trailing vol for low-vol. Combine scores with weights
reflecting conviction and correlation. Long the top decile, short the bottom
(for a long-only mandate, overweight top vs underweight bottom), rebalance on
a fixed calendar or when drift exceeds bands.

Monitor factor crowding, turnover, and exposure drift. Multi-factor blends
smooth single-factor pain: value + momentum + quality historically diversifies
some drawdown paths. FATE computes composite factor tilts from fundamentals
and price features, feeding rank boosts in the hedge-fund stack.
""".strip(),
        formulas=(
            _F(
                "Fama-French 3-factor",
                r"E[R] = r_f + \beta_m MKT + \beta_s SMB + \beta_v HML",
                "Market, size (SMB), and value (HML) premia explain much cross-sectional return variation.",
                "investing.formulas.quant.fama_french_expected",
            ),
            _F(
                "Factor tilt composite (FATE)",
                r"score = w_v V + w_s S + w_m M + w_q Q",
                "Blends value, size, momentum, quality proxies into a single rank tilt in [-1, 1].",
                "investing.formulas.quant.factor_tilt_score",
            ),
            _F(
                "CAPM beta (building block)",
                r"\beta_i = \frac{\mathrm{Cov}(R_i, R_m)}{\mathrm{Var}(R_m)}",
                "Market exposure before layering style factors; used for risk attribution.",
                "investing.formulas.quant.capm_expected_return",
            ),
        ),
        screens=(
            "Value: low P/B, P/E vs sector; avoid extreme distress without catalyst",
            "Momentum: positive 6–12m return, skip last month (short-term reversal)",
            "Quality: high ROE, stable margins, moderate leverage",
            "Low vol: bottom quintile trailing σ, liquidity adequate",
            "Neutralize unintended sector/industry bets if mandate requires",
        ),
        traps=(
            "Factor timing based on one bad year",
            "Double-counting value in both P/B screen and deep-value module",
            "Ignoring reconstitution effects in index-like factor products",
            "Capacity: small-cap value names illiquid for large AUM",
        ),
        catalysts=(
            "Style rotation after prolonged factor drawdown",
            "Index rebalance flows into factor ETFs",
            "Earnings season confirming quality vs junk divergence",
        ),
        fate_hook="`analytics.hedge_fund_stack.factor_scores_from_row` and `factor_tilt_score` in `investing.formulas.quant`. Live rank boosts when `USE_HEDGE_FUND_STACK=true`.",
        related=("smart_beta", "quant", "value", "momentum"),
        further_reading=(
            "Fama & French — Common risk factors in stock returns",
            "Andrew Ang — Factor Investing",
        ),
    )
)

register(
    DeepChapter(
        topic_id="smart_beta",
        title="Smart Beta",
        family="quant",
        philosophy="""
Smart beta sits between passive cap-weight indexing and active stock picking:
transparent, rules-based portfolios that *tilt* toward factors investors want
(value, momentum, quality, low vol) without paying for closet indexing or opaque
discretion. **Enhanced index** is the same family under another label — still
tracks a universe like the S&P 500, but weights by chosen factors instead of
market cap alone (cap-weighting forces you to own more of whatever already got
expensive). The promise is better risk-adjusted outcomes than pure market-cap
weighting at lower cost than traditional active management.

The catch is that “smart” / “enhanced” is marketing when rules are naive. Equal-weight,
fundamental-weight, and factor-weight all change turnover, sector bets, and
crisis behavior versus SPY. Due diligence means reading the index methodology,
not the brochure tagline.
""".strip(),
        how_it_works="""
A smart-beta index defines a universe (e.g. S&P 500), a scoring rule (e.g.
composite value + quality), and a weighting scheme (rank-weight, inverse vol,
or capped equal). Constituents rebalance periodically; the ETF or custom
portfolio tracks the rule set. Investors choose smart beta to express a view
(“I want cheaper, profitable large caps”) without hiring a PM to pick names.

Implementation compares factor loading, tracking error vs cap-weight benchmark,
expense ratio, and tax efficiency. In FATE, smart-beta *ideas* appear as
factor tilts inside the rank pipeline rather than as a separate ETF sleeve —
same math, different packaging.
""".strip(),
        formulas=(
            _F(
                "Rank-weight (conceptual)",
                r"w_i \propto rank(score_i)^{\alpha}",
                "Higher-ranked factor scores get more weight; α controls concentration.",
            ),
            _F(
                "Fundamental weight",
                r"w_i \propto \frac{1}{P/E_i} \text{ or } \frac{Sales_i}{MktCap_i}",
                "Weight by economic size rather than market cap — reduces bubble overweight.",
            ),
            _F(
                "Factor tilt score",
                r"score_i = f(P/B, P/E, mcap, mom, ROE)",
                "Same composite used for smart-beta-style tilts in FATE ranks.",
                "investing.formulas.quant.factor_tilt_score",
            ),
        ),
        screens=(
            "Methodology doc: rebalance frequency, sector caps, liquidity filters",
            "Historical factor loading vs stated objective (value? quality?)",
            "Turnover and tax drag in taxable accounts",
            "Expense ratio vs DIY factor portfolio feasibility",
            "Crisis behavior: low-vol smart beta can lag sharp rallies",
        ),
        traps=(
            "Smart beta = always beats cap-weight (false)",
            "Hidden sector bets (e.g. low-vol → utilities overload)",
            "Backtested index with favorable rebalance dates",
            "Confusing smart beta ETF with leveraged product",
        ),
        catalysts=(
            "Flows into factor ETFs after style leadership shifts",
            "Index provider rule changes affecting holdings",
            "Regulatory or tax changes favoring transparent rules",
        ),
        fate_hook="Factor scores in `analytics.hedge_fund_stack`; `factor_tilt_score` in `investing.formulas.quant`. Equivalent tilts applied in rank boosts, not a separate ETF wrapper.",
        related=("factor", "index_investing", "etf_investing", "risk_parity"),
        further_reading=(
            "BlackRock — Smart beta guide",
            "Research Affiliates — Fundamental Indexation",
        ),
    )
)

register(
    DeepChapter(
        topic_id="stat_arb",
        title="Statistical Arbitrage",
        family="quant",
        philosophy="""
Statistical arbitrage hunts mean-reverting spreads between related securities —
pairs, baskets, ETFs vs NAV — rather than betting on market direction. The edge
is modest per trade but stacks when many independent relationships are monitored
with tight risk controls. It is the quantitative cousin of pair trading, often
run market-neutral so beta exposure does not dominate P&L.

Relationships break. Cointegration today is not marriage forever: mergers,
regulatory shifts, or product divergence can permanently widen a historical
spread. Stat arb therefore demands stop rules, position limits, and humility
when z-scores stay extreme “longer than expected.”
""".strip(),
        how_it_works="""
Identify pairs or clusters with stable co-movement (correlation, cointegration
tests on rolling windows). Compute the spread: log price ratio or residual from
a regression. Standardize to a z-score. When |z| exceeds entry threshold,
go long the laggard and short the leader (or vs index hedge). Exit when z
mean-reverts toward zero or stop if z blows out further.

FATE implements a lightweight stat-arb tilt: configured peer map (KO:PEP, etc.),
rolling spread z-score, rank boost when dislocation is extreme and expected to
close. Full market-neutral books also require borrow, financing, and short
locate — beyond paper-equity defaults but conceptually aligned.
""".strip(),
        formulas=(
            _F(
                "Spread z-score",
                r"Z = \frac{S - \mu_S}{\sigma_S}",
                "Standardized spread; entry often at |Z| > 2, exit near 0.",
                "investing.formulas.technical.zscore",
            ),
            _F(
                "Pair spread (log)",
                r"S_t = \ln(P_A) - \beta \ln(P_B)",
                "Hedge ratio β from rolling regression; residual spread mean-reverts if pair is cointegrated.",
            ),
            _F(
                "Mean-reversion composite",
                r"MR = f(Z, RSI)",
                "FATE blends z-score and RSI for short-horizon reversion tilt.",
                "investing.formulas.technical.mean_reversion_score",
            ),
        ),
        screens=(
            "Rolling correlation > threshold over 60–120 sessions",
            "Cointegration or half-life of spread acceptable for holding period",
            "Liquidity on both legs; short borrow feasible if truly neutral",
            "Entry |z| ≥ 2 with planned exit at z ≈ 0.5 or time stop",
            "Not during known structural break (M&A, index deletion)",
        ),
        traps=(
            "Spurious correlation in small samples",
            "Convergence takes longer than capital patience",
            "Short squeeze on the hedge leg",
            "Ignoring dividends and corporate actions in spread math",
        ),
        catalysts=(
            "Earnings divergence then normalization across peers",
            "Index rebalancing forcing temporary dislocations",
            "Sector rotation leaving one name temporarily orphaned",
        ),
        fate_hook="`analytics.hedge_fund_stack.stat_arb_pair_signal` with `PAPER_SIM_PAIR_MAP`; z-score helper in `investing.formulas.technical`.",
        related=("pair_trading", "mean_reversion", "market_neutral", "quant"),
        further_reading=(
            "Andrew Pole — Statistical Arbitrage",
            "Ernie Chan — Algorithmic Trading (pairs chapter)",
        ),
    )
)

register(
    DeepChapter(
        topic_id="risk_parity",
        title="Risk Parity",
        family="quant",
        philosophy="""
Risk parity asks a different question than equal-dollar weighting: *equal risk
contribution*, not equal capital. Low-volatility assets (bonds) get more weight;
high-volatility assets (equities) get less — often with leverage on the safer
leg so expected return stays competitive. The goal is smoother paths through
macro regimes where stock-bond correlation shifts.

It is not magic. Leverage introduces path dependency and funding risk. In
equity-only sleeves, inverse-vol weighting is the practical cousin: overweight
stable names without cross-asset leverage. Understand which variant you run.
""".strip(),
        how_it_works="""
Estimate each asset’s volatility (σ) over a lookback window. Assign weights
proportional to 1/σ, normalized to sum to 1. Rebalance when vol estimates or
weights drift. Multi-asset risk parity extends to bonds, commodities, and FX
with correlation-aware risk budgets (ERC — equal risk contribution).

In FATE’s equity context, inverse-vol weights appear as a portfolio construction
helper and inform position sizing: smaller weight to chaotic small caps, larger
to stable large caps when vol-scaling. Full Bridgewater-style all-weather books
add leverage and macro overlays outside the default stack.
""".strip(),
        formulas=(
            _F(
                "Inverse-vol weights",
                r"w_i = \frac{1/\sigma_i}{\sum_j 1/\sigma_j}",
                "Naive risk parity: each name contributes inversely proportional to its volatility.",
                "investing.formulas.quant.inverse_vol_weights",
            ),
            _F(
                "Volatility (annualized)",
                r"\sigma = \sqrt{252} \times \mathrm{std}(r_{daily})",
                "Rolling std of daily returns, scaled to annual units for comparability.",
            ),
            _F(
                "Sharpe (evaluation)",
                r"Sharpe = \frac{\mu - r_f}{\sigma}",
                "Judge whether risk parity improved return *per unit risk* vs cap-weight.",
                "investing.formulas.quant.sharpe_ratio",
            ),
        ),
        screens=(
            "Use sufficiently long vol lookback (60–120d) but not so long it lags regime shifts",
            "Floor σ to avoid infinite weight on dead calm names",
            "Cap max single-name weight for concentration limits",
            "If multi-asset: estimate correlation matrix, not vol alone",
            "Stress test with rising rates / equity-bond correlation → +1",
        ),
        traps=(
            "Leveraged bond sleeve in rising-rate decade",
            "Inverse-vol → overcrowding in same low-vol defensives",
            "Vol estimate noise in small samples",
            "Confusing risk parity with minimum-variance (different objective)",
        ),
        catalysts=(
            "Vol crush after crisis — rebalance buys beaten high-σ names",
            "Macro shift favoring balanced risk budgets",
            "Institutional flows into risk-parity mutual funds",
        ),
        fate_hook="`investing.formulas.quant.inverse_vol_weights` for weight construction; vol scaling in risk modules and position sizing across fortress/day-trade paths.",
        related=("quant", "low_volatility", "portfolio_construction", "leveraged_investing"),
        further_reading=(
            "Ray Dalio — All Weather principles",
            "Qian — Risk parity fundamentals",
        ),
    )
)

register(
    DeepChapter(
        topic_id="ml_investing",
        title="Machine Learning Investing",
        family="quant",
        philosophy="""
Machine learning investing uses algorithms to map high-dimensional features
to return, direction, or risk outcomes — without hand-crafting every rule.

**Most important idea:** ML’s job in markets is to find subtle connections in
historical stock prices (and related features) that are completely invisible to
regular humans — lag structures, nonlinear interactions, and regime-conditioned
patterns no discretionary checklist would invent. Self-improving systems adjust
formulas over time so later trades can be sharper *when* the signal is real.

The danger is overfitting: ML excels at memorizing history and calling it alpha.
Discipline separates toy models from production: strict train/test splits,
walk-forward validation, feature parity between train and live, and monitoring
when distribution drift erodes edge. ML is a tool inside a risk framework, not
a substitute for position limits and cost awareness.
""".strip(),
        how_it_works="""
Pipeline: (1) build feature matrix (technicals, sentiment lags, vol regime,
industry co-movement, cross-sectional co-movement), (2) label forward returns or
binary up/down over horizons (e.g. 5d short, 20d long), (3) train classifiers or
regressors with regularization aimed at those subtle historical links, (4)
calibrate probabilities, (5) blend horizon heads into rank scores with caps,
(6) retrain on schedule with champion/challenger gates and OOS gates so
“invisible” patterns are not just in-sample ghosts.

FATE’s `ml_model.py` trains short- and long-horizon sklearn models on engineered
features, caches bundles, and exposes `predict_row_details` for live inference.
Outputs feed fortress rank blending — never raw auto-trade without risk gates.
""".strip(),
        formulas=(
            _F(
                "Binary classification edge",
                r"edge = P(up) - 0.5",
                "Centered probability as a soft signal; clip before sizing.",
            ),
            _F(
                "Expected return link (conceptual)",
                r"E[r] \approx \sum_k P_k \cdot \bar{r}_k",
                "Blend horizon-specific average outcomes weighted by model probability.",
            ),
            _F(
                "Sharpe for model evaluation",
                r"Sharpe = \frac{\mu_{portfolio}}{\sigma_{portfolio}}",
                "Judge the *strategy* implied by signals, not in-sample accuracy alone.",
                "investing.formulas.quant.sharpe_ratio",
            ),
        ),
        screens=(
            "Hold-out accuracy / AUC stable across rolling windows",
            "Feature importances economically sensible (not random noise)",
            "Live feature pipeline matches training (`build_features` parity)",
            "Probability calibration checked (reliability diagram)",
            "Max weight cap on ML contribution to final rank",
        ),
        traps=(
            "Leakage: future data in features or labels",
            "Accuracy obsession — 51% with bad payoff asymmetry loses",
            "Retrain too often → overfit to recent noise",
            "Black box without kill switch when drift detected",
        ),
        catalysts=(
            "New feature class (alt data) with genuine OOS lift",
            "Regime where historical patterns reassert",
            "Model ensemble reducing variance vs single head",
        ),
        fate_hook="`ml_model.py`: FEATURES list, train/inference, horizon heads; blended in `fortress_live.py` rank path with `predict_row_details`.",
        related=("ai_investing", "quant", "algo_trading", "alt_data"),
        further_reading=(
            "Marcos López de Prado — Advances in Financial Machine Learning",
            "Stefan Jansen — Machine Learning for Algorithmic Trading",
        ),
    )
)

register(
    DeepChapter(
        topic_id="forecast_combination",
        title="Forecast Combination & Precision Weights",
        family="quant",
        philosophy="""
A single model is almost never the most accurate forecast. Bates and Granger
(1969) showed that a combination of unbiased forecasts, weighted by inverse
error variance, has lower MSE than the best individual model. In log-odds
space (Jaynes), independent evidence *adds*; averaging raw probabilities
understates agreement and overstates a loud but noisy head.

Grinold and Kahn make the same idea operational for active management:
weight ∝ information coefficient / residual risk. FATE uses that algebra
for horizon heads (short/long/daily/xlong), hedge-fund factor tilts, and
investing-book family scores so a pick is *more sure* only when independent
signals agree.
""".strip(),
        how_it_works="""
1. Convert each head’s P(up) to logit ℓ = log(p/(1−p)).
2. Assign precision weights w_i ∝ skill_i / σ_i², then L1-normalize so Σ w = 1
   and w ≥ 0 (an evolver cannot invert a sleeve factor).
3. Fuse ℓ* = Σ w_i ℓ_i, p* = σ(ℓ*).
4. Execution confidence uses p* extremity *and* signed short/long agreement.
   If heads disagree below EXEC_MIN_AGREE, the dual gate fails — size does
   not go to full half-Kelly. Copies of p* passed as p_short/p_long are ignored.
""".strip(),
        formulas=(
            _F(
                "Inverse-variance combination",
                r"w_i = \frac{\sigma_i^{-2}}{\sum_j \sigma_j^{-2}}",
                "Bates–Granger: quieter (lower error variance) forecasts get more weight.",
                "analytics.vector_math.precision_weights",
            ),
            _F(
                "Logit evidence fuse",
                r"p^* = \sigma\!\left(\sum_i w_i \logit(p_i)\right)",
                "Evidence lives in log-odds; weights act on evidence, not on raw p.",
                "analytics.vector_math.logit_blend",
            ),
            _F(
                "Signed horizon agreement",
                r"agree = \min(s_{short}, s_{long})_+",
                "Both horizon heads must back the live direction or exec-conf cannot clear the dual gate.",
                "analytics.vector_math.signed_agreement",
            ),
            _F(
                "Fractional Kelly (after fusion)",
                r"f = \tfrac12 \frac{p^* b - (1-p^*)}{b}",
                "Size on fused p*, never on an unnormalized additive rank.",
                "investing.formulas.quant.kelly_fraction",
            ),
        ),
        screens=(
            "Horizon heads independent (not copies of fused p)",
            "Weight vector sums to 1 after overlay deltas",
            "Disagreeing short vs long fails EXEC_MIN_AGREE",
            "News/Cramer share of book blend stays a small L1 slice",
        ),
        traps=(
            "Linear mix of probabilities near 0/1",
            "Unnormalized env knobs (0.85 + 0.38 + 0.22 > 1)",
            "Fake agreement by passing p_entry as p_short and p_long",
            "Evolver overlay flipping factor signs",
        ),
        catalysts=(
            "New OOS skill / variance estimates for precision weights",
            "Additional independent heads (LSTM, neural) fused in LEA not Δp",
        ),
        fate_hook="`analytics/vector_math.py` precision_fuse / logit_blend; live path in `ml_model.py`, `fortress_live.py`, `analytics/execution_confidence.py`, `analytics/hedge_fund_stack.py`, `investing/integrate.py`.",
        related=("quant", "ml_investing", "ai_investing", "algo_trading"),
        further_reading=(
            "Bates & Granger (1969) — The Combination of Forecasts",
            "E.T. Jaynes — Probability Theory: The Logic of Science (log-odds)",
            "Grinold & Kahn — Active Portfolio Management (IR, IC, breadth)",
            "Edward O. Thorp — Beat the Dealer / Kelly criterion",
            "Timmermann (2006) — Forecast Combinations",
        ),
    )
)

register(
    DeepChapter(
        topic_id="ai_investing",
        title="AI Investing",
        family="quant",
        philosophy="""
AI investing extends quant and ML with large language models, transformers, and
multimodal systems that read news, transcripts, filings, and audio at scale —
tasks impractical for human analysts on a 500-name universe. The edge is speed
and breadth: detecting sentiment shifts, management tone changes, and thematic
risks before they fully price.

AI is not oracle. Models hallucinate, lag on breaking news, and inherit training
biases. Human judgment remains essential for corporate actions, fraud, and
context LLMs lack. Treat AI outputs as *features* feeding ranks and risk flags,
not autonomous portfolio managers.
""".strip(),
        how_it_works="""
Ingest text streams (headlines, SEC filings, earnings call transcripts). Run
sentiment classifiers, entity linking, and topic tagging. Aggregate to ticker-level
scores with decay (recent news weighs more). Combine with price action and
fundamentals in the rank pipeline. Optional: embedding similarity for thematic
baskets, anomaly detection on language vs historical baseline.

FATE wires news and transcript factors through sentiment pipelines and intel
modules; fortress blends `_intel_news_factors` and sentiment into buy confidence.
Cramer/Club analyzers exemplify specialized AI overlays on named sources.
""".strip(),
        formulas=(
            _F(
                "Sentiment score",
                r"S \in [-1, 1] \text{ or } [0, 1]",
                "Normalized tone from NLP; decay-weight recent items.",
            ),
            _F(
                "Decayed news factor",
                r"F_t = \sum_i w_i e^{-\lambda \Delta t_i} \cdot sentiment_i",
                "Fresh headlines dominate stale ones; λ sets half-life.",
            ),
            _F(
                "Blended confidence (FATE soft)",
                r"conf = f(p_{ML}, sentiment, news\_factor, hf\_boost)",
                "AI sentiment modulates but does not override risk gates.",
            ),
        ),
        screens=(
            "Source quality tier (wire > social rumor)",
            "Entity resolution correct (ticker not homonym)",
            "Sentiment shift magnitude vs 30d baseline",
            "Corroboration: price/volume confirms or denies narrative",
            "Hallucination guard on numeric claims from LLM summaries",
        ),
        traps=(
            "Headline trading without reading body/context",
            "Prompt injection or spam flooding alt feeds",
            "Overfitting sentiment lexicon to one regime",
            "Ignoring that markets discount news in milliseconds for liquid names",
        ),
        catalysts=(
            "Earnings call tone divergence from consensus",
            "Breaking macro headline repricing sector",
            "Regulatory filing revealing undisclosed risk",
        ),
        fate_hook="`sentiment_pipeline.py`, `intel/news_factor_engine.py`, fortress `_intel_news_factors` / `_fortress_blend_sentiment`; transcript factors in catalog.",
        related=("news_trading", "ml_investing", "alt_data", "event_driven"),
        further_reading=(
            "NLP for Finance surveys (SSRN)",
            "OpenAI / industry papers on financial document understanding",
        ),
    )
)

register(
    DeepChapter(
        topic_id="algo_trading",
        title="Algorithmic Trading",
        family="quant",
        philosophy="""
Algorithmic trading automates the last mile: turning portfolio targets into
orders with consistent timing, sizing, and execution logic. Humans decide the
*what*; algorithms handle the *how* — TWAP/VWAP slices, limit vs market,
cancel-replace rules, and kill switches when feeds stall.

Speed and determinism reduce emotional trading but expose you to software bugs,
stale quotes, and partial fills. Algo trading without monitoring is reckless;
the system must log every decision and fail safe when data is suspect.
""".strip(),
        how_it_works="""
Signal layer produces desired positions (from ranks, ML, or manual). Risk layer
caps gross/net exposure, single-name weight, and daily loss. Execution layer
translates deltas into orders via broker API (Alpaca in FATE), respecting
min lot sizes, halts, and session hours. Post-trade: reconcile fills, update
positions, log slippage vs arrival price.

FATE’s live loop in `fortress_live.py` and `alpaca_broker.py` implements
systematic entries/exits with confidence thresholds, min-hold timers, and
accuracy-mode gates. Paper sim paths mirror logic for research parity.
""".strip(),
        formulas=(
            _F(
                "Position delta",
                r"\Delta q = q_{target} - q_{current}",
                "Shares to buy/sell to reach target weight.",
            ),
            _F(
                "Slippage",
                r"slip = \frac{P_{fill} - P_{decision}}{P_{decision}}",
                "Implementation shortfall per order; aggregate to evaluate execution quality.",
            ),
            _F(
                "Kelly-capped size (optional)",
                r"size = \min(f^*_{Kelly}, cap) \times equity",
                "Optional sizing link from quant module.",
                "investing.formulas.quant.kelly_fraction",
            ),
        ),
        screens=(
            "Pre-trade: liquidity, spread, halt status",
            "Order type appropriate (limit in thin names, market when urgent)",
            "Daily loss limit and max orders/minute",
            "Reconciliation: broker position == internal book",
            "Clock sync and feed staleness alarms",
        ),
        traps=(
            "Runaway loop submitting duplicate orders",
            "Trading through stale Yahoo/Alpaca quotes",
            "Ignoring partial fills and open order backlog",
            "Weekend/on-holiday cron firing without session check",
        ),
        catalysts=(
            "Vol spike requiring faster execution or wider limits",
            "Broker API upgrade reducing latency",
            "New risk gate preventing historical bug class",
        ),
        fate_hook="`alpaca_broker.py` execution; `fortress_live.py` scan/buy/sell loop; `paper_sim_today.py` for research parity.",
        related=("automated_portfolio", "hft", "day_trading", "ml_investing"),
        further_reading=(
            "Barry Johnson — Algorithmic Trading & DMA",
            "SEC — Market access rule (Rule 15c3-5) overview",
        ),
    )
)

register(
    DeepChapter(
        topic_id="hft",
        title="High-Frequency Trading",
        family="quant",
        philosophy="""
High-frequency trading operates at millisecond to second horizons, profiting
from microstructure inefficiencies — order book imbalance, queue position,
short-lived arbitrage — rather than quarterly earnings. Edges are tiny per trade;
volume and technology determine whether net of fees works. HFT is not “better
day trading”; it is a different industrial process with colocation, feed
handlers, and strict inventory limits.

Retail and paper stacks cannot compete on raw speed with dedicated HFT firms,
but *microstructure-aware* signals (OBI, tape velocity) still inform short-horizon
tilts and sanity-check execution quality.
""".strip(),
        how_it_works="""
Low-latency stack ingests full depth-of-book and trade prints. Signals compute
imbalance: bid vs ask size, cancel rates, aggressor side velocity. Strategies
market-make, latency-arb related listings, or momentum-ignition fade — always
with inventory caps and auto-flatten rules. Risk kills on feed gap, widening
spread, or loss limit breach.

FATE’s HFT path (`hft/src/obi-tape/`) derives order-book imbalance and tape
signals for paper-compatible equity experiments; `tools/hft_scalper_backtest.py`
researches short-hold edges. This informs scalping/day-trade modules without
claiming colocation-tier HFT.
""".strip(),
        formulas=(
            _F(
                "Order book imbalance (conceptual)",
                r"OBI = \frac{V_{bid} - V_{ask}}{V_{bid} + V_{ask}}",
                "Positive OBI suggests near-term upward pressure from stacked bids.",
            ),
            _F(
                "Realized spread capture",
                r"\pi = (P_{sell} - P_{buy}) - fees",
                "Per-round-trip edge after costs; must be positive at scale.",
            ),
            _F(
                "Sharpe at high frequency",
                r"Sharpe = \frac{\mu}{\sigma} \sqrt{N}",
                "Many small independent bets can compound Sharpe if correlation is low.",
                "investing.formulas.quant.sharpe_ratio",
            ),
        ),
        screens=(
            "Median hold time matches signal half-life",
            "Fee tier and rebate structure modeled",
            "Max inventory and auto-flatten on feed stall",
            "Adverse selection metric (post-fill drift)",
            "Regulatory: market maker obligations if applicable",
        ),
        traps=(
            "Backtest without queue position realism",
            "Latency regression after infra change",
            "Crowded OBI signal after publication",
            "Confusing paper HFT sim with live colocation P&L",
        ),
        catalysts=(
            "Volatility burst widening spreads for market makers",
            "Exchange fee promotion changing rebate math",
            "New listing with temporary inefficiency",
        ),
        fate_hook="`hft/src/obi-tape/obi-tape-signals.ts`; `tools/hft_scalper_backtest.py`; optional pair tilt from `analytics/hedge_fund_stack` on short horizons.",
        related=("scalping", "algo_trading", "stat_arb", "day_trading"),
        further_reading=(
            "Maureen O'Hara — Market Microstructure Theory",
            "Hasbrouck — Empirical Market Microstructure",
        ),
    )
)

register(
    DeepChapter(
        topic_id="automated_portfolio",
        title="Automated Portfolio Management",
        family="quant",
        philosophy="""
Automated portfolio management runs the full loop — signal, allocate, execute,
rebalance, report — with minimal daily human intervention. Robo-advisors popularized
the idea for retail; institutional systems scale it with tax-loss harvesting,
direct indexing, and multi-account household optimization. The benefit is
consistency; the requirement is governance: someone must set mandates, audit
models, and intervene when markets break assumptions.

Automation does not remove accountability. It concentrates it into model design,
monitoring dashboards, and incident response playbooks.
""".strip(),
        how_it_works="""
Define mandate (risk tier, universe, tax status). On schedule (daily/intraday),
refresh signals and target weights. Apply constraints: max position, sector caps,
turnover budget. Generate orders, route to broker, reconcile. Log P&L, attribution,
and drift vs policy. Alert humans on exceptions: halt, drawdown breach, data outage.

FATE’s `fortress_live.py` embodies this for the equity book: rank refresh,
confidence gates, Alpaca execution, min-hold exits, news/ML blending, and
hedge-fund stack boosts — a single automated oversight loop with env-tunable
thresholds.
""".strip(),
        formulas=(
            _F(
                "Target weight",
                r"w_i^* = \frac{rank_i^+}{\sum_j rank_j^+} \times leverage cap",
                "Normalize positive ranks to portfolio weights under gross limit.",
            ),
            _F(
                "Drift rebalance trigger",
                r"|w_i - w_i^*| > \tau \Rightarrow trade",
                "Band threshold τ avoids churn; tax-aware systems use wider bands in taxable accounts.",
            ),
            _F(
                "Inverse-vol overlay",
                r"w_i \propto \frac{rank_i^+}{\sigma_i}",
                "Optional vol-scaling within automated allocator.",
                "investing.formulas.quant.inverse_vol_weights",
            ),
        ),
        screens=(
            "Mandate document: max DD, gross/net, forbidden names",
            "Daily reconciliation broker vs ledger",
            "Signal freshness timestamps",
            "Exception queue non-empty → human review",
            "Disaster recovery: kill switch tested",
        ),
        traps=(
            "Silent model drift over months",
            "Over-trading in taxable account destroying alpha",
            "Single point of failure in cron/orchestrator",
            "Automation without drawdown circuit breakers",
        ),
        catalysts=(
            "Scheduled rebalance day (monthly/quarterly)",
            "Cash inflow triggering invest sweep",
            "Risk breach forcing de-risk auto-liquidation",
        ),
        fate_hook="Primary loop: `fortress_live.py` + `analytics/rank_pipeline.py` + `alpaca_broker.py`; satellite `analytics/day_trade_engine.py` for intraday sleeve.",
        related=("algo_trading", "quant", "robo_advisor", "buy_and_hold"),
        further_reading=(
            "Betterment / Wealthfront white papers on automated allocation",
            "CFA — Robo-advisor suitability frameworks",
        ),
    )
)
