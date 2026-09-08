"""
Canonical math formula catalog — maps every FATE strategy to equations.

Human-readable twin: ``analytics/math_manifest.md``.
Strategy family ids align with ``analytics/strategy_registry.py``.

Hard pivot policy: news/text/events are *converted* into numeric z-scores and
factors (see ``intel/text_to_math.py``) — never deleted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FormulaEntry:
    id: str
    title: str
    strategy_ids: tuple[str, ...]
    module: str
    equations: tuple[str, ...]
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    notes: str = ""
    related: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "strategy_ids": list(self.strategy_ids),
            "module": self.module,
            "equations": list(self.equations),
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "notes": self.notes,
            "related": list(self.related),
        }


MATH_CATALOG: tuple[FormulaEntry, ...] = (
    FormulaEntry(
        "zscore",
        "Standard z-score",
        ("mean_reversion", "stat_arb_pairs", "news_sentiment", "earnings_surprise"),
        "investing/formulas/technical.py · intel/text_to_math.py",
        ("z = (x − μ) / σ", "tanh_z = tanh(z / k)  # bounded rank tilt"),
        ("x", "μ rolling mean", "σ rolling std"),
        ("z", "bounded_tilt"),
        "Universal normalize for prices, residuals, sentiment, and event surprises.",
    ),
    FormulaEntry(
        "cross_company_corr",
        "Cross-company correlation suite",
        ("cross_company_links",),
        "analytics/cross_company_links.py",
        (
            "ρ_pearson = cov(r_a, r_b) / (σ_a σ_b)",
            "ρ_spearman = pearson(rank(r_a), rank(r_b))",
            "τ_kendall = (C − D) / (n(n−1)/2)",
            "ρ_partial = (ρ_ab − ρ_am ρ_bm) / √((1−ρ_am²)(1−ρ_bm²))",
        ),
        ("log returns r_a, r_b", "market returns r_m"),
        ("corr metrics", "rank boost"),
    ),
    FormulaEntry(
        "cross_company_beta_idio",
        "Rolling beta + idiosyncratic residual",
        ("cross_company_links", "hidden_pattern_anomaly"),
        "analytics/cross_company_links.py",
        (
            "r_i = α + β r_peer + ε",
            "β̂ = cov(r_i, r_peer) / var(r_peer)",
            "ε = r_i − α̂ − β̂ r_peer",
            "IR_ε = mean(ε) / std(ε)",
        ),
        ("aligned returns"),
        ("beta", "residual", "IR"),
    ),
    FormulaEntry(
        "stat_arb_spread",
        "Log-spread z + OU half-life",
        ("stat_arb_pairs", "cross_company_links", "hedge_fund_composite"),
        "analytics/hedge_fund_stack.py · analytics/cross_company_links.py",
        (
            "s_t = log(P_a) − γ log(P_b)",
            "z_s = (s − μ_s) / σ_s",
            "s_t = φ s_{t−1} + η  ⇒  half_life = −log(2) / log(|φ|)",
            "Hurst H via R/S on spread (H < 0.5 ⇒ mean-reverting)",
        ),
        ("pair closes", "hedge ratio γ"),
        ("pair_z", "half_life", "direction"),
    ),
    FormulaEntry(
        "engle_granger",
        "Engle–Granger cointegration proxy",
        ("cross_company_links", "stat_arb_pairs"),
        "analytics/cross_company_links.py",
        (
            "P_a = α + β P_b + u",
            "ADF(u) or residual ACF decay ⇒ cointegration strength",
            "trade when |z(u)| > threshold and coint score high",
        ),
        ("price levels"),
        ("coint_score", "spread_z"),
    ),
    FormulaEntry(
        "lead_lag",
        "Lead–lag cross-correlation",
        ("cross_company_links", "industry_comovement"),
        "analytics/cross_company_links.py",
        (
            "ρ(k) = corr(r_a[t], r_b[t−k])",
            "k* = argmax_k |ρ(k)|",
            "lead_score = ρ(k*) · sign(k*)",
        ),
        ("returns"),
        ("lag", "lead_score"),
    ),
    FormulaEntry(
        "tail_dependence",
        "Tail co-move + copula-lite",
        ("cross_company_links",),
        "analytics/cross_company_links.py",
        (
            "tail_rate = P(|r_a|>q ∩ |r_b|>q) / P(|r_a|>q)",
            "upper/lower empirical tail dependence on ranked uniforms",
        ),
        ("returns", "quantile q"),
        ("tail_comove",),
    ),
    FormulaEntry(
        "hidden_idio_vol",
        "Hidden pattern: idio residual + vol divergence",
        ("hidden_pattern_anomaly",),
        "analytics/hidden_pattern_anomaly.py",
        (
            "ε_t = r_t − β̂_m r_m,t",
            "z_ε = (ε − μ_ε) / σ_ε",
            "z_vol = (σ_short − μ_σ) / σ_σ",
            "div = z(|r|) − z(vol)  # volume–return divergence",
        ),
        ("closes", "volume", "SPY"),
        ("anomaly_score", "direction"),
    ),
    FormulaEntry(
        "isolation_forest",
        "Multivariate IsolationForest outlier",
        ("hidden_pattern_anomaly",),
        "analytics/hidden_pattern_anomaly.py",
        (
            "features = [r, σ, vol_z, acf1, idio_z, …]",
            "score_IF ∝ path length anomaly (sklearn IsolationForest)",
            "blend with sequence foreshadow residual",
        ),
        ("feature window"),
        ("iforest_score",),
    ),
    FormulaEntry(
        "sequence_discover",
        "Closed-form / recurrence sequence search",
        ("sequence_discover", "structure_patterns"),
        "analytics/sequence_discover.py",
        (
            "poly: Δ^d s ≈ const ⇒ degree-d polynomial",
            "geo: s_{n+1}/s_n ≈ r ⇒ geometric",
            "recurrence: s_n = a1 s_{n−1} + … + ak s_{n−k}",
            "power: s_n ≈ base^exp with discovered sides",
            "next̂ − realized ⇒ foreshadow residual z",
        ),
        ("return / price sequence"),
        ("next_step", "fit_quality", "bias"),
    ),
    FormulaEntry(
        "hedge_fund_factors",
        "Fama–French-style factor tilts",
        ("hedge_fund_composite", "momentum_trend", "mean_reversion"),
        "analytics/hedge_fund_stack.py",
        (
            "mom = tanh(mom_5d·12)·0.55 + tanh((rs−1)·4)·0.45",
            "value = tanh((22 − PE)/22)  or fund.value_score",
            "quality = tanh(ROE·3)",
            "size = clip(−log10(mcap)/12 + 0.85)",
            "boost = Σ w_k · factor_k",
        ),
        ("row features", "fundamentals"),
        ("boost", "short_tilt"),
    ),
    FormulaEntry(
        "trend_macd_ema",
        "Trend: MA stack + MACD + RSI",
        ("momentum_trend", "hedge_fund_composite"),
        "analytics/hedge_fund_stack.py · investing/formulas/technical.py",
        (
            "trend += 0.5 · tanh((MA50/MA200 − 1)·25)",
            "MACD = EMA12 − EMA26; signal = EMA9(MACD)",
            "RSI_n = 100 − 100/(1 + avg_gain/avg_loss)",
        ),
        ("closes"),
        ("trend_score",),
    ),
    FormulaEntry(
        "dcf_intrinsic",
        "DCF intrinsic value + margin of safety",
        ("value_investing",),
        "analytics/value_investing.py",
        (
            "TV = CF_n (1+g) / (r − g)   requiring g < r",
            "IV = Σ_{t=1..n} CF_t/(1+r)^t + TV/(1+r)^n",
            "MoS = (IV − P) / IV",
            "NCAV = CA − TL; Net-Net when P < NCAV",
        ),
        ("cash flows", "r", "g", "price"),
        ("IV", "MoS", "value_boost"),
    ),
    FormulaEntry(
        "micro_scalp_edge",
        "Micro-scalp tick-aware edge",
        ("micro_scalp", "noise_harvest"),
        "analytics/micro_scalp.py",
        (
            "tick(P) = 0.01 if P≥1 else 0.001 if P≥0.1 else 0.0001",
            "edge = max(N·tick, abs_want, P·bps/10000)",
            "target_long = round(P + edge); stop = P − stop_dist",
            "spread sanity: quote_is_sane(bid, ask)",
        ),
        ("mid/bid", "spread"),
        ("entry", "target", "stop"),
    ),
    FormulaEntry(
        "industry_comovement",
        "Industry basket beta + residual z",
        ("industry_comovement",),
        "analytics/industry_comovement.py",
        (
            "β_ind = cov(r_i, r_basket) / var(r_basket)",
            "ε_ind = r_i − β_ind r_basket",
            "z_ind = (ε_ind − μ) / σ over 20d",
            "sympathy = f(leader_momentum, peer_corr)",
        ),
        ("symbol returns", "industry panel"),
        ("industry_z_20", "sympathy_score"),
    ),
    FormulaEntry(
        "news_to_z",
        "News / NLP → numeric z (math pivot)",
        ("news_sentiment", "earnings_surprise"),
        "intel/text_to_math.py · intel/news_factor_engine.py",
        (
            "s = lexicon_score(headline) ∈ [−1,1]",
            "emb_proxy = hash_bag_of_tokens → unit vector · polarity",
            "z_sent = (s − μ_hist) / σ_hist   (or s/σ0 if cold)",
            "surprise_z = (actual − consensus) / σ_est",
            "final_math = w_s·tanh(z_sent) + w_e·tanh(surprise_z) + …",
        ),
        ("headlines", "EPS/rev actual vs consensus"),
        ("sentiment_z", "event_z", "final_factor"),
        "Pipelines stay; narrative never sizes alone — only z/factors do.",
        ("zscore",),
    ),
    FormulaEntry(
        "ml_horizon",
        "ML calibrated horizon heads",
        ("ml_horizon_heads", "lstm_sequence", "neural_ensemble"),
        "ml_model.py · analytics/lstm_head.py",
        (
            "p_up = CalibratedClassifier(RF ⊕ XGB ⊕ LGBM)",
            "edge = 2(p_up − 0.5)",
            "LSTM overlay blends sequence log-odds into p_up",
        ),
        ("historical price/features"),
        ("p_up", "edge"),
    ),
    FormulaEntry(
        "obi_microprice",
        "Order-book imbalance / micro-price",
        ("obi_tape", "micro_mean_reversion"),
        "hft/src/obi-tape/",
        (
            "OBI = (Σ w_i bid_i − Σ w_i ask_i) / (Σ w_i bid_i + Σ w_i ask_i)",
            "micro_price ≈ (ask·V_bid + bid·V_ask) / (V_bid + V_ask)",
        ),
        ("L2 book", "tape"),
        ("obi", "burst"),
    ),
    FormulaEntry(
        "logit_evidence_algebra",
        "LogitEvidence Algebra (LEA) — vector probability fusion",
        ("ml_horizon_heads", "hidden_pattern_anomaly", "news_sentiment"),
        "analytics/vector_math.py · multi_algo_fusion.py",
        (
            "ℓ = logit(p) = log(p/(1−p))",
            "ℓ_fuse = Σ_i w_i · ℓ_i   (or LSE(ℓ_i + log w_i) − LSE(log w_i))",
            "p_fuse = σ(ℓ_fuse)",
            "motif: sim_i = ⟨q̃, w̃_i⟩  → top-k softmax-weighted forward return",
            "rolling μ/σ via cumsum; IsolationForest features as matrix rows",
        ),
        ("p_up sources", "returns windows", "lexicon tokens"),
        ("p_fuse", "motif_fwd", "anomaly features"),
        "Weights act on log-odds evidence, not raw probabilities — more precise near 0/1.",
        ("ml_horizon", "hidden_idio_vol", "text_to_math"),
    ),
    FormulaEntry(
        "precision_weighted_combination",
        "Precision-weighted forecast combination (Bates–Granger / Grinold)",
        ("ml_horizon_heads", "fortress_live", "hedge_fund_stack"),
        "analytics/vector_math.py",
        (
            r"w_i \propto skill_i / \sigma_i^2",
            r"\sum_i w_i = 1,\quad w_i \ge 0",
            r"\ell_{fuse} = \sum_i w_i \logit(p_i),\quad p^* = \sigma(\ell_{fuse})",
            r"agree = \min_i (2(p_i-1/2)\cdot\mathrm{sign}(p_{ref}-1/2))_+",
        ),
        ("horizon p_i", "factor scores", "exec certainty"),
        ("p_fuse", "normalized weights", "agree_score"),
        "Noisy or disagreeing heads cannot dominate via raw env scale. Copies of fused p are not agreement.",
        ("logit_evidence_algebra", "ultimate_learning_engine", "ml_horizon"),
    ),
    FormulaEntry(
        "ultimate_learning_engine",
        "Ultimate Learning Engine — sole learned LEA hub",
        ("fortress_live", "paper_sim", "hidden_pattern", "neural_ensemble"),
        "analytics/ultimate_learning_engine.py · vector_math.py",
        (
            "skill_i ← clip( skill_i · (1 ± η · reward) )",
            "w_i = softmax( skill / T )",
            "ℓ_fuse = Σ_{i∈ABS} (w_i·m_i) · logit(p_i)   # base,hidden,neural,lstm,crowd,news",
            "ℓ* = ℓ_fuse + Σ_{j∈REL} α_j · Δℓ_j         # overlay/cortex/regime via Δp→Δℓ",
            "p* = σ(ℓ*)",
            "Δℓ = logit(clip(p+Δp)) − logit(p)   |   factor→p = ½+½ tanh(s·x)",
        ),
        ("raw model p_i", "pattern p_pat", "neural/lstm p", "tilts", "crowd/news factors"),
        ("p_star", "skill weights", "active channels"),
        "Producers emit evidence only; ULE is the only fuse. Calibrate/Kelly after p*.",
        ("logit_evidence_algebra", "zscore", "hidden_idio_vol", "news_to_z", "ml_horizon"),
    ),
)


def catalog_by_id() -> dict[str, FormulaEntry]:
    return {e.id: e for e in MATH_CATALOG}


def formulas_for_strategy(strategy_id: str) -> list[FormulaEntry]:
    sid = strategy_id.strip().lower()
    return [e for e in MATH_CATALOG if sid in e.strategy_ids]


def all_equations() -> list[tuple[str, str]]:
    """Flat (formula_id, equation) list for docs / doc-chat summaries."""
    out: list[tuple[str, str]] = []
    for e in MATH_CATALOG:
        for eq in e.equations:
            out.append((e.id, eq))
    return out


def catalog_summary(max_entries: int = 12) -> str:
    lines = [f"Math catalog: {len(MATH_CATALOG)} formula families"]
    for e in MATH_CATALOG[:max_entries]:
        eq0 = e.equations[0] if e.equations else ""
        lines.append(f"- {e.id}: {eq0}")
    if len(MATH_CATALOG) > max_entries:
        lines.append(f"… +{len(MATH_CATALOG) - max_entries} more (see math_manifest.md)")
    return "\n".join(lines)
