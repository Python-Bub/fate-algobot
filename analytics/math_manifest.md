# FATE math formula manifest

**Hard pivot:** trading decisions are driven by math (factors, residuals, cointegration, micro-scalp edge, ML on prices). News/sentiment/events are **converted** into numeric z-scores and factors — pipelines are kept, narrative intuition is not a sizer.

Python twin: `analytics/math_catalog.py` · strategy map: `analytics/strategy_registry.py` · text transforms: `intel/text_to_math.py` · weight remapper: `analytics/math_pivot.py`.

Enable with `PURE_MATH_PIVOT=true` (default on after pivot).

---

## Universal

| Id | Equation |
|----|----------|
| zscore | \(z=(x-\mu)/\sigma\); rank tilt \(\tanh(z/k)\) |

---

## Cross-company links (`analytics/cross_company_links.py`)

| Id | Equations |
|----|-----------|
| corr | Pearson / Spearman / Kendall; partial corr controlling market |
| beta+idio | \(r_i=\alpha+\beta r_{peer}+\varepsilon\); \(IR_\varepsilon=\bar\varepsilon/\sigma_\varepsilon\) |
| spread z | \(s=\log P_a-\gamma\log P_b\); \(z_s=(s-\mu_s)/\sigma_s\) |
| cointegration | Engle–Granger: ADF on residual (or ACF proxy) |
| lead–lag | \(k^*=\arg\max_k|\mathrm{corr}(r_a[t],r_b[t-k])|\) |
| tails | joint extreme rate; empirical upper/lower tail dependence |
| OU | half-life \(=-\log 2/\log|\varphi|\) on AR(1) spread |
| Hurst | R/S on spread (\(H<0.5\) mean-reverting) |

Cache: `data/intel/cross_company_links.json` → `cross_company_rank_boost`.

---

## Hidden pattern anomaly (`analytics/hidden_pattern_anomaly.py`)

1. Idiosyncratic residual spike vs market beta  
2. Volume–return divergence (z-scored)  
3. Autocorr / vol-regime break  
4. IsolationForest on return/vol/volume features  
5. Sequence-discover next-step foreshadow residual  

Cache: `data/intel/hidden_pattern_anomalies.json`.

---

## Hedge-fund stack (`analytics/hedge_fund_stack.py`)

- Momentum / value / quality / size factor tilts (tanh-bounded)  
- Trend: MA50/MA200 + MACD + RSI  
- Stat-arb pair z vs peer map  
- ETF dislocation + market-neutral tilt  
- Composite: \(\mathrm{boost}=\sum_k w_k f_k\)

---

## Value DCF (`analytics/value_investing.py`)

\[
TV=\frac{CF_n(1+g)}{r-g},\quad
IV=\sum_{t=1}^{n}\frac{CF_t}{(1+r)^t}+\frac{TV}{(1+r)^n},\quad
MoS=\frac{IV-P}{IV}
\]

Plus Graham NCAV / net-net, deep value (low P/E + P/B&lt;1), Buffett quality, contrarian tilt.

---

## Micro-scalp (`analytics/micro_scalp.py`)

\[
\mathrm{edge}=\max(N\cdot\mathrm{tick}(P),\;\mathrm{abs},\;P\cdot\mathrm{bps}/10^4)
\]

Long target \(P+\mathrm{edge}\); stop floored to tick; spread sanity gate.

---

## Sequence discover (`analytics/sequence_discover.py`)

Polynomial differences, geometric ratios, linear recurrences, cycles, power decompositions, expression-tree evolution. Feeds small bias into structure patterns when `USE_SEQUENCE_DISCOVER`.

---

## Industry comovement (`analytics/industry_comovement.py`)

Basket β, industry residual z (`industry_z_20`), leader sympathy, rate/expansion factor tilts across 300+ industry buckets.

---

## News / NLP / events → math (`intel/text_to_math.py`)

| Transform | Formula |
|-----------|---------|
| Lexicon sentiment | \(s\in[-1,1]\) from headline classifier |
| Embedding proxy | hash bag-of-tokens → unit vector · polarity (no network required) |
| Sentiment z | \(z_s=(s-\mu_{hist})/\sigma_{hist}\) |
| Event surprise | \(z_e=(\mathrm{actual}-\mathrm{consensus})/\sigma_{est}\) |
| Final factor | weighted \(\tanh\) blend of z's + reliability · (1 − contradiction) |

`intel/news_factor_engine.py` still fetches Finnhub/NewsAPI/Cramer — scores are emitted as **numeric** fields (`sentiment_z`, `event_z`, `final_factor`).

---

## ML on historical prices

- Horizon heads: calibrated RF+XGB+LGBM → \(p_{up}\), edge \(=2(p_{up}-0.5)\)  
- LSTM sequence overlay  
- Online neural ensemble from trade replay  

Subtle connections humans miss: residual IR, lead–lag, IsolationForest, sequence foreshadow, industry residual z — all additive rank boosts under risk gates.

---

## Rank wiring

`analytics/rank_pipeline.py` + `analytics/math_pivot.py`:

- When `PURE_MATH_PIVOT=true`: boost hedge_fund / hidden_anomaly / cross_company / value / structure / ML; route news through z-path with **lower narrative weight**, not removal.  
- Env multipliers: `MATH_PIVOT_MATH_MULT` (default 1.35), `MATH_PIVOT_NEWS_MULT` (default 0.55).
