"""Bottom-fisher: scan worst performers for recovery signals + news catalysts + AI review."""

from bottom_fisher.config import bottom_fisher_enabled
from bottom_fisher.integrate import bottom_fisher_score_boost, enrich_row_with_bottom_fisher
from bottom_fisher.scanner import run_bottom_fisher_scan

__all__ = [
    "bottom_fisher_enabled",
    "bottom_fisher_score_boost",
    "enrich_row_with_bottom_fisher",
    "run_bottom_fisher_scan",
]
