"""Shared price-fetch policy — Polygon-first, throttled Yahoo, cache."""

from __future__ import annotations

import os


def polygon_configured() -> bool:
    return bool(os.getenv("POLYGON_API_KEY", "").strip())


def use_yahoo_first() -> bool:
    if os.getenv("USE_YAHOO_ONLY", "false").lower() in ("1", "true", "yes"):
        return True
    return os.getenv("USE_YAHOO_FIRST", "true").lower() in ("1", "true", "yes")


def use_polygon_first() -> bool:
    if not polygon_configured():
        return False
    # Explicit USE_POLYGON_FIRST wins over the Yahoo-first default.
    if os.getenv("USE_POLYGON_FIRST", "false").lower() in ("1", "true", "yes"):
        return True
    if use_yahoo_first():
        return False
    return False


def force_yahoo_prices(*, training: bool = False) -> bool:
    if os.getenv("FORCE_YAHOO_PRICES", "false").lower() in ("1", "true", "yes"):
        return True
    if training and os.getenv("TRAIN_FORCE_YAHOO", "false").lower() in ("1", "true", "yes"):
        return True
    if os.getenv("PAPER_SIM_ACTIVE_RUN", "false").lower() in ("1", "true", "yes"):
        if os.getenv("PAPER_SIM_FORCE_YAHOO", "false").lower() in ("1", "true", "yes"):
            return True
    return False


def apply_price_env_defaults(*, training: bool = False) -> None:
    """Yahoo-first by default (reliable, uncapped). Set USE_POLYGON_FIRST=true for Polygon.

    An explicit ``FORCE_YAHOO_PRICES=false`` pin (GCP paper, pytest) is never
    rewritten back to true by the Yahoo-first default.
    """
    os.environ.setdefault("USE_PRICE_CACHE", "true")
    explicit = os.getenv("FORCE_YAHOO_PRICES")
    pinned_off = explicit is not None and explicit.strip().lower() not in ("1", "true", "yes")
    if use_polygon_first() and not force_yahoo_prices(training=training):
        os.environ["PRICE_DATA_SOURCE"] = "hybrid_polygon"
        os.environ["FORCE_YAHOO_PRICES"] = "false"
        os.environ["SKIP_YAHOO_FALLBACK"] = "true"
        os.environ["PAPER_SIM_FORCE_YAHOO"] = "false"
        if training:
            os.environ["TRAIN_FORCE_YAHOO"] = "false"
        return
    if pinned_off:
        os.environ["FORCE_YAHOO_PRICES"] = "false"
        os.environ["PAPER_SIM_FORCE_YAHOO"] = "false"
        if training:
            os.environ["TRAIN_FORCE_YAHOO"] = "false"
        src = os.getenv("PRICE_DATA_SOURCE", "").strip().lower()
        if polygon_configured() or src in ("hybrid_polygon", "hybrid_alpaca"):
            os.environ.setdefault("SKIP_YAHOO_FALLBACK", "true")
            if not src:
                os.environ["PRICE_DATA_SOURCE"] = "hybrid_polygon"
        return
    if use_yahoo_first() or force_yahoo_prices(training=training):
        os.environ["PRICE_DATA_SOURCE"] = "yfinance"
        os.environ["FORCE_YAHOO_PRICES"] = "true"
        os.environ["SKIP_YAHOO_FALLBACK"] = "false"
        if training:
            os.environ["TRAIN_FORCE_YAHOO"] = "true"
        return
    if not polygon_configured():
        os.environ["PRICE_DATA_SOURCE"] = "yfinance"
        os.environ["FORCE_YAHOO_PRICES"] = "true"
        return
    os.environ["PRICE_DATA_SOURCE"] = "hybrid_polygon"
    os.environ["FORCE_YAHOO_PRICES"] = "false"
    os.environ["SKIP_YAHOO_FALLBACK"] = "true"
    os.environ["PAPER_SIM_FORCE_YAHOO"] = "false"
    if training:
        os.environ["TRAIN_FORCE_YAHOO"] = "false"


def price_fetch_blocking() -> bool:
    if os.getenv("PRICE_FETCH_BLOCK", "true").lower() in ("1", "true", "yes"):
        return True
    return os.getenv("PAPER_SIM_ACTIVE_RUN", "false").lower() in ("1", "true", "yes")


def skip_yahoo_fallback() -> bool:
    if force_yahoo_prices():
        return False
    skip_flag = os.getenv("SKIP_YAHOO_FALLBACK", "true").lower() in ("1", "true", "yes")
    paper_skip = (
        os.getenv("PAPER_SIM_ACTIVE_RUN", "false").lower() in ("1", "true", "yes")
        and os.getenv("PAPER_SIM_SKIP_YAHOO_FALLBACK", "true").lower() in ("1", "true", "yes")
        and os.getenv("PAPER_SIM_FORCE_YAHOO", "false").lower() not in ("1", "true", "yes")
    )
    if not skip_flag and not paper_skip:
        return False
    if use_polygon_first():
        return True
    src = os.getenv("PRICE_DATA_SOURCE", "").strip().lower()
    return src in ("hybrid_polygon", "hybrid_alpaca")


def paper_sim_skip_yahoo_fallback() -> bool:
    """Skip Yahoo during paper-sim unless Yahoo is explicitly forced."""
    if force_yahoo_prices():
        return False
    if os.getenv("PAPER_SIM_FORCE_YAHOO", "false").lower() in ("1", "true", "yes"):
        return False
    if os.getenv("PAPER_SIM_SKIP_YAHOO_FALLBACK", "true").lower() not in ("1", "true", "yes"):
        return skip_yahoo_fallback()
    return skip_yahoo_fallback() or os.getenv("PAPER_SIM_ACTIVE_RUN", "false").lower() in (
        "1",
        "true",
        "yes",
    )
