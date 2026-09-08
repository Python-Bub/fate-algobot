"""Per-industry anchor companies — project-wide enhancement hooks + historical smoke."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from analytics.industries.base import IndustryContext


class IndustryAnchor:
    """One anchor module per industry bucket — enhances rows/scores project-wide."""

    INDUSTRY_ID: str = "unclassified"
    INDUSTRY_NAME: str = "Unclassified"
    ETF_PROXY: str = "SPY"
    ANCHOR_TICKER: str = ""
    SMOKE_TICKERS: tuple[str, ...] = ()
    HISTORICAL_START: str = "2023-01-01"
    HISTORICAL_END: str = "2024-12-31"

    def enhance_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Attach anchor metadata and a small score bump for sector leaders."""
        out = dict(row)
        sym = str(out.get("ticker") or "").upper()
        anchor_block = {
            "industry_id": self.INDUSTRY_ID,
            "anchor_ticker": self.ANCHOR_TICKER,
            "etf_proxy": self.ETF_PROXY,
            "smoke_tickers": list(self.SMOKE_TICKERS),
        }
        if sym in self.SMOKE_TICKERS:
            boost = 0.012 if sym == self.ANCHOR_TICKER else 0.006
            out["score"] = float(out.get("score") or 0.0) + boost
            anchor_block["leader_boost"] = boost
        out["industry_anchor"] = anchor_block
        return out

    def enhance_score(
        self,
        symbol: str,
        score: float,
        p_up: float,
        *,
        row: dict | None = None,
    ) -> tuple[float, float]:
        sym = symbol.strip().upper()
        s, p = float(score), float(p_up)
        if sym == self.ANCHOR_TICKER:
            s += 0.015
            p = min(1.0, p + 0.008)
        elif sym in self.SMOKE_TICKERS:
            s += 0.008
            p = min(1.0, p + 0.004)
        return s, p

    def historical_smoke(self) -> dict[str, Any]:
        """Run historical data smoke: features + industry columns + pipeline."""
        sym = self.ANCHOR_TICKER or (self.SMOKE_TICKERS[0] if self.SMOKE_TICKERS else "")
        if not sym:
            return {"industry_id": self.INDUSTRY_ID, "ok": False, "error": "no_anchor_ticker"}

        result: dict[str, Any] = {
            "industry_id": self.INDUSTRY_ID,
            "anchor": sym,
            "start": self.HISTORICAL_START,
            "end": self.HISTORICAL_END,
            "ok": True,
            "checks": [],
        }

        def _chk(name: str, ok: bool, detail: str) -> None:
            result["checks"].append({"name": name, "ok": ok, "detail": detail})
            if not ok:
                result["ok"] = False

        try:
            import os
            from feature_engineering import build_features

            # Smoke must not die on Polygon rate-limits — Yahoo first (refetchable).
            os.environ["FORCE_YAHOO_PRICES"] = "true"
            os.environ["TRAIN_FORCE_YAHOO"] = "true"
            os.environ["PRICE_DATA_SOURCE"] = "yfinance"
            df = build_features(sym, self.HISTORICAL_START, self.HISTORICAL_END)
            if df is None or len(df) < 20:
                # Open-ended end date if the fixed window came back empty
                df = build_features(sym, self.HISTORICAL_START, None)
            _chk("build_features", df is not None and len(df) >= 15, f"rows={len(df) if df is not None else 0}")
        except Exception as e:
            _chk("build_features", False, str(e))
            return result

        if df is None or len(df) < 2:
            return result

        try:
            from analytics.industry_comovement import INDUSTRY_FEATURE_COLUMNS, enrich_industry_comovement

            enriched = enrich_industry_comovement(df, sym, self.HISTORICAL_START, self.HISTORICAL_END)
            missing = [c for c in INDUSTRY_FEATURE_COLUMNS if c not in enriched.columns]
            _chk("industry_comovement", not missing, f"missing={missing[:3]}" if missing else f"cols={len(INDUSTRY_FEATURE_COLUMNS)}")
            last = enriched.iloc[-2 if len(enriched) >= 2 else -1]
            rf = {k: float(last[k]) for k in INDUSTRY_FEATURE_COLUMNS if k in last.index}
        except Exception as e:
            _chk("industry_comovement", False, str(e))
            rf = {}

        try:
            from analytics.industries.pipeline import run_industry_pipeline

            pipe = run_industry_pipeline(sym, rf, macro_bundle={"macro_score": 0.2, "pmi_score": 0.4, "vix": 20.0})
            _chk(
                "pipeline",
                pipe.get("enabled") and float(pipe.get("score_delta") or 0) > -0.5,
                f"delta={pipe.get('score_delta'):.4f}" if pipe.get("score_delta") is not None else "no_delta",
            )
        except Exception as e:
            _chk("pipeline", False, str(e))

        try:
            from analytics.industries.enhancements import get_enhancement

            enh = get_enhancement(self.INDUSTRY_ID)
            report = enh.high_level_test()
            _chk("enhancement", report.get("net_positive"), f"score={report.get('score_delta')}")
        except Exception as e:
            _chk("enhancement", False, str(e))

        try:
            from signals.train_feature_enrich import enrich_training_features

            out = enrich_training_features(enriched, sym, self.HISTORICAL_START, self.HISTORICAL_END)
            fpw = [c for c in out.columns if str(c).startswith("fpw_")]
            _chk("train_fpw", len(fpw) >= 3, f"fpw_cols={len(fpw)}")
        except Exception as e:
            _chk("train_fpw", False, str(e))

        return result
